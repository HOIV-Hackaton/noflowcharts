import asyncio
from collections import defaultdict
from typing import Any

from sqlmodel import Session

from app.core.config import get_settings
from app.db.session import engine
from app.repositories.runs import RunRepository


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        queues = self._queues.get(run_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self._queues.pop(run_id, None)

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        queues = list(self._queues.get(run_id, ()))
        for queue in queues:
            await queue.put(event)


event_bus = EventBus()


def serialize_ws_event(event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "type": event.type,
        "run_id": event.run_id,
        "timestamp": event.timestamp.isoformat(),
        "payload": event.payload,
    }


async def persist_and_publish_ws_event(run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as session:
        repo = RunRepository(session, secrets=get_settings().configured_secrets())
        event = repo.add_websocket_event(run_id, event_type, payload)
        serialized = serialize_ws_event(event)
    await event_bus.publish(run_id, serialized)
    return serialized
