import { lazy, Suspense, useState } from "react";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  CheckIcon,
  ClipboardCheckIcon,
  PlayIcon,
  ShieldCheckIcon,
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
  onApproveConnection: () => void;
  onBackToTickets: () => void;
  onCopyAudit: () => void;
  onDraftChange: (draft: ActivityDraft) => void;
  onGenerateDraft: () => void;
  onLoadSystem: () => void;
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
  terminalCommands: TerminalCommandLog[];
  terminalTranscript: TerminalTranscriptLine[];
  ticket: Ticket;
  validation: ValidationResult;
}) {
  const [abortDialogOpen, setAbortDialogOpen] = useState(false);
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
            onRunValidation={props.onRunValidation}
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
            onApproveConnection={props.onApproveConnection}
            onLoadSystem={props.onLoadSystem}
            system={props.selectedSystem}
            systemLoaded={props.systemLoaded}
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
            onStartAnalysis={props.onStartAnalysis}
          />
        </TabsContent>
        <TabsContent className="min-h-[560px]" value="actions">
          <ActionsTab
            connectionStatus={props.connectionStatus}
            onApproveConnection={props.onApproveConnection}
            onLoadSystem={props.onLoadSystem}
            runId={props.backendRunId}
            systemLoaded={props.systemLoaded}
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
    </section>
  );
}

function OverviewTab({
  analyticsStats,
  connectionStatus,
  onGenerateDraft,
  onLoadSystem,
  onRunValidation,
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
  onRunValidation: () => void;
  onStartAnalysis: () => void;
  pendingApprovals: number;
  runState: RunState;
  systemLoaded: boolean;
  ticket: Ticket;
  validation: ValidationResult;
}) {
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
            <Button onClick={onStartAnalysis} type="button" variant="outline">
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
  onApproveConnection,
  onLoadSystem,
  system,
  systemLoaded,
}: {
  connectionStatus: ConnectionStatus;
  onApproveConnection: () => void;
  onLoadSystem: () => void;
  system: CustomerSystem | null;
  systemLoaded: boolean;
}) {
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);

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
          {systemLoaded && system ? (
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
            <Button onClick={onLoadSystem} type="button" variant="outline">
              Load system info
            </Button>
            <Button
              disabled={!systemLoaded || connectionStatus === "connected"}
              onClick={() => setConnectionDialogOpen(true)}
              type="button"
            >
              <ShieldCheckIcon data-icon="inline-start" />
              Approve connection
            </Button>
          </div>
        </CardContent>
      </Card>
      <ConfirmDialog
        confirmLabel="Approve"
        description="This approves backend SSH access for the selected customer system."
        onConfirm={onApproveConnection}
        onOpenChange={setConnectionDialogOpen}
        open={connectionDialogOpen}
        title="Approve connection?"
      />
    </div>
  );
}

function AnalysisTab({
  analyticsStats,
  analysisReady,
  connectionStatus,
  onStartAnalysis,
}: {
  analyticsStats: DashboardStat[];
  analysisReady: boolean;
  connectionStatus: ConnectionStatus;
  onStartAnalysis: () => void;
}) {
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
          <Button className="w-fit" onClick={onStartAnalysis} type="button">
            <PlayIcon data-icon="inline-start" />
            {analysisReady ? "Re-run analysis" : "Start analysis"}
          </Button>
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
  onApproveConnection,
  onLoadSystem,
  runId,
  systemLoaded,
}: {
  connectionStatus: ConnectionStatus;
  onApproveConnection: () => void;
  onLoadSystem: () => void;
  runId: string | null;
  systemLoaded: boolean;
}) {
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);

  return (
    <div className="flex h-full min-h-[560px] min-w-0 flex-col gap-3">
      {!runId ? (
        <Card className="border-dashed" size="sm">
          <CardContent className="flex flex-col gap-3">
            <div>
              <p className="font-medium text-foreground">Connection approval required</p>
              <p className="text-sm text-muted-foreground">
                Load system info and approve the backend SSH connection before opening the agent terminal.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={onLoadSystem} type="button" variant={systemLoaded ? "outline" : "default"}>
                Load system info
              </Button>
              <Button disabled={!systemLoaded} onClick={() => setConnectionDialogOpen(true)} type="button">
                {connectionStatus === "connected" ? "Prepare terminal" : "Approve connection"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <Suspense fallback={<EmptyState title="Loading terminal" detail="Preparing the remote terminal surface." />}>
        <TicketTerminal runId={runId} />
      </Suspense>
      <ConfirmDialog
        confirmLabel="Approve"
        description="This approves backend SSH access for the selected customer system."
        onConfirm={onApproveConnection}
        onOpenChange={setConnectionDialogOpen}
        open={connectionDialogOpen}
        title="Approve connection?"
      />
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
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
  variant?: "default" | "destructive";
}) {
  const confirm = () => {
    onConfirm();
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
