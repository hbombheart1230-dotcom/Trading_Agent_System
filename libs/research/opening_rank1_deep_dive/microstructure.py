from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


def load_minute_rows(cache_root: Path, symbols: set[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for symbol in sorted(symbols):
        path = cache_root / f"{symbol}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        result[symbol] = sorted(
            [dict(row) for row in (rows or []) if isinstance(row, dict) and int(row.get("ts") or 0) > 0],
            key=lambda row: int(row.get("ts") or 0),
        )
    return result


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator - 1.0) * 100.0, 4)


def _day_key(row: dict[str, Any]) -> str:
    raw = str(row.get("raw_ts") or "")
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) >= 8 else ""


def _target_price(rows: list[dict[str, Any]], target_epoch: int) -> float | None:
    for row in rows:
        if int(row.get("ts") or 0) >= target_epoch:
            value = float(row.get("close") or 0.0)
            return value if value > 0 else None
    return None


def _prior_day_volume_reference(
    rows_by_day: dict[str, list[dict[str, Any]]],
    *,
    day: str,
    elapsed_minute: int,
) -> float | None:
    references: list[float] = []
    for prior_day, rows in rows_by_day.items():
        if prior_day >= day:
            continue
        opening = rows[: max(1, elapsed_minute + 1)]
        if opening:
            references.append(sum(float(row.get("volume") or 0.0) for row in opening))
    return median(references[-10:]) if references else None


