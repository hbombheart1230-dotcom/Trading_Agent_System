from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping


ROUND_TRIP_COST_PCT = 0.28


def _day(row: Mapping[str, Any]) -> str:
    raw = str(row.get("raw_ts") or "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return ""


def _price(row: Mapping[str, Any], key: str) -> float | None:
    try:
        value = float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return None
    return value if value > 0.0 else None


def _net(price: float | None, baseline: float) -> float | None:
    if price is None or baseline <= 0.0:
        return None
    return round((price / baseline - 1.0) * 100.0 - ROUND_TRIP_COST_PCT, 4)


def _daily_rows(rows: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        day = _day(row)
        if day:
            grouped[day].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: int(row.get("ts") or 0))
    return dict(grouped)


def forward_30m_net(
    *,
    rows: list[Mapping[str, Any]],
    day: str,
    decision_epoch: int,
) -> float | None:
    day_rows = [
        row
        for row in rows
        if _day(row) == day and int(row.get("ts") or 0) > decision_epoch
    ]
    if not day_rows:
        return None
    entry = day_rows[0]
    baseline = _price(entry, "open") or _price(entry, "close")
    target_epoch = int(entry.get("ts") or 0) + 1800
    target = next(
        (row for row in day_rows if int(row.get("ts") or 0) >= target_epoch),
        None,
    )
    if baseline is None or target is None:
        return None
    return _net(_price(target, "close"), baseline)


def delayed_path(
    case: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    *,
    trading_calendar: list[str],
) -> dict[str, Any]:
    baseline = float(case.get("virtual_buy_price") or 0.0)
    baseline_epoch = _iso_epoch(case.get("virtual_buy_time_kst"))
    event_day = str(case.get("day") or "")
    grouped = _daily_rows(rows)
    future_days = [
        day
        for day in trading_calendar
        if day > event_day
    ]
    observed_future_days = [
        day
        for day in future_days
        if day in grouped
    ]
    result: dict[str, Any] = {
        "longitudinal_status": "MISSING",
        "available_future_day_count": len(observed_future_days),
        "future_days": future_days[:5],
        "observed_future_days": observed_future_days[:5],
    }
    if baseline <= 0.0 or event_day not in grouped:
        return result

    event_rows_after_30m = [
        row
        for row in grouped[event_day]
        if int(row.get("ts") or 0) >= baseline_epoch + 1800
    ]
    same_day_high = max(
        (_price(row, "high") or 0.0 for row in event_rows_after_30m),
        default=0.0,
    )
    event_close = _price(grouped[event_day][-1], "close")
    result.update(
        {
            "longitudinal_status": "OBSERVED",
            "same_day_after_30m_max_high_net_pct": _net(
                same_day_high or None,
                baseline,
            ),
            "same_day_close_net_pct": _net(event_close, baseline),
        }
    )

    for horizon in (1, 3, 5):
        selected_days = future_days[:horizon]
        prefix = f"d{horizon}"
        missing_days = [
            day
            for day in selected_days
            if day not in grouped
        ]
        if len(selected_days) < horizon or missing_days:
            result[f"{prefix}_status"] = "INSUFFICIENT_FUTURE_DAYS"
            result[f"{prefix}_missing_days"] = missing_days
            result[f"{prefix}_max_high_net_pct"] = None
            result[f"{prefix}_close_net_pct"] = None
            continue
        selected_rows = [
            row
            for day in selected_days
            for row in grouped.get(day) or []
        ]
        max_high = max(
            (_price(row, "high") or 0.0 for row in selected_rows),
            default=0.0,
        )
        last_close = _price(grouped[selected_days[-1]][-1], "close")
        result[f"{prefix}_status"] = "OBSERVED"
        result[f"{prefix}_max_high_net_pct"] = _net(
            max_high or None,
            baseline,
        )
        result[f"{prefix}_close_net_pct"] = _net(last_close, baseline)

    threshold_rows = [
        (day_index, day, row)
        for day_index, day in enumerate([event_day, *future_days[:5]])
        for row in grouped.get(day) or []
        if day > event_day or int(row.get("ts") or 0) >= baseline_epoch + 1800
    ]
    for threshold in (3.0, 5.0, 10.0):
        match = next(
            (
                (day_index, day, row)
                for day_index, day, row in threshold_rows
                if (_net(_price(row, "high"), baseline) or -10**9) >= threshold
            ),
            None,
        )
        key = str(int(threshold))
        result[f"first_plus_{key}pct_day_offset"] = match[0] if match else None
        result[f"first_plus_{key}pct_day"] = match[1] if match else None
        result[f"first_plus_{key}pct_epoch"] = (
            int(match[2].get("ts") or 0)
            if match
            else None
        )

    net_30m = float(case.get("net_return_30m_pct") or 0.0)
    d5_high = result.get("d5_max_high_net_pct")
    d5_close = result.get("d5_close_net_pct")
    result["delayed_high_opportunity"] = bool(
        net_30m <= 0.0
        and d5_high is not None
        and float(d5_high) >= 5.0
    )
    result["delayed_close_confirmation"] = bool(
        net_30m <= 0.0
        and d5_close is not None
        and float(d5_close) >= 3.0
    )
    if net_30m > 0.0:
        result["selection_horizon_label"] = "IMMEDIATE_POSITIVE"
    elif result["delayed_close_confirmation"]:
        result["selection_horizon_label"] = "HORIZON_TOO_SHORT_CONFIRMED"
    elif result["delayed_high_opportunity"]:
        result["selection_horizon_label"] = "DELAYED_HIGH_ONLY"
    elif result.get("d5_status") == "OBSERVED":
        result["selection_horizon_label"] = "NO_LATER_EDGE"
    else:
        result["selection_horizon_label"] = "INSUFFICIENT_FUTURE"
    return result


def _iso_epoch(value: Any) -> int:
    from datetime import datetime

    try:
        return int(
            datetime.fromisoformat(
                str(value or "").replace("Z", "+00:00")
            ).timestamp()
        )
    except ValueError:
        return 0
