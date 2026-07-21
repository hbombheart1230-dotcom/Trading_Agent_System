from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


TRACKED_ROOT_CAUSES = (
    "Scanner Ranking Failure",
    "Candidate Filtering",
    "Strategist Override",
    "Exit Horizon",
    "Missing Evidence",
)

ACTIONABLE_ROOT_CAUSES = (
    "Scanner Ranking Failure",
    "Candidate Filtering",
    "Strategist Override",
    "Exit Horizon",
)

REQUIRED_VALIDATION_DAYS = 5
MISSING_EVIDENCE_MAX_RATIO = 0.20
MISSING_EVIDENCE_MAX_DAILY_RATIO = 0.40


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in (value or []) if isinstance(row, Mapping)]


def _date_range(start: str, end: str) -> list[str]:
    cursor = date.fromisoformat(start)
    final = date.fromisoformat(end)
    if cursor > final:
        raise ValueError("start must be before or equal to end")
    rows: list[str] = []
    while cursor <= final:
        rows.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return rows


def _cause_trade_count(q14: Mapping[str, Any], cause: str) -> int:
    for row in _rows(q14.get("cause_summary")):
        if str(row.get("root_cause") or "") == cause:
            return int(row.get("trade_count") or 0)
    return 0


def _exit_horizon_count(horizon: Mapping[str, Any]) -> int:
    count = 0
    for row in _rows(horizon.get("rows")):
        if (
            row.get("horizon_violation_candidate")
            or row.get("exited_before_min_hold")
            or row.get("exited_before_target_hold")
            or row.get("target_hold_would_improve_exit")
        ):
            count += 1
    return count


def _q13_score(q13: Mapping[str, Any], key: str) -> int | None:
    item = _mapping(_mapping(q13.get("scores")).get(key))
    if str(item.get("status") or "") == "INSUFFICIENT_EVIDENCE":
        return None
    value = item.get("score")
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _daily_row(reports_root: Path, day: str) -> dict[str, Any]:
    daily = reports_root / "evaluation" / "daily" / day
    q13_path = daily / "attribution_score_v0.json"
    q14_path = daily / "scanner_alignment_root_cause_report.json"
    horizon_path = daily / "horizon_compliance_report.json"
    q13 = _read_json(q13_path)
    q14 = _read_json(q14_path)
    horizon = _read_json(horizon_path)
    q14_trade_count = int(q14.get("trade_count") or 0)
    missing_count = _cause_trade_count(q14, "Missing Evidence")
    missing_ratio = round(missing_count / q14_trade_count, 4) if q14_trade_count else 0.0
    root_counts = {
        "Scanner Ranking Failure": _cause_trade_count(q14, "Scanner Ranking Failure"),
        "Candidate Filtering": _cause_trade_count(q14, "Candidate Filtering"),
        "Strategist Override": _cause_trade_count(q14, "Strategist Override"),
        "Exit Horizon": _exit_horizon_count(horizon),
        "Missing Evidence": missing_count,
    }
    largest_behavior = str(_mapping(q14.get("largest_behavior_root_cause")).get("root_cause") or "")
    if root_counts["Exit Horizon"] > max(root_counts.get(cause, 0) for cause in ACTIONABLE_ROOT_CAUSES):
        largest_behavior = "Exit Horizon"
    return {
        "day": day,
        "q13_available": bool(q13),
        "q14_available": bool(q14),
        "horizon_available": bool(horizon),
        "report_complete": bool(q13 and q14 and horizon),
        "trade_count": q14_trade_count,
        "q13_scores": {
            "selection_integrity_score": _q13_score(q13, "selection_integrity_score"),
            "scanner_alignment_score": _q13_score(q13, "scanner_alignment_score"),
            "entry_timing_score": _q13_score(q13, "entry_timing_score"),
            "exit_horizon_score": _q13_score(q13, "exit_horizon_score"),
            "evidence_quality_score": _q13_score(q13, "evidence_quality_score"),
        },
        "root_cause_counts": root_counts,
        "largest_behavior_root_cause": largest_behavior,
        "missing_evidence_ratio": missing_ratio,
    }


def _validation_days_from_range(reports_root: Path, start: str, end: str) -> list[str]:
    days: list[str] = []
    for day in _date_range(start, end):
        daily = reports_root / "evaluation" / "daily" / day
        if daily.exists():
            days.append(day)
    return days


