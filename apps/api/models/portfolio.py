from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, MetricValue, Provenance


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    symbol_name: str | None = None
    quantity: float
    average_price: float | None
    current_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    unrealized_return_ratio: float | None
    lifecycle_status: str | None = None
    overnight_action: str | None = None


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    authority: str
    position_count: int = Field(ge=0)
    positions: list[Position]
    total_market_value: MetricValue
    total_unrealized_pnl: MetricValue
    open_order_count: MetricValue
    reconciliation_available: bool
    provenance: Provenance
    issues: list[str]
