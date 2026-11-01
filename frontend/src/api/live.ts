// Typed API calls. Auth: Bearer token from lib/auth.ts (guest token or Supabase account).
import { authHeaders, refreshSession, signOut } from "../lib/auth";
const BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) ??
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1"
    ? "https://sensora-ai.onrender.com"
    : "")
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string, public retryable = false) { super(message); }
}

export interface TroubleshootingResponse {
  assistant_message: string; observations: string[];
  likely_causes: { cause: string; likelihood: "low" | "medium" | "high" }[];
  confidence: { level: "low" | "medium" | "high"; note: string };
  current_step: { title: string; instruction: string; expected_result: string } | null;
  requested_user_action: string | null; requires_new_image: boolean; verification_required: boolean;
  safety_status: "ok" | "caution" | "stop"; escalation_recommended: boolean;
}
export interface TurnResult {
  user_message_id: string | null; assistant_message_id: string | null; response: TroubleshootingResponse;
  mode: "real" | "demo"; simulated: boolean; frames_analyzed: number; safety_overridden: boolean; warnings: string[];
}
export interface AIStatus { mode: "real" | "demo"; simulated: boolean; transcription: string; vision: string; reasoning: string; note: string }

export async function request<T>(path: string, init: RequestInit, retried = false): Promise<T> {
  let res: Response;
  try { res = await fetch(`${BASE}/api${path}`, { ...init, headers: { ...(init.headers ?? {}), ...authHeaders() } }); }
  catch { throw new ApiError("Can't reach the Sensora server. It may be waking up (free hosting can take up to a minute) or your connection dropped. Try again.", 0, "network", true); }
  if (res.status === 401 && !retried) {
    if (await refreshSession()) return request<T>(path, init, true);
    signOut();                                              // token invalid/expired: send the user back to the sign-in screen
    throw new ApiError("Your session expired. Please sign in again.", 401, "auth");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status}).`, code: string | undefined, retry = res.status >= 500 || res.status === 429;
    try {
      const d = (await res.json()).detail;
      if (typeof d === "string") msg = d; else if (d?.message) { msg = d.message; code = d.code; retry = !!d.retryable; }
      else if (Array.isArray(d)) msg = d.map((x: { msg: string }) => x.msg).join("; ");
    } catch { /* keep default */ }
    throw new ApiError(msg, res.status, code, retry);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const getAiStatus = () => request<AIStatus>("/ai/status", {});
export const postTurn = (sessionId: string, body: { text: string; input_mode: "voice" | "text"; frames: string[]; user_level?: "beginner" | "experienced" }) =>
  request<TurnResult>(`/sessions/${encodeURIComponent(sessionId)}/turn`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export async function transcribe(wav: Blob): Promise<{ text: string; provider: string; simulated: boolean }> {
  const fd = new FormData(); fd.append("audio", wav, "audio.wav");
  return request("/transcribe", { method: "POST", body: fd });
}
