from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded


def load_market_snapshot(
    logs_root: Path,
    day: date,
    *,
    max_bytes: int,
) -> dict[str, Any] | None:
    path = logs_root / "macro_indicators" / day.isoformat() / "latest.json"
    if not path.is_file():
        return None
    try:
        payload = read_json_bounded(path, max_bytes=max_bytes)
    except (OSError, BoundedReadError):
        return None
    return payload if isinstance(payload, dict) else None
