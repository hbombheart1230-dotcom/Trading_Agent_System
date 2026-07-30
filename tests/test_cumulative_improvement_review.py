from __future__ import annotations

from libs.reporting.evaluation.episode_scanner_review import (
    build_episode_scanner_review,
    build_same_symbol_reentry_review,
)
from libs.reporting.evaluation.post_reclaim_shadow_review import (
    build_post_reclaim_shadow_review,
)


def _prepared_row(
    *,
    day: str,
    symbol: str,
    epoch: int,
    rank: int,
    return_30m: float,
    score_breakdown: dict | None = None,
) -> dict:
    return {
        "day": day,
        "symbol": symbol,
        "rank": rank,
        "entry_lane_observation": {"primary_lane": "vwap_reclaim"},
        "score_breakdown": score_breakdown or {},
        "shadow_forward_base": {
            "baseline_epoch": epoch,
            "baseline_price": 100.0,
        },
        "shadow_forward_outcome": {
            "checkpoints": {
                "+5m": {"status": "observed", "return_pct": return_30m / 2},
                "+15m": {"status": "observed", "return_pct": return_30m * 0.8},
                "+30m": {"status": "observed", "return_pct": return_30m},
                "EOD": {"status": "pending"},
            }
        },
    }


def test_episode_scanner_review_compresses_serial_windows_deterministically() -> None:
    rows = [
        _prepared_row(
            day="2026-07-27",
            symbol="005930",
            epoch=1000,
            rank=1,
            return_30m=-0.4,
            score_breakdown={"trading_value": 0.2},
        ),
        _prepared_row(
            day="2026-07-27",
            symbol="005930",
            epoch=1060,
            rank=1,
            return_30m=5.0,
            score_breakdown={"trading_value": 0.3},
        ),
        _prepared_row(
            day="2026-07-27",
            symbol="005930",
            epoch=2000,
            rank=2,
            return_30m=0.6,
            score_breakdown={"trading_value": 0.1},
        ),
    ]

    result = build_episode_scanner_review(
        [],
        prepared_rows=rows,
        mock_drag_pct=1.0,
        live_drag_pct=0.3,
    )

    assert result["raw_candidate_row_count"] == 3
    assert result["episode_count"] == 2
    assert result["compression_ratio"] == 0.6667
    rank1 = next(
        row
        for row in result["rank_horizon_rows"]
        if row["rank_bucket"] == "rank1" and row["horizon"] == "+30m"
    )
    rank23 = next(
        row
        for row in result["rank_horizon_rows"]
        if row["rank_bucket"] == "rank2_3" and row["horizon"] == "+30m"
    )
    assert rank1["gross"]["expectancy_pct"] == -0.4
    assert rank23["live_net"]["expectancy_pct"] == 0.3
    assert result["rank1_minus_rank2_3_gross_30m_pct"] == -1.0
    assert result["score_component_review"]["component_covered_episode_count"] == 2
    assert result["score_component_review"]["status"] == (
        "NOT_READY_MISSING_SCORE_COMPONENT_ARTIFACT"
    )


def test_same_symbol_reentry_review_separates_first_and_repeat() -> None:
    result = build_same_symbol_reentry_review(
        [
            {
                "trade_id": "TRD_20260727_005930_01",
                "symbol": "005930",
                "net_return_pct": -0.2,
            },
            {
                "trade_id": "TRD_20260727_005930_02",
                "symbol": "005930",
                "net_return_pct": -1.2,
            },
            {
                "trade_id": "TRD_20260727_000660_01",
                "symbol": "000660",
                "net_return_pct": 0.5,
            },
        ]
    )

    assert result["day_symbol_group_count"] == 2
    assert result["repeated_day_symbol_group_count"] == 1
    assert result["first_entry"]["count"] == 2
    assert result["first_entry"]["expectancy_pct"] == 0.15
    assert result["repeat_entry"]["expectancy_pct"] == -1.2
    assert result["repeat_minus_first_expectancy_pct"] == -1.35
    assert result["repeat_after_loss"]["count"] == 1
    assert result["repeat_after_loss"]["expectancy_pct"] == -1.2
    assert result["repeat_after_non_loss"]["count"] == 0


def test_post_reclaim_shadow_review_keeps_live_and_mock_costs_separate() -> None:
    result = build_post_reclaim_shadow_review(
        {
            "below_vwap_reclaim_subtype_forward": [
                {
                    "name": "vwap_reclaim:post_reclaim_pullback_candidate",
                    "candidate_count": 24,
                    "observed_count": 24,
                    "day_count": 12,
                    "coverage": 1.0,
                    "avg_return_5m_pct": 0.35,
                    "avg_return_15m_pct": 0.49,
                    "avg_return_30m_pct": 0.54,
                    "avg_return_60m_pct": 0.58,
                }
            ]
        },
        mock_drag_pct=1.08,
        live_drag_pct=0.28,
    )

    row_30m = next(row for row in result["rows"] if row["horizon"] == "+30m")
    assert row_30m["live_net_expectancy_pct"] == 0.26
    assert row_30m["mock_net_expectancy_pct"] == -0.54
    assert result["promotion_status"] == "LIVE_COST_SHADOW_CANDIDATE"
    assert result["runtime_directional_edge_used"] is False
