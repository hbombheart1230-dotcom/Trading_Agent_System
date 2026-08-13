from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import INTRADAY_HORIZONS, LIVE_COST_PCT


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _day(row: Mapping[str, Any]) -> str:
    raw = str(row.get("raw_ts") or "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return str(row.get("day") or "")


def _net(price: float | None, baseline: float) -> float | None:
    if price is None or baseline <= 0.0:
        return None
    return round((price / baseline - 1.0) * 100.0 - LIVE_COST_PCT, 4)


def _checkpoint(
    rows: Sequence[Mapping[str, Any]],
    *,
    baseline_epoch: int,
    baseline_price: float,
    target_epoch: int,
) -> dict[str, Any]:
    path = [row for row in rows if baseline_epoch <= int(row.get("ts") or 0) <= target_epoch]
    target = next((row for row in rows if int(row.get("ts") or 0) >= target_epoch), None)
    if target is None:
        return {"status": "MISSING", "net_return_pct": None, "mfe_pct": None, "mae_pct": None}
    path = [*path, target]
    highs = [_number(row.get("high")) for row in path]
    lows = [_number(row.get("low")) for row in path]
    high = max((value for value in highs if value is not None), default=None)
    low = min((value for value in lows if value is not None), default=None)
    return {
        "status": "OBSERVED",
        "observed_epoch": int(target.get("ts") or 0),
        "price": _number(target.get("close")),
        "net_return_pct": _net(_number(target.get("close")), baseline_price),
        "mfe_pct": _net(high, baseline_price),
        "mae_pct": _net(low, baseline_price),
    }


def _fallback_checkpoint(value: Any) -> dict[str, Any]:
    observed = _number(value)
    return {
        "status": "OBSERVED_FALLBACK" if observed is not None else "MISSING",
        "net_return_pct": observed,
        "mfe_pct": None,
        "mae_pct": None,
    }


def build_original_hold_path(
    *,
    day: str,
    baseline_epoch: int,
    baseline_price: float,
    minute_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    fallback: Mapping[str, Any],
    longitudinal: Mapping[str, Any],
) -> dict[str, Any]:
    same_day = [row for row in minute_rows if _day(row) == day and int(row.get("ts") or 0) >= baseline_epoch]
    checkpoints: dict[str, Any] = {}
    fallback_fields = {5: "return_5m_pct", 15: "return_15m_pct", 30: "net_return_30m_pct", 60: "return_60m_pct"}
    for minutes in INTRADAY_HORIZONS:
        observed = _checkpoint(
            same_day,
            baseline_epoch=baseline_epoch,
            baseline_price=baseline_price,
            target_epoch=baseline_epoch + minutes * 60,
        )
        if observed["status"] == "MISSING" and minutes in fallback_fields:
            observed = _fallback_checkpoint(fallback.get(fallback_fields[minutes]))
        checkpoints[f"+{minutes}m"] = observed
    if same_day:
        close_row = same_day[-1]
        checkpoints["EOD"] = {
            "status": "OBSERVED",
            "observed_epoch": int(close_row.get("ts") or 0),
            "price": _number(close_row.get("close")),
            "net_return_pct": _net(_number(close_row.get("close")), baseline_price),
            "mfe_pct": _net(max((_number(row.get("high")) or 0.0) for row in same_day), baseline_price),
            "mae_pct": _net(min((_number(row.get("low")) or 10**30) for row in same_day), baseline_price),
        }
    else:
        checkpoints["EOD"] = _fallback_checkpoint(fallback.get("return_eod_pct"))

    future_daily = sorted(
        [row for row in daily_rows if _day(row) > day],
        key=lambda row: _day(row),
    )
    if future_daily:
        first = future_daily[0]
        checkpoints["NEXT_OPEN"] = {
            "status": "OBSERVED",
            "observed_day": _day(first),
            "price": _number(first.get("open")),
            "net_return_pct": _net(_number(first.get("open")), baseline_price),
            "mfe_pct": None,
            "mae_pct": None,
        }
        next_day_rows = [row for row in minute_rows if _day(row) == _day(first)]
        if next_day_rows:
            start = int(next_day_rows[0].get("ts") or 0)
            checkpoints["D+1_30m"] = _checkpoint(
                next_day_rows,
                baseline_epoch=start,
                baseline_price=baseline_price,
                target_epoch=start + 1800,
            )
        else:
            checkpoints["D+1_30m"] = {"status": "MISSING", "net_return_pct": None, "mfe_pct": None, "mae_pct": None}
    else:
        checkpoints["NEXT_OPEN"] = {"status": "MISSING", "net_return_pct": None, "mfe_pct": None, "mae_pct": None}
        checkpoints["D+1_30m"] = {"status": "MISSING", "net_return_pct": None, "mfe_pct": None, "mae_pct": None}
    for offset in (1, 2, 3, 5):
        label = f"D+{offset}_EOD"
        if len(future_daily) >= offset:
            row = future_daily[offset - 1]
            checkpoints[label] = {
                "status": "OBSERVED",
                "observed_day": _day(row),
                "price": _number(row.get("close")),
                "net_return_pct": _net(_number(row.get("close")), baseline_price),
                "mfe_pct": None,
                "mae_pct": None,
            }
        else:
            source_key = f"d{offset}_close_net_pct" if offset in (1, 3, 5) else ""
            checkpoints[label] = _fallback_checkpoint(longitudinal.get(source_key)) if source_key else {
                "status": "MISSING", "net_return_pct": None, "mfe_pct": None, "mae_pct": None
            }
    return {
        "schema_version": "rank1_original_hold_path.v1",
        "baseline_epoch": baseline_epoch,
        "baseline_price": baseline_price,
        "round_trip_cost_pct": LIVE_COST_PCT,
        "checkpoints": checkpoints,
    }
