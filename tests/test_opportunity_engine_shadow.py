from __future__ import annotations

import json
from pathlib import Path

from libs.research.opportunity_engine.contracts import PROHIBITED_RUNTIME_DEPENDENCIES
from libs.research.opportunity_engine.engine import build_signal_timeline
from libs.research.opportunity_engine.pipeline import build_opportunity_engine_artifacts
from libs.research.opportunity_engine.simulator import simulate_probe_v0


def _candles(symbol: str, *, start: int, step: float, volume: float = 100.0) -> dict[str, list[dict]]:
    rows = []
    for index in range(20):
        price = 100.0 + step * index
        rows.append(
            {
                "ts": start + index * 60,
                "raw_ts": f"2026062409{index:02d}00",
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": volume * (1.5 if index >= 6 else 1.0),
            }
        )
    return {symbol: rows}


def _market(start: int) -> list[dict]:
    return [
        {"ts": start, "kospi200_pct": 0.0, "breadth": -0.2},
        {"ts": start + 300, "kospi200_pct": 1.0, "breadth": 0.0},
        {"ts": start + 600, "kospi200_pct": 2.0, "breadth": 0.2},
    ]


def test_signal_timeline_is_deterministic() -> None:
    start = 1782259200
    candles = {
        **_candles("005930", start=start, step=0.5),
        **_candles("000660", start=start, step=0.3),
    }
    first = build_signal_timeline(day="2026-06-24", candles=candles, market_timeline=_market(start))
    second = build_signal_timeline(
        day="2026-06-24",
        candles=dict(reversed(list(candles.items()))),
        market_timeline=_market(start),
    )
    assert [(row["as_of_epoch"], row["symbol"], row["opportunity"]["score"]) for row in first] == [
        (row["as_of_epoch"], row["symbol"], row["opportunity"]["score"]) for row in second
    ]


def test_market_reversal_and_surge_candidate_are_observed() -> None:
    start = 1782259200
    signals = build_signal_timeline(
        day="2026-06-24",
        candles=_candles("005930", start=start, step=0.8),
        market_timeline=_market(start),
    )
    assert any(row["market"]["state"] in {"broad_market_reversal", "risk_on_acceleration"} for row in signals)
    assert any(row["opportunity"]["probe_candidate"] for row in signals)


def test_signal_timeline_is_limited_to_opening_hour() -> None:
    start = 1782259200
    rows = _candles("005930", start=start, step=0.8)["005930"]
    for index in range(61, 70):
        price = 100.0 + 0.8 * index
        rows.append(
            {
                "ts": start + index * 60,
                "raw_ts": f"2026062410{index - 60:02d}00",
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 150.0,
            }
        )
    signals = build_signal_timeline(
        day="2026-06-24",
        candles={"005930": rows},
        market_timeline=_market(start),
    )

    assert signals
    assert max(row["as_of_epoch"] for row in signals) <= start + 60 * 60
    assert all(row["research_window"] == "09:00-10:00 KST" for row in signals)


def test_virtual_trade_never_allows_execution() -> None:
    start = 1782259200
    signals = build_signal_timeline(
        day="2026-06-24",
        candles=_candles("005930", start=start, step=0.8),
        market_timeline=_market(start),
    )
    trades = simulate_probe_v0(signals, cost_pct=0.2, slippage_pct=0.05, max_hold_minutes=5)
    assert trades
    assert all(row["behavior_effect"] == "shadow_only" for row in trades)
    assert all(row["order_execution_allowed"] is False for row in trades)
    assert all(row["net_return_pct"] < row["gross_return_pct"] for row in trades)


def test_artifacts_are_separate_from_q9(tmp_path: Path) -> None:
    start = 1782259200
    result = build_opportunity_engine_artifacts(
        day="2026-06-24",
        symbols=("005930",),
        reports_root=tmp_path / "reports",
        candles=_candles("005930", start=start, step=0.8),
        market_timeline=_market(start),
        allow_fresh_fetch=False,
    )
    signals = json.loads(Path(result["signals"]).read_text(encoding="utf-8"))
    assert signals["behavior_effect"] == "shadow_only"
    assert signals["evaluation_program_id"] == "Q11_OPENING_SURGE_MARKET_REVERSAL"
    assert signals["research_window"] == "09:00-10:00 KST"
    assert "opportunity_engine_shadow" in result["signals"]
    assert "quant_shadow_candidates" not in result["signals"]


def test_package_has_no_q9_or_execution_imports() -> None:
    package = Path("libs/research/opportunity_engine")
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for prohibited in PROHIBITED_RUNTIME_DEPENDENCIES:
        assert f"from {prohibited}" not in source
        assert f"import {prohibited}" not in source
