from __future__ import annotations

from datetime import date, timedelta
from typing import Any


FREEZE_WINDOW_ID = "q9_q10_q11_q12_5d_20260629"
FREEZE_START_DAY = "2026-06-29"
TARGET_VALID_DAYS = 5

PROTECTED_BEHAVIOR = (
    "Q9 Scanner sourcing/filtering/ranking/weighting",
    "Q9 Strategist prompts/schemas/routing/cache/recommendations",
    "Q9 Commander approval/veto/routing/risk controls",
    "Q9 Monitor entry/exit/hold rules",
    "Q9 execution/order behavior",
    "Samsung/Hynix ranking formula",
    "Samsung/Hynix entry conditions and thresholds",
    "Samsung/Hynix exit conditions",
    "Q11 opening opportunity scoring and virtual trade rules",
    "Q12 BTC/Woori scoring and virtual entry rules",
)

ALLOWED_CHANGES = (
    "missing or malformed observability artifacts",
    "report generation defects",
    "forward observation defects",
    "schema, timestamp, linkage, and deterministic aggregation defects",
)


def _planned_weekdays(start: str, count: int) -> list[str]:
    current = date.fromisoformat(start)
    rows: list[str] = []
    while len(rows) < count:
        if current.weekday() < 5:
            rows.append(current.isoformat())
        current += timedelta(days=1)
    return rows


def build_freeze_manifest() -> dict[str, Any]:
    return {
        "schema_version": "q9_baseline_freeze_window.v1",
        "window_id": FREEZE_WINDOW_ID,
        "status": "ACTIVE",
        "start_day": FREEZE_START_DAY,
        "target_valid_trading_days": TARGET_VALID_DAYS,
        "planned_weekdays": _planned_weekdays(FREEZE_START_DAY, TARGET_VALID_DAYS),
        "valid_day_rule": (
            "Count only full regular-session days whose Q9 day-validity and "
            "post-close reporting verification pass. Holidays are skipped."
        ),
        "protected_behavior": list(PROTECTED_BEHAVIOR),
        "allowed_changes": list(ALLOWED_CHANGES),
        "behavior_changes_allowed": False,
        "observability_reporting_fixes_allowed": True,
    }


__all__ = [
    "FREEZE_START_DAY",
    "FREEZE_WINDOW_ID",
    "TARGET_VALID_DAYS",
    "build_freeze_manifest",
]
