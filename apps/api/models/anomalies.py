from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, CostBasis, Provenance


class AnomalySeverity(StrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    WATCH = "WATCH"


class AnomalyCategory(StrEnum):
    DATA_FRESHNESS = "DATA_FRESHNESS"
    ARTIFACT_INTEGRITY = "ARTIFACT_INTEGRITY"
    COST_SPIKE = "COST_SPIKE"
    REPEATED_LOSS = "REPEATED_LOSS"
    EARLY_LOSS_EXIT = "EARLY_LOSS_EXIT"
    MISSED_OPPORTUNITY = "MISSED_OPPORTUNITY"


class AnomalyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    observed_value: float | int | None
    threshold_value: float | int | None
    comparator: str
    unit: str
    sample_count: int = Field(ge=0)
    cost_basis: CostBasis = CostBasis.NOT_APPLICABLE


class OperationalAnomaly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly_id: str
    category: AnomalyCategory
    severity: AnomalySeverity
    title: str
    summary: str
    affected_symbols: list[str]
    evidence: AnomalyEvidence
    source: str
    observed_at: datetime | None = None


class AnomalyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    policy_version: str
    behavior_effect: str = "OBSERVATION_ONLY"
    critical_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    watch_count: int = Field(ge=0)
    evaluated_trade_count: int = Field(ge=0)
    evaluated_opportunity_count: int = Field(ge=0)
    evaluated_rule_count: int = Field(ge=0)
    items: list[OperationalAnomaly]
    issues: list[str]
    provenance: Provenance
