import { useEffect, useState } from "react";
import { deleteSession, listSessions, type SessionRow } from "../api/sessions";

const STATUS: Record<string, string> = { resolved_verified: "Resolved (verified)", resolved_unverified: "Resolved (your report)", escalated: "Escalated", unresolved: "Unresolved", abandoned: "Ended early" };

export default function SessionHistory({ onOpen, refreshKey = 0 }: { onOpen: (id: string) => void; refreshKey?: number }) {
  const [rows, setRows] = useState<SessionRow[] | null>(null); const [err, setErr] = useState<string | null>(null);
  const load = () => { setErr(null); listSessions().then(setRows).catch((e: Error) => { setErr(e.message); setRows([]); }); };
  useEffect(load, [refreshKey]);
  async function remove(id: string) {
    if (!window.confirm("Delete this session and everything saved with it? This can't be undone.")) return;
    try { await deleteSession(id); load(); } catch (e) { setErr((e as Error).message); }
  }
  if (rows === null) return <p role="status">Loading sessions…</p>;
  return (
    <section aria-label="Session history">
      {err && <p role="alert" className="err">{err} <button onClick={load}>Retry</button></p>}
      {rows.length === 0 && !err && <p className="empty">No sessions yet. Start one to see it here.</p>}
      <ul className="sessions">{rows.map((s) => (
        <li key={s.id}>
          <button className="linkish" onClick={() => onOpen(s.id)}>
            <strong>{s.title || s.device_name || "Untitled session"}</strong> <span>{(s.problem ?? "").slice(0, 80)}</span><br />
            <small>{new Date(s.created_at).toLocaleString()} · {s.final_status ? STATUS[s.final_status] ?? s.final_status : s.workflow_state.replace(/_/g, " ")}</small>
          </button>
          <button className="secondary" aria-label={`Delete session ${s.title ?? s.id}`} onClick={() => void remove(s.id)}>Delete</button>
        </li>))}
      </ul>
    </section>
  );
}
