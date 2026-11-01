import { useEffect, useState } from "react";
import { completeSession, exportHandoff, getHandoff, getSummary, type Handoff, type Pathway, type Summary } from "../api/agent";

export default function HandoffPanel({ sessionId }: { sessionId: string }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [h, setH] = useState<Handoff | null>(null);
  const [pathway, setPathway] = useState<Pathway>("local_technician");
  const [withEvidence, setWithEvidence] = useState(false);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const guard = async (fn: () => Promise<void>) => { setBusy(true); setErr(null); try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  useEffect(() => { void guard(async () => setSummary((await getSummary(sessionId)).summary)); }, [sessionId]);

  return (
    <section className="lc-ai" aria-label="Summary and technician report">
      <h3>Session summary</h3>
      {!summary ? <p className="lc-empty">{err ?? "Loading…"}</p> : <>
        {summary.simulated && <p className="lc-warn-text">Contains simulated demo content.</p>}
        <p><strong>{summary.device}</strong>: {summary.issue}</p>
        <p>Status: <strong>{summary.status}</strong></p>
        <ul>{summary.steps.map((s, i) => <li key={i}>{s.title}: {s.outcome_label} (you reported: {s.user_reported_complete ? "yes" : "no"}, verified on camera: {s.visually_verified ? "yes" : "no"})</li>)}</ul>
        <p className="lc-hint">Next: {summary.recommended_next}</p>
      </>}
      <div className="lc-row">
        <button className="secondary" disabled={busy} onClick={() => void guard(async () => { setSummary(await completeSession(sessionId)); })}>End session &amp; save summary</button>
      </div>

      <h3>Technician report</h3>
      <p className="lc-note">Sensora does not contact or book anyone. This creates a report you can download and send yourself.</p>
      <div className="lc-row">
        <select value={pathway} onChange={(e) => setPathway(e.target.value as Pathway)} aria-label="Who is it for">
          <option value="local_technician">Local technician</option><option value="remote_expert">Remote human expert</option></select>
        <label><input type="checkbox" checked={withEvidence} onChange={(e) => setWithEvidence(e.target.checked)} /> List my saved evidence frames</label>
        <button disabled={busy} onClick={() => void guard(async () => setH(await getHandoff(sessionId, pathway, withEvidence)))}>Preview report</button>
      </div>
      {h && <div className="lc-step">
        <strong>{h.title}</strong> ({h.pathway_label})
        {h.disclaimers.map((d) => <p key={d} className="lc-note">{d}</p>)}
        <h4>Possible causes (unconfirmed)</h4><ul>{h.possible_causes.map((c) => <li key={c.cause}>{c.cause} <em>({c.likelihood}, unconfirmed)</em></li>)}</ul>
        <h4>Unresolved questions</h4><ul>{h.unresolved_questions.map((q) => <li key={q}>{q}</li>)}</ul>
        <h4>Safety concerns</h4><ul>{(h.safety_concerns.length ? h.safety_concerns : ["None flagged"]).map((q) => <li key={q}>{q}</li>)}</ul>
        <p className="lc-note">{h.evidence_note}</p>
        <label><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> I agree to export this report so I can share it with the technician or expert.</label>
        <div className="lc-row">{(["md", "html"] as const).map((f) => (
          <button key={f} disabled={!agree || busy} onClick={() => void guard(() => exportHandoff(sessionId, { pathway, include_evidence: withEvidence, format: f }))}>
            Download .{f}</button>))}
          <button className="secondary" disabled={!agree} onClick={() => window.print()}>Print</button></div>
      </div>}
      {err && <p className="lc-err" role="alert">{err}</p>}
    </section>
  );
}
