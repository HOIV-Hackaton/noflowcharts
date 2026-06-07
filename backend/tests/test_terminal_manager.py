import asyncio

import pytest
from sqlmodel import Session

from app.agent.planner import CommandProposal
from app.core.errors import AgentError, ValidationError
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


class ClosingAfterMarkerPty(FakePty):
    def write(self, data):
        super().write(data)
        self.closed = True


class ClosingWithoutMarkerPty(FakePty):
    def write(self, data):
        self.writes.append(data)
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
    def __init__(self, command="systemctl status nginx", phase="diagnose"):
        self.command = command
        self.phase = phase
        self.observations = []

    def propose_next_command(self, ticket, customer_system, observations, safety_policy, related_ticket=None, run_id=None):
        self.observations = observations
        return CommandProposal(intent="Check service status", command=self.command, expected_signal="Service state is visible", phase=self.phase)


class FailingFollowupPlanner(FakePlanner):
    def __init__(self):
        super().__init__(command="systemctl restart nginx", phase="fix")
        self.calls = 0

    def propose_next_command(self, ticket, customer_system, observations, safety_policy, related_ticket=None, run_id=None):
        self.calls += 1
        if self.calls == 1:
            return super().propose_next_command(ticket, customer_system, observations, safety_policy, related_ticket, run_id)
        raise AgentError("Azure OpenAI returned an empty response")


class PhasedTerminalPlanner:
    def __init__(self):
        self.calls = []

    def propose_diagnosis_command(self, ticket, customer_system, observations, safety_policy, related_ticket=None, run_id=None):
        self.calls.append(("diagnosis", observations))
        return CommandProposal(intent="Restart the affected service after diagnosis evidence.", command="systemctl restart nginx", expected_signal="Restart exits successfully", phase="fix")

    def propose_verification_command(self, ticket, customer_system, observations, safety_policy, related_ticket=None, run_id=None):
        self.calls.append(("verification", observations))
        return CommandProposal(intent="Verify the customer-facing health endpoint after the fix.", command="curl --max-time 5 -fsS http://localhost/health", expected_signal="HTTP endpoint responds successfully", phase="validate")


class FakeWritePreviewer:
    def __init__(self):
        self.calls = []

    def preview(self, system, command):
        self.calls.append((system.ip, command))
        if ">" not in command and "tee" not in command and "sed -i" not in command:
            return {"status": "not_applicable", "redacted": True}
        return {
            "status": "available",
            "command_kind": "echo_redirect",
            "target_path": "/etc/app.conf",
            "diff": "--- a/etc/app.conf\n+++ b/etc/app.conf\n@@\n-old\n+new\n",
            "redacted": True,
        }


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


async def wait_for_terminal_output_containing(queue, text: str, attempts: int = 50):
    for _ in range(attempts):
        event = await asyncio.wait_for(queue.get(), timeout=1)
        if event.get("type") == "terminal_output" and text in event.get("data", ""):
            return event
    raise AssertionError(f"Did not receive terminal output containing {text}")


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
        output = await wait_for_terminal_output_containing(queue, "command output")
        completed = await wait_for(queue, "command_completed")

        assert "secret-value" not in output["data"]
        assert "[REDACTED]" in output["data"]
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


def test_closed_ssh_with_buffered_exit_marker_records_completion():
    async def run_test():
        manager = TerminalManager(pty_factory=ClosingAfterMarkerPty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "input", "data": "uptime\r"})
        completed = await wait_for(queue, "command_completed")

        assert completed["exit_code"] == 0
        logs = manager.logs(run_id)
        assert logs[-1].status == TerminalCommandStatus.COMPLETED.value
        assert logs[-1].exit_code == 0
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_closed_ssh_without_exit_marker_fails_pending_command_visibly():
    async def run_test():
        manager = TerminalManager(pty_factory=ClosingWithoutMarkerPty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "input", "data": "uptime\r"})
        completed = await wait_for(queue, "command_completed")
        closed = await wait_for(queue, "terminal_closed")

        assert "exit_code" not in completed
        assert closed["reason"] == "ssh_closed"
        logs = manager.logs(run_id)
        assert logs[-1].status == TerminalCommandStatus.FAILED.value
        assert "ssh_closed" in logs[-1].output

    asyncio.run(run_test())


def test_terminal_disconnect_keeps_ssh_runtime_for_reconnect():
    async def run_test():
        FakePty.instances = []
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id, cols=120, rows=32)
        await wait_for(queue, "terminal_opened")
        first_pty = FakePty.instances[-1]
        runtime.current_agent_phase = "fix"

        manager.disconnect(runtime, queue)

        assert first_pty.closed is False

        reconnected_runtime, reconnect_queue = await manager.connect(run_id, cols=96, rows=28)
        opened = await wait_for(reconnect_queue, "terminal_opened")
        phase = await wait_for(reconnect_queue, "agent_phase_selected")

        assert reconnected_runtime is runtime
        assert FakePty.instances[-1] is first_pty
        assert first_pty.cols == 96
        assert first_pty.rows == 28
        assert opened["session_id"] == runtime.db_session_id
        assert phase["phase"] == "fix"
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_manual_systemctl_command_is_made_non_interactive_before_execution():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer())
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "input", "data": "systemctl list-units --type=service --all\r"})
        await wait_for(queue, "command_completed")

        written = FakePty.instances[-1].writes[0]
        assert "SYSTEMD_PAGER=cat" in written
        assert "systemctl --no-pager list-units --type=service --all" in written
        logs = manager.logs(run_id)
        assert logs[-1].original_command == "systemctl list-units --type=service --all"
        assert logs[-1].final_command == "systemctl --no-pager list-units --type=service --all"
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