def microstructure_features(
    case: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    day = str(case.get("day") or "")
    decision_epoch = _iso_epoch(case.get("decision_time_kst"))
    baseline_epoch = _iso_epoch(case.get("virtual_buy_time_kst"))
    day_rows = [row for row in rows if _day_key(row) == day]
    if not day_rows or decision_epoch <= 0 or baseline_epoch <= 0:
        return {"microstructure_status": "MISSING"}
    rows_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _day_key(row)
        if key:
            rows_by_day[key].append(row)
    opening = day_rows[0]
    entry = next((row for row in day_rows if int(row.get("ts") or 0) == baseline_epoch), {})
    previous_rows = [row for row in rows if _day_key(row) < day]
    prior_close = float(previous_rows[-1].get("close") or 0.0) if previous_rows else 0.0
    opening_price = float(opening.get("open") or 0.0)
    entry_price = float(case.get("virtual_buy_price") or 0.0)
    completed = [row for row in day_rows if int(row.get("ts") or 0) + 60 <= decision_epoch]
    last_completed = completed[-1] if completed else {}
    # A minute row contains the completed bar's volume. Only bars fully closed
    # before the decision are valid point-in-time evidence.
    observed_opening = completed
    elapsed_minute = max(0, len(observed_opening) - 1)
    opening_volume = sum(float(row.get("volume") or 0.0) for row in observed_opening)
    reference_volume = (
        _prior_day_volume_reference(
            rows_by_day,
            day=day,
            elapsed_minute=elapsed_minute,
        )
        if observed_opening
        else None
    )
    path = [
        row
        for row in day_rows
        if baseline_epoch <= int(row.get("ts") or 0) <= baseline_epoch + 1800
    ]
    high_row = max(path, key=lambda row: float(row.get("high") or 0.0), default={})
    low_row = min(path, key=lambda row: float(row.get("low") or 10**30), default={})
    gross_5m = _gross_horizon(case.get("return_5m_pct"))
    gross_30m = _gross_horizon(case.get("net_return_30m_pct"))
    entry_vs_prior = _pct(entry_price, prior_close)
    path_high = float(high_row.get("high") or 0.0) if high_row else 0.0
    high_vs_prior = _pct(path_high, prior_close)
    return {
        "microstructure_status": "OBSERVED",
        "decision_second": decision_epoch % 60,
        "decision_from_open_sec": max(0, decision_epoch - int(opening.get("ts") or decision_epoch)),
        "baseline_delay_sec": max(0, baseline_epoch - decision_epoch),
        "opening_price": opening_price or None,
        "prior_close": prior_close or None,
        "opening_gap_pct": _pct(opening_price, prior_close),
        "entry_vs_prior_close_pct": entry_vs_prior,
        "path_high_vs_prior_close_pct": high_vs_prior,
        "open_to_entry_pct": _pct(entry_price, opening_price),
        "last_completed_bar_time": last_completed.get("raw_ts"),
        "last_completed_close": float(last_completed.get("close") or 0.0) or None,
        "completed_bar_count_before_decision": len(completed),
        "precompleted_return_1m_pct": _completed_return(completed, 1),
        "precompleted_return_3m_pct": _completed_return(completed, 3),
        "precompleted_return_5m_pct": _completed_return(completed, 5),
        "opening_observed_volume": round(opening_volume, 4)
        if observed_opening
        else None,
        "opening_volume_reference": round(reference_volume, 4) if reference_volume else None,
        "opening_relative_volume": round(opening_volume / reference_volume, 4)
        if reference_volume and reference_volume > 0
        else None,
        "entry_bar_volume": float(entry.get("volume") or 0.0) or None,
        "time_to_mfe_sec": max(0, int(high_row.get("ts") or baseline_epoch) - baseline_epoch)
        if high_row
        else None,
        "time_to_mae_sec": max(0, int(low_row.get("ts") or baseline_epoch) - baseline_epoch)
        if low_row
        else None,
        "first_plus_1pct_sec": _first_threshold(path, entry_price, 1.0, high=True),
        "first_minus_1pct_sec": _first_threshold(path, entry_price, -1.0, high=False),
        "gross_return_1m_pct": _pct(_target_price(path, baseline_epoch + 60) or 0.0, entry_price),
        "gross_return_3m_pct": _pct(_target_price(path, baseline_epoch + 180) or 0.0, entry_price),
        "gross_return_10m_pct": _pct(_target_price(path, baseline_epoch + 600) or 0.0, entry_price),
        "gross_return_20m_pct": _pct(_target_price(path, baseline_epoch + 1200) or 0.0, entry_price),
        "path_type": _path_type(gross_5m, gross_30m),
        "price_arc": _price_arc(
            entry_vs_prior=entry_vs_prior,
            high_vs_prior=high_vs_prior,
            net_30m=case.get("net_return_30m_pct"),
        ),
    }


def _iso_epoch(value: Any) -> int:
    from datetime import datetime

    try:
        return int(datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _completed_return(rows: list[dict[str, Any]], minutes: int) -> float | None:
    if len(rows) <= minutes:
        return None
    return _pct(float(rows[-1].get("close") or 0.0), float(rows[-1 - minutes].get("close") or 0.0))


def _first_threshold(
    rows: list[dict[str, Any]],
    entry_price: float,
    threshold_pct: float,
    *,
    high: bool,
) -> int | None:
    if entry_price <= 0:
        return None
    target = entry_price * (1.0 + threshold_pct / 100.0)
    baseline = int(rows[0].get("ts") or 0) if rows else 0
    for row in rows:
        value = float(row.get("high" if high else "low") or 0.0)
        if (high and value >= target) or (not high and value <= target):
            return max(0, int(row.get("ts") or 0) - baseline)
    return None


def _gross_horizon(net_return: Any) -> float | None:
    try:
        return float(net_return) + 0.28 if net_return is not None else None
    except (TypeError, ValueError):
        return None


def _path_type(gross_5m: float | None, gross_30m: float | None) -> str:
    if gross_5m is None or gross_30m is None:
        return "INSUFFICIENT"
    if gross_5m >= 1.0 and gross_30m > 0.28:
        return "IMMEDIATE_EXPANSION"
    if gross_5m < 1.0 and gross_30m > 0.28:
        return "DELAYED_EXPANSION"
    if gross_5m > 0.28 and gross_30m <= 0.28:
        return "EARLY_FADE"
    return "IMMEDIATE_FAILURE"


def _price_arc(
    *,
    entry_vs_prior: float | None,
    high_vs_prior: float | None,
    net_30m: Any,
) -> str:
    if entry_vs_prior is None or high_vs_prior is None:
        return "INSUFFICIENT"
    if high_vs_prior >= 28.0:
        return "LIMIT_UP_TRAJECTORY"
    if entry_vs_prior <= -10.0 and float(net_30m or 0.0) > 0.0:
        return "CRASH_REVERSAL"
    if entry_vs_prior >= 5.0:
        return "GAP_OR_MOMENTUM"
    return "NORMAL"
