from __future__ import annotations

from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

def to_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)

def kst_day_str(dt: datetime) -> str:
    k = to_kst(dt)
    return k.strftime("%Y-%m-%d")
