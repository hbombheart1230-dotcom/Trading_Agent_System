from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, Provenance


class MarketMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    category: str
    value: float | None
    change: float | None
    change_pct: float | None
    unit: str
    status: str
    source: str | None
    role: str | None


class MarketBreadth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rising: int = Field(ge=0)
    falling: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    breadth_ratio: float | None = Field(default=None, ge=-1.0, le=1.0)


class MarketSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    source_generated_at: datetime | None
    sentiment_score: float | None
    sentiment_reason: str | None
    breadth: MarketBreadth | None
    metrics: list[MarketMetric]
    warning_count: int = Field(ge=0)
    warnings: list[str]
    provenance: Provenance


class MarketSeriesPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    source_generated_at: datetime | None
    value: float | None
    change: float | None
    change_pct: float | None
    status: str


class MarketSeriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    start_date: date
    end_date: date
    generated_at: datetime
    metric_key: str
    label: str | None
    unit: str | None
    points: list[MarketSeriesPoint]
    missing_day_count: int = Field(ge=0)
    provenance: Provenance
