from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import LIVE_RESEARCH_COST_PCT
from .loaders import find_horizon, load_json, mapping
from .sensitivity import performance_metrics


INTEGRITY_BOUNDARY_DAY = "2026-08-21"
TARGET_HORIZON = "+180m"
MINIMUM_INDEPENDENT_DAYS = 5


def collect_large_cap_daily_rows(
    *, reports_root: Path, through_day: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = reports_root / "evaluation" / "baseline_samsung_hynix"
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for path in sorted(root.glob("20??-??-??/baseline_samsung_hynix_forward_returns.json")):
        day = path.parent.name
        if day < INTEGRITY_BOUNDARY_DAY or day > through_day:
            continue
        payload, source = load_json(path)
        sources.append(source)
        if source.get("error"):
            continue
        horizon = find_horizon(mapping(payload.get("summary")).get("horizons"), TARGET_HORIZON)
        gross = mapping(horizon.get("top1_gross"))
        average = gross.get("average_return_pct")
        count = int(gross.get("count") or 0)
        if average is None or count <= 0:
            continue
        rows.append(
            {
                "day": day,
                "symbol": "SAMSUNG_HYNIX_FIXED_UNIVERSE",
                "decision_epoch": day,
                "gross_return_pct": round(float(average), 4),
                "net_return_pct": round(float(average) - LIVE_RESEARCH_COST_PCT, 4),
                "window_count": count,
                "source_path": str(path),
            }
        )
    return rows, sources


def build_large_cap_daily_review(
    *, reports_root: Path, through_day: str
) -> dict[str, Any]:
    rows, sources = collect_large_cap_daily_rows(
        reports_root=reports_root, through_day=through_day
    )
    metrics = performance_metrics(rows)
    metrics["window_count"] = sum(int(row["window_count"]) for row in rows)
    invalid = [source for source in sources if source.get("error")]
    sample_count = int(metrics.get("sample_count") or 0)
    if invalid:
        decision = "RUNTIME_DATA_INTEGRITY_ERROR"
        rationale = "One or more corrected daily baseline artifacts are invalid."
    elif sample_count < MINIMUM_INDEPENDENT_DAYS:
        decision = "RUNTIME_DATA_REQUIRED"
        rationale = (
            f"Corrected day-level sample is {sample_count}; "
            f"{MINIMUM_INDEPENDENT_DAYS} independent days are required."
        )
    else:
        decision = "READY_FOR_OFFLINE_REVIEW"
        rationale = "The corrected day-level minimum sample is available for review."
    return {
        "schema_version": "large_cap_daily_review.v1",
        "evaluation_unit": "one_top1_average_per_trading_day",
        "integrity_boundary_day": INTEGRITY_BOUNDARY_DAY,
        "through_day": through_day,
        "target_horizon": TARGET_HORIZON,
        "cost_pct": LIVE_RESEARCH_COST_PCT,
        "minimum_independent_days": MINIMUM_INDEPENDENT_DAYS,
        "base": metrics,
        "days": rows,
        "source_count": len(sources),
        "invalid_sources": invalid,
        "decision": decision,
        "rationale": rationale,
    }
