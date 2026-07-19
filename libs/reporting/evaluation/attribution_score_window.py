from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


SCORE_KEYS = (
    "selection_integrity_score",
    "scanner_alignment_score",
    "entry_timing_score",
    "exit_horizon_score",
    "evidence_quality_score",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _score_value(row: Mapping[str, Any], key: str) -> int | None:
    item = _mapping(_mapping(row.get("scores")).get(key))
    if item.get("status") == "INSUFFICIENT_EVIDENCE":
        return None
    value = item.get("score")
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _ledger_days(freeze_root: Path) -> list[dict[str, Any]]:
    ledger = _read_json(freeze_root / "daily_ledger.json")
    return [dict(row) for row in ledger.get("days") or [] if isinstance(row, dict)]


def _day_payload(reports_root: Path, day: str) -> dict[str, Any]:
    return _read_json(reports_root / "evaluation" / "daily" / day / "attribution_score_v0.json")


def build_attribution_score_window(
    *,
    reports_root: Path = Path("reports"),
    window_id: str = "q9_q10_q11_q12_5d_20260629",
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    freeze_root = reports_root / "evaluation" / "freeze_window" / window_id
    ledger_rows = _ledger_days(freeze_root)
    day_rows: list[dict[str, Any]] = []
    for ledger in ledger_rows:
        day = str(ledger.get("day") or "")
        payload = _day_payload(reports_root, day)
        if not payload:
            day_rows.append({
                "day": day,
                "counts_as_valid_day": bool(ledger.get("counts_as_valid_day")),
                "available": False,
                "reason": "attribution_score_missing",
                "scores": {},
                "weakest_observed_axis": {},
                "trade_count": 0,
            })
            continue
        day_rows.append({
            "day": day,
            "counts_as_valid_day": bool(ledger.get("counts_as_valid_day")),
            "available": True,
            "reason": "",
            "scores": dict(payload.get("scores") or {}),
            "weakest_observed_axis": dict(payload.get("weakest_observed_axis") or {}),
            "trade_count": _read_json(
                reports_root / "evaluation" / "daily" / day / "daily_scorecard.json"
            ).get("artifact_integrity", {}).get("trade_count", 0),
        })

    valid_rows = [row for row in day_rows if row.get("counts_as_valid_day")]
    axis_summary: dict[str, Any] = {}
    for key in SCORE_KEYS:
        values: list[int] = []
        status_counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()
        for row in valid_rows:
            item = _mapping(_mapping(row.get("scores")).get(key))
            status = str(item.get("status") or "MISSING")
            status_counts[status] += 1
            value = _score_value(row, key)
            if value is not None:
                values.append(value)
            for reason in item.get("reasons") or []:
                reason_counts[str(reason)] += 1
        axis_summary[key] = {
            "valid_day_count": len(valid_rows),
            "scored_day_count": len(values),
            "insufficient_day_count": status_counts.get("INSUFFICIENT_EVIDENCE", 0),
            "average_score": round(sum(values) / len(values), 2) if values else None,
            "min_score": min(values) if values else None,
            "max_score": max(values) if values else None,
            "status_counts": dict(status_counts),
            "top_reasons": [
                {"reason": reason, "count": count}
                for reason, count in reason_counts.most_common(10)
            ],
        }

    weakest_counts: Counter[str] = Counter()
    for row in valid_rows:
        weakest = str(_mapping(row.get("weakest_observed_axis")).get("name") or "")
        if weakest:
            weakest_counts[weakest] += 1

    daily_table = []
    for row in day_rows:
        daily_table.append({
            "day": row.get("day"),
            "valid": bool(row.get("counts_as_valid_day")),
            "available": bool(row.get("available")),
            "trade_count": row.get("trade_count"),
            "weakest_axis": _mapping(row.get("weakest_observed_axis")).get("name") or "",
            **{
                key: _score_value(row, key)
                for key in SCORE_KEYS
            },
        })

    scored_axis_averages = {
        key: item.get("average_score")
        for key, item in axis_summary.items()
        if item.get("average_score") is not None
    }
    weakest_average_axis = (
        min(scored_axis_averages.items(), key=lambda item: float(item[1]))
        if scored_axis_averages
        else ("", None)
    )
    return {
        "schema_version": "attribution_score_window.v1",
        "evaluation_program_id": "Q13_ATTRIBUTION_SCORE_WINDOW",
        "behavior_effect": "observation_only",
        "window_id": window_id,
        "day_count": len(day_rows),
        "valid_day_count": len(valid_rows),
        "available_day_count": sum(1 for row in day_rows if row.get("available")),
        "total_trade_count_valid_days": sum(int(row.get("trade_count") or 0) for row in valid_rows),
        "axis_summary": axis_summary,
        "weakest_axis_distribution": dict(weakest_counts),
        "weakest_axis_by_average_score": {
            "name": weakest_average_axis[0],
            "average_score": weakest_average_axis[1],
        },
        "daily_rows": daily_table,
        "interpretation_rule": (
            "Use valid days for aggregate conclusions. Invalid days are shown for audit "
            "but excluded from average score and weakest-axis distribution."
        ),
    }


def render_attribution_score_window(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Q13 Attribution Score Window - {payload.get('window_id', '')}",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Days: {payload.get('day_count', 0)} total / {payload.get('valid_day_count', 0)} valid",
        f"- Available attribution days: {payload.get('available_day_count', 0)}",
        f"- Valid-day trades: {payload.get('total_trade_count_valid_days', 0)}",
        f"- Weakest by average score: `{_mapping(payload.get('weakest_axis_by_average_score')).get('name') or '-'}` "
        f"({_mapping(payload.get('weakest_axis_by_average_score')).get('average_score')})",
        "",
        "## Axis Summary",
        "",
        "| Axis | Avg Score | Min | Max | Scored Days | Insufficient Days | Top Reasons |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for key, item in _mapping(payload.get("axis_summary")).items():
        obj = _mapping(item)
        reasons = ", ".join(
            f"{row.get('reason')} ({row.get('count')})"
            for row in obj.get("top_reasons") or []
        ) or "-"
        lines.append(
            f"| {key} | {obj.get('average_score')} | {obj.get('min_score')} | "
            f"{obj.get('max_score')} | {obj.get('scored_day_count')} | "
            f"{obj.get('insufficient_day_count')} | {reasons} |"
        )
    lines.extend([
        "",
        "## Weakest Axis Distribution",
        "",
    ])
    distribution = _mapping(payload.get("weakest_axis_distribution"))
    if distribution:
        for key, count in sorted(distribution.items(), key=lambda item: (-int(item[1]), item[0])):
            lines.append(f"- `{key}`: {count}")
    else:
        lines.append("- No valid scored days.")
    lines.extend([
        "",
        "## Daily Rows",
        "",
        "| Day | Valid | Trades | Weakest | Selection | Scanner | Entry | Exit/Horizon | Evidence |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in payload.get("daily_rows") or []:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"| {row.get('day')} | {row.get('valid')} | {row.get('trade_count')} | "
            f"{row.get('weakest_axis') or '-'} | "
            f"{row.get('selection_integrity_score')} | "
            f"{row.get('scanner_alignment_score')} | "
            f"{row.get('entry_timing_score')} | "
            f"{row.get('exit_horizon_score')} | "
            f"{row.get('evidence_quality_score')} |"
        )
    lines.extend([
        "",
        "## Interpretation Rule",
        "",
        f"- {payload.get('interpretation_rule', '')}",
        "",
    ])
    return "\n".join(lines)


def write_attribution_score_window(
    *,
    reports_root: Path = Path("reports"),
    window_id: str = "q9_q10_q11_q12_5d_20260629",
) -> dict[str, str]:
    reports_root = Path(reports_root)
    payload = build_attribution_score_window(reports_root=reports_root, window_id=window_id)
    out_dir = reports_root / "evaluation" / "freeze_window" / window_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "attribution_score_window.json"
    md_path = out_dir / "attribution_score_window.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_attribution_score_window(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "build_attribution_score_window",
    "render_attribution_score_window",
    "write_attribution_score_window",
]
