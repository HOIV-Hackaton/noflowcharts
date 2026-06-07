import axios, { AxiosError, type AxiosRequestConfig } from "axios";
import type { TicketStatus } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json",
  },
});

export type BackendEmployee = {
  id: number;
  firstname: string;
  lastname: string;
  username: string;
  teamname: string;
};

export type BackendTicket = {
  id: number;
  title: string;
  description: string;
  priority: string;
  status: TicketStatus;
  customer_id: number;
  customer_name: string;
  tags: string[];
  sla_due_at: string | null;
  created_at: string | null;
  updated_at?: string | null;
};

export type BackendCustomer = {
  id: number;
  company_name: string;
  firstname: string;
  lastname: string;
  system: BackendSystemInfo;
};

export type BackendSystemInfo = {
  ip: string;
  port: number;
  username: string;
  os: string;
  notes: string | null;
};

export type BackendCustomerSystem = {
  ticket_id: number;
  customer_id: number;
  system: BackendSystemInfo;
};

export type BackendActionStatus =
  | "proposed"
  | "approved"
  | "rejected"
  | "edited"
  | "running"
  | "completed"
  | "failed"
  | "blocked";

export type BackendActionRead = {
  id: number;
  run_id: string;
  status: BackendActionStatus;
  command: string;
  command_classification: "read_only" | "mutating" | "risky_mutating" | "blocked";
  intent: string | null;
  risk_reason: string | null;
  expected_signal: string | null;
  typed_confirmation_status: "not_required" | "pending" | "confirmed";
  edited_command: string | null;
  created_at: string;
  updated_at: string;
};

export type BackendCommandResultRead = {
  id: number;
  action_id: number;
  command: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  started_at: string;
  ended_at: string | null;
};

export type BackendActivityDraftRead = {
  id: number;
  run_id: string;
  summary: string | null;
  root_cause: string | null;
  actions_taken: string | null;
  commands_summary: string | null;
  validation_result: string | null;
  description: string | null;
  review_status: "draft" | "reviewed" | "submitted";
  created_at: string;
  updated_at: string;
};

export type BackendRunRead = {
  id: string;
  ticket_id: number;
  status:
    | "created"
    | "pending"
    | "diagnosing"
    | "awaiting_approval"
    | "running_command"
    | "awaiting_validation_confirmation"
    | "ready_for_activity"
    | "submitted"
    | "aborted"
    | "failed";
  created_at: string;
  updated_at: string;
  customer_system_snapshot: Record<string, unknown> | null;
  current_action_id: number | null;
  validation_status: "not_started" | "evidence_collected" | "human_confirmed";
  ssh_confirmed: boolean;
  validation_confirmed: boolean;
};

export type BackendRunStateRead = {
  run: BackendRunRead;
  current_action: BackendActionRead | null;
  command_results: BackendCommandResultRead[];
  activity_draft: BackendActivityDraftRead | null;
  related_ticket: BackendRelatedTicketRead | null;
};

export type BackendRelatedTicketRead = {
  ticket_id: number;
  title: string;
  description: string;
  rationale: string | null;
  confidence: string | null;
};

export type BackendRunWebSocketEvent = {
  event_id: number | null;
  type: string;
  run_id: string;
  timestamp: string | null;
  payload: Record<string, unknown>;
};

export type BackendLatencyStats = {
  count: number;
  average_ms: number | null;
  min_ms: number | null;
  max_ms: number | null;
};

export type BackendTokenCostSummary = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
};

export type BackendLlmMetricsRead = {
  request_count: number;
  error_count: number;
  latency: BackendLatencyStats;
  tokens: BackendTokenCostSummary;
  by_operation: Record<string, BackendTokenCostSummary>;
  requests: Array<{
    id: number;
    run_id: string | null;
    operation: string;
    provider: string;
    model: string;
    latency_ms: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number | null;
    error: string | null;
    created_at: string;
  }>;
};

