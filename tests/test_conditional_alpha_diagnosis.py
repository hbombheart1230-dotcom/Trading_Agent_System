from __future__ import annotations

import json
from pathlib import Path

from libs.research.conditional_alpha_diagnosis.analysis import (
    horizon_cross_sections,
    horizon_reversals,
    opening_cross_sections,
    opening_archetype_analysis,
    research_candidates,
)
from libs.research.conditional_alpha_diagnosis.pipeline import (
    run_conditional_alpha_diagnosis,
)


def _opening_row(index: int, value: float = 1.0) -> dict[str, object]:
    return {
        "episode_id": f"E{index}",
        "day": f"2026-07-{index + 1:02d}",
        "symbol": f"{index:06d}",
        "decision_from_open_sec": 60,
        "return_5m_pct": value,
        "return_15m_pct": value,
        "net_return_30m_pct": value,
        "return_60m_pct": value,
        "return_eod_pct": value,
        "source_class": "scanner",
        "tactic_id": "opening_probe",
        "playbook": "breakout",
        "strategist_scenario": "risk_on",
        "path_type": "IMMEDIATE_EXPANSION",
        "price_arc": "NORMAL",
        "above_vwap": True,
        "engine_regime": "trend",
        "opening_gap_pct": 1.0,
        "entry_vs_prior_close_pct": 2.5,
        "opening_relative_volume": 2.0,
        "scanner_score": 1.0,
        "risk_score": 0.3,
        "scanner_chart_fit_score": 0.8,
        "scanner_macro_chart_fit_score": 0.8,
    }


def test_screenable_candidate_requires_breadth_and_positive_days() -> None:
    rows = [_opening_row(index) for index in range(10)]
    candidates = research_candidates(opening_cross_sections(rows))

    opening = next(
        row
        for row in candidates
        if row["dimension"] == "decision_time" and row["horizon"] == "30m"
    )
    assert opening["value"] == "09:00-09:04"
    assert opening["day_count"] == 10
    assert opening["symbol_count"] == 10
    assert opening["average_without_top3_pct"] == 1.0


def test_small_profitable_slice_is_not_promoted_as_candidate() -> None:
    rows = [_opening_row(index) for index in range(4)]
    assert research_candidates(opening_cross_sections(rows)) == []


def test_opening_screen_includes_exact_market_open() -> None:
    from libs.research.conditional_alpha_diagnosis.analysis import predefined_opening_screens

    row = _opening_row(0)
    row["decision_from_open_sec"] = 0
    result = predefined_opening_screens([row])
    assert next(item for item in result if item["screen"] == "OPEN_0_5_ALL" and item["horizon"] == "30m")["count"] == 1


def test_opening_archetype_uses_only_point_in_time_fields() -> None:
    immediate = _opening_row(0, 2.0)
    immediate["decision_from_open_sec"] = 10
    dislocation = _opening_row(1, 1.0)
    dislocation["decision_from_open_sec"] = 500
    dislocation["kospi_pct"] = -4.0
    result = opening_archetype_analysis([immediate, dislocation])
    assert result["IMMEDIATE_0_1M"]["count"] == 1
    assert result["DISLOCATION_REBOUND"]["count"] == 1


def test_horizon_loss_to_win_is_deterministic() -> None:
    source = [
        {
            "trade_id": "T1",
            "day": "2026-07-01",
            "symbol": "A",
            "scenario_returns": {
                "actual_exit": {"live_net_return_pct": -0.5},
                "+5m": {"live_net_return_pct": 0.2},
                "+15m": {"live_net_return_pct": 1.0},
            },
        }
    ]
    first, summary = horizon_reversals(source, {"T1": {"playbook": "pullback"}})
    second, _ = horizon_reversals(source, {"T1": {"playbook": "pullback"}})

    assert first == second
    assert first[0]["loss_to_win"] is True
    assert first[0]["best_alternative"]["scenario"] == "+15m"
    assert first[0]["best_alternative"]["delta_vs_actual_pct"] == 1.5
    assert summary["+5m"]["average_pct"] == 0.7
    grouped = horizon_cross_sections(first)
    strategy = next(
        row
        for row in grouped
        if row["dimension"] == "strategy_horizon"
        and row["value"] == "MISSING"
        and row["scenario"] == "+15m"
    )
    assert strategy["delta_metrics"]["average_pct"] == 1.5


def test_outcome_derived_path_is_not_a_research_candidate() -> None:
    rows = [_opening_row(index) for index in range(10)]
    candidates = research_candidates(opening_cross_sections(rows))
    assert not any(row["dimension"] == "path_type" for row in candidates)


def test_pipeline_writes_independent_research_artifacts(tmp_path: Path) -> None:
    deep = tmp_path / "deep.json"
    longitudinal = tmp_path / "long.json"
    horizon = tmp_path / "horizon.json"
    deep.write_text(json.dumps({"cases": [_opening_row(0)]}), encoding="utf-8")
    longitudinal.write_text(json.dumps({"events": []}), encoding="utf-8")
    horizon.write_text(json.dumps({"trade_rows": []}), encoding="utf-8")
    output = tmp_path / "output"

    paths = run_conditional_alpha_diagnosis(
        reports_root=tmp_path / "reports",
        output_root=output,
        deep_dive_path=deep,
        longitudinal_path=longitudinal,
        horizon_path=horizon,
    )

    summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
    assert summary["behavior_effect"] == "NONE_OFFLINE_RESEARCH_ONLY"
    assert summary["coverage"]["opening_case_count"] == 1
    assert Path(paths["report"]).exists()
    assert Path(paths["cross_sections"]).exists()
