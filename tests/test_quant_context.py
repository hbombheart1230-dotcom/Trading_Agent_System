from __future__ import annotations

import json
from pathlib import Path

from libs.runtime.quant.context import build_strategist_quant_context
from libs.runtime.quant.factors import build_factor_snapshot_from_candidate


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_strategist_quant_context_loads_weekly_scorecard(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "operator_summary" / "weekly" / "2026-W21" / "weekly_summary.json",
        {
            "period_type": "weekly",
            "period_key": "2026-W21",
            "metrics": {"trade_count": 2, "closed_trade_count": 2, "win_rate": 0.0, "avg_return_pct": -1.0},
            "pattern_performance": {
                "strategist": {
                    "by_tactical_strategy": [
                        {"name": "vwap_reclaim_pullback", "count": 2, "closed_or_realized_count": 2, "win_rate": 0.0, "avg_return_pct": -1.0}
                    ]
                },
                "monitor_exit": {
                    "by_exit_reason": [
                        {"name": "intraday_low_break", "count": 2, "closed_or_realized_count": 2, "win_rate": 0.0, "avg_return_pct": -1.2}
                    ]
                },
            },
        },
    )

    context = build_strategist_quant_context(
        {"reports_root": str(reports), "day": "2026-05-20"},
        call_kind="market_strategy_frame",
    )

    scorecard = context["quant_market_context"]["scorecard"]
    assert context["period_key"] == "2026-W21"
    assert scorecard["available"] is True
    assert scorecard["tactic_scorecards"][0]["tactic_id"] == "vwap_reclaim_pullback"
    assert "intraday_low_break" in scorecard["exit_loss_clusters"]


def test_stage2_quant_context_carries_selected_symbol_snapshot() -> None:
    snapshot = build_factor_snapshot_from_candidate(
        {"symbol": "005930", "score_total": 0.8, "confidence": 0.7, "features": {"engine_vwap_distance": -0.003}},
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    context = build_strategist_quant_context(
        {
            "day": "2026-05-20",
            "commander_refresh_context": {
                "selected_symbol": "005930",
                "actual_selected_candidate": {"symbol": "005930", "quant_factor_snapshot": snapshot},
            },
        },
        call_kind="selected_symbol_tactical_refresh",
    )

    assert context["selected_symbol_quant_snapshot"]["tactic_id"] == "vwap_reclaim_pullback"
    assert context["selected_symbol_quant_snapshot"]["factors"]["symbol"] == "005930"


def test_stage2_quant_context_synthesizes_snapshot_from_compact_candidate() -> None:
    context = build_strategist_quant_context(
        {
            "day": "2026-05-20",
            "commander_refresh_context": {
                "selected_symbol": "233740",
                "actual_selected_candidate": {
                    "symbol": "233740",
                    "rank": 1,
                    "score": 1.010093,
                    "risk_score": 0.244733,
                    "confidence": 0.896988,
                    "entry_compatibility_score": 0.175414,
                    "scanner_chart_fit_score": 0.255414,
                    "scanner_macro_chart_fit_score": 0.341822,
                    "expected_monitor_block_reason": "below_vwap_reclaim_not_ready",
                    "dominant_block_reason": "mixed",
                    "tactical_strategy": "opening_gap_momentum",
                    "playbook": "breakout",
                },
            },
        },
        call_kind="selected_symbol_tactical_refresh",
    )

    snapshot = context["selected_symbol_quant_snapshot"]
    assert snapshot["source"] == "quant_candidate_factor_snapshot.v1"
    assert snapshot["tactic_id"] == "opening_gap_momentum"
    assert snapshot["factors"]["symbol"] == "233740"
    assert snapshot["factors"]["score_total"] == 1.010093
    assert snapshot["factors"]["dominant_block_reason"] == "mixed"
    assert context["behavior_effect"] == "observation_only"


def test_memory_disabled_hides_scorecard_but_keeps_observation_contract() -> None:
    context = build_strategist_quant_context(
        {"day": "2026-05-20"},
        call_kind="market_strategy_frame",
        memory_usage_disabled=True,
    )

    scorecard = context["quant_market_context"]["scorecard"]
    assert scorecard["available"] is False
    assert scorecard["visible_to_llm"] is False
    assert context["behavior_effect"] == "observation_only"
