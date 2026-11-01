import { request } from "./live";

export interface SessionRow {
  id: string; created_at: string; title: string | null; device_name: string | null; device_model: string | null; problem: string | null;
  workflow_state: string; final_status: string | null; user_level: "beginner" | "experienced" | null; evidence_consent: boolean;
}
export interface Memory {
  session: SessionRow;
  messages: { id: string; role: "user" | "assistant"; content: string; created_at: string; metadata?: { simulated?: boolean } }[];
  steps: { id: string; title: string; instruction: string; user_reported_complete: boolean; visually_verified: boolean; verification_outcome: string; simulated?: boolean }[];
  observations: { text: string; simulated: boolean }[];
}
const json = (m: string, b: unknown): RequestInit => ({ method: m, headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
export const createSession = (b: { title?: string; device_name?: string; problem?: string; user_level?: "beginner" | "experienced" | null } = {}) => request<SessionRow>("/sessions", json("POST", b));
export const listSessions = () => request<{ sessions: SessionRow[] }>("/sessions", {}).then((r) => r.sessions);
export const getMemory = (id: string) => request<Memory>(`/sessions/${encodeURIComponent(id)}/memory`, {});
export const deleteSession = (id: string) => request<void>(`/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
export interface UserPreferences {
  experience_level: "beginner" | "experienced";
  speak_responses: boolean;
  speech_rate: number;
  larger_text: boolean;
  high_contrast: boolean;
  reduce_motion: boolean;
  save_transcripts: boolean;
  display_name: string;
}

export const exportMyData = () => request<unknown>("/me/export", {});
export const deleteMyData = () => request<{ deleted_sessions: number }>("/me/data", { method: "DELETE" });
export const getPreferences = () => request<UserPreferences>("/preferences", {});
export const updatePreferences = (patch: Partial<UserPreferences>) => request<UserPreferences>("/preferences", json("PATCH", patch));
export const getHealth = () => fetch(`${(import.meta.env.VITE_API_URL as string | undefined) ?? ""}/api/health`).then((r) => r.json());

