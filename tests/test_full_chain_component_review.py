from __future__ import annotations

from libs.reporting.evaluation.full_chain_component_review import (
    _attribution_component,
    _decision_window_attribution,
    _paired_role_deltas,
    _scanner_decision,
    _selection_availability,
    build_full_chain_component_review,
)


def _candidate(window: str, role: str, value: float) -> dict:
    return {
        "_payload_generated_at": window,
        "shadow_role": role,
        "shadow_forward_base": {"baseline_raw_ts": window[:10].replace("-", "") + "093000"},
        "shadow_forward_outcome": {
            "checkpoints": {
                "+30m": {"status": "observed", "return_pct": value},
            }
        },
    }


def test_paired_role_delta_uses_same_decision_window() -> None:
    rows = [
        _candidate("2026-06-16T00:00:00+00:00", "top_pick", 1.0),
        _candidate("2026-06-16T00:00:00+00:00", "runner_up_evaluated", 0.4),
        _candidate("2026-06-17T00:00:00+00:00", "top_pick", -0.2),
        _candidate("2026-06-17T00:00:00+00:00", "runner_up_evaluated", -0.5),
    ]
    result = _paired_role_deltas(rows, horizon="+30m")
    assert result["paired_window_count"] == 2
    assert result["observed_day_count"] == 2
    assert result["average_delta_pct"] == 0.45


def test_scanner_adjusts_when_ordering_helps_but_cost_edge_is_negative() -> None:
    role_metrics = [
        {
            "role": "top_pick",
            "horizon": "+30m",
            "expectancy_pct": -0.2,
        }
    ]
    paired = [
        {
            "horizon": "+30m",
            "paired_window_count": 30,
            "observed_day_count": 3,
            "average_delta_pct": 0.4,
            "positive_delta_rate": 0.60,
        }
    ]
    result = _scanner_decision(role_metrics=role_metrics, paired=paired)
    assert result["decision"] == "ADJUST_AND_RETEST"
    assert result["relative_ranking_effect_positive"] is True
    assert result["absolute_cost_adjusted_edge_positive"] is False


def test_scanner_does_not_treat_trivial_positive_delta_as_edge() -> None:
    result = _scanner_decision(
        role_metrics=[
            {
                "role": "top_pick",
                "horizon": "+30m",
                "expectancy_pct": -0.9,
            }
        ],
        paired=[
            {
                "horizon": "+30m",
                "paired_window_count": 100,
                "observed_day_count": 5,
                "average_delta_pct": 0.02,
                "positive_delta_rate": 0.55,
            }
        ],
    )
    assert result["decision"] == "ADJUST_AND_RETEST"
    assert result["relative_ranking_effect_positive"] is False


def test_decision_window_attribution_joins_roles_by_decision_id(monkeypatch) -> None:
    payloads = [
        {
            "generated_at": "2026-06-23T00:00:00+00:00",
            "q9_decision_candidates": [
                {
                    "q9_decision_id": "D1",
                    "q9_decision_role": "A_SCANNER_CONTROL",
                    "symbol": "000660",
                    "rank": 1,
                    "shadow_forward_outcome": {
                        "checkpoints": {"+30m": {"status": "observed", "return_pct": 0.5}}
                    },
                },
                {
                    "q9_decision_id": "D1",
                    "q9_decision_role": "B_STRATEGIST_RANKED",
                    "q9_selected": True,
                    "symbol": "005930",
                    "rank": 2,
                    "shadow_forward_outcome": {
                        "checkpoints": {"+30m": {"status": "observed", "return_pct": 1.0}}
                    },
                },
                {
                    "q9_decision_id": "D1",
                    "q9_decision_role": "C_COMMANDER_FINAL",
                    "q9_commander_no_trade": True,
                    "symbol": "005930",
                    "shadow_forward_outcome": {
                        "checkpoints": {"+30m": {"status": "observed", "return_pct": 1.0}}
                    },
                },
            ],
        }
    ]
    monkeypatch.setattr(
        "libs.reporting.evaluation.full_chain_component_review.attach_forward_outcomes",
        lambda rows: rows,
    )
    result = _decision_window_attribution(payloads, cost_pct=1.0)
    row = next(item for item in result["by_horizon"] if item["horizon"] == "+30m")
    assert row["average_strategist_delta_pct"] == 0.5
    assert row["average_commander_delta_pct"] == 0.0


def test_empty_realized_range_is_insufficient_not_rejected(tmp_path) -> None:
    result = build_full_chain_component_review(
        reports_root=tmp_path / "reports",
        start="2026-06-23",
        end="2026-06-23",
    )

    assert result["component_decisions"]["full_system"]["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["overall_decision"]["decision"] == "INSUFFICIENT_EVIDENCE"


def test_selection_availability_accepts_intrinsic_scanner_control() -> None:
    result = _selection_availability([
        {
            "selection": {
                "raw_scanner_snapshot_source": "scanner_intrinsic_control_snapshot",
                "raw_scanner_top10": [{"symbol": "000660"}],
                "strategist_run_id": "S1",
                "post_strategist_top10": [{"symbol": "005930"}],
                "commander_final_explicit": True,
            }
        }
    ])

    assert result["raw_scanner_control_count"] == 1
    assert result["scanner_vs_strategist_comparable_count"] == 1


def test_attribution_keeps_partial_metrics_when_only_day_count_is_missing() -> None:
    result = _attribution_component(
        attribution={
            "by_horizon": [{
                "horizon": "+30m",
                "strategist_comparison_count": 47,
                "strategist_day_count": 1,
                "average_strategist_delta_pct": 0.0,
                "strategist_positive_delta_rate": 0.0,
            }]
        },
        component="strategist",
        question="Does it help?",
        missing_comparison="missing",
        availability={},
    )

    assert result["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["metrics"]["strategist_comparison_count"] == 47
    assert "47 windows/1 days" in result["missing_comparison"]
