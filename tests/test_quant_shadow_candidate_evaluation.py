from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.quant_shadow_candidate_evaluation import (
    build_quant_shadow_candidate_evaluation,
    load_quant_shadow_candidate_payloads,
    render_quant_shadow_candidate_evaluation_lines,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_quant_shadow_candidate_evaluation_counts_roles_and_blockers() -> None:
    payload = {
        "candidates": [
            {
                "symbol": "005930",
                "shadow_role": "top_pick",
                "evaluated": True,
                "would_enter": False,
                "guard_blocked": True,
                "reason": "volume_confirmation_missing",
                "quant_tactic_id": "vwap_reclaim_pullback",
                "tactic_suitability_tier": "weak",
                "entry_quant_cost_floor_state": "not_met",
                "primary_failure_axis": "volume",
            },
            {
                "symbol": "000660",
                "shadow_role": "runner_up_evaluated",
                "evaluated": True,
                "would_enter": True,
                "reason": "ready",
                "quant_tactic_id": "breakout_continuation",
                "tactic_suitability_tier": "strong",
            },
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["behavior_effect"] == "observation_only"
    assert evaluation["payload_count"] == 1
    assert evaluation["candidate_count"] == 2
    assert evaluation["evaluated_count"] == 2
    assert evaluation["would_enter_count"] == 1
    assert evaluation["guard_blocked_count"] == 1
    assert evaluation["by_role"][0] == {"name": "top_pick", "count": 1}
    assert {"name": "volume_confirmation_missing", "count": 1} in evaluation["by_reason"]
    assert evaluation["promotion_candidate"]["candidate"] == "cost_edge"
    assert evaluation["promotion_candidate"]["behavior_effect"] == "recommendation_only"
    lines = "\n".join(render_quant_shadow_candidate_evaluation_lines(evaluation))
    assert "Quant Shadow Candidates" in lines
    assert "would-enter 1" in lines
    assert "Q8 promotion candidate" in lines


def test_quant_shadow_candidate_evaluation_recommends_cost_edge_when_dominant() -> None:
    payload = {
        "candidates": [
            {
                "symbol": f"00593{idx}",
                "shadow_role": "top_pick",
                "evaluated": True,
                "would_enter": False,
                "reason": "cost_edge_fail",
                "primary_failure_axis": "cost",
            }
            for idx in range(5)
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["promotion_candidate"]["candidate"] == "cost_edge"
    assert evaluation["promotion_candidate"]["confidence"] == "high"


def test_quant_shadow_candidate_evaluation_recommends_runner_up_when_dominant() -> None:
    payload = {
        "candidates": [
            {
                "symbol": f"00066{idx}",
                "shadow_role": "runner_up_evaluated",
                "evaluated": True,
                "would_enter": False,
                "reason": "runner_up_quality_gate_failed",
                "runner_up_quality_blocked": True,
            }
            for idx in range(3)
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["promotion_candidate"]["candidate"] == "runner_up"
    assert evaluation["promotion_candidate"]["confidence"] == "medium"


def test_quant_shadow_candidate_evaluation_ignores_confirmed_entry_ready_as_guard_block() -> None:
    payload = {
        "candidates": [
            {
                "symbol": "122630",
                "shadow_role": "top_pick",
                "evaluated": True,
                "guard_blocked": True,
                "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                "primary_failure_axis": "confirmed_entry",
                "entry_quant_decision": {"decision": "entry_ready", "blockers": []},
            }
            for _ in range(4)
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["guard_blocked_count"] == 4
    assert evaluation["actionable_guard_blocked_count"] == 0
    assert evaluation["promotion_candidate"]["candidate"] == "hold"
    assert "actionable 0" in "\n".join(render_quant_shadow_candidate_evaluation_lines(evaluation))


def test_quant_shadow_candidate_evaluation_counts_entry_quant_cost_edge_blockers() -> None:
    payload = {
        "candidates": [
            {
                "symbol": "069500",
                "shadow_role": "top_pick",
                "evaluated": True,
                "guard_blocked": True,
                "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                "primary_failure_axis": "confirmed_entry",
                "entry_quant_decision": {
                    "decision": "block_recommended",
                    "blockers": ["cost_edge_fail"],
                    "cost_edge": {"cost_floor_state": "not_met"},
                },
            }
            for _ in range(3)
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["by_cost_floor_state"][0] == {"name": "not_met", "count": 3}
    assert evaluation["promotion_candidate"]["candidate"] == "cost_edge"
    assert evaluation["promotion_candidate"]["counts"]["cost_edge"] == 3


def test_quant_shadow_candidate_evaluation_surfaces_entry_shape_diagnostics() -> None:
    payload = {
        "candidates": [
            {"symbol": "005930", "reason": "below_vwap_reclaim_not_ready", "primary_failure_axis": "vwap_relationship"},
            {"symbol": "000660", "reason": "pullback_not_mature", "primary_failure_axis": "pullback_structure"},
            {
                "symbol": "009150",
                "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                "primary_failure_axis": "confirmed_entry",
            },
            {"symbol": "402340", "reason": "breakout_not_ready", "primary_failure_axis": "breakout_readiness"},
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])
    diagnostics = evaluation["entry_shape_diagnostics"]

    assert diagnostics["pullback_or_vwap_blocked_count"] == 2
    assert diagnostics["breakout_ready_like_count"] == 1
    assert diagnostics["breakout_not_ready_count"] == 2
    lines = "\n".join(render_quant_shadow_candidate_evaluation_lines(evaluation))
    assert "Entry shape diagnostics" in lines
    assert "pullback/vwap blocked 2" in lines


def test_quant_shadow_candidate_evaluation_surfaces_opening_probe_shadow() -> None:
    payload = {
        "candidates": [
            {
                "symbol": "122630",
                "shadow_role": "top_pick",
                "evaluated": True,
                "would_enter": False,
                "reason": "too_extended_from_vwap",
                "opening_momentum_probe_would_enter": True,
                "opening_momentum_probe_shadow": {
                    "eligible": True,
                    "would_probe": True,
                    "reason": "opening_momentum_probe_ready",
                    "behavior_effect": "observation_only",
                },
            },
            {
                "symbol": "005930",
                "shadow_role": "runner_up_evaluated",
                "evaluated": True,
                "would_enter": False,
                "reason": "volume_insufficient",
                "opening_momentum_probe_shadow": {
                    "eligible": True,
                    "would_probe": False,
                    "reason": "volume_ratio_below_probe_floor",
                    "behavior_effect": "observation_only",
                },
            },
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["opening_momentum_probe_count"] == 2
    assert evaluation["opening_momentum_probe_would_enter_count"] == 1
    assert evaluation["opening_momentum_probe"]["would_enter_count"] == 1
    assert evaluation["opening_momentum_probe"]["by_would_enter_symbol"][0] == {
        "name": "122630",
        "count": 1,
    }
    lines = "\n".join(render_quant_shadow_candidate_evaluation_lines(evaluation))
    assert "Opening momentum probe shadow" in lines
    assert "1/2 would-probe" in lines


def test_quant_shadow_candidate_evaluation_surfaces_opening_largecap_surge_shadow() -> None:
    payload = {
        "candidates": [
            {
                "symbol": "005930",
                "shadow_role": "top_pick",
                "opening_largecap_surge_would_enter": True,
                "opening_largecap_surge_shadow": {
                    "eligible": True,
                    "would_probe": True,
                    "reason": "opening_largecap_surge_ready",
                },
            },
            {
                "symbol": "009150",
                "shadow_role": "opening_largecap_watchlist",
                "opening_largecap_surge_shadow": {
                    "eligible": True,
                    "would_probe": False,
                    "reason": "volume_ratio_below_largecap_floor",
                },
            },
        ]
    }

    evaluation = build_quant_shadow_candidate_evaluation([payload])

    assert evaluation["opening_largecap_surge_count"] == 2
    assert evaluation["opening_largecap_surge_would_enter_count"] == 1
    assert evaluation["opening_largecap_surge"]["by_would_enter_symbol"][0] == {
        "name": "005930",
        "count": 1,
    }
    lines = "\n".join(render_quant_shadow_candidate_evaluation_lines(evaluation))
    assert "largecap-surge 1" in lines
    assert "Opening largecap surge shadow: 1/2 would-probe" in lines


def test_load_quant_shadow_candidate_payloads_uses_reports_sibling_data_logs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        tmp_path / "data" / "logs" / "quant_shadow_candidates" / "2026-05-24" / "sample.json",
        {"candidates": [{"symbol": "005930", "shadow_role": "top_pick"}]},
    )
    _write_json(
        tmp_path / "data" / "logs" / "quant_shadow_candidates" / "2026-05-24" / "latest.json",
        {"candidates": [{"symbol": "000660", "shadow_role": "latest_only"}]},
    )

    payloads = load_quant_shadow_candidate_payloads(reports_root=reports, days=["2026-05-24"])

    assert len(payloads) == 1
    assert payloads[0]["candidates"][0]["symbol"] == "005930"
