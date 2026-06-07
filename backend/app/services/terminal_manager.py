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
from app.schemas.runs import CommandClassification, RunStatus, TerminalCommandSource, TerminalCommandStatus
from app.services.audit_log import AuditLog
from app.services.events import persist_and_publish_ws_event_sync
from app.services.terminal_safety import TerminalSafetyReviewer
from app.services.terminal_session import SshPtySession, monotonic_seconds


IDLE_TIMEOUT_SECONDS = 15 * 60
EXIT_MARKER_RE = re.compile(r"__NOFLOW_EXIT:(\d+):(-?\d+)__")
SECRET_PROMPT_RE = re.compile(r"(?i)(password|passphrase|token|secret|api\s*key|private\s*key|sudo password)\s*:")
NONINTERACTIVE_ENV = "SYSTEMD_PAGER=cat SYSTEMD_COLORS=0 PAGER=cat LESS=FRXMK"


@dataclass
class PendingCommand:
    command_id: int
    output: str = ""


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
    current_agent_phase: str | None = None
    waiting_after_rejection: bool = False
    last_activity: float = field(default_factory=monotonic_seconds)
    secret_input_mode: bool = False
    reader_task: asyncio.Task | None = None
    closing: bool = False


class TerminalManager:
    def __init__(self, pty_factory=None, safety_reviewer: TerminalSafetyReviewer | None = None, planner: Planner | None = None):
        self._runtimes: dict[str, TerminalRuntime] = {}
        self.pty_factory = pty_factory or SshPtySession
        self.safety_reviewer = safety_reviewer or TerminalSafetyReviewer()
        self.planner = planner

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
            runtime.agent_active = True
            runtime.waiting_after_rejection = False
            self._audit(runtime.run_id, "agent_mode_started", {})
            await self._propose_agent(runtime)
        elif message_type == "agent_next":
            runtime.agent_active = True
            runtime.waiting_after_rejection = False
            await self._propose_agent(runtime)
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

    def logs(self, run_id: str) -> list[TerminalCommand]:
        with Session(engine) as session:
            return RunRepository(session).list_terminal_commands(run_id)

    async def _runtime(self, run_id: str, cols: int, rows: int) -> TerminalRuntime:
        runtime = self._runtimes.get(run_id)
        if runtime is not None and not runtime.closing:
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
            db_terminal_session = repo.get_open_terminal_session(run_id) or repo.create_terminal_session(run_id)
            customer_system = CustomerSystem.model_validate((run.customer_system_snapshot or {}).get("customer_system"))

        pty = self.pty_factory(customer_system.system, cols=cols, rows=rows)
        await asyncio.to_thread(pty.open)
        runtime = TerminalRuntime(run_id=run_id, db_session_id=db_terminal_session.id, pty=pty)
        runtime.reader_task = asyncio.create_task(self._reader(runtime))
        self._runtimes[run_id] = runtime
        self._audit(run_id, "terminal_opened", {"terminal_session_id": db_terminal_session.id})
        persist_and_publish_ws_event_sync(run_id, "terminal_opened", {"terminal_session_id": db_terminal_session.id})
        return runtime

    async def _handle_input(self, runtime: TerminalRuntime, data: str) -> None:
        if runtime.secret_input_mode:
            await asyncio.to_thread(runtime.pty.write, data)
            if "\n" in data or "\r" in data:
                runtime.secret_input_mode = False
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

    async def _propose_agent(self, runtime: TerminalRuntime) -> None:
        planner = self.planner or Planner()
        context = self._context(runtime.run_id)
        proposal = await asyncio.to_thread(
            planner.propose_next_command,
            context.get("ticket", {}),
            context.get("customer_system", {}),
            context.get("observations", []),
            SAFETY_POLICY_SUMMARY,
            context.get("related_ticket"),
        )
        command = _make_command_non_interactive(proposal.command)
        phase = _agent_phase(proposal.phase)
        runtime.current_agent_phase = phase
        self._audit(runtime.run_id, "agent_phase_selected", {"phase": phase})
        await self._broadcast(runtime, {"type": "agent_phase_selected", "phase": phase})
        safety = self.safety_reviewer.review(command, context)
        status = TerminalCommandStatus.BLOCKED if safety.decision == "block" else TerminalCommandStatus.SUBMITTED
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
                },
            )

    async def _record_agent_guidance(self, runtime: TerminalRuntime, guidance: str) -> None:
        guidance = guidance.strip()
        if not guidance:
            return
        runtime.agent_active = True
        runtime.waiting_after_rejection = False
        self._audit(runtime.run_id, "agent_guidance_received", {"message": guidance})
        await self._broadcast(runtime, {"type": "agent_guidance_recorded"})
        await self._propose_agent(runtime)

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
            )
        self._audit(runtime.run_id, "agent_command_edited", {"command_id": command_id, "from": terminal_command.original_command, "to": final_command, "original_edit": command})
        if safety.decision == "block":
            await self._broadcast(runtime, {"type": "command_blocked", "command_id": command_id, "reason": safety.reason})
        else:
            await self._broadcast(runtime, {"type": "agent_proposal", "command_id": command_id, "command": final_command, "phase": runtime.current_agent_phase, "classification": safety.classification.value, "reason": safety.reason})

    async def _execute(self, runtime: TerminalRuntime, command_id: int, command: str, source: TerminalCommandSource) -> None:
        with Session(engine) as session:
            repo = RunRepository(session)
            terminal_command = repo.get_terminal_command(command_id)
            if terminal_command is not None:
                repo.update_terminal_command(terminal_command, TerminalCommandStatus.RUNNING, final_command=command, started=True)
        runtime.pending_commands[command_id] = PendingCommand(command_id)
        event_prefix = "agent" if source == TerminalCommandSource.AGENT else "manual"
        self._audit(runtime.run_id, f"{event_prefix}_command_running", {"command_id": command_id, "command": command})
        await self._broadcast(runtime, {"type": "command_running", "command_id": command_id})
        wrapped = _wrap_command_for_pty(command, command_id)
        await asyncio.to_thread(runtime.pty.write, wrapped)

    async def _reader(self, runtime: TerminalRuntime) -> None:
        try:
            while not runtime.closing:
                if monotonic_seconds() - runtime.last_activity > IDLE_TIMEOUT_SECONDS:
                    await self._close_runtime(runtime, "idle_timeout")
                    return
                if runtime.pty.is_closed():
                    await self._close_runtime(runtime, "ssh_closed")
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
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

    async def _capture_output(self, runtime: TerminalRuntime, data: str) -> None:
        for pending in list(runtime.pending_commands.values()):
            pending.output += data
        for match in EXIT_MARKER_RE.finditer(data):
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
                source = TerminalCommandSource(terminal_command.source)
            event_prefix = "agent" if source == TerminalCommandSource.AGENT else "manual"
            self._audit(runtime.run_id, f"{event_prefix}_command_completed", {"command_id": command_id, "exit_code": exit_code})
            await self._broadcast(runtime, {"type": "command_completed", "command_id": command_id, "exit_code": exit_code})
            if source == TerminalCommandSource.AGENT and runtime.agent_active and not runtime.waiting_after_rejection:
                await self._propose_agent(runtime)

    async def _close_runtime(self, runtime: TerminalRuntime, reason: str) -> None:
        if runtime.closing:
            return
        runtime.closing = True
        if runtime.reader_task is not None and runtime.reader_task is not asyncio.current_task():
            runtime.reader_task.cancel()
        await asyncio.to_thread(runtime.pty.close)
        with Session(engine) as session:
            repo = RunRepository(session)
            db_terminal_session = repo.get_open_terminal_session(runtime.run_id)
            if db_terminal_session is not None:
                repo.close_terminal_session(db_terminal_session, reason)
        self._audit(runtime.run_id, "terminal_closed", {"terminal_session_id": runtime.db_session_id, "reason": reason})
        await self._broadcast(runtime, {"type": "terminal_closed", "reason": reason})
        self._runtimes.pop(runtime.run_id, None)

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

    def _audit(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with Session(engine) as session:
            AuditLog(session).record(event_type, payload, run_id)
        persist_and_publish_ws_event_sync(run_id, event_type, payload)


terminal_manager = TerminalManager()


def _wrap_command_for_pty(command: str, command_id: int) -> str:
    command = _make_command_non_interactive(command)
    return f"{NONINTERACTIVE_ENV} {command}\nprintf '\\n__NOFLOW_EXIT:{command_id}:%s__\\n' \"$?\"\n"


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
    if normalized in {"diagnose", "fix", "validate", "recover"}:
        return normalized
    return "diagnose"


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
