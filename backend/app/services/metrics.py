from datetime import datetime

from sqlmodel import Session, select

from app.db.models import Action, AuditEvent, CommandResult, LlmUsageMetric, Run, TerminalCommand, utc_now
from app.schemas.metrics import LatencyStats, LlmMetricsRead, LlmUsageMetricRead, MetricsSummaryRead, RunMetricsRead, TokenCostSummary
from app.schemas.runs import RunStatus


TERMINAL_RUN_STATUSES = {RunStatus.SUBMITTED.value, RunStatus.ABORTED.value, RunStatus.FAILED.value}


class MetricsService:
    def __init__(self, session: Session):
        self.session = session

    def summary(
        self,
        input_cost_per_1m_tokens: float | None = None,
        output_cost_per_1m_tokens: float | None = None,
    ) -> MetricsSummaryRead:
        runs = list(self.session.exec(select(Run)))
        actions = list(self.session.exec(select(Action)))
        command_results = list(self.session.exec(select(CommandResult)))
        terminal_commands = list(self.session.exec(select(TerminalCommand)))
        audit_events = list(self.session.exec(select(AuditEvent)))
        llm_metrics = list(self.session.exec(select(LlmUsageMetric).order_by(LlmUsageMetric.id)))
        now = utc_now()

        return MetricsSummaryRead(
            generated_at=now,
            run_count=len(runs),
            active_run_count=sum(1 for run in runs if run.status not in TERMINAL_RUN_STATUSES),
            submitted_run_count=sum(1 for run in runs if run.status == RunStatus.SUBMITTED.value),
            aborted_run_count=sum(1 for run in runs if run.status == RunStatus.ABORTED.value),
            failed_run_count=sum(1 for run in runs if run.status == RunStatus.FAILED.value),
            action_count=len(actions),
            command_result_count=len(command_results),
            terminal_command_count=len(terminal_commands),
            audit_event_count=len(audit_events),
            run_latency=_latency_stats([_duration_ms(run.created_at, run.updated_at) for run in runs]),
            command_latency=_latency_stats([_duration_ms(result.started_at, result.ended_at) for result in command_results if result.ended_at is not None]),
            terminal_command_latency=_latency_stats(
                [_duration_ms(command.started_at, command.ended_at) for command in terminal_commands if command.started_at is not None and command.ended_at is not None]
            ),
            llm=_llm_metrics(llm_metrics, input_cost_per_1m_tokens, output_cost_per_1m_tokens),
        )

    def run_metrics(
        self,
        run_id: str,
        input_cost_per_1m_tokens: float | None = None,
        output_cost_per_1m_tokens: float | None = None,
    ) -> RunMetricsRead | None:
        run = self.session.get(Run, run_id)
        if run is None:
            return None
        actions = list(self.session.exec(select(Action).where(Action.run_id == run_id)))
        action_ids = [action.id for action in actions if action.id is not None]
        command_results = list(self.session.exec(select(CommandResult).where(CommandResult.action_id.in_(action_ids)))) if action_ids else []
        terminal_commands = list(self.session.exec(select(TerminalCommand).where(TerminalCommand.run_id == run_id)))
        audit_events = list(self.session.exec(select(AuditEvent).where(AuditEvent.run_id == run_id)))
        llm_metrics = list(self.session.exec(select(LlmUsageMetric).where(LlmUsageMetric.run_id == run_id).order_by(LlmUsageMetric.id)))

        return RunMetricsRead(
            run_id=run.id,
            ticket_id=run.ticket_id,
            status=run.status,
            created_at=run.created_at,
            updated_at=run.updated_at,
            run_duration_ms=_duration_ms(run.created_at, run.updated_at),
            action_count=len(actions),
            command_result_count=len(command_results),
            successful_command_count=sum(1 for result in command_results if result.exit_code == 0 and not result.timed_out),
            failed_command_count=sum(1 for result in command_results if result.exit_code not in (0, None) or result.timed_out),
            timed_out_command_count=sum(1 for result in command_results if result.timed_out),
            terminal_command_count=len(terminal_commands),
            audit_event_count=len(audit_events),
            command_latency=_latency_stats([_duration_ms(result.started_at, result.ended_at) for result in command_results if result.ended_at is not None]),
            terminal_command_latency=_latency_stats(
                [_duration_ms(command.started_at, command.ended_at) for command in terminal_commands if command.started_at is not None and command.ended_at is not None]
            ),
            llm=_llm_metrics(llm_metrics, input_cost_per_1m_tokens, output_cost_per_1m_tokens),
        )

    def llm_metrics(
        self,
        run_id: str | None = None,
        input_cost_per_1m_tokens: float | None = None,
        output_cost_per_1m_tokens: float | None = None,
    ) -> LlmMetricsRead:
        statement = select(LlmUsageMetric).order_by(LlmUsageMetric.id)
        if run_id is not None:
            statement = statement.where(LlmUsageMetric.run_id == run_id)
        return _llm_metrics(list(self.session.exec(statement)), input_cost_per_1m_tokens, output_cost_per_1m_tokens)


