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


def _executor_broker_outcome(reports_root: Path, day: str, run_id: str) -> dict[str, Any]:
    """2026-09-03 daily audit (P1-B): read the actual executor artifact for
    one run_id, to distinguish "the probe reservation was claimed" (what
    `submission_count` below has always measured -- it is written by
    graphs/nodes/monitor_node.py::record_probe_submission at Monitor
    decision time, before Commander approval or execute_from_packet ever
    run) from "a broker HTTP submission was actually attempted" (only
    knowable from executor.json's own submission_attempts/broker_outcome,
    written later by graphs/nodes/execute_from_packet.py). Read-only,
    best-effort: a missing/unreadable artifact yields an empty outcome
    rather than raising."""
    if not run_id:
        return {"broker_outcome": "", "submission_attempts": 0}
    path = Path(reports_root) / "canonical" / day / run_id / "executor.json"
    payload = _read(path)
    try:
        submission_attempts = int(payload.get("submission_attempts") or 0)
    except (TypeError, ValueError):
        submission_attempts = 0
    return {
        "broker_outcome": str(payload.get("broker_outcome") or ""),
        "submission_attempts": submission_attempts,
    }


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

    # P1-B (additive, read-only): cross-reference each probe-reservation
    # row against its own executor.json for the ACTUAL broker outcome.
    # `submission_count` below is left completely unchanged for backward
    # compatibility -- these are new, separately-named fields only.
    broker_submission_attempted_count = 0
    broker_outcome_counts: dict[str, int] = {}
    for row in opening_submissions:
        outcome = _executor_broker_outcome(reports_root, day, str(row.get("run_id") or ""))
        if outcome["submission_attempts"] > 0:
            broker_submission_attempted_count += 1
        label = outcome["broker_outcome"] or "UNKNOWN_ARTIFACT"
        broker_outcome_counts[label] = broker_outcome_counts.get(label, 0) + 1

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
            # P1-B (2026-09-03 daily audit): `submission_count` above has
            # always meant "probe reservation claimed" (Monitor-decision-time
            # commit point), not "broker HTTP submission attempted". These
            # two fields make that distinction explicit without touching the
            # existing field's name or meaning.
            "submission_candidate_count": len(opening_submissions),
            "broker_submission_attempted_count": broker_submission_attempted_count,
            "broker_outcome_counts": broker_outcome_counts,
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
    if "broker_submission_attempted_count" in opening:
        # P1-B (2026-09-03 daily audit, additive): clarifies that
        # "submitted" above counts probe-reservation claims (Monitor
        # decision time), not actual broker HTTP submissions.
        broker_outcomes = ", ".join(
            f"{key}={value}" for key, value in dict(opening.get("broker_outcome_counts") or {}).items()
        )
        lines.append(
            "- Opening Alpha submissions (detail): "
            f"probe_reservation_claimed {int(opening.get('submission_candidate_count') or 0)}"
            f" / broker_submission_attempted {int(opening.get('broker_submission_attempted_count') or 0)}"
            f" / broker_outcomes {broker_outcomes or '-'}"
        )
    return lines


__all__ = [
    "build_controlled_validation_daily",
    "render_controlled_validation_daily_lines",
]
