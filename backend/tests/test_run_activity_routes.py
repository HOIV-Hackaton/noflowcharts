from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api import routes_activity, routes_runs
from app.core.errors import ValidationError
from app.main import app
from app.schemas.phoenix import Activity, Ticket, TicketStatus
from app.schemas.runs import (
    ActionRead,
    ActivityDraftRead,
    ActivityReviewStatus,
    RunRead,
    RunStateRead,
    RunStatus,
    ValidationStatus,
)


def _state(status: RunStatus = RunStatus.PENDING, action: ActionRead | None = None) -> RunStateRead:
    now = datetime.now(UTC)
    return RunStateRead(
        run=RunRead(
            id="run-1",
            ticket_id=7001,
            status=status,
            created_at=now,
            updated_at=now,
            current_action_id=action.id if action else None,
            validation_status=ValidationStatus.NOT_STARTED,
            ssh_confirmed=status != RunStatus.PENDING,
            validation_confirmed=False,
        ),
        current_action=action,
    )


def _action() -> ActionRead:
    now = datetime.now(UTC)
    return ActionRead(
        id=1,
        run_id="run-1",
        status="proposed",
        command="systemctl status nginx",
        command_classification="read_only",
        intent="Check service",
        expected_signal="state visible",
        typed_confirmation_status="not_required",
        created_at=now,
        updated_at=now,
    )


class FakeRunManager:
    def __init__(self):
        self.pending = []
        self.approved = False

    def start_run(self, ticket_id):
        self.pending.append(ticket_id)
        return _state(RunStatus.PENDING)

    def state(self, run_id):
        return _state(RunStatus.DIAGNOSING)

    def confirm_ssh(self, run_id):
        return _state(RunStatus.DIAGNOSING)

    def propose_next(self, run_id):
        return _state(RunStatus.AWAITING_APPROVAL, _action())

    def approve(self, run_id, action_id=None):
        self.approved = True
        return _state(RunStatus.AWAITING_APPROVAL, _action()), 1

    def generate_activity_draft(self, run_id):
        raise ValidationError("Activity requires human-confirmed validation evidence first")


class FakeActivityManager(FakeRunManager):
    def __init__(self):
        super().__init__()
        self.phoenix = self

    def set_ticket_status(self, ticket_id, status):
        return Ticket(
            id=ticket_id,
            title="T",
            description="D",
            priority="high",
            status=status,
            customer_id=1,
            customer_name="C",
        )

    def generate_activity_draft(self, run_id):
        return _draft()

    def review_activity_draft(self, run_id, approved=True):
        draft = _draft()
        draft.review_status = ActivityReviewStatus.REVIEWED
        return draft

    def submit_activity(self, run_id, request):
        now = datetime.now(UTC)
        return Activity(id=1, team_id=1, team_name="T", employee_id=1, ticket_id=7001, start_datetime=now, end_datetime=now, description="done")


def _draft() -> ActivityDraftRead:
    now = datetime.now(UTC)
    return ActivityDraftRead(
        id=1,
        run_id="run-1",
        summary="s",
        root_cause="r",
        actions_taken="a",
        commands_summary="c",
        validation_result="v",
        description="d",
        review_status=ActivityReviewStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )


def test_run_routes_create_confirm_next_and_approve(monkeypatch):
    manager = FakeRunManager()
    app.dependency_overrides[routes_runs.get_run_manager] = lambda: manager
    monkeypatch.setattr(routes_runs, "_execute_action_background", lambda run_id, action_id: None)
    try:
        client = TestClient(app)
        assert client.post("/api/runs", json={"ticket_id": 7001}).json()["run"]["status"] == "pending"
        assert client.post("/api/runs/run-1/confirm-ssh").json()["run"]["status"] == "diagnosing"
        next_response = client.post("/api/runs/run-1/next")
        assert next_response.json()["current_action"]["status"] == "proposed"
        approve_response = client.post("/api/runs/run-1/approve", json={})
        assert approve_response.status_code == 200
        assert manager.approved is True
    finally:
        app.dependency_overrides.clear()


def test_route_errors_map_app_error_to_http_response():
    class FailingManager(FakeRunManager):
        def propose_next(self, run_id):
            raise ValidationError("Technician must confirm SSH connection before any system action")

    app.dependency_overrides[routes_runs.get_run_manager] = lambda: FailingManager()
    try:
        response = TestClient(app).post("/api/runs/run-1/next")
        assert response.status_code == 422
        assert "confirm SSH" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_activity_routes_reject_missing_validation_and_accept_valid_flow():
    app.dependency_overrides[routes_activity.get_run_manager] = lambda: FakeRunManager()
    try:
        client = TestClient(app)
        response = client.post("/api/runs/run-1/activity/draft")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[routes_activity.get_run_manager] = lambda: FakeActivityManager()
    try:
        client = TestClient(app)
        assert client.post("/api/runs/run-1/activity/draft").status_code == 200
        assert client.post("/api/runs/run-1/activity/review", json={"approved": True}).json()["review_status"] == "reviewed"
        assert client.post("/api/runs/run-1/activity/submit", json={"submit": True}).json()["id"] == 1
    finally:
        app.dependency_overrides.clear()


def test_patch_ticket_status_rejects_direct_done_but_allows_pending():
    app.dependency_overrides[routes_activity.get_run_manager] = lambda: FakeActivityManager()
    try:
        client = TestClient(app)
        done = client.patch("/api/tickets/7001/status", json={"status": "DONE"})
        pending = client.patch("/api/tickets/7001/status", json={"status": "PENDING"})

        assert done.status_code == 422
        assert "activity submission" in done.json()["detail"]
        assert pending.status_code == 200
        assert pending.json()["status"] == TicketStatus.PENDING
    finally:
        app.dependency_overrides.clear()
