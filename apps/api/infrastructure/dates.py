from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


def inclusive_days(start: date, end: date, *, max_days: int) -> list[date]:
    if end < start:
        raise ValueError("end date must not precede start date")
    count = (end - start).days + 1
    if count > max_days:
        raise ValueError(f"date range exceeds {max_days} days")
    return [start + timedelta(days=offset) for offset in range(count)]


def latest_iso_day(root: Path) -> date | None:
    if not root.is_dir():
        return None
    days: list[date] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            days.append(date.fromisoformat(child.name))
        except ValueError:
            continue
    return max(days) if days else None
