from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from typing import Optional

# Korea Stock Exchange regular session (default): 09:00-15:30 KST
KST = timezone(timedelta(hours=9))

@dataclass(frozen=True)
class MarketHours:
    open_time: time = time(9, 0)
    close_time: time = time(15, 30)
    tz = KST

    def is_open(self, dt: datetime) -> bool:
        """Return True if dt is within market hours on a weekday (Mon-Fri) in KST."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        else:
            dt = dt.astimezone(self.tz)

        if dt.weekday() >= 5:
            return False

        t = dt.time()
        return (t >= self.open_time) and (t <= self.close_time)

def now_kst() -> datetime:
    return datetime.now(tz=KST)
