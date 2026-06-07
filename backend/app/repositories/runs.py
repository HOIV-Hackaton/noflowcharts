from typing import Any

from sqlmodel import Session, select

from app.core.redaction import redact_payload
from app.core.config import get_settings
from app.db.models import Action, ActivityDraft, AuditEvent, CommandResult, Run, TerminalCommand, TerminalSession, TerminalTranscriptEvent, WebSocketEvent, utc_now
from app.schemas.runs import (
    ActionStatus,
    ActivityReviewStatus,
    CommandClassification,
    ConfirmationStatus,
    RunStatus,
    TerminalCommandSource,
    TerminalCommandStatus,
    TerminalSessionStatus,
    ValidationStatus,
)


MAX_STREAM_CHARS = 32 * 1024


class RunRepository:
    def __init__(self, session: Session, secrets: list[str] | None = None):
        self.session = session
        self.secrets = secrets if secrets is not None else get_settings().configured_secrets()

    def create_run(self, ticket_id: int, customer_system_snapshot: dict[str, Any] | None = None) -> Run:
        run = Run(ticket_id=ticket_id, customer_system_snapshot=customer_system_snapshot)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run(self, run_id: str) -> Run | None:
        return self.session.get(Run, run_id)

    def update_run_status(self, run: Run, status: RunStatus) -> Run:
        run.status = status.value
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def set_current_action(self, run: Run, action: Action | None) -> Run:
        run.current_action_id = action.id if action is not None else None
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def set_ssh_confirmed(self, run: Run) -> Run:
        run.ssh_confirmed = True
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def set_validation_status(self, run: Run, status: ValidationStatus, confirmed: bool = False) -> Run:
        run.validation_status = status.value
        run.validation_confirmed = confirmed
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def add_action(
        self,
        run: Run,
        command: str,
        classification: CommandClassification,
        intent: str | None = None,
        risk_reason: str | None = None,
        expected_signal: str | None = None,
        write_preview: dict[str, Any] | None = None,
        typed_confirmation_status: ConfirmationStatus = ConfirmationStatus.NOT_REQUIRED,
    ) -> Action:
        action = Action(
            run_id=run.id,
            command=command,
            command_classification=classification.value,
            intent=intent,
            risk_reason=risk_reason,
            expected_signal=expected_signal,
            write_preview=redact_payload(write_preview, self.secrets) if write_preview is not None else None,
            typed_confirmation_status=typed_confirmation_status.value,
        )
        self.session.add(action)
        self.session.commit()
        self.session.refresh(action)
        run.current_action_id = action.id
        run.status = RunStatus.AWAITING_APPROVAL.value
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        return action

    def get_action(self, action_id: int) -> Action | None:
        return self.session.get(Action, action_id)

    def get_current_action(self, run: Run) -> Action | None:
        if run.current_action_id is None:
            return None
        return self.get_action(run.current_action_id)

    def list_actions(self, run_id: str) -> list[Action]:
        statement = select(Action).where(Action.run_id == run_id).order_by(Action.id)
        return list(self.session.exec(statement))

    def update_action_status(
        self,
        action: Action,
        status: ActionStatus,
        edited_command: str | None = None,
        typed_confirmation_status: ConfirmationStatus | None = None,
    ) -> Action:
        action.status = status.value
        action.updated_at = utc_now()
        if edited_command is not None:
            action.edited_command = edited_command
        if typed_confirmation_status is not None:
            action.typed_confirmation_status = typed_confirmation_status.value
        self.session.add(action)
        self.session.commit()
        self.session.refresh(action)
        return action

    def update_action_command(
        self,
        action: Action,
        command: str,
        classification: CommandClassification,
        risk_reason: str | None,
        typed_confirmation_status: ConfirmationStatus,
        intent: str | None = None,
        write_preview: dict[str, Any] | None = None,
    ) -> Action:
        action.command = command
        action.edited_command = command
        action.command_classification = classification.value
        action.risk_reason = risk_reason
        action.write_preview = redact_payload(write_preview, self.secrets) if write_preview is not None else None
        action.typed_confirmation_status = typed_confirmation_status.value
        action.status = ActionStatus.EDITED.value
        if intent is not None:
            action.intent = intent
        action.updated_at = utc_now()
        self.session.add(action)
        self.session.commit()
        self.session.refresh(action)
        return action

    def add_command_result(
        self,
        action: Action,
        command: str,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        timed_out: bool = False,
    ) -> CommandResult:
        result = CommandResult(
            action_id=action.id,
            command=redact_payload(command, self.secrets),
            exit_code=exit_code,
            stdout=_truncate_stream(redact_payload(stdout, self.secrets)),
            stderr=_truncate_stream(redact_payload(stderr, self.secrets)),
            timed_out=timed_out,
            ended_at=utc_now(),
        )
        self.session.add(result)
        self.session.commit()
        self.session.refresh(result)
        return result

    def list_command_results(self, run_id: str) -> list[CommandResult]:
        statement = (
            select(CommandResult)
            .join(Action, CommandResult.action_id == Action.id)
            .where(Action.run_id == run_id)
            .order_by(CommandResult.id)
        )
        return list(self.session.exec(statement))

    def add_audit_event(self, event_type: str, payload: dict[str, Any], run_id: str | None = None) -> AuditEvent:
        event = AuditEvent(
            run_id=run_id,
            type=event_type,
            payload=redact_payload(payload, self.secrets),
            redacted=True,
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_audit_events(self, run_id: str) -> list[AuditEvent]:
        statement = select(AuditEvent).where(AuditEvent.run_id == run_id).order_by(AuditEvent.id)
        return list(self.session.exec(statement))

    def upsert_activity_draft(self, run: Run, **fields: str | None) -> ActivityDraft:
        statement = select(ActivityDraft).where(ActivityDraft.run_id == run.id)
        draft = self.session.exec(statement).first()
        if draft is None:
            draft = ActivityDraft(run_id=run.id)
        for key, value in fields.items():
            if hasattr(draft, key):
                setattr(draft, key, value)
        draft.updated_at = utc_now()
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def get_activity_draft(self, run_id: str) -> ActivityDraft | None:
        statement = select(ActivityDraft).where(ActivityDraft.run_id == run_id)
        return self.session.exec(statement).first()

    def set_activity_review_status(self, draft: ActivityDraft, status: ActivityReviewStatus) -> ActivityDraft:
        draft.review_status = status.value
        draft.updated_at = utc_now()
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def add_websocket_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> WebSocketEvent:
        event = WebSocketEvent(run_id=run_id, type=event_type, payload=redact_payload(payload, self.secrets))
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def replay_websocket_events(self, run_id: str, last_event_id: int | None = None) -> list[WebSocketEvent]:
        statement = select(WebSocketEvent).where(WebSocketEvent.run_id == run_id)
        if last_event_id is not None:
            statement = statement.where(WebSocketEvent.event_id > last_event_id)
        statement = statement.order_by(WebSocketEvent.event_id)
        return list(self.session.exec(statement))

    def create_terminal_session(self, run_id: str) -> TerminalSession:
        terminal_session = TerminalSession(run_id=run_id)
        self.session.add(terminal_session)
        self.session.commit()
        self.session.refresh(terminal_session)
        return terminal_session

    def get_open_terminal_session(self, run_id: str) -> TerminalSession | None:
        statement = (
            select(TerminalSession)
            .where(TerminalSession.run_id == run_id, TerminalSession.status == TerminalSessionStatus.OPEN.value)
            .order_by(TerminalSession.id.desc())
        )
        return self.session.exec(statement).first()

    def touch_terminal_session(self, terminal_session: TerminalSession) -> TerminalSession:
        terminal_session.last_seen_at = utc_now()
        self.session.add(terminal_session)
        self.session.commit()
        self.session.refresh(terminal_session)
        return terminal_session

    def close_terminal_session(self, terminal_session: TerminalSession, reason: str) -> TerminalSession:
        terminal_session.status = TerminalSessionStatus.CLOSED.value
        terminal_session.closed_at = utc_now()
        terminal_session.last_seen_at = terminal_session.closed_at
        terminal_session.close_reason = reason
        self.session.add(terminal_session)
        self.session.commit()
        self.session.refresh(terminal_session)
        return terminal_session

    def add_terminal_command(
        self,
        run_id: str,
        source: TerminalCommandSource,
        original_command: str,
        terminal_session_id: int | None = None,
        final_command: str | None = None,
        status: TerminalCommandStatus = TerminalCommandStatus.SUBMITTED,
        classification: CommandClassification | None = None,
        risk_reason: str | None = None,
        write_preview: dict[str, Any] | None = None,
    ) -> TerminalCommand:
        command = TerminalCommand(
            run_id=run_id,
            terminal_session_id=terminal_session_id,
            source=source.value,
            status=status.value,
            original_command=redact_payload(original_command, self.secrets),
            final_command=redact_payload(final_command, self.secrets) if final_command is not None else None,
            classification=classification.value if classification is not None else None,
            risk_reason=redact_payload(risk_reason, self.secrets) if risk_reason is not None else None,
            write_preview=redact_payload(write_preview, self.secrets) if write_preview is not None else None,
        )
        self.session.add(command)
        self.session.commit()
        self.session.refresh(command)
        return command

    def get_terminal_command(self, command_id: int) -> TerminalCommand | None:
        return self.session.get(TerminalCommand, command_id)

    def update_terminal_command(
        self,
        command: TerminalCommand,
        status: TerminalCommandStatus | None = None,
        final_command: str | None = None,
        edited_from: str | None = None,
        edited_to: str | None = None,
        classification: CommandClassification | None = None,
        risk_reason: str | None = None,
        write_preview: dict[str, Any] | None = None,
        exit_code: int | None = None,
        output: str | None = None,
        started: bool = False,
        ended: bool = False,
    ) -> TerminalCommand:
        if status is not None:
            command.status = status.value
        if final_command is not None:
            command.final_command = redact_payload(final_command, self.secrets)
        if edited_from is not None:
            command.edited_from = redact_payload(edited_from, self.secrets)
        if edited_to is not None:
            command.edited_to = redact_payload(edited_to, self.secrets)
        if classification is not None:
            command.classification = classification.value
        if risk_reason is not None:
            command.risk_reason = redact_payload(risk_reason, self.secrets)
        if write_preview is not None:
            command.write_preview = redact_payload(write_preview, self.secrets)
        if exit_code is not None:
            command.exit_code = exit_code
        if output is not None:
            command.output = _truncate_stream(redact_payload(output, self.secrets))
        now = utc_now()
        if started and command.started_at is None:
            command.started_at = now
        if ended:
            command.ended_at = now
        command.updated_at = now
        self.session.add(command)
        self.session.commit()
        self.session.refresh(command)
        return command

    def list_terminal_commands(self, run_id: str) -> list[TerminalCommand]:
        statement = select(TerminalCommand).where(TerminalCommand.run_id == run_id).order_by(TerminalCommand.id)
        return list(self.session.exec(statement))

    def add_terminal_transcript_event(self, run_id: str, terminal_session_id: int | None, data: str, stream: str = "stdout") -> TerminalTranscriptEvent:
        event = TerminalTranscriptEvent(
            run_id=run_id,
            terminal_session_id=terminal_session_id,
            stream=stream,
            data=_truncate_stream(redact_payload(data, self.secrets)),
            redacted=True,
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_terminal_transcript(self, run_id: str) -> list[TerminalTranscriptEvent]:
        statement = select(TerminalTranscriptEvent).where(TerminalTranscriptEvent.run_id == run_id).order_by(TerminalTranscriptEvent.id)
        return list(self.session.exec(statement))


def _truncate_stream(value: str) -> str:
    if len(value) <= MAX_STREAM_CHARS:
        return value
    return value[:MAX_STREAM_CHARS] + "\n[truncated]"
