import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Clock,
  Square,
  ArrowRight,
  ShieldAlert,
  Video,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import { ConnectionPill, EmptyState, ErrorBlock, LoadingBlock, Modal } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useAsync } from "../hooks/useAsync";
import { formatElapsed } from "../lib/format";
import type { CompletionStatus, SafetyAssessment, SessionCreated, SessionDetail } from "../types";
import LiveConsole from "../components/LiveConsole";
import PrivacyControls from "../components/PrivacyControls";

/* ── Setup: nothing is created until the user presses Start ─────────────── */
function Setup() {
  const navigate = useNavigate();
  const { prefs, connection, retryConnection } = useApp();
  const [device, setDevice] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createSession({
        device_name: device.trim() || undefined,
        problem_description: problem.trim() || undefined,
      });
      navigate(`/live/${created.id}`, { replace: true, state: { created } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the session.");
      setBusy(false);
    }
  }

  return (
    <div className="container page narrow">
      <div className="mb-4">
        <p className="eyebrow">Interactive Live Diagnostics</p>
        <h1 className="text-2xl font-bold">Start a Troubleshooting Session</h1>
        <p className="lead text-slate-600">
          Describe what's not working. You can show the device and discuss symptoms once the live workspace opens.
        </p>
      </div>

      <form className="card block-card" onSubmit={start}>
        <div className="form-group">
          <label htmlFor="setup-device">Device Name or Category (Optional)</label>
          <input
            id="setup-device"
            type="text"
            value={device}
            maxLength={120}
            onChange={(e) => setDevice(e.target.value)}
            placeholder="e.g. Asus RT-AX58U Router, LG Washing Machine, HP Monitor"
          />
        </div>

        <div className="form-group">
          <label htmlFor="setup-problem">What problem are you experiencing? (Optional)</label>
          <textarea
            id="setup-problem"
            rows={4}
            value={problem}
            maxLength={4000}
            onChange={(e) => setProblem(e.target.value)}
            placeholder="e.g. The power LED is solid red and there is no Wi-Fi broadcast signal after the storm."
          />
        </div>

        <div className="flex items-center justify-between text-xs text-slate-500 mb-4 pt-2 border-t border-slate-100">
          <span>Active mode: <strong className="capitalize text-slate-700">{prefs.experience_level}</strong> (changeable in Settings)</span>
          <span className="flex items-center gap-1">
            <ShieldAlert size={14} className="text-amber-600" />
            <span>Hazard detection active</span>
          </span>
        </div>

        {connection === "offline" && (
          <div className="flex items-center justify-between gap-3 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-sm mb-4" role="alert">
            <span>The API is currently unreachable. Make sure the backend server is running on port 8000.</span>
            <button
              type="button"
              onClick={() => retryConnection()}
              className="px-3 py-1 bg-white border border-rose-300 rounded text-rose-700 font-medium hover:bg-rose-100 transition whitespace-nowrap text-xs shadow-sm cursor-pointer"
            >
              Retry Connection
            </button>
          </div>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}

        <button className="btn btn-primary btn-large btn-block" disabled={busy || connection === "offline"}>
          {busy ? (
            <>
              <span className="spinner spinner-sm" />
              <span>Initializing Workspace...</span>
            </>
          ) : (
            <>
              <Video size={18} />
              <span>Launch Live Workspace</span>
              <ArrowRight size={18} />
            </>
          )}
        </button>
      </form>
    </div>
  );
}

/* ── Session loader ─────────────────────────────────────────────────────── */
function SessionLoader({ id }: { id: string }) {
  const location = useLocation();
  const created = (location.state as { created?: SessionCreated } | null)?.created;
  const { data, error, loading, reload } = useAsync<SessionDetail>(
    () => created && created.id === id
      ? Promise.resolve({ ...created, messages: [], steps: [], summary: null })
      : api.getSession(id),
    [id],
  );
  if (loading) return <div className="container page"><LoadingBlock label="Loading session…" /></div>;
  if (error || !data) {
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <div className="container page">
        {missing
          ? <div className="card"><EmptyState title="Session not found" action={<Link to="/dashboard" className="btn btn-primary">Go to dashboard</Link>}>It may have been deleted.</EmptyState></div>
          : <ErrorBlock error={error ?? new Error("Could not load the session.")} onRetry={reload} />}
      </div>
    );
  }
  if (data.status !== "active") return <Navigate to={`/history/${id}`} replace />;
  return <Workspace detail={data} initialSafety={created?.id === id ? created.safety : null} />;
}

function useElapsed(startIso: string): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(t); }, []);
  return (now - new Date(startIso).getTime()) / 1000;
}

