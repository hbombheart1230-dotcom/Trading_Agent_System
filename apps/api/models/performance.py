from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, CostBasis, MetricValue, Provenance


class PerformanceCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    win_count: int = Field(ge=0)
    loss_count: int = Field(ge=0)
    flat_count: int = Field(ge=0)


class PerformancePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    status: AvailabilityStatus
    trade_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    average_trade_return_pct: float | None
    realized_pnl_krw: float | None
    cumulative_realized_pnl_krw: float | None


class PerformanceSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    start_date: date
    end_date: date
    generated_at: datetime
    cost_basis: CostBasis
    counts: PerformanceCounts
    win_rate: MetricValue
    average_trade_return: MetricValue
    average_gain: MetricValue
    average_loss: MetricValue
    realized_pnl: MetricValue
    gross_pnl: MetricValue
    total_cost: MetricValue
    cost_drag: MetricValue
    profit_factor: MetricValue
    max_drawdown: MetricValue
    source_day_count: int = Field(ge=0)
    invalid_source_day_count: int = Field(ge=0)
    provenance: Provenance


class PerformanceSeriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    start_date: date
    end_date: date
    generated_at: datetime
    cost_basis: CostBasis
    series_kind: str
    points: list[PerformancePoint]
    provenance: Provenance
