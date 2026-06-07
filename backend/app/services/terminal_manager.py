import asyncio
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session

from app.agent.planner import SAFETY_POLICY_SUMMARY, Planner
from app.core.config import get_settings
from app.core.errors import SafetyError, ValidationError
from app.core.redaction import redact_payload, redact_text
from app.db.session import engine
from app.db.models import TerminalCommand
from app.repositories.runs import RunRepository
from app.schemas.phoenix import CustomerSystem
from app.schemas.runs import RunStatus, TerminalCommandSource, TerminalCommandStatus, ValidationStatus
from app.services.audit_log import AuditLog
from app.services.events import persist_and_publish_ws_event_sync
from app.services.terminal_safety import TerminalSafetyReviewer
from app.services.terminal_session import SshPtySession, monotonic_seconds
from app.services.ssh_runner import SshRunner
from app.services.write_preview import WritePreviewer


IDLE_TIMEOUT_SECONDS = 15 * 60
COMMAND_TIMEOUT_SECONDS = 30
EXIT_MARKER_RE = re.compile(r"__NOFLOW_EXIT:(\d+):(-?\d+)__")
SECRET_PROMPT_RE = re.compile(r"(?i)(password|passphrase|token|secret|api\s*key|private\s*key|sudo password)\s*:")
NONINTERACTIVE_ENV = "SYSTEMD_PAGER=cat SYSTEMD_COLORS=0 PAGER=cat LESS=FRXMK"


@dataclass
class PendingCommand:
    command_id: int
    phase: str | None = None
    output: str = ""
    started_at: float = field(default_factory=monotonic_seconds)


@dataclass
class TerminalRuntime:
    run_id: str
    db_session_id: int
    pty: SshPtySession
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    input_buffer: str = ""
    pending_confirmation: int | None = None
    pending_commands: dict[int, PendingCommand] = field(default_factory=dict)
    agent_active: bool = False
    agent_workflow_phase: str = "diagnosis"
    current_agent_phase: str | None = None
    waiting_after_rejection: bool = False
    last_activity: float = field(default_factory=monotonic_seconds)
    secret_input_mode: bool = False
    reader_task: asyncio.Task | None = None
    closing: bool = False


