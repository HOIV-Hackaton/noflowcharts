from fastapi import APIRouter, Depends, WebSocket

from app.clients.phoenix import PhoenixClient, get_phoenix_client
from app.core.errors import AppError
from app.services.terminal_session import TerminalSession


router = APIRouter(tags=["terminal"])


@router.websocket("/api/terminal/tickets/{ticket_id}/ws")
async def ticket_terminal_ws(
    websocket: WebSocket,
    ticket_id: int,
    cols: int = 120,
    rows: int = 32,
    client: PhoenixClient = Depends(get_phoenix_client),
) -> None:
    try:
        customer_system = client.get_customer_system(ticket_id)
    except AppError as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": exc.message})
        await websocket.close()
        return

    await TerminalSession().bridge(websocket, customer_system.system, cols=cols, rows=rows)
