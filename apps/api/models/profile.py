from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExposureProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    public_mode: bool
    checked_at: datetime
    read_only: bool = True
    execution_callable: bool = False
    execution_mode: str = "SIMULATION_MOCK"
    report_content_access: bool
    metric_contract: str = "SAME_AS_PRIVATE_PROFILE"
    redactions: list[str]
