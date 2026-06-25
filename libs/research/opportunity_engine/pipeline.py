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
    )
    summary = summarize_trades(trades)
    data_quality = {
        "symbol_count": len(normalized_symbols),
        "symbols_with_candles": sum(1 for rows in candle_map.values() if rows),
        "candle_row_count": sum(len(rows) for rows in candle_map.values()),
        "market_snapshot_count": len(timeline),
        "missing_symbols": [symbol for symbol, rows in candle_map.items() if not rows],
    }
    output_dir = reports_root / "evaluation" / "opportunity_engine_shadow" / day
    signals_path = output_dir / "opportunity_engine_signals.json"
    trades_path = output_dir / "opportunity_engine_virtual_trades.json"
    report_path = output_dir / "opportunity_engine_daily_report.md"
    metadata_path = output_dir / "opportunity_engine_daily_report.json"
    _write_json(
        signals_path,
        {
            "schema_version": SIGNALS_SCHEMA,
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
