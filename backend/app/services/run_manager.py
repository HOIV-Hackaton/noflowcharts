import re
from typing import Any

from sqlmodel import Session

from app.agent.planner import SAFETY_POLICY_SUMMARY, CommandProposal, Planner
from app.clients.phoenix import PhoenixClient
from app.core.errors import SafetyError, ValidationError
from app.core.redaction import redact_payload, redact_text
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
    RelatedTicketRead,
    RunRead,
    RunStateRead,
    RunStatus,
    ValidationStatus,
)
from app.services.audit_log import AuditLog
from app.services.activity_generator import ActivityGenerator
from app.services.diagnostic_policy import MAX_AUTO_DIAGNOSTIC_STEPS
from app.services.diagnostic_tools import DiagnosticToolbox
from app.services.events import persist_and_publish_ws_event_sync
from app.services.safety import classify_command
from app.services.ssh_runner import SshRunner
from app.services.ticket_memory import RelatedTicketContext, TicketMemoryService
from app.services.terminal_manager import terminal_manager
from app.services.write_preview import WritePreviewer


RISK_CONFIRMATION_PREFIX = "RUN "


class RunManager:
    def __init__(
        self,
        session: Session,
        phoenix_client: PhoenixClient | None = None,
        planner: Planner | None = None,
        ssh_runner: SshRunner | None = None,
        diagnostic_toolbox: DiagnosticToolbox | None = None,
        activity_generator: ActivityGenerator | None = None,
        ticket_memory_service: TicketMemoryService | None = None,
        write_previewer: WritePreviewer | None = None,
    ):
        self.session = session
        self.repo = RunRepository(session)
        self.audit = AuditLog(session)
        self.phoenix = phoenix_client or PhoenixClient()
        self.planner = planner
        self.ssh_runner = ssh_runner or SshRunner()
        self.diagnostic_toolbox = diagnostic_toolbox or DiagnosticToolbox(self.ssh_runner)
        self.activity_generator = activity_generator
        self.ticket_memory_service = ticket_memory_service
        self.write_previewer = write_previewer

    def start_run(self, ticket_id: int) -> RunStateRead:
        ticket = self.phoenix.get_ticket(ticket_id)
        customer_system = self.phoenix.get_customer_system(ticket_id)
        snapshot = {"ticket": ticket.model_dump(mode="json"), "customer_system": customer_system.model_dump(mode="json")}
        related_context = self._prepare_related_ticket(ticket)
        if related_context is not None:
            snapshot["related_ticket"] = related_context.model_dump(mode="json")
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
        proposal = self._ticket_validation_proposal(snapshot, observations)
        if proposal is None:
            planner = self.planner or Planner()
            phase = self._select_agent_phase(run, observations)
            self.audit.record("agent_phase_selected", {"phase": phase, "observation_count": len(observations)}, run.id)
            self._event(run.id, "agent_phase_selected", {"phase": phase})
            proposal = self._propose_for_phase(planner, phase, snapshot, observations, run.id)
        safety = classify_command(proposal.command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        write_preview = self._write_preview(run, proposal.command, safety)
        action = self.repo.add_action(
            run,
            command=proposal.command,
            classification=safety.classification,
            intent=proposal.intent,
            risk_reason=safety.reason,
            expected_signal=proposal.expected_signal,
            write_preview=write_preview,
            typed_confirmation_status=typed_status,
        )
        self.audit.record("command_classified", {"command": proposal.command, "classification": safety.classification.value, "reason": safety.reason}, run.id)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"command": proposal.command, "reason": safety.reason}, run.id)
            self._event(run.id, "command_blocked", {"action_id": action.id, "reason": safety.reason})
        else:
            self.audit.record("command_proposed", {"action_id": action.id, "command": proposal.command, "intent": proposal.intent}, run.id)
            self._event(run.id, "command_proposed", {"action_id": action.id, "command": proposal.command, "classification": safety.classification.value, "write_preview": write_preview})
        return self.state(run.id)

    def _propose_for_phase(self, planner: Planner, phase: str, snapshot: dict[str, Any], observations: list[dict[str, Any]], run_id: str) -> CommandProposal:
        ticket = snapshot.get("ticket", {})
        customer_system = snapshot.get("customer_system", {})
        related_ticket = snapshot.get("related_ticket")
        if phase == "verification" and hasattr(planner, "propose_verification_command"):
            return planner.propose_verification_command(
                ticket=ticket,
                customer_system=customer_system,
                observations=observations,
                safety_policy=SAFETY_POLICY_SUMMARY,
                related_ticket=related_ticket,
                run_id=run_id,
            )
        if phase == "execution" and hasattr(planner, "propose_execution_command"):
            return planner.propose_execution_command(
                ticket=ticket,
                customer_system=customer_system,
                observations=observations,
                safety_policy=SAFETY_POLICY_SUMMARY,
                related_ticket=related_ticket,
                run_id=run_id,
            )
        if hasattr(planner, "propose_diagnosis_command"):
            return planner.propose_diagnosis_command(
                ticket=ticket,
                customer_system=customer_system,
                observations=observations,
                safety_policy=SAFETY_POLICY_SUMMARY,
                related_ticket=related_ticket,
                run_id=run_id,
            )
        return planner.propose_next_command(
            ticket=ticket,
            customer_system=customer_system,
            observations=observations,
            safety_policy=SAFETY_POLICY_SUMMARY,
            related_ticket=related_ticket,
            run_id=run_id,
        )

    def start_safe_autodiagnosis(self, run_id: str) -> RunStateRead:
        run = self._run(run_id)
        self._require_ssh_confirmed(run)
        if run.status not in {RunStatus.DIAGNOSING.value, RunStatus.PENDING.value}:
            raise ValidationError("Safe autodiagnosis can only start during diagnosis")

        self.repo.update_run_status(run, RunStatus.DIAGNOSING)
        self.audit.record("safe_autodiagnosis_started", {"max_steps": MAX_AUTO_DIAGNOSTIC_STEPS}, run.id)
        self._event(run.id, "safe_autodiagnosis_started", {"max_steps": MAX_AUTO_DIAGNOSTIC_STEPS})

        planner = self.planner or Planner()
        for _ in range(MAX_AUTO_DIAGNOSTIC_STEPS - self._auto_diagnostic_count(run.id)):
            run = self._run(run_id)
            if run.status != RunStatus.DIAGNOSING.value:
                self.audit.record("safe_autodiagnosis_stopped", {"reason": "run_left_diagnosis", "status": run.status}, run.id)
                self._event(run.id, "safe_autodiagnosis_stopped", {"reason": "run_left_diagnosis", "status": run.status})
                return self.state(run.id)

            snapshot = self._snapshot(run)
            observations = self._observations(run.id)
            proposal = planner.propose_diagnostic_tool(
                ticket=snapshot.get("ticket", {}),
                customer_system=snapshot.get("customer_system", {}),
                observations=observations,
                related_ticket=snapshot.get("related_ticket"),
                run_id=run.id,
            )
            self.audit.record(
                "agent_diagnostic_requested",
                {"mode": proposal.mode, "tool": proposal.tool, "arguments": proposal.arguments, "intent": proposal.intent},
                run.id,
            )

            if proposal.mode == "command_proposal":
                assert proposal.command is not None
                command = CommandProposal(
                    intent=proposal.intent,
                    command=proposal.command,
                    expected_signal=proposal.expected_signal,
                    risk_level=proposal.risk_level,
                    rollback_note=proposal.rollback_note,
                    evidence_basis=proposal.evidence_basis,
                    evidence_gap=proposal.evidence_gap,
                )
                self._add_proposed_action(run, command, event_type="safe_autodiagnosis_handed_to_human")
                self.audit.record("safe_autodiagnosis_stopped", {"reason": "human_approval_required", "command": proposal.command}, run.id)
                self._event(run.id, "safe_autodiagnosis_stopped", {"reason": "human_approval_required"})
                return self.state(run.id)

            assert proposal.tool is not None
            try:
                diagnostic = self.diagnostic_toolbox.run(self._customer_system(run).system, proposal.tool, proposal.arguments)
            except (SafetyError, ValidationError) as exc:
                self.audit.record("agent_diagnostic_blocked", {"tool": proposal.tool, "arguments": proposal.arguments, "reason": exc.message}, run.id)
                self._event(run.id, "agent_diagnostic_blocked", {"tool": proposal.tool, "reason": exc.message})
                self.audit.record("safe_autodiagnosis_stopped", {"reason": "diagnostic_blocked"}, run.id)
                return self.state(run.id)

            self.audit.record("agent_diagnostic_allowed", {"tool": proposal.tool, "rule_id": diagnostic.rule_id, "command": diagnostic.command}, run.id)
            action = self.repo.add_action(
                run,
                command=diagnostic.command,
                classification=CommandClassification.READ_ONLY,
                intent=proposal.intent,
                risk_reason=f"Auto-diagnostic allowlist rule {diagnostic.rule_id}: {diagnostic.reason}",
                expected_signal=proposal.expected_signal,
                typed_confirmation_status=ConfirmationStatus.NOT_REQUIRED,
            )
            self.repo.update_action_status(action, ActionStatus.COMPLETED if diagnostic.exit_code == 0 and not diagnostic.timed_out else ActionStatus.FAILED)
            self.repo.add_command_result(action, diagnostic.command, diagnostic.exit_code, diagnostic.stdout, diagnostic.stderr, diagnostic.timed_out)
            self.repo.set_current_action(run, None)
            self.repo.update_run_status(run, RunStatus.DIAGNOSING)
            self.audit.record(
                "agent_diagnostic_result",
                {
                    "tool": diagnostic.tool,
                    "rule_id": diagnostic.rule_id,
                    "command": diagnostic.command,
                    "exit_code": diagnostic.exit_code,
                    "timed_out": diagnostic.timed_out,
                    "stdout": diagnostic.stdout,
                    "stderr": diagnostic.stderr,
                },
                run.id,
            )
            self._event(run.id, "agent_diagnostic_result", {"tool": diagnostic.tool, "rule_id": diagnostic.rule_id, "exit_code": diagnostic.exit_code})

        self.audit.record("agent_diagnostic_limit_reached", {"max_steps": MAX_AUTO_DIAGNOSTIC_STEPS}, run_id)
        self._event(run_id, "agent_diagnostic_limit_reached", {"max_steps": MAX_AUTO_DIAGNOSTIC_STEPS})
        return self.state(run_id)

    def request_safer_alternative(self, run_id: str, action_id: int | None = None) -> RunStateRead:
        run = self._run(run_id)
        self._require_ssh_confirmed(run)
        blocked_action = self._action(run, action_id)
        if blocked_action.status != ActionStatus.BLOCKED.value:
            raise ValidationError("Safer alternative requires a blocked action")
        snapshot = self._snapshot(run)
        observations = self._observations(run.id)
        planner = self.planner or Planner()
        proposal = planner.propose_next_command(
            ticket=snapshot.get("ticket", {}),
            customer_system=snapshot.get("customer_system", {}),
            observations=observations
            + [
                {
                    "blocked_command": blocked_action.command,
                    "block_reason": blocked_action.risk_reason or "Blocked by safety policy",
                    "request": "Propose one safer alternative command that avoids the blocked behavior. Do not execute anything.",
                }
            ],
            safety_policy=SAFETY_POLICY_SUMMARY,
            related_ticket=snapshot.get("related_ticket"),
            run_id=run.id,
        )
        safety = classify_command(proposal.command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        write_preview = self._write_preview(run, proposal.command, safety)
        action = self.repo.add_action(
            run,
            command=proposal.command,
            classification=safety.classification,
            intent=proposal.intent,
            risk_reason=safety.reason,
            expected_signal=proposal.expected_signal,
            write_preview=write_preview,
            typed_confirmation_status=typed_status,
        )
        self.audit.record(
            "safer_alternative_requested",
            {"blocked_action_id": blocked_action.id, "blocked_command": blocked_action.command, "reason": blocked_action.risk_reason},
            run.id,
        )
        self.audit.record("command_classified", {"command": proposal.command, "classification": safety.classification.value, "reason": safety.reason}, run.id)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"action_id": action.id, "command": proposal.command, "reason": safety.reason}, run.id)
            self._event(run.id, "command_blocked", {"action_id": action.id, "reason": safety.reason})
        else:
            self.audit.record("safer_alternative_proposed", {"action_id": action.id, "command": proposal.command, "intent": proposal.intent}, run.id)
            self._event(run.id, "safer_alternative_proposed", {"action_id": action.id, "classification": safety.classification.value, "write_preview": write_preview})
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
        write_preview = self._write_preview(run, command, safety)
        self.repo.update_action_command(action, command, safety.classification, safety.reason, typed_status, intent=intent, write_preview=write_preview)
        self.audit.record("edited_command", {"action_id": action.id, "command": command}, run.id)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"action_id": action.id, "command": command, "reason": safety.reason}, run.id)
        self._event(run.id, "command_edited", {"action_id": action.id, "classification": safety.classification.value, "blocked": safety.blocked, "write_preview": write_preview})
        return self.state(run.id)

    def retry(self, run_id: str, action_id: int | None = None) -> RunStateRead:
        run = self._run(run_id)
        previous = self._action(run, action_id)
        safety = classify_command(previous.command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        write_preview = self._write_preview(run, previous.command, safety)
        action = self.repo.add_action(
            run,
            previous.command,
            safety.classification,
            previous.intent,
            safety.reason,
            previous.expected_signal,
            write_preview=write_preview,
            typed_confirmation_status=typed_status,
        )
        self.audit.record("retry", {"previous_action_id": previous.id, "action_id": action.id, "command": action.command}, run.id)
        self._event(run.id, "command_retry_proposed", {"action_id": action.id, "write_preview": write_preview})
        return self.state(run.id)

    def confirm_validation(self, run_id: str, evidence: str) -> RunStateRead:
        run = self._run(run_id)
        if not self._is_concrete_validation_evidence(evidence):
            raise ValidationError("Validation confirmation requires concrete evidence")
        successful_results = [result for result in self.repo.list_command_results(run.id) if result.exit_code == 0 and not result.timed_out]
        validation_results = [result for result in successful_results if self._result_is_validation_evidence(result)]
        if not validation_results:
            raise ValidationError("Validation requires at least one successful validation command result as evidence")
        self.repo.set_validation_status(run, ValidationStatus.HUMAN_CONFIRMED, confirmed=True)
        self.repo.update_run_status(run, RunStatus.READY_FOR_ACTIVITY)
        self.audit.record("validation_evidence", {"evidence": evidence, "result_count": len(validation_results)}, run.id)
        self.audit.record("human_validation_confirmation", {"confirmed": True}, run.id)
        self._event(run.id, "validation_confirmed", {"status": RunStatus.READY_FOR_ACTIVITY.value})
        return self.state(run.id)

    def abort(self, run_id: str) -> RunStateRead:
        run = self._run(run_id)
        self.repo.update_run_status(run, RunStatus.ABORTED)
        terminal_manager.close_run_sync(run.id, "run_aborted")
        self.audit.record("abort", {"ticket_id": run.ticket_id}, run.id)
        self._event(run.id, "run_aborted", {"status": RunStatus.ABORTED.value})
        return self.state(run.id)

    def generate_activity_draft(self, run_id: str) -> ActivityDraftRead:
        run = self._run(run_id)
        self._require_ready_for_activity(run)
        snapshot = self._snapshot(run)
        actions = [self._action_payload(action) for action in self.repo.list_actions(run.id)]
        terminal_commands = [self._terminal_command_payload(command) for command in self.repo.list_terminal_commands(run.id)]
        command_results = [self._command_result_payload(result) for result in self.repo.list_command_results(run.id)]
        validation_events = [event.payload for event in self.audit.for_run(run.id) if event.type in {"validation_evidence", "human_validation_confirmation"}]
        activity_generator = self.activity_generator or ActivityGenerator()
        self.audit.record("agent_phase_selected", {"phase": "final_analysis", "observation_count": len(command_results)}, run.id)
        self._event(run.id, "agent_phase_selected", {"phase": "final_analysis"})
        generated = activity_generator.generate(
            ticket=snapshot.get("ticket", {}),
            customer_system=snapshot.get("customer_system", {}),
            actions=actions + terminal_commands,
            command_results=command_results + terminal_commands,
            validation={"status": run.validation_status, "confirmed": run.validation_confirmed, "events": validation_events},
            run_id=run.id,
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
        self._create_completed_ticket_memory(run, draft)
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
            related_ticket=self._related_ticket_read(run),
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
        observations = []
        for result in results:
            action = self.repo.get_action(result.action_id)
            source = "auto_diagnostic" if action and (action.risk_reason or "").startswith("Auto-diagnostic allowlist rule") else "approved_command"
            observations.append(
                redact_payload(
                    {
                        "source": source,
                        "command": result.command,
                        "intent": action.intent if action else None,
                        "classification": action.command_classification if action else None,
                        "exit_code": result.exit_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "timed_out": result.timed_out,
                    }
                )
            )
        return observations

    def _select_agent_phase(self, run: Run, observations: list[dict[str, Any]]) -> str:
        results = self.repo.list_command_results(run.id)
        if not results:
            return "diagnosis"

        latest = results[-1]
        latest_action = self.repo.get_action(latest.action_id)
        latest_failed = latest.timed_out or latest.exit_code != 0
        latest_was_validation = self._result_is_validation_evidence(latest)
        if latest_failed and latest_was_validation:
            return "diagnosis"

        if latest_action and latest_action.command_classification in {CommandClassification.MUTATING.value, CommandClassification.RISKY_MUTATING.value}:
            if not latest_failed:
                return "verification"
            return "diagnosis"

        if latest_was_validation:
            return "verification" if not latest_failed else "diagnosis"

        return "diagnosis"

    def _auto_diagnostic_count(self, run_id: str) -> int:
        return sum(1 for observation in self._observations(run_id) if observation.get("source") == "auto_diagnostic")

    def _add_proposed_action(self, run: Run, proposal: CommandProposal, event_type: str = "command_proposed") -> Action:
        safety = classify_command(proposal.command)
        typed_status = ConfirmationStatus.PENDING if safety.requires_typed_confirmation else ConfirmationStatus.NOT_REQUIRED
        write_preview = self._write_preview(run, proposal.command, safety)
        action = self.repo.add_action(
            run,
            command=proposal.command,
            classification=safety.classification,
            intent=proposal.intent,
            risk_reason=safety.reason,
            expected_signal=proposal.expected_signal,
            write_preview=write_preview,
            typed_confirmation_status=typed_status,
        )
        self.audit.record("command_classified", {"command": proposal.command, "classification": safety.classification.value, "reason": safety.reason}, run.id)
        if safety.blocked:
            self.repo.update_action_status(action, ActionStatus.BLOCKED)
            self.audit.record("blocked_command", {"command": proposal.command, "reason": safety.reason}, run.id)
            self._event(run.id, "command_blocked", {"action_id": action.id, "reason": safety.reason})
        else:
            self.audit.record(event_type, {"action_id": action.id, "command": proposal.command, "intent": proposal.intent}, run.id)
            self._event(run.id, event_type, {"action_id": action.id, "command": proposal.command, "classification": safety.classification.value, "write_preview": write_preview})
        return action

    def _write_preview(self, run: Run, command: str, safety) -> dict[str, Any] | None:
        if safety.blocked:
            return None
        previewer = self.write_previewer or WritePreviewer(self.ssh_runner, self.repo.secrets)
        return previewer.preview(self._customer_system(run).system, command)

    def _is_concrete_validation_evidence(self, evidence: str) -> bool:
        text = evidence.strip().lower()
        if len(text) < 12:
            return False
        concrete_terms = ("http", "200", "ok", "active", "running", "respond", "success", "passed", "reachable", "restored", "validated")
        return any(term in text for term in concrete_terms)

    def _result_is_validation_evidence(self, result) -> bool:
        action = self.repo.get_action(result.action_id)
        if action is None:
            return False
        action_text = " ".join(filter(None, [action.intent, action.expected_signal])).lower()
        command_text = " ".join(filter(None, [action.command, result.command])).lower()
        if any(term in action_text for term in ("validat", "verify", "confirm", "test", "respond", "restored", "customer benefit")):
            return True
        return any(term in command_text for term in ("curl", "health", "is-active", "smoke", "wget --spider"))

    def _ticket_validation_proposal(self, snapshot: dict[str, Any], observations: list[dict[str, Any]]) -> CommandProposal | None:
        ticket = snapshot.get("ticket", {})
        description = " ".join(str(ticket.get(field, "")) for field in ("title", "description"))
        health_url = self._extract_health_url(description)
        health_command = f"curl --max-time 5 -fsS {health_url}" if health_url else None
        validation_command = self._extract_ticket_validation_command(description)

        if health_command and not self._command_was_observed(observations, health_command):
            return CommandProposal(
                intent="Run the ticket-specified customer-facing health check before deeper diagnostics or changes.",
                command=health_command,
                expected_signal="The command exits 0 and returns the expected health payload, such as ok; failure means the incident is still active and needs diagnosis.",
                risk_level="low",
                command_class_hint=CommandClassification.READ_ONLY,
                phase="validate",
                evidence_basis="ticket provides an explicit local health endpoint",
                evidence_gap="whether the customer-facing status API is currently reachable",
            )

        if (not health_command or self._command_succeeded(observations, health_command)) and validation_command:
            if validation_command and not self._command_was_observed(observations, validation_command):
                return CommandProposal(
                    intent="Run the ticket-provided validation command after the available ticket-directed checks indicate it is the next required proof.",
                    command=validation_command,
                    expected_signal="The command exits 0 and reports that the ticket-required service or capability is healthy.",
                    risk_level="medium",
                    command_class_hint=CommandClassification.RISKY_MUTATING,
                    rollback_note="No rollback is expected because this is the ticket-provided validation command, not a repair command.",
                    phase="validate",
                    evidence_basis="direct health endpoint validation succeeded" if health_command else "ticket provides an explicit validation command",
                    evidence_gap="whether the ticket's required validation passes",
                )

        return None

    def _extract_health_url(self, text: str) -> str | None:
        match = re.search(r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?/[^\s)`,]*health[^\s)`,]*", text, flags=re.IGNORECASE)
        return match.group(0).rstrip(".,") if match else None

    def _extract_ticket_validation_command(self, text: str) -> str | None:
        lines = text.splitlines()
        for index, raw_line in enumerate(lines):
            line = raw_line.strip().lower()
            if "validation" not in line and line != "run:":
                continue
            for candidate_line in lines[index + 1 : index + 5]:
                command = self._normalize_ticket_command(candidate_line.strip())
                if command:
                    return command
        return None

    def _normalize_ticket_command(self, line: str) -> str | None:
        command = line.strip().strip("`").strip()
        if not command or command.startswith("#"):
            return None
        if command.startswith(("- ", "* ")):
            command = command[2:].strip()
        if command.startswith("sudo ") and not command.startswith("sudo -n "):
            command = "sudo -n " + command.removeprefix("sudo ").strip()
        if self._is_simple_ticket_validation_command(command):
            return command
        return None

    def _is_simple_ticket_validation_command(self, command: str) -> bool:
        if any(operator in command for operator in ("&&", "||", ";", "|", "$", "`", "\n")):
            return False
        allowed_prefixes = (
            "curl ",
            "wget --spider ",
            "systemctl is-active ",
            "sudo -n systemctl is-active ",
            "sudo -n /",
            "/",
        )
        return command.startswith(allowed_prefixes)

    def _command_was_observed(self, observations: list[dict[str, Any]], command: str) -> bool:
        return any(observation.get("command") == command for observation in observations)

    def _command_succeeded(self, observations: list[dict[str, Any]], command: str) -> bool:
        return any(observation.get("command") == command and observation.get("exit_code") == 0 and not observation.get("timed_out") for observation in observations)

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

    def _prepare_related_ticket(self, ticket) -> RelatedTicketContext | None:
        try:
            service = self.ticket_memory_service or TicketMemoryService(self.session)
            context = service.prepare_ticket_relation(ticket)
            if service.last_candidate_payloads:
                self.audit.record("related_ticket_candidates_found", {"ticket_id": ticket.id, "candidates": service.last_candidate_payloads})
            if service.last_decision_payload is not None:
                self.audit.record("related_ticket_decision", service.last_decision_payload)
            return context
        except Exception as exc:
            self.audit.record("related_ticket_lookup_failed", {"ticket_id": ticket.id, "error": redact_text(str(exc))})
            return None

    def _create_completed_ticket_memory(self, run: Run, draft: ActivityDraft) -> None:
        snapshot = self._snapshot(run)
        ticket = snapshot.get("ticket") or {}
        if not ticket:
            return
        try:
            service = self.ticket_memory_service or TicketMemoryService(self.session)
            commands = self._completed_memory_commands(run.id)
            service.create_completed_memory(ticket, draft, commands)
            self.audit.record("ticket_memory_created", {"ticket_id": run.ticket_id, "command_count": len(commands)}, run.id)
        except Exception as exc:
            self.audit.record("ticket_memory_create_failed", {"ticket_id": run.ticket_id, "error": redact_text(str(exc))}, run.id)

    def _completed_memory_commands(self, run_id: str) -> list[str]:
        commands: list[str] = []
        for result in self.repo.list_command_results(run_id):
            if result.command.strip():
                commands.append(result.command)
        for command in self.repo.list_terminal_commands(run_id):
            if command.exit_code is None:
                continue
            selected = command.final_command or command.original_command
            if selected.strip():
                commands.append(selected)
        sanitized: list[str] = []
        seen = set()
        for command in commands:
            redacted = redact_payload(command, self.repo.secrets)
            if redacted not in seen:
                seen.add(redacted)
                sanitized.append(redacted)
        return sanitized

    def _related_ticket_read(self, run: Run) -> RelatedTicketRead | None:
        related = self._snapshot(run).get("related_ticket")
        if not related:
            return None
        return RelatedTicketRead(
            ticket_id=related["ticket_id"],
            title=related.get("title", ""),
            description=related.get("description", ""),
            rationale=related.get("rationale"),
            confidence=related.get("confidence"),
        )

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
                "write_preview": action.write_preview,
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

    def _terminal_command_payload(self, command) -> dict[str, Any]:
        return redact_payload(
            {
                "id": command.id,
                "source": command.source,
                "status": command.status,
                "command": command.final_command or command.original_command,
                "original_command": command.original_command,
                "edited_from": command.edited_from,
                "edited_to": command.edited_to,
                "classification": command.classification,
                "risk_reason": command.risk_reason,
                "write_preview": command.write_preview,
                "exit_code": command.exit_code,
                "output": command.output,
            }
        )

    def _event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        persist_and_publish_ws_event_sync(run_id, event_type, payload)
