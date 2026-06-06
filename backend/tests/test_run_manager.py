import pytest
from datetime import UTC, datetime
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.agent.planner import CommandProposal
from app.core.errors import PhoenixError, ValidationError
from app.schemas.phoenix import Activity, ActivityCreate, CustomerSystem, SystemInfo, Ticket, TicketStatus
from app.schemas.runs import ActivityDraftUpdate, ActivityReviewStatus, ActivitySubmitRequest, RunStatus
from app.services.run_manager import RunManager
from app.services.ssh_runner import MAX_STREAM_CHARS, SshCommandResult


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class FakePhoenix:
    def __init__(self):
        self.status_updates = []
        self.activities = []

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

    def create_activity(self, activity: ActivityCreate):
        self.activities.append(activity)
        return Activity(
            id=9001,
            team_id=1,
            team_name="Remote Support",
            employee_id=1001,
            ticket_id=activity.ticket_id,
            start_datetime=activity.start_datetime,
            end_datetime=activity.end_datetime,
            description=activity.description or "",
            summary=activity.summary,
            root_cause=activity.root_cause,
            actions_taken=activity.actions_taken,
            commands_summary=activity.commands_summary,
            validation_result=activity.validation_result,
            created_at=datetime.now(UTC),
        )

class TicketValidationPhoenix(FakePhoenix):
    def get_ticket(self, ticket_id):
        ticket = super().get_ticket(ticket_id)
        ticket.description = """
The customer reports that the internal status API is not reachable at:
http://localhost:8080/health

Public validation:
sudo /usr/local/bin/status-smoke-test.sh
"""
        return ticket


class ValidationOnlyPhoenix(FakePhoenix):
    def get_ticket(self, ticket_id):
        ticket = super().get_ticket(ticket_id)
        ticket.description = """
Customer report: the batch processor health is degraded.

Run:
/usr/local/bin/batch-smoke-test.sh
"""
        return ticket


class FailingActivityPhoenix(FakePhoenix):
    def create_activity(self, activity: ActivityCreate):
        raise PhoenixError("activity failed")


class FakePlanner:
    def __init__(self, command="systemctl status nginx"):
        self.command = command

    def propose_next_command(self, ticket, customer_system, observations, safety_policy):
        return CommandProposal(intent="Check service", command=self.command, expected_signal="Service state is visible")


class FakeValidationPlanner(FakePlanner):
    def __init__(self):
        super().__init__("curl -fsS http://localhost/health")

    def propose_next_command(self, ticket, customer_system, observations, safety_policy):
        self.observations = observations
        return CommandProposal(intent="Validate customer service restoration", command=self.command, expected_signal="HTTP endpoint responds successfully")


class FakeSshRunner:
    def __init__(self):
        self.commands = []

    def run(self, system, command):
        self.commands.append((system.ip, command))
        return SshCommandResult(command=command, exit_code=0, stdout="active", stderr="", timed_out=False)


class FakeActivityGenerator:
    def generate(self, ticket, customer_system, actions, command_results, validation):
        return ActivityDraftUpdate(
            summary="Restored the status API service.",
            root_cause="nginx was inactive, so the API proxy was unavailable.",
            actions_taken="Checked nginx status, restarted the service, then validated it was active.",
            commands_summary="Used service status and validation commands; no secret output included.",
            validation_result="systemctl reported nginx active and the service responded successfully.",
            description="Restored customer-facing status API availability after service recovery.",
        )


def make_manager(session, planner=None, ssh_runner=None, phoenix=None, activity_generator=None):
    manager = RunManager(
        session,
        phoenix_client=phoenix or FakePhoenix(),
        planner=planner or FakePlanner(),
        ssh_runner=ssh_runner or FakeSshRunner(),
        activity_generator=activity_generator,
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

def test_run_manager_prefers_ticket_health_and_public_validation_before_generic_planner():
    with make_session() as session:
        ssh_runner = FakeSshRunner()
        manager = make_manager(
            session,
            phoenix=TicketValidationPhoenix(),
            planner=FakePlanner("ss -ltn sport = :8080"),
            ssh_runner=ssh_runner,
        )
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)

        state = manager.propose_next(run_id)
        assert state.current_action.command == "curl --max-time 5 -fsS http://localhost:8080/health"

        _, action_id = manager.approve(run_id, state.current_action.id)
        manager.execute_action(run_id, action_id)

        state = manager.propose_next(run_id)
        assert state.current_action.command == "sudo -n /usr/local/bin/status-smoke-test.sh"
        assert state.current_action.typed_confirmation_status == "pending"
        assert ssh_runner.commands == [("10.0.0.5", "curl --max-time 5 -fsS http://localhost:8080/health")]


def test_run_manager_can_propose_explicit_validation_command_without_health_url():
    with make_session() as session:
        manager = make_manager(
            session,
            phoenix=ValidationOnlyPhoenix(),
            planner=FakePlanner("systemctl status batch-processor"),
        )
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)

        state = manager.propose_next(run_id)

        assert state.current_action.command == "/usr/local/bin/batch-smoke-test.sh"


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


