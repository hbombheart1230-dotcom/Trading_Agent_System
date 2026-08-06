from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix.data_provider import (
    load_existing_candles,
)
from libs.research.post_reclaim_alpha.kiwoom_history import (
    KiwoomHistoricalMinuteReader,
    load_or_fetch_symbol_history,
)


KST = timezone(timedelta(hours=9))


def load_historical_reference_rows(
    *,
    cache_root: Path,
    symbols: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    result = {}
    for symbol in symbols:
        try:
            payload = json.loads(
                (cache_root / f"{symbol}.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            payload = {}
        rows = payload.get("rows") if isinstance(payload, Mapping) else []
        result[symbol] = sorted(
            [
                dict(row)
                for row in rows or []
                if isinstance(row, Mapping) and int(row.get("ts") or 0) > 0
            ],
            key=lambda row: int(row.get("ts") or 0),
        )
    return result


def _day_rows(rows: list[Mapping[str, Any]], day: str) -> list[dict[str, Any]]:
    result = []
    for raw in rows:
        epoch = int(raw.get("ts") or 0)
        if epoch <= 0:
            continue
        if datetime.fromtimestamp(epoch, tz=KST).date().isoformat() != day:
            continue
        close = float(raw.get("close") or 0.0)
        if close <= 0.0:
            continue
        result.append(dict(raw))
    return sorted(result, key=lambda row: int(row.get("ts") or 0))


def _close_complete(rows: list[Mapping[str, Any]]) -> bool:
    if not rows:
        return False
    latest = datetime.fromtimestamp(int(rows[-1].get("ts") or 0), tz=KST)
    return latest.hour * 60 + latest.minute >= 15 * 60 + 20


def load_opening_candles(
    *,
    state_path: Path,
    day: str,
    symbols: tuple[str, ...],
    allow_fresh_fetch: bool,
    cache_root: Path = Path(
        "data/research/opening_rank1_shadow/minute_cache"
    ),
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    candles = load_existing_candles(
        state_path=state_path,
        day=day,
        symbols=symbols,
        allow_fresh_fetch=allow_fresh_fetch,
        run_id_prefix="opening_rank1_shadow",
    )
    unresolved = [
        symbol
        for symbol in symbols
        if not _close_complete(candles.get(symbol) or [])
    ]
    history_meta: dict[str, Any] = {}
    if unresolved:
        reader = KiwoomHistoricalMinuteReader.from_env() if allow_fresh_fetch else None
        minimum_epoch = int(
            datetime.fromisoformat(day)
            .replace(hour=9, minute=0, second=0, tzinfo=KST)
            .timestamp()
        )
        for symbol in unresolved:
            rows, meta = load_or_fetch_symbol_history(
                reader=reader,
                symbol=symbol,
                minimum_epoch=minimum_epoch,
                cache_root=cache_root,
                max_pages=20,
            )
            history_meta[symbol] = meta
            historical_day_rows = _day_rows(rows, day)
            if _close_complete(historical_day_rows) or not candles.get(symbol):
                candles[symbol] = historical_day_rows
    return candles, {
        "state_or_current_fetch_symbol_count": sum(
            bool(rows) for rows in candles.values()
        ),
        "historical_fallback_requested_symbols": unresolved,
        "historical_fallback": history_meta,
        "complete_symbol_count": sum(
            _close_complete(rows) for rows in candles.values()
        ),
    }
