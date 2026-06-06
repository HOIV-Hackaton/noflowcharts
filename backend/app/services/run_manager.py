from typing import Any

from sqlmodel import Session

from app.agent.planner import SAFETY_POLICY_SUMMARY, Planner
from app.clients.phoenix import PhoenixClient
from app.core.errors import SafetyError, ValidationError
from app.core.redaction import redact_payload
from app.db.models import Action, ActivityDraft, Run, utc_now
from app.repositories.runs import RunRepository
from app.schemas.phoenix import Activity, ActivityCreate, CustomerSystem, TicketStatus
from app.schemas.runs import (
    ActionRead,
    ActionStatus,
    ActivityDraftRead,
    ActivityDraftUpdate,
    ActivityReviewStatus,
    ActivitySubmitRequest,
    CommandClassification,
    CommandResultRead,
    ConfirmationStatus,
    RunRead,
    RunStateRead,
    RunStatus,
    ValidationStatus,
)
from app.services.audit_log import AuditLog
from app.services.activity_generator import ActivityGenerator
from app.services.events import persist_and_publish_ws_event_sync
from app.services.safety import classify_command
from app.services.ssh_runner import SshRunner


RISK_CONFIRMATION_PREFIX = "RUN "


class RunManager:
    def __init__(
        self,
        session: Session,
        phoenix_client: PhoenixClient | None = None,
        planner: Planner | None = None,
        ssh_runner: SshRunner | None = None,
        activity_generator: ActivityGenerator | None = None,
    ):
        self.session = session
        self.repo = RunRepository(session)
        self.audit = AuditLog(session)
        self.phoenix = phoenix_client or PhoenixClient()
        self.planner = planner
        self.ssh_runner = ssh_runner or SshRunner()
        self.activity_generator = activity_generator

    def start_run(self, ticket_id: int) -> RunStateRead:
        ticket = self.phoenix.get_ticket(ticket_id)
        customer_system = self.phoenix.get_customer_system(ticket_id)
        snapshot = {"ticket": ticket.model_dump(mode="json"), "customer_system": customer_system.model_dump(mode="json")}
        run = self.repo.create_run(ticket_id=ticket_id, customer_system_snapshot=snapshot)
        self.audit.record("ticket_loaded", {"ticket_id": ticket_id, "title": ticket.title}, run.id)
        self.audit.record("customer_system_loaded", {"ticket_id": ticket_id, "system": customer_system.model_dump(mode="json")}, run.id)
        self.phoenix.set_ticket_status(ticket_id, TicketStatus.PENDING)
        self.repo.update_run_status(run, RunStatus.PENDING)
        self.audit.record("ticket_set_pending", {"ticket_id": ticket_id}, run.id)
        self._event(run.id, "run_started", {"ticket_id": ticket_id, "status": RunStatus.PENDING.value})
        return self.state(run.id)

    def confirm_ssh(self, run_id: str) -> RunStateRead:
        run = self._run(run_id)
        self.repo.set_ssh_confirmed(run)
        self.repo.update_run_status(run, RunStatus.DIAGNOSING)
        self.audit.record("ssh_connection_confirmed", {"ticket_id": run.ticket_id}, run.id)
        self._event(run.id, "ssh_confirmed", {"status": RunStatus.DIAGNOSING.value})
        return self.state(run.id)

    def propose_next(self, run_id: str) -> RunStateRead:
        run = self._run(run_id)
        self._require_ssh_confirmed(run)
        snapshot = self._snapshot(run)
        observations = self._observations(run.id)
        planner = self.planner or Planner()
        proposal = planner.propose_next_command(
            ticket=snapshot.get("ticket", {}),
            customer_system=snapshot.get("customer_system", {}),
            observations=observations,
            safety_policy=SAFETY_POLICY_SUMMARY,
        )
        safety = classify_command(proposal.command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        action = self.repo.add_action(
            run,
            command=proposal.command,
            classification=safety.classification,
            intent=proposal.intent,
            risk_reason=safety.reason,
            expected_signal=proposal.expected_signal,
            typed_confirmation_status=typed_status,
        )
        self.audit.record("command_classified", {"command": proposal.command, "classification": safety.classification.value, "reason": safety.reason}, run.id)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"command": proposal.command, "reason": safety.reason}, run.id)
            self._event(run.id, "command_blocked", {"action_id": action.id, "reason": safety.reason})
        else:
            self.audit.record("command_proposed", {"action_id": action.id, "command": proposal.command, "intent": proposal.intent}, run.id)
            self._event(run.id, "command_proposed", {"action_id": action.id, "command": proposal.command, "classification": safety.classification.value})
        return self.state(run.id)

    def confirm_risk(self, run_id: str, confirmation_text: str, action_id: int | None = None) -> RunStateRead:
        run = self._run(run_id)
        action = self._action(run, action_id)
        expected = f"{RISK_CONFIRMATION_PREFIX}{action.command}"
        if action.typed_confirmation_status != ConfirmationStatus.PENDING.value:
            raise ValidationError("Current action does not require typed confirmation")
        if confirmation_text != expected:
            raise ValidationError(f"Typed confirmation must exactly match: {expected}")
        self.repo.update_action_status(action, ActionStatus.PROPOSED, typed_confirmation_status=ConfirmationStatus.CONFIRMED)
        self.audit.record("typed_confirmation", {"action_id": action.id, "confirmed": True}, run.id)
        self._event(run.id, "risk_confirmed", {"action_id": action.id})
        return self.state(run.id)

    def approve(self, run_id: str, action_id: int | None = None) -> tuple[RunStateRead, int]:
        run = self._run(run_id)
        self._require_ssh_confirmed(run)
        action = self._action(run, action_id)
        if action.status == ActionStatus.BLOCKED.value:
            raise SafetyError("Blocked commands cannot be approved; edit the command or request a safer alternative")
        if action.typed_confirmation_status == ConfirmationStatus.PENDING.value:
            raise ValidationError("Risky command requires typed confirmation before approval")
        self.repo.update_action_status(action, ActionStatus.APPROVED)
        self.audit.record("approved_command", {"action_id": action.id, "command": action.command}, run.id)
        self._event(run.id, "command_approved", {"action_id": action.id})
        return self.state(run.id), action.id

    def execute_action(self, run_id: str, action_id: int) -> None:
        run = self._run(run_id)
        action = self._action(run, action_id)
        if action.status != ActionStatus.APPROVED.value:
            raise ValidationError("Action must be approved before execution")
        safety = classify_command(action.command)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"action_id": action.id, "command": action.command, "reason": safety.reason}, run.id)
            self._event(run.id, "command_blocked", {"action_id": action.id, "reason": safety.reason})
            return
        if safety.requires_typed_confirmation and action.typed_confirmation_status != ConfirmationStatus.CONFIRMED.value:
            raise ValidationError("Risky command requires typed confirmation before execution")

        self.repo.update_run_status(run, RunStatus.RUNNING_COMMAND)
        self.repo.update_action_status(action, ActionStatus.RUNNING)
        self.audit.record("safety_result", {"action_id": action.id, "classification": safety.classification.value, "reason": safety.reason}, run.id)
        self._event(run.id, "command_running", {"action_id": action.id})
        try:
            result = self.ssh_runner.run(self._customer_system(run).system, action.command)
            stored = self.repo.add_command_result(action, result.command, result.exit_code, result.stdout, result.stderr, result.timed_out)
            status = ActionStatus.COMPLETED if result.exit_code == 0 and not result.timed_out else ActionStatus.FAILED
            self.repo.update_action_status(action, status)
            self.repo.update_run_status(run, RunStatus.DIAGNOSING)
            self.audit.record(
                "command_result",
                {
                    "action_id": action.id,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                run.id,
            )
            self._event(run.id, "command_result", {"action_id": action.id, "result_id": stored.id, "exit_code": result.exit_code, "timed_out": result.timed_out})
        except Exception as exc:
            self.repo.update_action_status(action, ActionStatus.FAILED)
            self.repo.update_run_status(run, RunStatus.FAILED)
            self.audit.record("command_result", {"action_id": action.id, "error": str(exc)}, run.id)
            self._event(run.id, "command_failed", {"action_id": action.id, "error": str(exc)})
            raise

    def reject(self, run_id: str, action_id: int | None = None) -> RunStateRead:
        run = self._run(run_id)
        action = self._action(run, action_id)
        self.repo.update_action_status(action, ActionStatus.REJECTED)
        self.repo.update_run_status(run, RunStatus.DIAGNOSING)
        self.audit.record("rejected_command", {"action_id": action.id, "command": action.command}, run.id)
        self._event(run.id, "command_rejected", {"action_id": action.id})
        return self.state(run.id)

    def edit(self, run_id: str, command: str, intent: str | None = None, action_id: int | None = None) -> RunStateRead:
        run = self._run(run_id)
        action = self._action(run, action_id)
        safety = classify_command(command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        self.repo.update_action_command(action, command, safety.classification, safety.reason, typed_status, intent=intent)
        self.audit.record("edited_command", {"action_id": action.id, "command": command}, run.id)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"action_id": action.id, "command": command, "reason": safety.reason}, run.id)
        self._event(run.id, "command_edited", {"action_id": action.id, "classification": safety.classification.value, "blocked": safety.blocked})
        return self.state(run.id)

    def retry(self, run_id: str, action_id: int | None = None) -> RunStateRead:
        run = self._run(run_id)
        previous = self._action(run, action_id)
        safety = classify_command(previous.command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        action = self.repo.add_action(run, previous.command, safety.classification, previous.intent, safety.reason, previous.expected_signal, typed_status)
        self.audit.record("retry", {"previous_action_id": previous.id, "action_id": action.id, "command": action.command}, run.id)
        self._event(run.id, "command_retry_proposed", {"action_id": action.id})
        return self.state(run.id)

    def confirm_validation(self, run_id: str, evidence: str) -> RunStateRead:
        run = self._run(run_id)
        if not evidence.strip():
            raise ValidationError("Validation confirmation requires concrete evidence")
        successful_results = [result for result in self.repo.list_command_results(run.id) if result.exit_code == 0 and not result.timed_out]
        if not successful_results:
            raise ValidationError("Validation requires at least one successful command result as evidence")
        self.repo.set_validation_status(run, ValidationStatus.HUMAN_CONFIRMED, confirmed=True)
        self.repo.update_run_status(run, RunStatus.READY_FOR_ACTIVITY)
        self.audit.record("validation_evidence", {"evidence": evidence, "result_count": len(successful_results)}, run.id)
        self.audit.record("human_validation_confirmation", {"confirmed": True}, run.id)
        self._event(run.id, "validation_confirmed", {"status": RunStatus.READY_FOR_ACTIVITY.value})
        return self.state(run.id)

    def abort(self, run_id: str) -> RunStateRead:
        run = self._run(run_id)
        self.repo.update_run_status(run, RunStatus.ABORTED)
        self.audit.record("abort", {"ticket_id": run.ticket_id}, run.id)
        self._event(run.id, "run_aborted", {"status": RunStatus.ABORTED.value})
        return self.state(run.id)

    def generate_activity_draft(self, run_id: str) -> ActivityDraftRead:
        run = self._run(run_id)
        self._require_ready_for_activity(run)
        snapshot = self._snapshot(run)
        actions = [self._action_payload(action) for action in self.repo.list_actions(run.id)]
        command_results = [self._command_result_payload(result) for result in self.repo.list_command_results(run.id)]
        validation_events = [event.payload for event in self.audit.for_run(run.id) if event.type in {"validation_evidence", "human_validation_confirmation"}]
        activity_generator = self.activity_generator or ActivityGenerator()
        generated = activity_generator.generate(
            ticket=snapshot.get("ticket", {}),
            customer_system=snapshot.get("customer_system", {}),
            actions=actions,
            command_results=command_results,
            validation={"status": run.validation_status, "confirmed": run.validation_confirmed, "events": validation_events},
        )
        draft = self.repo.upsert_activity_draft(run, **generated.model_dump())
        self.audit.record("activity_draft_generated", generated.model_dump(), run.id)
        self._event(run.id, "activity_draft_generated", {"draft_id": draft.id})
        return ActivityDraftRead.model_validate(draft, from_attributes=True)

    def update_activity_draft(self, run_id: str, update: ActivityDraftUpdate) -> ActivityDraftRead:
        run = self._run(run_id)
        self._require_ready_for_activity(run)
        fields = update.model_dump(exclude_unset=True)
        if not fields:
            raise ValidationError("Activity draft update must include at least one field")
        draft = self.repo.upsert_activity_draft(run, **fields)
        self.repo.set_activity_review_status(draft, ActivityReviewStatus.DRAFT)
        self.audit.record("activity_draft_updated", fields, run.id)
        self._event(run.id, "activity_draft_updated", {"draft_id": draft.id})
        return ActivityDraftRead.model_validate(draft, from_attributes=True)

    def review_activity_draft(self, run_id: str, approved: bool = True) -> ActivityDraftRead:
        run = self._run(run_id)
        self._require_ready_for_activity(run)
        draft = self._activity_draft(run)
        if not approved:
            self.repo.set_activity_review_status(draft, ActivityReviewStatus.DRAFT)
            self.audit.record("activity_reviewed", {"approved": False}, run.id)
            self._event(run.id, "activity_reviewed", {"approved": False})
            return ActivityDraftRead.model_validate(draft, from_attributes=True)
        self._require_complete_activity_draft(draft)
        draft = self.repo.set_activity_review_status(draft, ActivityReviewStatus.REVIEWED)
        self.audit.record("activity_reviewed", {"approved": True}, run.id)
        self._event(run.id, "activity_reviewed", {"approved": True})
        return ActivityDraftRead.model_validate(draft, from_attributes=True)

    def submit_activity(self, run_id: str, request: ActivitySubmitRequest) -> Activity:
        if not request.submit:
            raise ValidationError("Activity submission requires explicit submit=true")
        run = self._run(run_id)
        self._require_ready_for_activity(run)
        draft = self._activity_draft(run)
        self._require_complete_activity_draft(draft)
        if draft.review_status != ActivityReviewStatus.REVIEWED.value:
            raise ValidationError("Activity draft must be explicitly reviewed before submission")
        activity = ActivityCreate(
            ticket_id=run.ticket_id,
            start_datetime=run.created_at,
            end_datetime=utc_now(),
            description=draft.description,
            summary=draft.summary,
            root_cause=draft.root_cause,
            actions_taken=draft.actions_taken,
            commands_summary=draft.commands_summary,
            validation_result=draft.validation_result,
        )
        created = self.phoenix.create_activity(activity)
        self.repo.set_activity_review_status(draft, ActivityReviewStatus.SUBMITTED)
        self.repo.update_run_status(run, RunStatus.SUBMITTED)
        self.audit.record("activity_submitted", {"activity_id": created.id, "ticket_id": run.ticket_id}, run.id)
        self._event(run.id, "activity_submitted", {"activity_id": created.id})
        self.phoenix.set_ticket_status(run.ticket_id, TicketStatus.DONE)
        self.audit.record("ticket_set_done", {"ticket_id": run.ticket_id}, run.id)
        self._event(run.id, "ticket_done", {"ticket_id": run.ticket_id, "status": TicketStatus.DONE.value})
        return created

    def audit_events(self, run_id: str):
        self._run(run_id)
        return self.audit.for_run(run_id)

    def state(self, run_id: str) -> RunStateRead:
        run = self._run(run_id)
        action = self.repo.get_current_action(run)
        results = self.repo.list_command_results(run.id)
        draft = self.repo.get_activity_draft(run.id)
        return RunStateRead(
            run=RunRead.model_validate(run, from_attributes=True),
            current_action=ActionRead.model_validate(action, from_attributes=True) if action else None,
            command_results=[CommandResultRead.model_validate(result, from_attributes=True) for result in results],
            activity_draft=ActivityDraftRead.model_validate(draft, from_attributes=True) if draft else None,
        )

    def _run(self, run_id: str) -> Run:
        run = self.repo.get_run(run_id)
        if run is None:
            raise ValidationError("Run was not found")
        return run

    def _action(self, run: Run, action_id: int | None) -> Action:
        action = self.repo.get_action(action_id) if action_id is not None else self.repo.get_current_action(run)
        if action is None or action.run_id != run.id:
            raise ValidationError("Action was not found for this run")
        return action

    def _snapshot(self, run: Run) -> dict[str, Any]:
        return run.customer_system_snapshot or {}

    def _customer_system(self, run: Run) -> CustomerSystem:
        snapshot = self._snapshot(run).get("customer_system")
        if not snapshot:
            raise ValidationError("Run has no customer system snapshot")
        return CustomerSystem.model_validate(snapshot)

    def _observations(self, run_id: str) -> list[dict[str, Any]]:
        results = self.repo.list_command_results(run_id)
        return [redact_payload({"command": result.command, "exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr, "timed_out": result.timed_out}) for result in results]

    def _require_ssh_confirmed(self, run: Run) -> None:
        if not run.ssh_confirmed:
            raise ValidationError("Technician must confirm SSH connection before any system action")

    def _require_ready_for_activity(self, run: Run) -> None:
        if run.status not in {RunStatus.READY_FOR_ACTIVITY.value, RunStatus.SUBMITTED.value} or not run.validation_confirmed:
            raise ValidationError("Activity requires human-confirmed validation evidence first")

    def _activity_draft(self, run: Run) -> ActivityDraft:
        draft = self.repo.get_activity_draft(run.id)
        if draft is None:
            raise ValidationError("Activity draft was not found")
        return draft

    def _require_complete_activity_draft(self, draft: ActivityDraft) -> None:
        required_fields = ["summary", "root_cause", "actions_taken", "commands_summary", "validation_result", "description"]
        missing = [field for field in required_fields if not (getattr(draft, field) or "").strip()]
        if missing:
            raise ValidationError(f"Activity draft is missing required field(s): {', '.join(missing)}")

    def _action_payload(self, action: Action) -> dict[str, Any]:
        return redact_payload(
            {
                "id": action.id,
                "status": action.status,
                "command": action.command,
                "classification": action.command_classification,
                "intent": action.intent,
                "risk_reason": action.risk_reason,
                "expected_signal": action.expected_signal,
            }
        )

    def _command_result_payload(self, result) -> dict[str, Any]:
        return redact_payload(
            {
                "action_id": result.action_id,
                "command": result.command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": result.timed_out,
            }
        )

    def _event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        persist_and_publish_ws_event_sync(run_id, event_type, payload)