def test_validation_confirmation_requires_successful_validation_command_evidence():
    with make_session() as session:
        manager = make_manager(session)
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)

        with pytest.raises(ValidationError):
            manager.confirm_validation(run_id, "Service responds with HTTP 200")

        state = manager.propose_next(run_id)
        _, action_id = manager.approve(run_id, state.current_action.id)
        manager.execute_action(run_id, action_id)

        with pytest.raises(ValidationError):
            manager.confirm_validation(run_id, "Service responds with HTTP 200 and systemctl reports active")

        manager.planner = FakeValidationPlanner()
        state = manager.propose_next(run_id)
        _, action_id = manager.approve(run_id, state.current_action.id)
        manager.execute_action(run_id, action_id)
        state = manager.confirm_validation(run_id, "Service responds with HTTP 200 and systemctl reports active")

        assert state.run.status == RunStatus.READY_FOR_ACTIVITY
        assert state.run.validation_confirmed is True


def ready_run(manager):
    run_id = manager.start_run(7001).run.id
    manager.confirm_ssh(run_id)
    manager.planner = FakeValidationPlanner()
    state = manager.propose_next(run_id)
    _, action_id = manager.approve(run_id, state.current_action.id)
    manager.execute_action(run_id, action_id)
    manager.confirm_validation(run_id, "Service responds with HTTP 200 and systemctl reports active")
    return run_id


def test_activity_submission_requires_validation_review_and_complete_draft():
    with make_session() as session:
        manager = make_manager(session, activity_generator=FakeActivityGenerator())
        run_id = manager.start_run(7001).run.id

        with pytest.raises(ValidationError):
            manager.generate_activity_draft(run_id)

        manager.confirm_ssh(run_id)
        manager.planner = FakeValidationPlanner()
        state = manager.propose_next(run_id)
        _, action_id = manager.approve(run_id, state.current_action.id)
        manager.execute_action(run_id, action_id)
        manager.confirm_validation(run_id, "Service responds with HTTP 200 and systemctl reports active")
        draft = manager.update_activity_draft(run_id, ActivityDraftUpdate(summary="Only a summary"))

        assert draft.review_status == ActivityReviewStatus.DRAFT
        with pytest.raises(ValidationError):
            manager.review_activity_draft(run_id)
        with pytest.raises(ValidationError):
            manager.submit_activity(run_id, ActivitySubmitRequest())


def test_activity_draft_review_submission_sets_ticket_done():
    with make_session() as session:
        phoenix = FakePhoenix()
        manager = make_manager(session, phoenix=phoenix, activity_generator=FakeActivityGenerator())
        run_id = ready_run(manager)

        draft = manager.generate_activity_draft(run_id)
        reviewed = manager.review_activity_draft(run_id)
        activity = manager.submit_activity(run_id, ActivitySubmitRequest())
        state = manager.state(run_id)

        assert draft.summary == "Restored the status API service."
        assert reviewed.review_status == ActivityReviewStatus.REVIEWED
        assert activity.id == 9001
        assert phoenix.activities[0].root_cause == "nginx was inactive, so the API proxy was unavailable."
        assert phoenix.status_updates[-1] == (7001, TicketStatus.DONE)
        assert state.run.status == RunStatus.SUBMITTED
        assert state.activity_draft.review_status == ActivityReviewStatus.SUBMITTED


def test_activity_submission_failure_does_not_set_ticket_done():
    with make_session() as session:
        phoenix = FailingActivityPhoenix()
        manager = make_manager(session, phoenix=phoenix, activity_generator=FakeActivityGenerator())
        run_id = ready_run(manager)
        manager.generate_activity_draft(run_id)
        manager.review_activity_draft(run_id)

        with pytest.raises(PhoenixError):
            manager.submit_activity(run_id, ActivitySubmitRequest())

        assert (7001, TicketStatus.DONE) not in phoenix.status_updates


def test_command_results_are_redacted_in_state_and_llm_observations():
    with make_session() as session:
        manager = make_manager(session)
        manager.repo.secrets = ["configured-secret"]
        manager.audit.repository.secrets = ["configured-secret"]
        run_id = manager.start_run(7001).run.id
        manager.confirm_ssh(run_id)
        state = manager.propose_next(run_id)
        action = manager.repo.get_action(state.current_action.id)
        manager.repo.add_command_result(action, action.command, 0, "output configured-secret " + ("x" * (MAX_STREAM_CHARS + 10)), "password=hunter2")

        state = manager.state(run_id)
        observations = manager._observations(run_id)

        assert "configured-secret" not in state.command_results[0].stdout
        assert "hunter2" not in state.command_results[0].stderr
        assert state.command_results[0].stdout.endswith("[truncated]")
        assert "configured-secret" not in str(observations)


def test_safer_alternative_requires_ssh_and_blocked_action_and_does_not_execute():
    with make_session() as session:
        ssh_runner = FakeSshRunner()
        planner = FakeValidationPlanner()
        manager = make_manager(session, planner=planner, ssh_runner=ssh_runner)
        run_id = manager.start_run(7001).run.id

        with pytest.raises(ValidationError):
            manager.request_safer_alternative(run_id)

        manager.confirm_ssh(run_id)
        state = manager.propose_next(run_id)
        with pytest.raises(ValidationError):
            manager.request_safer_alternative(run_id, state.current_action.id)

        manager.edit(run_id, "rm -rf /etc", action_id=state.current_action.id)
        alternative = manager.request_safer_alternative(run_id, state.current_action.id)

        assert alternative.current_action.command == "curl -fsS http://localhost/health"
        assert alternative.current_action.status == "proposed"
        assert ssh_runner.commands == []
        assert planner.observations[-1]["blocked_command"] == "rm -rf /etc"
