from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.research.structural_alpha_batch2.features import (
    market_return_15m,
    oversold_reversal_features,
    trend_pullback_features,
)
from libs.research.structural_alpha_batch2.strategies import (
    build_market_shock_reversal_episodes,
    build_oversold_reversal_episodes,
)


KST = timezone(timedelta(hours=9))


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=KST).timestamp())


def _candles(
    *,
    start: int,
    prices: list[float],
    volume: float = 100.0,
) -> list[dict]:
    return [
        {
            "ts": start + index * 60,
            "open": price,
            "high": price + 0.1,
            "low": price - 0.1,
            "close": price,
            "volume": volume,
        }
        for index, price in enumerate(prices)
    ]


def test_market_return_uses_only_completed_minutes() -> None:
    start = _epoch("2026-07-10T09:30:00")
    rows = _candles(start=start, prices=[100.0] * 30 + [1000.0])

    result = market_return_15m(
        rows,
        decision_epoch=_epoch("2026-07-10T10:00:10"),
        day="2026-07-10",
    )

    assert result == 0.0


def test_oversold_reversal_contract() -> None:
    start = _epoch("2026-07-10T09:30:00")
    prices = [110.0 - index for index in range(15)] + [96.5, 97.0]
    rows = _candles(start=start, prices=prices)

    result = oversold_reversal_features(
        rows,
        decision_epoch=_epoch("2026-07-10T09:47:10"),
        day="2026-07-10",
    )

    assert result["oversold_ok"] is True
    assert result["reversal_ok"] is True
    assert result["volume_ok"] is True


def test_trend_pullback_resumption_contract() -> None:
    start = _epoch("2026-07-10T09:30:00")
    prices = [100.0 + index * 0.2 for index in range(24)]
    prices.extend([104.0, 105.2])
    rows = _candles(start=start, prices=prices)
    rows[-2]["high"] = 105.0

    result = trend_pullback_features(
        rows,
        decision_epoch=_epoch("2026-07-10T09:56:10"),
        day="2026-07-10",
    )

    assert result["trend_ok"] is True
    assert result["pullback_reclaim_ok"] is True
    assert result["resume_ok"] is True


def test_market_shock_selection_is_deterministic() -> None:
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
            ],
        }
    ]
    market = [100.0] * 14 + [99.5 - index * 0.1 for index in range(17)]
    candles = {
        "069500": _candles(start=start, prices=market),
        "229200": _candles(start=start, prices=market),
        "A": _candles(
            start=start,
            prices=[100.0] * 24 + [100.0 + index * 0.2 for index in range(7)],
            volume=200.0,
        ),
        "B": _candles(
            start=start,
            prices=[100.0] * 24 + [100.0 + index * 0.1 for index in range(7)],
            volume=200.0,
        ),
    }
    candles["A"][29]["volume"] = 300.0
    candles["B"][29]["volume"] = 300.0

    first = build_market_shock_reversal_episodes(
        windows,
        minute_rows_by_symbol=candles,
    )
    second = build_market_shock_reversal_episodes(
        windows,
        minute_rows_by_symbol=dict(reversed(list(candles.items()))),
    )

    assert first == second
    assert first[0]["symbol"] == "A"
    assert first[0]["baseline_epoch"] == _epoch("2026-07-10T10:00:00")


def test_oversold_episode_spacing_is_global() -> None:
    start = _epoch("2026-07-10T09:30:00")
    prices = [110.0 - index for index in range(15)] + [96.5, 97.0] + [97.0] * 20
    windows = [
        {
            "decision_id": "d1",
            "day": "2026-07-10",
            "decision_epoch": _epoch("2026-07-10T09:47:10"),
            "candidates": [{"rank": 1, "symbol": "A"}],
        },
        {
            "decision_id": "d2",
            "day": "2026-07-10",
            "decision_epoch": _epoch("2026-07-10T09:50:10"),
            "candidates": [{"rank": 1, "symbol": "A"}],
        },
    ]

    result = build_oversold_reversal_episodes(
        windows,
        minute_rows_by_symbol={"A": _candles(start=start, prices=prices)},
    )

    assert len(result) == 1


def test_batch2_has_no_execution_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("libs/research/structural_alpha_batch2").glob("*.py")
    )

    assert "OrderIntent" not in source
    assert "libs.runtime.execution" not in source
    assert "graphs.nodes" not in source
