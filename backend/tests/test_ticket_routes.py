from fastapi.testclient import TestClient

from app.clients.phoenix import get_phoenix_client
from app.core.errors import PhoenixNotFoundError
from app.main import app
from app.schemas.phoenix import CustomerSystem, Employee, SimpleMessage, SystemInfo, Ticket, TicketStatus


class FakePhoenixClient:
    def __init__(self):
        self.last_sort = None

    def get_me(self):
        return Employee(id=1001, firstname="Max", lastname="Mustermann", username="m.mustermann", teamname="Remote Support")

    def list_tickets(self, status=None, priority=None, sort="date"):
        self.last_sort = sort
        return [
            Ticket(
                id=7002,
                title="B",
                description="B",
                priority="low",
                status=TicketStatus.OPEN,
                customer_id=5002,
                customer_name="Zulu GmbH",
            ),
            Ticket(
                id=7001,
                title="A",
                description="A",
                priority="high",
                status=TicketStatus.OPEN,
                customer_id=5001,
                customer_name="Alpha GmbH",
            ),
        ]

    def get_ticket(self, ticket_id):
        if ticket_id == 404:
            raise PhoenixNotFoundError("missing")
        return self.list_tickets()[0]

    def get_customer_system(self, ticket_id):
        return CustomerSystem(
            ticket_id=ticket_id,
            customer_id=5001,
            system=SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu 22.04 LTS"),
        )

    def get_customer(self, customer_id):
        raise AssertionError("not used")

    def reset_me(self):
        return SimpleMessage(message="reset queued")


def test_ticket_routes_proxy_phoenix_and_sort_customer_client_side():
    fake = FakePhoenixClient()
    app.dependency_overrides[get_phoenix_client] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/tickets?sort=customer")

        assert response.status_code == 200
        assert [ticket["customer_name"] for ticket in response.json()] == ["Alpha GmbH", "Zulu GmbH"]
        assert fake.last_sort == "date"
    finally:
        app.dependency_overrides.clear()


def test_reset_route_proxies_phoenix_reset_without_exposing_credentials():
    app.dependency_overrides[get_phoenix_client] = lambda: FakePhoenixClient()
    try:
        client = TestClient(app)
        response = client.post("/api/me/reset")

        assert response.status_code == 200
        assert response.json() == {"message": "reset queued", "detail": None}
        assert "Bearer" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_ticket_route_maps_app_errors_to_http_response():
    app.dependency_overrides[get_phoenix_client] = lambda: FakePhoenixClient()
    try:
        client = TestClient(app)
        response = client.get("/api/tickets/404")

        assert response.status_code == 404
        assert response.json() == {"detail": "missing"}
    finally:
        app.dependency_overrides.clear()


def test_customer_system_route_returns_backend_only_ssh_target_data():
    app.dependency_overrides[get_phoenix_client] = lambda: FakePhoenixClient()
    try:
        client = TestClient(app)
        response = client.get("/api/tickets/7001/customer-system")

        assert response.status_code == 200
        assert response.json()["system"]["username"] == "azureuser"
        assert "private_key" not in response.text
    finally:
        app.dependency_overrides.clear()
