from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api import routes_metrics
from app.db.models import Action, CommandResult, LlmUsageMetric, Run
from app.main import app
from app.schemas.runs import ActionStatus, CommandClassification, RunStatus


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_metrics_summary_reports_latency_tokens_and_estimated_cost():
    with make_session() as session:
        started = datetime(2026, 6, 7, 10, 0, tzinfo=UTC)
        run = Run(ticket_id=7001, status=RunStatus.SUBMITTED.value, created_at=started, updated_at=started + timedelta(seconds=12))
        session.add(run)
        session.commit()
        session.refresh(run)
        action = Action(
            run_id=run.id,
            status=ActionStatus.COMPLETED.value,
            command="systemctl status nginx",
            command_classification=CommandClassification.READ_ONLY.value,
        )
        session.add(action)
        session.commit()
        session.refresh(action)
        session.add(
            CommandResult(
                action_id=action.id,
                command=action.command,
                exit_code=0,
                started_at=started,
                ended_at=started + timedelta(milliseconds=250),
            )
        )
        session.add(
            LlmUsageMetric(
                run_id=run.id,
                operation="planner.propose_next_command",
                provider="azure_openai",
                model="gpt-test",
                latency_ms=800,
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
            )
        )
        session.commit()

        app.dependency_overrides[routes_metrics.get_session] = lambda: session
        try:
            response = TestClient(app).get("/api/metrics/summary?input_cost_per_1m_tokens=2&output_cost_per_1m_tokens=6")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_count"] == 1
    assert payload["submitted_run_count"] == 1
    assert payload["run_latency"]["average_ms"] == 12000
    assert payload["command_latency"]["average_ms"] == 250
    assert payload["llm"]["request_count"] == 1
    assert payload["llm"]["tokens"]["total_tokens"] == 1500
    assert payload["llm"]["tokens"]["estimated_cost_usd"] == 0.005


def test_run_metrics_404_for_unknown_run():
    with make_session() as session:
        app.dependency_overrides[routes_metrics.get_session] = lambda: session
        try:
            response = TestClient(app).get("/api/metrics/runs/missing")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 404
