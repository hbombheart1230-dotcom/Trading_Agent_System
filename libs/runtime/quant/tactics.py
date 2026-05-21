from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from libs.runtime.quant.contracts import (
    LEGACY_TACTIC_ALIASES,
    TACTIC_IDS,
    TACTICAL_SUBTYPE_ALIASES,
    TACTICAL_SUBTYPES,
    TacticId,
)


DEFAULT_TACTIC_BY_PLAYBOOK: Mapping[str, TacticId] = {
    "breakout": "opening_range_breakout",
    "pullback": "vwap_reclaim_pullback",
    "reversal": "reversal_reclaim",
    "defensive": "defensive_observe",
}

TACTIC_CANDIDATES_BY_PLAYBOOK: Mapping[str, Tuple[TacticId, ...]] = {
    "breakout": ("opening_range_breakout", "volume_breakout", "opening_gap_momentum"),
    "pullback": ("vwap_reclaim_pullback", "lower_vwap_rebound_probe", "cost_aware_scalp"),
    "reversal": ("reversal_reclaim", "mean_reversion_probe", "lower_vwap_rebound_probe"),
    "defensive": ("defensive_observe", "cost_aware_scalp", "inverse_hedge_reclaim"),
}

TACTIC_DEFAULT_RUNNER_UP_RANK: Mapping[TacticId, int] = {
    "defensive_observe": 3,
    "vwap_reclaim_pullback": 5,
    "lower_vwap_rebound_probe": 5,
    "mean_reversion_probe": 5,
    "reversal_reclaim": 5,
    "cost_aware_scalp": 5,
    "inverse_hedge_reclaim": 5,
    "opening_gap_momentum": 7,
    "opening_range_breakout": 7,
    "volume_breakout": 7,
    "trend_continuation": 7,
    "event_theme_momentum": 7,
}


def normalize_playbook(value: Any, *, default: str = "") -> str:
    raw = str(value or "").strip().lower()
    if raw in ("breakout", "pullback", "reversal", "defensive"):
        return raw
    return str(default or "")


def default_tactic_for_playbook(playbook: str) -> TacticId:
    mode = normalize_playbook(playbook, default="defensive")
    return str(DEFAULT_TACTIC_BY_PLAYBOOK.get(mode) or "defensive_observe")


def normalize_tactic_id(value: Any, *, playbook: str) -> TacticId:
    raw = str(value or "").strip().lower()
    raw = str(LEGACY_TACTIC_ALIASES.get(raw, raw))
    if raw in TACTIC_IDS:
        return raw
    return default_tactic_for_playbook(playbook)


def canonical_tactic_key(value: Any) -> TacticId:
    raw = str(value or "").strip().lower()
    raw = str(LEGACY_TACTIC_ALIASES.get(raw, raw))
    return raw if raw in TACTIC_IDS else ""


def normalize_tactical_subtype(value: Any, *, tactic_id: str) -> str:
    raw = str(value or "").strip().lower()
    raw = str(TACTICAL_SUBTYPE_ALIASES.get(raw, raw))
    if raw in TACTICAL_SUBTYPES:
        return raw
    if normalize_tactic_id(tactic_id, playbook="pullback") == "vwap_reclaim_pullback":
        return "vwap_reclaim_setup"
    return "none"


def tactic_candidates_for_playbook(playbook: str) -> List[TacticId]:
    mode = normalize_playbook(playbook, default="defensive")
    return list(TACTIC_CANDIDATES_BY_PLAYBOOK.get(mode) or ("defensive_observe",))


def tactic_catalog() -> Dict[str, Any]:
    return {
        "tactic_ids": list(TACTIC_IDS),
        "legacy_aliases": dict(LEGACY_TACTIC_ALIASES),
        "tactical_subtypes": list(TACTICAL_SUBTYPES),
        "subtype_aliases": dict(TACTICAL_SUBTYPE_ALIASES),
        "default_tactic_by_playbook": dict(DEFAULT_TACTIC_BY_PLAYBOOK),
        "candidates_by_playbook": {
            key: list(value)
            for key, value in TACTIC_CANDIDATES_BY_PLAYBOOK.items()
        },
        "runner_up_default_rank": dict(TACTIC_DEFAULT_RUNNER_UP_RANK),
    }
