"""Tiny stdlib fake of Supabase PostgREST + Auth, to exercise our REST/auth code paths offline.
It validates request SHAPE against our understanding of the API; it is not a substitute for a real Supabase test."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class FakeSupabase:
    def __init__(self, service_key="svc-key", anon_key="anon-key", good_token="good-token"):
        self.tables, self.service_key, self.anon_key, self.good_token = {}, service_key, anon_key, good_token
        self.fail_status = None
        self.requests = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=None):
                raw = json.dumps(body).encode() if body is not None else b""
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self):
                u = urlparse(self.path)
                fake.requests.append((self.command, u.path, dict(self.headers)))
                if fake.fail_status:
                    return self._send(fake.fail_status, {"message": "boom"})
                if u.path == "/auth/v1/user":
                    ok = self.headers.get("apikey") == fake.anon_key and self.headers.get("Authorization") == f"Bearer {fake.good_token}"
                    return self._send(200, {"id": "11111111-aaaa"}) if ok else self._send(401, {"msg": "bad jwt"})
                if self.headers.get("apikey") != fake.service_key or self.headers.get("Authorization") != f"Bearer {fake.service_key}":
                    return self._send(401, {"message": "invalid key"})
                table = u.path.rsplit("/", 1)[-1]
                rows = fake.tables.setdefault(table, [])
                q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                want = "return=representation" in (self.headers.get("Prefer") or "")

                def match(r):
                    for k, v in q.items():
                        if k in ("select", "order", "limit"):
                            continue
                        op, _, val = v.partition(".")
                        if op == "eq" and str(r.get(k)) != val:
                            return False
                        if op == "lt" and not str(r.get(k)) < val:
                            return False
                    return True
                if self.command == "POST":
                    rows.append(body)
                    return self._send(201, [body] if want else None)
                hit = [r for r in rows if match(r)]
                if self.command == "PATCH":
                    for r in hit:
                        r.update(body)
                    return self._send(200, hit if want else None)
                if self.command == "DELETE":
                    fake.tables[table] = [r for r in rows if not match(r)]
                    return self._send(200, hit if want else None)
                if "order" in q:
                    col, _, d = q["order"].partition(".")
                    hit.sort(key=lambda r: r[col], reverse=d == "desc")
                if "limit" in q:
                    hit = hit[: int(q["limit"])]
                cols = q.get("select", "*")
                if cols != "*":
                    hit = [{c: r[c] for c in cols.split(",")} for r in hit]
                self._send(200, hit)
            do_GET = do_POST = do_PATCH = do_DELETE = _handle

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
