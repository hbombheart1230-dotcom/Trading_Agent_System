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
        "execution": {
            "order": {
                "symbol": "041190",
                "meta": {
                    "controlled_mock_lane": {
                        "lane_id": "BTC_WOORI",
                        "signal_id": "Q12_2026-08-31_09:05",
                        "score": 7.1,
                        "evidence": {"btc_0855_return_24h_pct": 5.2},
                    },
                    "position_strategy_snapshot": _strategy(),
                },
            }
        }
    }

    surface = build_controlled_lane_report_surface(state)

    assert surface["lane_label"] == "Q12 BTC-우기투"
    assert surface["evidence"]["btc_0855_return_24h_pct"] == 5.2
    assert surface["stage3_horizon_review_allowed"] is False


def test_sell_report_recovers_lane_evidence_from_position_and_ledger(tmp_path: Path) -> None:
    ledger = (
        tmp_path
        / "data"
        / "logs"
        / "controlled_mock_lanes"
        / "2026-08-31"
        / "lane_submissions.json"
    )
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "submissions": [
                    {
                        "lane_id": "Q10_SEMICONDUCTOR",
                        "symbol": "000660",
                        "signal_id": "Q10_SEMI_2026-08-31_sk_hynix_09:05",
                        "score": 4.2,
                        "evidence": {"expected_state": "STRONG_POSITIVE"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    state = {
        "execution": {"order": {"action": "SELL", "symbol": "000660"}},
        "persisted_state": {
            "position_strategy_context": {"000660": {"output": _strategy()}}
        },
    }

    surface = build_controlled_lane_report_surface(
        state, day="2026-08-31", root=tmp_path
    )

    assert surface["lane_id"] == "Q10_SEMICONDUCTOR"
    assert surface["evidence"]["expected_state"] == "STRONG_POSITIVE"


def test_attach_and_render_explains_r3_is_frozen() -> None:
    surface = {
        "lane_id": "Q10_INDEX",
        "lane_label": "Q10 한국지수 선행시장",
        "signal_id": "Q10_INDEX_2026-08-31_kospi_09:03",
        "evidence": {"expected_state": "RISK_ON"},
        "stage3_horizon_review_allowed": False,
        "llm_used": False,
    }
    report = attach_controlled_lane_report_surface({}, {"controlled_mock_lane": surface})
    lines = render_controlled_lane_report_lines(report)

    assert report["controlled_mock_lane"] == surface
    assert any("Q10 한국지수" in line for line in lines)
    assert any("R3 연결: 차단됨" in line for line in lines)
