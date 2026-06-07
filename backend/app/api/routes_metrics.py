from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.metrics import LlmMetricsRead, MetricsSummaryRead, RunMetricsRead
from app.services.metrics import MetricsService


router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummaryRead)
def metrics_summary(
    input_cost_per_1m_tokens: float | None = Query(default=None, ge=0),
    output_cost_per_1m_tokens: float | None = Query(default=None, ge=0),
    session: Session = Depends(get_session),
) -> MetricsSummaryRead:
    return MetricsService(session).summary(input_cost_per_1m_tokens, output_cost_per_1m_tokens)


@router.get("/runs/{run_id}", response_model=RunMetricsRead)
def run_metrics(
    run_id: str,
    input_cost_per_1m_tokens: float | None = Query(default=None, ge=0),
    output_cost_per_1m_tokens: float | None = Query(default=None, ge=0),
    session: Session = Depends(get_session),
) -> RunMetricsRead:
    metrics = MetricsService(session).run_metrics(run_id, input_cost_per_1m_tokens, output_cost_per_1m_tokens)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Run was not found")
    return metrics


@router.get("/llm", response_model=LlmMetricsRead)
def llm_metrics(
    run_id: str | None = None,
    input_cost_per_1m_tokens: float | None = Query(default=None, ge=0),
    output_cost_per_1m_tokens: float | None = Query(default=None, ge=0),
    session: Session = Depends(get_session),
) -> LlmMetricsRead:
    return MetricsService(session).llm_metrics(run_id, input_cost_per_1m_tokens, output_cost_per_1m_tokens)
