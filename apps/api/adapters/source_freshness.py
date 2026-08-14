from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FreshnessObservation:
    source: str
    available: bool
    modified_at: datetime | None
    age_seconds: float | None


def inspect_runtime_event_freshness(
    logs_root: Path,
    *,
    now: datetime,
) -> FreshnessObservation:
    path = logs_root / "events.jsonl"
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return FreshnessObservation("runtime_events", False, None, None)
    normalized_now = now.astimezone(UTC)
    age = max(0.0, (normalized_now - modified_at).total_seconds())
    return FreshnessObservation("runtime_events", True, modified_at, age)
