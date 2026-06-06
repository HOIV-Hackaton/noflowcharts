export type TicketStatus = "OPEN" | "PENDING" | "DONE";
export type Priority = "Critical" | "High" | "Medium" | "Low";

export type ConnectionStatus = "not_requested" | "awaiting_approval" | "connected" | "disconnected";

export type RunState =
  | "idle"
  | "awaiting_connection_approval"
  | "analyzing"
  | "awaiting_action_approval"
  | "executing"
  | "validating"
  | "ready_to_submit"
  | "submitted"
  | "aborted";

export type TabId = "overview" | "system" | "analysis" | "actions" | "logs" | "activity";
export type ActionStatus = "pending" | "executed" | "rejected" | "failed";
export type RiskLevel = "Low" | "Medium" | "High";
export type EventType = "analysis" | "approval" | "command" | "output" | "validation" | "error";
export type TerminalCommandStatus =
  | "submitted"
  | "confirmation_required"
  | "blocked"
  | "accepted"
  | "rejected"
  | "edited"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type TechnicianSession = {
  email: string;
  name: string;
  role: "Technician";
  expiresAt: number;
};

export type Ticket = {
  id: number;
  customerId: number | null;
  title: string;
  customer: string;
  priority: Priority;
  status: TicketStatus;
  createdAt: string;
  updatedAt: string;
  report: string;
  assignedTo: string;
};

export type CustomerSystem = {
  ticketId: number;
  hostLabel: string;
  os: string;
  target: string;
  username: string;
  notes: string;
};

export type Hypothesis = {
  id: string;
  title: string;
  evidence: string;
  confidence: "High" | "Medium" | "Low";
};

export type ProposedAction = {
  id: string;
  type: "diagnostic" | "fix" | "validation";
  title: string;
  command: string;
  purpose: string;
  risk: RiskLevel;
  flags: string[];
  status: ActionStatus;
  result?: string;
};

export type RunEvent = {
  id: string;
  time: string;
  type: EventType;
  title: string;
  detail: string;
};

export type TerminalCommandLog = {
  id: number;
  source: "manual" | "agent";
  status: TerminalCommandStatus;
  command: string;
  classification: string | null;
  riskReason: string | null;
  exitCode: number | null;
  output: string;
  startedAt: string | null;
  endedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type TerminalTranscriptLine = {
  id: number;
  stream: string;
  data: string;
  createdAt: string;
  redacted: boolean;
};

export type ValidationResult = {
  status: "not_run" | "passed" | "failed";
  summary: string;
  evidence: string;
};

export type ActivityDraft = {
  summary: string;
  root_cause: string;
  actions_taken: string;
  commands_summary: string;
  validation_result: string;
};
