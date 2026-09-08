from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.controlled_mock_lane_report import (
    attach_controlled_lane_report_surface,
    build_controlled_lane_report_surface,
    render_controlled_lane_report_lines,
)


def _strategy() -> dict:
    return {
        "controlled_mock_lane": True,
        "strategy_horizon": "intraday",
        "expected_hold_window": {"min_sec": 300, "target_sec": 1800, "max_sec": 14400},
        "llm_used": False,
        "horizon_revision_allowed": False,
    }


def test_build_surface_from_buy_order_meta() -> None:
    state = {
        "execution": {"order": {"symbol": "041190", "meta": {
            "controlled_mock_lane": {
                "lane_id": "BTC_WOORI", "signal_id": "Q12_2026-08-31_09:05",
                "score": 7.1, "evidence": {"btc_0855_return_24h_pct": 5.2},
            },
            "position_strategy_snapshot": _strategy(),
        }}}
    }
    surface = build_controlled_lane_report_surface(state)
    assert surface["lane_label"] == "Q12 BTC-우리기술투자"
    assert surface["evidence"]["btc_0855_return_24h_pct"] == 5.2
    assert surface["stage3_horizon_review_allowed"] is False
    assert surface["scanner_rank_applicable"] is False


def test_sell_report_recovers_lane_by_exact_entry_order(tmp_path: Path) -> None:
    ledger = tmp_path / "data/logs/controlled_mock_lanes/2026-08-31/lane_submissions.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"submissions": [{
        "lane_id": "Q10_SEMICONDUCTOR", "symbol": "000660", "run_id": "entry-run",
        "order_id": "0021787", "signal_epoch": 1788739800,
        "signal_id": "Q10_SEMI_2026-08-31_sk_hynix_09:05", "score": 4.2,
        "evidence": {"expected_state": "STRONG_POSITIVE"},
    }]}), encoding="utf-8")
    state = {"execution": {"order": {"action": "SELL", "symbol": "000660"}}}
    prior_entry = {"symbol": "000660", "run_id": "entry-run", "execution_details": {"order_id": "21787"}}

    surface = build_controlled_lane_report_surface(
        state, day="2026-08-31", root=tmp_path, prior_entry=prior_entry
    )
    assert surface["lane_id"] == "Q10_SEMICONDUCTOR"
    assert surface["entry_order_id"] == "0021787"
    assert surface["evidence"]["expected_state"] == "STRONG_POSITIVE"


def test_sell_report_does_not_guess_lane_from_symbol_only(tmp_path: Path) -> None:
    ledger = tmp_path / "data/logs/controlled_mock_lanes/2026-08-31/lane_submissions.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"submissions": [{
        "lane_id": "Q10_SEMICONDUCTOR", "symbol": "000660", "order_id": "0021787"
    }]}), encoding="utf-8")
    state = {"execution": {"order": {"action": "SELL", "symbol": "000660"}}}
    assert build_controlled_lane_report_surface(state, day="2026-08-31", root=tmp_path) == {}


def test_attach_and_render_explains_r3_is_frozen() -> None:
    surface = {
        "lane_id": "Q10_INDEX", "lane_label": "Q10 한국지수 선행시장",
        "signal_id": "Q10_INDEX_2026-08-31_kospi_09:03",
        "evidence": {"expected_state": "RISK_ON"},
        "stage3_horizon_review_allowed": False, "scanner_rank_applicable": False,
        "llm_used": False,
    }
    report = attach_controlled_lane_report_surface({}, {"controlled_mock_lane": surface})
    lines = render_controlled_lane_report_lines(report)
    assert report["controlled_mock_lane"] == surface
    assert any("Q10 한국지수" in line for line in lines)
    assert any("R3 연결: 차단" in line for line in lines)
