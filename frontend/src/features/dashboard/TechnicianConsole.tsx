import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangleIcon, RefreshCwIcon, RotateCcwIcon } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyPanel, type DashboardStat, type SidebarCounts, type SidebarView } from "@/components/service-desk-ui";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { getQueueHeading } from "@/lib/queue";
import { Toast } from "../../components/ui/Toast";
import { useAuth } from "../auth/AuthProvider";
import {
  createEvent,
  emptyDraft,
  formatDate,
  initialValidation,
  isDraftComplete,
} from "../../lib/serviceDesk";
import {
  backendApi,
  getApiErrorMessage,
  runEventsWebSocketUrl,
  type BackendEmployee,
  type BackendMetricsSummaryRead,
  type BackendRunMetricsRead,
  type BackendRunStateRead,
  type BackendRunWebSocketEvent,
} from "../../services/backendApi";
import {
  employeeName,
  mapActivityDraft,
  mapAuditEvent,
  mapBackendCustomer,
  mapBackendAction,
  mapBackendCommandResultAction,
  mapBackendCustomerSystem,
  mapBackendTicket,
  mapRelatedTicket,
  mapRunState,
  mapTerminalCommand,
  mapTerminalTranscript,
  mapValidation,
} from "../../services/backendMapping";
import type {
  ActivityDraft,
  AgentPhase,
  CustomerSystem,
  EventType,
  Priority,
  ProposedAction,
  RelatedTicket,
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

const RESET_CONFIRMATION_TEXT = "reset assigned VMs";

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
  const [employee, setEmployee] = useState<BackendEmployee | null>(null);
  const [ticketList, setTicketList] = useState<Ticket[]>([]);
  const [systemsByTicket, setSystemsByTicket] = useState<Record<number, CustomerSystem>>({});
  const [backendReady, setBackendReady] = useState(false);
  const [ticketsLoading, setTicketsLoading] = useState(true);
  const [systemLoading, setSystemLoading] = useState(false);
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
  const [agentPhase, setAgentPhase] = useState<AgentPhase | null>(null);
  const [analysisReady, setAnalysisReady] = useState(false);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [autodiagnosisRunning, setAutodiagnosisRunning] = useState(false);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [terminalCommands, setTerminalCommands] = useState<TerminalCommandLog[]>([]);
  const [terminalTranscript, setTerminalTranscript] = useState<TerminalTranscriptLine[]>([]);
  const [metricsSummary, setMetricsSummary] = useState<BackendMetricsSummaryRead | null>(null);
  const [runMetrics, setRunMetrics] = useState<BackendRunMetricsRead | null>(null);
  const [relatedTicket, setRelatedTicket] = useState<RelatedTicket | null>(null);
  const [validation, setValidation] = useState<ValidationResult>(initialValidation);
  const [draft, setDraft] = useState<ActivityDraft>(emptyDraft);
  const [submitStatus, setSubmitStatus] = useState<"idle" | "submitted">("idle");
  const [logFilter, setLogFilter] = useState<"all" | EventType>("all");
  const [notice, setNotice] = useState("");
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetInFlight, setResetInFlight] = useState(false);
  const runEventCursorRef = useRef<number | null>(null);

  const selectedTicket = ticketList.find((ticket) => ticket.id === selectedTicketId) ?? null;
  const selectedSystem = selectedTicketId ? systemsByTicket[selectedTicketId] ?? null : null;
  const assignedTechnicianName = employee ? employeeName(employee) : session?.name ?? "Technician";
  const sidebarProfile = {
    email: employee?.username ?? session?.email ?? "",
    name: assignedTechnicianName,
    role: employee?.teamname ?? session?.role ?? "Technician",
  };
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
        const backendMetrics = await backendApi.getMetricsSummary().catch((error) => {
          setNotice(`Metrics summary failed to load. ${getApiErrorMessage(error)}`);
          return null;
        });

        if (cancelled) {
          return;
        }

        const assignedTo = employeeName(employee);
        setEmployee(employee);
        setTicketList(backendTickets.map((ticket) => mapBackendTicket(ticket, assignedTo)));
        setMetricsSummary(backendMetrics);
        setLastTicketFetchAt(new Date().toISOString());
        setBackendReady(true);
        if (backendMetrics) {
          setNotice("");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }

        setTicketList([]);
        setEmployee(null);
        setMetricsSummary(null);
        setLastTicketFetchAt(null);
        setBackendReady(false);
        setNotice(`Ticket queue failed to load. ${getApiErrorMessage(error)}`);
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
      High: 0,
      Medium: 1,
      Low: 2,
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
          (sidebarView === "high" && ticket.priority === "High") ||
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
    () => ticketList.filter((ticket) => ticket.priority === "High"),
    [ticketList],
  );

  const sidebarCounts = useMemo<SidebarCounts>(
    () => ({
      all: ticketList.length,
      assigned: ticketList.filter((ticket) => ticket.assignedTo === assignedTechnicianName || backendReady).length,
      high: ticketList.filter((ticket) => ticket.priority === "High").length,
      pending: ticketList.filter((ticket) => ticket.status === "PENDING").length,
    }),
    [assignedTechnicianName, backendReady, ticketList],
  );

  const stats = useMemo<DashboardStat[]>(() => {
    const total = Math.max(ticketList.length, 1);
    const openTickets = ticketList.filter((ticket) => ticket.status === "OPEN").length;
    const highTickets = ticketList.filter((ticket) => ticket.priority === "High").length;
    const runTotal = Math.max(metricsSummary?.run_count ?? 0, 1);

    return [
      {
        detail: `${openTickets} tickets still need diagnosis or documentation.`,
        label: "Open tickets",
        progress: (openTickets / total) * 100,
        tone: "default",
        value: openTickets,
      },
      {
        detail: "High priority work.",
        label: "High priority",
        progress: (highTickets / total) * 100,
        tone: highTickets ? "danger" : "success",
        value: highTickets,
      },
      {
        detail: metricsSummary
          ? `${metricsSummary.submitted_run_count} submitted, ${metricsSummary.failed_run_count} failed, ${metricsSummary.audit_event_count} audit events.`
          : "Backend metrics summary did not load.",
        label: "Active runs",
        progress: metricsSummary ? (metricsSummary.active_run_count / runTotal) * 100 : undefined,
        tone: metricsSummary?.failed_run_count ? "warning" : "default",
        value: metricsSummary ? metricsSummary.active_run_count : "unavailable",
      },
    ];
  }, [metricsSummary, ticketList]);

  const ticketAnalyticsStats = useMemo<DashboardStat[]>(() => {
    if (!backendRunId) {
      return [
        {
          detail: "Create and approve a backend run to load telemetry.",
          label: "Run metrics",
          tone: "warning",
          value: "waiting",
        },
      ];
    }

    if (!runMetrics) {
      return [
        {
          detail: "Metrics are loaded from the backend run telemetry endpoint.",
          label: "Run metrics",
          tone: "default",
          value: "loading",
        },
      ];
    }

    return [
      {
        detail: `${runMetrics.llm.tokens.prompt_tokens} input / ${runMetrics.llm.tokens.completion_tokens} output`,
        label: "LLM tokens",
        tone: runMetrics.llm.error_count ? "warning" : "default",
        value: runMetrics.llm.tokens.total_tokens,
      },
      {
        detail: `${runMetrics.llm.request_count} LLM requests, ${runMetrics.llm.error_count} errors`,
        label: "LLM latency",
        tone: runMetrics.llm.error_count ? "warning" : "default",
        value: formatMs(runMetrics.llm.latency.average_ms),
      },
      {
        detail: `${runMetrics.successful_command_count} successful / ${runMetrics.failed_command_count} failed`,
        label: "Command latency",
        tone: runMetrics.failed_command_count ? "warning" : "success",
        value: formatMs(runMetrics.command_latency.average_ms),
      },
      {
        detail: `${runMetrics.action_count} actions, ${runMetrics.command_result_count} stored command results`,
        label: "Audit events",
        tone: "default",
        value: runMetrics.audit_event_count,
      },
    ];
  }, [backendRunId, runMetrics]);

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

        setTicketList((currentTickets) =>
          upsertTicket(currentTickets, mapBackendTicket(backendTicket, assignedTechnicianName)),
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
  }, [assignedTechnicianName, backendReady, selectedTicketId]);

  const resetTicketWorkspace = useCallback((ticketId: number, tab: TabId = "overview") => {
    setSelectedTicketId(ticketId);
    setBackendRunId(null);
    setActiveTab(tab);
    setSystemLoaded(false);
    setSystemLoading(false);
    setConnectionStatus("not_requested");
    setRunState("idle");
    setAgentPhase(null);
    setAnalysisReady(false);
    setActions([]);
    setEvents([createEvent("approval", "Ticket opened", `Ticket ${ticketId} opened.`)]);
    setTerminalCommands([]);
    setTerminalTranscript([]);
    setRunMetrics(null);
    setRelatedTicket(null);
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
    setRelatedTicket(mapRelatedTicket(state.related_ticket));

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

  const refreshRunMetrics = useCallback(async (runId: string) => {
    try {
      setRunMetrics(await backendApi.getRunMetrics(runId));
    } catch (error) {
      setNotice(`Run metrics failed to load. ${getApiErrorMessage(error)}`);
    }
  }, []);

  const handleRunWebSocketEvent = useCallback((event: BackendRunWebSocketEvent) => {
    if (event.event_id !== null) {
      runEventCursorRef.current = event.event_id;
    }

    if (event.type === "ping") {
      return;
    }

    const phase = readAgentPhase(event.payload.phase);
    if (event.type === "agent_phase_selected" && phase) {
      setAgentPhase(phase);
      setAnalysisReady(true);
    }

    if (event.type === "safe_autodiagnosis_started") {
      setAgentPhase("diagnosis");
      setAutodiagnosisRunning(true);
      setAnalysisReady(true);
    }

    if (event.type === "command_running") {
      setAgentPhase("execution");
    }

    if (event.type === "command_result") {
      setAgentPhase("verification");
    }

    if (event.type === "validation_confirmed" || event.type === "activity_draft_generated") {
      setAgentPhase("final_analysis");
    }

    if (
      event.type === "safe_autodiagnosis_stopped" ||
      event.type === "agent_diagnostic_limit_reached" ||
      event.type === "command_blocked" ||
      event.type === "command_proposed" ||
      event.type === "safe_autodiagnosis_handed_to_human"
    ) {
      setAutodiagnosisRunning(false);
    }

    setEvents((currentEvents) => upsertRunEvent(currentEvents, mapRunWebSocketEvent(event)));

    if (
      event.type === "agent_diagnostic_result" ||
      event.type === "command_result" ||
      event.type === "command_failed" ||
      event.type === "command_proposed" ||
      event.type === "command_blocked" ||
      event.type === "safe_autodiagnosis_handed_to_human" ||
      event.type === "validation_confirmed" ||
      event.type === "activity_draft_generated" ||
      event.type === "activity_submitted"
    ) {
      void backendApi.getRun(event.run_id).then(syncRunState).catch(() => undefined);
      void refreshAuditEvents(event.run_id).catch(() => undefined);
      void refreshRunMetrics(event.run_id).catch(() => undefined);
    }
  }, [refreshAuditEvents, refreshRunMetrics, syncRunState]);

  useEffect(() => {
    runEventCursorRef.current = null;
  }, [backendRunId]);

  useEffect(() => {
    if (!backendReady || !backendRunId) {
      setRunMetrics(null);
      return;
    }

    void refreshRunMetrics(backendRunId);
  }, [backendReady, backendRunId, refreshRunMetrics]);

  useEffect(() => {
    if (!backendReady || !backendRunId) {
      return;
    }

    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;

    const connect = () => {
      socket = new WebSocket(runEventsWebSocketUrl(backendRunId, runEventCursorRef.current));

      socket.onmessage = (message) => {
        try {
          handleRunWebSocketEvent(JSON.parse(String(message.data)) as BackendRunWebSocketEvent);
        } catch {
          setEvents((currentEvents) =>
            upsertRunEvent(currentEvents, createEvent("error", "Run event ignored", "Backend sent an unreadable run event.")),
          );
        }
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, 1500);
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [backendReady, backendRunId, handleRunWebSocketEvent]);

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

    setSystemLoading(true);

    try {
      if (!backendReady) {
        throw new Error("Backend is unavailable.");
      }

      try {
        const backendSystem = await backendApi.getCustomerSystem(selectedTicket.id);
        setSystemsByTicket((currentSystems) => ({
          ...currentSystems,
          [selectedTicket.id]: mapBackendCustomerSystem(backendSystem),
        }));
      } catch (error) {
        if (selectedTicket.customerId) {
          const backendCustomer = await backendApi.getCustomer(selectedTicket.customerId);
          setSystemsByTicket((currentSystems) => ({
            ...currentSystems,
            [selectedTicket.id]: mapBackendCustomer(backendCustomer, selectedTicket.id),
          }));
        } else {
          throw error;
        }
      }

      setSystemLoaded(true);
      setConnectionStatus("awaiting_approval");
      setRunState("awaiting_connection_approval");
      appendEvent("approval", "System info loaded", "Redacted customer system context loaded.");
    } catch (error) {
      setSystemLoaded(false);
      setNotice(`System info failed to load. ${getApiErrorMessage(error)}`);
    } finally {
      setSystemLoading(false);
    }
  };

  const approveConnection = async () => {
    if (!selectedTicket || !systemLoaded) {
      return;
    }

    if (!backendReady) {
      setNotice("Backend is unavailable. Connection approval cannot continue.");
      return;
    }

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
      await refreshRunMetrics(confirmedState.run.id);
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
  };

  const startAnalysis = async () => {
    if (!selectedTicket) {
      return;
    }

    if (!backendReady || connectionStatus !== "connected" || !backendRunId) {
      setNotice("Approve the backend connection before starting analysis.");
      return;
    }

    try {
      const state = await backendApi.getRun(backendRunId);
      syncRunState(state);
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      setAnalysisReady(true);
      appendEvent("analysis", "Terminal agent ready", "Open the terminal and start the backend agent.");
      setTicketTab("actions");
      return;
    } catch (error) {
      setNotice(`Analysis state failed to load. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Analysis blocked", "Backend run state could not be loaded.");
      return;
    }
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
      await refreshRunMetrics(backendRunId);
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
      await refreshRunMetrics(backendRunId).catch(() => undefined);
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

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before approving commands.");
      return;
    }

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
      setAgentPhase("execution");
      window.setTimeout(() => {
        void backendApi.getRun(backendRunId).then(syncRunState).catch(() => undefined);
        void refreshAuditEvents(backendRunId);
        void refreshRunMetrics(backendRunId);
      }, 900);
      appendEvent("approval", "Action approved", action.title);
      return;
    } catch (error) {
      setNotice(`Action approval failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Action approval blocked", action.title);
      return;
    }
  };

  const rejectAction = async (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action) {
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before rejecting commands.");
      return;
    }

    const backendActionId = Number(actionId);

    try {
      const state = await backendApi.rejectAction(
        backendRunId,
        Number.isFinite(backendActionId) ? backendActionId : null,
      );
      syncRunState(state);
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      appendEvent("approval", "Action rejected", action.title);
      return;
    } catch (error) {
      setNotice(`Action rejection failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Action rejection blocked", action.title);
      return;
    }
  };

  const retryAction = async (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (!action) {
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before retrying commands.");
      return;
    }

    const backendActionId = Number(actionId);

    try {
      const state = await backendApi.retryAction(
        backendRunId,
        Number.isFinite(backendActionId) ? backendActionId : null,
      );
      syncRunState(state);
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      appendEvent("approval", "Action queued again", action.title);
      return;
    } catch (error) {
      setNotice(`Action retry failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Action retry blocked", action.title);
      return;
    }
  };

  const requestSaferAlternative = async (actionId: string) => {
    const action = actions.find((candidate) => candidate.id === actionId);

    if (backendReady && backendRunId) {
      const backendActionId = Number(actionId);

      try {
        const state = await backendApi.saferAlternative(
          backendRunId,
          Number.isFinite(backendActionId) ? backendActionId : null,
        );
        syncRunState(state);
        await refreshAuditEvents(backendRunId);
        appendEvent(
          "approval",
          "Safer alternative requested",
          action?.title ?? "Technician requested a safer command alternative.",
        );
        setTicketTab("actions");
        return;
      } catch (error) {
        setNotice(`Safer alternative failed. ${getApiErrorMessage(error)}`);
        return;
      }
    }

    setNotice("Safer alternatives require an active backend run.");
  };

  const abortRun = async () => {
    if (!selectedTicket) {
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before aborting.");
      return;
    }

    try {
      const state = await backendApi.abortRun(backendRunId);
      syncRunState(state);
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      setConnectionStatus((current) => (current === "connected" ? "disconnected" : current));
      appendEvent("error", "Run aborted", "Technician stopped the backend run.");
      return;
    } catch (error) {
      setNotice(`Abort failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Abort blocked", "Backend did not abort the run.");
      return;
    }
  };

  const runValidation = async () => {
    if (!selectedTicket) {
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before confirming validation.");
      return;
    }

    const evidence = "Technician confirmed service behavior after approved action execution.";
    setAgentPhase("verification");

    try {
      const state = await backendApi.confirmValidation(backendRunId, evidence);
      syncRunState(state);
      setAgentPhase("final_analysis");
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      appendEvent("validation", "Validation passed", evidence);
      return;
    } catch (error) {
      setNotice(`Validation confirmation failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Validation blocked", "Backend did not accept the validation evidence.");
      return;
    }
  };

  const generateDraft = async () => {
    if (!selectedTicket) {
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before generating an activity draft.");
      return;
    }

    try {
      const draftResponse = await backendApi.generateActivityDraft(backendRunId);
      setDraft(mapActivityDraft(draftResponse));
      setAgentPhase("final_analysis");
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      appendEvent("output", "Activity draft generated", "Backend generated the ERP activity draft.");
      setTicketTab("activity");
      return;
    } catch (error) {
      setNotice(`Activity draft generation failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Activity draft blocked", "Backend did not generate a draft.");
      return;
    }
  };

  const saveDraft = async () => {
    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before saving an activity draft.");
      return;
    }

    try {
      const draftResponse = await backendApi.updateActivityDraft(backendRunId, {
        actions_taken: draft.actions_taken,
        commands_summary: draft.commands_summary,
        description: draft.summary,
        root_cause: draft.root_cause,
        summary: draft.summary,
        validation_result: draft.validation_result,
      });
      setDraft(mapActivityDraft(draftResponse));
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      setNotice("Activity draft saved to backend.");
      return;
    } catch (error) {
      setNotice(`Activity draft save failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Activity draft save blocked", "Backend did not save the draft.");
      return;
    }
  };

  const reviewDraft = async () => {
    if (!isDraftComplete(draft)) {
      setNotice("Complete every activity field before marking the draft reviewed.");
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before reviewing an activity draft.");
      return;
    }

    try {
      await backendApi.updateActivityDraft(backendRunId, {
        actions_taken: draft.actions_taken,
        commands_summary: draft.commands_summary,
        description: draft.summary,
        root_cause: draft.root_cause,
        summary: draft.summary,
        validation_result: draft.validation_result,
      });
      const draftResponse = await backendApi.reviewActivityDraft(backendRunId, true);
      setDraft(mapActivityDraft(draftResponse));
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      setNotice("Activity draft marked reviewed.");
      return;
    } catch (error) {
      setNotice(`Activity draft review failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Activity draft review blocked", "Backend did not mark the draft reviewed.");
      return;
    }
  };

  const submitActivity = async () => {
    if (!isDraftComplete(draft)) {
      setNotice("Complete every activity field before submitting.");
      return;
    }

    if (!backendReady || !backendRunId) {
      setNotice("Backend run is required before submitting activity.");
      return;
    }

    const ticketId = selectedTicket?.id;

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
      if (ticketId) {
        await backendApi.setTicketStatus(ticketId, "DONE");
      }
      const state = await backendApi.getRun(backendRunId);
      syncRunState(state);
      if (ticketId) {
        updateTicketStatus(ticketId, "DONE");
      }
      setSubmitStatus("submitted");
      setAgentPhase("final_analysis");
      setNotice("Activity submitted to backend.");
      await refreshAuditEvents(backendRunId);
      await refreshRunMetrics(backendRunId);
      const backendMetrics = await backendApi.getMetricsSummary().catch(() => null);
      if (backendMetrics) {
        setMetricsSummary(backendMetrics);
      }
      appendEvent("output", "Activity submitted", "Backend ERP activity submission completed.");
      return;
    } catch (error) {
      setNotice(`Activity submission failed. ${getApiErrorMessage(error)}`);
      appendEvent("error", "Activity submission blocked", "Backend did not submit the ERP activity.");
      return;
    }
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
      setNotice("Backend ticket queue is unavailable.");
      return;
    }

    setTicketsLoading(true);

    try {
      const [backendTickets, backendMetrics] = await Promise.all([
        backendApi.listTickets({
          priority: priorityFilter === "all" ? null : priorityFilter,
          sort: sortBy,
          status: statusFilter === "all" ? null : statusFilter,
        }),
        backendApi.getMetricsSummary().catch(() => null),
      ]);
      setTicketList(backendTickets.map((ticket) => mapBackendTicket(ticket, assignedTechnicianName)));
      setMetricsSummary(backendMetrics);
      setLastTicketFetchAt(new Date().toISOString());
      setNotice("Backend ticket queue refreshed.");
    } catch (error) {
      setNotice(`Ticket refresh failed. ${getApiErrorMessage(error)}`);
    } finally {
      setTicketsLoading(false);
    }
  };

  const resetEnvironment = async () => {
    if (resetConfirmation.trim() !== RESET_CONFIRMATION_TEXT) {
      setNotice(`Type "${RESET_CONFIRMATION_TEXT}" before resetting assigned VMs.`);
      return;
    }

    setResetInFlight(true);

    try {
      const response = await backendApi.resetEnvironment();
      const [backendTickets, backendMetrics] = await Promise.all([
        backendApi.listTickets({
          priority: priorityFilter === "all" ? null : priorityFilter,
          sort: sortBy,
          status: statusFilter === "all" ? null : statusFilter,
        }),
        backendApi.getMetricsSummary().catch(() => null),
      ]);
      setTicketList(backendTickets.map((ticket) => mapBackendTicket(ticket, assignedTechnicianName)));
      setMetricsSummary(backendMetrics);
      setLastTicketFetchAt(new Date().toISOString());
      setSelectedTicketId(null);
      setBackendRunId(null);
      setActiveTab("overview");
      setSystemLoaded(false);
      setSystemLoading(false);
      setConnectionStatus("not_requested");
      setRunState("idle");
      setAgentPhase(null);
      setAnalysisReady(false);
      setActions([]);
      setEvents([]);
      setTerminalCommands([]);
      setTerminalTranscript([]);
      setRunMetrics(null);
      setRelatedTicket(null);
      setValidation(initialValidation);
      setDraft(emptyDraft);
      setSubmitStatus("idle");
      setNotice(response.message || "VM reset requested.");
      setResetDialogOpen(false);
      setResetConfirmation("");
    } catch (error) {
      setNotice(`VM reset failed. ${getApiErrorMessage(error)}`);
    } finally {
      setResetInFlight(false);
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
  const ticketRouteLoading = Boolean(selectedTicketId && ticketsLoading && !selectedTicket);
  const pageTitle = selectedTicket
    ? `Ticket #${selectedTicket.id}`
    : ticketRouteLoading
      ? "Ticket"
    : sidebarView === "overview"
      ? "Service desk overview"
      : queueHeading.title;
  const headerDescription = selectedTicket
    ? undefined
    : ticketRouteLoading
      ? "Loading ticket details."
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
          onClick={() => setResetDialogOpen(true)}
          size="sm"
          type="button"
          variant="destructive"
        >
          <RotateCcwIcon data-icon="inline-start" />
          Reset environment
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
        profile={sidebarProfile}
        search={search}
        setSearch={setSearch}
        loading={ticketsLoading}
        tickets={ticketList}
      >
        <div className="flex min-h-[calc(100svh-7rem)] flex-col">
          {selectedTicket ? (
            <TicketWorkspace
              activeTab={activeTab}
              actions={actions}
              agentPhase={agentPhase}
              analyticsStats={ticketAnalyticsStats}
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
              onSaferAlternative={requestSaferAlternative}
              onReviewDraft={reviewDraft}
              onSaveDraft={saveDraft}
              onStartAutodiagnosis={startAutodiagnosis}
              onStartAnalysis={startAnalysis}
              onSubmitActivity={submitActivity}
              onTabChange={setTicketTab}
              onUpdateCommand={updateActionCommand}
              pendingActions={pendingActions}
              relatedTicket={relatedTicket}
              autodiagnosisRunning={autodiagnosisRunning}
              backendRunId={backendRunId}
              canStartAutodiagnosis={canStartAutodiagnosis}
              runState={runState}
              selectedSystem={selectedSystem}
              setLogFilter={setLogFilter}
              submitStatus={submitStatus}
              systemLoaded={systemLoaded}
              systemLoading={systemLoading}
              terminalCommands={terminalCommands}
              terminalTranscript={terminalTranscript}
              ticket={selectedTicket}
              validation={validation}
            />
          ) : ticketRouteLoading ? (
            <TicketWorkspaceSkeleton />
          ) : selectedTicketId ? (
            <EmptyPanel detail="The ticket was not returned by the backend." title="Ticket not found" />
          ) : sidebarView === "overview" ? (
            <DashboardOverview
              highPriorityTickets={highPriorityTickets}
              loading={ticketsLoading}
              onSelectTicket={selectTicket}
              stats={stats}
              tickets={ticketList}
            />
          ) : (
            <DashboardHome
              filteredTickets={filteredTickets}
              loading={ticketsLoading}
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

      <ResetEnvironmentDialog
        confirmation={resetConfirmation}
        inFlight={resetInFlight}
        onConfirm={resetEnvironment}
        onConfirmationChange={setResetConfirmation}
        onOpenChange={(open) => {
          if (resetInFlight) {
            return;
          }
          setResetDialogOpen(open);
          if (!open) {
            setResetConfirmation("");
          }
        }}
        open={resetDialogOpen}
      />

      {notice ? <Toast message={notice} onDone={dismissNotice} /> : null}
    </>
  );
}

function ResetEnvironmentDialog({
  confirmation,
  inFlight,
  onConfirm,
  onConfirmationChange,
  onOpenChange,
  open,
}: {
  confirmation: string;
  inFlight: boolean;
  onConfirm: () => void;
  onConfirmationChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
}) {
  const canReset = confirmation.trim() === RESET_CONFIRMATION_TEXT;

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
              <AlertTriangleIcon className="size-4" />
            </span>
            <div className="grid gap-2">
              <DialogTitle>Reset assigned VMs?</DialogTitle>
              <DialogDescription>
                This clears generated activities and requests a reboot of the assigned customer VMs. Use it only when
                restarting the evaluation environment is intentional.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <label className="grid gap-1.5">
          <span className="text-sm font-medium text-foreground">
            Type <code className="rounded border bg-muted px-1 py-0.5">{RESET_CONFIRMATION_TEXT}</code> to continue
          </span>
          <Input
            aria-invalid={Boolean(confirmation) && !canReset}
            autoComplete="off"
            onChange={(event) => onConfirmationChange(event.target.value)}
            value={confirmation}
          />
        </label>
        <DialogFooter>
          <Button disabled={inFlight} onClick={() => onOpenChange(false)} type="button" variant="outline">
            Cancel
          </Button>
          <Button disabled={!canReset || inFlight} onClick={onConfirm} type="button" variant="destructive">
            {inFlight ? "Resetting environment" : "Reset assigned VMs"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

function formatMs(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "n/a";
  }

  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}s`;
  }

  return `${Math.round(value)}ms`;
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

function readAgentPhase(value: unknown): AgentPhase | null {
  if (
    value === "diagnosis" ||
    value === "execution" ||
    value === "verification" ||
    value === "final_analysis"
  ) {
    return value;
  }

  return null;
}

function formatAgentPhaseLabel(phase: AgentPhase) {
  switch (phase) {
    case "diagnosis":
      return "Diagnosis";
    case "execution":
      return "Fixing";
    case "verification":
      return "Verifying";
    case "final_analysis":
      return "Final Analysis";
  }
}

function mapRunWebSocketEvent(event: BackendRunWebSocketEvent): RunEvent {
  const phase = readAgentPhase(event.payload.phase);
  const time = event.timestamp
    ? new Date(event.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });

  return {
    detail: runWebSocketEventDetail(event, phase),
    id: event.event_id === null ? `ws-${event.type}-${time}` : `ws-${event.event_id}`,
    time,
    title: runWebSocketEventTitle(event.type, phase),
    type: runWebSocketEventType(event),
  };
}

function runWebSocketEventTitle(type: string, phase: AgentPhase | null) {
  if (type === "agent_phase_selected" && phase) {
    return `Agent phase: ${formatAgentPhaseLabel(phase)}`;
  }

  if (type === "safe_autodiagnosis_started") {
    return "Safe autodiagnosis started";
  }

  if (type === "safe_autodiagnosis_stopped") {
    return "Safe autodiagnosis stopped";
  }

  if (type === "agent_diagnostic_result") {
    return "Diagnostic result captured";
  }

  return type.split("_").join(" ");
}

function runWebSocketEventDetail(event: BackendRunWebSocketEvent, phase: AgentPhase | null) {
  if (event.type === "agent_phase_selected" && phase) {
    return `Current phase is ${formatAgentPhaseLabel(phase)}.`;
  }

  if (event.type === "agent_diagnostic_result") {
    const tool = typeof event.payload.tool === "string" ? event.payload.tool : "diagnostic tool";
    const exitCode = typeof event.payload.exit_code === "number" ? event.payload.exit_code : "unknown";
    return `${tool} finished with exit ${exitCode}. Redacted details are available in the logs.`;
  }

  if (event.type === "safe_autodiagnosis_started") {
    const maxSteps = typeof event.payload.max_steps === "number" ? event.payload.max_steps : null;
    return maxSteps
      ? `Backend will run up to ${maxSteps} allowlisted read-only diagnostic tools.`
      : "Backend will run allowlisted read-only diagnostic tools.";
  }

  if (event.type === "safe_autodiagnosis_stopped") {
    const reason = typeof event.payload.reason === "string" ? event.payload.reason.split("_").join(" ") : "completed or paused";
    return `Reason: ${reason}.`;
  }

  return JSON.stringify(event.payload);
}

function runWebSocketEventType(event: BackendRunWebSocketEvent): EventType {
  const type = event.type;
  const reason = typeof event.payload.reason === "string" ? event.payload.reason : "";

  if (type === "safe_autodiagnosis_stopped" && reason === "human_approval_required") {
    return "approval";
  }

  if (type.includes("validation")) {
    return "validation";
  }
  if (type.includes("command") || type.includes("ssh")) {
    return "command";
  }
  if (type.includes("approval") || type.includes("confirmed") || type.includes("review")) {
    return "approval";
  }
  if (type.includes("blocked") || type.includes("failed") || type.includes("abort") || type.includes("stopped")) {
    return "error";
  }
  if (type.includes("result") || type.includes("activity")) {
    return "output";
  }
  return "analysis";
}

function upsertTicket(tickets: Ticket[], ticket: Ticket) {
  const exists = tickets.some((candidate) => candidate.id === ticket.id);
  if (!exists) {
    return [ticket, ...tickets];
  }

  return tickets.map((candidate) => (candidate.id === ticket.id ? ticket : candidate));
}

function upsertRunEvent(events: RunEvent[], event: RunEvent) {
  if (!events.some((candidate) => candidate.id === event.id)) {
    return [...events, event];
  }

  return events.map((candidate) => (candidate.id === event.id ? event : candidate));
}

function TicketWorkspaceSkeleton() {
  return (
    <section className="flex flex-1 flex-col gap-5">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-8 w-72" />
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-5 w-16" />
        </div>
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton className="h-9 w-24" key={index} />
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div className="rounded-lg border bg-card p-4" key={index}>
            <Skeleton className="h-4 w-32" />
            <Skeleton className="mt-3 h-8 w-16" />
            <Skeleton className="mt-6 h-16 w-full" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-lg border bg-card p-5">
          <Skeleton className="h-7 w-48" />
          <div className="mt-8 flex flex-col gap-3">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-11/12" />
            <Skeleton className="h-5 w-4/5" />
          </div>
        </div>
        <div className="rounded-lg border bg-card p-5">
          <Skeleton className="h-7 w-36" />
          <div className="mt-6 flex flex-col gap-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton className="h-5 w-full" key={index} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
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