def test_agent_proposal_reports_current_phase():
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer(), planner=FakePlanner(phase="fix"))
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        phase = await wait_for(queue, "agent_phase_selected")
        proposal = await wait_for(queue, "agent_proposal")

        assert phase["phase"] == "fix"
        assert proposal["phase"] == "fix"
        with Session(engine) as session:
            audit_events = RunRepository(session).list_audit_events(run_id)
        assert any(event.type == "agent_phase_selected" and event.payload["phase"] == "fix" for event in audit_events)
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("planner_phase", "expected_phase"),
    [
        ("diagnosis", "diagnose"),
        ("execution", "fix"),
        ("verification", "validate"),
    ],
)
def test_agent_proposal_normalizes_phase_aliases(planner_phase, expected_phase):
    async def run_test():
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer(), planner=FakePlanner(phase=planner_phase))
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        phase = await wait_for(queue, "agent_phase_selected")
        proposal = await wait_for(queue, "agent_proposal")

        assert phase["phase"] == expected_phase
        assert proposal["phase"] == expected_phase
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_agent_followup_failure_is_reported_without_killing_reader():
    async def run_test():
        planner = FailingFollowupPlanner()
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer(), planner=planner)
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        proposal = await wait_for(queue, "agent_proposal")
        await manager.handle_message(runtime, {"type": "agent_accept", "command_id": proposal["command_id"]})

        await wait_for(queue, "command_completed")
        continuing = await wait_for(queue, "status")
        error = await wait_for(queue, "error")

        assert continuing["message"] == "Agent is preparing the next action..."
        assert "empty response" in error["message"]
        assert runtime.reader_task is not None
        assert not runtime.reader_task.done()
        with Session(engine) as session:
            audit_events = RunRepository(session).list_audit_events(run_id)
        assert any(event.type == "agent_proposal_failed" and "empty response" in event.payload["error"] for event in audit_events)
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_agent_routes_successful_terminal_fix_to_verification_command():
    async def run_test():
        planner = PhasedTerminalPlanner()
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer(), planner=planner)
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        first_phase = await wait_for(queue, "agent_phase_selected")
        proposal = await wait_for(queue, "agent_proposal")
        await manager.handle_message(runtime, {"type": "agent_accept", "command_id": proposal["command_id"]})

        await wait_for(queue, "command_completed")
        await wait_for(queue, "status")
        verification_phase = await wait_for(queue, "agent_phase_selected")
        verification = await wait_for(queue, "agent_proposal")

        assert first_phase["phase"] == "fix"
        assert planner.calls[0][0] == "diagnosis"
        assert planner.calls[-1][0] == "verification"
        assert verification_phase["phase"] == "validate"
        assert verification["command"] == "curl --max-time 5 -fsS http://localhost/health"
        assert any(call[0] == "verification" and any("restart nginx" in observation.get("command", "") for observation in call[1]) for call in planner.calls)
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_agent_guidance_after_rejection_is_not_submitted_as_shell_command():
    async def run_test():
        planner = FakePlanner()
        manager = TerminalManager(pty_factory=FakePty, safety_reviewer=ConfirmingReviewer(), planner=planner)
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        proposal = await wait_for(queue, "agent_proposal")
        assert proposal["command"] == "systemctl --no-pager status nginx"
        await manager.handle_message(runtime, {"type": "agent_reject", "command_id": proposal["command_id"], "reason": "not enough context"})
        await wait_for(queue, "agent_waiting_for_guidance")

        await manager.handle_message(runtime, {"type": "input", "data": "sorry try again\r"})
        await wait_for(queue, "agent_guidance_recorded")
        await wait_for(queue, "agent_proposal")

        assert FakePty.instances[-1].writes == []
        logs = manager.logs(run_id)
        assert len(logs) == 2
        assert logs[0].status == TerminalCommandStatus.REJECTED.value
        assert logs[1].status == TerminalCommandStatus.SUBMITTED.value
        context = manager._context(run_id)
        assert {"source": "technician", "status": "guidance", "guidance": "sorry try again"} in context["observations"]
        assert any(observation.get("guidance") == "sorry try again" for observation in planner.observations)
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_agent_systemctl_list_units_is_made_non_interactive_before_proposal():
    async def run_test():
        manager = TerminalManager(
            pty_factory=FakePty,
            safety_reviewer=ConfirmingReviewer(),
            planner=FakePlanner("systemctl list-units --type=service --all"),
        )
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        proposal = await wait_for(queue, "agent_proposal")

        assert proposal["command"] == "systemctl --no-pager list-units --type=service --all"
        logs = manager.logs(run_id)
        assert logs[-1].original_command == "systemctl list-units --type=service --all"
        assert logs[-1].final_command == "systemctl --no-pager list-units --type=service --all"
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())


def test_agent_write_proposal_includes_write_preview():
    async def run_test():
        previewer = FakeWritePreviewer()
        manager = TerminalManager(
            pty_factory=FakePty,
            safety_reviewer=ConfirmingReviewer(),
            planner=FakePlanner("echo 'PORT=9090' > /etc/app.conf", phase="fix"),
            write_previewer=previewer,
        )
        run_id = create_run()
        runtime, queue = await manager.connect(run_id)
        await wait_for(queue, "terminal_opened")

        await manager.handle_message(runtime, {"type": "agent_start"})
        proposal = await wait_for(queue, "agent_proposal")

        assert proposal["write_preview"]["status"] == "available"
        assert proposal["write_preview"]["target_path"] == "/etc/app.conf"
        logs = manager.logs(run_id)
        assert logs[-1].write_preview["status"] == "available"
        assert previewer.calls == [("10.0.0.5", "echo 'PORT=9090' > /etc/app.conf")]
        assert FakePty.instances[-1].writes == []
        await manager.close_run(run_id, "test_done")

    asyncio.run(run_test())
