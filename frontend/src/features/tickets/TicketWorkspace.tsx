import { lazy, Suspense, useEffect, useState } from "react";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  CheckIcon,
  ClipboardCheckIcon,
  Loader2Icon,
  PlayIcon,
  ShieldCheckIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react";

import { MarkdownContent } from "@/components/ui/MarkdownContent";
import {
  DefinitionTable,
  EmptyState,
  EventTable,
  LogFilter,
  StatusLabel,
  TruncatedText,
} from "@/components/ui/primitives";
import {
  PageHeading,
  StatsGrid,
  type DashboardStat,
} from "@/components/service-desk-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { BackendLlmMetricsRead } from "@/services/backendApi";
import {
  formatConnection,
  formatDate,
  formatRunState,
  isDraftComplete,
} from "@/lib/serviceDesk";
import type {
  ActivityDraft,
  AgentPhase,
  ConnectionStatus,
  CustomerSystem,
  EventType,
  ProposedAction,
  RelatedTicket,
  RunEvent,
  RunState,
  TabId,
  TerminalCommandLog,
  TerminalTranscriptLine,
  Ticket,
  ValidationResult,
} from "@/types";

const TicketTerminal = lazy(() =>
  import("./TicketTerminal").then((module) => ({ default: module.TicketTerminal })),
);

type ConnectionIntent = "analysis" | "autodiagnosis" | "terminal";

const TICKET_TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "system", label: "System" },
  { id: "analysis", label: "Analysis" },
  { id: "actions", label: "Terminal" },
  { id: "logs", label: "Logs" },
  { id: "activity", label: "Activity" },
];

