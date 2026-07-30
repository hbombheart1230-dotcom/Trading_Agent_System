from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_rows(value: Any, *, day: str = "") -> list[dict[str, Any]]:
    raw_rows = value.get("rows") if isinstance(value, Mapping) else value
    if not isinstance(raw_rows, list):
        return []
    compact_day = day.replace("-", "")
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            continue
        ts = int(_number(raw.get("ts")) or 0)
        close = _number(raw.get("close") or raw.get("price"))
        if ts <= 0 or close is None or close <= 0:
            continue
        raw_ts = str(raw.get("raw_ts") or raw.get("datetime") or raw.get("time") or "")
        row_day = (
            raw_ts[:8]
            if len(raw_ts) >= 8 and raw_ts[:8].isdigit()
            else datetime.fromtimestamp(ts, tz=KST).strftime("%Y%m%d")
        )
        if compact_day and row_day != compact_day:
            continue
        volume = _number(raw.get("volume"))
        rows.append(
            {
                "ts": ts,
                "raw_ts": raw_ts,
                "open": _number(raw.get("open")) or close,
                "high": _number(raw.get("high")) or close,
                "low": _number(raw.get("low")) or close,
                "close": close,
                "volume": volume or 0.0,
            }
        )
    rows.sort(key=lambda row: int(row["ts"]))
    return rows


def load_existing_candles(
    *,
    state_path: Path = Path("data/state.json"),
    day: str,
    symbols: tuple[str, ...],
    allow_fresh_fetch: bool = True,
    run_id_prefix: str = "baseline_samsung_hynix",
) -> dict[str, list[dict[str, Any]]]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {symbol: [] for symbol in symbols}
    if not isinstance(state, Mapping):
        return {symbol: [] for symbol in symbols}
    root: Mapping[str, Any] = {}
    for key in (
        "recent_minute_ohlcv_by_symbol",
        "minute_ohlcv_by_symbol",
        "monitor_minute_ohlcv_by_symbol",
        "intraday_ohlcv_by_symbol",
        "ohlcv_by_symbol",
    ):
        value = state.get(key)
        if isinstance(value, Mapping) and value:
            root = value
            break
    result = {
        symbol: _normalize_rows(root.get(symbol), day=day)
        for symbol in symbols
    }
    if not allow_fresh_fetch:
        return result
    for symbol in symbols:
        for attempt in range(2):
            try:
                from libs.reporting.post_exit_shadow_recap import (
                    fetch_fresh_minute_rows_for_symbol,
                )

                fresh, _meta = fetch_fresh_minute_rows_for_symbol(
                    symbol,
                    run_id=(
                        f"{str(run_id_prefix or 'minute_ohlcv_recovery')}_"
                        f"{day}_{symbol}_{attempt + 1}"
                    ),
                )
                normalized = _normalize_rows(fresh, day=day)
                existing = result.get(symbol) or []
                existing_latest = int(existing[-1].get("ts") or 0) if existing else 0
                fresh_latest = int(normalized[-1].get("ts") or 0) if normalized else 0
                if fresh_latest > existing_latest or (
                    fresh_latest == existing_latest and len(normalized) > len(existing)
                ):
                    result[symbol] = normalized
                if normalized:
                    break
            except Exception:
                if attempt == 1:
                    break
    return result


def load_market_change_pct(
    *,
    day: str,
    macro_root: Path = Path("data/logs/macro_indicators"),
) -> float | None:
    path = macro_root / day / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    moves = payload.get("index_moves")
    moves = moves if isinstance(moves, Mapping) else {}
    return _number(moves.get("kospi_pct"))


def common_as_of_epoch(
    candles: Mapping[str, list[Mapping[str, Any]]],
    *,
    requested_epoch: int | None = None,
) -> int:
    if not candles or any(not rows for rows in candles.values()):
        return 0
    latest = [
        int(rows[-1].get("ts") or 0)
        for rows in candles.values()
        if rows and int(rows[-1].get("ts") or 0) > 0
    ]
    if not latest:
        return 0
    common = min(latest)
    return min(common, int(requested_epoch)) if requested_epoch else common
