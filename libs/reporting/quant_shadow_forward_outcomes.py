from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from libs.reporting.q8_evaluation_contract import FORWARD_MAX_OBSERVATION_DELAY_SEC


CHECKPOINT_MINUTES = (3, 5, 15, 30, 60)
KST = timezone(timedelta(hours=9))


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


def load_minute_rows_from_state(state_path: Path = Path("data/state.json")) -> Dict[str, list[Dict[str, Any]]]:
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
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


def attach_forward_outcomes(
    candidates: Iterable[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]] | None = None,
) -> list[Dict[str, Any]]:
    rows_by_symbol = minute_rows_by_symbol if minute_rows_by_symbol is not None else load_minute_rows_from_state()
    out: list[Dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        symbol = _text(row.get("symbol"))
        base = row.get("shadow_forward_base") if isinstance(row.get("shadow_forward_base"), Mapping) else {}
        base_epoch = _to_int(base.get("baseline_epoch"), 0) if isinstance(base, Mapping) else 0
        base_price = _to_float(base.get("baseline_price"), None) if isinstance(base, Mapping) else None
        minute_rows = list(rows_by_symbol.get(symbol) or [])
        if (base_epoch <= 0 or base_price is None or base_price <= 0) and minute_rows:
            generated_epoch = _parse_epoch(row.get("_payload_generated_at") or row.get("generated_at"))
            usable = [r for r in minute_rows if int(r.get("ts") or 0) <= generated_epoch] if generated_epoch > 0 else []
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
        if not symbol or base_epoch <= 0 or base_price is None or base_price <= 0 or not minute_rows:
            row["shadow_forward_outcome"] = {
                "available": False,
                "reason": "baseline_or_minute_rows_unavailable",
            }
            out.append(row)
            continue
        checkpoints: Dict[str, Any] = {}
        observed = 0
        base_day = _row_day({"ts": base_epoch, "raw_ts": base.get("baseline_raw_ts") if isinstance(base, Mapping) else ""})
        same_day_rows = [r for r in minute_rows if not base_day or _row_day(r) == base_day]
        for minutes in CHECKPOINT_MINUTES:
            target = int(base_epoch + minutes * 60)
            future = [
                r
                for r in same_day_rows
                if int(r.get("ts") or 0) >= base_epoch and int(r.get("ts") or 0) <= target
            ]
            target_row = next((r for r in same_day_rows if int(r.get("ts") or 0) >= target), None)
            if target_row is None:
                stale_row = next((r for r in minute_rows if int(r.get("ts") or 0) >= target), None)
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
        row["shadow_forward_outcome"] = {
            "available": observed > 0,
            "observed_checkpoint_count": observed,
            "baseline_price": base_price,
            "baseline_epoch": base_epoch,
            "checkpoints": checkpoints,
            "behavior_effect": "evaluation_only",
        }
        out.append(row)
    return out
