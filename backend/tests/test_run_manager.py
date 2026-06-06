import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.agent.planner import CommandProposal
from app.core.errors import ValidationError
from app.schemas.phoenix import CustomerSystem, SystemInfo, Ticket, TicketStatus
from app.schemas.runs import RunStatus
from app.services.run_manager import RunManager
from app.services.ssh_runner import SshCommandResult


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class FakePhoenix:
    def __init__(self):
        self.status_updates = []

    def get_ticket(self, ticket_id):
        return Ticket(
            id=ticket_id,
            title="Status API unavailable",
            description="Customer reports API is down",
            priority="high",
            status=TicketStatus.OPEN,
            customer_id=5001,
            customer_name="Example GmbH",
        )

    def get_customer_system(self, ticket_id):
        return CustomerSystem(
            ticket_id=ticket_id,
            customer_id=5001,
            system=SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu 22.04"),
        )

    def set_ticket_status(self, ticket_id, status):
        self.status_updates.append((ticket_id, status))
        ticket = self.get_ticket(ticket_id)
        ticket.status = status
        return ticket


class FakePlanner:
    def __init__(self, command="systemctl status nginx"):
        self.command = command

    def propose_next_command(self, ticket, customer_system, observations, safety_policy):
        return CommandProposal(intent="Check service", command=self.command, expected_signal="Service state is visible")


class FakeSshRunner:
    def __init__(self):
        self.commands = []

    def run(self, system, command):
        self.commands.append((system.ip, command))
        return SshCommandResult(command=command, exit_code=0, stdout="active", stderr="", timed_out=False)


def make_manager(session, planner=None, ssh_runner=None, phoenix=None):
    manager = RunManager(
        session,
        phoenix_client=phoenix or FakePhoenix(),
        planner=planner or FakePlanner(),
        ssh_runner=ssh_runner or FakeSshRunner(),
    )
    manager._event = lambda run_id, event_type, payload: None
    return manager


def test_run_manager_requires_ssh_confirmation_before_proposing_commands():
    with make_session() as session:
        phoenix = FakePhoenix()
        manager = make_manager(session, phoenix=phoenix)
        state = manager.start_run(7001)

        assert state.run.status == RunStatus.PENDING
        assert phoenix.status_updates == [(7001, TicketStatus.PENDING)]
        with pytest.raises(ValidationError):
            manager.propose_next(state.run.id)


def test_run_manager_requires_approval_before_command_execution():
    with make_session() as session:
        ssh_runner = FakeSshRunner()
        manager = make_manager(session, ssh_runner=ssh_runner)
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)
        state = manager.propose_next(run_id)

        with pytest.raises(ValidationError):
            manager.execute_action(run_id, state.current_action.id)

        _, action_id = manager.approve(run_id)
        manager.execute_action(run_id, action_id)
        state = manager.state(run_id)

        assert ssh_runner.commands == [("10.0.0.5", "systemctl status nginx")]
        assert state.command_results[0].stdout == "active"


def test_run_manager_requires_typed_confirmation_for_risky_command():
    with make_session() as session:
        manager = make_manager(session, planner=FakePlanner("sudo systemctl restart nginx"))
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)
        state = manager.propose_next(run_id)

        with pytest.raises(ValidationError):
            manager.approve(run_id)

        manager.confirm_risk(run_id, f"RUN {state.current_action.command}")
        state, _ = manager.approve(run_id)

        assert state.current_action.typed_confirmation_status == "confirmed"


def test_validation_confirmation_requires_successful_command_evidence():
    with make_session() as session:
        manager = make_manager(session)
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)

        with pytest.raises(ValidationError):
            manager.confirm_validation(run_id, "Service responds with HTTP 200")

        state = manager.propose_next(run_id)
        _, action_id = manager.approve(run_id, state.current_action.id)
        manager.execute_action(run_id, action_id)
        state = manager.confirm_validation(run_id, "Service responds with HTTP 200 and systemctl reports active")

        assert state.run.status == RunStatus.READY_FOR_ACTIVITY
        assert state.run.validation_confirmed is True
