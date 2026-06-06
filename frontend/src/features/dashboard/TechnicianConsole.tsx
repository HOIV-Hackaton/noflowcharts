import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCwIcon, RotateCcwIcon } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DashboardStat, SidebarCounts, SidebarView } from "@/components/service-desk-ui";
import { getQueueHeading } from "@/lib/queue";
import { Toast } from "../../components/ui/Toast";
import { emptyDraft, initialValidation, systems, tickets } from "../../data/mockData";
import { useAuth } from "../auth/AuthProvider";
import {
  createActions,
  createEvent,
  formatDate,
  isDraftComplete,
} from "../../lib/serviceDesk";
import { backendApi, getApiErrorMessage, type BackendRunStateRead } from "../../services/backendApi";
import {
  employeeName,
  mapActivityDraft,
  mapAuditEvent,
  mapBackendCustomer,
  mapBackendAction,
  mapBackendCommandResultAction,
  mapBackendCustomerSystem,
  mapBackendTicket,
  mapRunState,
  mapTerminalCommand,
  mapTerminalTranscript,
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
  TerminalCommandLog,
  TerminalTranscriptLine,
} from "../../types";
import { DashboardHome } from "./DashboardHome";
import { DashboardOverview } from "./DashboardOverview";
import { TicketWorkspace } from "../tickets/TicketWorkspace";

type AppRouteState = {
  tab: TabId;
  ticketId: number | null;
  view: SidebarView;
};

const routeByView: Record<SidebarView, string> = {
  all: "/app/tickets",
  assigned: "/app/tickets/assigned",
  high: "/app/tickets/high-priority",
  overview: "/app/overview",
  pending: "/app/tickets/pending",
};

