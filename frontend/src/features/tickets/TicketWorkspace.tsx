import { lazy, Suspense, useState } from "react";
import {
  BlocksConfirmDialog,
  BlocksStatsGrid,
  type BlocksStat,
} from "../../components/blocks";
import { MarkdownContent } from "../../components/ui/MarkdownContent";
import {
  DefinitionTable,
  EmptyState,
  EventTable,
  HeadingWithTags,
  LogFilter,
  PageHeader,
  StatusLabel,
} from "../../components/ui/primitives";
import { hypotheses, tabs } from "../../data/mockData";
import { formatConnection, formatDate, formatRunState, isDraftComplete } from "../../lib/serviceDesk";
import type {
  ActivityDraft,
  ConnectionStatus,
  CustomerSystem,
  EventType,
  ProposedAction,
  RunEvent,
  RunState,
  TabId,
  Ticket,
  ValidationResult,
} from "../../types";

const TicketTerminal = lazy(() =>
  import("./TicketTerminal").then((module) => ({ default: module.TicketTerminal })),
);

export function TicketWorkspace(props: {
  activeTab: TabId;
  actions: ProposedAction[];
  analysisReady: boolean;
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
  onStartAnalysis: () => void;
  onSubmitActivity: () => void;
  onTabChange: (tabId: TabId) => void;
  onUpdateCommand: (actionId: string, command: string) => void;
  pendingActions: ProposedAction[];
  runState: RunState;
  selectedSystem: CustomerSystem | null;
  setLogFilter: (filter: "all" | EventType) => void;
  submitStatus: "idle" | "submitted";
  systemLoaded: boolean;
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
  const overviewStats: BlocksStat[] = [
    { label: "Pending approvals", value: props.pendingActions.length, kind: "metric", tone: "neutral" },
    { label: "Run events", value: props.events.length, kind: "metric", tone: "positive" },
    { label: "Validation", value: props.validation.status, kind: "status" },
    { label: "Connection", value: formatConnection(props.connectionStatus), kind: "status" },
  ];
  const analysisStats: BlocksStat[] = [
    ...overviewStats,
    { label: "Actions executed", value: props.executedActions.length, kind: "metric", tone: "positive" },
  ];

  return (
    <section className="ticket-workspace">
      <TicketBreadcrumb onBackToTickets={props.onBackToTickets} ticketId={props.ticket.id} />
      <PageHeader
        title={props.ticket.title}
        badges={
          <>
            <StatusLabel label={props.ticket.priority} />
            <StatusLabel label={props.ticket.status} />
            <StatusLabel label={formatRunState(props.runState)} />
          </>
        }
        aside={
          <button
            className="button button-danger"
            disabled={props.runState === "idle" || props.runState === "submitted" || props.runState === "aborted"}
            onClick={() => setAbortDialogOpen(true)}
            type="button"
          >
            Abort
          </button>
        }
      />

      {pendingMessage ? (
        <div className="approval-strip">
          <strong>{pendingMessage}</strong>
          <span>Review required before backend/system action.</span>
        </div>
      ) : null}

      <nav className="tab-bar" aria-label="Ticket workflow tabs">
        {tabs.map((tab) => (
          <button
            className={props.activeTab === tab.id ? "active" : ""}
            key={tab.id}
            onClick={() => props.onTabChange(tab.id)}
            type="button"
          >
            {tab.label}
            {tab.id === "actions" && props.pendingActions.length ? <span>{props.pendingActions.length}</span> : null}
          </button>
        ))}
      </nav>

      <div className="tab-body">
        {props.activeTab === "overview" ? (
          <OverviewTab
            analyticsStats={overviewStats}
            connectionStatus={props.connectionStatus}
            onLoadSystem={props.onLoadSystem}
            onStartAnalysis={props.onStartAnalysis}
            runState={props.runState}
            systemLoaded={props.systemLoaded}
            ticket={props.ticket}
            validation={props.validation}
          />
        ) : null}
        {props.activeTab === "system" ? (
          <SystemTab
            connectionStatus={props.connectionStatus}
            onApproveConnection={props.onApproveConnection}
            onLoadSystem={props.onLoadSystem}
            system={props.selectedSystem}
            systemLoaded={props.systemLoaded}
          />
        ) : null}
        {props.activeTab === "analysis" ? (
          <AnalysisTab
            analyticsStats={analysisStats}
            analysisReady={props.analysisReady}
            connectionStatus={props.connectionStatus}
            onStartAnalysis={props.onStartAnalysis}
          />
        ) : null}
        {props.activeTab === "actions" ? (
          <ActionsTab ticketId={props.ticket.id} />
        ) : null}
        {props.activeTab === "logs" ? (
          <LogsTab
            events={props.events}
            logFilter={props.logFilter}
            onCopy={props.onCopyAudit}
            onFilterChange={props.setLogFilter}
          />
        ) : null}
        {props.activeTab === "activity" ? (
          <ActivityTab
            draft={props.draft}
            notice={props.notice}
            onDraftChange={props.onDraftChange}
            onGenerateDraft={props.onGenerateDraft}
            onSubmit={props.onSubmitActivity}
            submitStatus={props.submitStatus}
            validation={props.validation}
          />
        ) : null}
      </div>
      <BlocksConfirmDialog
        confirmLabel="Abort"
        description="This stops the current mock run and disconnects any active mock connection."
        onConfirm={props.onAbort}
        onOpenChange={setAbortDialogOpen}
        open={abortDialogOpen}
        title="Abort run?"
        tone="danger"
      />
    </section>
  );
}

function TicketBreadcrumb({
  onBackToTickets,
  ticketId,
}: {
  onBackToTickets: () => void;
  ticketId: number;
}) {
  return (
    <nav className="page-breadcrumb" aria-label="Ticket breadcrumb">
      <button onClick={onBackToTickets} type="button">
        Tickets
      </button>
      <span>/</span>
      <span>#{ticketId}</span>
    </nav>
  );
}

function OverviewTab({
  analyticsStats,
  connectionStatus,
  onLoadSystem,
  onStartAnalysis,
  runState,
  systemLoaded,
  ticket,
  validation,
}: {
  analyticsStats: BlocksStat[];
  connectionStatus: ConnectionStatus;
  onLoadSystem: () => void;
  onStartAnalysis: () => void;
  runState: RunState;
  systemLoaded: boolean;
  ticket: Ticket;
  validation: ValidationResult;
}) {
  return (
    <>
      <BlocksStatsGrid density="compact" stats={analyticsStats} />
      <div className="split-layout">
        <section className="section-block report-card">
          <div className="section-heading">
            <HeadingWithTags badges={<StatusLabel label={formatRunState(runState)} />}>Customer report</HeadingWithTags>
          </div>
          <MarkdownContent omitFirstHeading="Customer report">{ticket.report}</MarkdownContent>
        </section>

        <section className="min-w-0">
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
        </section>

        <section className="section-block full-span">
          <div className="section-heading">
            <HeadingWithTags
              badges={
                <>
                  <StatusLabel label={`connection: ${formatConnection(connectionStatus)}`} />
                  <StatusLabel label={`validation: ${validation.status}`} />
                </>
              }
            >
              Next actions
            </HeadingWithTags>
          </div>
          <div className="action-strip">
            <button className={systemLoaded ? "button" : "button button-info"} onClick={onLoadSystem} type="button">
              {systemLoaded ? "Reload system info" : "Load system info"}
            </button>
            <button className={systemLoaded ? "button button-info" : "button"} onClick={onStartAnalysis} type="button">
              Start analysis
            </button>
          </div>
        </section>
      </div>
    </>
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
    <>
      <div className="split-layout">
        <section className="section-block full-span">
          <div className="section-heading">
            <HeadingWithTags badges={<StatusLabel label={formatConnection(connectionStatus)} />}>
              Customer system
            </HeadingWithTags>
          </div>
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
            <p className="body-copy">Load redacted system context before approving any connection.</p>
          )}
          <div className="action-strip">
            <button className="button" onClick={onLoadSystem} type="button">
              Load system info
            </button>
            <button
              className="button button-success"
              disabled={!systemLoaded || connectionStatus === "connected"}
              onClick={() => setConnectionDialogOpen(true)}
              type="button"
            >
              Approve connection
            </button>
            <span className="caption">No private key, token, or raw credential is displayed.</span>
          </div>
        </section>
      </div>
      <BlocksConfirmDialog
        confirmLabel="Approve"
        description="This approves a mock connection for the selected customer system. No backend connection is created yet."
        onConfirm={onApproveConnection}
        onOpenChange={setConnectionDialogOpen}
        open={connectionDialogOpen}
        title="Approve connection?"
        tone="success"
      />
    </>
  );
}