export function TicketWorkspace(props: {
  activeTab: TabId;
  actions: ProposedAction[];
  agentPhase: AgentPhase | null;
  analyticsStats: DashboardStat[];
  analysisReady: boolean;
  backendRunId: string | null;
  connectionStatus: ConnectionStatus;
  draft: ActivityDraft;
  draftGenerating: boolean;
  events: RunEvent[];
  executedActions: ProposedAction[];
  logFilter: "all" | EventType;
  llmMetrics: BackendLlmMetricsRead | null;
  notice: string;
  onAbort: () => void;
  onApproveAction: (actionId: string) => void;
  onApproveConnection: () => Promise<void> | void;
  onBackToTickets: () => void;
  onCopyAudit: () => void;
  onDraftChange: (draft: ActivityDraft) => void;
  onGenerateDraft: () => void;
  onLoadSystem: () => Promise<void> | void;
  onAgentPhaseChange: (phase: AgentPhase) => void;
  onTerminalConnectionError: (message: string) => void;
  onRejectAction: (actionId: string) => void;
  onReviewDraft: () => void;
  onRetryAction: (actionId: string) => void;
  onRunValidation: () => void;
  onSaferAlternative: (actionId: string) => void;
  onSaveDraft: () => void;
  onStartAutodiagnosis: () => void;
  onStartAnalysis: () => void;
  onSubmitActivity: () => void;
  onTabChange: (tabId: TabId) => void;
  onUpdateCommand: (actionId: string, command: string) => void;
  pendingActions: ProposedAction[];
  relatedTicket: RelatedTicket | null;
  autodiagnosisRunning: boolean;
  autoStartAgentRequestId: number;
  runState: RunState;
  canStartAutodiagnosis: boolean;
  selectedSystem: CustomerSystem | null;
  setLogFilter: (filter: "all" | EventType) => void;
  submitStatus: "idle" | "submitted";
  systemLoaded: boolean;
  systemLoading: boolean;
  terminalCommands: TerminalCommandLog[];
  terminalTranscript: TerminalTranscriptLine[];
  ticket: Ticket;
  validation: ValidationResult;
}) {
  const [abortDialogOpen, setAbortDialogOpen] = useState(false);
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);
  const [connectionIntent, setConnectionIntent] = useState<ConnectionIntent | null>(null);
  const pendingMessage =
    props.systemLoaded && props.connectionStatus === "awaiting_approval"
      ? "Connection approval required"
      : props.pendingActions.length
        ? "Action approval required"
        : "";
  const requestConnectionApproval = async (intent: ConnectionIntent) => {
    setConnectionIntent(intent);

    if (!props.systemLoaded) {
      await props.onLoadSystem();
    }

    setConnectionDialogOpen(true);
  };

  useEffect(() => {
    if (props.connectionStatus !== "connected" || !connectionIntent) {
      return;
    }

    const approvedIntent = connectionIntent;
    setConnectionIntent(null);
    setConnectionDialogOpen(false);

    if (approvedIntent === "analysis") {
      props.onStartAnalysis();
      return;
    }

    if (approvedIntent === "autodiagnosis") {
      props.onStartAutodiagnosis();
      return;
    }

    props.onTabChange("actions");
  }, [
    connectionIntent,
    props.connectionStatus,
    props.onStartAnalysis,
    props.onStartAutodiagnosis,
    props.onTabChange,
  ]);

  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeading
        action={
          <div className="flex items-center gap-2">
            <Button onClick={props.onBackToTickets} size="sm" type="button" variant="outline">
              <ArrowLeftIcon data-icon="inline-start" />
              Tickets
            </Button>
            <Button
              disabled={props.runState === "idle" || props.runState === "submitted" || props.runState === "aborted"}
              onClick={() => setAbortDialogOpen(true)}
              size="sm"
              type="button"
              variant="destructive"
            >
              <XIcon data-icon="inline-start" />
              Abort
            </Button>
          </div>
        }
        badges={
          <>
            <StatusLabel label={props.ticket.priority} />
            <StatusLabel label={props.ticket.status} />
            <StatusLabel label={formatRunState(props.runState)} />
          </>
        }
        description={`${props.ticket.customer} · updated ${formatDate(props.ticket.updatedAt)}`}
        title={props.ticket.title}
      />

      <AgentPhaseProgress
        autodiagnosisRunning={props.autodiagnosisRunning}
        phase={props.agentPhase}
        runState={props.runState}
      />

      {pendingMessage ? (
        <Card className="border-destructive/30 bg-destructive/10" size="sm">
          <CardContent className="flex items-center gap-3">
            <AlertTriangleIcon className="text-destructive" />
            <div>
              <p className="font-medium text-foreground">{pendingMessage}</p>
              <p className="text-sm text-muted-foreground">Review is required before backend or system action.</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Tabs onValueChange={(value) => props.onTabChange(value as TabId)} value={props.activeTab}>
        <div className="-mx-1 max-w-full overflow-x-auto px-1 pb-1">
          <TabsList className="min-w-max gap-2" variant="line">
            {TICKET_TABS.map((tab) => (
              <TabsTrigger key={tab.id} value={tab.id}>
                {tab.label}
                {tab.id === "actions" && props.pendingActions.length ? (
                  <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive/20 px-1.5 text-[10px] font-medium leading-none text-destructive">
                    {props.pendingActions.length}
                  </span>
                ) : null}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="overview">
          <OverviewTab
            analysisReady={props.analysisReady}
            connectionStatus={props.connectionStatus}
            onGenerateDraft={props.onGenerateDraft}
            onLoadSystem={props.onLoadSystem}
            onOpenActivity={() => props.onTabChange("activity")}
            onOpenTerminal={() => props.onTabChange("actions")}
            onRunValidation={props.onRunValidation}
            onRequestConnectionApproval={requestConnectionApproval}
            onStartAutodiagnosis={props.onStartAutodiagnosis}
            onStartAnalysis={props.onStartAnalysis}
            pendingApprovals={props.pendingActions.length}
            runState={props.runState}
            autodiagnosisRunning={props.autodiagnosisRunning}
            canStartAutodiagnosis={props.canStartAutodiagnosis}
            executedActionCount={props.executedActions.length}
            systemLoaded={props.systemLoaded}
            ticket={props.ticket}
            validation={props.validation}
          />
        </TabsContent>
        <TabsContent value="system">
          <SystemTab
            connectionStatus={props.connectionStatus}
            onLoadSystem={props.onLoadSystem}
            onOpenTerminal={() => props.onTabChange("actions")}
            system={props.selectedSystem}
            systemLoaded={props.systemLoaded}
            systemLoading={props.systemLoading}
          />
        </TabsContent>
        <TabsContent value="analysis">
          <AnalysisTab
            actions={props.actions}
            analyticsStats={props.analyticsStats}
            analysisReady={props.analysisReady}
            connectionStatus={props.connectionStatus}
            llmMetrics={props.llmMetrics}
            onRequestConnectionApproval={requestConnectionApproval}
            onStartAutodiagnosis={props.onStartAutodiagnosis}
            onStartAnalysis={props.onStartAnalysis}
            relatedTicket={props.relatedTicket}
            terminalCommands={props.terminalCommands}
            autodiagnosisRunning={props.autodiagnosisRunning}
            canStartAutodiagnosis={props.canStartAutodiagnosis}
          />
        </TabsContent>
        <TabsContent
          className="h-[clamp(340px,calc(100svh-21rem),620px)] min-h-0 data-[state=inactive]:hidden"
          forceMount
          value="actions"
        >
          <ActionsTab
            autodiagnosisRunning={props.autodiagnosisRunning}
            autoStartAgentRequestId={props.autoStartAgentRequestId}
            canStartAutodiagnosis={props.canStartAutodiagnosis}
            connectionStatus={props.connectionStatus}
            onLoadSystem={props.onLoadSystem}
            onAgentPhaseChange={props.onAgentPhaseChange}
            onRequestConnectionApproval={requestConnectionApproval}
            onStartAutodiagnosis={props.onStartAutodiagnosis}
            onTerminalConnectionError={props.onTerminalConnectionError}
            runId={props.backendRunId}
            systemLoaded={props.systemLoaded}
            systemLoading={props.systemLoading}
          />
        </TabsContent>
        <TabsContent value="logs">
          <LogsTab
            events={props.events}
            logFilter={props.logFilter}
            onCopy={props.onCopyAudit}
            onFilterChange={props.setLogFilter}
            terminalCommands={props.terminalCommands}
            terminalTranscript={props.terminalTranscript}
          />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityTab
            draft={props.draft}
            draftGenerating={props.draftGenerating}
            notice={props.notice}
            onDraftChange={props.onDraftChange}
            onGenerateDraft={props.onGenerateDraft}
            onRunValidation={props.onRunValidation}
            onReview={props.onReviewDraft}
            onSave={props.onSaveDraft}
            onSubmit={props.onSubmitActivity}
            runState={props.runState}
            submitStatus={props.submitStatus}
            validation={props.validation}
          />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        confirmLabel="Abort run"
        description="This stops the current run, disconnects any active terminal session, and reloads the workspace."
        onConfirm={props.onAbort}
        onOpenChange={setAbortDialogOpen}
        open={abortDialogOpen}
        title="Abort run?"
        variant="destructive"
      />
      <ConfirmDialog
        confirmLabel="Approve connection"
        description={getConnectionApprovalDescription(connectionIntent)}
        onConfirm={props.onApproveConnection}
        onOpenChange={setConnectionDialogOpen}
        open={connectionDialogOpen}
        title="Approve backend connection?"
      />
    </section>
  );
}

const AGENT_PHASE_STEPS: Array<{ phase: AgentPhase; label: string }> = [
  { phase: "diagnosis", label: "Diagnosis" },
  { phase: "execution", label: "Fixing" },
  { phase: "recovery", label: "Recovery" },
  { phase: "verification", label: "Verifying" },
  { phase: "final_analysis", label: "Final Analysis" },
];

function AgentPhaseProgress({
  autodiagnosisRunning,
  phase,
  runState,
}: {
  autodiagnosisRunning: boolean;
  phase: AgentPhase | null;
  runState: RunState;
}) {
  const effectivePhase = phase ?? phaseFromRunState(runState);
  const activeIndex =
    effectivePhase === "waiting"
      ? -1
      : AGENT_PHASE_STEPS.findIndex((step) => step.phase === effectivePhase);
  const currentLabel = effectivePhase === "waiting" ? "Waiting" : AGENT_PHASE_STEPS[activeIndex]?.label ?? "Waiting";

  return (
    <div className="rounded-lg border bg-muted/20 px-4 py-3">
      <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-center">
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-sm font-medium text-foreground">Agent phase</span>
          <StatusLabel label={currentLabel} />
        </div>
        <div className="min-w-0 flex-1 overflow-x-auto">
          <ol className="relative flex min-w-[620px] py-1">
            {AGENT_PHASE_STEPS.map((step, index) => {
              const active = index === activeIndex;
              const completed = activeIndex > index;
              const reached = active || completed;

              return (
                <li
                  aria-current={active ? "step" : undefined}
                  className="relative min-w-28 flex-1"
                  key={step.phase}
                >
                  {index < AGENT_PHASE_STEPS.length - 1 ? (
                    <span
                      className={cn(
                        "absolute left-1/2 right-[-50%] top-2 h-px",
                        reached ? "bg-primary/70" : "bg-border",
                      )}
                      aria-hidden="true"
                    />
                  ) : null}
                  <div className="relative z-10 flex justify-center">
                    <span
                      className={cn(
                        "flex size-4 shrink-0 rounded-full border-2 bg-background",
                        active
                          ? "border-primary ring-4 ring-primary/20"
                          : completed
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/40",
                      )}
                    />
                  </div>
                  <div className="mt-2 px-2 text-center">
                    <p className={cn("text-sm font-medium", reached ? "text-foreground" : "text-muted-foreground")}>
                      {step.label}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
      {autodiagnosisRunning ? (
        <div className="mt-3 flex justify-end">
          <span className="rounded-full border border-border bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">
            Autonomous diagnosis running
          </span>
        </div>
      ) : null}
    </div>
  );
}

function phaseFromRunState(runState: RunState): AgentPhase | "waiting" {
  switch (runState) {
    case "analyzing":
      return "diagnosis";
    case "awaiting_action_approval":
    case "executing":
      return "execution";
    case "validating":
      return "verification";
    case "ready_to_submit":
    case "submitted":
      return "final_analysis";
    case "idle":
    case "awaiting_connection_approval":
    case "aborted":
      return "waiting";
  }
}

function OverviewTab({
  analysisReady,
  autodiagnosisRunning,
  canStartAutodiagnosis,
  connectionStatus,
  executedActionCount,
  onGenerateDraft,
  onLoadSystem,
  onOpenActivity,
  onOpenTerminal,
  onRunValidation,
  onRequestConnectionApproval,
  onStartAutodiagnosis,
  onStartAnalysis,
  pendingApprovals,
  runState,
  systemLoaded,
  ticket,
  validation,
}: {
  analysisReady: boolean;
  autodiagnosisRunning: boolean;
  canStartAutodiagnosis: boolean;
  connectionStatus: ConnectionStatus;
  executedActionCount: number;
  onGenerateDraft: () => void;
  onLoadSystem: () => void;
  onOpenActivity: () => void;
  onOpenTerminal: () => void;
  onRunValidation: () => void;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
  onStartAutodiagnosis: () => void;
  onStartAnalysis: () => void;
  pendingApprovals: number;
  runState: RunState;
  systemLoaded: boolean;
  ticket: Ticket;
  validation: ValidationResult;
}) {
  const requiresConnection = connectionStatus !== "connected";
  const handleStartAnalysis = () => {
    if (requiresConnection) {
      onRequestConnectionApproval("analysis");
      return;
    }

    onStartAnalysis();
  };
  const handleOpenTerminal = () => {
    if (requiresConnection) {
      onRequestConnectionApproval("terminal");
      return;
    }

    onOpenTerminal();
  };

  return (
    <div className="flex flex-col gap-4">
      <IncidentPath
        analysisReady={analysisReady}
        autodiagnosisRunning={autodiagnosisRunning}
        canStartAutodiagnosis={canStartAutodiagnosis}
        connectionStatus={connectionStatus}
        onGenerateDraft={onGenerateDraft}
        onLoadSystem={onLoadSystem}
        onOpenActivity={onOpenActivity}
        onOpenTerminal={handleOpenTerminal}
        onRunValidation={onRunValidation}
        onRequestConnectionApproval={onRequestConnectionApproval}
        onStartAutodiagnosis={onStartAutodiagnosis}
        onStartAnalysis={handleStartAnalysis}
        pendingApprovals={pendingApprovals}
        runState={runState}
        executedActionCount={executedActionCount}
        systemLoaded={systemLoaded}
        validation={validation}
      />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>Customer report</CardTitle>
            <CardDescription>{formatRunState(runState)}</CardDescription>
          </CardHeader>
          <CardContent>
            <MarkdownContent omitFirstHeading="Customer report">{ticket.report}</MarkdownContent>
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Ticket facts</CardTitle>
            <CardDescription>ERP ticket context.</CardDescription>
          </CardHeader>
          <CardContent>
            <DefinitionTable
              rows={[
                ["Customer", ticket.customer],
                ["Priority", ticket.priority],
                ["Status", ticket.status],
                ["Created", formatDate(ticket.createdAt)],
                ["Updated", formatDate(ticket.updatedAt)],
                ["Technician", ticket.assignedTo],
              ]}
            />
          </CardContent>
        </Card>

      </div>
    </div>
  );
}

function IncidentPath({
  analysisReady,
  autodiagnosisRunning,
  canStartAutodiagnosis,
  connectionStatus,
  executedActionCount,
  onGenerateDraft,
  onLoadSystem,
  onOpenActivity,
  onOpenTerminal,
  onRunValidation,
  onRequestConnectionApproval,
  onStartAutodiagnosis,
  onStartAnalysis,
  pendingApprovals,
  runState,
  systemLoaded,
  validation,
}: {
  analysisReady: boolean;
  autodiagnosisRunning: boolean;
  canStartAutodiagnosis: boolean;
  connectionStatus: ConnectionStatus;
  executedActionCount: number;
  onGenerateDraft: () => void;
  onLoadSystem: () => void;
  onOpenActivity: () => void;
  onOpenTerminal: () => void;
  onRunValidation: () => void;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
  onStartAutodiagnosis: () => void;
  onStartAnalysis: () => void;
  pendingApprovals: number;
  runState: RunState;
  systemLoaded: boolean;
  validation: ValidationResult;
}) {
  const connected = connectionStatus === "connected";
  const validationPassed = validation.status === "passed";
  const hasRun = runState !== "idle" && runState !== "awaiting_connection_approval";
  const commandReviewComplete =
    pendingApprovals === 0 &&
    (executedActionCount > 0 ||
      runState === "executing" ||
      runState === "validating" ||
      runState === "ready_to_submit" ||
      runState === "submitted");
  const activityComplete = runState === "submitted";
  const steps = [
    {
      complete: systemLoaded,
      detail: systemLoaded
        ? "Phoenix customer-system info is loaded. SSH is still gated separately."
        : "Fetch the redacted SSH target from Phoenix. No machine access yet.",
      label: "Load ERP system info",
    },
    {
      complete: connected,
      detail: connected
        ? "Backend SSH access is approved for this run."
        : systemLoaded
          ? "Approve the backend SSH connection before terminal or diagnostics."
          : "Locked until customer-system info is loaded.",
      label: "Approve SSH access",
    },
    {
      complete: analysisReady,
      detail: analysisReady
        ? "Diagnostic context is available."
        : connected
          ? "Run safe read-only diagnostics first."
          : "Locked until SSH access is approved.",
      label: "Diagnose safely",
    },
    {
      complete: commandReviewComplete,
      detail: pendingApprovals
        ? `${pendingApprovals} command ${pendingApprovals === 1 ? "needs" : "need"} review.`
        : commandReviewComplete
          ? "Commands have been reviewed or executed."
          : "Review each proposed command before it runs.",
      label: "Review commands",
    },
    {
      complete: validationPassed,
      detail: validationPassed
        ? validation.evidence
        : hasRun
          ? "Confirm concrete evidence that the customer benefit is restored."
          : "Locked until approved work produces evidence.",
      label: "Confirm validation",
    },
    {
      complete: activityComplete,
      detail: activityComplete
        ? "Activity submitted to Phoenix."
        : validationPassed
          ? "Generate from audit, review fields, then submit."
          : "Locked until validation is confirmed.",
      label: "Submit activity",
    },
  ];

  const nextAction = (() => {
    if (!systemLoaded) {
      return { label: "Load ERP system info", onClick: onLoadSystem };
    }
    if (!connected) {
      return { label: "Approve SSH access", onClick: () => onRequestConnectionApproval("terminal") };
    }
    if (pendingApprovals) {
      return { label: "Review command", onClick: onOpenTerminal };
    }
    if (!analysisReady) {
      return {
        label: autodiagnosisRunning ? "Automated diagnosis requested" : "Start automated diagnosis",
        onClick: canStartAutodiagnosis ? onStartAutodiagnosis : onStartAnalysis,
        disabled: autodiagnosisRunning,
      };
    }
    if (!validationPassed) {
      return { label: "Confirm validation", onClick: onRunValidation };
    }
    if (!activityComplete) {
      return { label: "Review activity", onClick: onOpenActivity };
    }
    return { label: "Activity submitted", onClick: onOpenActivity, disabled: true };
  })();

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle>Incident path</CardTitle>
            <CardDescription>
              ERP context loads first. SSH approval is a separate gate before diagnostics or terminal access.
            </CardDescription>
          </div>
          <Button disabled={nextAction.disabled} onClick={nextAction.onClick} type="button">
            <PlayIcon data-icon="inline-start" />
            {nextAction.label}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ol className="grid gap-2 md:grid-cols-2 xl:grid-cols-6">
          {steps.map((step, index) => {
            const active = !step.complete && steps.slice(0, index).every((candidate) => candidate.complete);
            return (
              <li
                className={cn(
                  "flex min-h-24 flex-col gap-2 rounded-lg border p-3",
                  step.complete
                    ? "border-primary/40 bg-primary/10"
                    : active
                      ? "border-ring bg-muted/60"
                      : "border-border bg-background text-muted-foreground",
                )}
                key={step.label}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{step.label}</span>
                  <StatusLabel label={step.complete ? "done" : active ? "next" : "locked"} />
                </div>
                <p className="text-xs leading-5 text-muted-foreground">{step.detail}</p>
              </li>
            );
          })}
        </ol>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!connected} onClick={onOpenTerminal} type="button" variant="outline">
            <TerminalIcon data-icon="inline-start" />
            Open terminal
          </Button>
          <Button disabled={!validationPassed} onClick={onGenerateDraft} type="button" variant="outline">
            <ClipboardCheckIcon data-icon="inline-start" />
            Draft activity
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SystemTab({
  connectionStatus,
  onLoadSystem,
  onOpenTerminal,
  system,
  systemLoaded,
  systemLoading,
}: {
  connectionStatus: ConnectionStatus;
  onLoadSystem: () => void;
  onOpenTerminal: () => void;
  system: CustomerSystem | null;
  systemLoaded: boolean;
  systemLoading: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Customer system</CardTitle>
          <CardDescription>
            <StatusLabel label={formatConnection(connectionStatus)} />
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {systemLoading ? (
            <SystemInfoSkeleton />
          ) : systemLoaded && system ? (
            <DefinitionTable
              rows={[
                ["Host", system.hostLabel],
                ["Operating system", system.os],
                ["Target", system.target],
                ["Username", system.username],
                ["Notes", system.notes],
              ]}
            />
          ) : (
            <EmptyState title="System not loaded" detail="Load redacted customer system context before approval." />
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={systemLoading} onClick={onLoadSystem} type="button" variant="outline">
              <ShieldCheckIcon data-icon="inline-start" />
              {systemLoading ? "Loading system info" : systemLoaded ? "Reload system info" : "Load system info"}
            </Button>
            <Button
              disabled={systemLoading}
              onClick={onOpenTerminal}
              type="button"
              variant={systemLoaded ? "default" : "outline"}
            >
              <TerminalIcon data-icon="inline-start" />
              Open terminal
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SystemInfoSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border">
      {Array.from({ length: 5 }).map((_, index) => (
        <div className="grid grid-cols-[180px_minmax(0,1fr)] border-b last:border-b-0" key={index}>
          <div className="bg-muted/40 p-3">
            <Skeleton className="h-4 w-24" />
          </div>
          <div className="p-3">
            <Skeleton className="h-4 w-full max-w-sm" />
          </div>
        </div>
      ))}
    </div>
  );
}

function AnalysisTab({
  actions,
  analyticsStats,
  analysisReady,
  autodiagnosisRunning,
  canStartAutodiagnosis,
  connectionStatus,
  llmMetrics,
  onRequestConnectionApproval,
  onStartAutodiagnosis,
  onStartAnalysis,
  relatedTicket,
  terminalCommands,
}: {
  actions: ProposedAction[];
  analyticsStats: DashboardStat[];
  analysisReady: boolean;
  autodiagnosisRunning: boolean;
  canStartAutodiagnosis: boolean;
  connectionStatus: ConnectionStatus;
  llmMetrics: BackendLlmMetricsRead | null;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
  onStartAutodiagnosis: () => void;
  onStartAnalysis: () => void;
  relatedTicket: RelatedTicket | null;
  terminalCommands: TerminalCommandLog[];
}) {
  const requiresConnection = connectionStatus !== "connected";
  const evidenceRows = analysisEvidenceRows(actions, terminalCommands, relatedTicket);

  return (
    <div className="flex flex-col gap-4">
      <StatsGrid stats={analyticsStats} />
      <Card>
        <CardHeader>
          <CardTitle>Agent analysis</CardTitle>
          <CardDescription>
            Context: {connectionStatus === "connected" ? "ticket and system" : "ticket only"}.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {requiresConnection ? (
              <Button className="w-fit" onClick={() => onRequestConnectionApproval("analysis")} type="button">
                <ShieldCheckIcon data-icon="inline-start" />
                Approve connection to start analysis
              </Button>
            ) : (
              <>
                <Button
                  className="w-fit"
                  disabled={!canStartAutodiagnosis || autodiagnosisRunning}
                  onClick={onStartAutodiagnosis}
                  type="button"
                  variant="default"
                >
                  <PlayIcon data-icon="inline-start" />
                  {autodiagnosisRunning ? "Automated diagnosis requested" : "Start automated diagnosis"}
                </Button>
                <Button className="w-fit" onClick={onStartAnalysis} type="button" variant="outline">
                  <PlayIcon data-icon="inline-start" />
                  {analysisReady ? "Refresh analysis state" : "Start analysis"}
                </Button>
              </>
            )}
          </div>
          {analysisReady && evidenceRows.length ? (
            <Table className="table-fixed">
              <colgroup>
                <col className="w-40" />
                <col />
                <col className="w-28" />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Evidence</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {evidenceRows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="whitespace-normal break-words font-medium">
                      <TruncatedText maxLength={80} text={row.source} />
                    </TableCell>
                    <TableCell className="whitespace-normal break-words text-muted-foreground">
                      <TruncatedText maxLength={220} text={row.evidence} />
                    </TableCell>
                    <TableCell>
                      <StatusLabel label={row.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState
              title={analysisReady ? "No backend analysis evidence" : "No analysis yet"}
              detail={
                analysisReady
                  ? "Backend actions, terminal commands, or related-ticket context will appear here when available."
                  : "Start analysis or autonomous diagnosis to collect backend evidence."
              }
            />
          )}
        </CardContent>
      </Card>
      <LlmTelemetryPanel metrics={llmMetrics} />
    </div>
  );
}

function LlmTelemetryPanel({ metrics }: { metrics: BackendLlmMetricsRead | null }) {
  if (!metrics) {
    return null;
  }

  const requests = metrics.requests.slice(0, 6);
  const operations = Object.entries(metrics.by_operation);

  return (
    <Card>
      <CardHeader>
        <CardTitle>LLM telemetry</CardTitle>
        <CardDescription>
          {metrics.request_count} requests, {metrics.error_count} errors, {metrics.tokens.total_tokens} tokens.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-0">
        {operations.length ? (
          <Table className="table-fixed">
            <colgroup>
              <col className="w-48" />
              <col className="w-28" />
              <col className="w-28" />
              <col className="w-28" />
              <col className="w-28" />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead>Operation</TableHead>
                <TableHead>Input</TableHead>
                <TableHead>Output</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {operations.map(([operation, summary]) => (
                <TableRow key={operation}>
                  <TableCell className="whitespace-normal break-words font-medium">
                    <TruncatedText maxLength={52} text={operation} />
                  </TableCell>
                  <TableCell>{formatTokenCount(summary.prompt_tokens)}</TableCell>
                  <TableCell>{formatTokenCount(summary.completion_tokens)}</TableCell>
                  <TableCell>{formatTokenCount(summary.total_tokens)}</TableCell>
                  <TableCell>{formatUsd(summary.estimated_cost_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {requests.length ? (
          <Table className="table-fixed">
            <colgroup>
              <col className="w-44" />
              <col className="w-44" />
              <col className="w-28" />
              <col className="w-28" />
              <col />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead>Operation</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead>Tokens</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((request) => (
                <TableRow key={request.id}>
                  <TableCell className="whitespace-normal break-words font-medium">
                    <TruncatedText maxLength={52} text={request.operation} />
                  </TableCell>
                  <TableCell className="whitespace-normal break-words text-muted-foreground">
                    <TruncatedText maxLength={52} text={`${request.provider} / ${request.model}`} />
                  </TableCell>
                  <TableCell>{formatMetricMs(request.latency_ms)}</TableCell>
                  <TableCell>{formatTokenCount(request.total_tokens)}</TableCell>
                  <TableCell>
                    <StatusLabel label={request.error ? "error" : "completed"} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="px-4 py-3">
            <p className="font-medium text-foreground">No LLM request records</p>
            <p className="text-sm text-muted-foreground">Backend returned zero LLM requests for this run.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatMetricMs(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "n/a";
  }

  return `${Math.round(value)} ms`;
}

function formatTokenCount(value: number) {
  return Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

function formatUsd(value: number | null | undefined) {
  if (typeof value !== "number") {
    return "n/a";
  }

  return Intl.NumberFormat(undefined, {
    currency: "USD",
    maximumFractionDigits: 4,
    style: "currency",
  }).format(value);
}

function analysisEvidenceRows(
  actions: ProposedAction[],
  terminalCommands: TerminalCommandLog[],
  relatedTicket: RelatedTicket | null,
) {
  const rows: Array<{ evidence: string; id: string; source: string; status: string }> = [];

  if (relatedTicket) {
    rows.push({
      evidence: [relatedTicket.rationale, relatedTicket.description].filter(Boolean).join(" ") || relatedTicket.title,
      id: `related-${relatedTicket.ticketId}`,
      source: `Related ticket #${relatedTicket.ticketId}`,
      status: relatedTicket.confidence ?? "related",
    });
  }

  for (const action of actions.slice(0, 8)) {
    rows.push({
      evidence: action.result ? `${action.purpose} Result: ${action.result}` : `${action.purpose} Command: ${action.command}`,
      id: `action-${action.id}`,
      source: action.title,
      status: action.status,
    });
  }

  for (const command of terminalCommands.slice(0, 8)) {
    const exitCode = command.exitCode === null ? "pending" : `exit ${command.exitCode}`;
    rows.push({
      evidence: `${command.command} (${exitCode})`,
      id: `terminal-${command.id}`,
      source: `${command.source} terminal command`,
      status: command.status,
    });
  }

  return rows;
}

function ActionsTab({
  autodiagnosisRunning,
  autoStartAgentRequestId,
  canStartAutodiagnosis,
  connectionStatus,
  onLoadSystem,
  onAgentPhaseChange,
  onRequestConnectionApproval,
  onStartAutodiagnosis,
  onTerminalConnectionError,
  runId,
  systemLoaded,
  systemLoading,
}: {
  autodiagnosisRunning: boolean;
  autoStartAgentRequestId: number;
  canStartAutodiagnosis: boolean;
  connectionStatus: ConnectionStatus;
  onLoadSystem: () => Promise<void> | void;
  onAgentPhaseChange: (phase: AgentPhase) => void;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
  onStartAutodiagnosis: () => void;
  onTerminalConnectionError: (message: string) => void;
  runId: string | null;
  systemLoaded: boolean;
  systemLoading: boolean;
}) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-3">
      {!runId ? (
        <Card className="border-dashed" size="sm">
          <CardContent className="flex flex-col gap-3 pb-4">
            <div>
              <p className="font-medium text-foreground">Connection approval required</p>
              <p className="text-sm text-muted-foreground">
                Load system info and approve the backend SSH connection before opening the agent terminal.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={systemLoading} onClick={onLoadSystem} type="button" variant={systemLoaded ? "outline" : "default"}>
                {systemLoading ? "Loading system info" : "Load system info"}
              </Button>
              <Button disabled={systemLoading} onClick={() => onRequestConnectionApproval("terminal")} type="button">
                {connectionStatus === "connected" ? "Prepare terminal" : "Approve connection"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <Suspense fallback={<EmptyState title="Loading terminal" detail="Preparing the remote terminal surface." />}>
        <TicketTerminal
          autodiagnosisRunning={autodiagnosisRunning}
          autoStartAgentRequestId={autoStartAgentRequestId}
          canStartAutodiagnosis={canStartAutodiagnosis}
          onAgentPhaseChange={onAgentPhaseChange}
          onStartAutodiagnosis={onStartAutodiagnosis}
          onTerminalConnectionError={onTerminalConnectionError}
          runId={runId}
        />
      </Suspense>
    </div>
  );
}

function LogsTab({
  events,
  logFilter,
  onCopy,
  onFilterChange,
  terminalCommands,
  terminalTranscript,
}: {
  events: RunEvent[];
  logFilter: "all" | EventType;
  onCopy: () => void;
  onFilterChange: (filter: "all" | EventType) => void;
  terminalCommands: TerminalCommandLog[];
  terminalTranscript: TerminalTranscriptLine[];
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-lg font-medium tracking-normal">Live run and audit log</h2>
        <div className="flex items-center gap-2">
          <LogFilter value={logFilter} onChange={onFilterChange} />
          <Button onClick={onCopy} size="sm" type="button" variant="outline">
            Copy safe excerpt
          </Button>
        </div>
      </div>
      <Card>
        <CardContent className="px-0">
          <EventTable events={events} />
        </CardContent>
      </Card>
      {terminalCommands.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Terminal command history</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <TerminalCommandTable commands={terminalCommands} />
          </CardContent>
        </Card>
      ) : null}
      {terminalTranscript.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Terminal transcript</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-3 font-mono text-xs leading-5 text-foreground">
              {terminalTranscript.map((line) => line.data).join("")}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function TerminalCommandTable({ commands }: { commands: TerminalCommandLog[] }) {
  return (
    <Table className="table-fixed">
      <colgroup>
        <col className="w-36" />
        <col className="w-24" />
        <col className="w-32" />
        <col />
        <col className="w-20" />
      </colgroup>
      <TableHeader>
        <TableRow>
          <TableHead>Timing</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Command</TableHead>
          <TableHead>Exit</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {commands.map((command) => (
          <TableRow className={command.status === "blocked" ? "bg-destructive/10" : undefined} key={command.id}>
            <TableCell className="align-top">
              <CommandTiming command={command} />
            </TableCell>
            <TableCell className="align-top">
              <StatusLabel label={command.source} />
            </TableCell>
            <TableCell className="align-top">
              <StatusLabel label={formatTerminalCommandStatus(command.status)} />
            </TableCell>
            <TableCell className="whitespace-normal break-words align-top">
              <div className="flex flex-col gap-1.5">
                <CommandSummary command={command} />
                <WritePreviewSummary preview={command.writePreview} />
                {command.status === "blocked" && command.riskReason ? (
                  <p className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive">
                    <TruncatedText maxLength={180} text={`Blocked before execution: ${command.riskReason}`} />
                  </p>
                ) : command.riskReason ? (
                  <p className="text-xs text-muted-foreground">
                    <TruncatedText maxLength={180} text={`Safety note: ${command.riskReason}`} />
                  </p>
                ) : null}
              </div>
            </TableCell>
            <TableCell className="align-top">{command.status === "blocked" ? "Not run" : command.exitCode === null ? "Pending" : command.exitCode}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function CommandTiming({ command }: { command: TerminalCommandLog }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 text-xs text-muted-foreground">
      <span>
        {formatCommandTimestamp(command.startedAt ?? command.createdAt)}
        {" -> "}
        {command.endedAt ? formatCommandTimestamp(command.endedAt) : "running"}
      </span>
      <span>{formatCommandRuntime(command.startedAt, command.endedAt)}</span>
    </div>
  );
}

function CommandSummary({ command }: { command: TerminalCommandLog }) {
  const finalCommand = command.finalCommand ?? command.command;
  const originalCommand = command.originalCommand || command.command;

  if (finalCommand === originalCommand) {
    return <CommandLine label="Command" value={finalCommand} strong />;
  }

  return (
    <>
      <CommandLine label="Final command" value={finalCommand} strong />
      <CommandLine label="Original command" value={originalCommand} />
    </>
  );
}

function CommandLine({ label, strong = false, value }: { label: string; strong?: boolean; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <code className={strong ? "font-semibold" : undefined}>
        <TruncatedText maxLength={180} text={value} />
      </code>
    </div>
  );
}

function WritePreviewSummary({ preview }: { preview: TerminalCommandLog["writePreview"] }) {
  if (!preview) {
    return null;
  }

  const status = readPreviewString(preview, "status") ?? "available";
  const targetPath = readPreviewString(preview, "target_path");
  const commandKind = readPreviewString(preview, "command_kind");
  const diff = readPreviewString(preview, "diff");

  return (
    <div className="rounded-md border bg-muted/30 p-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">Write preview</span>
        <StatusLabel label={status.split("_").join(" ")} />
        {commandKind ? <span className="text-muted-foreground">{commandKind.split("_").join(" ")}</span> : null}
      </div>
      {targetPath ? <p className="mt-1 text-muted-foreground">Target: {targetPath}</p> : null}
      {diff ? (
        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-background p-2 font-mono text-[11px] leading-4 text-foreground">
          {diff}
        </pre>
      ) : null}
    </div>
  );
}

function formatTerminalCommandStatus(status: TerminalCommandLog["status"]) {
  switch (status) {
    case "submitted":
    case "edited":
      return "proposed";
    case "confirmation_required":
      return "confirmation required";
    case "accepted":
    case "running":
      return "accepted/running";
    case "completed":
    case "failed":
      return status;
    case "blocked":
      return "blocked";
    case "rejected":
    case "cancelled":
      return "rejected/cancelled";
  }
}

function formatCommandTimestamp(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatCommandRuntime(startedAt: string | null, endedAt: string | null) {
  if (!startedAt) {
    return "Not started";
  }

  if (!endedAt) {
    return "Running or awaiting completion";
  }

  const durationMs = Math.max(0, new Date(endedAt).getTime() - new Date(startedAt).getTime());
  if (durationMs < 1000) {
    return "<1s";
  }

  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

function readPreviewString(preview: Record<string, unknown>, key: string) {
  const value = preview[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function getConnectionApprovalDescription(intent: ConnectionIntent | null) {
  if (intent === "analysis") {
    return "This approves backend SSH access for the selected customer system, then starts the analysis flow.";
  }

  if (intent === "autodiagnosis") {
    return "This approves backend SSH access for the selected customer system, then starts automated diagnosis in the terminal.";
  }

  if (intent === "terminal") {
    return "This approves backend SSH access for the selected customer system before opening the terminal.";
  }

  return "This approves backend SSH access for the selected customer system.";
}

function ActivityTab({
  draft,
  draftGenerating,
  notice,
  onDraftChange,
  onGenerateDraft,
  onRunValidation,
  onReview,
  onSave,
  onSubmit,
  runState,
  submitStatus,
  validation,
}: {
  draft: ActivityDraft;
  draftGenerating: boolean;
  notice: string;
  onDraftChange: (draft: ActivityDraft) => void;
  onGenerateDraft: () => void;
  onRunValidation: () => void;
  onReview: () => void;
  onSave: () => void;
  onSubmit: () => void;
  runState: RunState;
  submitStatus: "idle" | "submitted";
  validation: ValidationResult;
}) {
  const complete = isDraftComplete(draft);
  const validationPassed = validation.status === "passed";
  const canConfirmValidation =
    runState === "validating" || runState === "ready_to_submit" || runState === "submitted";
  const generationStatus = validationPassed
    ? draftGenerating
      ? "Generating the activity draft from audit evidence."
      : "Ready: validation is confirmed."
    : canConfirmValidation
      ? "Required first: approve the collected validation evidence."
      : "Required first: run a validation command and collect successful evidence.";

  return (
    <Card className="relative overflow-hidden">
      {draftGenerating ? <div className="absolute inset-x-0 top-0 h-0.5 animate-pulse bg-primary motion-reduce:animate-none" /> : null}
      <CardHeader>
        <CardTitle>ERP activity draft</CardTitle>
        <CardDescription>
          <StatusLabel label={complete ? "complete" : "incomplete"} />{" "}
          <StatusLabel label={`validation: ${validation.status}`} />
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">Generate from audit requirement</p>
            <p className="text-sm text-muted-foreground">{generationStatus}</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button disabled={draftGenerating || !canConfirmValidation || validationPassed} onClick={onRunValidation} type="button" variant="outline">
              <CheckIcon data-icon="inline-start" />
              Confirm validation
            </Button>
            <Button disabled={draftGenerating || !validationPassed} onClick={onGenerateDraft} type="button" variant="outline">
              {draftGenerating ? (
                <Loader2Icon className="size-4 animate-spin motion-reduce:animate-none" data-icon="inline-start" />
              ) : (
                <ClipboardCheckIcon data-icon="inline-start" />
              )}
              {draftGenerating ? "Generating draft" : "Generate from audit"}
            </Button>
          </div>
        </div>
        {draftGenerating ? (
          <div className="flex items-center gap-2 rounded-lg border border-primary/30 bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 shrink-0 animate-spin text-foreground motion-reduce:animate-none" />
            <span>Generating the Phoenix activity draft from audit events and command evidence.</span>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button disabled={draftGenerating} onClick={onSave} type="button" variant="outline">
            Save draft
          </Button>
          <Button disabled={draftGenerating || !complete || submitStatus === "submitted"} onClick={onReview} type="button" variant="outline">
            Mark reviewed
          </Button>
          <Button disabled={draftGenerating || !complete || submitStatus === "submitted"} onClick={onSubmit} type="button">
            Submit activity
          </Button>
        </div>
        {notice ? <p className="rounded-lg border bg-muted px-3 py-2 text-sm text-muted-foreground">{notice}</p> : null}
        <div className="grid gap-3 lg:grid-cols-2">
          {(
            [
              ["summary", "Summary", 2],
              ["root_cause", "Root cause", 3],
              ["actions_taken", "Actions taken", 5],
              ["commands_summary", "Commands summary", 5],
              ["validation_result", "Validation result", 3],
            ] as Array<[keyof ActivityDraft, string, number]>
          ).map(([field, label, rows]) => (
            <label className={rows > 3 ? "lg:col-span-2" : ""} key={field}>
              <span className="text-sm font-medium text-foreground">{label}</span>
              <Textarea
                disabled={draftGenerating}
                onChange={(event) => onDraftChange({ ...draft, [field]: event.target.value })}
                rows={rows}
                value={draft[field]}
              />
            </label>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ConfirmDialog({
  confirmLabel,
  description,
  onConfirm,
  onOpenChange,
  open,
  title,
  variant = "default",
}: {
  confirmLabel: string;
  description: string;
  onConfirm: () => Promise<void> | void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
  variant?: "default" | "destructive";
}) {
  const confirm = async () => {
    await onConfirm();
    onOpenChange(false);
  };

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} type="button" variant="outline">
            Cancel
          </Button>
          <Button onClick={confirm} type="button" variant={variant}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
