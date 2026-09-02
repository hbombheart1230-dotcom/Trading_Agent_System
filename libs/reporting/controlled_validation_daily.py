from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LANE_LABELS = {
    "BTC_WOORI": "Q12 BTC-Woori",
    "Q10_SEMICONDUCTOR": "Q10 Semiconductor",
    "Q10_INDEX": "Q10 Index",
}


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _rows(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    return [dict(row) for row in list(payload.get(key) or []) if isinstance(row, Mapping)]


def build_controlled_validation_daily(
    *, reports_root: Path, day: str
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    workspace_root = reports_root.parent if reports_root.name.lower() == "reports" else reports_root
    controlled_root = workspace_root / "data" / "logs" / "controlled_mock_lanes" / day
    opening_root = workspace_root / "data" / "logs" / "opening_rank1_controlled_probe" / day
    evaluations = _rows(_read(controlled_root / "lane_evaluations.json"), "evaluations")
    attempts = _rows(_read(controlled_root / "lane_attempts.json"), "attempts")
    submissions = _rows(_read(controlled_root / "lane_submissions.json"), "submissions")
    opening_evaluations = _rows(_read(opening_root / "probe_evaluations.json"), "evaluations")
    opening_submissions = _rows(_read(opening_root / "probe_submissions.json"), "submissions")

    lane_rows: list[dict[str, Any]] = []
    for lane_id in ("Q10_SEMICONDUCTOR", "Q10_INDEX", "BTC_WOORI"):
        lane_evaluations = [row for row in evaluations if str(row.get("lane_id") or "") == lane_id]
        latest = lane_evaluations[-1] if lane_evaluations else {}
        lane_attempts = [row for row in attempts if str(row.get("lane_id") or "") == lane_id]
        lane_submissions = [row for row in submissions if str(row.get("lane_id") or "") == lane_id]
        lane_rows.append(
            {
                "lane_id": lane_id,
                "label": LANE_LABELS[lane_id],
                "evaluation_status": str(latest.get("status") or "NOT_EVALUATED"),
                "reason": str(latest.get("reason") or ""),
                "observation_count": int(latest.get("observation_count") or 0),
                "attempt_count": len(lane_attempts),
                "submission_count": len(lane_submissions),
                "latest_submission_status": str((lane_submissions[-1] if lane_submissions else {}).get("status") or ""),
            }
        )

    return {
        "schema_version": "controlled_validation_daily.v1",
        "day": day,
        "lanes": lane_rows,
        "opening_alpha": {
            "evaluation_count": len(opening_evaluations),
            "eligible_count": sum(bool(row.get("eligible")) for row in opening_evaluations),
            "applied_count": sum(bool(row.get("applied")) for row in opening_evaluations),
            "submission_count": len(opening_submissions),
            "reason_counts": {
                reason: sum(1 for row in opening_evaluations if str(row.get("reason") or "") == reason)
                for reason in sorted({str(row.get("reason") or "") for row in opening_evaluations if str(row.get("reason") or "")})
            },
        },
    }


def render_controlled_validation_daily_lines(payload: Mapping[str, Any]) -> list[str]:
    lanes = [dict(row) for row in list(payload.get("lanes") or []) if isinstance(row, Mapping)]
    opening = dict(payload.get("opening_alpha") or {})
    lines = ["", "## Controlled Validation Lanes", ""]
    for row in lanes:
        lines.append(
            f"- {row.get('label')}: `{row.get('evaluation_status')}`"
            f" / reason `{row.get('reason') or '-'}`"
            f" / attempts {int(row.get('attempt_count') or 0)}"
            f" / accepted {int(row.get('submission_count') or 0)}"
        )
    reasons = ", ".join(
        f"{key}={value}" for key, value in dict(opening.get("reason_counts") or {}).items()
    )
    lines.append(
        "- Opening Alpha: "
        f"evaluated {int(opening.get('evaluation_count') or 0)}"
        f" / eligible {int(opening.get('eligible_count') or 0)}"
        f" / applied {int(opening.get('applied_count') or 0)}"
        f" / submitted {int(opening.get('submission_count') or 0)}"
        f" / reasons {reasons or '-'}"
    )
    return lines


__all__ = [
    "build_controlled_validation_daily",
    "render_controlled_validation_daily_lines",
]
