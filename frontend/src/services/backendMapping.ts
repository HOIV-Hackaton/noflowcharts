import type {
  ActivityDraft,
  CustomerSystem,
  EventType,
  Priority,
  ProposedAction,
  RunEvent,
  RunState,
  Ticket,
  ValidationResult,
} from "../types";
import type {
  BackendActionRead,
  BackendActivityDraftRead,
  BackendAuditEventRead,
  BackendCommandResultRead,
  BackendCustomer,
  BackendCustomerSystem,
  BackendEmployee,
  BackendRunStateRead,
  BackendTicket,
  BackendTerminalCommandRead,
  BackendTerminalTranscriptRead,
} from "./backendApi";
import type { TerminalCommandLog, TerminalTranscriptLine } from "../types";

export function employeeName(employee: BackendEmployee) {
  return `${employee.firstname} ${employee.lastname}`.trim() || employee.username;
}

export function mapBackendTicket(ticket: BackendTicket, assignedTo: string): Ticket {
  const createdAt = ticket.created_at ?? new Date().toISOString();
  const updatedAt = ticket.updated_at ?? createdAt;

  return {
    assignedTo,
    createdAt,
    customer: ticket.customer_name,
    customerId: ticket.customer_id,
    id: ticket.id,
    priority: normalizePriority(ticket.priority),
    report: ticket.description,
    status: ticket.status,
    title: ticket.title,
    updatedAt,
  };
}

export function mapBackendCustomerSystem(customerSystem: BackendCustomerSystem): CustomerSystem {
  return {
    hostLabel: `customer-${customerSystem.customer_id}`,
    notes: customerSystem.system.notes ?? "No additional notes provided.",
    os: customerSystem.system.os,
    target: `${customerSystem.system.ip}:${customerSystem.system.port}`,
    ticketId: customerSystem.ticket_id,
    username: customerSystem.system.username,
  };
}

export function mapBackendCustomer(customer: BackendCustomer, ticketId: number): CustomerSystem {
  return {
    hostLabel: `customer-${customer.id}`,
    notes: customer.system.notes ?? "No additional notes provided.",
    os: customer.system.os,
    target: `${customer.system.ip}:${customer.system.port}`,
    ticketId,
    username: customer.system.username,
  };
}

export function mapBackendAction(action: BackendActionRead, results: BackendCommandResultRead[] = []): ProposedAction {
  const result = results.find((candidate) => candidate.action_id === action.id);

  return {
    command: action.edited_command ?? action.command,
    flags: action.risk_reason ? [action.risk_reason] : [],
    id: String(action.id),
    purpose: action.expected_signal ?? action.intent ?? "Backend proposed action.",
    result: result ? summarizeCommandResult(result) : undefined,
    risk: mapRisk(action.command_classification),
    status: mapActionStatus(action.status),
    title: action.intent ?? action.command,
    type: action.command_classification === "read_only" ? "diagnostic" : "fix",
  };
}

export function mapBackendCommandResultAction(result: BackendCommandResultRead): ProposedAction {
  const failed = result.timed_out || (result.exit_code !== null && result.exit_code !== 0);

  return {
    command: result.command,
    flags: ["backend-validated", "read-only", "redacted"],
    id: String(result.action_id),
    purpose: "Backend-owned safe autodiagnosis result. Raw output remains redacted in the audit log.",
    result: summarizeCommandResult(result),
    risk: "Low",
    status: failed ? "failed" : "executed",
    title: `Safe diagnostic #${result.action_id}`,
    type: "diagnostic",
  };
}

export function mapRunState(state: BackendRunStateRead): RunState {
  switch (state.run.status) {
    case "created":
    case "pending":
      return state.run.ssh_confirmed ? "idle" : "awaiting_connection_approval";
    case "diagnosing":
      return "analyzing";
    case "awaiting_approval":
      return "awaiting_action_approval";
    case "running_command":
      return "executing";
    case "awaiting_validation_confirmation":
      return "validating";
    case "ready_for_activity":
      return "ready_to_submit";
    case "submitted":
      return "submitted";
    case "aborted":
      return "aborted";
    case "failed":
      return "idle";
  }
}

