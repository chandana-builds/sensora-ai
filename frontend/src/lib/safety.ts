import type { SafetyAssessment } from "../types";

const rank = { ok: 0, caution: 1, stop: 2 } as const;

/** Keeps the highest safety level seen in a session and the union of guidance. */
export function mergeSafety(prev: SafetyAssessment | null, next: SafetyAssessment): SafetyAssessment | null {
  if (next.level === "ok") return prev;
  if (!prev) return next;
  return {
    level: rank[next.level] > rank[prev.level] ? next.level : prev.level,
    categories: [...new Set([...prev.categories, ...next.categories])],
    guidance: [...new Set([...prev.guidance, ...next.guidance])],
  };
}
