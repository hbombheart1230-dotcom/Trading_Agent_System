from __future__ import annotations

from libs.reporting.evaluation.full_chain_component_review import _classify_root_cause
from libs.reporting.evaluation.scanner_quality import (
    build_scanner_topk_forward_performance,
)


def _row(decision_id: str, rank: int, value: float) -> dict:
    return {
        "q9_decision_id": decision_id,
        "rank": rank,
        "symbol": f"{rank:06d}",
        "shadow_forward_base": {"baseline_raw_ts": "20260623090000"},
        "shadow_forward_outcome": {
            "checkpoints": {
                "+30m": {"status": "observed", "return_pct": value},
            }
        },
    }


def test_topk_forward_outcome_is_deterministic() -> None:
    rows = [
        _row("D2", 2, -1.0),
        _row("D1", 1, 1.0),
        _row("D2", 1, 3.0),
        _row("D1", 2, -1.0),
    ]

    first = build_scanner_topk_forward_performance(rows, cost_pct=0.2, slippage_pct=0.1)
    second = build_scanner_topk_forward_performance(
        list(reversed(rows)),
        cost_pct=0.2,
        slippage_pct=0.1,
    )
    first_1 = next(
        row for row in first["rows"] if row["top_k"] == 1 and row["horizon"] == "+30m"
    )
    first_3 = next(
        row for row in first["rows"] if row["top_k"] == 3 and row["horizon"] == "+30m"
    )

    assert first == second
    assert first_1["gross"]["expectancy_pct"] == 2.0
    assert first_1["net"]["expectancy_pct"] == 1.7
    assert first_3["gross"]["expectancy_pct"] == 0.5


def test_negative_scanner_edge_is_root_cause_before_strategist() -> None:
    scanner_quality = {
        "topk_forward_performance": {
            "rows": [
                {
                    "top_k": 1,
                    "horizon": "+30m",
                    "window_count": 30,
                    "observed_day_count": 3,
                    "net": {"expectancy_pct": -0.8},
                },
                {
                    "top_k": 3,
                    "horizon": "+30m",
                    "window_count": 30,
                    "observed_day_count": 3,
                    "net": {"expectancy_pct": -0.5},
                },
            ]
        }
    }
    attribution = {
        "by_horizon": [{
            "horizon": "+30m",
            "strategist_comparison_count": 30,
            "strategist_day_count": 3,
            "average_strategist_delta_pct": -0.4,
            "commander_comparison_count": 30,
            "commander_day_count": 3,
            "average_commander_delta_pct": 0.1,
        }]
    }

    result = _classify_root_cause(
        scanner_quality=scanner_quality,
        attribution=attribution,
        entry={},
        exit_hold={},
    )

    assert result["statuses"]["scanner_intrinsic_fail"] is True
    assert result["statuses"]["strategist_degradation"] is True
    assert result["primary_root_cause"] == "scanner_intrinsic_fail"