class TerminalManager:
    def __init__(
        self,
        pty_factory=None,
        safety_reviewer: TerminalSafetyReviewer | None = None,
        planner: Planner | None = None,
        write_previewer: WritePreviewer | None = None,
        command_timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
    ):
        self._runtimes: dict[str, TerminalRuntime] = {}
        self.pty_factory = pty_factory or SshPtySession
        self.safety_reviewer = safety_reviewer or TerminalSafetyReviewer()
        self.planner = planner
        self.write_previewer = write_previewer
        self.command_timeout_seconds = command_timeout_seconds

    async def connect(self, run_id: str, cols: int = 120, rows: int = 32) -> tuple[TerminalRuntime, asyncio.Queue[dict[str, Any]]]:
        runtime = await self._runtime(run_id, cols, rows)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        runtime.subscribers.add(queue)
        runtime.last_activity = monotonic_seconds()
        await queue.put({"type": "terminal_opened", "session_id": runtime.db_session_id, "run_id": run_id})
        if runtime.current_agent_phase:
            await queue.put({"type": "agent_phase_selected", "phase": runtime.current_agent_phase})
        self._audit(run_id, "terminal_reconnected" if len(runtime.subscribers) > 1 else "terminal_connected", {"terminal_session_id": runtime.db_session_id})
        return runtime, queue

    def disconnect(self, runtime: TerminalRuntime, queue: asyncio.Queue[dict[str, Any]]) -> None:
        runtime.subscribers.discard(queue)
        runtime.last_activity = monotonic_seconds()
        self._audit(runtime.run_id, "terminal_disconnected", {"terminal_session_id": runtime.db_session_id})

    async def handle_message(self, runtime: TerminalRuntime, message: dict[str, Any]) -> None:
        runtime.last_activity = monotonic_seconds()
        message_type = message.get("type")
        if message_type == "input":
            await self._handle_input(runtime, str(message.get("data") or ""))
        elif message_type == "resize":
            cols = int(message.get("cols") or 120)
            rows = int(message.get("rows") or 32)
            await asyncio.to_thread(runtime.pty.resize, cols, rows)
        elif message_type == "manual_confirm":
            await self._confirm_manual(runtime, int(message.get("command_id")))
        elif message_type == "manual_cancel":
            await self._cancel_command(runtime, int(message.get("command_id")), TerminalCommandSource.MANUAL)
        elif message_type == "agent_start":
            if await self._agent_is_waiting_on_existing_work(runtime):
                return
            runtime.agent_active = True
            runtime.agent_workflow_phase = "diagnosis"
            runtime.waiting_after_rejection = False
            self._audit(runtime.run_id, "agent_mode_started", {})
            await self._safe_propose_agent(runtime)
        elif message_type == "agent_next":
            if await self._agent_is_waiting_on_existing_work(runtime):
                return
            runtime.agent_active = True
            runtime.waiting_after_rejection = False
            await self._safe_propose_agent(runtime)
        elif message_type == "agent_accept":
            await self._accept_agent(runtime, int(message.get("command_id")))
        elif message_type == "agent_reject":
            await self._reject_agent(runtime, int(message.get("command_id")), str(message.get("reason") or ""))
        elif message_type == "agent_edit":
            await self._edit_agent(runtime, int(message.get("command_id")), str(message.get("command") or ""))
        elif message_type == "agent_message":
            await self._record_agent_guidance(runtime, str(message.get("message") or ""))
        elif message_type == "agent_cancel":
            runtime.agent_active = False
            runtime.waiting_after_rejection = False
            self._audit(runtime.run_id, "agent_mode_cancelled", {})
            await self._broadcast(runtime, {"type": "agent_cancelled"})
        else:
            await self._broadcast(runtime, {"type": "error", "message": f"Unsupported terminal message type: {message_type}"})

    async def close_run(self, run_id: str, reason: str = "run_closed") -> None:
        runtime = self._runtimes.get(run_id)
        if runtime is None:
            return
        await self._close_runtime(runtime, reason)

    def close_run_sync(self, run_id: str, reason: str = "run_closed") -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.close_run(run_id, reason))
        else:
            loop.create_task(self.close_run(run_id, reason))

    async def announce_completion(self, run_id: str, message: str, ascii_art: str) -> None:
        runtime = self._runtimes.get(run_id)
        if runtime is None or runtime.closing:
            return
        data = f"\r\n\x1b[32m{ascii_art}\x1b[0m\r\n\x1b[32m{message}\x1b[0m\r\n"
        await self._broadcast(runtime, {"type": "terminal_output", "data": data})

    def announce_completion_sync(self, run_id: str, message: str, ascii_art: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.announce_completion(run_id, message, ascii_art))
        else:
            loop.create_task(self.announce_completion(run_id, message, ascii_art))

    def logs(self, run_id: str) -> list[TerminalCommand]:
        with Session(engine) as session:
            return RunRepository(session).list_terminal_commands(run_id)

    async def _runtime(self, run_id: str, cols: int, rows: int) -> TerminalRuntime:
        runtime = self._runtimes.get(run_id)
        if runtime is not None and not runtime.closing:
            if await asyncio.to_thread(runtime.pty.is_closed):
                await self._close_runtime(runtime, "ssh_closed")
            else:
                await asyncio.to_thread(runtime.pty.resize, cols, rows)
                return runtime

        with Session(engine) as session:
            repo = RunRepository(session)
            run = repo.get_run(run_id)
            if run is None:
                raise ValidationError("Run was not found")
            if not run.ssh_confirmed:
                raise ValidationError("Technician must confirm SSH connection before opening terminal")
            if run.status in {RunStatus.SUBMITTED.value, RunStatus.ABORTED.value, RunStatus.FAILED.value}:
                raise ValidationError("Terminal cannot be opened for a closed run")
            customer_system = CustomerSystem.model_validate((run.customer_system_snapshot or {}).get("customer_system"))

        pty = self.pty_factory(customer_system.system, cols=cols, rows=rows)
        await asyncio.to_thread(pty.open)

        with Session(engine) as session:
            repo = RunRepository(session)
            db_terminal_session = repo.get_open_terminal_session(run_id) or repo.create_terminal_session(run_id)
            db_terminal_session_id = db_terminal_session.id

        runtime = TerminalRuntime(run_id=run_id, db_session_id=db_terminal_session_id, pty=pty)
        runtime.reader_task = asyncio.create_task(self._reader(runtime))
        self._runtimes[run_id] = runtime
        self._audit(run_id, "terminal_opened", {"terminal_session_id": db_terminal_session_id})
        persist_and_publish_ws_event_sync(run_id, "terminal_opened", {"terminal_session_id": db_terminal_session_id})
        return runtime

    async def _handle_input(self, runtime: TerminalRuntime, data: str) -> None:
        if runtime.secret_input_mode:
            await asyncio.to_thread(runtime.pty.write, data)
            if "\n" in data or "\r" in data:
                runtime.secret_input_mode = False
            return
        if runtime.pending_commands:
            self._audit(runtime.run_id, "terminal_input_ignored_during_command", {"pending_command_ids": sorted(runtime.pending_commands)})
            return
        for char in data:
            if char in {"\r", "\n"}:
                command = runtime.input_buffer.strip()
                runtime.input_buffer = ""
                await self._broadcast(runtime, {"type": "terminal_output", "data": "\r\n"})
                if command:
                    if runtime.waiting_after_rejection:
                        await self._record_agent_guidance(runtime, command)
                        continue
                    if runtime.agent_active:
                        self._audit(runtime.run_id, "manual_intervention_during_agent", {"command": command})
                    await self._submit_manual(runtime, command)
            elif char in {"\b", "\x7f"}:
                runtime.input_buffer = runtime.input_buffer[:-1]
                await self._broadcast(runtime, {"type": "terminal_output", "data": "\b \b"})
            else:
                runtime.input_buffer += char
                await self._broadcast(runtime, {"type": "terminal_output", "data": char})

    async def _submit_manual(self, runtime: TerminalRuntime, command: str) -> None:
        final_command = _make_command_non_interactive(command)
        safety = self.safety_reviewer.review(final_command, self._context(runtime.run_id))
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.add_terminal_command(
                runtime.run_id,
                TerminalCommandSource.MANUAL,
                command,
                terminal_session_id=runtime.db_session_id,
                final_command=final_command,
                classification=safety.classification,
                risk_reason=safety.reason,
            )
            self._audit(runtime.run_id, "manual_command_submitted", {"command_id": terminal_command.id, "command": final_command, "original_command": command})
            self._audit(
                runtime.run_id,
                "manual_command_classified",
                {"command_id": terminal_command.id, "classification": safety.classification.value, "reason": safety.reason, "semantic_used": safety.semantic_used},
            )
            if safety.decision == "block":
                repo.update_terminal_command(terminal_command, TerminalCommandStatus.BLOCKED, risk_reason=safety.reason, ended=True)
                self._audit(runtime.run_id, "manual_command_blocked", {"command_id": terminal_command.id, "reason": safety.reason})
                await self._broadcast(runtime, {"type": "command_blocked", "command_id": terminal_command.id, "reason": safety.reason})
                return
            if safety.decision == "confirm":
                repo.update_terminal_command(terminal_command, TerminalCommandStatus.CONFIRMATION_REQUIRED, risk_reason=safety.reason)
                runtime.pending_confirmation = terminal_command.id
                self._audit(runtime.run_id, "manual_command_confirmation_required", {"command_id": terminal_command.id, "reason": safety.reason})
                await self._broadcast(runtime, {"type": "confirmation_required", "command_id": terminal_command.id, "command": final_command, "reason": safety.reason})
                return
            command_id = terminal_command.id
        await self._execute(runtime, command_id, final_command, TerminalCommandSource.MANUAL)

    async def _confirm_manual(self, runtime: TerminalRuntime, command_id: int) -> None:
        if runtime.pending_confirmation != command_id:
            raise ValidationError("No matching manual command is awaiting confirmation")
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is None or terminal_command.run_id != runtime.run_id:
                raise ValidationError("Terminal command was not found")
            runtime.pending_confirmation = None
            repo.update_terminal_command(terminal_command, TerminalCommandStatus.ACCEPTED)
            self._audit(runtime.run_id, "manual_command_confirmed", {"command_id": command_id})
            command = terminal_command.final_command or terminal_command.original_command
        await self._execute(runtime, command_id, command, TerminalCommandSource.MANUAL)

    async def _cancel_command(self, runtime: TerminalRuntime, command_id: int, source: TerminalCommandSource) -> None:
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is None or terminal_command.run_id != runtime.run_id:
                raise ValidationError("Terminal command was not found")
            repo.update_terminal_command(terminal_command, TerminalCommandStatus.CANCELLED, ended=True)
        if source == TerminalCommandSource.MANUAL:
            runtime.pending_confirmation = None
            self._audit(runtime.run_id, "manual_command_cancelled", {"command_id": command_id})
        await self._broadcast(runtime, {"type": "command_cancelled", "command_id": command_id})

    async def _propose_agent(self, runtime: TerminalRuntime, forced_phase: str | None = None) -> None:
        planner = self.planner or Planner()
        context = self._context(runtime.run_id)
        selected_phase = _workflow_phase(forced_phase or runtime.agent_workflow_phase)
        runtime.agent_workflow_phase = selected_phase
        proposal = await asyncio.to_thread(
            self._propose_for_phase,
            planner,
            selected_phase,
            context.get("ticket", {}),
            context.get("customer_system", {}),
            context.get("observations", []),
            SAFETY_POLICY_SUMMARY,
            context.get("related_ticket"),
            runtime.run_id,
        )
        command = _make_command_non_interactive(proposal.command)
        phase = _agent_phase(proposal.phase or selected_phase)
        runtime.agent_workflow_phase = _workflow_phase(phase)
        runtime.current_agent_phase = phase
        self._audit(runtime.run_id, "agent_phase_selected", {"phase": phase, "routed_phase": selected_phase})
        await self._broadcast(runtime, {"type": "agent_phase_selected", "phase": phase})
        safety = self.safety_reviewer.review(command, context)
        status = TerminalCommandStatus.BLOCKED if safety.decision == "block" else TerminalCommandStatus.SUBMITTED
        write_preview = None if safety.decision == "block" else self._write_preview(runtime.run_id, command)
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.add_terminal_command(
                runtime.run_id,
                TerminalCommandSource.AGENT,
                proposal.command,
                terminal_session_id=runtime.db_session_id,
                final_command=command,
                status=status,
                classification=safety.classification,
                risk_reason=safety.reason,
                write_preview=write_preview,
            )
        self._audit(runtime.run_id, "agent_command_proposed", {"command_id": terminal_command.id, "command": command, "original_command": proposal.command, "intent": proposal.intent, "phase": phase})
        if safety.decision == "block":
            self._audit(runtime.run_id, "agent_command_blocked", {"command_id": terminal_command.id, "reason": safety.reason})
            await self._broadcast(runtime, {"type": "command_blocked", "command_id": terminal_command.id, "reason": safety.reason})
        else:
            await self._broadcast(
                runtime,
                {
                    "type": "agent_proposal",
                    "command_id": terminal_command.id,
                    "command": command,
                    "intent": proposal.intent,
                    "phase": phase,
                    "classification": safety.classification.value,
                    "reason": safety.reason,
                    "write_preview": write_preview,
                },
            )

    def _propose_for_phase(
        self,
        planner: Planner,
        phase: str,
        ticket: dict[str, Any],
        customer_system: dict[str, Any],
        observations: list[dict[str, Any]],
        safety_policy: str,
        related_ticket: dict[str, Any] | None,
        run_id: str,
    ):
        if phase == "verification" and hasattr(planner, "propose_verification_command"):
            return planner.propose_verification_command(
                ticket=ticket,
                customer_system=customer_system,
                observations=observations,
                safety_policy=safety_policy,
                related_ticket=related_ticket,
                run_id=run_id,
            )
        if phase == "execution" and hasattr(planner, "propose_execution_command"):
            return planner.propose_execution_command(
                ticket=ticket,
                customer_system=customer_system,
                observations=observations,
                safety_policy=safety_policy,
                related_ticket=related_ticket,
                run_id=run_id,
            )
        if hasattr(planner, "propose_diagnosis_command"):
            return planner.propose_diagnosis_command(
                ticket=ticket,
                customer_system=customer_system,
                observations=observations,
                safety_policy=safety_policy,
                related_ticket=related_ticket,
                run_id=run_id,
            )
        return planner.propose_next_command(
            ticket=ticket,
            customer_system=customer_system,
            observations=observations,
            safety_policy=safety_policy,
            related_ticket=related_ticket,
            run_id=run_id,
        )

    async def _record_agent_guidance(self, runtime: TerminalRuntime, guidance: str) -> None:
        guidance = guidance.strip()
        if not guidance:
            return
        runtime.agent_active = True
        runtime.waiting_after_rejection = False
        self._audit(runtime.run_id, "agent_guidance_received", {"message": guidance})
        await self._broadcast(runtime, {"type": "agent_guidance_recorded"})
        await self._safe_propose_agent(runtime)

    async def _safe_propose_agent(self, runtime: TerminalRuntime, forced_phase: str | None = None) -> None:
        try:
            await self._propose_agent(runtime, forced_phase=forced_phase)
        except Exception as exc:
            runtime.agent_active = False
            runtime.waiting_after_rejection = False
            message = redact_text(str(exc), get_settings().configured_secrets())
            self._audit(runtime.run_id, "agent_proposal_failed", {"error": message})
            await self._broadcast(runtime, {"type": "error", "message": f"Agent could not propose the next command: {message}"})

    async def _agent_is_waiting_on_existing_work(self, runtime: TerminalRuntime) -> bool:
        if runtime.pending_commands:
            await self._broadcast(runtime, {"type": "status", "message": "A command is still running. Wait for completion or timeout before requesting another agent action."})
            return True
        if self._has_pending_agent_proposal(runtime.run_id):
            await self._broadcast(runtime, {"type": "status", "message": "Review the current agent proposal before requesting another action."})
            return True
        return False

    def _has_pending_agent_proposal(self, run_id: str) -> bool:
        with Session(engine) as session:
            repo = RunRepository(session)
            return any(
                command.source == TerminalCommandSource.AGENT.value
                and command.status in {TerminalCommandStatus.SUBMITTED.value, TerminalCommandStatus.EDITED.value}
                for command in repo.list_terminal_commands(run_id)
            )

    async def _accept_agent(self, runtime: TerminalRuntime, command_id: int) -> None:
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is None or terminal_command.run_id != runtime.run_id or terminal_command.source != TerminalCommandSource.AGENT.value:
                raise ValidationError("Agent command was not found")
            if terminal_command.status == TerminalCommandStatus.BLOCKED.value:
                raise SafetyError("Blocked agent command cannot be accepted")
            repo.update_terminal_command(terminal_command, TerminalCommandStatus.ACCEPTED)
            command = terminal_command.final_command or terminal_command.original_command
        self._audit(runtime.run_id, "agent_command_accepted", {"command_id": command_id, "command": command})
        await self._execute(runtime, command_id, command, TerminalCommandSource.AGENT)

    async def _reject_agent(self, runtime: TerminalRuntime, command_id: int, reason: str) -> None:
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is None or terminal_command.run_id != runtime.run_id:
                raise ValidationError("Agent command was not found")
            repo.update_terminal_command(terminal_command, TerminalCommandStatus.REJECTED, risk_reason=reason, ended=True)
        runtime.waiting_after_rejection = True
        self._audit(runtime.run_id, "agent_command_rejected", {"command_id": command_id, "reason": reason})
        await self._broadcast(runtime, {"type": "agent_waiting_for_guidance", "command_id": command_id})

    async def _edit_agent(self, runtime: TerminalRuntime, command_id: int, command: str) -> None:
        if not command.strip():
            raise ValidationError("Edited command must not be empty")
        final_command = _make_command_non_interactive(command)
        safety = self.safety_reviewer.review(final_command, self._context(runtime.run_id))
        write_preview = None if safety.decision == "block" else self._write_preview(runtime.run_id, final_command)
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is None or terminal_command.run_id != runtime.run_id:
                raise ValidationError("Agent command was not found")
            repo.update_terminal_command(
                terminal_command,
                TerminalCommandStatus.EDITED if safety.decision != "block" else TerminalCommandStatus.BLOCKED,
                final_command=final_command,
                edited_from=terminal_command.final_command or terminal_command.original_command,
                edited_to=final_command,
                classification=safety.classification,
                risk_reason=safety.reason,
                write_preview=write_preview,
            )
        self._audit(runtime.run_id, "agent_command_edited", {"command_id": command_id, "from": terminal_command.original_command, "to": final_command, "original_edit": command})
        if safety.decision == "block":
            await self._broadcast(runtime, {"type": "command_blocked", "command_id": command_id, "reason": safety.reason})
        else:
            await self._broadcast(runtime, {"type": "agent_proposal", "command_id": command_id, "command": final_command, "phase": runtime.current_agent_phase, "classification": safety.classification.value, "reason": safety.reason, "write_preview": write_preview})

    async def _execute(self, runtime: TerminalRuntime, command_id: int, command: str, source: TerminalCommandSource) -> None:
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is not None:
                repo.update_terminal_command(terminal_command, TerminalCommandStatus.RUNNING, final_command=command, started=True)
        runtime.pending_commands[command_id] = PendingCommand(
            command_id,
            phase=runtime.current_agent_phase if source == TerminalCommandSource.AGENT else None,
        )
        event_prefix = "agent" if source == TerminalCommandSource.AGENT else "manual"
        self._audit(runtime.run_id, f"{event_prefix}_command_running", {"command_id": command_id, "command": command})
        await self._broadcast(runtime, {"type": "command_running", "command_id": command_id})
        runtime.input_buffer = ""
        wrapped = _wrap_command_for_pty(command, command_id)
        await asyncio.to_thread(runtime.pty.write, wrapped)

    async def _reader(self, runtime: TerminalRuntime) -> None:
        try:
            while not runtime.closing:
                if monotonic_seconds() - runtime.last_activity > IDLE_TIMEOUT_SECONDS:
                    await self._close_runtime(runtime, "idle_timeout")
                    return
                data = await asyncio.to_thread(runtime.pty.read_available)
                if data:
                    runtime.last_activity = monotonic_seconds()
                    with Session(engine) as session:
                        RunRepository(session).add_terminal_transcript_event(runtime.run_id, runtime.db_session_id, data)
                    if SECRET_PROMPT_RE.search(data):
                        runtime.secret_input_mode = True
                        self._audit(runtime.run_id, "secret_input_suppressed", {"terminal_session_id": runtime.db_session_id})
                    await self._broadcast(runtime, {"type": "terminal_output", "data": data})
                    await self._capture_output(runtime, data)
                else:
                    await self._timeout_pending_commands(runtime)
                    if runtime.pty.is_closed():
                        await self._close_runtime(runtime, "ssh_closed")
                        return
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

    async def _capture_output(self, runtime: TerminalRuntime, data: str) -> None:
        for pending in list(runtime.pending_commands.values()):
            pending.output += data
        for match in _pending_exit_markers(runtime):
            command_id = int(match.group(1))
            exit_code = int(match.group(2))
            pending = runtime.pending_commands.pop(command_id, None)
            if pending is None:
                continue
            cleaned_output = EXIT_MARKER_RE.sub("", pending.output)
            with Session(engine) as session:
                repo = RunRepository(session)
                terminal_command = repo.get_terminal_command(command_id)
                if terminal_command is None:
                    continue
                status = TerminalCommandStatus.COMPLETED if exit_code == 0 else TerminalCommandStatus.FAILED
                repo.update_terminal_command(terminal_command, status, exit_code=exit_code, output=cleaned_output, ended=True)
                validation_evidence_collected = exit_code == 0 and _terminal_command_is_validation_evidence(
                    terminal_command.final_command or terminal_command.original_command,
                    cleaned_output,
                    pending.phase,
                )
                if validation_evidence_collected:
                    run = repo.get_run(runtime.run_id)
                    if run is not None:
                        repo.set_validation_status(run, ValidationStatus.EVIDENCE_COLLECTED)
                        repo.update_run_status(run, RunStatus.AWAITING_VALIDATION_CONFIRMATION)
                source = TerminalCommandSource(terminal_command.source)
            event_prefix = "agent" if source == TerminalCommandSource.AGENT else "manual"
            self._audit(runtime.run_id, f"{event_prefix}_command_completed", {"command_id": command_id, "exit_code": exit_code})
            await self._broadcast(runtime, {"type": "command_completed", "command_id": command_id, "exit_code": exit_code})
            if validation_evidence_collected:
                runtime.agent_active = False
                payload = {
                    "command_id": command_id,
                    "status": RunStatus.AWAITING_VALIDATION_CONFIRMATION.value,
                    "validation_status": ValidationStatus.EVIDENCE_COLLECTED.value,
                }
                self._audit(runtime.run_id, "validation_evidence_collected", payload)
                await self._broadcast(runtime, {"type": "validation_evidence_collected", **payload})
                await self._broadcast(
                    runtime,
                    {
                        "type": "terminal_output",
                        "data": "\r\n\x1b[32mValidation evidence collected. Agent stopped; confirm validation in the activity workflow to generate the draft.\x1b[0m\r\n",
                    },
                )
                continue
            if source == TerminalCommandSource.AGENT and runtime.agent_active and not runtime.waiting_after_rejection:
                next_phase = _next_workflow_phase_after_command(pending.phase, exit_code)
                runtime.agent_workflow_phase = next_phase
                self._audit(runtime.run_id, "agent_continuing", {"after_command_id": command_id, "next_phase": next_phase})
                message = "Agent is preparing validation evidence..." if next_phase == "verification" else "Agent is preparing the next action..."
                await self._broadcast(runtime, {"type": "status", "message": message})
                await self._safe_propose_agent(runtime, forced_phase=next_phase)

    async def _timeout_pending_commands(self, runtime: TerminalRuntime) -> None:
        now = monotonic_seconds()
        expired = [
            pending
            for pending in list(runtime.pending_commands.values())
            if now - pending.started_at > self.command_timeout_seconds
        ]
        for pending in expired:
            runtime.pending_commands.pop(pending.command_id, None)
            try:
                await asyncio.to_thread(runtime.pty.write, "\x03")
            except Exception:
                pass
            cleaned_output = EXIT_MARKER_RE.sub("", pending.output)
            timeout_message = f"\nCommand timed out after {int(self.command_timeout_seconds)} seconds and was interrupted."
            with Session(engine) as session:
                repo = RunRepository(session)
                terminal_command = repo.get_terminal_command(pending.command_id)
                if terminal_command is None:
                    continue
                repo.update_terminal_command(
                    terminal_command,
                    TerminalCommandStatus.FAILED,
                    exit_code=124,
                    output=f"{cleaned_output}{timeout_message}",
                    ended=True,
                )
                source = TerminalCommandSource(terminal_command.source)
            event_prefix = "agent" if source == TerminalCommandSource.AGENT else "manual"
            self._audit(runtime.run_id, f"{event_prefix}_command_timed_out", {"command_id": pending.command_id, "timeout_seconds": self.command_timeout_seconds})
            await self._broadcast(runtime, {"type": "command_completed", "command_id": pending.command_id, "exit_code": 124})
            if source == TerminalCommandSource.AGENT and runtime.agent_active and not runtime.waiting_after_rejection:
                runtime.agent_workflow_phase = "diagnosis"
                self._audit(runtime.run_id, "agent_continuing", {"after_command_id": pending.command_id, "next_phase": "diagnosis", "reason": "command_timeout"})
                await self._broadcast(runtime, {"type": "status", "message": "Command timed out; agent is returning to diagnosis."})
                await self._safe_propose_agent(runtime, forced_phase="diagnosis")

    async def _close_runtime(self, runtime: TerminalRuntime, reason: str) -> None:
        if runtime.closing:
            return
        runtime.closing = True
        if runtime.reader_task is not None and runtime.reader_task is not asyncio.current_task():
            runtime.reader_task.cancel()
        await self._fail_pending_commands(runtime, reason)
        await asyncio.to_thread(runtime.pty.close)
        with Session(engine) as session:
            repo = RunRepository(session)
            db_terminal_session = repo.get_open_terminal_session(runtime.run_id)
            if db_terminal_session is not None:
                repo.close_terminal_session(db_terminal_session, reason)
        self._audit(runtime.run_id, "terminal_closed", {"terminal_session_id": runtime.db_session_id, "reason": reason})
        await self._broadcast(runtime, {"type": "terminal_closed", "reason": reason})
        self._runtimes.pop(runtime.run_id, None)

    async def _fail_pending_commands(self, runtime: TerminalRuntime, reason: str) -> None:
        for command_id, pending in list(runtime.pending_commands.items()):
            cleaned_output = EXIT_MARKER_RE.sub("", pending.output)
            close_message = f"\nTerminal closed before the command exit marker was received: {reason}."
            with Session(engine) as session:
                repo = RunRepository(session)
                terminal_command = repo.get_terminal_command(command_id)
                if terminal_command is None:
                    runtime.pending_commands.pop(command_id, None)
                    continue
                repo.update_terminal_command(
                    terminal_command,
                    TerminalCommandStatus.FAILED,
                    output=f"{cleaned_output}{close_message}",
                    ended=True,
                )
            runtime.pending_commands.pop(command_id, None)
            self._audit(runtime.run_id, "terminal_command_failed_on_close", {"command_id": command_id, "reason": reason})
            await self._broadcast(runtime, {"type": "command_completed", "command_id": command_id})

    async def _broadcast(self, runtime: TerminalRuntime, event: dict[str, Any]) -> None:
        safe_event = redact_payload(event, get_settings().configured_secrets())
        for queue in list(runtime.subscribers):
            await queue.put(safe_event)

    def _context(self, run_id: str) -> dict[str, Any]:
        with Session(engine) as session:
            repo = RunRepository(session)
            run = repo.get_run(run_id)
            if run is None:
                return {}
            terminal_commands = repo.list_terminal_commands(run_id)
            observations = [
                {
                    "source": command.source,
                    "status": command.status,
                    "command": command.final_command or command.original_command,
                    "classification": command.classification,
                    "exit_code": command.exit_code,
                    "output": command.output,
                    "reason": command.risk_reason,
                }
                for command in terminal_commands[-12:]
            ]
            guidance_events = [
                event.payload.get("message")
                for event in repo.list_audit_events(run_id)[-12:]
                if event.type == "agent_guidance_received" and event.payload.get("message")
            ]
            observations.extend({"source": "technician", "status": "guidance", "guidance": message} for message in guidance_events[-4:])
            snapshot = run.customer_system_snapshot or {}
            return {
                "ticket": snapshot.get("ticket", {}),
                "customer_system": snapshot.get("customer_system", {}),
                "related_ticket": snapshot.get("related_ticket"),
                "observations": observations,
            }

    def _write_preview(self, run_id: str, command: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            repo = RunRepository(session)
            run = repo.get_run(run_id)
            if run is None:
                return None
            snapshot = run.customer_system_snapshot or {}
            customer_system = snapshot.get("customer_system")
            if not customer_system:
                return None
            previewer = self.write_previewer or WritePreviewer(SshRunner(), repo.secrets)
            return previewer.preview(CustomerSystem.model_validate(customer_system).system, command)

    def _audit(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with Session(engine) as session:
            AuditLog(session).record(event_type, payload, run_id)
        persist_and_publish_ws_event_sync(run_id, event_type, payload)


terminal_manager = TerminalManager()


def _wrap_command_for_pty(command: str, command_id: int) -> str:
    command = _make_command_non_interactive(command)
    wrapped_command = shlex.quote(command)
    return f"\x15env {NONINTERACTIVE_ENV} bash -lc {wrapped_command}; __noflow_exit=$?; printf '\\n__NOFLOW_EXIT:{command_id}:%s__\\n' \"$__noflow_exit\"\n"


def _make_command_non_interactive(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    if not parts:
        return command

    command_index = _main_command_index(parts)
    if command_index is None:
        return command

    base = parts[command_index].split("/")[-1]
    if base == "systemctl" and "--no-pager" not in parts:
        parts.insert(command_index + 1, "--no-pager")
        return shlex.join(parts)
    if base == "journalctl":
        changed = False
        if "--no-pager" not in parts:
            parts.insert(command_index + 1, "--no-pager")
            changed = True
        if not _has_journal_line_bound(parts[command_index + 1 :]) and not _has_follow_flag(parts[command_index + 1 :]):
            parts[command_index + 1:command_index + 1] = ["-n", "120"]
            changed = True
        if changed:
            return shlex.join(parts)
    return command


def _agent_phase(phase: str | None) -> str:
    normalized = (phase or "").strip().lower()
    aliases = {
        "diagnosis": "diagnose",
        "diagnose": "diagnose",
        "execution": "fix",
        "fix": "fix",
        "verification": "validate",
        "validate": "validate",
        "recover": "recover",
    }
    if normalized in aliases:
        return aliases[normalized]
    return "diagnose"


def _workflow_phase(phase: str | None) -> str:
    normalized = _agent_phase(phase)
    if normalized == "fix":
        return "execution"
    if normalized == "validate":
        return "verification"
    return "diagnosis"


def _next_workflow_phase_after_command(phase: str | None, exit_code: int) -> str:
    normalized = _agent_phase(phase)
    if exit_code != 0:
        return "diagnosis"
    if normalized == "fix":
        return "verification"
    if normalized == "validate":
        return "verification"
    return "diagnosis"


def _terminal_observation_is_validation_evidence(observation: dict[str, Any]) -> bool:
    phase_text = str(observation.get("phase") or "").lower()
    command_text = str(observation.get("command") or "").lower()
    output_text = str(observation.get("output") or "").lower()
    if _terminal_command_looks_like_validation(command_text, phase_text):
        return True
    return _terminal_output_indicates_validation_success(output_text)


def _terminal_command_is_validation_evidence(command: str, output: str, phase: str | None = None) -> bool:
    return _terminal_observation_is_validation_evidence({"command": command, "output": output, "phase": phase})


def _terminal_command_looks_like_validation(command_text: str, phase_text: str | None = None) -> bool:
    if phase_text in {"validate", "validation", "verification"}:
        return True
    return any(term in command_text for term in ("curl", "health", "is-active", "smoke", "wget --spider"))


def _terminal_output_indicates_validation_success(output_text: str) -> bool:
    return any(
        term in output_text
        for term in (
            "validation passed",
            "validated successfully",
            "health check passed",
            "http 200",
            "status 200",
            "service reachable",
            "service is reachable",
            "service healthy",
            "service is healthy",
        )
    )


def _pending_exit_markers(runtime: TerminalRuntime):
    seen: set[tuple[int, int]] = set()
    for pending in list(runtime.pending_commands.values()):
        for match in EXIT_MARKER_RE.finditer(pending.output):
            marker = (int(match.group(1)), match.start())
            if marker in seen:
                continue
            seen.add(marker)
            yield match


def _main_command_index(parts: list[str]) -> int | None:
    if parts[0].split("/")[-1] != "sudo":
        return 0
    index = 1
    sudo_options_with_value = {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt"}
    while index < len(parts):
        token = parts[index]
        if token == "--":
            index += 1
            break
        if token in sudo_options_with_value:
            index += 2
            continue
        if token.startswith("--user=") or token.startswith("--group=") or token.startswith("--host=") or token.startswith("--prompt="):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return index if index < len(parts) else None


def _has_journal_line_bound(parts: list[str]) -> bool:
    for index, token in enumerate(parts):
        if token in {"-n", "--lines"}:
            return True
        if token.startswith("--lines="):
            return True
        if token.startswith("-") and not token.startswith("--") and "n" in token:
            return True
        if index > 0 and parts[index - 1] in {"-n", "--lines"}:
            return True
    return False


def _has_follow_flag(parts: list[str]) -> bool:
    return any(token in {"-f", "--follow"} or (token.startswith("-") and not token.startswith("--") and "f" in token) for token in parts)
