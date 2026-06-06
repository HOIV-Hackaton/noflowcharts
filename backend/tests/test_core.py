from app.core.redaction import REDACTED, redact_payload, redact_text
from app.schemas.phoenix import ActivityCreate, CustomerSystem, Ticket, TicketStatus
from app.schemas.runs import CommandClassification, RunStatus


def test_redact_text_masks_configured_and_common_secrets():
    text = "Authorization: Bearer abc.def token=secret-value password=hunter2 keep=this"

    redacted = redact_text(text, secrets=["secret-value"])

    assert "abc.def" not in redacted
    assert "secret-value" not in redacted
    assert "hunter2" not in redacted
    assert REDACTED in redacted
    assert "keep=this" in redacted


def test_redact_payload_recurses_nested_values():
    payload = {"outer": [{"token": "api_key=top-secret"}]}

    assert redact_payload(payload)["outer"][0]["token"] == f"api_key={REDACTED}"


def test_phoenix_schemas_match_openapi_optional_fields():
    ticket = Ticket.model_validate(
        {
            "id": 7001,
            "title": "Broken service",
            "description": "Customer symptom",
            "priority": "high",
            "status": "OPEN",
            "customer_id": 5001,
            "customer_name": "Example GmbH",
        }
    )
    system = CustomerSystem.model_validate(
        {
            "ticket_id": 7001,
            "customer_id": 5001,
            "system": {"ip": "10.0.0.5", "port": 22, "username": "azureuser", "os": "Ubuntu 22.04 LTS"},
        }
    )

    assert ticket.status == TicketStatus.OPEN
    assert ticket.tags == []
    assert ticket.sla_due_at is None
    assert system.system.notes is None


def test_activity_create_allows_openapi_required_minimum():
    activity = ActivityCreate.model_validate(
        {
            "ticket_id": 7001,
            "start_datetime": "2026-06-07T10:00:00Z",
            "end_datetime": "2026-06-07T10:25:00Z",
        }
    )

    assert activity.ticket_id == 7001
    assert activity.summary is None


def test_run_schema_enums_have_planned_values():
    assert RunStatus.AWAITING_APPROVAL.value == "awaiting_approval"
    assert CommandClassification.RISKY_MUTATING.value == "risky_mutating"
