from __future__ import annotations

from bisect import bisect_left, bisect_right
from copy import deepcopy
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from libs.reporting.q8_evaluation_contract import FORWARD_MAX_OBSERVATION_DELAY_SEC


CHECKPOINT_MINUTES = (3, 5, 15, 30, 60)
KST = timezone(timedelta(hours=9))
EOD_READY_TIME = (15, 20)


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_epoch(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except Exception:
        pass
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def _parse_raw_ts_epoch(value: Any) -> int:
    text = _text(value)
    if len(text) >= 14 and text[:14].isdigit():
        try:
            return int(datetime.strptime(text[:14], "%Y%m%d%H%M%S").replace(tzinfo=KST).timestamp())
        except Exception:
            return 0
    return _parse_epoch(text)


def _kst_day_from_epoch(value: Any) -> str:
    epoch = _to_int(value, 0)
    if epoch <= 0:
        return ""
    try:
        return datetime.fromtimestamp(epoch, tz=KST).strftime("%Y%m%d")
    except Exception:
        return ""


def _row_day(row: Mapping[str, Any]) -> str:
    raw_ts = _text(row.get("raw_ts"))
    if len(raw_ts) >= 8 and raw_ts[:8].isdigit():
        return raw_ts[:8]
    return _kst_day_from_epoch(row.get("ts"))


def _kst_time_tuple(row: Mapping[str, Any]) -> tuple[int, int]:
    epoch = _parse_raw_ts_epoch(row.get("raw_ts")) or _to_int(row.get("ts"), 0)
    if epoch <= 0:
        return (0, 0)
    dt = datetime.fromtimestamp(epoch, tz=KST)
    return (dt.hour, dt.minute)


def _normalize_rows(value: Any) -> list[Dict[str, Any]]:
    if isinstance(value, Mapping) and isinstance(value.get("rows"), list):
        raw_rows = value.get("rows") or []
    elif isinstance(value, list):
        raw_rows = value
    else:
        raw_rows = []
    rows: list[Dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            continue
        ts = _to_int(raw.get("ts"), 0)
        close = _to_float(raw.get("close") or raw.get("price"), None)
        if ts <= 0 or close is None or close <= 0:
            continue
        high = _to_float(raw.get("high"), close) or close
        low = _to_float(raw.get("low"), close) or close
        rows.append(
            {
                "ts": ts,
                "close": float(close),
                "high": float(high),
                "low": float(low),
                "raw_ts": _text(raw.get("raw_ts") or raw.get("datetime") or raw.get("time")),
            }
        )
    rows.sort(key=lambda item: int(item["ts"]))
    return rows


@lru_cache(maxsize=4)
def _load_minute_rows_from_state_cached(
    resolved_path: str,
    mtime_ns: int,
    size: int,
) -> Dict[str, list[Dict[str, Any]]]:
    del mtime_ns, size
    try:
        state = json.loads(Path(resolved_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(state, Mapping):
        return {}
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
    return {str(symbol): _normalize_rows(rows) for symbol, rows in root.items()}


def load_minute_rows_from_state(state_path: Path = Path("data/state.json")) -> Dict[str, list[Dict[str, Any]]]:
    path = Path(state_path)
    try:
        stat = path.stat()
        resolved_path = str(path.resolve())
    except Exception:
        return {}
    return _load_minute_rows_from_state_cached(
        resolved_path,
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def attach_forward_outcomes(
    candidates: Iterable[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]] | None = None,
) -> list[Dict[str, Any]]:
    candidate_rows = [dict(candidate) for candidate in candidates]
    rows_by_symbol = minute_rows_by_symbol if minute_rows_by_symbol is not None else load_minute_rows_from_state()
    snapshot_rows: dict[str, dict[int, Dict[str, Any]]] = {}
    for candidate in candidate_rows:
        symbol = _text(candidate.get("symbol"))
        base = candidate.get("shadow_forward_base")
        base = base if isinstance(base, Mapping) else {}
        epoch = _to_int(base.get("baseline_epoch"), 0)
        price = _to_float(base.get("baseline_price"), None)
        if not symbol or epoch <= 0 or price is None or price <= 0:
            continue
        snapshot_rows.setdefault(symbol, {})[epoch] = {
            "ts": epoch,
            "close": float(price),
            "high": float(price),
            "low": float(price),
            "raw_ts": _text(base.get("baseline_raw_ts")),
        }
    out: list[Dict[str, Any]] = []
    outcome_cache: dict[tuple[str, int, float, str], Dict[str, Any]] = {}
    same_day_rows_cache: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    same_day_epochs_cache: dict[tuple[str, str], list[int]] = {}
    symbol_epochs_cache: dict[str, list[int]] = {}
    for candidate in candidate_rows:
        row = dict(candidate)
        symbol = _text(row.get("symbol"))
        base = row.get("shadow_forward_base") if isinstance(row.get("shadow_forward_base"), Mapping) else {}
        base_epoch = _to_int(base.get("baseline_epoch"), 0) if isinstance(base, Mapping) else 0
        base_price = _to_float(base.get("baseline_price"), None) if isinstance(base, Mapping) else None
        minute_rows = list(rows_by_symbol.get(symbol) or [])
        observation_source = "state.minute_ohlcv_by_symbol"
        if not minute_rows:
            fallback_rows = sorted(
                (snapshot_rows.get(symbol) or {}).values(),
                key=lambda item: int(item.get("ts") or 0),
            )
            if len(fallback_rows) >= 2:
                minute_rows = fallback_rows
                observation_source = "q9_scanner_snapshot_series"
        generated_epoch = _parse_epoch(row.get("_payload_generated_at") or row.get("generated_at"))
        generated_day = _kst_day_from_epoch(generated_epoch)
        if (base_epoch <= 0 or base_price is None or base_price <= 0) and minute_rows:
            usable = [
                r
                for r in minute_rows
                if int(r.get("ts") or 0) <= generated_epoch
                and (not generated_day or _row_day(r) == generated_day)
            ] if generated_epoch > 0 else []
            baseline_row = usable[-1] if usable else None
            if baseline_row:
                base_epoch = int(baseline_row.get("ts") or 0)
                base_price = _to_float(baseline_row.get("close"), None)
                row["shadow_forward_base"] = {
                    "available": bool(base_epoch > 0 and base_price and base_price > 0),
                    "baseline_epoch": base_epoch,
                    "baseline_price": base_price,
                    "baseline_raw_ts": baseline_row.get("raw_ts"),
                    "source": "summary.state.minute_ohlcv_by_symbol",
                }
        if not symbol:
            row["shadow_forward_outcome"] = {
                "available": False,
                "reason": "symbol_missing",
            }
            out.append(row)
            continue
        if not minute_rows:
            row["shadow_forward_outcome"] = {
                "available": False,
                "reason": "minute_rows_unavailable",
            }
            out.append(row)
            continue
        if base_epoch <= 0 or base_price is None or base_price <= 0:
            row["shadow_forward_outcome"] = {
                "available": False,
                "reason": "baseline_unavailable",
            }
            out.append(row)
            continue
        base_day = _row_day(
            {
                "ts": base_epoch,
                "raw_ts": base.get("baseline_raw_ts") if isinstance(base, Mapping) else "",
            }
        )
        if generated_day and base_day and generated_day != base_day:
            row["shadow_forward_outcome"] = {
                "available": False,
                "reason": "stale_baseline_cross_day",
                "generated_day": generated_day,
                "baseline_day": base_day,
            }
            out.append(row)
            continue
        cache_key = (symbol, int(base_epoch), float(base_price), base_day)
        cached_outcome = outcome_cache.get(cache_key)
        if cached_outcome is not None:
            row["shadow_forward_outcome"] = deepcopy(cached_outcome)
            out.append(row)
            continue
        checkpoints: Dict[str, Any] = {}
        observed = 0
        day_cache_key = (symbol, base_day)
        same_day_rows = same_day_rows_cache.get(day_cache_key)
        if same_day_rows is None:
            same_day_rows = sorted(
                [r for r in minute_rows if not base_day or _row_day(r) == base_day],
                key=lambda item: int(item.get("ts") or 0),
            )
            same_day_rows_cache[day_cache_key] = same_day_rows
            same_day_epochs_cache[day_cache_key] = [
                int(item.get("ts") or 0) for item in same_day_rows
            ]
        same_day_epochs = same_day_epochs_cache.get(day_cache_key) or []
        start_index = bisect_left(same_day_epochs, base_epoch)
        for minutes in CHECKPOINT_MINUTES:
            target = int(base_epoch + minutes * 60)
            target_index = bisect_left(same_day_epochs, target)
            target_row = (
                same_day_rows[target_index]
                if target_index < len(same_day_rows)
                else None
            )
            future_end = bisect_right(same_day_epochs, target)
            future = same_day_rows[start_index:future_end]
            if target_row is None:
                symbol_epochs = symbol_epochs_cache.get(symbol)
                if symbol_epochs is None:
                    symbol_epochs = [int(item.get("ts") or 0) for item in minute_rows]
                    symbol_epochs_cache[symbol] = symbol_epochs
                stale_index = bisect_left(symbol_epochs, target)
                stale_row = (
                    minute_rows[stale_index]
                    if stale_index < len(minute_rows)
                    else None
                )
                stale_day = _row_day(stale_row) if isinstance(stale_row, Mapping) else ""
                if stale_row is not None and base_day and stale_day and stale_day != base_day:
                    checkpoints[f"+{minutes}m"] = {
                        "status": "stale",
                        "reason": "stale_cross_day_observation",
                        "base_day": base_day,
                        "observed_day": stale_day,
                        "target_epoch": target,
                        "observed_epoch": _parse_raw_ts_epoch(stale_row.get("raw_ts"))
                        or _to_int(stale_row.get("ts"), 0),
                        "observed_ts": stale_row.get("raw_ts") or stale_row.get("ts"),
                    }
                else:
                    checkpoints[f"+{minutes}m"] = {"status": "pending"}
                continue
            observed_epoch = _parse_raw_ts_epoch(target_row.get("raw_ts")) or _to_int(target_row.get("ts"), 0)
            delay_sec = int(observed_epoch - target) if observed_epoch > 0 else 0
            if observed_epoch <= 0 or delay_sec > FORWARD_MAX_OBSERVATION_DELAY_SEC:
                checkpoints[f"+{minutes}m"] = {
                    "status": "stale",
                    "reason": "stale_forward_gap",
                    "target_epoch": target,
                    "observed_epoch": observed_epoch,
                    "delay_sec": delay_sec,
                    "max_delay_sec": FORWARD_MAX_OBSERVATION_DELAY_SEC,
                    "observed_ts": target_row.get("raw_ts") or target_row.get("ts"),
                }
                continue
            window = future or [target_row]
            close = _to_float(target_row.get("close"), base_price) or base_price
            high = max(_to_float(r.get("high"), base_price) or base_price for r in window)
            low = min(_to_float(r.get("low"), base_price) or base_price for r in window)
            checkpoints[f"+{minutes}m"] = {
                "status": "observed",
                "return_pct": round(((close / base_price) - 1.0) * 100.0, 4),
                "mfe_pct": round(((high / base_price) - 1.0) * 100.0, 4),
                "mae_pct": round(((low / base_price) - 1.0) * 100.0, 4),
                "price": close,
                "high": high,
                "low": low,
                "observed_ts": target_row.get("raw_ts") or target_row.get("ts"),
            }
            observed += 1
        eod_index = len(same_day_rows) - 1
        eod_row = same_day_rows[eod_index] if eod_index >= start_index else None
        if eod_row is not None and _kst_time_tuple(eod_row) >= EOD_READY_TIME:
            eod_close = _to_float(eod_row.get("close"), base_price) or base_price
            eod_window = same_day_rows[start_index : eod_index + 1] or [eod_row]
            checkpoints["EOD"] = {
                "status": "observed",
                "return_pct": round(((eod_close / base_price) - 1.0) * 100.0, 4),
                "mfe_pct": round(
                    ((max(_to_float(r.get("high"), base_price) or base_price for r in eod_window) / base_price) - 1.0)
                    * 100.0,
                    4,
                ),
                "mae_pct": round(
                    ((min(_to_float(r.get("low"), base_price) or base_price for r in eod_window) / base_price) - 1.0)
                    * 100.0,
                    4,
                ),
                "price": eod_close,
                "observed_ts": eod_row.get("raw_ts") or eod_row.get("ts"),
            }
            observed += 1
        else:
            checkpoints["EOD"] = {"status": "pending"}
        row["shadow_forward_outcome"] = {
            "available": observed > 0,
            "observed_checkpoint_count": observed,
            "baseline_price": base_price,
            "baseline_epoch": base_epoch,
            "observation_source": observation_source,
            "checkpoints": checkpoints,
            "behavior_effect": "evaluation_only",
        }
        outcome_cache[cache_key] = deepcopy(row["shadow_forward_outcome"])
        out.append(row)
    return out