const OUTCOMES: { value: CompletionStatus; label: string; help: string }[] = [
  { value: "resolved", label: "Resolved", help: "The problem is fixed and verified." },
  { value: "unresolved", label: "Not resolved", help: "Still malfunctioning; keep record of diagnostic steps." },
  { value: "escalated", label: "Needs professional technician", help: "Hazardous or requires specialized equipment." },
  { value: "abandoned", label: "Ending early", help: "Exiting without a diagnostic conclusion." },
];

/* ── Workspace ──────────────────────────────────────────────────────────── */
function Workspace({ detail }: { detail: SessionDetail; initialSafety: SafetyAssessment | null }) {
  const navigate = useNavigate();
  const { prefs } = useApp();
  const elapsed = useElapsed(detail.started_at);

  const [endOpen, setEndOpen] = useState(false);
  const [outcome, setOutcome] = useState<CompletionStatus>("resolved");
  const [notes, setNotes] = useState("");
  const [unresolved, setUnresolved] = useState("");
  const [ending, setEnding] = useState(false);
  const [endError, setEndError] = useState<string | null>(null);

  function openEnd() {
    setEndError(null);
    setEndOpen(true);
  }

  async function endSession() {
    setEnding(true);
    setEndError(null);
    try {
      await api.completeSession(detail.id, {
        status: outcome,
        summary: notes.trim() || undefined,
        unresolved_issues: unresolved.split("\n").map((l) => l.trim()).filter(Boolean),
      });
      navigate(`/history/${detail.id}`, { replace: true });
    } catch (err) {
      setEndError(err instanceof Error ? err.message : "Could not end the session.");
      setEnding(false);
    }
  }

  return (
    <div className="container page">
      <header className="live-head card mb-4">
        <div>
          <p className="eyebrow">Active Workspace</p>
          <h1 className="text-xl font-bold m-0">{detail.title || detail.device_name || "Diagnostic Session"}</h1>
        </div>
        <div className="live-status flex items-center gap-3">
          <span className="badge badge-active">Active</span>
          <span className="badge">
            <Clock size={13} className="text-slate-400" />
            <span>{formatElapsed(elapsed)}</span>
          </span>
          <ConnectionPill />
          <button className="btn btn-danger btn-small" onClick={openEnd}>
            <Square size={13} />
            <span>Complete Session</span>
          </button>
        </div>
      </header>

      <div className="card block-card p-5 mb-4">
        <LiveConsole
          sessionId={detail.id}
          userLevel={prefs.experience_level}
          deviceName={detail.device_name || undefined}
          problemDescription={detail.problem_description || (detail as unknown as { problem?: string }).problem || undefined}
          initialMessages={detail.messages}
        />
      </div>

      <div className="card block-card p-5">
        <PrivacyControls sessionId={detail.id} />
      </div>

      {endOpen && (
        <Modal title="Complete this session" onClose={() => !ending && setEndOpen(false)}>
          <fieldset className="outcomes mb-4">
            <legend className="font-semibold text-slate-800 text-sm mb-2">Diagnostic Outcome</legend>
            {OUTCOMES.map((o) => (
              <label key={o.value} className={`radio-card ${outcome === o.value ? "selected" : ""}`}>
                <input type="radio" name="outcome" checked={outcome === o.value} onChange={() => setOutcome(o.value)} />
                <strong>{o.label}</strong>
                <span className="text-xs text-slate-500">{o.help}</span>
              </label>
            ))}
          </fieldset>
          <div className="form-group">
            <label htmlFor="end-notes">Resolution Notes (Optional)</label>
            <textarea
              id="end-notes"
              rows={3}
              value={notes}
              maxLength={2000}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What step fixed it, or what symptoms remain?"
            />
          </div>
          <div className="form-group">
            <label htmlFor="end-unresolved">Still Unresolved (Optional, one per line)</label>
            <textarea
              id="end-unresolved"
              rows={2}
              value={unresolved}
              onChange={(e) => setUnresolved(e.target.value)}
              placeholder="e.g. 5GHz radio still non-responsive"
            />
          </div>
          {endError && <p className="form-error" role="alert">{endError}</p>}
          <div className="modal-actions">
            <button className="btn btn-secondary" onClick={() => setEndOpen(false)} disabled={ending}>
              Resume Session
            </button>
            <button className="btn btn-primary" onClick={endSession} disabled={ending}>
              {ending ? "Saving..." : "Save and Finalize"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default function Live() {
  const { sessionId } = useParams();
  return sessionId ? <SessionLoader key={sessionId} id={sessionId} /> : <Setup />;
}
