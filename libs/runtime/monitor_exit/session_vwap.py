from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from libs.runtime.monitor_exit.numeric import to_float


KST = ZoneInfo("Asia/Seoul")
SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(15, 30)


def _row_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
        if numeric > 0:
            return datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(KST)
    except (TypeError, ValueError, OSError):
        pass
    text = str(value).strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def current_session_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [dict(row) for row in rows if isinstance(row, Mapping)]
    dated = [
        (_row_datetime(row.get("ts") or row.get("timestamp") or row.get("datetime")), row)
        for row in normalized
    ]
    valid = [(stamp, row) for stamp, row in dated if stamp is not None]
    if not valid:
        return normalized
    latest_day = max(stamp.date() for stamp, _row in valid)
    return [
        row
        for stamp, row in valid
        if stamp.date() == latest_day
        and SESSION_OPEN <= stamp.time().replace(tzinfo=None) <= SESSION_CLOSE
    ]


def rows_with_session_vwap(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    session_rows = current_session_rows(rows)
    if not session_rows:
        return [], "current_session_minute_rows_unavailable"
    cumulative_value = 0.0
    cumulative_volume = 0.0
    out: list[dict[str, Any]] = []
    explicit_only = True
    for source_row in session_rows:
        row = dict(source_row)
        volume = max(0.0, to_float(row.get("volume")))
        explicit_vwap = to_float(row.get("vwap"))
        high = to_float(row.get("high"))
        low = to_float(row.get("low"))
        close = to_float(row.get("close"))
        typical = (high + low + close) / 3.0 if high > 0 and low > 0 and close > 0 else close
        if volume > 0 and typical > 0:
            cumulative_value += typical * volume
            cumulative_volume += volume
        if explicit_vwap <= 0:
            explicit_only = False
            derived = cumulative_value / cumulative_volume if cumulative_volume > 0 else 0.0
            if derived > 0:
                row["vwap"] = derived
                row["vwap_source"] = "derived_current_session_typical_price_volume"
        else:
            row["vwap_source"] = "explicit_minute_vwap"
        out.append(row)
    source = (
        "explicit_current_session_minute_vwap"
        if explicit_only
        else "derived_current_session_minute_vwap"
    )
    return out, source


__all__ = ["current_session_rows", "rows_with_session_vwap"]
