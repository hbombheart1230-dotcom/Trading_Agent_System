from __future__ import annotations

import math
import time
from typing import Any, Dict
from datetime import datetime, timezone

DEFAULT_SIGNAL_SCORE = 0.0
SIGNAL_STATUS_OK = "ok"
SIGNAL_STATUS_FALLBACK = "fallback"
SIGNAL_STATUS_UNAVAILABLE = "unavailable"

_VALID_STATUSES = {
    SIGNAL_STATUS_OK,
    SIGNAL_STATUS_FALLBACK,
    SIGNAL_STATUS_UNAVAILABLE,
}


def normalize_signal_score(value: Any, default: float = DEFAULT_SIGNAL_SCORE) -> float:
    try:
        x = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(x):
        return float(default)
    if x < -1.0:
        return -1.0
    if x > 1.0:
        return 1.0
    return float(x)


def make_signal(
    *,
    score: Any = DEFAULT_SIGNAL_SCORE,
    status: str = SIGNAL_STATUS_OK,
    source: str = "",
    reason: str = "",
    ts: int | None = None,
    default_score: float = DEFAULT_SIGNAL_SCORE,
) -> Dict[str, Any]:
    stat = str(status or SIGNAL_STATUS_OK).strip().lower()
    if stat not in _VALID_STATUSES:
        stat = SIGNAL_STATUS_FALLBACK
    ts_epoch = int(time.time())
    if ts is not None:
        try:
            if isinstance(ts, str):
                s = str(ts).strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts_epoch = int(dt.timestamp())
            else:
                ts_epoch = int(float(ts))
        except Exception:
            ts_epoch = int(time.time())
    return {
        "score": normalize_signal_score(score, default=default_score),
        "status": stat,
        "source": str(source or "").strip(),
        "reason": str(reason or "").strip(),
        "ts": ts_epoch,
    }
