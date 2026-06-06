import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.db.session import get_session
from app.repositories.runs import RunRepository
from app.services.events import event_bus, serialize_ws_event
from app.core.config import get_settings


router = APIRouter(tags=["runs"])


@router.websocket("/api/runs/{run_id}/ws")
async def run_events_ws(
    websocket: WebSocket,
    run_id: str,
    last_event_id: int | None = None,
    session: Session = Depends(get_session),
) -> None:
    await websocket.accept()
    repo = RunRepository(session, secrets=get_settings().configured_secrets())
    if repo.get_run(run_id) is None:
        await websocket.close(code=1008, reason="Run was not found")
        return
    replayed = repo.replay_websocket_events(run_id, last_event_id=last_event_id)
    for event in replayed:
        await websocket.send_json(serialize_ws_event(event))

    queue = await event_bus.subscribe(run_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(event)
            except TimeoutError:
                await websocket.send_json({"event_id": None, "type": "ping", "run_id": run_id, "timestamp": None, "payload": {}})
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(run_id, queue)
