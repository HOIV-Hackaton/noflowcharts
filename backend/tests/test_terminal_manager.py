import asyncio

import pytest
from sqlmodel import Session

from app.agent.planner import CommandProposal
from app.core.errors import ValidationError
from app.db.session import engine, init_db
from app.repositories.runs import RunRepository
from app.schemas.phoenix import CustomerSystem, SystemInfo, Ticket, TicketStatus
from app.schemas.runs import CommandClassification, RunStatus, TerminalCommandStatus
from app.services.safety import classify_command
from app.services.terminal_manager import TerminalManager
from app.services.terminal_safety import TerminalSafetyResult


class FakePty:
    instances = []

    def __init__(self, system, cols=120, rows=32):
        self.system = system
        self.cols = cols
        self.rows = rows
        self.opened = False
        self.closed = False
        self.writes = []
        self.reads = []
        FakePty.instances.append(self)

    def open(self):
        self.opened = True

    def read_available(self):
        return self.reads.pop(0) if self.reads else ""

    def write(self, data):
        self.writes.append(data)
        marker_id = _marker_id(data)
        if marker_id is not None:
            self.reads.append(f"command output token=secret-value\n__NOFLOW_EXIT:{marker_id}:0__\n")

    def resize(self, cols, rows):
        self.cols = cols
        self.rows = rows

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class ConfirmingReviewer:
    def review(self, command, context=None):
        deterministic = classify_command(command)
        if deterministic.blocked:
            return TerminalSafetyResult("block", deterministic.classification, deterministic.reason, deterministic)
        if command.startswith("touch"):
            return TerminalSafetyResult("confirm", CommandClassification.MUTATING, "Semantic review requires confirmation", deterministic, semantic_used=True)
        return TerminalSafetyResult("allow", deterministic.classification, deterministic.reason, deterministic)


class FakePlanner:
    def propose_next_command(self, ticket, customer_system, observations, safety_policy):
        return CommandProposal(intent="Check service status", command="systemctl status nginx", expected_signal="Service state is visible")


def _marker_id(data: str) -> int | None:
    prefix = "__NOFLOW_EXIT:"
    if prefix not in data:
        return None
    return int(data.split(prefix, 1)[1].split(":", 1)[0])


def create_run(confirmed: bool = True) -> str:
    init_db()
    ticket = Ticket(
        id=9901,
        title="Status API down",
        description="Customer cannot reach API",
        priority="high",
        status=TicketStatus.OPEN,
        customer_id=5001,
        customer_name="Example GmbH",
    )
    customer_system = CustomerSystem(
        ticket_id=9901,
        customer_id=5001,
        system=SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"),
    )
    with Session(engine) as session:
        repo = RunRepository(session)
        run = repo.create_run(9901, {"ticket": ticket.model_dump(mode="json"), "customer_system": customer_system.model_dump(mode="json")})
        if confirmed:
            repo.set_ssh_confirmed(run)
            repo.update_run_status(run, RunStatus.DIAGNOSING)
        return run.id


async def wait_for(queue, event_type: str, attempts: int = 50):
    for _ in range(attempts):
        event = await asyncio.wait_for(queue.get(), timeout=1)
        if event.get("type") == event_type:
            return event
    raise AssertionError(f"Did not receive {event_type}")


def test_terminal_requires_ssh_confirmation():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        with pytest.raises(ValidationError):
            await manager.connect(create_run(confirmed=False))

    asyncio.run(run_test())


def test_manual_read_only_command_executes_and_records_exit_code():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "input", "data": "uptime\r"})
        completed = await wait_for(queue, "command_completed")

        assert completed["exit_code"] == 0
        assert "uptime" in FakePty.instances[-1].writes[0]
        logs = manager.logs(run_id)
        assert logs[-1].status == TerminalCommandStatus.COMPLETED.value
        assert logs[-1].exit_code == 0
        assert "command output" in logs[-1].output
        with Session(engine) as session:
            transcript = RunRepository(session).list_terminal_transcript(run_id)
        assert "secret-value" not in transcript[-1].data
        assert "[REDACTED]" in transcript[-1].data
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_manual_interactive_command_is_blocked_before_ssh():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "input", "data": "vim /tmp/file\r"})
        blocked = await wait_for(queue, "command_blocked")

        assert "Interactive command" in blocked["reason"]
        assert FakePty.instances[-1].writes == []
        assert manager.logs(run_id)[-1].status == TerminalCommandStatus.BLOCKED.value
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_manual_semantic_confirmation_required_then_executes():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "input", "data": "touch /tmp/example\r"})
        required = await wait_for(queue, "confirmation_required")
        assert required["reason"] == "Semantic review requires confirmation"
        assert FakePty.instances[-1].writes == []

        await manager.handle_message(runtime, {"type": "manual_confirm", "command_id": required["command_id"]})
        await wait_for(queue, "command_completed")
        assert "touch /tmp/example" in FakePty.instances[-1].writes[0]
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_secret_prompt_suppresses_input_logging():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")
        FakePty.instances[-1].reads.append("Password:")
        await wait_for(queue, "terminal_output")

        await manager.handle_message(runtime, {"type": "input", "data": "super-secret\r"})

        assert FakePty.instances[-1].writes[-1] == "super-secret\r"
        assert manager.logs(run_id) == []
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_agent_reject_records_without_writing_to_pty():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer(), planner=FakePlanner())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        proposal = await wait_for(queue, "agent_proposal")
        await manager.handle_message(runtime, {"type": "agent_reject", "command_id": proposal["command_id"], "reason": "not the right service"})
        await wait_for(queue, "agent_waiting_for_guidance")

        assert FakePty.instances[-1].writes == []
        logs = manager.logs(run_id)
        assert logs[-1].status == TerminalCommandStatus.REJECTED.value
        assert "not the right service" in logs[-1].risk_reason
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())