def _duration_ms(start: datetime, end: datetime | None) -> int:
    if end is None:
        end = utc_now()
    return max(0, round((end - start).total_seconds() * 1000))


def _latency_stats(values: list[int]) -> LatencyStats:
    if not values:
        return LatencyStats()
    return LatencyStats(count=len(values), average_ms=round(sum(values) / len(values), 2), min_ms=min(values), max_ms=max(values))


def _llm_metrics(
    metrics: list[LlmUsageMetric],
    input_cost_per_1m_tokens: float | None,
    output_cost_per_1m_tokens: float | None,
) -> LlmMetricsRead:
    by_operation: dict[str, TokenCostSummary] = {}
    requests = []
    for metric in metrics:
        estimated_cost = _estimated_cost(metric.prompt_tokens, metric.completion_tokens, input_cost_per_1m_tokens, output_cost_per_1m_tokens)
        requests.append(
            LlmUsageMetricRead(
                id=metric.id or 0,
                run_id=metric.run_id,
                operation=metric.operation,
                provider=metric.provider,
                model=metric.model,
                latency_ms=metric.latency_ms,
                prompt_tokens=metric.prompt_tokens,
                completion_tokens=metric.completion_tokens,
                total_tokens=metric.total_tokens,
                estimated_cost_usd=estimated_cost,
                error=metric.error,
                created_at=metric.created_at,
            )
        )
        operation_summary = by_operation.setdefault(metric.operation, TokenCostSummary(estimated_cost_usd=0 if estimated_cost is not None else None))
        operation_summary.prompt_tokens += metric.prompt_tokens
        operation_summary.completion_tokens += metric.completion_tokens
        operation_summary.total_tokens += metric.total_tokens
        if estimated_cost is None:
            operation_summary.estimated_cost_usd = None
        elif operation_summary.estimated_cost_usd is not None:
            operation_summary.estimated_cost_usd = round(operation_summary.estimated_cost_usd + estimated_cost, 8)

    prompt_tokens = sum(metric.prompt_tokens for metric in metrics)
    completion_tokens = sum(metric.completion_tokens for metric in metrics)
    total_tokens = sum(metric.total_tokens for metric in metrics)
    return LlmMetricsRead(
        request_count=len(metrics),
        error_count=sum(1 for metric in metrics if metric.error),
        latency=_latency_stats([metric.latency_ms for metric in metrics]),
        tokens=TokenCostSummary(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=_estimated_cost(prompt_tokens, completion_tokens, input_cost_per_1m_tokens, output_cost_per_1m_tokens),
        ),
        by_operation=by_operation,
        requests=requests,
    )


def _estimated_cost(
    prompt_tokens: int,
    completion_tokens: int,
    input_cost_per_1m_tokens: float | None,
    output_cost_per_1m_tokens: float | None,
) -> float | None:
    if input_cost_per_1m_tokens is None or output_cost_per_1m_tokens is None:
        return None
    return round((prompt_tokens / 1_000_000 * input_cost_per_1m_tokens) + (completion_tokens / 1_000_000 * output_cost_per_1m_tokens), 8)
