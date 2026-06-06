import { useCallback, useEffect, useMemo, useState } from "react";
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
import { backendApi, getApiErrorMessage, type BackendRunStateRead } from "../../services/backendApi";
import {
  employeeName,
  mapActivityDraft,
  mapAuditEvent,
  mapBackendAction,
  mapBackendCustomerSystem,
  mapBackendTicket,
  mapRunState,
  mapValidation,
} from "../../services/backendMapping";
import type {
  ActivityDraft,
  CustomerSystem,
  EventType,
  Priority,
  ProposedAction,
  RunEvent,
  RunState,
  TabId,
  TicketStatus,
  ValidationResult,
  Ticket,
} from "../../types";
import { DashboardHome } from "./DashboardHome";
import { DashboardOverview } from "./DashboardOverview";
import { TicketWorkspace } from "../tickets/TicketWorkspace";

type SidebarView = BlocksSidebarView;
type SidebarCounts = BlocksSidebarCounts;

export function TechnicianConsole() {
  const { session, logout } = useAuth();
  const [ticketList, setTicketList] = useState<Ticket[]>(tickets);
  const [systemsByTicket, setSystemsByTicket] = useState<Record<number, CustomerSystem>>(systems);
  const [backendReady, setBackendReady] = useState(false);
  const [ticketsLoading, setTicketsLoading] = useState(true);
  const [lastTicketFetchAt, setLastTicketFetchAt] = useState<string | null>(null);
  const [backendRunId, setBackendRunId] = useState<string | null>(null);
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

  const selectedTicket = ticketList.find((ticket) => ticket.id === selectedTicketId) ?? null;
  const selectedSystem = selectedTicketId ? systemsByTicket[selectedTicketId] ?? null : null;
  const pendingActions = actions.filter((action) => action.status === "pending");
  const executedActions = actions.filter((action) => action.status === "executed");

  useEffect(() => {
    let cancelled = false;

    async function loadDashboardData() {
      setTicketsLoading(true);

      try {
        const [employee, backendTickets] = await Promise.all([
          backendApi.getMe(),
          backendApi.listTickets({ sort: "date" }),
        ]);

        if (cancelled) {
          return;
        }

        const assignedTo = employeeName(employee);
        setTicketList(backendTickets.map((ticket) => mapBackendTicket(ticket, assignedTo)));
        setLastTicketFetchAt(new Date().toISOString());
        setBackendReady(true);
        setNotice("");
      } catch (error) {
        if (cancelled) {
          return;
        }

        setTicketList(tickets);
        setLastTicketFetchAt(null);
        setBackendReady(false);
        setNotice(`Using mock dashboard data. ${getApiErrorMessage(error)}`);
      } finally {
        if (!cancelled) {
          setTicketsLoading(false);
        }
      }
    }

    void loadDashboardData();

    return () => {
      cancelled = true;
    };
  }, []);

  const filteredTickets = useMemo(() => {
    const query = search.trim().toLowerCase();
    const priorityRank: Record<Priority, number> = {
      Critical: 0,
      High: 1,
      Medium: 2,
      Low: 3,
    };

    return ticketList
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
  }, [priorityFilter, search, sidebarView, sortBy, statusFilter, ticketList]);

  const filteredEvents = useMemo(() => {
    if (logFilter === "all") {
      return events;
    }

    return events.filter((event) => event.type === logFilter);
  }, [events, logFilter]);

  const highPriorityTickets = useMemo(
    () => ticketList.filter((ticket) => ticket.priority === "Critical" || ticket.priority === "High"),
    [ticketList],
  );

  const sidebarCounts = useMemo<SidebarCounts>(
    () => ({
      all: ticketList.length,
      assigned: ticketList.filter((ticket) => ticket.assignedTo === session?.name || backendReady).length,
      high: ticketList.filter((ticket) => ticket.priority === "Critical" || ticket.priority === "High").length,
      pending: ticketList.filter((ticket) => ticket.status === "PENDING").length,
    }),
    [backendReady, session?.name, ticketList],
  );

  const stats = useMemo<BlocksStat[]>(
    () => [
      {
        label: "Open tickets",
        value: ticketList.filter((ticket) => ticket.status === "OPEN").length,
        kind: "chart",
        tone: "positive",
      },
      {
        label: "High priority",
        value: ticketList.filter((ticket) => ticket.priority === "Critical" || ticket.priority === "High").length,
        kind: "chart",
        tone: "negative",
      },
      { label: "Pending approval", value: pendingActions.length, kind: "metric", tone: "neutral" },
    ],
    [pendingActions.length, ticketList],
  );

  const dismissNotice = useCallback(() => setNotice(""), []);

  const syncRunState = useCallback((state: BackendRunStateRead) => {
    setRunState(mapRunState(state));
    setValidation(mapValidation(state));

    if (state.activity_draft) {
      setDraft(mapActivityDraft(state.activity_draft));
    }

    setActions((currentActions) => {
      if (!state.current_action) {
        return currentActions;
      }

      const nextAction = mapBackendAction(state.current_action, state.command_results);
      const existing = currentActions.find((action) => action.id === nextAction.id);

      if (existing) {
        return currentActions.map((action) => (action.id === nextAction.id ? nextAction : action));
      }

      return [...currentActions, nextAction];
    });
  }, []);

  const refreshAuditEvents = useCallback(async (runId: string) => {
    try {
      const auditEvents = await backendApi.getAudit(runId);
      setEvents(auditEvents.map(mapAuditEvent));
    } catch {
      // Audit refresh is helpful, but should not block the technician flow.
    }
  }, []);

  const updateTicketStatus = useCallback((ticketId: number, status: TicketStatus) => {
    setTicketList((currentTickets) =>
      currentTickets.map((ticket) => (ticket.id === ticketId ? { ...ticket, status } : ticket)),
    );
  }, []);

  const selectTicket = (ticketId: number) => {
    setSelectedTicketId(ticketId);
    setBackendRunId(null);
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

  const loadSystemInfo = async () => {
    if (!selectedTicket) {
      return;
    }

    if (backendReady) {
      try {
        const backendSystem = await backendApi.getCustomerSystem(selectedTicket.id);
        setSystemsByTicket((currentSystems) => ({
          ...currentSystems,
          [selectedTicket.id]: mapBackendCustomerSystem(backendSystem),
        }));
      } catch (error) {
        setNotice(`Using local system context. ${getApiErrorMessage(error)}`);
      }
    }

    setSystemLoaded(true);
    setConnectionStatus("awaiting_approval");
    setRunState("awaiting_connection_approval");
    appendEvent("approval", "System info loaded", "Redacted customer system context loaded.");
    setActiveTab("system");
  };

  const approveConnection = async () => {
    if (!selectedTicket || !systemLoaded) {
      return;
    }

    if (backendReady) {
      try {
        const runState = backendRunId
          ? await backendApi.getRun(backendRunId)
          : await backendApi.createRun(selectedTicket.id);
        const confirmedState = await backendApi.confirmSsh(runState.run.id);

        setBackendRunId(confirmedState.run.id);
        setConnectionStatus("connected");
        updateTicketStatus(selectedTicket.id, "PENDING");
        syncRunState(confirmedState);
        await refreshAuditEvents(confirmedState.run.id);
        appendEvent("approval", "Connection approved", "Backend run created and SSH approval confirmed.");
        return;
      } catch (error) {
        setNotice(`Using mock connection approval. ${getApiErrorMessage(error)}`);
      }
    }

    setConnectionStatus("connected");
    setRunState("idle");
    appendEvent("approval", "Connection approved", "Technician approved the mock SSH connection.");
  };

  const startAnalysis = async () => {
    if (!selectedTicket) {
      return;
    }

    if (backendReady) {
      if (connectionStatus !== "connected" || !backendRunId) {
        setNotice("Approve the backend connection before starting analysis.");
        return;
      }

      try {
        const state = await backendApi.nextAction(backendRunId);
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        setAnalysisReady(true);
        appendEvent("analysis", "Analysis complete", "Backend proposed the next action.");
        setActiveTab("analysis");
        return;
      } catch (error) {
        setNotice(`Using mock analysis. ${getApiErrorMessage(error)}`);
      }
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

  const approveAction = async (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action || action.status !== "pending") {
      return;
    }

    if (backendReady && backendRunId) {
      const backendActionId = Number(actionId);

      try {
        let state = await backendApi.editAction(
          backendRunId,
          Number.isFinite(backendActionId) ? backendActionId : null,
          action.command,
          action.title,
        );
        syncRunState(state);
        state = await backendApi.approveAction(
          backendRunId,
          Number.isFinite(backendActionId) ? backendActionId : null,
        );
        syncRunState(state);
        window.setTimeout(() => {
          void backendApi.getRun(backendRunId).then(syncRunState).catch(() => undefined);
          void refreshAuditEvents(backendRunId);
        }, 900);
        appendEvent("approval", "Action approved", action.title);
        return;
      } catch (error) {
        setNotice(`Using mock action execution. ${getApiErrorMessage(error)}`);
      }
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

  const rejectAction = async (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action) {
      return;
    }

    if (backendReady && backendRunId) {
      const backendActionId = Number(actionId);

      try {
        const state = await backendApi.rejectAction(
          backendRunId,
          Number.isFinite(backendActionId) ? backendActionId : null,
        );
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        appendEvent("approval", "Action rejected", action.title);
        return;
      } catch (error) {
        setNotice(`Using mock rejection. ${getApiErrorMessage(error)}`);
      }
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

  const retryAction = async (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action) {
      return;
    }

    if (backendReady && backendRunId) {
      const backendActionId = Number(actionId);

      try {
        const state = await backendApi.retryAction(
          backendRunId,
          Number.isFinite(backendActionId) ? backendActionId : null,
        );
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        appendEvent("approval", "Action queued again", action.title);
        return;
      } catch (error) {
        setNotice(`Using mock retry. ${getApiErrorMessage(error)}`);
      }
    }

    setActions((currentActions) =>
      currentActions.map((candidate) =>
        candidate.id === actionId ? { ...candidate, status: "pending", result: undefined } : candidate,
      ),
    );
    appendEvent("approval", "Action queued again", action.title);
    setRunState("awaiting_action_approval");
  };

  const abortRun = async () => {
    if (!selectedTicket) {
      return;
    }

    if (backendReady && backendRunId) {
      try {
        const state = await backendApi.abortRun(backendRunId);
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        setConnectionStatus((current) => (current === "connected" ? "disconnected" : current));
        appendEvent("error", "Run aborted", "Technician stopped the backend run.");
        return;
      } catch (error) {
        setNotice(`Using mock abort. ${getApiErrorMessage(error)}`);
      }
    }

    setRunState("aborted");
    setConnectionStatus((current) => (current === "connected" ? "disconnected" : current));
    appendEvent("error", "Run aborted", "Technician stopped the run.");
  };

  const runValidation = async () => {
    if (!selectedTicket) {
      return;
    }

    if (backendReady && backendRunId) {
      const evidence = "Technician confirmed service behavior after approved action execution.";

      try {
        const state = await backendApi.confirmValidation(backendRunId, evidence);
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        appendEvent("validation", "Validation passed", evidence);
        return;
      } catch (error) {
        setNotice(`Using mock validation. ${getApiErrorMessage(error)}`);
      }
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

  const generateDraft = async () => {
    if (!selectedTicket) {
      return;
    }

    if (backendReady && backendRunId) {
      try {
        const draftResponse = await backendApi.generateActivityDraft(backendRunId);
        setDraft(mapActivityDraft(draftResponse));
        await refreshAuditEvents(backendRunId);
        appendEvent("output", "Activity draft generated", "Backend generated the ERP activity draft.");
        setActiveTab("activity");
        return;
      } catch (error) {
        setNotice(`Using mock activity draft. ${getApiErrorMessage(error)}`);
      }
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

  const submitActivity = async () => {
    if (!isDraftComplete(draft)) {
      setNotice("Complete every activity field before submitting.");
      return;
    }

    const ticketId = selectedTicket?.id;

    if (backendReady && backendRunId) {
      try {
        await backendApi.updateActivityDraft(backendRunId, {
          actions_taken: draft.actions_taken,
          commands_summary: draft.commands_summary,
          description: draft.summary,
          root_cause: draft.root_cause,
          summary: draft.summary,
          validation_result: draft.validation_result,
        });
        await backendApi.reviewActivityDraft(backendRunId, true);
        await backendApi.submitActivity(backendRunId);
        const state = await backendApi.getRun(backendRunId);
        syncRunState(state);
        if (ticketId) {
          updateTicketStatus(ticketId, "DONE");
        }
        setSubmitStatus("submitted");
        setNotice("Activity submitted to backend.");
        await refreshAuditEvents(backendRunId);
        appendEvent("output", "Activity submitted", "Backend ERP activity submission completed.");
        return;
      } catch (error) {
        setNotice(`Using mock activity submission. ${getApiErrorMessage(error)}`);
      }
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

  const refreshTickets = async () => {
    if (!backendReady) {
      setNotice("Mock ticket queue refreshed.");
      return;
    }

    try {
      const backendTickets = await backendApi.listTickets({
        priority: priorityFilter === "all" ? null : priorityFilter,
        sort: sortBy,
        status: statusFilter === "all" ? null : statusFilter,
      });
      const assignedTo = session?.name ?? "Technician";
      setTicketList(backendTickets.map((ticket) => mapBackendTicket(ticket, assignedTo)));
      setLastTicketFetchAt(new Date().toISOString());
      setNotice("Backend ticket queue refreshed.");
    } catch (error) {
      setNotice(`Ticket refresh failed. ${getApiErrorMessage(error)}`);
    }
  };

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
        tickets={ticketList}
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
              latestFetchedAt={lastTicketFetchAt}
              onSelectTicket={selectTicket}
              stats={stats}
              tickets={ticketList}
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
