from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple


TacticId = str

TACTIC_IDS: Tuple[TacticId, ...] = (
    "trend_continuation",
    "opening_gap_momentum",
    "opening_range_breakout",
    "volume_breakout",
    "vwap_reclaim_pullback",
    "lower_vwap_rebound_probe",
    "mean_reversion_probe",
    "event_theme_momentum",
    "reversal_reclaim",
    "cost_aware_scalp",
    "defensive_observe",
    "inverse_hedge_reclaim",
)

LEGACY_TACTIC_ALIASES: Mapping[str, TacticId] = {
    "leader_vwap_reclaim_pullback": "vwap_reclaim_pullback",
    "theme_leader_pullback": "vwap_reclaim_pullback",
}

PULLBACK_SUBTYPES: Tuple[str, ...] = (
    "theme_confirmed_pullback",
    "market_representative_pullback",
    "liquidity_confirmed_pullback",
    "vwap_reclaim_setup",
    "weak_fallback_pullback",
)

TACTICAL_SUBTYPES: Tuple[str, ...] = (*PULLBACK_SUBTYPES, "none")

TACTICAL_SUBTYPE_ALIASES: Mapping[str, str] = {
    "theme_leader_pullback": "theme_confirmed_pullback",
    "liquidity_leader_trend": "liquidity_confirmed_pullback",
    "vwap_reclaim_pullback": "vwap_reclaim_setup",
}


@dataclass(frozen=True)
class FactorSnapshot:
    """Deterministic factor snapshot shared across runtime agents."""

    tactic_id: TacticId = ""
    factors: Mapping[str, Any] = field(default_factory=dict)
    missing: Tuple[str, ...] = ()
    source: str = "quant_factor_snapshot.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "tactic_id": self.tactic_id,
            "factors": dict(self.factors or {}),
            "missing": list(self.missing or ()),
        }


@dataclass(frozen=True)
class TacticScorecard:
    """Empirical tactic performance summary with small-sample awareness."""

    tactic_id: TacticId
    sample_count: int = 0
    win_rate: float | None = None
    avg_return_pct: float | None = None
    confidence: str = "low"
    loss_clusters: Tuple[str, ...] = ()
    source: str = "quant_tactic_scorecard.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "tactic_id": self.tactic_id,
            "sample_count": int(self.sample_count or 0),
            "win_rate": self.win_rate,
            "avg_return_pct": self.avg_return_pct,
            "confidence": self.confidence,
            "loss_clusters": list(self.loss_clusters or ()),
        }


@dataclass(frozen=True)
class QuantDecision:
    """Observation or behavior recommendation emitted by the quant layer."""

    tactic_id: TacticId = ""
    decision: str = "observe"
    score: float | None = None
    reasons: Tuple[str, ...] = ()
    blockers: Tuple[str, ...] = ()
    behavior_effect: str = "observation_only"
    source: str = "quant_decision.v1"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "tactic_id": self.tactic_id,
            "decision": self.decision,
            "score": self.score,
            "reasons": list(self.reasons or ()),
            "blockers": list(self.blockers or ()),
            "behavior_effect": self.behavior_effect,
        }

