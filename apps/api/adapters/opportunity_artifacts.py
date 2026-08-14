from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..infrastructure.bounded_reader import BoundedReadError, read_json_bounded


@dataclass(frozen=True, slots=True)
class OpportunitySources:
    day: date
    signals: dict[str, Any] | None
    blockers: dict[str, Any] | None
    opening_outcomes: dict[str, Any] | None
    issues: tuple[str, ...]


def load_opportunity_sources(
    reports_root: Path,
    day: date,
    *,
    max_bytes: int,
) -> OpportunitySources:
    day_text = day.isoformat()
    paths = {
        "signals": reports_root
        / "evaluation"
        / "opportunity_engine_shadow"
        / day_text
        / "opportunity_engine_signals.json",
        "blockers": reports_root
        / "operator_summary"
        / "daily"
        / day_text
        / "q8_shadow_blocker_review.json",
        "opening_outcomes": reports_root
        / "evaluation"
        / "opening_rank1_shadow"
        / day_text
        / "opening_rank1_shadow_daily.json",
    }
    loaded: dict[str, dict[str, Any] | None] = {}
    issues: list[str] = []
    for name, path in paths.items():
        if not path.is_file():
            loaded[name] = None
            issues.append(f"MISSING_SOURCE:{name}")
            continue
        try:
            payload = read_json_bounded(path, max_bytes=max_bytes)
        except (OSError, BoundedReadError):
            loaded[name] = None
            issues.append(f"INVALID_SOURCE:{name}")
            continue
        if not isinstance(payload, dict):
            loaded[name] = None
            issues.append(f"SCHEMA_MISMATCH:{name}")
            continue
        loaded[name] = payload
    return OpportunitySources(
        day=day,
        signals=loaded["signals"],
        blockers=loaded["blockers"],
        opening_outcomes=loaded["opening_outcomes"],
        issues=tuple(issues),
    )
