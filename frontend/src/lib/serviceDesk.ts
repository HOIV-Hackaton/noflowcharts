import type {
  ActivityDraft,
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
  return Object.values(draft).every((value) => value.trim().length > 0);
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