export type BackendRunMetricsRead = {
  run_id: string;
  ticket_id: number;
  status: string;
  created_at: string;
  updated_at: string;
  run_duration_ms: number;
  action_count: number;
  command_result_count: number;
  successful_command_count: number;
  failed_command_count: number;
  timed_out_command_count: number;
  terminal_command_count: number;
  audit_event_count: number;
  command_latency: BackendLatencyStats;
  terminal_command_latency: BackendLatencyStats;
  llm: BackendLlmMetricsRead;
};

export type BackendAuditEventRead = {
  id: number;
  run_id: string | null;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
  redacted: boolean;
};

export type BackendActivity = {
  id: number;
  team_id: number;
  team_name: string;
  employee_id: number;
  ticket_id: number;
  start_datetime: string;
  end_datetime: string;
  description: string;
  summary: string | null;
  root_cause: string | null;
  actions_taken: string | null;
  commands_summary: string | null;
  validation_result: string | null;
  created_at: string | null;
};

export type BackendTerminalCommandSource = "manual" | "agent";
export type BackendTerminalCommandStatus =
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

export type BackendTerminalCommandRead = {
  id: number;
  run_id: string;
  terminal_session_id: number | null;
  source: BackendTerminalCommandSource;
  status: BackendTerminalCommandStatus;
  original_command: string;
  final_command: string | null;
  edited_from: string | null;
  edited_to: string | null;
  classification: BackendActionRead["command_classification"] | null;
  risk_reason: string | null;
  exit_code: number | null;
  output: string;
  started_at: string | null;
  ended_at: string | null;
  redacted: boolean;
  created_at: string;
  updated_at: string;
};

export type BackendTerminalTranscriptRead = {
  id: number;
  run_id: string;
  terminal_session_id: number | null;
  stream: string;
  data: string;
  created_at: string;
  redacted: boolean;
};