export function TechnicianConsole() {
  const { session, logout } = useAuth();
  const initialRoute = getAppRouteState();
  const [ticketList, setTicketList] = useState<Ticket[]>(tickets);
  const [systemsByTicket, setSystemsByTicket] = useState<Record<number, CustomerSystem>>(systems);
  const [backendReady, setBackendReady] = useState(false);
  const [ticketsLoading, setTicketsLoading] = useState(true);
  const [lastTicketFetchAt, setLastTicketFetchAt] = useState<string | null>(null);
  const [backendRunId, setBackendRunId] = useState<string | null>(null);
  const [selectedTicketId, setSelectedTicketId] = useState<number | null>(() => initialRoute.ticketId);
  const [activeTab, setActiveTab] = useState<TabId>(() => initialRoute.tab);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | TicketStatus>("all");
  const [priorityFilter, setPriorityFilter] = useState<"all" | Priority>("all");
  const [sortBy, setSortBy] = useState<"date" | "priority" | "customer">("date");
  const [sidebarView, setSidebarView] = useState<SidebarView>(() => initialRoute.view);
  const [systemLoaded, setSystemLoaded] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<"not_requested" | "awaiting_approval" | "connected" | "disconnected">("not_requested");
  const [runState, setRunState] = useState<RunState>("idle");
  const [analysisReady, setAnalysisReady] = useState(false);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [autodiagnosisRunning, setAutodiagnosisRunning] = useState(false);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [terminalCommands, setTerminalCommands] = useState<TerminalCommandLog[]>([]);
  const [terminalTranscript, setTerminalTranscript] = useState<TerminalTranscriptLine[]>([]);
  const [validation, setValidation] = useState<ValidationResult>(initialValidation);
  const [draft, setDraft] = useState<ActivityDraft>(emptyDraft);
  const [submitStatus, setSubmitStatus] = useState<"idle" | "submitted">("idle");
  const [logFilter, setLogFilter] = useState<"all" | EventType>("all");
  const [notice, setNotice] = useState("");

  const selectedTicket = ticketList.find((ticket) => ticket.id === selectedTicketId) ?? null;
  const selectedSystem = selectedTicketId ? systemsByTicket[selectedTicketId] ?? null : null;
  const pendingActions = actions.filter((action) => action.status === "pending");
  const executedActions = actions.filter((action) => action.status === "executed");
  const canStartAutodiagnosis =
    backendReady &&
    Boolean(backendRunId) &&
    connectionStatus === "connected" &&
    (runState === "idle" || runState === "analyzing") &&
    submitStatus === "idle";

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

  const stats = useMemo<DashboardStat[]>(() => {
    const total = Math.max(ticketList.length, 1);
    const openTickets = ticketList.filter((ticket) => ticket.status === "OPEN").length;
    const highTickets = ticketList.filter(
      (ticket) => ticket.priority === "Critical" || ticket.priority === "High",
    ).length;

    return [
      {
        detail: `${openTickets} tickets still need diagnosis or documentation.`,
        label: "Open tickets",
        progress: (openTickets / total) * 100,
        tone: "default",
        value: openTickets,
      },
      {
        detail: "Critical and high priority work.",
        label: "High priority",
        progress: (highTickets / total) * 100,
        tone: highTickets ? "critical" : "success",
        value: highTickets,
      },
      {
        detail: "Commands or connection steps waiting on a human.",
        label: "Pending approval",
        progress: pendingActions.length ? 100 : 0,
        tone: pendingActions.length ? "warning" : "success",
        value: pendingActions.length,
      },
    ];
  }, [pendingActions.length, ticketList]);

  const dismissNotice = useCallback(() => setNotice(""), []);

  useEffect(() => {
    if (!backendReady || !selectedTicketId) {
      return;
    }

    const ticketId = selectedTicketId;
    let cancelled = false;

    async function loadSelectedTicket() {
      try {
        const backendTicket = await backendApi.getTicket(ticketId);
        if (cancelled) {
          return;
        }

        const assignedTo = session?.name ?? "Technician";
        setTicketList((currentTickets) =>
          upsertTicket(currentTickets, mapBackendTicket(backendTicket, assignedTo)),
        );
      } catch (error) {
        if (!cancelled) {
          setNotice(`Ticket detail refresh failed. ${getApiErrorMessage(error)}`);
        }
      }
    }

    void loadSelectedTicket();

    return () => {
      cancelled = true;
    };
  }, [backendReady, selectedTicketId, session?.name]);

  const resetTicketWorkspace = useCallback((ticketId: number, tab: TabId = "overview") => {
    setSelectedTicketId(ticketId);
    setBackendRunId(null);
    setActiveTab(tab);
    setSystemLoaded(false);
    setConnectionStatus("not_requested");
    setRunState("idle");
    setAnalysisReady(false);
    setActions([]);
    setEvents([createEvent("approval", "Ticket opened", `Ticket ${ticketId} opened.`)]);
    setTerminalCommands([]);
    setTerminalTranscript([]);
    setValidation(initialValidation);
    setDraft(emptyDraft);
    setSubmitStatus("idle");
    setNotice("");
  }, []);

  useEffect(() => {
    const syncRoute = () => {
      const route = getAppRouteState();
      setSidebarView(route.view);

      if (route.ticketId) {
        resetTicketWorkspace(route.ticketId, route.tab);
        return;
      }

      setSelectedTicketId(null);
      setActiveTab("overview");
    };

    syncRoute();
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, [resetTicketWorkspace]);

  const syncRunState = useCallback((state: BackendRunStateRead) => {
    setRunState(mapRunState(state));
    setValidation(mapValidation(state));

    if (state.activity_draft) {
      setDraft(mapActivityDraft(state.activity_draft));
    }

    setActions((currentActions) => {
      let nextActions = currentActions;

      for (const result of state.command_results) {
        nextActions = upsertAction(nextActions, mapBackendCommandResultAction(result));
      }

      if (state.current_action) {
        nextActions = upsertAction(nextActions, mapBackendAction(state.current_action, state.command_results));
      }

      return nextActions;
    });
  }, []);

  const refreshAuditEvents = useCallback(async (runId: string) => {
    const [auditResult, commandResult, transcriptResult] = await Promise.allSettled([
      backendApi.getAudit(runId),
      backendApi.getTerminalLogs(runId),
      backendApi.getTerminalTranscript(runId),
    ]);

    if (auditResult.status === "fulfilled") {
      setEvents(auditResult.value.map(mapAuditEvent));
    }

    if (commandResult.status === "fulfilled") {
      setTerminalCommands(commandResult.value.map(mapTerminalCommand));
    }

    if (transcriptResult.status === "fulfilled") {
      setTerminalTranscript(transcriptResult.value.map(mapTerminalTranscript));
    }
  }, []);

  const updateTicketStatus = useCallback((ticketId: number, status: TicketStatus) => {
    setTicketList((currentTickets) =>
      currentTickets.map((ticket) => (ticket.id === ticketId ? { ...ticket, status } : ticket)),
    );
  }, []);

  const selectTicket = (ticketId: number) => {
    pushAppRoute(ticketRoute(ticketId, "overview"));
    setSidebarView("all");
    resetTicketWorkspace(ticketId, "overview");
  };

  const setTicketTab = useCallback((tab: TabId) => {
    setActiveTab(tab);

    if (selectedTicketId) {
      replaceAppRoute(ticketRoute(selectedTicketId, tab));
    }
  }, [selectedTicketId]);

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
        if (selectedTicket.customerId) {
          try {
            const backendCustomer = await backendApi.getCustomer(selectedTicket.customerId);
            setSystemsByTicket((currentSystems) => ({
              ...currentSystems,
              [selectedTicket.id]: mapBackendCustomer(backendCustomer, selectedTicket.id),
            }));
          } catch (customerError) {
            setNotice(
              `Using local system context. ${getApiErrorMessage(error)} ${getApiErrorMessage(customerError)}`,
            );
          }
        } else {
          setNotice(`Using local system context. ${getApiErrorMessage(error)}`);
        }
      }
    }

    setSystemLoaded(true);
    setConnectionStatus("awaiting_approval");
    setRunState("awaiting_connection_approval");
    appendEvent("approval", "System info loaded", "Redacted customer system context loaded.");
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
        setTicketTab("actions");
        return;
      } catch (error) {
        setBackendRunId(null);
        setConnectionStatus("awaiting_approval");
        setRunState("awaiting_connection_approval");
        setNotice(`Connection approval failed. ${getApiErrorMessage(error)}`);
        return;
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
        const state = await backendApi.getRun(backendRunId);
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        setAnalysisReady(true);
        appendEvent("analysis", "Terminal agent ready", "Open the terminal and start the backend agent.");
        setTicketTab("actions");
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
    setTicketTab("analysis");
  };

  const startAutodiagnosis = async () => {
    if (!backendReady || !backendRunId || autodiagnosisRunning) {
      return;
    }

    if (connectionStatus !== "connected") {
      setNotice("Approve the backend connection before starting safe autodiagnosis.");
      return;
    }

    setAutodiagnosisRunning(true);
    setAnalysisReady(true);
    setRunState("analyzing");
    appendEvent(
      "analysis",
      "Safe autodiagnosis started",
      "Backend will auto-run only deterministic read-only diagnostic tools.",
    );

    try {
      const state = await backendApi.startAutodiagnosis(backendRunId);
      syncRunState(state);
      await refreshAuditEvents(backendRunId);
      setAnalysisReady(true);

      const currentActionNeedsReview =
        state.current_action !== null &&
        (state.current_action.status === "proposed" ||
          state.current_action.status === "edited" ||
          state.current_action.status === "blocked");

      if (state.current_action?.status === "blocked" || state.run.status === "failed") {
        appendEvent(
          "error",
          "Safe autodiagnosis stopped",
          "See audit log for the blocked request or error.",
        );
        setNotice("Safe autodiagnosis stopped. See audit log for the blocked request or error.");
        setTicketTab("actions");
        return;
      }

      if (currentActionNeedsReview) {
        appendEvent("approval", "A proposed fix requires technician approval", "Safe autodiagnosis handed off to the normal approval flow.");
        setNotice("A proposed fix requires technician approval.");
        setTicketTab("actions");
        return;
      }

      appendEvent(
        "analysis",
        "Safe autodiagnosis completed",
        "Redacted diagnostic evidence was captured.",
      );
      setNotice("Safe autodiagnosis completed. Redacted diagnostic evidence was captured.");
      setTicketTab("actions");
    } catch (error) {
      setNotice(`Safe autodiagnosis stopped. See audit log for the blocked request or error. ${getApiErrorMessage(error)}`);
      appendEvent(
        "error",
        "Safe autodiagnosis stopped",
        "See audit log for the blocked request or error.",
      );
      await refreshAuditEvents(backendRunId).catch(() => undefined);
    } finally {
      setAutodiagnosisRunning(false);
    }
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
        setTicketTab("activity");
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
    setTicketTab("activity");
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
    const auditExcerpt = events
      .map((event) => `[${event.time}] ${event.type.toUpperCase()}: ${event.title} - ${event.detail}`)
      .join("\n");
    const terminalExcerpt = terminalCommands
      .map((command) => {
        const exitCode = command.exitCode === null ? "pending" : `exit ${command.exitCode}`;
        return `[${new Date(command.updatedAt).toLocaleTimeString()}] ${command.source.toUpperCase()} ${command.status.toUpperCase()} (${exitCode}): ${command.command}`;
      })
      .join("\n");
    const excerpt = [auditExcerpt, terminalExcerpt].filter(Boolean).join("\n");

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

  const resetEnvironment = async () => {
    if (!backendReady) {
      setNotice("Backend reset is unavailable in mock mode.");
      return;
    }

    try {
      const response = await backendApi.resetEnvironment();
      const backendTickets = await backendApi.listTickets({
        priority: priorityFilter === "all" ? null : priorityFilter,
        sort: sortBy,
        status: statusFilter === "all" ? null : statusFilter,
      });
      const assignedTo = session?.name ?? "Technician";
      setTicketList(backendTickets.map((ticket) => mapBackendTicket(ticket, assignedTo)));
      setLastTicketFetchAt(new Date().toISOString());
      setSelectedTicketId(null);
      setBackendRunId(null);
      setActiveTab("overview");
      setSystemLoaded(false);
      setConnectionStatus("not_requested");
      setRunState("idle");
      setAnalysisReady(false);
      setActions([]);
      setEvents([]);
      setTerminalCommands([]);
      setTerminalTranscript([]);
      setValidation(initialValidation);
      setDraft(emptyDraft);
      setSubmitStatus("idle");
      setNotice(response.message || "VM reset requested.");
    } catch (error) {
      setNotice(`VM reset failed. ${getApiErrorMessage(error)}`);
    }
  };

  const handleSidebarView = (view: SidebarView) => {
    pushAppRoute(routeByView[view]);
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

  const newestTicket = useMemo(
    () =>
      ticketList
        .slice()
        .sort((first, second) => new Date(second.updatedAt).getTime() - new Date(first.updatedAt).getTime())[0],
    [ticketList],
  );
  const latestQueueUpdate = lastTicketFetchAt ?? newestTicket?.updatedAt ?? null;
  const queueHeading = getQueueHeading(sidebarView, filteredTickets.length);
  const pageTitle = selectedTicket
    ? `Ticket #${selectedTicket.id}`
    : sidebarView === "overview"
      ? "Service desk overview"
      : queueHeading.title;
  const headerDescription = selectedTicket
    ? undefined
    : sidebarView === "overview"
      ? latestQueueUpdate
        ? `Last queue update ${formatDate(latestQueueUpdate)}.`
        : "No tickets loaded yet."
      : `${filteredTickets.length} visible tickets across the selected queue.`;
  const headerBadges = selectedTicket ? undefined : (
    <>
      {sidebarView === "overview" ? <Badge variant="secondary">{ticketList.length} assigned</Badge> : null}
      {pendingActions.length ? <Badge variant="destructive">{pendingActions.length} approvals</Badge> : null}
    </>
  );
  const headerAction =
    !selectedTicket && sidebarView !== "overview" ? (
      <>
        <Button onClick={refreshTickets} size="sm" type="button" variant="outline">
          <RefreshCwIcon data-icon="inline-start" />
          Refresh
        </Button>
        <Button
          className="bg-destructive text-white hover:bg-destructive/90"
          onClick={resetEnvironment}
          size="sm"
          type="button"
          variant="destructive"
        >
          <RotateCcwIcon data-icon="inline-start" />
          Reset
        </Button>
      </>
    ) : undefined;

  return (
    <>
      <AppShell
        activeView={sidebarView}
        counts={sidebarCounts}
        headerAction={headerAction}
        headerBadges={headerBadges}
        headerDescription={headerDescription}
        onLogout={logout}
        onNavigate={handleSidebarView}
        onSelectTicket={selectTicket}
        pageTitle={pageTitle}
        profile={{
          email: session?.email ?? "",
          name: session?.name ?? "Technician",
          role: session?.role ?? "Technician",
        }}
        search={search}
        setSearch={setSearch}
        tickets={ticketList}
      >
        <div className="flex min-h-[calc(100svh-7rem)] flex-col">
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
              onStartAutodiagnosis={startAutodiagnosis}
              onStartAnalysis={startAnalysis}
              onSubmitActivity={submitActivity}
              onTabChange={setTicketTab}
              onUpdateCommand={updateActionCommand}
              pendingActions={pendingActions}
              autodiagnosisRunning={autodiagnosisRunning}
              backendRunId={backendRunId}
              canStartAutodiagnosis={canStartAutodiagnosis}
              runState={runState}
              selectedSystem={selectedSystem}
              setLogFilter={setLogFilter}
              submitStatus={submitStatus}
              systemLoaded={systemLoaded}
              terminalCommands={terminalCommands}
              terminalTranscript={terminalTranscript}
              ticket={selectedTicket}
              validation={validation}
            />
          ) : sidebarView === "overview" ? (
            <DashboardOverview
              highPriorityTickets={highPriorityTickets}
              onSelectTicket={selectTicket}
              stats={stats}
              tickets={ticketList}
            />
          ) : (
            <DashboardHome
              filteredTickets={filteredTickets}
              onSelectTicket={selectTicket}
              priorityFilter={priorityFilter}
              setPriorityFilter={setPriorityFilter}
              setSortBy={setSortBy}
              setStatusFilter={setStatusFilter}
              sortBy={sortBy}
              stats={stats}
              statusFilter={statusFilter}
            />
          )}
        </div>
      </AppShell>

      {notice ? <Toast message={notice} onDone={dismissNotice} /> : null}
    </>
  );
}

