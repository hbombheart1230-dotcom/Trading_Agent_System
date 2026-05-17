from __future__ import annotations

from typing import Any, Dict

from graphs.nodes.skill_contracts import extract_minute_ohlcv_by_symbol
from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_minute_ohlcv import _ensure_monitor_minute_ohlcv_for_symbol, _latest_row_ts

POST_EXIT_SHADOW_WATCH_MAX_SYMBOLS = 3
POST_EXIT_SHADOW_WATCH_WINDOW_SEC = 90 * 60


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def active_post_exit_shadow_watches(state: Dict[str, Any], *, now_epoch: int) -> Dict[str, Dict[str, Any]]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw = persisted.get("post_exit_shadow_watchlist")
    rows = list(raw.values()) if isinstance(raw, dict) else list(raw) if isinstance(raw, list) else []
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol:
            continue
        exit_epoch = _to_int(row.get("exit_epoch") or row.get("sold_epoch") or row.get("ts"))
        if exit_epoch <= 0:
            continue
        expires_epoch = _to_int(row.get("expires_epoch")) or int(exit_epoch + POST_EXIT_SHADOW_WATCH_WINDOW_SEC)
        if now_epoch > 0 and expires_epoch > 0 and now_epoch > expires_epoch:
            continue
        normalized = dict(row)
        normalized["symbol"] = symbol
        normalized["exit_epoch"] = int(exit_epoch)
        normalized["expires_epoch"] = int(expires_epoch)
        normalized["observability_only"] = True
        out[symbol] = normalized
    return out


def refresh_post_exit_shadow_watchlist_minute_rows(state: Dict[str, Any], *, now_epoch: int) -> Dict[str, Any]:
    watches = active_post_exit_shadow_watches(state, now_epoch=now_epoch)
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    if not watches:
        if isinstance(persisted.get("post_exit_shadow_watchlist"), (dict, list)):
            persisted.pop("post_exit_shadow_watchlist", None)
            state["persisted_state"] = persisted
        state["post_exit_shadow_watchlist_refresh"] = {
            "enabled": True,
            "observability_only": True,
            "watch_count": 0,
            "refreshed_symbols": [],
            "reason": "no_active_watches",
        }
        return state

    refreshed_symbols: list[str] = []
    refresh_rows: list[Dict[str, Any]] = []
    for symbol, watch in sorted(watches.items(), key=lambda item: int((item[1] or {}).get("exit_epoch") or 0), reverse=True):
        if len(refreshed_symbols) >= POST_EXIT_SHADOW_WATCH_MAX_SYMBOLS:
            break
        state = _ensure_monitor_minute_ohlcv_for_symbol(
            state,
            symbol=symbol,
            timeframe_minutes=1,
            now_epoch=int(now_epoch or 0),
            prefer_fresh_runner=False,
        )
        minute_rows_by_symbol, minute_meta = extract_minute_ohlcv_by_symbol(state)
        rows = minute_rows_by_symbol.get(symbol) if isinstance(minute_rows_by_symbol, dict) else []
        latest_ts = _latest_row_ts(rows) if isinstance(rows, list) else None
        fetch_meta = (
            dict(state.get("monitor_minute_ohlcv_fetch") or {})
            if isinstance(state.get("monitor_minute_ohlcv_fetch"), dict)
            else {}
        )
        updated_watch = dict(watch)
        updated_watch["last_refresh_epoch"] = int(now_epoch or 0)
        updated_watch["latest_candle_ts"] = latest_ts
        updated_watch["minute_source"] = str((minute_meta or {}).get("source") or fetch_meta.get("source") or "")
        updated_watch["post_exit_rows_available"] = bool(latest_ts and latest_ts >= _to_int(watch.get("exit_epoch")))
        watches[symbol] = updated_watch
        refreshed_symbols.append(symbol)
        refresh_rows.append(
            {
                "symbol": symbol,
                "latest_candle_ts": latest_ts,
                "row_count": len(rows) if isinstance(rows, list) else 0,
                "minute_refetch_attempted": bool(fetch_meta.get("minute_refetch_attempted")),
                "minute_refetch_succeeded": bool(fetch_meta.get("minute_refetch_succeeded")),
                "minute_refetch_reason": str(fetch_meta.get("minute_refetch_reason") or ""),
                "post_exit_rows_available": bool(updated_watch.get("post_exit_rows_available")),
            }
        )

    persisted["post_exit_shadow_watchlist"] = watches
    state["persisted_state"] = persisted
    state["post_exit_shadow_watchlist_refresh"] = {
        "enabled": True,
        "observability_only": True,
        "watch_count": len(watches),
        "refreshed_symbols": refreshed_symbols,
        "rows": refresh_rows,
        "reason": "refreshed_active_watches" if refreshed_symbols else "no_symbols_refreshed",
    }
    return state

