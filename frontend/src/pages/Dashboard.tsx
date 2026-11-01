import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Video,
  Clock,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Plus,
  SlidersHorizontal,
  FolderOpen,
  Calendar,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { listSessions, SessionRow } from "../api/sessions";

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

function StatusBadge({ status, finalStatus }: { status: string; finalStatus: string | null }) {
  if (finalStatus === "resolved") {
    return (
      <span className="badge badge-resolved">
        <CheckCircle2 size={13} />
        <span>Resolved</span>
      </span>
    );
  }
  if (finalStatus === "escalated" || status === "escalated") {
    return (
      <span className="badge badge-escalated">
        <AlertTriangle size={13} />
        <span>Escalated</span>
      </span>
    );
  }
  if (finalStatus === "unresolved") {
    return (
      <span className="badge badge-unresolved">
        <span>Unresolved</span>
      </span>
    );
  }
  return (
    <span className="badge badge-active">
      <span className="w-1.5 h-1.5 rounded-full bg-blue-600 inline-block mr-1" />
      <span>{status.replace(/_/g, " ")}</span>
    </span>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSessions();
      setSessions(data || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load your sessions.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const activeSessions = sessions.filter(
    (s) => !s.final_status && s.workflow_state !== "resolved" && s.workflow_state !== "unresolved"
  );
  const resolvedSessions = sessions.filter((s) => s.final_status === "resolved");
  const recentSessions = sessions.slice(0, 5);

  return (
    <div className="container page">
      {/* Personalized Welcome Banner */}
      <section className="card block-card mb-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="eyebrow">Personalized Workspace</div>
            <h1 className="text-2xl font-bold mb-1">
              Welcome back, {user?.displayName || "User"}
            </h1>
            <p className="text-slate-600 text-sm m-0">
              {user?.kind === "guest"
                ? "You are using an isolated guest session. Create an account anytime in Settings to preserve your history across devices."
                : `Account verified: ${user?.email}`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/live" className="btn btn-primary">
              <Plus size={16} />
              <span>New Troubleshooting Session</span>
            </Link>
          </div>
        </div>
      </section>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Total Sessions
          </div>
          <div className="text-2xl font-bold text-slate-900">{sessions.length}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Active In Progress
          </div>
          <div className="text-2xl font-bold text-blue-600">{activeSessions.length}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Resolved
          </div>
          <div className="text-2xl font-bold text-emerald-600">{resolvedSessions.length}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Preferences
          </div>
          <Link to="/settings" className="text-sm font-semibold text-accent hover:underline flex items-center gap-1 mt-1">
            <SlidersHorizontal size={15} />
            <span>Manage Preferences</span>
          </Link>
        </div>
      </div>

      {/* Active Session Highlight if any */}
      {activeSessions.length > 0 && (
        <section className="mb-6">
          <h2 className="text-base font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <Clock size={18} className="text-blue-600" />
            <span>Active Session in Progress</span>
          </h2>
          <div className="card p-5 border-l-4 border-l-blue-600">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-bold text-slate-900 text-lg">
                    {activeSessions[0].title || activeSessions[0].device_name || "Device Troubleshooting"}
                  </span>
                  <StatusBadge
                    status={activeSessions[0].workflow_state}
                    finalStatus={activeSessions[0].final_status}
                  />
                </div>
                <p className="text-slate-600 text-sm m-0 line-clamp-1">
                  {activeSessions[0].problem || "Diagnosis in progress. Resume to continue step-by-step guidance."}
                </p>
                <div className="text-xs text-slate-400 mt-2 flex items-center gap-1">
                  <Calendar size={13} />
                  <span>Started {formatTimestamp(activeSessions[0].created_at)}</span>
                </div>
              </div>
              <Link to={`/live/${activeSessions[0].id}`} className="btn btn-primary flex-shrink-0">
                <Video size={16} />
                <span>Resume Live Session</span>
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* Recent Sessions List */}
      <section className="mb-6">
        <div className="block-head">
          <h2 className="text-base font-semibold text-slate-900 m-0">Recent Sessions</h2>
          {sessions.length > 5 && (
            <Link to="/history" className="text-sm font-semibold text-accent hover:underline flex items-center gap-1">
              <span>View all {sessions.length} sessions</span>
              <ArrowRight size={14} />
            </Link>
          )}
        </div>

        {loading ? (
          <div className="card p-8 state">
            <div className="spinner" />
            <p className="text-slate-500 text-sm">Loading your session history...</p>
          </div>
        ) : error ? (
          <div className="card p-6 auth-error-alert flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
            <button type="button" onClick={fetchSessions} className="btn btn-secondary btn-small">
              <RefreshCw size={14} />
              <span>Retry</span>
            </button>
          </div>
        ) : sessions.length === 0 ? (
          <div className="card p-10 state text-center">
            <FolderOpen size={40} className="text-slate-300 mb-2" />
            <h3 className="text-base font-semibold text-slate-800">No troubleshooting sessions yet</h3>
            <p className="text-sm text-slate-500 max-w-md mb-4">
              When you diagnose a malfunctioning device, its steps, visual observations, and resolution history will appear here.
            </p>
            <Link to="/live" className="btn btn-primary">
              <Plus size={16} />
              <span>Start Your First Session</span>
            </Link>
          </div>
        ) : (
          <div className="card divide-y divide-slate-100 overflow-hidden">
            {recentSessions.map((s) => (
              <div
                key={s.id}
                onClick={() => navigate(`/history/${s.id}`)}
                className="p-4 hover:bg-slate-50 cursor-pointer transition-colors flex flex-col md:flex-row md:items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-slate-900 text-base hover:text-blue-600 transition-colors">
                      {s.title || s.device_name || "Diagnostic Session"}
                    </span>
                    <StatusBadge status={s.workflow_state} finalStatus={s.final_status} />
                  </div>
                  {s.problem && (
                    <p className="text-slate-600 text-sm m-0 line-clamp-1">{s.problem}</p>
                  )}
                  <div className="text-xs text-slate-400 mt-1 flex items-center gap-2">
                    <span>{formatTimestamp(s.created_at)}</span>
                    {s.user_level && (
                      <>
                        <span>·</span>
                        <span className="capitalize">{s.user_level} mode</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-xs font-semibold text-slate-400 hover:text-blue-600 flex items-center gap-1">
                    <span>Details</span>
                    <ArrowRight size={14} />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
