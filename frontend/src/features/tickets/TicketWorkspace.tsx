import { lazy, Suspense, useEffect, useState } from "react";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  CheckIcon,
  ClipboardCheckIcon,
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
} from "@/components/ui/primitives";
import {
  PageHeading,
  StatsGrid,
  WorkflowCards,
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
import { hypotheses, tabs } from "@/data/mockData";
import { formatConnection, formatDate, formatRunState, isDraftComplete } from "@/lib/serviceDesk";
import type {
  ActivityDraft,
  ConnectionStatus,
  CustomerSystem,
  EventType,
  ProposedAction,
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

export function TicketWorkspace(props: {
  activeTab: TabId;
  actions: ProposedAction[];
  analysisReady: boolean;
  backendRunId: string | null;
  connectionStatus: ConnectionStatus;
  draft: ActivityDraft;
  events: RunEvent[];
  executedActions: ProposedAction[];
  logFilter: "all" | EventType;
  notice: string;
  onAbort: () => void;
  onApproveAction: (actionId: string) => void;
  onApproveConnection: () => Promise<void> | void;
  onBackToTickets: () => void;
  onCopyAudit: () => void;
  onDraftChange: (draft: ActivityDraft) => void;
  onGenerateDraft: () => void;
  onLoadSystem: () => Promise<void> | void;
  onRejectAction: (actionId: string) => void;
  onRetryAction: (actionId: string) => void;
  onRunValidation: () => void;
  onStartAutodiagnosis: () => void;
  onStartAnalysis: () => void;
  onSubmitActivity: () => void;
  onTabChange: (tabId: TabId) => void;
  onUpdateCommand: (actionId: string, command: string) => void;
  pendingActions: ProposedAction[];
  autodiagnosisRunning: boolean;
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
  const overviewStats: DashboardStat[] = [
    {
      detail: "Commands or connection steps awaiting technician review.",
      label: "Pending approvals",
      progress: props.pendingActions.length ? 100 : 0,
      tone: props.pendingActions.length ? "warning" : "success",
      value: props.pendingActions.length,
    },
    {
      detail: "Audit and run events captured for the activity draft.",
      label: "Run events",
      progress: Math.min(props.events.length * 12, 100),
      tone: "default",
      value: props.events.length,
    },
    {
      detail: props.validation.evidence,
      label: "Validation",
      progress: props.validation.status === "passed" ? 100 : 0,
      tone: props.validation.status === "passed" ? "success" : "warning",
      value: props.validation.status,
    },
    {
      detail: "Backend-owned SSH approval state.",
      label: "Connection",
      progress: props.connectionStatus === "connected" ? 100 : 0,
      tone: props.connectionStatus === "connected" ? "success" : "warning",
      value: formatConnection(props.connectionStatus),
    },
  ];

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
        <TabsList className="max-w-full gap-2 overflow-x-auto" variant="line">
          {tabs.map((tab) => (
            <TabsTrigger key={tab.id} value={tab.id}>
              {tab.label}
              {tab.id === "actions" && props.pendingActions.length ? (
                <span className="rounded-full bg-destructive/20 px-1.5 py-0.5 text-[10px] text-destructive">
                  {props.pendingActions.length}
                </span>
              ) : null}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab
            analyticsStats={overviewStats}
            connectionStatus={props.connectionStatus}
            onGenerateDraft={props.onGenerateDraft}
            onLoadSystem={props.onLoadSystem}
            onOpenTerminal={() => props.onTabChange("actions")}
            onRunValidation={props.onRunValidation}
            onRequestConnectionApproval={requestConnectionApproval}
            onStartAnalysis={props.onStartAnalysis}
            pendingApprovals={props.pendingActions.length}
            runState={props.runState}
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
            analyticsStats={[
              ...overviewStats,
              {
                detail: "Approved commands with stored results.",
                label: "Actions executed",
                progress: Math.min(props.executedActions.length * 25, 100),
                tone: "success",
                value: props.executedActions.length,
              },
            ]}
            analysisReady={props.analysisReady}
            connectionStatus={props.connectionStatus}
            onRequestConnectionApproval={requestConnectionApproval}
            onStartAnalysis={props.onStartAnalysis}
          />
        </TabsContent>
        <TabsContent className="min-h-[560px]" value="actions">
          <ActionsTab
            connectionStatus={props.connectionStatus}
            onLoadSystem={props.onLoadSystem}
            onRequestConnectionApproval={requestConnectionApproval}
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
            notice={props.notice}
            onDraftChange={props.onDraftChange}
            onGenerateDraft={props.onGenerateDraft}
            onSubmit={props.onSubmitActivity}
            submitStatus={props.submitStatus}
            validation={props.validation}
          />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        confirmLabel="Abort run"
        description="This stops the current run and disconnects any active terminal session."
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

function OverviewTab({
  analyticsStats,
  connectionStatus,
  onGenerateDraft,
  onLoadSystem,
  onOpenTerminal,
  onRunValidation,
  onRequestConnectionApproval,
  onStartAnalysis,
  pendingApprovals,
  runState,
  systemLoaded,
  ticket,
  validation,
}: {
  analyticsStats: DashboardStat[];
  connectionStatus: ConnectionStatus;
  onGenerateDraft: () => void;
  onLoadSystem: () => void;
  onOpenTerminal: () => void;
  onRunValidation: () => void;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
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
      <StatsGrid stats={analyticsStats} />
      <WorkflowCards
        connected={connectionStatus === "connected"}
        pendingApprovals={pendingApprovals}
        validated={validation.status === "passed"}
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>Customer report</CardTitle>
            <CardDescription>{formatRunState(runState)}</CardDescription>
          </CardHeader>
          <CardContent>
            <MarkdownContent omitFirstHeading="Customer report">{ticket.report}</MarkdownContent>
          </CardContent>
        </Card>

        <Card>
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

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Next actions</CardTitle>
            <CardDescription>
              <StatusLabel label={`connection: ${formatConnection(connectionStatus)}`} />{" "}
              <StatusLabel label={`validation: ${validation.status}`} />
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button onClick={onLoadSystem} type="button" variant={systemLoaded ? "outline" : "default"}>
              <ShieldCheckIcon data-icon="inline-start" />
              {systemLoaded ? "Reload system info" : "Load system info"}
            </Button>
            {requiresConnection ? (
              <Button onClick={() => onRequestConnectionApproval("terminal")} type="button" variant="default">
                <ShieldCheckIcon data-icon="inline-start" />
                Approve connection
              </Button>
            ) : null}
            <Button
              onClick={handleOpenTerminal}
              type="button"
              variant={systemLoaded && connectionStatus !== "connected" ? "default" : "outline"}
            >
              <TerminalIcon data-icon="inline-start" />
              Open terminal
            </Button>
            <Button onClick={handleStartAnalysis} type="button" variant="outline">
              <PlayIcon data-icon="inline-start" />
              Start analysis
            </Button>
            <Button onClick={onRunValidation} type="button" variant="outline">
              <CheckIcon data-icon="inline-start" />
              Validate
            </Button>
            <Button onClick={onGenerateDraft} type="button" variant="outline">
              <ClipboardCheckIcon data-icon="inline-start" />
              Draft activity
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
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
  analyticsStats,
  analysisReady,
  connectionStatus,
  onRequestConnectionApproval,
  onStartAnalysis,
}: {
  analyticsStats: DashboardStat[];
  analysisReady: boolean;
  connectionStatus: ConnectionStatus;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
  onStartAnalysis: () => void;
}) {
  const requiresConnection = connectionStatus !== "connected";

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
              <Button className="w-fit" onClick={onStartAnalysis} type="button">
                <PlayIcon data-icon="inline-start" />
                {analysisReady ? "Re-run analysis" : "Start analysis"}
              </Button>
            )}
          </div>
          {analysisReady ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Hypothesis</TableHead>
                  <TableHead>Evidence</TableHead>
                  <TableHead>Confidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {hypotheses.map((hypothesis) => (
                  <TableRow key={hypothesis.id}>
                    <TableCell className="font-medium">{hypothesis.title}</TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">{hypothesis.evidence}</TableCell>
                    <TableCell>
                      <StatusLabel label={hypothesis.confidence} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState title="No analysis yet" detail="Start analysis to queue hypotheses and actions." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ActionsTab({
  connectionStatus,
  onLoadSystem,
  onRequestConnectionApproval,
  runId,
  systemLoaded,
  systemLoading,
}: {
  connectionStatus: ConnectionStatus;
  onLoadSystem: () => Promise<void> | void;
  onRequestConnectionApproval: (intent: ConnectionIntent) => void;
  runId: string | null;
  systemLoaded: boolean;
  systemLoading: boolean;
}) {
  return (
    <div className="flex h-full min-h-[560px] min-w-0 flex-col gap-3">
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
        <TicketTerminal runId={runId} />
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
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Command</TableHead>
          <TableHead>Exit</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {commands.map((command) => (
          <TableRow className={command.status === "blocked" ? "bg-destructive/10" : undefined} key={command.id}>
            <TableCell>{new Date(command.updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</TableCell>
            <TableCell>
              <StatusLabel label={command.source} />
            </TableCell>
            <TableCell>
              <StatusLabel label={formatTerminalCommandStatus(command.status)} />
            </TableCell>
            <TableCell className="max-w-[520px] whitespace-normal">
              <div className="flex flex-col gap-1.5">
                <CommandLine label="Original command" value={command.originalCommand} />
                <CommandLine label="Final command" value={command.finalCommand ?? command.command} strong />
                {command.status === "blocked" && command.riskReason ? (
                  <p className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive">
                    Blocked before execution: {command.riskReason}
                  </p>
                ) : command.riskReason ? (
                  <p className="text-xs text-muted-foreground">Safety note: {command.riskReason}</p>
                ) : null}
              </div>
            </TableCell>
            <TableCell>{command.status === "blocked" ? "Not run" : command.exitCode === null ? "Pending" : command.exitCode}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function CommandLine({ label, strong = false, value }: { label: string; strong?: boolean; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <code className={strong ? "font-semibold" : undefined}>{value}</code>
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

function getConnectionApprovalDescription(intent: ConnectionIntent | null) {
  if (intent === "analysis") {
    return "This approves backend SSH access for the selected customer system, then starts the analysis flow.";
  }

  if (intent === "autodiagnosis") {
    return "This approves backend SSH access for the selected customer system, then starts safe autodiagnosis.";
  }

  if (intent === "terminal") {
    return "This approves backend SSH access for the selected customer system before opening the terminal.";
  }

  return "This approves backend SSH access for the selected customer system.";
}

function ActivityTab({
  draft,
  notice,
  onDraftChange,
  onGenerateDraft,
  onSubmit,
  submitStatus,
  validation,
}: {
  draft: ActivityDraft;
  notice: string;
  onDraftChange: (draft: ActivityDraft) => void;
  onGenerateDraft: () => void;
  onSubmit: () => void;
  submitStatus: "idle" | "submitted";
  validation: ValidationResult;
}) {
  const complete = isDraftComplete(draft);

  return (
    <Card>
      <CardHeader>
        <CardTitle>ERP activity draft</CardTitle>
        <CardDescription>
          <StatusLabel label={complete ? "complete" : "incomplete"} />{" "}
          <StatusLabel label={`validation: ${validation.status}`} />
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <Button onClick={onGenerateDraft} type="button" variant="outline">
            Generate from audit
          </Button>
          <Button disabled={!complete || submitStatus === "submitted"} onClick={onSubmit} type="button">
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
