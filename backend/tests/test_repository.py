from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.repositories.runs import RunRepository
from app.schemas.runs import ActivityReviewStatus, CommandClassification, ConfirmationStatus, RunStatus, ValidationStatus


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_run_repository_persists_run_action_result_and_activity():
    with make_session() as session:
        repo = RunRepository(session)
        run = repo.create_run(7001, {"system": {"ip": "10.0.0.5"}})

        action = repo.add_action(
            run,
            command="systemctl status nginx",
            classification=CommandClassification.READ_ONLY,
            intent="Check service health",
        )
        result = repo.add_command_result(action, action.command, 0, "active", "")
        draft = repo.upsert_activity_draft(run, summary="Restored service")
        repo.set_activity_review_status(draft, ActivityReviewStatus.REVIEWED)

        stored_run = repo.get_run(run.id)
        assert stored_run is not None
        assert stored_run.current_action_id == action.id
        assert stored_run.status == RunStatus.AWAITING_APPROVAL.value
        assert action.typed_confirmation_status == ConfirmationStatus.NOT_REQUIRED.value
        assert result.stdout == "active"
        assert draft.review_status == ActivityReviewStatus.REVIEWED.value


def test_audit_and_websocket_events_are_redacted_and_replayed_in_order():
    with make_session() as session:
        repo = RunRepository(session, secrets=["real-token"])
        run = repo.create_run(7001)

        audit = repo.add_audit_event("ticket_loaded", {"header": "Bearer real-token"}, run.id)
        first = repo.add_websocket_event(run.id, "created", {"token": "real-token"})
        second = repo.add_websocket_event(run.id, "next", {"ok": True})

        replayed = repo.replay_websocket_events(run.id, last_event_id=first.event_id)

        assert audit.payload["header"] == "Bearer [REDACTED]"
        assert first.payload["token"] == "[REDACTED]"
        assert replayed == [second]


def test_run_repository_updates_confirmation_and_validation_state():
    with make_session() as session:
        repo = RunRepository(session)
        run = repo.create_run(7001)

        repo.set_ssh_confirmed(run)
        repo.update_run_status(run, RunStatus.DIAGNOSING)
        repo.set_validation_status(run, ValidationStatus.HUMAN_CONFIRMED, confirmed=True)

        stored = repo.get_run(run.id)
        assert stored is not None
        assert stored.ssh_confirmed is True
        assert stored.status == RunStatus.DIAGNOSING.value
        assert stored.validation_status == ValidationStatus.HUMAN_CONFIRMED.value
        assert stored.validation_confirmed is True
