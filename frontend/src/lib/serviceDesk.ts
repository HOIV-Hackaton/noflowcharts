import type {
  ActivityDraft,
  AgentPhase,
  EventType,
  RunEvent,
  RunState,
  ValidationResult,
} from "../types";

export const initialValidation: ValidationResult = {
  status: "not_run",
  summary: "Not run",
  evidence: "Run validation after approved diagnostics and fixes complete.",
};

export const emptyDraft: ActivityDraft = {
  summary: "",
  root_cause: "",
  actions_taken: "",
  commands_summary: "",
  validation_result: "",
  description: "",
  fix_score: null,
};

export function createEvent(type: EventType, title: string, detail: string): RunEvent {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    time: new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
    type,
    title,
    detail,
  };
}

export function isDraftComplete(draft: ActivityDraft) {
  return (
    draft.summary.trim().length > 0 &&
    draft.root_cause.trim().length > 0 &&
    draft.actions_taken.trim().length > 0 &&
    draft.commands_summary.trim().length > 0 &&
    draft.validation_result.trim().length > 0 &&
    draft.description.trim().length > 0 &&
    draft.fix_score !== null &&
    draft.fix_score >= 0 &&
    draft.fix_score <= 3
  );
}

export function formatDate(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRunState(state: RunState) {
  return state.split("_").join(" ");
}

export function formatConnection(status: string) {
  return status.split("_").join(" ");
}

export function readAgentPhase(value: unknown): AgentPhase | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim().toLowerCase().replace(/[-\s]+/g, "_").replace(/_+/g, "_");

  switch (normalized) {
    case "diagnose":
    case "diagnosis":
      return "diagnosis";
    case "execute":
    case "execution":
    case "fix":
    case "fixing":
      return "execution";
    case "recover":
    case "recovery":
      return "recovery";
    case "validate":
    case "validation":
    case "verification":
    case "verify":
      return "verification";
    case "analysis_final":
    case "final":
    case "final_analysis":
      return "final_analysis";
    default:
      return null;
  }
}

export function formatAgentPhaseLabel(phase: AgentPhase) {
  switch (phase) {
    case "diagnosis":
      return "Diagnosis";
    case "execution":
      return "Fixing";
    case "recovery":
      return "Recovery";
    case "verification":
      return "Verifying";
    case "final_analysis":
      return "Final Analysis";
  }
}
