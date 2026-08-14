from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus, CostBasis, Provenance


class OpportunityBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    candidate_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    missed_opportunity_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    adverse_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_latest_return_pct: float | None
    decision: str | None


class OpportunitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    observed_at: datetime | None
    price: float | None
    score: float | None
    state: str | None
    probe_candidate: bool
    probe_near_miss: bool
    blocker_reasons: list[str]
    market_state: str | None
    market_relative_strength: float | None
    vwap_distance_pct: float | None
    volume_ratio: float | None
    breakout_5m: bool | None


class OpportunityFunnelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    behavior_effect: str
    raw_candidate_count: int = Field(ge=0)
    deduplicated_candidate_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    current_signal_count: int = Field(ge=0)
    probe_candidate_count: int = Field(ge=0)
    probe_near_miss_count: int = Field(ge=0)
    blockers: list[OpportunityBlocker]
    current_signals: list[OpportunitySignal]
    issues: list[str]
    provenance: Provenance


class ForwardCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon: str
    status: str
    gross_return_pct: float | None
    live_equivalent_net_return_pct: float | None
    mock_broker_net_return_pct: float | None
    maximum_favorable_excursion_pct: float | None
    maximum_adverse_excursion_pct: float | None


class OpportunityOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    symbol: str
    symbol_name: str | None
    observed_at: datetime | None
    reference_entry_at: datetime | None
    rank: int | None
    score: float | None
    source_labels: list[str]
    prospective_eligible: bool
    checkpoints: list[ForwardCheckpoint]


class OpportunityOutcomesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    day: date
    generated_at: datetime
    behavior_effect: str
    cost_basis: CostBasis
    opportunity_count: int = Field(ge=0)
    observed_checkpoint_count: int = Field(ge=0)
    expected_checkpoint_count: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    outcomes: list[OpportunityOutcome]
    issues: list[str]
    provenance: Provenance
