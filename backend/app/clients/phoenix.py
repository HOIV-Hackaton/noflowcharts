from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, PhoenixError, PhoenixNotFoundError, PhoenixUnauthorizedError, PhoenixValidationError
from app.core.redaction import redact_text
from app.schemas.phoenix import Activity, ActivityCreate, Customer, CustomerSystem, Employee, SimpleMessage, StatusUpdate, Ticket, TicketStatus


TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
PHOENIX_RESET_BASE_URL = "http://68.210.101.85:8000"
PHOENIX_RESET_TIMEOUT_SECONDS = 60.0


class PhoenixClient:
    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 10.0,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings or get_settings()
        self.timeout = timeout
        self.retries = retries
        self.transport = transport

    def get_me(self) -> Employee:
        return self._validate(Employee, self._request("GET", "/api/v1/me"), "technician identity")

    def list_tickets(
        self,
        status: TicketStatus | None = None,
        priority: str | None = None,
        sort: str = "date",
    ) -> list[Ticket]:
        params: dict[str, str] = {"sort": sort}
        if status is not None:
            params["status"] = status.value
        if priority:
            params["priority"] = priority
        payload = self._request("GET", "/api/v1/me/tickets", params=params)
        if not isinstance(payload, list):
            raise PhoenixError("Phoenix returned an invalid ticket list")
        return [self._validate(Ticket, item, "ticket item") for item in payload]

    def get_ticket(self, ticket_id: int) -> Ticket:
        return self._validate(Ticket, self._request("GET", f"/api/v1/tickets/{ticket_id}"), "ticket")

    def get_customer_system(self, ticket_id: int) -> CustomerSystem:
        return self._validate(CustomerSystem, self._request("GET", f"/api/v1/tickets/{ticket_id}/customer-system"), "customer system")

    def get_customer(self, customer_id: int) -> Customer:
        return self._validate(Customer, self._request("GET", f"/api/v1/customers/{customer_id}"), "customer")

    def set_ticket_status(self, ticket_id: int, status: TicketStatus) -> Ticket:
        update = StatusUpdate(status=status)
        return self._validate(
            Ticket,
            self._request("PATCH", f"/api/v1/tickets/{ticket_id}/status", json=update.model_dump(mode="json")),
            "ticket status update",
        )

    def create_activity(self, activity: ActivityCreate) -> Activity:
        return self._validate(
            Activity,
            self._request("POST", "/api/v1/activities/create", json=activity.model_dump(mode="json", exclude_none=True)),
            "created activity",
        )

    def reset_me(self) -> SimpleMessage:
        return self._validate(
            SimpleMessage,
            self._request(
                "POST",
                "/api/v1/me/reset",
                request_base_url=PHOENIX_RESET_BASE_URL,
                timeout=PHOENIX_RESET_TIMEOUT_SECONDS,
            ),
            "reset response",
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        request_base_url: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            if request_base_url is None:
                self.settings.require_phoenix()
            elif not self.settings.phoenix_api_token:
                raise RuntimeError("Missing required Phoenix setting(s): PHOENIX_API_TOKEN")
        except RuntimeError as exc:
            raise ConfigurationError(str(exc)) from exc

        assert self.settings.phoenix_api_token is not None

        base_url = (request_base_url or self.settings.phoenix_api_base_url)
        assert base_url is not None
        base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {self.settings.phoenix_api_token}"}
        request_timeout = timeout if timeout is not None else self.timeout
        last_error: PhoenixError | None = None

        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(base_url=base_url, timeout=request_timeout, headers=headers, transport=self.transport) as client:
                    response = client.request(method, path, **kwargs)
                return self._handle_response(response)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = PhoenixError(f"Phoenix request failed: {exc}")
            except PhoenixError as exc:
                if not self._is_retryable(exc) or attempt >= self.retries:
                    raise
                last_error = exc
            if attempt >= self.retries and last_error is not None:
                raise last_error

        raise PhoenixError("Phoenix request failed")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code == 401:
            raise PhoenixUnauthorizedError("Phoenix rejected the configured bearer token")
        if response.status_code == 404:
            raise PhoenixNotFoundError("Phoenix resource was not found")
        if response.status_code == 422:
            raise PhoenixValidationError(self._response_detail(response, "Phoenix request failed validation"))
        if response.status_code in TRANSIENT_STATUS_CODES:
            raise PhoenixError(self._response_detail(response, "Phoenix is temporarily unavailable"))
        if response.is_error:
            raise PhoenixError(self._response_detail(response, f"Phoenix request failed with status {response.status_code}"))
        try:
            return response.json()
        except ValueError as exc:
            raise PhoenixError("Phoenix returned invalid JSON") from exc
        except PydanticValidationError as exc:
            raise PhoenixError(f"Phoenix response validation failed: {redact_text(str(exc), self.settings.configured_secrets())}") from exc

    def _validate(self, model, payload: Any, label: str):
        try:
            return model.model_validate(payload)
        except PydanticValidationError as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            raise PhoenixError(f"Phoenix returned an invalid {label}: {message}") from exc

    def _response_detail(self, response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return redact_text(fallback, self.settings.configured_secrets())
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if not detail:
            detail = fallback
        return redact_text(str(detail), self.settings.configured_secrets())

    def _is_retryable(self, error: PhoenixError) -> bool:
        return type(error) is PhoenixError


def get_phoenix_client() -> PhoenixClient:
    return PhoenixClient()


PhoenixClientDependency = Callable[[], PhoenixClient]
