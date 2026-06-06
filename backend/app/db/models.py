from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.schemas.runs import (
    ActionStatus,
    ActivityReviewStatus,
    CommandClassification,
    ConfirmationStatus,
    RunStatus,
    TerminalCommandSource,
    TerminalCommandStatus,
    TerminalSessionStatus,
    ValidationStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Run(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    ticket_id: int = Field(index=True)
    status: str = Field(default=RunStatus.CREATED.value, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    customer_system_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    current_action_id: int | None = Field(default=None, foreign_key="action.id")
    validation_status: str = Field(default=ValidationStatus.NOT_STARTED.value)
    ssh_confirmed: bool = Field(default=False)
    validation_confirmed: bool = Field(default=False)


class Action(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    status: str = Field(default=ActionStatus.PROPOSED.value, index=True)
    command: str
    command_classification: str = Field(default=CommandClassification.READ_ONLY.value)
    intent: str | None = None
    risk_reason: str | None = None
    expected_signal: str | None = None
    typed_confirmation_status: str = Field(default=ConfirmationStatus.NOT_REQUIRED.value)
    edited_command: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CommandResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    action_id: int = Field(foreign_key="action.id", index=True)
    command: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = Field(default=False)
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str | None = Field(default=None, foreign_key="run.id", index=True)
    type: str = Field(index=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    redacted: bool = Field(default=True)


class ActivityDraft(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True, unique=True)
    summary: str | None = None
    root_cause: str | None = None
    actions_taken: str | None = None
    commands_summary: str | None = None
    validation_result: str | None = None
    description: str | None = None
    review_status: str = Field(default=ActivityReviewStatus.DRAFT.value)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WebSocketEvent(SQLModel, table=True):
    event_id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    type: str = Field(index=True)
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class TerminalSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    status: str = Field(default=TerminalSessionStatus.OPEN.value, index=True)
    opened_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None
    last_seen_at: datetime = Field(default_factory=utc_now, index=True)
    close_reason: str | None = None


class TerminalCommand(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    terminal_session_id: int | None = Field(default=None, foreign_key="terminalsession.id", index=True)
    source: str = Field(default=TerminalCommandSource.MANUAL.value, index=True)
    status: str = Field(default=TerminalCommandStatus.SUBMITTED.value, index=True)
    original_command: str
    final_command: str | None = None
    edited_from: str | None = None
    edited_to: str | None = None
    classification: str | None = None
    risk_reason: str | None = None
    exit_code: int | None = None
    output: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    redacted: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TerminalTranscriptEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    terminal_session_id: int | None = Field(default=None, foreign_key="terminalsession.id", index=True)
    stream: str = Field(default="stdout")
    data: str
    created_at: datetime = Field(default_factory=utc_now, index=True)
    redacted: bool = Field(default=True)
