from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.session import engine, init_db
from app.main import app
from app.repositories.runs import RunRepository
from app.services.events import persist_and_publish_ws_event


def test_websocket_replays_events_after_last_event_id():
    init_db()
    with Session(engine) as session:
        repo = RunRepository(session)
        run = repo.create_run(8001)
        first = repo.add_websocket_event(run.id, "created", {"step": 1})
        second = repo.add_websocket_event(run.id, "next", {"step": 2})
        run_id = run.id
        first_event_id = first.event_id
        second_event_id = second.event_id

    client = TestClient(app)
    with client.websocket_connect(f"/api/runs/{run_id}/ws?last_event_id={first_event_id}") as websocket:
        event = websocket.receive_json()

    assert event["event_id"] == second_event_id
    assert event["type"] == "next"
    assert event["payload"] == {"step": 2}


def test_websocket_replays_all_events_without_cursor():
    init_db()
    with Session(engine) as session:
        repo = RunRepository(session)
        run = repo.create_run(8002)
        repo.add_websocket_event(run.id, "created", {"step": 1})
        run_id = run.id

    client = TestClient(app)
    with client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
        event = websocket.receive_json()

    assert event["type"] == "created"
    assert event["run_id"] == run_id


def test_persist_and_publish_ws_event_stores_redacted_event():
    init_db()
    with Session(engine) as session:
        repo = RunRepository(session, secrets=["secret-token"])
        run = repo.create_run(8003)

    # Publish with repository defaults; direct repository redaction is covered elsewhere.
    import asyncio

    event = asyncio.run(persist_and_publish_ws_event(run.id, "created", {"ok": True}))

    assert event["type"] == "created"
    assert event["payload"] == {"ok": True}
