export type ExperienceLevel = "beginner" | "experienced";
export type SessionStatus = "active" | "resolved" | "unresolved" | "escalated" | "abandoned";
export type CompletionStatus = Exclude<SessionStatus, "active">;
export type SafetyLevel = "ok" | "caution" | "stop";
export type StepStatus = "pending" | "in_progress" | "completed" | "failed" | "skipped";
export type StepVerification = "not_verified" | "user_confirmed" | "visually_verified";

export interface Preferences {
  experience_level: ExperienceLevel;
  speak_responses: boolean;
  speech_rate: number;
  larger_text: boolean;
  high_contrast: boolean;
  reduce_motion: boolean;
  save_transcripts: boolean;
  updated_at: string | null;
}
export type PreferencesUpdate = Partial<Omit<Preferences, "updated_at">>;

export interface Session {
  id: string;
  title: string;
  device_name: string | null;
  problem_description: string | null;
  experience_level: ExperienceLevel;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
  updated_at: string;
}
export interface SafetyAssessment {
  level: SafetyLevel;
  categories: string[];
  guidance: string[];
}
export interface SessionCreated extends Session {
  safety: SafetyAssessment;
}
export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  input_mode: "text" | "speech";
  safety_level: SafetyLevel;
  created_at: string;
}
export interface Step {
  id: string;
  session_id: string;
  step_number: number;
  instruction: string;
  status: StepStatus;
  verification: StepVerification;
  outcome_note: string | null;
  created_at: string;
  updated_at: string;
}
export interface Summary {
  session_id: string;
  summary: string;
  unresolved_issues: string[];
  generated_by: "user" | "system" | "ai";
  created_at: string;
  updated_at: string;
}
export interface SessionDetail extends Session {
  messages: Message[];
  steps: Step[];
  summary: Summary | null;
}
export interface SessionPage {
  items: Session[];
  has_more: boolean;
  limit: number;
  offset: number;
}
export interface Health {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  time: string;
  database: { mode: string; persistent: boolean; warning: string | null; connected: boolean; error: string | null };
  ai: { status: string; detail: string };
  auth: { mode: string };
}
