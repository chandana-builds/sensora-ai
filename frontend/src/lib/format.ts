import type { SessionStatus, StepStatus, StepVerification } from "../types";

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const mm = String(m).padStart(h > 0 ? 2 : 1, "0"), ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
export const STATUS_LABEL: Record<SessionStatus, string> = {
  active: "In progress", resolved: "Resolved", unresolved: "Unresolved",
  escalated: "Escalated", abandoned: "Ended early",
};
export const STEP_STATUS_LABEL: Record<StepStatus, string> = {
  pending: "Pending", in_progress: "In progress", completed: "Completed", failed: "Did not work", skipped: "Skipped",
};
export const VERIFICATION_LABEL: Record<StepVerification, string> = {
  not_verified: "Not verified", user_confirmed: "Confirmed by you", visually_verified: "Verified from camera",
};
