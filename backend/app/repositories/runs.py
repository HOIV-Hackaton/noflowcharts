from typing import Any

from sqlmodel import Session, select

from app.core.redaction import redact_payload
from app.db.models import Action, ActivityDraft, AuditEvent, CommandResult, Run, WebSocketEvent, utc_now
from app.schemas.runs import ActionStatus, ActivityReviewStatus, CommandClassification, ConfirmationStatus, RunStatus, ValidationStatus


class RunRepository:
    def __init__(self, session: Session, secrets: list[str] | None = None):
        self.session = session
        self.secrets = secrets or []

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
        typed_confirmation_status: ConfirmationStatus = ConfirmationStatus.NOT_REQUIRED,
    ) -> Action:
        action = Action(
            run_id=run.id,
            command=command,
            command_classification=classification.value,
            intent=intent,
            risk_reason=risk_reason,
            expected_signal=expected_signal,
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
    ) -> Action:
        action.command = command
        action.edited_command = command
        action.command_classification = classification.value
        action.risk_reason = risk_reason
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
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
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