export type BackendResetResponse = {
  detail: Record<string, unknown> | null;
  message: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const backendApi = {
  getMe() {
    return request<BackendEmployee>("/api/me");
  },

  listTickets(params: {
    priority?: string | null;
    sort?: "date" | "priority" | "status" | "customer";
    status?: TicketStatus | null;
  } = {}) {
    const search = new URLSearchParams();
    if (params.status) {
      search.set("status", params.status);
    }
    if (params.priority) {
      search.set("priority", params.priority);
    }
    search.set("sort", params.sort ?? "date");
    return request<BackendTicket[]>(`/api/tickets?${search.toString()}`);
  },

  getTicket(ticketId: number) {
    return request<BackendTicket>(`/api/tickets/${ticketId}`);
  },

  getCustomerSystem(ticketId: number) {
    return request<BackendCustomerSystem>(`/api/tickets/${ticketId}/customer-system`);
  },

  getCustomer(customerId: number) {
    return request<BackendCustomer>(`/api/customers/${customerId}`);
  },

  health() {
    return request<Record<string, unknown>>("/health");
  },

  resetEnvironment() {
    return request<BackendResetResponse>("/api/me/reset", { method: "POST" });
  },

  createRun(ticketId: number) {
    return request<BackendRunStateRead>("/api/runs", {
      data: { ticket_id: ticketId },
      method: "POST",
    });
  },

  getRun(runId: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}`);
  },

  confirmSsh(runId: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/confirm-ssh`, { method: "POST" });
  },

  nextAction(runId: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/next`, { method: "POST" });
  },

  startAutodiagnosis(runId: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/autodiagnosis/start`, { method: "POST" });
  },

  confirmRisk(runId: string, actionId: number | null, confirmationText: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/confirm-risk`, {
      data: { action_id: actionId, confirmation_text: confirmationText },
      method: "POST",
    });
  },

  approveAction(runId: string, actionId: number | null) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/approve`, {
      data: { action_id: actionId },
      method: "POST",
    });
  },

  rejectAction(runId: string, actionId: number | null) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/reject`, {
      data: { action_id: actionId },
      method: "POST",
    });
  },

  editAction(runId: string, actionId: number | null, command: string, intent?: string | null) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/edit`, {
      data: { action_id: actionId, command, intent },
      method: "POST",
    });
  },

  retryAction(runId: string, actionId: number | null) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/retry`, {
      data: { action_id: actionId },
      method: "POST",
    });
  },

  saferAlternative(runId: string, actionId: number | null) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/safer-alternative`, {
      data: { action_id: actionId },
      method: "POST",
    });
  },

  confirmValidation(runId: string, evidence: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/validation/confirm`, {
      data: { evidence },
      method: "POST",
    });
  },

  abortRun(runId: string) {
    return request<BackendRunStateRead>(`/api/runs/${runId}/abort`, { method: "POST" });
  },

  getAudit(runId: string) {
    return request<BackendAuditEventRead[]>(`/api/runs/${runId}/audit`);
  },

  getTerminalLogs(runId: string) {
    return request<BackendTerminalCommandRead[]>(`/api/runs/${runId}/terminal/logs`);
  },

  getTerminalTranscript(runId: string) {
    return request<BackendTerminalTranscriptRead[]>(`/api/runs/${runId}/terminal/transcript`);
  },

  getRunMetrics(runId: string) {
    return request<BackendRunMetricsRead>(`/api/metrics/runs/${runId}`);
  },

  generateActivityDraft(runId: string) {
    return request<BackendActivityDraftRead>(`/api/runs/${runId}/activity/draft`, { method: "POST" });
  },

  updateActivityDraft(runId: string, draft: {
    actions_taken?: string | null;
    commands_summary?: string | null;
    description?: string | null;
    root_cause?: string | null;
    summary?: string | null;
    validation_result?: string | null;
  }) {
    return request<BackendActivityDraftRead>(`/api/runs/${runId}/activity/draft`, {
      data: draft,
      method: "PATCH",
    });
  },

  reviewActivityDraft(runId: string, approved = true) {
    return request<BackendActivityDraftRead>(`/api/runs/${runId}/activity/review`, {
      data: { approved },
      method: "POST",
    });
  },

  submitActivity(runId: string) {
    return request<BackendActivity>(`/api/runs/${runId}/activity/submit`, {
      data: { submit: true },
      method: "POST",
    });
  },

  setTicketStatus(ticketId: number, status: TicketStatus) {
    return request<BackendTicket>(`/api/tickets/${ticketId}/status`, {
      data: { status },
      method: "PATCH",
    });
  },
};

export function getApiErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Backend request failed.";
}

export function runTerminalWebSocketUrl(runId: string, cols = 120, rows = 32) {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/api/runs/${runId}/terminal/ws`;
  url.search = new URLSearchParams({
    cols: String(cols),
    rows: String(rows),
  }).toString();
  return url.toString();
}

export function runEventsWebSocketUrl(runId: string, lastEventId?: number | null) {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/api/runs/${runId}/ws`;
  if (lastEventId !== undefined && lastEventId !== null) {
    url.search = new URLSearchParams({ last_event_id: String(lastEventId) }).toString();
  }
  return url.toString();
}

async function request<T>(path: string, config: AxiosRequestConfig = {}): Promise<T> {
  try {
    const response = await apiClient.request<T>({
      url: path,
      ...config,
    });
    return response.data;
  } catch (error) {
    if (error instanceof AxiosError) {
      const status = error.response?.status ?? 0;
      throw new ApiError(status, responseErrorMessage(error));
    }

    throw error;
  }
}

function responseErrorMessage(error: AxiosError) {
  const payload = error.response?.data as { detail?: unknown } | undefined;

  if (typeof payload?.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload?.detail)) {
    const messages = payload.detail
      .map((item) => (typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : ""))
      .filter(Boolean);

    if (messages.length) {
      return messages.join(", ");
    }
  }

  return error.response?.statusText || error.message || "Backend request failed.";
}
