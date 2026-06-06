from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    PENDING = "PENDING"
    DONE = "DONE"


class Employee(BaseModel):
    id: int
    firstname: str
    lastname: str
    username: str
    teamname: str


class Ticket(BaseModel):
    id: int
    title: str
    description: str
    priority: str
    status: TicketStatus
    customer_id: int
    customer_name: str
    tags: list[str] = []
    sla_due_at: datetime | None = None
    created_at: datetime | None = None


class SystemInfo(BaseModel):
    ip: str
    port: int
    username: str
    os: str
    notes: str | None = None


class CustomerSystem(BaseModel):
    ticket_id: int
    customer_id: int
    system: SystemInfo


class Customer(BaseModel):
    id: int
    company_name: str
    firstname: str
    lastname: str
    system: SystemInfo


class StatusUpdate(BaseModel):
    status: TicketStatus


class ActivityCreate(BaseModel):
    ticket_id: int
    start_datetime: datetime
    end_datetime: datetime
    description: str | None = None
    summary: str | None = None
    root_cause: str | None = None
    actions_taken: str | None = None
    commands_summary: str | None = None
    validation_result: str | None = None


class Activity(BaseModel):
    id: int
    team_id: int
    team_name: str
    employee_id: int
    ticket_id: int
    start_datetime: datetime
    end_datetime: datetime
    description: str
    summary: str | None = None
    root_cause: str | None = None
    actions_taken: str | None = None
    commands_summary: str | None = None
    validation_result: str | None = None
    created_at: datetime | None = None


class SimpleMessage(BaseModel):
    message: str
    detail: dict | None = None


class PhoenixErrorResponse(BaseModel):
    detail: str | None = None


class HTTPValidationError(BaseModel):
    detail: list[dict] | None = None


class PhoenixModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
