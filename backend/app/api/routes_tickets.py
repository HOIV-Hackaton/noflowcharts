from fastapi import APIRouter, Depends, Query

from app.clients.phoenix import PhoenixClient, get_phoenix_client
from app.core.errors import AppError, to_http_exception
from app.schemas.phoenix import Customer, CustomerSystem, Employee, SimpleMessage, Ticket, TicketStatus


router = APIRouter(prefix="/api", tags=["tickets"])


@router.get("/me", response_model=Employee)
def get_me(client: PhoenixClient = Depends(get_phoenix_client)) -> Employee:
    try:
        return client.get_me()
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/me/reset", response_model=SimpleMessage)
def reset_me(client: PhoenixClient = Depends(get_phoenix_client)) -> SimpleMessage:
    try:
        return client.reset_me()
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.get("/tickets", response_model=list[Ticket])
def list_tickets(
    status: TicketStatus | None = None,
    priority: str | None = None,
    sort: str = Query(default="date", pattern="^(date|priority|status|customer)$"),
    client: PhoenixClient = Depends(get_phoenix_client),
) -> list[Ticket]:
    try:
        phoenix_sort = sort if sort != "customer" else "date"
        tickets = client.list_tickets(status=status, priority=priority, sort=phoenix_sort)
        if sort == "customer":
            return sorted(tickets, key=lambda ticket: ticket.customer_name.lower())
        return tickets
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.get("/tickets/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: int, client: PhoenixClient = Depends(get_phoenix_client)) -> Ticket:
    try:
        return client.get_ticket(ticket_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.get("/tickets/{ticket_id}/customer-system", response_model=CustomerSystem)
def get_customer_system(ticket_id: int, client: PhoenixClient = Depends(get_phoenix_client)) -> CustomerSystem:
    try:
        return client.get_customer_system(ticket_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: int, client: PhoenixClient = Depends(get_phoenix_client)) -> Customer:
    try:
        return client.get_customer(customer_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc
