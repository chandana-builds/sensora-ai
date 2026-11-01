import { useEffect, useState } from "react";
import { getAiStatus, type AIStatus } from "../api/live";

/** Always-visible indicator so nobody mistakes simulated demo output for live Meta model output. */
export default function ModeBadge() {
  const [s, setS] = useState<AIStatus | null>(null); const [err, setErr] = useState(false);
  useEffect(() => { getAiStatus().then(setS).catch(() => setErr(true)); }, []);
  if (err) return <span className="badge badge-warn" role="status">Server unreachable</span>;
  if (!s) return <span className="badge" role="status">Checking…</span>;
  return s.simulated
    ? <span className="badge badge-demo" role="status" title={s.note}>DEMO MODE · simulated, not real AI</span>
    : <span className="badge badge-live" role="status" title={`${s.reasoning} / ${s.vision} / ${s.transcription}`}>LIVE · Meta models</span>;
}
