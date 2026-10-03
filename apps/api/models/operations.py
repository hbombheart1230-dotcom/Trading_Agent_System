from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, Provenance


class OperationsTimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    phase: str
    title: str
    expected_time_kst: str | None
    actual_time: datetime | None
    status: str
    detail: str | None
    source: str
    trade_id: str | None = None


class OperationsAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    severity: str
    title: str
    detail: str
    source: str
    observed_at: datetime | None = None


class OperationsComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    current_value: str | None
    previous_value: str | None
    change: str


class OperationsDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    previous_day: date | None
    generated_at: datetime
    read_only: bool = True
    execution_callable: bool = False
    timeline: list[OperationsTimelineItem]
    alerts: list[OperationsAlert]
    comparison: list[OperationsComparisonRow]
    trade_count: int = Field(ge=0)
    issues: list[str]
    provenance: Provenance
