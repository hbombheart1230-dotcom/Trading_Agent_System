from __future__ import annotations

from pathlib import Path

from libs.reporting.evaluation.attribution_score_v0 import build_attribution_score_v0


def _base_score(**overrides):
    payload = {
        "day": "2026-07-06",
        "reports_root": Path("missing"),
        "models": [],
        "daily_scorecard": {
            "artifact_integrity": {
                "status_counts": {"PASS": 1},
            }
        },
        "selection_authority": {
            "rows": [{
                "trade_id": "T1",
                "raw_scanner_top1": "005930",
                "post_strategy_top1": "005930",
                "selected_symbol": "005930",
                "monitor_to_commander_changed": False,
                "final_to_executed_changed": False,
                "post_to_selected_changed": False,
            }]
        },
        "horizon_compliance": {
            "rows": [{
                "trade_id": "T1",
                "exited_before_min_hold": False,
                "exited_before_target_hold": False,
                "horizon_violation_candidate": False,
                "target_hold_would_improve_exit": False,
            }]
        },
        "entry_timing": {
            "rows": [{
                "trade_id": "T1",
                "label": "ENTRY_APPROPRIATE",
            }]
        },
    }
    payload.update(overrides)
    return build_attribution_score_v0(**payload)


def test_attribution_score_marks_missing_evidence_as_insufficient() -> None:
    payload = _base_score(
        selection_authority={"rows": []},
        horizon_compliance={"rows": []},
        entry_timing={"rows": []},
    )

    assert payload["scores"]["selection_integrity_score"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert payload["scores"]["scanner_alignment_score"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert payload["scores"]["entry_timing_score"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert payload["scores"]["exit_horizon_score"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_explicit_defect_exclusion_does_not_reduce_evidence_quality() -> None:
    payload = _base_score(
        models=[{"trade_id": "T1", "integrity": {"defects": ["confirmed_runtime_defect"]}}],
        daily_scorecard={"artifact_integrity": {"status_counts": {"WATCH": 1}}},
        selection_authority={
            "rows": [],
            "summary": {"excluded:confirmed_runtime_defect": 1},
        },
        horizon_compliance={"rows": [], "excluded_trade_count": 1},
        entry_timing={"rows": [], "excluded_trade_count": 1},
    )

    assert payload["scores"]["evidence_quality_score"]["score"] == 100
    assert payload["weakest_observed_axis"] == {"name": "", "score": None}


def test_attribution_score_penalizes_bad_entry_timing() -> None:
    payload = _base_score(
        entry_timing={
            "rows": [
                {"trade_id": "T1", "label": "ENTRY_TOO_LATE"},
                {"trade_id": "T2", "label": "ENTRY_TOO_EARLY"},
            ]
        }
    )

    entry = payload["scores"]["entry_timing_score"]
    assert entry["status"] == "OK"
    assert entry["score"] == 35
    assert payload["weakest_observed_axis"]["name"] == "entry_timing_score"


def test_attribution_score_identifies_exit_horizon_as_weak_axis() -> None:
    payload = _base_score(
        horizon_compliance={
            "rows": [{
                "trade_id": "T1",
                "exited_before_min_hold": True,
                "exited_before_target_hold": True,
                "horizon_violation_candidate": True,
                "target_hold_would_improve_exit": False,
            }]
        }
    )

    exit_score = payload["scores"]["exit_horizon_score"]
    assert exit_score["status"] == "OK"
    assert exit_score["score"] == 50
    assert payload["weakest_observed_axis"]["name"] == "exit_horizon_score"


def test_evidence_quality_is_not_selected_as_behavior_axis() -> None:
    payload = _base_score(
        daily_scorecard={"artifact_integrity": {"status_counts": {"PASS": 9, "FAIL": 1}}},
    )

    assert payload["scores"]["evidence_quality_score"]["score"] < 100
    assert payload["weakest_observed_axis"]["name"] != "evidence_quality_score"
