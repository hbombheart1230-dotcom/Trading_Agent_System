from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
DEFAULT_STOP_HOUR = 16
DEFAULT_STOP_MINUTE = 10


def should_stop_shadow_loop(
    *,
    day: str,
    now: datetime | None = None,
    stop_hour: int = DEFAULT_STOP_HOUR,
    stop_minute: int = DEFAULT_STOP_MINUTE,
) -> bool:
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    current = current.astimezone(KST)
    if current.date().isoformat() != day:
        return True
    return (current.hour, current.minute) >= (stop_hour, stop_minute)
