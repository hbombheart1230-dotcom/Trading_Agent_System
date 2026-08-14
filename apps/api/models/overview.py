from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .common import AvailabilityStatus
from .performance import PerformanceSummaryResponse
from .portfolio import PortfolioResponse


class OverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    mode: str
    read_only: bool = True
    performance: PerformanceSummaryResponse
    portfolio: PortfolioResponse
    issues: list[str]
