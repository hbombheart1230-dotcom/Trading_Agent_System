from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .common import AvailabilityStatus


class SourceRootStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    status: AvailabilityStatus
    readable: bool


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    service: str
    checked_at: datetime
    read_only: bool = True
    execution_callable: bool = False
    exposure_profile: str
    public_mode: bool


class ReadinessResponse(HealthResponse):
    sources: list[SourceRootStatus]
