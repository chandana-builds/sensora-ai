import { ReactNode, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { SessionStatus } from "../types";
import { STATUS_LABEL } from "../lib/format";
import { useApp } from "../context/AppContext";
import { Icon } from "./Icon";

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <Icon name="alert" size={22} />
      <p>{error.message}</p>
      {onRetry && <button className="btn btn-secondary" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}

export function StatusBadge({ status }: { status: SessionStatus }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function ConnectionPill() {
  const { connection, health } = useApp();
  if (connection === "checking") return <span className="pill pill-neutral">Connecting…</span>;
  if (connection === "offline") return <span className="pill pill-danger" title="The backend API is unreachable">API offline</span>;
  const db = health?.database;
  if (db && !db.connected) return <span className="pill pill-warn" title={db.error ?? ""}>Database unreachable</span>;
  if (db?.mode !== "supabase")
    return <span className="pill pill-warn" title={db?.warning ?? ""}>Online · dev storage</span>;
  return <span className="pill pill-ok">Online · Supabase</span>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); previous?.focus?.(); };
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function SessionRow({ id, title, subtitle, status, date }: {
  id: string; title: string; subtitle: string | null; status: SessionStatus; date: string;
}) {
  return (
    <li className="row">
      <div className="row-main">
        <Link to={`/history/${id}`} className="row-title">{title}</Link>
        {subtitle && <p className="row-sub">{subtitle}</p>}
        <p className="row-meta">{date}</p>
      </div>
      <div className="row-side">
        <StatusBadge status={status} />
        {status === "active" && <Link className="btn btn-small btn-primary" to={`/live/${id}`}>Resume</Link>}
      </div>
    </li>
  );
}
