from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.research.structural_alpha.evaluator import (
    evaluate_strategy,
    sector_not_testable_result,
)
from libs.research.structural_alpha.features import (
    contraction_breakout_features,
    relative_strength_features,
)
from libs.research.structural_alpha.strategies import (
    build_cross_sectional_episodes,
)
from libs.research.structural_alpha.windows import load_point_in_time_windows


KST = timezone(timedelta(hours=9))


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=KST).timestamp())


def _candles(
    *,
    start: int,
    count: int,
    step: float,
    volume: float,
) -> list[dict]:
    rows = []
    for index in range(count):
        price = 100.0 + step * index
        rows.append(
            {
                "ts": start + index * 60,
                "open": price,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
                "volume": volume + index,
            }
        )
    return rows


def test_window_loader_keeps_top5_and_rejects_synthetic_epoch(
    tmp_path: Path,
) -> None:
    day = "2026-07-10"
    root = tmp_path / "reports" / "operator_summary" / "daily" / day
    root.mkdir(parents=True)
    candidates = [
        {"rank": index, "symbol": f"{index:06d}"}
        for index in range(1, 8)
    ]
    payload = {
        "windows": [
            {
                "window_type": "scanner_selection",
                "decision_id": "valid",
                "decision_epoch": _epoch("2026-07-10T10:00:10"),
                "scanner_pre_strategist_universe": {
                    "intrinsic_ranked_top20": candidates
                },
            },
            {
                "window_type": "scanner_selection",
                "decision_id": "synthetic",
                "decision_epoch": 1000,
                "scanner_pre_strategist_universe": {
                    "intrinsic_ranked_top20": candidates
                },
            },
        ]
    }
    (root / "q9_decision_windows.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    result = load_point_in_time_windows(
        reports_root=tmp_path / "reports",
        start=day,
        end=day,
    )

    assert result["canonical_window_count"] == 1
    assert result["invalid_epoch_count"] == 1
    assert len(result["windows"][0]["candidates"]) == 5


def test_relative_strength_uses_only_completed_minutes() -> None:
    start = _epoch("2026-07-10T09:30:00")
    rows = _candles(start=start, count=31, step=0.1, volume=100.0)
    rows[-1]["close"] = 1000.0
    decision = _epoch("2026-07-10T10:00:10")

    features = relative_strength_features(
        rows,
        decision_epoch=decision,
        day="2026-07-10",
    )

    assert features["feature_epoch"] == _epoch("2026-07-10T09:59:00")
    assert features["close"] < 200.0


def test_contraction_breakout_contract_is_exact() -> None:
    start = _epoch("2026-07-10T09:30:00")
    rows = _candles(start=start, count=31, step=0.0, volume=100.0)
    for row in rows[-20:-5]:
        row["high"] = 101.0
        row["low"] = 99.0
    for row in rows[-5:]:
        row["high"] = 100.2
        row["low"] = 99.8
    rows[-1]["close"] = 101.1
    rows[-1]["high"] = 101.1
    rows[-1]["volume"] = 200.0

    result = contraction_breakout_features(
        rows,
        decision_epoch=_epoch("2026-07-10T10:01:10"),
        day="2026-07-10",
    )

    assert result["contraction_ok"] is True
    assert result["breakout_ok"] is True
    assert result["volume_ok"] is True


def test_cross_sectional_ranking_and_entry_are_deterministic() -> None:
    start = _epoch("2026-07-10T09:30:00")
    decision = _epoch("2026-07-10T10:00:10")
    windows = [
        {
            "decision_id": "d1",
            "day": "2026-07-10",
            "decision_epoch": decision,
            "candidates": [
                {"rank": 1, "symbol": "A"},
                {"rank": 2, "symbol": "B"},
                {"rank": 3, "symbol": "C"},
            ],
        }
    ]
    candles = {
        "A": _candles(start=start, count=40, step=0.05, volume=100.0),
        "B": _candles(start=start, count=40, step=0.10, volume=200.0),
        "C": _candles(start=start, count=40, step=-0.02, volume=50.0),
    }

    first = build_cross_sectional_episodes(
        windows,
        minute_rows_by_symbol=candles,
    )
    second = build_cross_sectional_episodes(
        windows,
        minute_rows_by_symbol=dict(reversed(list(candles.items()))),
    )

    assert first == second
    assert len(first) == 1
    assert first[0]["symbol"] == "B"
    assert first[0]["baseline_epoch"] == _epoch("2026-07-10T10:00:00")


def test_strategy_evaluation_applies_cost_and_small_sample_rejects() -> None:
    epoch = _epoch("2026-07-20T10:00:00")
    episodes = [
        {
            "episode_id": "e1",
            "day": "2026-07-20",
            "symbol": "A",
            "baseline_epoch": epoch,
            "baseline_price": 100.0,
        }
    ]
    candles = {
        "A": [
            {
                "ts": epoch + minute * 60,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 101.0 if minute >= 30 else 100.0,
                "volume": 100.0,
            }
            for minute in range(61)
        ]
    }

    result = evaluate_strategy(
        episodes,
        minute_rows_by_symbol=candles,
    )
    primary = result["splits"]["retrospective"]["+30m"]

    assert primary["metrics"]["expectancy_pct"] == 0.72
    assert result["decision"] == "REJECT"


def test_sector_strategy_is_not_fabricated() -> None:
    result = sector_not_testable_result()

    assert (
        result["decision"]
        == "NOT_TESTABLE_MISSING_POINT_IN_TIME_SECTOR_MEMBERSHIP"
    )
    assert result["episode_count"] == 0


def test_structural_research_has_no_execution_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("libs/research/structural_alpha").glob("*.py")
    )

    assert "OrderIntent" not in source
    assert "libs.runtime.execution" not in source
    assert "graphs.nodes" not in source
