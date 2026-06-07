import httpx
import pytest

from app.clients.phoenix import PhoenixClient
from app.core.config import Settings
from app.core.errors import ConfigurationError, PhoenixError, PhoenixNotFoundError, PhoenixUnauthorizedError, PhoenixValidationError
from app.schemas.phoenix import ActivityCreate, TicketStatus


def settings() -> Settings:
    return Settings(_env_file=None, phoenix_api_base_url="https://phoenix.example", phoenix_api_token="secret-token")


def empty_settings() -> Settings:
    return Settings(_env_file=None)


def transport(handler):
    return httpx.MockTransport(handler)


def ticket_payload(ticket_id: int = 7001) -> dict:
    return {
        "id": ticket_id,
        "title": "Status API unavailable",
        "description": "Customer report",
        "priority": "high",
        "status": "OPEN",
        "customer_id": 5001,
        "customer_name": "Example GmbH",
    }


def test_list_tickets_sends_bearer_auth_and_query_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=[ticket_payload()])

    tickets = PhoenixClient(settings(), transport=transport(handler)).list_tickets(
        status=TicketStatus.OPEN,
        priority="high",
        sort="priority",
    )

    assert len(tickets) == 1
    request = captured["request"]
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.url.params["status"] == "OPEN"
    assert request.url.params["priority"] == "high"
    assert request.url.params["sort"] == "priority"


def test_get_customer_system_parses_openapi_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/tickets/7001/customer-system"
        return httpx.Response(
            200,
            json={
                "ticket_id": 7001,
                "customer_id": 5001,
                "system": {"ip": "10.0.0.5", "port": 22, "username": "azureuser", "os": "Ubuntu 22.04 LTS"},
            },
        )

    customer_system = PhoenixClient(settings(), transport=transport(handler)).get_customer_system(7001)

    assert customer_system.system.username == "azureuser"


def test_create_activity_excludes_none_fields():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            201,
            json={
                "id": 1,
                "team_id": 2,
                "team_name": "Remote Support",
                "employee_id": 1001,
                "ticket_id": 7001,
                "start_datetime": "2026-06-07T10:00:00Z",
                "end_datetime": "2026-06-07T10:25:00Z",
                "description": "Done",
            },
        )
    activity = ActivityCreate(
        ticket_id=7001,
        start_datetime="2026-06-07T10:00:00Z",
        end_datetime="2026-06-07T10:25:00Z",
        description="Done",
    )

    PhoenixClient(settings(), transport=transport(handler)).create_activity(activity)

    assert "summary" not in captured["request"].content.decode()


def test_reset_me_posts_to_v1_reset_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"message": "reset requested"})

    PhoenixClient(settings(), transport=transport(handler)).reset_me()

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.scheme == "http"
    assert request.url.host == "68.210.101.85"
    assert request.url.port == 8000
    assert request.url.path == "/api/v1/me/reset"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.extensions["timeout"]["connect"] == 60.0
    assert request.extensions["timeout"]["read"] == 60.0


def test_error_statuses_map_to_clean_exceptions_without_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "bad token secret-token"})

    with pytest.raises(PhoenixValidationError) as exc_info:
        PhoenixClient(settings(), transport=transport(handler)).get_ticket(7001)

    assert "secret-token" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_unauthorized_and_not_found_are_specific_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/me":
            return httpx.Response(401, json={"detail": "no"})
        return httpx.Response(404, json={"detail": "missing"})

    client = PhoenixClient(settings(), transport=transport(handler))

    with pytest.raises(PhoenixUnauthorizedError):
        client.get_me()
    with pytest.raises(PhoenixNotFoundError):
        client.get_ticket(7001)


def test_missing_phoenix_config_fails_only_when_client_operation_is_called():
    client = PhoenixClient(empty_settings())

    with pytest.raises(ConfigurationError):
        client.get_me()


def test_get_me_malformed_payload_raises_clean_phoenix_error_without_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "bad", "username": "secret-token"})

    with pytest.raises(PhoenixError) as exc_info:
        PhoenixClient(settings(), transport=transport(handler)).get_me()

    assert "invalid technician identity" in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)


def test_list_tickets_malformed_item_raises_clean_phoenix_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[ticket_payload(), {"id": "bad", "title": "secret-token"}])

    with pytest.raises(PhoenixError) as exc_info:
        PhoenixClient(settings(), transport=transport(handler)).list_tickets()

    assert "invalid ticket item" in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)


def test_create_activity_malformed_response_raises_clean_phoenix_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "bad", "description": "secret-token"})

    activity = ActivityCreate(ticket_id=7001, start_datetime="2026-06-07T10:00:00Z", end_datetime="2026-06-07T10:25:00Z")

    with pytest.raises(PhoenixError) as exc_info:
        PhoenixClient(settings(), transport=transport(handler)).create_activity(activity)

    assert "invalid created activity" in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)
