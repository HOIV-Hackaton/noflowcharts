import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.clients.phoenix import PhoenixClient, get_phoenix_client
from app.core.errors import AppError, to_http_exception
from app.db.session import engine
from app.repositories.runs import RunRepository
from app.schemas.runs import TerminalCommandRead, TerminalTranscriptRead
from app.services.terminal_manager import terminal_manager
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


@router.get("/api/runs/{run_id}/terminal/logs", response_model=list[TerminalCommandRead])
def terminal_logs(run_id: str) -> list[TerminalCommandRead]:
    with Session(engine) as session:
        repo = RunRepository(session)
        if repo.get_run(run_id) is None:
            from app.core.errors import ValidationError

            raise to_http_exception(ValidationError("Run was not found"))
        return [TerminalCommandRead.model_validate(command, from_attributes=True) for command in repo.list_terminal_commands(run_id)]


@router.get("/api/runs/{run_id}/terminal/transcript", response_model=list[TerminalTranscriptRead])
def terminal_transcript(run_id: str) -> list[TerminalTranscriptRead]:
    with Session(engine) as session:
        repo = RunRepository(session)
        if repo.get_run(run_id) is None:
            from app.core.errors import ValidationError

            raise to_http_exception(ValidationError("Run was not found"))
        return [TerminalTranscriptRead.model_validate(event, from_attributes=True) for event in repo.list_terminal_transcript(run_id)]


@router.websocket("/api/runs/{run_id}/terminal/ws")
async def terminal_ws(websocket: WebSocket, run_id: str, cols: int = 120, rows: int = 32) -> None:
    await websocket.accept()
    try:
        runtime, queue = await terminal_manager.connect(run_id, cols=cols, rows=rows)
    except AppError as exc:
        await websocket.send_json({"type": "error", "message": exc.message})
        await websocket.close(code=1008, reason=exc.message[:120])
        return

    sender = asyncio.create_task(_send_events(websocket, queue))
    try:
        while True:
            message = await websocket.receive_json()
            try:
                await terminal_manager.handle_message(runtime, message)
            except AppError as exc:
                await websocket.send_json({"type": "error", "message": exc.message})
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        terminal_manager.disconnect(runtime, queue)


async def _send_events(websocket: WebSocket, queue: asyncio.Queue[dict]) -> None:
    while True:
        event = await queue.get()
        await websocket.send_json(event)
