from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import CHECKPOINTS, TARGETS


KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _pct(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0.0):
        return None
    return round((current / base - 1.0) * 100.0, 6)


def _checkpoint_epoch(day: str, label: str) -> int:
    parsed = time(15, 30) if label == "CLOSE" else time.fromisoformat(label)
    return int(datetime.combine(date.fromisoformat(day), parsed, tzinfo=KST).timestamp())


def _point_at(rows: list[Mapping[str, Any]], epoch: int, max_lag_sec: int) -> dict[str, Any] | None:
    candidate = next((row for row in rows if int(row.get("ts") or 0) >= epoch), None)
    if candidate is None or int(candidate.get("ts") or 0) - epoch > max_lag_sec:
        return None
    return dict(candidate)


def _close_point(rows: list[Mapping[str, Any]], day: str) -> dict[str, Any] | None:
    close_epoch = _checkpoint_epoch(day, "CLOSE")
    auction_start = close_epoch - 10 * 60
    eligible = [row for row in rows if auction_start <= int(row.get("ts") or 0) <= close_epoch + 60]
    return dict(eligible[-1]) if eligible else None


def _forward_window(rows: list[Mapping[str, Any]], *, entry_ts: int, entry_price: float | None) -> dict[str, Any]:
    if entry_price in (None, 0.0):
        return {"status": "PENDING", "return_to_close_pct": None, "mfe_pct": None, "mae_pct": None}
    future = [row for row in rows if int(row.get("ts") or 0) >= entry_ts]
    if not future:
        return {"status": "PENDING", "return_to_close_pct": None, "mfe_pct": None, "mae_pct": None}
    prices = [_number(row.get("close")) for row in future]
    prices = [value for value in prices if value is not None]
    return {
        "status": "OBSERVED" if prices else "PENDING",
        "return_to_close_pct": _pct(prices[-1], entry_price) if prices else None,
        "mfe_pct": _pct(max(prices), entry_price) if prices else None,
        "mae_pct": _pct(min(prices), entry_price) if prices else None,
    }


def _stock_reaction(
    *, day: str, target: Mapping[str, Any], rows: list[Mapping[str, Any]], previous_close: float | None
) -> dict[str, Any]:
    valid = sorted(
        (dict(row) for row in rows if int(row.get("ts") or 0) > 0 and _number(row.get("close")) is not None),
        key=lambda row: int(row["ts"]),
    )
    points: dict[str, Any] = {}
    for label in CHECKPOINTS:
        point = _close_point(valid, day) if label == "CLOSE" else _point_at(valid, _checkpoint_epoch(day, label), 90)
        price_field = "open" if label == "09:00" else "close"
        points[label] = (
            {
                "status": "OBSERVED",
                "ts": int(point["ts"]),
                "price": _number(point.get(price_field)),
                "volume": _number(point.get("volume")),
                "return_from_previous_close_pct": _pct(_number(point.get(price_field)), previous_close),
            }
            if point
            else {"status": "PENDING", "price": None, "volume": None}
        )
    regular = [
        row for row in valid
        if _checkpoint_epoch(day, "09:00") <= int(row["ts"]) <= _checkpoint_epoch(day, "CLOSE") + 300
    ]
    highs = [_number(row.get("high")) for row in regular]
    lows = [_number(row.get("low")) for row in regular]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    open_price = (points.get("09:00") or {}).get("price")
    forward_windows = {
        label: _forward_window(
            regular,
            entry_ts=int((points.get(label) or {}).get("ts") or 0),
            entry_price=_number((points.get(label) or {}).get("price")),
        )
        for label in CHECKPOINTS[:-1]
    }
    if (points.get("CLOSE") or {}).get("status") != "OBSERVED":
        for window in forward_windows.values():
            if window.get("status") == "OBSERVED":
                window["status"] = "PARTIAL"
                window["return_to_close_pct"] = None
    return {
        "target": dict(target),
        "source": "q10_current_day_minute_candles",
        "previous_close": previous_close,
        "opening_gap_pct": _pct(_number(open_price), previous_close),
        "points": points,
        "forward_windows": forward_windows,
        "day_high": max(highs) if highs else None,
        "day_low": min(lows) if lows else None,
        "day_high_return_pct": _pct(max(highs), previous_close) if highs else None,
        "day_low_return_pct": _pct(min(lows), previous_close) if lows else None,
        "evidence_status": "AVAILABLE" if open_price is not None else "INSUFFICIENT_EVIDENCE",
        "path": regular,
    }


def load_index_timeline(*, day: str, macro_root: Path, index_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((macro_root / day).glob("*_macro_indicators.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            generated = datetime.fromisoformat(str(payload.get("generated_at") or "").replace("Z", "+00:00"))
            item = (((payload.get("korea_indices") or {}).get("indices") or {}).get(index_name) or {})
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        current = _number(item.get("current"))
        if current is None:
            continue
        rows.append(
            {
                "ts": int(generated.timestamp()),
                "close": current,
                "open": _number(item.get("open")) or current,
                "high": _number(item.get("high")) or current,
                "low": _number(item.get("low")) or current,
                "volume": _number(item.get("volume")),
                "previous_close": _number(item.get("previous_close")),
                "source_path": str(path),
            }
        )
    return [row for _, row in sorted({int(row["ts"]): row for row in rows}.items())]


def _index_reaction(*, day: str, target: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    previous_close = next((_number(row.get("previous_close")) for row in rows if _number(row.get("previous_close")) is not None), None)
    result = _stock_reaction(day=day, target=target, rows=rows, previous_close=previous_close)
    result["source"] = "kiwoom_ka20009_macro_snapshots"
    return result


def build_actual_reactions(
    *, day: str, candle_map: Mapping[str, list[Mapping[str, Any]]], macro_root: Path, signal_inputs: Mapping[str, Any]
) -> dict[str, Any]:
    reactions: dict[str, Any] = {}
    for target in TARGETS:
        key = str(target["key"])
        if target["kind"] == "stock":
            previous_key = "hynix_previous_close" if key == "sk_hynix" else f"{key}_previous_close"
            reactions[key] = _stock_reaction(
                day=day,
                target=target,
                rows=list(candle_map.get(str(target["symbol"])) or []),
                previous_close=_number(signal_inputs.get(previous_key)),
            )
        else:
            reactions[key] = _index_reaction(
                day=day,
                target=target,
                rows=load_index_timeline(day=day, macro_root=macro_root, index_name=str(target["symbol"])),
            )
    return {"day": day, "targets": reactions}
