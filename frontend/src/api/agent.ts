import { request, type TroubleshootingResponse, type TurnResult } from "./live";
import { authHeaders } from "../lib/auth";

export type WorkflowState = "problem_reported" | "information_gathering" | "awaiting_visual_evidence" | "analyzing" |
  "awaiting_user_action" | "verifying_action" | "resolved" | "escalation_required" | "session_completed";

export interface StepInfo {
  id: string; status?: string; title: string; instruction: string; expected_result?: string; verification_mode?: "visual" | "user_confirmation";
  user_reported_complete: boolean; visually_verified: boolean; verification_outcome: string; verification_basis?: string; verification_note?: string;
}
export interface AgentTurnResult extends Omit<TurnResult, "response"> {
  response: TroubleshootingResponse; workflow_state: WorkflowState; outcome: string | null;
  visually_verified: boolean; user_reported_complete: boolean; step: StepInfo | null;
}
export interface Summary {
  device: string; issue: string; initial_symptoms: string[]; observations: { text: string; simulated: boolean }[];
  steps: { title: string; outcome_label: string; user_reported_complete: boolean; visually_verified: boolean }[];
  successful: string[]; unsuccessful: string[]; verified: string[]; unverified: string[]; status: string; recommended_next: string; simulated: boolean;
}
export interface Handoff {
  title: string; pathway_label: string; customer_issue: string; disclaimers: string[]; unresolved_questions: string[];
  safety_concerns: string[]; recommended_next_steps: string[]; possible_causes: { cause: string; likelihood: string; status: string }[];
  steps: Summary["steps"]; evidence_note: string; evidence_included: boolean; status: string; generated_at: string;
  device: { name: string | null; model: string | null };
}
export type Pathway = "remote_expert" | "local_technician";
const json = (b: unknown): RequestInit => ({ method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
const post = (b: unknown): RequestInit => ({ ...json(b), method: "POST" });
const sid = (s: string) => encodeURIComponent(s);

export const postAgentTurn = (id: string, body: { text: string; input_mode: "voice" | "text"; frames: string[];
  user_level?: "beginner" | "experienced"; reported_step_done?: boolean }) => request<AgentTurnResult>(`/sessions/${sid(id)}/agent/turn`, post(body));
export const getSummary = (id: string) => request<{ summary: Summary; markdown: string }>(`/sessions/${sid(id)}/summary`, {});
export const completeSession = (id: string, status?: "resolved" | "unresolved" | "abandoned") => request<Summary>(`/sessions/${sid(id)}/complete`, post({ status }));
export const getHandoff = (id: string, pathway: Pathway, includeEvidence: boolean) =>
  request<Handoff>(`/sessions/${sid(id)}/handoff?pathway=${pathway}&include_evidence=${includeEvidence}`, {});
export const setEvidenceConsent = (id: string, evidence_consent: boolean) =>
  request<{ evidence_consent: boolean; deleted_frames: number; retention_days: number; max_frames: number }>(`/sessions/${sid(id)}/consent`, json({ evidence_consent }));
export const deleteEvidence = (id: string) => request<{ deleted_frames: number }>(`/sessions/${sid(id)}/evidence`, { method: "DELETE" });
export const getRelated = (id: string) => request<{ related: { score: number; id: string; device: string | null; problem: string | null; status: string; steps: { title: string; outcome: string }[] }[] }>(`/sessions/${sid(id)}/related`, {});
export const getExperience = () => request<{ user_level: "beginner" | "experienced" | null; remember_level: boolean }>("/preferences/experience", {});
export const setExperience = (level: "beginner" | "experienced" | null, remember: boolean) => request("/preferences/experience", json({ level, remember }));

/** Download needs consent_to_share=true; the server refuses otherwise. Nothing is sent to any technician. */
export async function exportHandoff(id: string, o: { pathway: Pathway; include_evidence: boolean; format: "md" | "html" }) {
  const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
  const res = await fetch(`${BASE}/api/sessions/${sid(id)}/handoff/export`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ ...o, consent_to_share: true }) });
  if (!res.ok) throw new Error(`Export failed (${res.status}).`);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: `sensora-handoff.${o.format}` });
  a.click(); URL.revokeObjectURL(url);
}