def build_q13_q14_validation_report(
    *,
    reports_root: Path = Path("reports"),
    days: Sequence[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    if days is None:
        if not start or not end:
            raise ValueError("Either days or start/end must be provided")
        days = _validation_days_from_range(reports_root, start, end)
    selected_days = [str(day) for day in days]
    daily_rows = [_daily_row(reports_root, day) for day in selected_days]
    completed_rows = [row for row in daily_rows if row.get("report_complete")]
    total_trade_count = sum(int(row.get("trade_count") or 0) for row in daily_rows)
    root_totals: Counter[str] = Counter()
    largest_counts: Counter[str] = Counter()
    missing_total = 0
    daily_missing_ratio_failures = 0
    for row in daily_rows:
        for cause, count in _mapping(row.get("root_cause_counts")).items():
            root_totals[str(cause)] += int(count or 0)
        largest = str(row.get("largest_behavior_root_cause") or "")
        if largest:
            largest_counts[largest] += 1
        missing_total += int(_mapping(row.get("root_cause_counts")).get("Missing Evidence") or 0)
        if float(row.get("missing_evidence_ratio") or 0.0) > MISSING_EVIDENCE_MAX_DAILY_RATIO:
            daily_missing_ratio_failures += 1

    missing_ratio = round(missing_total / total_trade_count, 4) if total_trade_count else 0.0
    scanner_failure_days = largest_counts.get("Scanner Ranking Failure", 0)
    report_ok = len(completed_rows) == len(daily_rows) and len(daily_rows) >= REQUIRED_VALIDATION_DAYS
    enough_days = len(daily_rows) >= REQUIRED_VALIDATION_DAYS
    missing_ok = (
        missing_ratio <= MISSING_EVIDENCE_MAX_RATIO
        and daily_missing_ratio_failures == 0
    )
    stable_ok = scanner_failure_days >= 4
    if not enough_days:
        decision = "IN_PROGRESS"
        decision_reasons = [f"needs_{REQUIRED_VALIDATION_DAYS}_trading_days"]
    elif report_ok and missing_ok and stable_ok:
        decision = "GO"
        decision_reasons = ["scanner_ranking_failure_stable", "missing_evidence_within_threshold", "reports_complete"]
    else:
        decision = "NO_GO"
        decision_reasons = []
        if not report_ok:
            decision_reasons.append("q13_q14_reports_incomplete")
        if not missing_ok:
            decision_reasons.append("missing_evidence_above_threshold")
        if not stable_ok:
            decision_reasons.append("scanner_ranking_failure_not_stable_4_of_5")

    return {
        "schema_version": "q13_q14_validation.v1",
        "evaluation_program_id": "Q13_Q14_VALIDATION_RUN",
        "behavior_effect": "observation_only",
        "days": selected_days,
        "required_validation_days": REQUIRED_VALIDATION_DAYS,
        "day_count": len(daily_rows),
        "completed_report_day_count": len(completed_rows),
        "total_trade_count": total_trade_count,
        "root_cause_totals": {cause: int(root_totals.get(cause, 0)) for cause in TRACKED_ROOT_CAUSES},
        "largest_behavior_root_cause_day_counts": dict(largest_counts),
        "missing_evidence_ratio": missing_ratio,
        "missing_evidence_thresholds": {
            "max_total_ratio": MISSING_EVIDENCE_MAX_RATIO,
            "max_daily_ratio": MISSING_EVIDENCE_MAX_DAILY_RATIO,
        },
        "decision": decision,
        "decision_reasons": decision_reasons,
        "daily_rows": daily_rows,
        "validation_rules": [
            "Q13/Q14 axes and score formulas are frozen.",
            "Only instrumentation and artifact bugs may be fixed during validation.",
            "GO requires Scanner Ranking Failure to be the largest behavior root cause on at least 4 of 5 trading days.",
            "GO requires Missing Evidence to remain within the configured thresholds.",
            "GO requires Q13/Q14 reports to be generated without schema/report errors.",
        ],
    }


def render_q13_q14_validation_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Q13/Q14 Validation Run",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Decision: `{payload.get('decision', '')}`",
        f"- Days: {payload.get('day_count', 0)} / {payload.get('required_validation_days', 0)}",
        f"- Completed report days: {payload.get('completed_report_day_count', 0)}",
        f"- Total trades: {payload.get('total_trade_count', 0)}",
        f"- Missing Evidence ratio: {float(payload.get('missing_evidence_ratio') or 0):.1%}",
        f"- Decision reasons: {', '.join(str(row) for row in payload.get('decision_reasons') or []) or '-'}",
        "",
        "## Root Cause Totals",
        "",
        "| Root Cause | Total |",
        "| --- | ---: |",
    ]
    totals = _mapping(payload.get("root_cause_totals"))
    for cause in TRACKED_ROOT_CAUSES:
        lines.append(f"| {cause} | {int(totals.get(cause) or 0)} |")
    lines.extend(
        [
            "",
            "## Daily Root Cause Table",
            "",
            "| Root Cause | "
            + " | ".join(str(day) for day in payload.get("days") or [])
            + " | Total |",
            "| --- | "
            + " | ".join("---:" for _ in payload.get("days") or [])
            + " | ---: |",
        ]
    )
    daily_rows = [row for row in payload.get("daily_rows") or [] if isinstance(row, Mapping)]
    for cause in TRACKED_ROOT_CAUSES:
        values = [int(_mapping(row.get("root_cause_counts")).get(cause) or 0) for row in daily_rows]
        lines.append(
            f"| {cause} | "
            + " | ".join(str(value) for value in values)
            + f" | {sum(values)} |"
        )
    lines.extend(
        [
            "",
            "## Q13 Scores",
            "",
            "| Day | Complete | Selection | Scanner | Entry | Exit | Evidence | Largest Behavior Root Cause | Missing Evidence |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for row in daily_rows:
        scores = _mapping(row.get("q13_scores"))
        lines.append(
            f"| {row.get('day')} | {row.get('report_complete')} | "
            f"{scores.get('selection_integrity_score')} | "
            f"{scores.get('scanner_alignment_score')} | "
            f"{scores.get('entry_timing_score')} | "
            f"{scores.get('exit_horizon_score')} | "
            f"{scores.get('evidence_quality_score')} | "
            f"{row.get('largest_behavior_root_cause') or '-'} | "
            f"{float(row.get('missing_evidence_ratio') or 0):.1%} |"
        )
    lines.extend(["", "## Validation Rules", ""])
    for rule in payload.get("validation_rules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_q13_q14_validation_report(
    *,
    reports_root: Path = Path("reports"),
    validation_id: str,
    days: Sequence[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, str]:
    reports_root = Path(reports_root)
    payload = build_q13_q14_validation_report(
        reports_root=reports_root,
        days=days,
        start=start,
        end=end,
    )
    out_dir = reports_root / "evaluation" / "validation" / validation_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "q13_q14_validation_report.json"
    md_path = out_dir / "q13_q14_validation_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_q13_q14_validation_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "build_q13_q14_validation_report",
    "render_q13_q14_validation_report",
    "write_q13_q14_validation_report",
]
