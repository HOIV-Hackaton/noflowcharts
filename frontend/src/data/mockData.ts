import type {
  ActivityDraft,
  CustomerSystem,
  Hypothesis,
  TabId,
  Ticket,
  ValidationResult,
} from "../types";

export const SESSION_KEY = "techbold_mock_session";
export const DEMO_EMAIL = "technician@techbold.local";
export const DEMO_PASSWORD = "demo-password";
export const SESSION_LENGTH_MS = 8 * 60 * 60 * 1000;

export const tabs: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "system", label: "System" },
  { id: "analysis", label: "Analysis" },
  { id: "actions", label: "Actions" },
  { id: "logs", label: "Logs" },
  { id: "activity", label: "Activity" },
];

export const tickets: Ticket[] = [
  {
    id: 7001,
    title: "Customer portal unavailable",
    customer: "Mayer & Partner Steuerberatung",
    priority: "Critical",
    status: "OPEN",
    createdAt: "2026-06-06T08:12:00Z",
    updatedAt: "2026-06-06T08:31:00Z",
    assignedTo: "Demo Technician",
    report:
      "Users report that the customer portal returns a gateway error. The issue started after the nightly maintenance window.",
  },
  {
    id: 7002,
    title: "Invoice PDF export failing",
    customer: "Alpine Retail GmbH",
    priority: "High",
    status: "OPEN",
    createdAt: "2026-06-06T07:40:00Z",
    updatedAt: "2026-06-06T08:08:00Z",
    assignedTo: "Demo Technician",
    report:
      "ERP users can create invoices but PDF export fails for every invoice generated this morning.",
  },
  {
    id: 7003,
    title: "Monitoring shows mail queue growing",
    customer: "Nordwest Logistics",
    priority: "Medium",
    status: "PENDING",
    createdAt: "2026-06-05T16:22:00Z",
    updatedAt: "2026-06-06T07:54:00Z",
    assignedTo: "Demo Technician",
    report: "Outbound mail is delayed and the monitoring system shows a steadily growing queue.",
  },
  {
    id: 7004,
    title: "Internal wiki intermittently slow",
    customer: "Vienna Studio AG",
    priority: "Low",
    status: "OPEN",
    createdAt: "2026-06-05T12:05:00Z",
    updatedAt: "2026-06-05T17:18:00Z",
    assignedTo: "Demo Technician",
    report:
      "The internal wiki works, but page loads are slow several times per hour. No data loss reported.",
  },
];

export const systems: Record<number, CustomerSystem> = {
  7001: {
    ticketId: 7001,
    hostLabel: "phoenix-web-01",
    os: "Ubuntu 22.04 LTS",
    target: "10.20.41.17:22",
    username: "azureuser",
    notes: "Portal runs behind nginx and a local application service.",
  },
  7002: {
    ticketId: 7002,
    hostLabel: "erp-worker-02",
    os: "Ubuntu 22.04 LTS",
    target: "10.20.41.23:22",
    username: "azureuser",
    notes: "PDF generation is handled by a worker service.",
  },
  7003: {
    ticketId: 7003,
    hostLabel: "mail-relay-01",
    os: "Ubuntu 20.04 LTS",
    target: "10.20.41.34:22",
    username: "azureuser",
    notes: "Mail relay is customer-managed but monitored by techbold.",
  },
  7004: {
    ticketId: 7004,
    hostLabel: "wiki-app-01",
    os: "Ubuntu 22.04 LTS",
    target: "10.20.41.44:22",
    username: "azureuser",
    notes: "Internal wiki service and local database are on the same VM.",
  },
};

export const hypotheses: Hypothesis[] = [
  {
    id: "h1",
    title: "Application service is unhealthy",
    evidence: "The report points to a reachable host with a failing upstream service.",
    confidence: "High",
  },
  {
    id: "h2",
    title: "Maintenance changed a config or dependency",
    evidence: "The incident started after the maintenance window and affects one workflow.",
    confidence: "Medium",
  },
  {
    id: "h3",
    title: "Resource pressure is causing failures",
    evidence: "Disk, memory, service status, and logs should be checked before changing config.",
    confidence: "Low",
  },
];

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
