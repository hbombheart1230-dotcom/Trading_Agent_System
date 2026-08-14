from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded


@dataclass(frozen=True, slots=True)
class PortfolioDaySource:
    day: date
    generated_at: datetime | None
    residual: dict[str, Any] | None
    source_status: str
    error: str | None = None


def load_portfolio_day(
    reports_root: Path,
    day: date,
    *,
    max_bytes: int,
) -> PortfolioDaySource:
    path = (
        reports_root
        / "operator_summary"
        / "daily"
        / day.isoformat()
        / "daily_summary.json"
    )
    if not path.is_file():
        return PortfolioDaySource(day, None, None, "MISSING")
    try:
        payload = read_json_bounded(path, max_bytes=max_bytes)
        if not isinstance(payload, dict):
            raise BoundedReadError("daily summary root must be an object")
        if payload.get("day") != day.isoformat():
            raise BoundedReadError("daily summary day mismatch")
        residual = payload.get("residual_positions")
        if not isinstance(residual, dict):
            raise BoundedReadError("residual_positions must be an object")
        return PortfolioDaySource(
            day,
            _parse_datetime(payload.get("generated_at")),
            residual,
            "VALID",
        )
    except (BoundedReadError, TypeError, ValueError) as exc:
        return PortfolioDaySource(day, None, None, "INVALID", str(exc))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
