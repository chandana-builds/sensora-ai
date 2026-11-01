import type { AgentTurnResult, WorkflowState } from "../api/agent";

const LABEL: Record<WorkflowState, string> = {
  problem_reported: "Problem reported", information_gathering: "Gathering information", awaiting_visual_evidence: "Waiting for a camera view",
  analyzing: "Analysing", awaiting_user_action: "Waiting for you to try the step", verifying_action: "Checking the result",
  resolved: "Resolved", escalation_required: "Escalation recommended", session_completed: "Session completed",
};
const OUTCOME: Record<string, string> = {
  succeeded: "Worked, verified on camera", failed: "Did not work", user_confirmed: "Done, confirmed by you (not checked on camera)",
  user_reported_unverified: "You said it's done; I still need to see it", uncertain: "Can't tell yet", pending: "Not tried yet",
  simulated_not_verified: "Demo only, not verified",
};

/** Shows workflow state and keeps "you reported it" separate from "verified on camera". */
export default function StepStatus({ result, onDone, busy }: { result: AgentTurnResult | null; onDone: () => void; busy: boolean }) {
  if (!result) return null;
  const s = result.step;
  return (
    <div className="lc-status">
      <p><span className="lc-chip">{LABEL[result.workflow_state]}</span></p>
      {s && (
        <>
          <p className="lc-note">
            You reported this step done: <strong>{s.user_reported_complete ? "yes" : "not yet"}</strong> · Verified on camera:{" "}
            <strong>{s.visually_verified ? "yes" : "no"}</strong>
            {s.verification_outcome && s.verification_outcome !== "pending" ? ` · ${OUTCOME[s.verification_outcome] ?? s.verification_outcome}` : ""}
          </p>
          {["awaiting_user", "awaiting_verification"].includes(s.status ?? "awaiting_user") && result.workflow_state !== "escalation_required" && (
            <button onClick={onDone} disabled={busy}>I've done this step</button>
          )}
        </>
      )}
    </div>
  );
}