function AnalysisTab({
  analyticsStats,
  analysisReady,
  connectionStatus,
  onStartAnalysis,
}: {
  analyticsStats: BlocksStat[];
  analysisReady: boolean;
  connectionStatus: ConnectionStatus;
  onStartAnalysis: () => void;
}) {
  return (
    <>
      <BlocksStatsGrid density="compact" stats={analyticsStats} />
      <section className="section-block">
        <div className="section-heading">
          <div>
            <h2>Agent analysis</h2>
            <p className="body-copy">
              Context: {connectionStatus === "connected" ? "ticket + system" : "ticket only"}.
            </p>
          </div>
          <button className="button button-info" onClick={onStartAnalysis} type="button">
            {analysisReady ? "Re-run analysis" : "Start analysis"}
          </button>
        </div>

        {analysisReady ? (
          <table className="data-table">
            <colgroup>
              <col className="w-[32%]" />
              <col className="w-[52%]" />
              <col className="w-[16%]" />
            </colgroup>
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>Evidence</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {hypotheses.map((hypothesis) => (
                <tr key={hypothesis.id}>
                  <td>{hypothesis.title}</td>
                  <td>{hypothesis.evidence}</td>
                  <td>
                    <StatusLabel label={hypothesis.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="No analysis yet" detail="Start analysis to queue hypotheses and actions." />
        )}
      </section>
    </>
  );
}

function ActionsTab({ ticketId }: { ticketId: number }) {
  return (
    <section className="action-terminal-tab">
      <Suspense fallback={<EmptyState title="Loading terminal" detail="Preparing the remote terminal surface." />}>
        <TicketTerminal ticketId={ticketId} />
      </Suspense>
    </section>
  );
}

function LogsTab({
  events,
  logFilter,
  onCopy,
  onFilterChange,
}: {
  events: RunEvent[];
  logFilter: "all" | EventType;
  onCopy: () => void;
  onFilterChange: (filter: "all" | EventType) => void;
}) {
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <div className="inline-actions">
          <LogFilter value={logFilter} onChange={onFilterChange} />
          <button className="button" onClick={onCopy} type="button">
            Copy safe excerpt
          </button>
        </div>
      </div>
      <h2>Live run and audit log</h2>
      <div className="table-scroll">
        <EventTable events={events} />
      </div>
    </section>
  );
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
    <section className="section-block">
      <div className="section-heading">
        <div>
          <HeadingWithTags
            badges={
              <>
                <StatusLabel label={complete ? "complete" : "incomplete"} />
                <StatusLabel label={`validation: ${validation.status}`} />
              </>
            }
          >
            ERP activity draft
          </HeadingWithTags>
          <p className="body-copy">Required fields are editable before backend submission.</p>
        </div>
        <div className="inline-actions">
          <button className="button button-info" onClick={onGenerateDraft} type="button">
            Generate from audit
          </button>
          <button
            className="button button-success"
            disabled={!complete || submitStatus === "submitted"}
            onClick={onSubmit}
            type="button"
          >
            Submit activity
          </button>
        </div>
      </div>

      {notice ? <p className="notice-line">{notice}</p> : null}

      <div className="activity-form">
        {(
          [
            ["summary", "Summary", 2],
            ["root_cause", "Root cause", 3],
            ["actions_taken", "Actions taken", 5],
            ["commands_summary", "Commands summary", 5],
            ["validation_result", "Validation result", 3],
          ] as Array<[keyof ActivityDraft, string, number]>
        ).map(([field, label, rows]) => (
          <label key={field}>
            {label}
            <textarea
              onChange={(event) => onDraftChange({ ...draft, [field]: event.target.value })}
              rows={rows}
              value={draft[field]}
            />
          </label>
        ))}
      </div>
    </section>
  );
}
