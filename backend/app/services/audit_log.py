from typing import Any

from sqlmodel import Session

from app.core.config import get_settings
from app.db.models import AuditEvent
from app.repositories.runs import RunRepository


class AuditLog:
    def __init__(self, session: Session, secrets: list[str] | None = None):
        self.repository = RunRepository(session, secrets=secrets or get_settings().configured_secrets())

    def record(self, event_type: str, payload: dict[str, Any], run_id: str | None = None) -> AuditEvent:
        return self.repository.add_audit_event(event_type, payload, run_id=run_id)

    def for_run(self, run_id: str) -> list[AuditEvent]:
        return self.repository.list_audit_events(run_id)
