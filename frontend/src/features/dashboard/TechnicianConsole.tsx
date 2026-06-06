import { useCallback, useMemo, useState } from "react";
import {
  BlocksSidebar,
  type BlocksStat,
  type BlocksSidebarCounts,
  type BlocksSidebarView,
} from "../../components/blocks";
import { Toast } from "../../components/ui/Toast";
import { emptyDraft, initialValidation, systems, tickets } from "../../data/mockData";
import { useAuth } from "../auth/AuthProvider";
import {
  createActions,
  createEvent,
  isDraftComplete,
} from "../../lib/serviceDesk";
import type {
  ActivityDraft,
  EventType,
  Priority,
  ProposedAction,
  RunEvent,
  RunState,
  TabId,
  TicketStatus,
  ValidationResult,
} from "../../types";
import { DashboardHome } from "./DashboardHome";
import { DashboardOverview } from "./DashboardOverview";
import { TicketWorkspace } from "../tickets/TicketWorkspace";

type SidebarView = BlocksSidebarView;
type SidebarCounts = BlocksSidebarCounts;

export function TechnicianConsole() {
  const { session, logout } = useAuth();
  const [selectedTicketId, setSelectedTicketId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | TicketStatus>("all");
  const [priorityFilter, setPriorityFilter] = useState<"all" | Priority>("all");
  const [sortBy, setSortBy] = useState<"date" | "priority" | "customer">("date");
  const [sidebarView, setSidebarView] = useState<SidebarView>("overview");
  const [systemLoaded, setSystemLoaded] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<"not_requested" | "awaiting_approval" | "connected" | "disconnected">("not_requested");
  const [runState, setRunState] = useState<RunState>("idle");
  const [analysisReady, setAnalysisReady] = useState(false);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [validation, setValidation] = useState<ValidationResult>(initialValidation);
  const [draft, setDraft] = useState<ActivityDraft>(emptyDraft);
  const [submitStatus, setSubmitStatus] = useState<"idle" | "submitted">("idle");
  const [logFilter, setLogFilter] = useState<"all" | EventType>("all");
  const [notice, setNotice] = useState("");

  const selectedTicket = tickets.find((ticket) => ticket.id === selectedTicketId) ?? null;
  const selectedSystem = selectedTicketId ? systems[selectedTicketId] : null;
  const pendingActions = actions.filter((action) => action.status === "pending");
  const executedActions = actions.filter((action) => action.status === "executed");

  const filteredTickets = useMemo(() => {
    const query = search.trim().toLowerCase();
    const priorityRank: Record<Priority, number> = {
      Critical: 0,
      High: 1,
      Medium: 2,
      Low: 3,
    };

    return tickets
      .filter((ticket) => {
        const matchesSearch =
          !query ||
          ticket.title.toLowerCase().includes(query) ||
          ticket.customer.toLowerCase().includes(query) ||
          String(ticket.id).includes(query);
        const matchesStatus = statusFilter === "all" || ticket.status === statusFilter;
        const matchesPriority = priorityFilter === "all" || ticket.priority === priorityFilter;
        const matchesSidebar =
          sidebarView === "overview" ||
          sidebarView === "all" ||
          sidebarView === "assigned" ||
          (sidebarView === "high" && (ticket.priority === "Critical" || ticket.priority === "High")) ||
          (sidebarView === "pending" && ticket.status === "PENDING");

        return matchesSearch && matchesStatus && matchesPriority && matchesSidebar;
      })
      .sort((first, second) => {
        if (sortBy === "priority") {
          return priorityRank[first.priority] - priorityRank[second.priority];
        }

        if (sortBy === "customer") {
          return first.customer.localeCompare(second.customer);
        }

        return new Date(second.createdAt).getTime() - new Date(first.createdAt).getTime();
      });
  }, [priorityFilter, search, sidebarView, sortBy, statusFilter]);

  const filteredEvents = useMemo(() => {
    if (logFilter === "all") {
      return events;
    }

    return events.filter((event) => event.type === logFilter);
  }, [events, logFilter]);

  const highPriorityTickets = useMemo(
    () => tickets.filter((ticket) => ticket.priority === "Critical" || ticket.priority === "High"),
    [],
  );

  const sidebarCounts = useMemo<SidebarCounts>(
    () => ({
      all: tickets.length,
      assigned: tickets.filter((ticket) => ticket.assignedTo === session?.name).length,
      high: tickets.filter((ticket) => ticket.priority === "Critical" || ticket.priority === "High").length,
      pending: tickets.filter((ticket) => ticket.status === "PENDING").length,
    }),
    [session?.name],
  );

  const stats = useMemo<BlocksStat[]>(
    () => [
      {
        label: "Open tickets",
        value: tickets.filter((ticket) => ticket.status === "OPEN").length,
        kind: "chart",
        tone: "positive",
      },
      {
        label: "High priority",
        value: tickets.filter((ticket) => ticket.priority === "Critical" || ticket.priority === "High").length,
        kind: "chart",
        tone: "negative",
      },
      { label: "Pending approval", value: pendingActions.length, kind: "metric", tone: "neutral" },
    ],
    [pendingActions.length],
  );

  const dismissNotice = useCallback(() => setNotice(""), []);

  const selectTicket = (ticketId: number) => {
    setSelectedTicketId(ticketId);
    setActiveTab("overview");
    setSystemLoaded(false);
    setConnectionStatus("not_requested");
    setRunState("idle");
    setAnalysisReady(false);
    setActions([]);
    setEvents([createEvent("approval", "Ticket opened", `Ticket ${ticketId} opened.`)]);
    setValidation(initialValidation);
    setDraft(emptyDraft);
    setSubmitStatus("idle");
    setNotice("");
  };

  const loadSystemInfo = () => {
    if (!selectedTicket) {
      return;
    }

    setSystemLoaded(true);
    setConnectionStatus("awaiting_approval");
    setRunState("awaiting_connection_approval");
    appendEvent("approval", "System info loaded", "Redacted customer system context loaded.");
    setActiveTab("system");
  };

  const approveConnection = () => {
    if (!selectedTicket || !systemLoaded) {
      return;
    }

    setConnectionStatus("connected");
    setRunState("idle");
    appendEvent("approval", "Connection approved", "Technician approved the mock SSH connection.");
  };

  const startAnalysis = () => {
    if (!selectedTicket) {
      return;
    }

    setRunState("analyzing");
    setAnalysisReady(true);
    setActions(createActions(selectedTicket));
    appendEvent("analysis", "Analysis complete", "Hypotheses and proposed actions are ready.");
    setRunState("awaiting_action_approval");
    setActiveTab("analysis");
  };

  const updateActionCommand = (actionId: string, command: string) => {
    setActions((currentActions) =>
      currentActions.map((action) =>
        action.id === actionId && action.status === "pending" ? { ...action, command } : action,
      ),
    );
  };

  const approveAction = (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action || action.status !== "pending") {
      return;
    }

    setRunState("executing");
    setActions((currentActions) =>
      currentActions.map((candidate) =>
        candidate.id === actionId
          ? {
              ...candidate,
              status: "executed",
              result: "Executed in mock mode. Output redacted.",
            }
          : candidate,
      ),
    );
    appendEvent("approval", "Action approved", action.title);
    appendEvent("command", "Command executed", action.command);
    appendEvent("output", "Output summarized", "Mock command output was captured safely.");

    const remainingPending = actions.filter(
      (candidate) => candidate.id !== actionId && candidate.status === "pending",
    );
    setRunState(remainingPending.length ? "awaiting_action_approval" : "idle");
  };

  const rejectAction = (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action) {
      return;
    }

    setActions((currentActions) =>
      currentActions.map((candidate) =>
        candidate.id === actionId
          ? { ...candidate, status: "rejected", result: "Rejected by technician." }
          : candidate,
      ),
    );
    appendEvent("approval", "Action rejected", action.title);
  };

  const retryAction = (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action) {
      return;
    }

    setActions((currentActions) =>
      currentActions.map((candidate) =>
        candidate.id === actionId ? { ...candidate, status: "pending", result: undefined } : candidate,
      ),
    );
    appendEvent("approval", "Action queued again", action.title);
    setRunState("awaiting_action_approval");
  };

  const abortRun = () => {
    if (!selectedTicket) {
      return;
    }

    setRunState("aborted");
    setConnectionStatus((current) => (current === "connected" ? "disconnected" : current));
    appendEvent("error", "Run aborted", "Technician stopped the run.");
  };

  const runValidation = () => {
    if (!selectedTicket) {
      return;
    }

    setRunState("validating");
    const nextValidation: ValidationResult = {
      status: "passed",
      summary: "Passed",
      evidence: "Mock health check returned OK and customer-facing endpoint responded.",
    };
    setValidation(nextValidation);
    appendEvent("validation", "Validation passed", nextValidation.evidence);
    setRunState("ready_to_submit");
  };

  const generateDraft = () => {
    if (!selectedTicket) {
      return;
    }

    const nextDraft: ActivityDraft = {
      summary: `${selectedTicket.title} investigated and restored in the mock technician flow.`,
      root_cause: "Mock root cause: service or configuration condition identified by diagnostics.",
      actions_taken: executedActions.length
        ? executedActions.map((action) => `${action.type}: ${action.title}`).join("\n")
        : "No approved actions have executed yet.",
      commands_summary: executedActions.length
        ? executedActions.map((action) => action.command).join("\n")
        : "No command summaries available yet.",
      validation_result:
        validation.status === "passed" ? validation.evidence : "Validation has not passed yet.",
    };

    setDraft(nextDraft);
    appendEvent("output", "Activity draft generated", "Draft fields populated from mock audit data.");
    setActiveTab("activity");
  };

  const submitActivity = () => {
    if (!isDraftComplete(draft)) {
      setNotice("Complete every activity field before submitting.");
      return;
    }

    setSubmitStatus("submitted");
    setRunState("submitted");
    setNotice("Mock activity submitted.");
    appendEvent("output", "Activity submitted", "Mock ERP activity submission completed.");
  };

  const copyAuditExcerpt = () => {
    const excerpt = events
      .map((event) => `[${event.time}] ${event.type.toUpperCase()}: ${event.title} - ${event.detail}`)
      .join("\n");

    if (!excerpt) {
      setNotice("No log entries to copy yet.");
      return;
    }

    void navigator.clipboard?.writeText(excerpt);
    setNotice("Safe log excerpt copied.");
  };

  const refreshTickets = () => setNotice("Mock ticket queue refreshed.");

  const handleSidebarView = (view: SidebarView) => {
    setSidebarView(view);

    if (selectedTicket) {
      setSelectedTicketId(null);
    }

    if (view === "overview") {
      setPriorityFilter("all");
      setStatusFilter("all");
      setSortBy("date");
      setNotice("");
      return;
    }

    if (view === "high") {
      setPriorityFilter("all");
      setStatusFilter("all");
      setSortBy("priority");
      setNotice("Showing high priority tickets.");
      return;
    }

    if (view === "pending") {
      setPriorityFilter("all");
      setStatusFilter("all");
      setSortBy("date");
      setNotice("Showing pending approval tickets.");
      if (selectedTicket) {
        setActiveTab("actions");
      }
      return;
    }

    setPriorityFilter("all");
    setStatusFilter("all");
    setSortBy("date");
  };

  function appendEvent(type: EventType, title: string, detail: string) {
    setEvents((currentEvents) => [...currentEvents, createEvent(type, title, detail)]);
  }

  return (
    <main className="console">
      <BlocksSidebar
        activeView={sidebarView}
        counts={sidebarCounts}
        onNavigate={handleSidebarView}
        onLogout={logout}
        onSelectTicket={selectTicket}
        profile={{
          email: session?.email ?? "",
          name: session?.name ?? "Technician",
          role: session?.role ?? "Technician",
        }}
        search={search}
        setSearch={setSearch}
        tickets={tickets}
      />

      <section className="app-main">
        <section className="main-canvas" aria-label="Main dashboard">
          {selectedTicket ? (
            <TicketWorkspace
              activeTab={activeTab}
              actions={actions}
              analysisReady={analysisReady}
              connectionStatus={connectionStatus}
              draft={draft}
              events={filteredEvents}
              executedActions={executedActions}
              logFilter={logFilter}
              notice={notice}
              onAbort={abortRun}
              onApproveAction={approveAction}
              onApproveConnection={approveConnection}
              onBackToTickets={() => handleSidebarView("all")}
              onCopyAudit={copyAuditExcerpt}
              onDraftChange={setDraft}
              onGenerateDraft={generateDraft}
              onLoadSystem={loadSystemInfo}
              onRejectAction={rejectAction}
              onRetryAction={retryAction}
              onRunValidation={runValidation}
              onStartAnalysis={startAnalysis}
              onSubmitActivity={submitActivity}
              onTabChange={setActiveTab}
              onUpdateCommand={updateActionCommand}
              pendingActions={pendingActions}
              runState={runState}
              selectedSystem={selectedSystem}
              setLogFilter={setLogFilter}
              submitStatus={submitStatus}
              systemLoaded={systemLoaded}
              ticket={selectedTicket}
              validation={validation}
            />
          ) : sidebarView === "overview" ? (
            <DashboardOverview
              highPriorityTickets={highPriorityTickets}
              onSelectTicket={selectTicket}
              stats={stats}
              tickets={tickets}
            />
          ) : (
            <DashboardHome
              filteredTickets={filteredTickets}
              onSelectTicket={selectTicket}
              onRefreshTickets={refreshTickets}
              priorityFilter={priorityFilter}
              setPriorityFilter={setPriorityFilter}
              setSortBy={setSortBy}
              setStatusFilter={setStatusFilter}
              sidebarView={sidebarView}
              sortBy={sortBy}
              stats={stats}
              statusFilter={statusFilter}
            />
          )}
        </section>
      </section>

      {notice ? <Toast message={notice} onDone={dismissNotice} /> : null}
    </main>
  );
}
