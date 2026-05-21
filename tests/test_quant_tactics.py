from __future__ import annotations

from libs.runtime.quant.contracts import FactorSnapshot, QuantDecision, TacticScorecard
from libs.runtime.quant.tactics import (
    canonical_tactic_key,
    default_tactic_for_playbook,
    normalize_tactic_id,
    normalize_tactical_subtype,
    tactic_catalog,
    tactic_candidates_for_playbook,
)
from libs.strategies.playbook_contracts import playbook_inventory


def test_legacy_leader_pullback_is_alias_only() -> None:
    assert normalize_tactic_id("leader_vwap_reclaim_pullback", playbook="pullback") == "vwap_reclaim_pullback"
    assert canonical_tactic_key("leader_vwap_reclaim_pullback") == "vwap_reclaim_pullback"
    assert "leader_vwap_reclaim_pullback" not in tactic_catalog()["tactic_ids"]


def test_pullback_subtype_aliases_preserve_existing_split() -> None:
    assert normalize_tactical_subtype("theme_leader_pullback", tactic_id="vwap_reclaim_pullback") == "theme_confirmed_pullback"
    assert normalize_tactical_subtype("liquidity_leader_trend", tactic_id="vwap_reclaim_pullback") == "liquidity_confirmed_pullback"
    assert normalize_tactical_subtype("", tactic_id="vwap_reclaim_pullback") == "vwap_reclaim_setup"
    assert normalize_tactical_subtype("", tactic_id="opening_range_breakout") == "none"


def test_playbook_defaults_and_candidates_are_cataloged() -> None:
    assert default_tactic_for_playbook("breakout") == "opening_range_breakout"
    assert default_tactic_for_playbook("pullback") == "vwap_reclaim_pullback"
    assert default_tactic_for_playbook("unknown") == "defensive_observe"
    assert "lower_vwap_rebound_probe" in tactic_candidates_for_playbook("pullback")
    assert "inverse_hedge_reclaim" in tactic_candidates_for_playbook("defensive")


def test_playbook_inventory_exposes_quant_catalog() -> None:
    inventory = playbook_inventory()
    assert "vwap_reclaim_pullback" in inventory["tactic_ids"]
    assert inventory["legacy_tactic_aliases"]["leader_vwap_reclaim_pullback"] == "vwap_reclaim_pullback"
    assert inventory["default_tactic_by_playbook"]["pullback"] == "vwap_reclaim_pullback"
    assert "none" not in inventory["tactical_subtypes"]


def test_quant_contracts_are_serializable_dicts() -> None:
    assert FactorSnapshot(tactic_id="vwap_reclaim_pullback", factors={"vwap_distance_pct": -0.2}).as_dict()[
        "factors"
    ]["vwap_distance_pct"] == -0.2
    assert TacticScorecard(tactic_id="vwap_reclaim_pullback", sample_count=3).as_dict()["sample_count"] == 3
    assert QuantDecision(tactic_id="vwap_reclaim_pullback", blockers=("cost_floor_not_met",)).as_dict()[
        "behavior_effect"
    ] == "observation_only"

