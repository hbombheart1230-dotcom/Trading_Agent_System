from __future__ import annotations

from libs.reporting.evaluation.cost_basis_comparison import (
    build_cost_basis_comparison,
    build_evaluation_cost_bases,
    render_cost_basis_comparison,
)


def test_cost_bases_separate_mock_observation_from_live_assumption() -> None:
    result = build_evaluation_cost_bases({
        "source": "kiwoom.ka10170",
        "sample_count": 153,
        "conservative_round_trip_cost_pct": 0.010368485,
    })

    assert result["mock_observed"]["round_trip_cost_pct"] == 1.036849
    assert result["mock_observed"]["total_drag_with_slippage_pct"] == 1.086849
    assert result["live_deployment_equity"]["round_trip_cost_pct"] == 0.23
    assert result["live_deployment_equity"]["total_drag_with_slippage_pct"] == 0.28


def test_comparison_uses_same_gross_return_for_both_cost_bases(monkeypatch, tmp_path) -> None:
    payloads = [{
        "generated_at": "2026-07-21T00:00:00+00:00",
        "q9_decision_candidates": [{
            "q9_decision_id": "D1",
            "q9_decision_role": "P_SCANNER_PRE_STRATEGIST_UNIVERSE",
            "symbol": "005930",
            "rank": 1,
            "shadow_forward_base": {"baseline_raw_ts": "20260721090000"},
            "shadow_forward_outcome": {
                "checkpoints": {"+30m": {"status": "observed", "return_pct": 1.2}}
            },
        }],
    }]
    monkeypatch.setattr(
        "libs.reporting.evaluation.cost_basis_comparison.load_quant_shadow_candidate_payloads_for_range",
        lambda **_: payloads,
    )
    monkeypatch.setattr(
        "libs.reporting.evaluation.cost_basis_comparison.load_broker_cost_profile",
        lambda *_: {"conservative_round_trip_cost_pct": 0.009, "sample_count": 10},
    )
    monkeypatch.setattr(
        "libs.reporting.evaluation.cost_basis_comparison.load_q9_forward_candles",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "libs.reporting.evaluation.scanner_quality.attach_forward_outcomes",
        lambda rows, **_kwargs: rows,
    )

    result = build_cost_basis_comparison(
        reports_root=tmp_path,
        start="2026-07-21",
        end="2026-07-21",
    )
    row = next(
        item for item in result["rows"]
        if item["top_k"] == 1 and item["horizon"] == "+30m"
    )

    assert row["gross"]["expectancy_pct"] == 1.2
    assert row["mock_net"]["expectancy_pct"] == 0.25
    assert row["live_net"]["expectancy_pct"] == 0.92
    assert row["expectancy_delta_live_minus_mock_pct"] == 0.67
    assert result["forward_data_source"] == "state_plus_kiwoom_minute_recovery"
    assert result["cohort_scope"] == "all_pre_strategist_windows_with_observed_horizon"
    assert "Mock Net" in render_cost_basis_comparison(result)
