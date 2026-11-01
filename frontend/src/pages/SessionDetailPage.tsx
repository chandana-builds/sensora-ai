import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Eye,
  FileText,
  Trash2,
  Video,
  AlertTriangle,
  Copy,
  Check,
} from "lucide-react";
import { getMemory, deleteSession, Memory } from "../api/sessions";

function formatTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function SessionDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();

  const [memory, setMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedHandoff, setCopiedHandoff] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getMemory(id)
      .then((data) => {
        if (active) {
          setMemory(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load session details.");
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [id]);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteSession(id);
      navigate("/history", { replace: true });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete session.");
      setIsDeleting(false);
    }
  };

  const copyHandoffReport = () => {
    if (!memory) return;
    const { session, steps, observations, messages } = memory;
    const reportText = `--- SENSORA AI TECHNICIAN HANDOFF REPORT ---
Session ID: ${session.id}
Date: ${session.created_at}
Device: ${session.device_name || "Unspecified"} (${session.device_model || "Model unknown"})
Initial Problem: ${session.problem || "None described"}
Workflow State: ${session.workflow_state}
Final Status: ${session.final_status || "In progress"}

DIAGNOSTIC STEPS COMPLETED:
${steps.map((st, i) => `${i + 1}. ${st.title} - ${st.instruction}
   User Confirmed: ${st.user_reported_complete ? "YES" : "NO"}
   Visually Verified: ${st.visually_verified ? "YES" : "NO"} (${st.verification_outcome || "No outcome"})`).join("\n")}

RECORDED OBSERVATIONS:
${observations.map((obs) => `- ${obs.text} (${obs.simulated ? "simulated" : "live camera"})`).join("\n")}

LAST MESSAGE SUMMARY:
${messages.slice(-2).map((m) => `[${m.role.toUpperCase()}]: ${m.content}`).join("\n")}
---------------------------------------------`;

    navigator.clipboard.writeText(reportText);
    setCopiedHandoff(true);
    setTimeout(() => setCopiedHandoff(false), 2500);
  };

  if (loading) {
    return (
      <div className="container page narrow">
        <div className="card p-12 state">
          <div className="spinner" />
          <p className="text-slate-500 text-sm">Loading session memory...</p>
        </div>
      </div>
    );
  }

  if (error || !memory) {
    return (
      <div className="container page narrow">
        <div className="card p-8 state text-center">
          <AlertTriangle size={36} className="text-amber-500 mb-2" />
          <h2 className="text-lg font-bold text-slate-900">Session unavailable</h2>
          <p className="text-sm text-slate-600 mb-4">{error || "This session does not exist or has been deleted."}</p>
          <Link to="/history" className="btn btn-primary">
            Back to History
          </Link>
        </div>
      </div>
    );
  }

  const { session, steps, observations, messages } = memory;
  const isResolved = session.final_status === "resolved";
  const isEscalated = session.final_status === "escalated" || session.workflow_state === "escalated";

  return (
    <div className="container page narrow">
      <div className="mb-4">
        <Link to="/history" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900">
          <ArrowLeft size={16} />
          <span>Back to All Sessions</span>
        </Link>
      </div>

      {/* Header */}
      <div className="card block-card mb-6">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold m-0">
                {session.title || session.device_name || "Diagnostic Session"}
              </h1>
              {isResolved && (
                <span className="badge badge-resolved">
                  <CheckCircle2 size={13} />
                  <span>Resolved</span>
                </span>
              )}
              {isEscalated && (
                <span className="badge badge-escalated">
                  <AlertTriangle size={13} />
                  <span>Escalated to Human</span>
                </span>
              )}
              {!session.final_status && (
                <span className="badge badge-active">
                  <span>{session.workflow_state.replace(/_/g, " ")}</span>
                </span>
              )}
            </div>
            <div className="text-xs text-slate-500 flex flex-wrap items-center gap-3 mt-2">
              <span className="flex items-center gap-1">
                <Calendar size={13} />
                <span>Started {formatTimestamp(session.created_at)}</span>
              </span>
              {session.device_name && (
                <span>Device: <strong>{session.device_name}</strong></span>
              )}
              {session.user_level && (
                <span className="capitalize">{session.user_level} mode</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!session.final_status && (
              <Link to={`/live/${session.id}`} className="btn btn-primary btn-small">
                <Video size={15} />
                <span>Resume Live</span>
              </Link>
            )}
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="btn btn-danger-outline btn-small"
              title="Delete session"
            >
              <Trash2 size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Problem Description */}
      {session.problem && (
        <section className="card p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase text-slate-500 tracking-wider mb-2">
            Initial Problem Statement
          </h2>
          <p className="text-slate-800 text-base m-0 leading-relaxed">{session.problem}</p>
        </section>
      )}

      {/* Dual Verification Step Checklist */}
      <section className="card p-5 mb-6">
        <h2 className="text-base font-bold text-slate-900 mb-3 flex items-center justify-between">
          <span>Troubleshooting Steps & Dual Verification</span>
          <span className="text-xs font-normal text-slate-500">
            {steps.length} {steps.length === 1 ? "step" : "steps"} recorded
          </span>
        </h2>

        {steps.length === 0 ? (
          <p className="text-sm text-slate-500 italic m-0">No discrete steps reached in this session.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {steps.map((st, idx) => (
              <div key={st.id || idx} className="py-3">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="font-semibold text-slate-900 text-sm">
                    {idx + 1}. {st.title}
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {/* User Report Badge */}
                    <span
                      className={`badge-verification ${
                        st.user_reported_complete ? "badge-verified-user" : "badge-not-verified"
                      }`}
                      title={st.user_reported_complete ? "User confirmed completion" : "User hasn't confirmed"}
                    >
                      <CheckCircle2 size={13} />
                      <span>User Confirmed</span>
                    </span>

                    {/* Camera Visual Verification Badge */}
                    <span
                      className={`badge-verification ${
                        st.visually_verified ? "badge-verified-visual" : "badge-not-verified"
                      }`}
                      title={
                        st.visually_verified
                          ? "Camera frame verified change"
                          : "Not independently verified by camera"
                      }
                    >
                      <Eye size={13} />
                      <span>{st.visually_verified ? "Camera Verified" : "Unverified Visual"}</span>
                    </span>
                  </div>
                </div>
                <p className="text-slate-600 text-sm m-0">{st.instruction}</p>
                {st.verification_outcome && (
                  <p className="text-xs text-slate-400 mt-1 m-0 italic">
                    Outcome: {st.verification_outcome}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Hardware Observations */}
      {observations.length > 0 && (
        <section className="card p-5 mb-6">
          <h2 className="text-base font-bold text-slate-900 mb-3">
            Hardware Observations
          </h2>
          <ul className="list-disc list-inside text-sm text-slate-700 space-y-1.5 m-0">
            {observations.map((obs, idx) => (
              <li key={idx}>
                <span>{obs.text}</span>
                {obs.simulated && (
                  <span className="text-xs text-slate-400 ml-2">(simulated)</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Transcript Log */}
      <section className="card p-5 mb-6">
        <h2 className="text-base font-bold text-slate-900 mb-3">Conversation Transcript</h2>
        {messages.length === 0 ? (
          <p className="text-sm text-slate-500 italic m-0">No dialogue messages recorded.</p>
        ) : (
          <div className="transcript-list">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`msg-bubble ${m.role === "user" ? "msg-user" : "msg-assistant"}`}
              >
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span className="font-semibold uppercase tracking-wider">
                    {m.role === "user" ? "You" : "Sensora Assistant"}
                  </span>
                  <span>{formatTimestamp(m.created_at)}</span>
                </div>
                <p className="m-0 text-sm leading-relaxed">{m.content}</p>
                {(m.metadata as any)?.images && Array.isArray((m.metadata as any).images) && (m.metadata as any).images.length > 0 && (
                  <div className="flex gap-2 mt-2 flex-wrap">
                    {((m.metadata as any).images as string[]).map((imgSrc: string, i: number) => (
                      <img
                        key={i}
                        src={imgSrc}
                        alt={`Captured picture ${i + 1}`}
                        className="h-16 w-auto rounded border border-slate-300 object-cover cursor-pointer hover:opacity-90 shadow-sm"
                        onClick={() => window.open(imgSrc, "_blank")}
                        title="Click to view full photo"
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Technician Handoff Report Panel */}
      <section className="card p-5 mb-6 border-slate-300">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2 m-0">
              <FileText size={18} className="text-blue-600" />
              <span>Technician Handoff Export</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 m-0">
              When hardware needs a professional repair, export this structured diagnosis so the technician knows exactly what has already been attempted.
            </p>
          </div>
          <button
            type="button"
            onClick={copyHandoffReport}
            className="btn btn-secondary btn-small flex-shrink-0"
          >
            {copiedHandoff ? (
              <>
                <Check size={14} className="text-emerald-600" />
                <span>Copied to Clipboard</span>
              </>
            ) : (
              <>
                <Copy size={14} />
                <span>Copy Report</span>
              </>
            )}
          </button>
        </div>

        <div className="bg-slate-900 text-slate-100 p-4 rounded-lg font-mono text-xs overflow-x-auto leading-relaxed">
          <p className="text-slate-400 mb-1"># SENSORA AI CERTIFIED HANDOFF SUMMARY</p>
          <p>DEVICE: {session.device_name || "Generic device"} | STATUS: {session.final_status || "In progress"}</p>
          <p>PROBLEM: {session.problem || "None reported"}</p>
          <p className="text-slate-400 mt-2"># ATTEMPTED STEPS ({steps.length})</p>
          {steps.map((st, i) => (
            <p key={i}>[{st.user_reported_complete ? "x" : " "}] Step {i+1}: {st.title} (visual: {st.visually_verified ? "verified" : "unverified"})</p>
          ))}
        </div>
      </section>

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <h2 className="text-lg font-bold text-slate-900 mb-2">Delete this session?</h2>
            <p className="text-sm text-slate-600 mb-4">
              This will permanently remove the transcript, step verifications, and observation records for this session from your database.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setConfirmDelete(false)}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? "Deleting..." : "Permanently Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
