import { useEffect, useState } from "react";
import { getMemory, type Memory } from "../api/sessions";
import HandoffPanel from "./HandoffPanel";

export default function SessionView({ sessionId, onResume }: { sessionId: string; onResume: () => void }) {
  const [m, setM] = useState<Memory | null>(null); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setM(null); getMemory(sessionId).then(setM).catch((e: Error) => setErr(e.message)); }, [sessionId]);
  if (err) return <p role="alert" className="err">{err}</p>;
  if (!m) return <p role="status">Loading session…</p>;
  return (
    <article>
      <h2>{m.session.title || m.session.device_name || "Session"}</h2>
      <p>Original issue: {m.session.problem ?? "not recorded"}</p>
      <button onClick={onResume}>Resume this session</button>
      <h3>Transcript</h3>
      <ol className="transcript">{m.messages.map((x) => <li key={x.id}><strong>{x.role === "user" ? "You" : "Sensora"}{x.metadata?.simulated ? " (simulated)" : ""}:</strong> {x.content}</li>)}</ol>
      <h3>Steps attempted</h3>
      {m.steps.length === 0 ? <p className="empty">No steps yet.</p> :
        <ul>{m.steps.map((s) => <li key={s.id}>{s.title}: you reported done <strong>{s.user_reported_complete ? "yes" : "no"}</strong>, verified on camera <strong>{s.visually_verified ? "yes" : "no"}</strong> ({s.verification_outcome.replace(/_/g, " ")})</li>)}</ul>}
      <h3>Observations (unconfirmed)</h3>
      {m.observations.length === 0 ? <p className="empty">None recorded.</p> : <ul>{m.observations.map((o) => <li key={o.text}>{o.simulated ? "[simulated] " : ""}{o.text}</li>)}</ul>}
      <HandoffPanel sessionId={sessionId} />
    </article>
  );
}
