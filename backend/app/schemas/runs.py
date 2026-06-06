from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    DIAGNOSING = "diagnosing"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING_COMMAND = "running_command"
    AWAITING_VALIDATION_CONFIRMATION = "awaiting_validation_confirmation"
    READY_FOR_ACTIVITY = "ready_for_activity"
    SUBMITTED = "submitted"
    ABORTED = "aborted"
    FAILED = "failed"


class CommandClassification(StrEnum):
    READ_ONLY = "read_only"
    MUTATING = "mutating"
    RISKY_MUTATING = "risky_mutating"
    BLOCKED = "blocked"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ConfirmationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    CONFIRMED = "confirmed"


class ValidationStatus(StrEnum):
    NOT_STARTED = "not_started"
    EVIDENCE_COLLECTED = "evidence_collected"
    HUMAN_CONFIRMED = "human_confirmed"


class ActivityReviewStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SUBMITTED = "submitted"


class RunRead(BaseModel):
    id: str
    ticket_id: int
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    customer_system_snapshot: dict[str, Any] | None = None
    current_action_id: int | None = None
    validation_status: ValidationStatus
    ssh_confirmed: bool
    validation_confirmed: bool


class ActionRead(BaseModel):
    id: int
    run_id: str
    status: ActionStatus
    command: str
    command_classification: CommandClassification
    intent: str | None = None
    risk_reason: str | None = None
    expected_signal: str | None = None
    typed_confirmation_status: ConfirmationStatus
    edited_command: str | None = None
    created_at: datetime
    updated_at: datetime


class CommandResultRead(BaseModel):
    id: int
    action_id: int
    command: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    started_at: datetime
    ended_at: datetime | None = None


class AuditEventRead(BaseModel):
    id: int
    run_id: str | None = None
    type: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    redacted: bool = True


class WebSocketEventRead(BaseModel):
    event_id: int
    run_id: str
    type: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ActivityDraftRead(BaseModel):
    id: int
    run_id: str
    summary: str | None = None
    root_cause: str | None = None
    actions_taken: str | None = None
    commands_summary: str | None = None
    validation_result: str | None = None
    description: str | None = None
    review_status: ActivityReviewStatus
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    ticket_id: int


class ActionDecision(BaseModel):
    action_id: int | None = None


class RiskConfirmation(BaseModel):
    action_id: int | None = None
    confirmation_text: str


class ActionEdit(BaseModel):
    action_id: int | None = None
    command: str
    intent: str | None = None


class ValidationConfirmation(BaseModel):
    evidence: str


class RunStateRead(BaseModel):
    run: RunRead
    current_action: ActionRead | None = None
    command_results: list[CommandResultRead] = Field(default_factory=list)