export function mapValidation(state: BackendRunStateRead): ValidationResult {
  if (state.run.validation_confirmed || state.run.validation_status === "human_confirmed") {
    return {
      evidence: "Backend validation evidence was confirmed by the technician.",
      status: "passed",
      summary: "Passed",
    };
  }

  if (state.run.validation_status === "evidence_collected") {
    return {
      evidence: "Backend collected validation evidence and is waiting for technician confirmation.",
      status: "not_run",
      summary: "Evidence collected",
    };
  }

  return {
    evidence: "Run validation after approved diagnostics and fixes complete.",
    status: "not_run",
    summary: "Not run",
  };
}

export function mapActivityDraft(draft: BackendActivityDraftRead): ActivityDraft {
  return {
    actions_taken: draft.actions_taken ?? "",
    commands_summary: draft.commands_summary ?? "",
    root_cause: draft.root_cause ?? "",
    summary: draft.summary ?? "",
    validation_result: draft.validation_result ?? "",
  };
}

export function mapAuditEvent(event: BackendAuditEventRead): RunEvent {
  return {
    detail: JSON.stringify(event.payload),
    id: String(event.id),
    time: new Date(event.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
    title: event.type.split("_").join(" "),
    type: mapEventType(event.type),
  };
}

export function mapTerminalCommand(command: BackendTerminalCommandRead): TerminalCommandLog {
  return {
    classification: command.classification,
    command: command.final_command ?? command.original_command,
    createdAt: command.created_at,
    endedAt: command.ended_at,
    exitCode: command.exit_code,
    id: command.id,
    output: command.output,
    riskReason: command.risk_reason,
    source: command.source,
    startedAt: command.started_at,
    status: command.status,
    updatedAt: command.updated_at,
  };
}

export function mapTerminalTranscript(event: BackendTerminalTranscriptRead): TerminalTranscriptLine {
  return {
    createdAt: event.created_at,
    data: event.data,
    id: event.id,
    redacted: event.redacted,
    stream: event.stream,
  };
}

function normalizePriority(priority: string): Priority {
  const normalized = priority.trim().toLowerCase();
  if (normalized === "critical") {
    return "Critical";
  }
  if (normalized === "high") {
    return "High";
  }
  if (normalized === "medium") {
    return "Medium";
  }
  return "Low";
}

function mapRisk(classification: BackendActionRead["command_classification"]) {
  if (classification === "risky_mutating" || classification === "blocked") {
    return "High";
  }
  if (classification === "mutating") {
    return "Medium";
  }
  return "Low";
}

function mapActionStatus(status: BackendActionRead["status"]) {
  if (status === "completed" || status === "approved" || status === "running") {
    return "executed";
  }
  if (status === "failed" || status === "blocked") {
    return "failed";
  }
  if (status === "rejected") {
    return "rejected";
  }
  return "pending";
}

function summarizeCommandResult(result: BackendCommandResultRead) {
  if (result.timed_out) {
    return "Command timed out.";
  }

  if (result.exit_code === 0) {
    return "Command completed successfully.";
  }

  return `Command exited with code ${result.exit_code ?? "unknown"}.`;
}

function mapEventType(type: string): EventType {
  if (type.includes("validation")) {
    return "validation";
  }
  if (type.includes("command") || type.includes("ssh")) {
    return "command";
  }
  if (type.includes("approval") || type.includes("confirmed") || type.includes("review")) {
    return "approval";
  }
  if (type.includes("error") || type.includes("failed") || type.includes("abort")) {
    return "error";
  }
  if (type.includes("activity") || type.includes("result")) {
    return "output";
  }
  return "analysis";
}
