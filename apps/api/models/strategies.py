from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, CostBasis, Provenance


class StrategyDimension(StrEnum):
    PLAYBOOK = "playbook"
    TACTIC = "tactic"
    SETUP = "setup"
    HORIZON = "horizon"
    THEME = "theme"


class StrategyPerformanceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    trade_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    win_count: int = Field(ge=0)
    loss_count: int = Field(ge=0)
    flat_count: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_return_pct: float | None
    profit_factor: float | None
    max_drawdown_pct: float | None


class StrategyPerformanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    start_date: date
    end_date: date
    generated_at: datetime
    dimension: StrategyDimension
    cost_basis: CostBasis
    trade_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    items: list[StrategyPerformanceItem]
    issues: list[str]
    provenance: Provenance
