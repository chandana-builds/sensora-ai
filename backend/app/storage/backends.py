"""Two interchangeable low-level backends with the same tiny API: SQLite (dev / single instance) and
Supabase PostgREST (production). Operators in `where`: key or key__lt (e.g. expires_at__lt)."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import StoreError, StoreUnavailable

PREFIX = "sensora_"
JSON_COLS = {"sessions": {"data"}, "messages": {"metadata"}, "steps": {"data"}, "prefs": {"data"}}
BOOL_COLS = {"observations": {"simulated"}, "prefs": {"remember_level"}}
BLOB_COLS = {"evidence": {"data"}}
_IDENT = re.compile(r"^[a-z_]+$")

SQLITE_SCHEMA = """
create table if not exists sensora_sessions (owner text not null, id text not null, seq integer not null, created_at text not null, data text not null, primary key (owner, id));
create table if not exists sensora_messages (id text primary key, owner text not null, sid text not null, seq integer not null, created_at text not null, role text not null, content text not null, metadata text not null);
create index if not exists ix_msg on sensora_messages(owner, sid, seq);
create table if not exists sensora_steps (id text primary key, owner text not null, sid text not null, seq integer not null, created_at text not null, data text not null);
create index if not exists ix_steps on sensora_steps(owner, sid, seq);
create table if not exists sensora_observations (id text primary key, owner text not null, sid text not null, seq integer not null, created_at text not null, text text not null, simulated integer not null);
create index if not exists ix_obs on sensora_observations(owner, sid, seq);
create table if not exists sensora_evidence (id text primary key, owner text not null, sid text not null, seq integer not null, note text, size integer not null, captured_at text not null, expires_at text not null, data blob not null);
create index if not exists ix_ev on sensora_evidence(owner, sid);
create table if not exists sensora_prefs (owner text primary key, user_level text, remember_level integer not null default 0, data text);
create table if not exists sensora_users (id text primary key, email text unique not null, password_hash text not null, display_name text, created_at text not null);
"""


class SQLiteBackend:
    name = "sqlite"

    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.RLock()
        try:
            self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            if path != ":memory:":
                self.conn.execute("pragma journal_mode=wal")
            self.conn.executescript(SQLITE_SCHEMA)
            try:
                self.conn.execute("alter table sensora_prefs add column data text")
            except sqlite3.OperationalError:
                pass
        except sqlite3.Error as e:
            raise StoreUnavailable(f"cannot open SQLite database: {e}") from e

    @staticmethod
    def _where(where: dict[str, Any]) -> tuple[str, list[Any]]:
        parts, args = [], []
        for k, v in where.items():
            col, op = (k[:-4], "<") if k.endswith("__lt") else (k, "=")
            assert _IDENT.match(col)
            parts.append(f"{col} {op} ?")
            args.append(v)
        return (" where " + " and ".join(parts)) if parts else "", args

    def _enc(self, t: str, row: dict[str, Any]) -> dict[str, Any]:
        return {k: ((json.dumps(v) if v is not None else None) if k in JSON_COLS.get(t, ()) else int(v) if k in BOOL_COLS.get(t, ()) else v) for k, v in row.items()}

    def _dec(self, t: str, row: dict[str, Any]) -> dict[str, Any]:
        return {k: ((json.loads(v) if v is not None else None) if k in JSON_COLS.get(t, ()) else bool(v) if k in BOOL_COLS.get(t, ()) else v) for k, v in row.items()}

    def _run(self, sql: str, args: list[Any]):
        try:
            with self._lock:
                return self.conn.execute(sql, args)
        except sqlite3.Error as e:
            raise StoreUnavailable(f"database error: {e}") from e

    def insert(self, t: str, row: dict[str, Any]) -> dict[str, Any]:
        r = self._enc(t, row)
        cols = list(r)
        assert all(_IDENT.match(c) for c in cols)
        self._run(f"insert into {PREFIX}{t} ({','.join(cols)}) values ({','.join('?' * len(cols))})", [r[c] for c in cols])
        return dict(row)

    def select(self, t: str, where: dict[str, Any], order: str | None = None, limit: int | None = None, columns: list[str] | None = None) -> list[dict[str, Any]]:
        w, args = self._where(where)
        cols = ",".join(columns) if columns else "*"
        sql = f"select {cols} from {PREFIX}{t}{w}"
        if order:
            c, _, d = order.partition(".")
            assert _IDENT.match(c)
            sql += f" order by {c} {'desc' if d == 'desc' else 'asc'}"
        if limit:
            sql += f" limit {int(limit)}"
        with self._lock:
            cur = self._run(sql, args)
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
        return [self._dec(t, r) for r in rows]

    def update(self, t: str, where: dict[str, Any], values: dict[str, Any]) -> int:
        v = self._enc(t, values)
        w, wargs = self._where(where)
        return self._run(f"update {PREFIX}{t} set {','.join(f'{k}=?' for k in v)}{w}", [*v.values(), *wargs]).rowcount

    def delete(self, t: str, where: dict[str, Any]) -> int:
        w, args = self._where(where)
        return self._run(f"delete from {PREFIX}{t}{w}", args).rowcount

    def count(self, t: str, where: dict[str, Any]) -> int:
        w, args = self._where(where)
        return self._run(f"select count(*) from {PREFIX}{t}{w}", args).fetchone()[0]

    def ping(self) -> None:
        self._run("select 1", [])

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self.conn.execute(
                "select id, email, password_hash, display_name, created_at from sensora_users where lower(email) = ?",
                (email.lower().strip(),),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "email": row[1],
                    "password_hash": row[2],
                    "display_name": row[3],
                    "created_at": row[4],
                }
            return None

    def create_user(self, user_id: str, email: str, password_hash: str, display_name: str) -> dict[str, Any]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.conn.execute(
                "insert into sensora_users (id, email, password_hash, display_name, created_at) values (?, ?, ?, ?, ?)",
                (user_id, email.lower().strip(), password_hash, display_name, now),
            )
        return {
            "id": user_id,
            "email": email.lower().strip(),
            "display_name": display_name,
            "created_at": now,
        }


class PostgRESTBackend:
    """Supabase REST (PostgREST) with the service-role key. RLS is on with no policies, so only this backend can read/write."""
    name = "supabase"

    def __init__(self, url: str, service_key: str, *, timeout: float = 8.0) -> None:
        self.base, self.key, self.timeout = url.rstrip("/") + "/rest/v1", service_key, timeout

    def _call(self, method: str, t: str, params: list[tuple[str, str]], body: Any = None, want: bool = True):
        url = f"{self.base}/{PREFIX}{t}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if want:
            headers["Prefer"] = "return=representation"
        req = urllib.request.Request(url, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) or e.code >= 500:
                raise StoreUnavailable(f"database returned HTTP {e.code}") from e
            raise StoreError(f"database rejected the request (HTTP {e.code})") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise StoreUnavailable("database unreachable") from e
        return json.loads(raw) if raw else []

    @staticmethod
    def _filters(where: dict[str, Any]) -> list[tuple[str, str]]:
        out = []
        for k, v in where.items():
            col, op = (k[:-4], "lt") if k.endswith("__lt") else (k, "eq")
            assert _IDENT.match(col)
            out.append((col, f"{op}.{v}"))
        return out

    @staticmethod
    def _enc(t: str, row: dict[str, Any]) -> dict[str, Any]:
        return {k: ("\\x" + v.hex() if k in BLOB_COLS.get(t, ()) and isinstance(v, (bytes, bytearray)) else v) for k, v in row.items()}

    def insert(self, t, row):
        self._call("POST", t, [], self._enc(t, row))
        return dict(row)

    def select(self, t, where, order=None, limit=None, columns=None):
        p = [("select", ",".join(columns) if columns else "*"), *self._filters(where)]
        if order:
            p.append(("order", order))
        if limit:
            p.append(("limit", str(int(limit))))
        return self._call("GET", t, p, want=False)

    def update(self, t, where, values):
        return len(self._call("PATCH", t, self._filters(where), self._enc(t, values)))

    def delete(self, t, where):
        return len(self._call("DELETE", t, self._filters(where)))

    def count(self, t, where):
        return len(self.select(t, where, columns=["id" if t != "prefs" else "owner"]))

    def ping(self):
        self._call("GET", "prefs", [("select", "owner"), ("limit", "1")], want=False)
