from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    NO_DATA = "NO_DATA"
    ERROR = "ERROR"


class CostBasis(StrEnum):
    GROSS = "GROSS"
    MOCK_BROKER_NET = "MOCK_BROKER_NET"
    LIVE_EQUIVALENT_NET = "LIVE_EQUIVALENT_NET"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    generated_at: datetime | None = None
    as_of: datetime | None = None
    sample_count: int | None = Field(default=None, ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)


class MetricValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | int | None
    unit: str
    status: AvailabilityStatus
    cost_basis: CostBasis = CostBasis.NOT_APPLICABLE
    provenance: Provenance
    reason: str | None = None
