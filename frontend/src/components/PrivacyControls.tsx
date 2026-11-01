import { useState } from "react";
import { deleteEvidence, setEvidenceConsent } from "../api/agent";

export default function PrivacyControls({ sessionId }: { sessionId: string }) {
  const [on, setOn] = useState(false);
  const [info, setInfo] = useState<{ retention_days: number; max_frames: number } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function toggle(v: boolean) {
    setErr(null); setMsg(null);
    try {
      const r = await setEvidenceConsent(sessionId, v);
      setOn(r.evidence_consent); setInfo(r);
      setMsg(v ? "Saved. Only frames you capture and send are kept." : `Consent withdrawn. ${r.deleted_frames} saved frame(s) deleted.`);
    } catch (e) { setErr((e as Error).message); }
  }
  async function wipe() {
    setErr(null);
    try { const r = await deleteEvidence(sessionId); setMsg(`${r.deleted_frames} saved frame(s) deleted.`); } catch (e) { setErr((e as Error).message); }
  }
  return (
    <section className="lc-ai" aria-label="Privacy">
      <h3>Privacy</h3>
      <label><input type="checkbox" checked={on} onChange={(e) => void toggle(e.target.checked)} /> Keep the camera frames I send as evidence for this session</label>
      <p className="lc-note">By default nothing visual is stored. If you agree, only the individual frames you capture are kept (never video)
        {info ? `, up to ${info.max_frames} per session, for ${info.retention_days} days` : ", with a limit per session and an expiry date"}.
        Turning this off deletes them. They are only included in a technician report if you choose that and agree to share.</p>
      <button className="secondary" onClick={() => void wipe()}>Delete saved frames now</button>
      {msg && <p className="lc-note" role="status">{msg}</p>}{err && <p className="lc-err" role="alert">{err}</p>}
    </section>
  );
}
