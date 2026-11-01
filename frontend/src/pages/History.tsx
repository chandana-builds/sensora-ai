import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Search,
  Filter,
  Trash2,
  Calendar,
  AlertCircle,
  FolderOpen,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Plus,
} from "lucide-react";
import { deleteSession, listSessions, SessionRow } from "../api/sessions";

function formatTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
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

export default function History() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sessionToDelete, setSessionToDelete] = useState<SessionRow | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSessions();
      setSessions(data || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load session history.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleDelete = async () => {
    if (!sessionToDelete) return;
    setIsDeleting(true);
    try {
      await deleteSession(sessionToDelete.id);
      setSessions((prev) => prev.filter((s) => s.id !== sessionToDelete.id));
      setSessionToDelete(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete session.");
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredSessions = sessions.filter((s) => {
    const matchesSearch =
      !searchQuery.trim() ||
      (s.title?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
      (s.device_name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false) ||
      (s.problem?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false);

    if (!matchesSearch) return false;

    if (statusFilter === "all") return true;
    if (statusFilter === "resolved") return s.final_status === "resolved";
    if (statusFilter === "escalated") return s.final_status === "escalated" || s.workflow_state === "escalated";
    if (statusFilter === "active") return !s.final_status && s.workflow_state !== "resolved";
    return true;
  });

  return (
    <div className="container page">
      <div className="block-head mb-6">
        <div>
          <p className="eyebrow">Session Archive</p>
          <h1 className="text-2xl font-bold">Your Troubleshooting History</h1>
          <p className="text-slate-600 text-sm m-0">
            Persistent transcripts, steps, and diagnostic observations associated with your account.
          </p>
        </div>
        <div>
          <Link to="/live" className="btn btn-primary">
            <Plus size={16} />
            <span>New Session</span>
          </Link>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="card p-4 mb-6">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="input-wrap flex-1">
            <Search size={18} className="input-icon" />
            <input
              type="text"
              placeholder="Search by device, problem description, or title..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-slate-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-white"
            >
              <option value="all">All States</option>
              <option value="active">In Progress / Active</option>
              <option value="resolved">Resolved</option>
              <option value="escalated">Escalated</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Content */}
      {loading ? (
        <div className="card p-10 state">
          <div className="spinner" />
          <p className="text-slate-500 text-sm">Loading archive...</p>
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
      ) : filteredSessions.length === 0 ? (
        <div className="card p-12 state text-center">
          <FolderOpen size={44} className="text-slate-300 mb-2" />
          <h3 className="text-base font-semibold text-slate-800">
            {sessions.length === 0 ? "No sessions in your account" : "No matching sessions found"}
          </h3>
          <p className="text-sm text-slate-500 max-w-md mb-4">
            {sessions.length === 0
              ? "When you troubleshoot devices with Sensora AI, transcripts and verified steps are saved here."
              : "Try clearing your search query or switching the status filter."}
          </p>
          {sessions.length === 0 ? (
            <Link to="/live" className="btn btn-primary">
              <Plus size={16} />
              <span>Start First Session</span>
            </Link>
          ) : (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
              }}
            >
              Clear Filters
            </button>
          )}
        </div>
      ) : (
        <div className="card divide-y divide-slate-100 overflow-hidden">
          {filteredSessions.map((s) => (
            <div
              key={s.id}
              className="p-4 hover:bg-slate-50 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              <div
                className="min-w-0 cursor-pointer flex-1"
                onClick={() => navigate(`/history/${s.id}`)}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-slate-900 text-base hover:text-blue-600 transition-colors">
                    {s.title || s.device_name || "Diagnostic Session"}
                  </span>
                  <StatusBadge status={s.workflow_state} finalStatus={s.final_status} />
                </div>
                {s.problem && (
                  <p className="text-slate-600 text-sm m-0 line-clamp-2">{s.problem}</p>
                )}
                <div className="text-xs text-slate-400 mt-2 flex items-center gap-3">
                  <span className="flex items-center gap-1">
                    <Calendar size={13} />
                    <span>{formatTimestamp(s.created_at)}</span>
                  </span>
                  {s.device_model && <span>Model: {s.device_model}</span>}
                  {s.user_level && <span className="capitalize">{s.user_level} mode</span>}
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => navigate(`/history/${s.id}`)}
                  className="btn btn-secondary btn-small"
                >
                  <span>View Details</span>
                  <ArrowRight size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => setSessionToDelete(s)}
                  className="btn btn-danger-outline btn-small"
                  aria-label="Delete session"
                  title="Delete session"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {sessionToDelete && (
        <div className="overlay" role="dialog" aria-modal="true">
          <div className="modal">
            <div className="flex items-start gap-3 mb-3">
              <div className="p-2 rounded-full bg-red-100 text-red-600">
                <Trash2 size={20} />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900 m-0">Delete Session?</h2>
                <p className="text-sm text-slate-600 mt-1 m-0">
                  Are you sure you want to delete{" "}
                  <strong>{sessionToDelete.title || sessionToDelete.device_name || "this session"}</strong>?
                  All associated messages, steps, and observation logs will be permanently deleted from the database.
                </p>
              </div>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSessionToDelete(null)}
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
