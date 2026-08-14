from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, Provenance


class LlmLatencySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    observed_count: int = Field(ge=0)
    average_ms: float | None = Field(default=None, ge=0)
    p95_ms: float | None = Field(default=None, ge=0)
    maximum_ms: float | None = Field(default=None, ge=0)
    coverage: float | None = Field(default=None, ge=0, le=1)
    recent_window_only: bool = True


class LlmTokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    reason: str | None = None


class LlmRoleUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    label: str
    configured_model: str
    fallback_model: str | None = None
    configuration_source: str
    observed_model: str | None = None
    call_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    latest_call_at: datetime | None = None
    state: str


class LlmStageUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_key: str
    stage_label: str
    stage_index: int | None = None
    call_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    model: str | None = None
    latest_call_at: datetime | None = None


class LlmRecentCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    role: str
    stage: str
    model: str
    status: str
    latency_ms: float | None = Field(default=None, ge=0)
    attempts: int | None = Field(default=None, ge=0)
    error_type: str | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class LlmOperationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    provider: str
    total_calls: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    success_rate: float | None = Field(default=None, ge=0, le=1)
    latency: LlmLatencySummary
    token_usage: LlmTokenUsage
    roles: list[LlmRoleUsage]
    stages: list[LlmStageUsage]
    recent_calls: list[LlmRecentCall]
    issues: list[str]
    provenance: Provenance