function getAppRouteState(): AppRouteState {
  const pathname = window.location.pathname.replace(/\/$/, "") || "/";
  const ticketMatch = pathname.match(/^\/app\/tickets\/(\d+)$/);
  const tab = getTicketTabFromQuery();

  if (ticketMatch) {
    return { tab, ticketId: Number(ticketMatch[1]), view: "all" };
  }

  if (pathname === "/app/tickets/assigned") {
    return { tab: "overview", ticketId: null, view: "assigned" };
  }

  if (pathname === "/app/tickets/high-priority") {
    return { tab: "overview", ticketId: null, view: "high" };
  }

  if (pathname === "/app/tickets/pending") {
    return { tab: "overview", ticketId: null, view: "pending" };
  }

  if (pathname === "/app/tickets") {
    return { tab: "overview", ticketId: null, view: "all" };
  }

  return { tab: "overview", ticketId: null, view: "overview" };
}

function pushAppRoute(path: string) {
  if (currentAppRoute() === path) {
    return;
  }

  window.history.pushState(null, "", path);
}

function replaceAppRoute(path: string) {
  if (currentAppRoute() === path) {
    return;
  }

  window.history.replaceState(null, "", path);
}

function currentAppRoute() {
  return `${window.location.pathname}${window.location.search}`;
}

