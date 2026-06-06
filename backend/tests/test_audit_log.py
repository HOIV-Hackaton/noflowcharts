from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.repositories.runs import RunRepository
from app.services.audit_log import AuditLog


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_audit_log_records_redacted_append_only_events():
    with make_session() as session:
        repo = RunRepository(session)
        run = repo.create_run(7001)
        audit = AuditLog(session, secrets=["secret-token"])

        first = audit.record("ticket_loaded", {"token": "secret-token"}, run.id)
        second = audit.record("command_proposed", {"command": "systemctl status nginx"}, run.id)
        events = audit.for_run(run.id)

        assert first.payload["token"] == "[REDACTED]"
        assert [event.id for event in events] == [first.id, second.id]
        assert [event.type for event in events] == ["ticket_loaded", "command_proposed"]
