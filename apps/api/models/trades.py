from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, CostBasis, Provenance


class TradeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_id: str
    day: date
    symbol: str
    symbol_name: str | None
    themes: list[str]
    status: str
    entry_time: datetime | None
    exit_time: datetime | None
    entry_price: float | None
    exit_price: float | None
    quantity: float | None
    hold_seconds: float | None
    realized_pnl_krw: float | None
    realized_return_pct: float | None
    result: str | None
    playbook: str | None
    tactic_id: str | None
    strategy_horizon: str | None
    scanner_rank: int | None
    cost_basis: CostBasis = CostBasis.MOCK_BROKER_NET
    artifact_status: AvailabilityStatus
    artifact_scope: str


class TradeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    start_date: date
    end_date: date
    generated_at: datetime
    total_count: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    items: list[TradeSummary]
    issue_count: int = Field(ge=0)
    issues_truncated: bool
    issues: list[str]
    provenance: Provenance


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    stage: str
    action: str
    reason: str | None
    price: float | None
    quantity: float | None
    source: str


class DecisionLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    playbook: str | None
    tactic_id: str | None
    strategist_horizon: str | None
    commander_horizon: str | None
    scanner_rank: int | None
    scanner_score: float | None
    scanner_chart_fit_score: float | None
    selection_basis: str | None
    monitor_entry_reason: str | None
    monitor_exit_trigger: str | None
    tactic_suitability_score: float | None


class PostExitCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon: str
    status: str
    observed_at: datetime | None
    price: float | None
    return_pct: float | None


class ArtifactIntegrity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    lifecycle_status: str | None
    lifecycle_completeness: str | None
    completeness_score: float | None
    broker_reconciliation_status: str | None
    agent_sources: dict[str, str]
    evaluation_eligible: bool
    exclusion_reason: str | None
    issues: list[str]


class TradeDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    generated_at: datetime
    trade: TradeSummary
    decisions: DecisionLineage
    timeline: list[TimelineEvent]
    post_exit: list[PostExitCheckpoint]
    integrity: ArtifactIntegrity
    provenance: Provenance
