import type {
  CompletionStatus, ExperienceLevel, Health, Message, Preferences, PreferencesUpdate,
  SafetyAssessment, SessionCreated, SessionDetail, SessionPage, SessionStatus, Session,
} from "../types";

export const API_BASE_URL: string =
  ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000").replace(/\/$/, "");

const CLIENT_ID_KEY = "sensora.clientId";
let memoryClientId: string | null = null;

function randomUuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** Anonymous device identifier only. All real data lives in the backend database. */
export function getClientId(): string {
  try {
    let id = localStorage.getItem(CLIENT_ID_KEY);
    if (!id) {
      id = randomUuid();
      localStorage.setItem(CLIENT_ID_KEY, id);
    }
    return id;
  } catch {
    memoryClientId ??= randomUuid();
    return memoryClientId;
  }
}

import { authHeaders, refreshSession } from "../lib/auth";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

async function send(path: string, method: string, body?: unknown, retry = true): Promise<Response> {
  let res: Response;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Client-Id": getClientId(),
    ...authHeaders(),
  };
  try {
    res = await fetch(`${API_BASE_URL}/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the Sensora API at ${API_BASE_URL}. Is the backend running?`);
  }
  if (res.status === 401 && retry) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return send(path, method, body, false);
    }
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status}).`;
    let details: unknown;
    try {
      const data = await res.json();
      code = data?.error?.code ?? (typeof data?.detail === "object" ? data?.detail?.code : code);
      message = data?.error?.message ?? (typeof data?.detail === "string" ? data.detail : data?.detail?.message ?? message);
      details = data?.error?.details ?? data?.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message, details);
  }
  return res;
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await send(path, method, body);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export interface ListParams { status?: SessionStatus; limit?: number; offset?: number }

export const api = {
  health: () => request<Health>("/health"),
  getPreferences: () => request<Preferences>("/preferences"),
  updatePreferences: (patch: PreferencesUpdate) => request<Preferences>("/preferences", "PATCH", patch),
  listSessions: ({ status, limit = 20, offset = 0 }: ListParams = {}) => {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) q.set("status", status);
    return request<SessionPage>(`/sessions?${q}`);
  },
  createSession: (body: { device_name?: string; problem_description?: string; experience_level?: ExperienceLevel }) =>
    request<SessionCreated>("/sessions", "POST", body),
  getSession: (id: string) => request<SessionDetail>(`/sessions/${id}`),
  updateSession: (id: string, body: { device_name?: string; problem_description?: string }) =>
    request<Session>(`/sessions/${id}`, "PATCH", body),
  completeSession: (id: string, body: { status: CompletionStatus; summary?: string; unresolved_issues?: string[] }) =>
    request<SessionDetail>(`/sessions/${id}/complete`, "POST", body),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, "DELETE"),
  deleteAllSessions: () => request<{ deleted: number }>("/sessions", "DELETE"),
  addMessage: (id: string, content: string, input_mode: "text" | "speech" = "text") =>
    request<{ message: Message; safety: SafetyAssessment }>(`/sessions/${id}/messages`, "POST", { content, input_mode }),
  assessSafety: (text: string) => request<SafetyAssessment>("/safety/assess", "POST", { text }),
  exportData: async (): Promise<Blob> => (await send("/me/export", "GET")).blob(),
};
