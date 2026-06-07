from datetime import datetime

from pydantic import BaseModel, Field


class LatencyStats(BaseModel):
    count: int = 0
    average_ms: float | None = None
    min_ms: int | None = None
    max_ms: int | None = None


class TokenCostSummary(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


class LlmUsageMetricRead(BaseModel):
    id: int
    run_id: str | None = None
    operation: str
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    error: str | None = None
    created_at: datetime


class LlmMetricsRead(BaseModel):
    request_count: int = 0
    error_count: int = 0
    latency: LatencyStats = Field(default_factory=LatencyStats)
    tokens: TokenCostSummary = Field(default_factory=TokenCostSummary)
    by_operation: dict[str, TokenCostSummary] = Field(default_factory=dict)
    requests: list[LlmUsageMetricRead] = Field(default_factory=list)


class RunMetricsRead(BaseModel):
    run_id: str
    ticket_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    run_duration_ms: int
    action_count: int = 0
    command_result_count: int = 0
    successful_command_count: int = 0
    failed_command_count: int = 0
    timed_out_command_count: int = 0
    terminal_command_count: int = 0
    audit_event_count: int = 0
    command_latency: LatencyStats = Field(default_factory=LatencyStats)
    terminal_command_latency: LatencyStats = Field(default_factory=LatencyStats)
    llm: LlmMetricsRead = Field(default_factory=LlmMetricsRead)


class MetricsSummaryRead(BaseModel):
    generated_at: datetime
    run_count: int = 0
    active_run_count: int = 0
    submitted_run_count: int = 0
    aborted_run_count: int = 0
    failed_run_count: int = 0
    action_count: int = 0
    command_result_count: int = 0
    terminal_command_count: int = 0
    audit_event_count: int = 0
    run_latency: LatencyStats = Field(default_factory=LatencyStats)
    command_latency: LatencyStats = Field(default_factory=LatencyStats)
    terminal_command_latency: LatencyStats = Field(default_factory=LatencyStats)
    llm: LlmMetricsRead = Field(default_factory=LlmMetricsRead)