function ticketRoute(ticketId: number, tab: TabId) {
  const search = new URLSearchParams();
  if (tab !== "overview") {
    search.set("tab", tab);
  }
  const query = search.toString();
  return `/app/tickets/${ticketId}${query ? `?${query}` : ""}`;
}

function getTicketTabFromQuery(): TabId {
  const tab = new URLSearchParams(window.location.search).get("tab");
  return isTicketTab(tab) ? tab : "overview";
}

function isTicketTab(tab: string | null): tab is TabId {
  return tab === "overview" || tab === "system" || tab === "analysis" || tab === "actions" || tab === "logs" || tab === "activity";
}

function upsertTicket(tickets: Ticket[], ticket: Ticket) {
  const exists = tickets.some((candidate) => candidate.id === ticket.id);
  if (!exists) {
    return [ticket, ...tickets];
  }

  return tickets.map((candidate) => (candidate.id === ticket.id ? ticket : candidate));
}

function upsertAction(actions: ProposedAction[], action: ProposedAction) {
  const exists = actions.some((candidate) => candidate.id === action.id);
  if (!exists) {
    return [...actions, action];
  }

  return actions.map((candidate) => (candidate.id === action.id ? action : candidate));
}

function getPageTitle(view: SidebarView) {
  if (view === "assigned") {
    return "Assigned tickets";
  }

  if (view === "high") {
    return "High priority";
  }

  if (view === "pending") {
    return "Pending approval";
  }

  if (view === "all") {
    return "All tickets";
  }

  return "Overview";
}
