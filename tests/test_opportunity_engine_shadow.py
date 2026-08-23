from __future__ import annotations

import json
from pathlib import Path

from libs.research.opportunity_engine.contracts import PROHIBITED_RUNTIME_DEPENDENCIES
from libs.research.opportunity_engine.data_provider import load_market_timeline
from libs.research.opportunity_engine.engine import build_signal_timeline
from libs.research.opportunity_engine.features import build_market_features, build_symbol_features
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


def test_probe_fail_reasons_and_near_miss_are_recorded() -> None:
    start = 1782259200
    rows = _candles("005930", start=start, step=0.6, volume=100.0)["005930"]
    signals = build_signal_timeline(
        day="2026-06-24",
        candles={"005930": rows},
        market_timeline=[],
    )

    assert signals
    assert all("probe_fail_reasons" in row["opportunity"] for row in signals)
    assert all("market_data_missing" in row["opportunity"] for row in signals)
    assert any(row["opportunity"]["market_data_missing"] for row in signals)


def test_untrusted_kospi200_move_is_preserved_but_excluded_from_relative_strength(tmp_path: Path) -> None:
    day = "2026-07-31"
    day_dir = tmp_path / day
    day_dir.mkdir()
    (day_dir / "090100_macro_indicators.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-31T00:01:00+00:00",
                "index_moves": {"kospi200_pct": 16.29},
                "korea_indices": {"breadth": 0.2},
                "korea_index_sanity": {
                    "status": "warning",
                    "warnings": [
                        {
                            "index": "KOSPI200",
                            "code": "extreme_index_change_pct",
                            "requires_confirmation": True,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    timeline = load_market_timeline(day=day, macro_root=tmp_path)
    market = build_market_features(timeline[0], {})
    symbol = build_symbol_features(
        _candles("009150", start=timeline[0]["ts"], step=0.5)["009150"],
        as_of_epoch=timeline[0]["ts"] + 19 * 60,
        market_features=market,
    )

    assert timeline[0]["kospi200_pct"] is None
    assert timeline[0]["kospi200_pct_raw"] == 16.29
    assert market["kospi200_trusted"] is False
    assert market["kospi200_pct"] == 0.0
    assert symbol["market_relative_strength_reference"] == "market_neutral_fallback"
    assert symbol["market_relative_strength_proxy_pct"] == symbol["open_return_pct"]


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


def test_late_opening_entry_is_observed_beyond_signal_window() -> None:
    start = 1782262500
    signal = {
        "signal_id": "late",
        "symbol": "005930",
        "as_of_epoch": start,
        "symbol_features": {
            "price": 100.0,
            "atr_6_pct": 0.5,
            "opening_low": 90.0,
        },
        "opportunity": {"probe_candidate": True, "score": 0.8},
    }
    candles = []
    for index in range(31):
        candles.append({
            "ts": start + index * 60,
            "raw_ts": f"2026062410{index:02d}00",
            "close": 100.0 + index * 0.1,
            "high": 100.2 + index * 0.1,
            "low": 99.8 + index * 0.1,
        })

    trades = simulate_probe_v0(
        [signal],
        cost_pct=0.2,
        slippage_pct=0.05,
        minute_rows_by_symbol={"005930": candles},
    )

    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "max_hold"
    assert trades[0]["held_minutes"] == 30
    assert trades[0]["price_extrema_source"] == "minute_high_low"
    assert trades[0]["mfe_pct"] > trades[0]["gross_return_pct"]


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
    report = Path(result["daily_report"]).read_text(encoding="utf-8")
    assert signals["behavior_effect"] == "shadow_only"
    assert signals["measurement_contract_version"] == "q11_market_freshness.v2"
    trades = json.loads(Path(result["virtual_trades"]).read_text(encoding="utf-8"))
    assert trades["measurement_contract_version"] == "q11_minute_path.v2"
    assert signals["evaluation_program_id"] == "Q11_OPENING_SURGE_MARKET_REVERSAL"
    assert signals["research_window"] == "09:00-10:00 KST"
    assert "market_data_missing_signal_count" in signals["data_quality"]
    assert "probe_near_miss_count" in signals["data_quality"]
    assert "## Probe Near-Misses" in report
    assert "## Probe Fail Reasons" in report
    assert "opportunity_engine_shadow" in result["signals"]
    assert "quant_shadow_candidates" not in result["signals"]


def test_pipeline_preserves_higher_quality_existing_signal_snapshot(tmp_path: Path) -> None:
    start = 1782259200
    first = build_opportunity_engine_artifacts(
        day="2026-06-24",
        symbols=("005930",),
        reports_root=tmp_path / "reports",
        candles=_candles("005930", start=start, step=0.8),
        market_timeline=_market(start),
        allow_fresh_fetch=False,
    )
    first_payload = json.loads(Path(first["signals"]).read_text(encoding="utf-8"))

    second = build_opportunity_engine_artifacts(
        day="2026-06-24",
        symbols=("005930",),
        reports_root=tmp_path / "reports",
        candles={"005930": []},
        market_timeline=_market(start),
        allow_fresh_fetch=False,
    )
    second_payload = json.loads(Path(second["signals"]).read_text(encoding="utf-8"))

    assert second_payload["signal_count"] == first_payload["signal_count"]
    assert second_payload["data_quality"]["preserved_higher_quality_previous_snapshot"] is True
    assert "stale_market_snapshot_signal_count" in second_payload["data_quality"]


def test_package_has_no_q9_or_execution_imports() -> None:
    package = Path("libs/research/opportunity_engine")
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for prohibited in PROHIBITED_RUNTIME_DEPENDENCIES:
        assert f"from {prohibited}" not in source
        assert f"import {prohibited}" not in source
