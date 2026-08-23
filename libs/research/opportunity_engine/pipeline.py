from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .contracts import (
    DEFAULT_SLIPPAGE_PCT,
    DEFAULT_SYMBOLS,
    PROGRAM_ID,
    PROGRAM_NAME,
    REPORT_SCHEMA,
    SIGNALS_SCHEMA,
    TRADES_SCHEMA,
)
from .data_provider import load_candles, load_market_timeline
from .engine import build_signal_timeline
from .report import render_report
from .simulator import simulate_probe_v0, summarize_trades


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _signal_payload_quality(payload: Mapping[str, Any]) -> tuple[int, int, int]:
    quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), Mapping) else {}
    signal_count = int(payload.get("signal_count") or 0)
    candle_rows = int(quality.get("candle_row_count") or 0)
    missing_count = len(list(quality.get("missing_symbols") or [])) if isinstance(quality.get("missing_symbols"), list) else 0
    return signal_count, candle_rows, -missing_count


def build_opportunity_engine_artifacts(
    *,
    day: str,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
    reports_root: Path = Path("reports"),
    state_path: Path = Path("data/state.json"),
    macro_root: Path = Path("data/logs/macro_indicators"),
    cost_profile_path: Path | None = None,
    candles: Mapping[str, list[Mapping[str, Any]]] | None = None,
    market_timeline: Sequence[Mapping[str, Any]] | None = None,
    allow_fresh_fetch: bool = True,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> dict[str, str]:
    normalized_symbols = tuple(sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()}))
    candle_map = (
        {symbol: [dict(row) for row in candles.get(symbol, [])] for symbol in normalized_symbols}
        if candles is not None
        else load_candles(
            day=day,
            symbols=normalized_symbols,
            state_path=state_path,
            allow_fresh_fetch=allow_fresh_fetch,
        )
    )
    timeline = [dict(row) for row in market_timeline] if market_timeline is not None else load_market_timeline(
        day=day,
        macro_root=macro_root,
    )
    signals = build_signal_timeline(day=day, candles=candle_map, market_timeline=timeline)
    profile = load_broker_cost_profile(cost_profile_path)
    cost_pct = float(profile.get("conservative_round_trip_cost_pct") or 0.0) * 100.0
    trades = simulate_probe_v0(
        signals,
        cost_pct=cost_pct,
        slippage_pct=slippage_pct,
        minute_rows_by_symbol=candle_map,
    )
    summary = summarize_trades(trades)
    market_missing_count = sum(
        1
        for row in signals
        if not bool((row.get("market") or {}).get("available"))
        or bool((row.get("opportunity") or {}).get("market_data_missing"))
    )
    probe_near_miss_count = sum(1 for row in signals if bool((row.get("opportunity") or {}).get("probe_near_miss")))
    stale_market_count = sum(
        1 for row in signals if bool((row.get("market") or {}).get("snapshot_stale"))
    )
    data_quality = {
        "symbol_count": len(normalized_symbols),
        "symbols_with_candles": sum(1 for rows in candle_map.values() if rows),
        "candle_row_count": sum(len(rows) for rows in candle_map.values()),
        "market_snapshot_count": len(timeline),
        "market_data_missing_signal_count": market_missing_count,
        "probe_near_miss_count": probe_near_miss_count,
        "stale_market_snapshot_signal_count": stale_market_count,
        "missing_symbols": [symbol for symbol, rows in candle_map.items() if not rows],
    }
    output_dir = reports_root / "evaluation" / "opportunity_engine_shadow" / day
    signals_path = output_dir / "opportunity_engine_signals.json"
    trades_path = output_dir / "opportunity_engine_virtual_trades.json"
    report_path = output_dir / "opportunity_engine_daily_report.md"
    metadata_path = output_dir / "opportunity_engine_daily_report.json"
    existing_signal_payload = _read_json(signals_path)
    if existing_signal_payload and _signal_payload_quality(existing_signal_payload) > (len(signals), int(data_quality["candle_row_count"]), -len(data_quality["missing_symbols"])):
        existing_signals = existing_signal_payload.get("signals") if isinstance(existing_signal_payload.get("signals"), list) else []
        if existing_signals:
            signals = [dict(row) for row in existing_signals if isinstance(row, Mapping)]
            for signal in signals:
                market = signal.get("market")
                if not isinstance(market, dict):
                    continue
                age = market.get("snapshot_age_sec")
                market["snapshot_stale"] = bool(
                    age is not None and int(float(age)) > 300
                )
            trades = simulate_probe_v0(
                signals,
                cost_pct=cost_pct,
                slippage_pct=slippage_pct,
                minute_rows_by_symbol=candle_map,
            )
            summary = summarize_trades(trades)
            data_quality = dict(existing_signal_payload.get("data_quality") or {})
            data_quality["preserved_higher_quality_previous_snapshot"] = True
            data_quality["stale_market_snapshot_signal_count"] = sum(
                1 for row in signals if bool((row.get("market") or {}).get("snapshot_stale"))
            )
    _write_json(
        signals_path,
        {
            "schema_version": SIGNALS_SCHEMA,
            "measurement_contract_version": "q11_market_freshness.v2",
            "evaluation_program_id": PROGRAM_ID,
            "evaluation_program_name": PROGRAM_NAME,
            "behavior_effect": "shadow_only",
            "research_window": "09:00-10:00 KST",
            "day": day,
            "symbols": list(normalized_symbols),
            "signal_count": len(signals),
            "data_quality": data_quality,
            "signals": signals,
        },
    )
    _write_json(
        trades_path,
        {
            "schema_version": TRADES_SCHEMA,
            "measurement_contract_version": "q11_minute_path.v2",
            "evaluation_program_id": PROGRAM_ID,
            "evaluation_program_name": PROGRAM_NAME,
            "behavior_effect": "shadow_only",
            "research_window": "09:00-10:00 KST",
            "day": day,
            "strategy_id": "probe_v0",
            "cost_model": {
                "source": str(profile.get("source") or "broker_cost_profile_unavailable"),
                "round_trip_cost_pct": round(cost_pct, 6),
                "slippage_pct": round(float(slippage_pct), 6),
            },
            "summary": summary,
            "trade_count": len(trades),
            "trades": trades,
        },
    )
    report_path.write_text(
        render_report(
            day=day,
            signals=signals,
            trades=trades,
            summary=summary,
            data_quality=data_quality,
        ),
        encoding="utf-8",
    )
    _write_json(
        metadata_path,
        {
            "schema_version": REPORT_SCHEMA,
            "evaluation_program_id": PROGRAM_ID,
            "evaluation_program_name": PROGRAM_NAME,
            "behavior_effect": "shadow_only",
            "research_window": "09:00-10:00 KST",
            "day": day,
            "signals_path": str(signals_path),
            "virtual_trades_path": str(trades_path),
            "markdown_path": str(report_path),
        },
    )
    return {
        "signals": str(signals_path),
        "virtual_trades": str(trades_path),
        "daily_report": str(report_path),
        "daily_report_metadata": str(metadata_path),
    }
