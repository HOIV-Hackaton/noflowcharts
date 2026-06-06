import type {
  ActivityDraft,
  EventType,
  ProposedAction,
  RunEvent,
  RunState,
  Ticket,
} from "../types";

export function createActions(ticket: Ticket): ProposedAction[] {
  return [
    {
      id: `${ticket.id}-diagnostic-service`,
      type: "diagnostic",
      title: "Inspect service state",
      command: "systemctl status customer-app --no-pager",
      purpose: "Confirm whether the affected service is active and capture safe status output.",
      risk: "Low",
      flags: [],
      status: "pending",
    },
    {
      id: `${ticket.id}-diagnostic-logs`,
      type: "diagnostic",
      title: "Read recent service logs",
      command: "journalctl -u customer-app -n 80 --no-pager",
      purpose: "Collect recent errors without exposing secrets or broad filesystem content.",
      risk: "Medium",
      flags: ["output review"],
      status: "pending",
    },
    {
      id: `${ticket.id}-fix-restart`,
      type: "fix",
      title: "Restart affected service",
      command: "sudo systemctl restart customer-app",
      purpose: "Apply a proportionate service restart after diagnostics support it.",
      risk: "Medium",
      flags: ["service impact"],
      status: "pending",
    },
    {
      id: `${ticket.id}-validation-http`,
      type: "validation",
      title: "Validate customer endpoint",
      command: "curl -fsS http://localhost:8080/health",
      purpose: "Verify the restored customer benefit with a concrete health check.",
      risk: "Low",
      flags: [],
      status: "pending",
    },
  ];
}

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
