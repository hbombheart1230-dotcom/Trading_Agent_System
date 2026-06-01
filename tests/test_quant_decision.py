from __future__ import annotations

from libs.runtime.quant.decision import build_entry_quant_decision, build_exit_quant_decision
from libs.runtime.quant.enforcement import build_entry_quant_enforcement


def test_entry_quant_decision_marks_cost_and_volume_blockers():
    out = build_entry_quant_decision(
        {
            "reason": "volume_confirmation_missing",
            "failed_checks": ["volume_confirmation_missing"],
            "entry_cost_filter": {"passed": False, "cost_adjusted_edge_pct": -0.001},
            "cost_adjusted_edge_ok": False,
            "cost_adjusted_edge_pct": -0.001,
            "cost_drag_pct": 0.002,
        },
        selected={
            "playbook": "pullback",
            "tactic_suitability": {"score": 0.42, "tier": "weak"},
        },
        factor_snapshot={
            "source": "quant_monitor_entry_factor_snapshot.v1",
            "tactic_id": "vwap_reclaim_pullback",
            "factors": {"cost_floor_state": "not_met"},
            "missing": [],
        },
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    assert out["schema_version"] == "quant_entry_decision.v1"
    assert out["decision"] == "block_recommended"
    assert "cost_edge_fail" in out["blockers"]
    assert "volume_confirmation_missing" in out["blockers"]
    assert "weak_tactic_suitability" in out["warnings"]
    assert out["commander_override_required"] is True
    assert out["behavior_effect"] == "observation_only"


def test_lower_vwap_probe_downgrades_pullback_maturity_to_warning():
    out = build_entry_quant_decision(
        {
            "reason": "pullback_not_mature",
            "cost_adjusted_edge_ok": True,
            "entry_cost_filter": {"passed": True},
        },
        selected={"playbook": "pullback", "tactic_suitability": {"score": 0.71, "tier": "watch"}},
        factor_snapshot={
            "source": "quant_monitor_entry_factor_snapshot.v1",
            "tactic_id": "lower_vwap_rebound_probe",
            "factors": {"cost_floor_state": "met"},
            "missing": [],
        },
        tactic_id="lower_vwap_rebound_probe",
        playbook="pullback",
    )

    assert out["decision"] == "wait"
    assert "pullback_not_mature" not in out["blockers"]
    assert "pullback_not_mature" in out["warnings"]


def test_lower_vwap_probe_weak_suitability_blocks_entry():
    out = build_entry_quant_decision(
        {
            "reason": "lower_vwap_rebound_probe_entry",
            "cost_adjusted_edge_ok": True,
            "entry_cost_filter": {"passed": True},
            "triggered": True,
        },
        selected={"playbook": "pullback", "tactic_suitability": {"score": 0.48, "tier": "weak"}},
        factor_snapshot={
            "source": "quant_monitor_entry_factor_snapshot.v1",
            "tactic_id": "lower_vwap_rebound_probe",
            "factors": {"cost_floor_state": "met"},
            "missing": [],
        },
        tactic_id="lower_vwap_rebound_probe",
        playbook="pullback",
    )

    assert out["decision"] == "block_recommended"
    assert "weak_probe_tactic_suitability" in out["blockers"]
    assert "weak_tactic_suitability" in out["warnings"]


def test_entry_quant_enforcement_blocks_only_configured_hard_blockers():
    out = build_entry_quant_enforcement(
        {
            "decision": "block_recommended",
            "blockers": ["cost_edge_fail", "pullback_not_mature"],
        },
        mode="enforce",
    )

    assert out["blocked"] is True
    assert out["reason"] == "quant_entry_block:cost_edge_fail"
    assert out["behavior_effect"] == "entry_guard_enforced"


def test_entry_quant_enforcement_observe_mode_does_not_block():
    out = build_entry_quant_enforcement(
        {
            "decision": "block_recommended",
            "blockers": ["volume_confirmation_missing"],
        },
        mode="observe",
    )

    assert out["blocked"] is False
    assert out["matched_blockers"] == ["volume_confirmation_missing"]
    assert out["behavior_effect"] == "observation_only"


def test_entry_quant_enforcement_ignores_non_promoted_blockers():
    out = build_entry_quant_enforcement(
        {
            "decision": "block_recommended",
            "blockers": ["pullback_not_mature"],
        },
        mode="enforce",
    )

    assert out["blocked"] is False
    assert out["matched_blockers"] == []


def test_vwap_pullback_weak_or_watch_quality_gate_blocks_live_entry():
    out = build_entry_quant_decision(
        {
            "reason": "pullback_structure_above_vwap_with_volume_confirmation",
            "triggered": True,
            "cost_adjusted_edge_ok": True,
            "entry_cost_filter": {"passed": True},
        },
        selected={"playbook": "pullback", "tactic_suitability": {"score": 0.62, "tier": "watch"}},
        factor_snapshot={
            "source": "quant_monitor_entry_factor_snapshot.v1",
            "tactic_id": "vwap_reclaim_pullback",
            "factors": {
                "cost_floor_state": "met",
                "volume_ok": True,
                "pullback_ok": False,
                "reclaim_ok": False,
                "breakout_ok": False,
                "confidence_score": 0.56,
                "confidence_threshold": 0.55,
            },
            "missing": [],
        },
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )
    enforcement = build_entry_quant_enforcement(out, mode="enforce")

    assert out["decision"] == "block_recommended"
    assert "vwap_pullback_promoted_quality_gate" in out["blockers"]
    assert enforcement["blocked"] is True
    assert enforcement["reason"] == "quant_entry_block:vwap_pullback_promoted_quality_gate"


def test_vwap_pullback_quality_gate_allows_mature_confirmed_setup():
    out = build_entry_quant_decision(
        {
            "reason": "pullback_structure_above_vwap_with_volume_confirmation",
            "triggered": True,
            "cost_adjusted_edge_ok": True,
            "entry_cost_filter": {"passed": True},
        },
        selected={"playbook": "pullback", "tactic_suitability": {"score": 0.64, "tier": "watch"}},
        factor_snapshot={
            "source": "quant_monitor_entry_factor_snapshot.v1",
            "tactic_id": "vwap_reclaim_pullback",
            "factors": {
                "cost_floor_state": "met",
                "volume_ok": True,
                "pullback_ok": True,
                "reclaim_ok": True,
                "breakout_ok": False,
                "confidence_score": 0.61,
                "confidence_threshold": 0.55,
            },
            "missing": [],
        },
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    assert out["decision"] == "entry_ready"
    assert "vwap_pullback_promoted_quality_gate" not in out["blockers"]
    assert "vwap_pullback_mature_confirmed" in out["positive_reasons"]


def test_entry_quant_enforcement_always_enforces_cost_edge_even_if_config_omits_it():
    out = build_entry_quant_enforcement(
        {
            "decision": "block_recommended",
            "blockers": ["cost_edge_fail"],
        },
        mode="enforce",
        enforced_blockers="volume_confirmation_missing",
    )

    assert out["blocked"] is True
    assert out["matched_blockers"] == ["cost_edge_fail"]
    assert out["reason"] == "quant_entry_block:cost_edge_fail"


def test_exit_quant_decision_flags_early_confirmation_pending():
    out = build_exit_quant_decision(
        {
            "triggered": True,
            "reason": "intraday_low_break",
            "position_age_seconds": 35,
            "intraday_low_break_confirmation_required": True,
            "intraday_low_break_confirmation_pending": True,
            "intraday_low_break_confirmed": False,
            "exit_vs_strategy_intent": {
                "actual_hold_sec": 35,
                "expected_hold_window": {"min_sec": 120, "target_sec": 600, "max_sec": 1800},
                "exit_alignment": "early_unproven",
                "alignment_reason": "actual_hold_sec_below_strategy_min_without_hard_exit",
            },
        },
        state={"strategy_horizon_feedback": {"expected_hold_window": {"min_sec": 120, "target_sec": 600, "max_sec": 1800}}},
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    assert out["schema_version"] == "quant_exit_decision.v1"
    assert out["decision"] == "confirm_before_exit_recommended"
    assert out["confirmation_pending"] is True
    assert out["early_exit_flag"] is True
    assert "exit_confirmation_pending" in out["blockers"]
    assert "early_exit_before_expected_min_hold" in out["warnings"]


def test_exit_quant_decision_allows_hard_exit_even_when_early():
    out = build_exit_quant_decision(
        {
            "triggered": True,
            "reason": "stop_loss",
            "position_age_seconds": 20,
            "protective_exit_hard_invalidation": True,
            "exit_vs_strategy_intent": {
                "expected_hold_window": {"min_sec": 120, "target_sec": 600, "max_sec": 1800},
            },
        },
        state={"strategy_horizon_feedback": {"expected_hold_window": {"min_sec": 120, "target_sec": 600, "max_sec": 1800}}},
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    assert out["decision"] == "hard_exit"
    assert out["hard_exit"] is True
    assert out["hold_window_mismatch"] is False
    assert "hard_exit_allowed" in out["positive_reasons"]


def test_exit_quant_decision_does_not_treat_intraday_low_break_deep_as_hard_exit():
    out = build_exit_quant_decision(
        {
            "triggered": True,
            "reason": "intraday_low_break",
            "position_age_seconds": 32,
            "hard_exit": True,
            "protective_exit_hard_invalidation": True,
            "protective_exit_hard_invalidation_reason": "intraday_low_break_deep:0.0065",
            "intraday_low_break_confirmation_required": True,
            "intraday_low_break_confirmation_pending": True,
            "intraday_low_break_confirmed": False,
            "exit_vs_strategy_intent": {
                "expected_hold_window": {"min_sec": 60, "target_sec": 300, "max_sec": 900},
            },
        },
        state={"strategy_horizon_feedback": {"expected_hold_window": {"min_sec": 60, "target_sec": 300, "max_sec": 900}}},
        tactic_id="lower_vwap_rebound_probe",
        playbook="pullback",
    )

    assert out["decision"] == "confirm_before_exit_recommended"
    assert out["hard_exit"] is False
    assert out["confirmation_pending"] is True
    assert "exit_confirmation_pending" in out["blockers"]
