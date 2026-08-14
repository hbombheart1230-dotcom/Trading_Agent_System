from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, Provenance


class ReportDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    title: str
    format: str
    available: bool
    size_bytes: int | None = Field(default=None, ge=0)


class ReportCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    trade_id: str
    generated_at: datetime
    reports: list[ReportDescriptor]
    provenance: Provenance


class ReportContentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    trade_id: str
    report_id: str
    title: str
    format: str
    generated_at: datetime
    markdown: str | None = None
    json_content: dict[str, Any] | list[Any] | None = None
    provenance: Provenance
