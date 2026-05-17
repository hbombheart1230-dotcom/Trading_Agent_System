from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from libs.runtime.market_hours import MarketHours


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def monitor_runtime_dt_kst(
    state: Dict[str, Any],
    *,
    market_hours: MarketHours | None = None,
) -> datetime:
    market_hours_obj = market_hours or MarketHours()
    tick_ts = _to_int(state.get("tick_ts"))
    if tick_ts > 0:
        return datetime.fromtimestamp(tick_ts, tz=timezone.utc).astimezone(market_hours_obj.tz)
    for key in ("tick_ts_iso", "ts", "now_iso", "started_at"):
        text = str(state.get(key) or "").strip()
        if not text:
            continue
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=market_hours_obj.tz)
            return dt.astimezone(market_hours_obj.tz)
        except Exception:
            continue
    return datetime.now(tz=market_hours_obj.tz)


def monitor_runtime_clock_input_present(state: Dict[str, Any]) -> bool:
    if _to_int(state.get("tick_ts")) > 0:
        return True
    return any(str(state.get(key) or "").strip() for key in ("tick_ts_iso", "ts", "now_iso", "started_at"))


def carry_calendar_context(state: Dict[str, Any]) -> Dict[str, Any]:
    if not monitor_runtime_clock_input_present(state):
        return {
            "calendar_known": False,
            "date_kst": "",
            "weekday": None,
            "weekday_name": "",
            "weekend_carry": False,
            "holding_gap_days": 1,
            "reason": "runtime_clock_missing",
        }
    dt_kst = monitor_runtime_dt_kst(state)
    weekday = int(dt_kst.weekday())
    weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekend_carry = weekday == 4
    return {
        "calendar_known": True,
        "date_kst": dt_kst.date().isoformat(),
        "weekday": weekday,
        "weekday_name": weekday_names[weekday] if 0 <= weekday < len(weekday_names) else "",
        "weekend_carry": bool(weekend_carry),
        "holding_gap_days": 3 if weekend_carry else 1,
        "reason": "friday_weekend_gap" if weekend_carry else "regular_overnight",
    }


def ensure_entry_market_context_clock_fields(
    state: Dict[str, Any],
    *,
    market_hours: MarketHours | None = None,
) -> Dict[str, Any]:
    market_hours_obj = market_hours or MarketHours()
    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    out = dict(market_context or {})
    existing_minutes = _optional_float(out.get("minutes_to_close"))
    has_reliable_runtime_clock = monitor_runtime_clock_input_present(state)
    if existing_minutes is not None and not has_reliable_runtime_clock:
        state["market_context"] = out
        return out
    dt_kst = monitor_runtime_dt_kst(state, market_hours=market_hours_obj)
    minutes_to_close: float | None = None
    if market_hours_obj.is_open(dt_kst):
        close_dt = dt_kst.replace(
            hour=market_hours_obj.close_time.hour,
            minute=market_hours_obj.close_time.minute,
            second=0,
            microsecond=0,
        )
        minutes_to_close = max(0.0, (close_dt - dt_kst).total_seconds() / 60.0)
    if minutes_to_close is None and existing_minutes is not None:
        state["market_context"] = out
        return out

    previous_source = str(out.get("market_clock_source") or "")
    if existing_minutes is not None and minutes_to_close is not None:
        drift = abs(float(existing_minutes) - float(minutes_to_close))
        if drift <= 1.0:
            out["minutes_to_close"] = float(existing_minutes)
            out.setdefault("market_clock_source", previous_source or "runtime_clock_verified")
            out.setdefault("market_clock_kst", dt_kst.isoformat())
            out["market_clock_verified_minutes_to_close"] = float(minutes_to_close)
            state["market_context"] = out
            return out
        out["market_clock_previous_minutes_to_close"] = float(existing_minutes)
        if previous_source:
            out["market_clock_previous_source"] = previous_source
        out["market_clock_source"] = "runtime_clock_override"
    else:
        out.setdefault("market_clock_source", "runtime_clock")
    out["minutes_to_close"] = minutes_to_close
    out["market_clock_kst"] = dt_kst.isoformat()
    state["market_context"] = out
    return out
