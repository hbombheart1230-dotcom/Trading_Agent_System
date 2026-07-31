from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_candles(value: Any, *, day: str) -> list[dict[str, Any]]:
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
        row_day = raw_ts[:8] if len(raw_ts) >= 8 and raw_ts[:8].isdigit() else datetime.fromtimestamp(
            ts, tz=timezone.utc
        ).strftime("%Y%m%d")
        if row_day != compact_day:
            continue
        rows.append(
            {
                "ts": ts,
                "raw_ts": raw_ts,
                "open": _number(raw.get("open")) or close,
                "high": _number(raw.get("high")) or close,
                "low": _number(raw.get("low")) or close,
                "close": close,
                "volume": _number(raw.get("volume")) or 0.0,
            }
        )
    deduped = {int(row["ts"]): row for row in rows}
    return [deduped[key] for key in sorted(deduped)]


def load_candles(
    *,
    day: str,
    symbols: Sequence[str],
    state_path: Path = Path("data/state.json"),
    allow_fresh_fetch: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    root: Mapping[str, Any] = {}
    if isinstance(state, Mapping):
        for key in (
            "recent_minute_ohlcv_by_symbol",
            "minute_ohlcv_by_symbol",
            "monitor_minute_ohlcv_by_symbol",
            "intraday_ohlcv_by_symbol",
        ):
            value = state.get(key)
            if isinstance(value, Mapping) and value:
                root = value
                break
    result = {symbol: normalize_candles(root.get(symbol), day=day) for symbol in symbols}
    if not allow_fresh_fetch:
        return result
    for symbol in symbols:
        if len(result[symbol]) >= 30:
            continue
        try:
            from libs.reporting.post_exit_shadow_recap import fetch_fresh_minute_rows_for_symbol

            fresh, _meta = fetch_fresh_minute_rows_for_symbol(
                symbol,
                run_id=f"opportunity_engine_{day}_{symbol}",
            )
            normalized = normalize_candles(fresh, day=day)
            if len(normalized) > len(result[symbol]):
                result[symbol] = normalized
        except Exception:
            continue
    return result


def load_market_timeline(
    *,
    day: str,
    macro_root: Path = Path("data/logs/macro_indicators"),
) -> list[dict[str, Any]]:
    day_dir = macro_root / day
    rows: list[dict[str, Any]] = []
    for path in sorted(day_dir.glob("*_macro_indicators.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, Mapping):
            continue
        generated_at = str(payload.get("generated_at") or "")
        try:
            epoch = int(datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp())
        except Exception:
            epoch = 0
        moves = payload.get("index_moves") if isinstance(payload.get("index_moves"), Mapping) else {}
        korea = payload.get("korea_indices") if isinstance(payload.get("korea_indices"), Mapping) else {}
        sanity = payload.get("korea_index_sanity") if isinstance(payload.get("korea_index_sanity"), Mapping) else {}
        sanity_warnings = sanity.get("warnings") if isinstance(sanity.get("warnings"), list) else []
        kospi200_warning = next(
            (
                warning
                for warning in sanity_warnings
                if isinstance(warning, Mapping)
                and str(warning.get("index") or "").strip().upper() == "KOSPI200"
                and bool(warning.get("requires_confirmation"))
            ),
            None,
        )
        kospi200_raw = _number(moves.get("kospi200_pct"))
        kospi200_trusted = kospi200_warning is None
        rows.append(
            {
                "ts": epoch,
                "source_path": str(path),
                "kospi_pct": _number(moves.get("kospi_pct")),
                "kosdaq_pct": _number(moves.get("kosdaq_pct")),
                "kospi200_pct": kospi200_raw if kospi200_trusted else None,
                "kospi200_pct_raw": kospi200_raw,
                "kospi200_trusted": kospi200_trusted,
                "market_sanity_status": str(sanity.get("status") or "unknown"),
                "market_sanity_reason": (
                    str(kospi200_warning.get("code") or "confirmation_required")
                    if kospi200_warning is not None
                    else ""
                ),
                "breadth": _number(korea.get("breadth")),
                "rising": int(_number(korea.get("rising")) or 0),
                "falling": int(_number(korea.get("falling")) or 0),
                "nasdaq_pct": _number(moves.get("nasdaq_pct")),
                "sp500_pct": _number(moves.get("sp500_pct")),
                "krx_night_futures_pct": _number(moves.get("krx_night_futures_pct")),
            }
        )
    deduped = {int(row["ts"]): row for row in rows if int(row["ts"]) > 0}
    return [deduped[key] for key in sorted(deduped)]


def market_pair_at(
    timeline: Sequence[Mapping[str, Any]],
    *,
    epoch: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    eligible = [dict(row) for row in timeline if int(row.get("ts") or 0) <= epoch]
    if not eligible:
        return {}, {}
    return eligible[-1], eligible[-2] if len(eligible) >= 2 else {}
