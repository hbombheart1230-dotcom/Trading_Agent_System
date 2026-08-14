from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded


@dataclass(frozen=True, slots=True)
class PerformanceDaySource:
    day: date
    generated_at: datetime | None
    rows: tuple[dict[str, Any], ...]
    total_trades: int
    source_status: str
    error: str | None = None


def load_performance_day(
    reports_root: Path,
    day: date,
    *,
    max_bytes: int,
) -> PerformanceDaySource:
    path = reports_root / "performance" / day.isoformat() / "summary.json"
    if not path.is_file():
        return PerformanceDaySource(day, None, (), 0, "MISSING")
    try:
        payload = read_json_bounded(path, max_bytes=max_bytes)
        if not isinstance(payload, dict):
            raise BoundedReadError("performance summary root must be an object")
        if payload.get("schema_version") != "performance_summary.v1":
            raise BoundedReadError("unsupported performance summary schema")
        if payload.get("day") != day.isoformat():
            raise BoundedReadError("performance summary day mismatch")
        rows = payload.get("trade_rows")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise BoundedReadError("trade_rows must be an object array")
        generated_at = _parse_datetime(payload.get("generated_at"))
        total_trades = int(payload.get("total_trades", len(rows)))
        return PerformanceDaySource(
            day,
            generated_at,
            tuple(rows),
            total_trades,
            "VALID",
        )
    except (BoundedReadError, TypeError, ValueError) as exc:
        return PerformanceDaySource(day, None, (), 0, "INVALID", str(exc))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
