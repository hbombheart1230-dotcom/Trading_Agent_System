"""2026-09-03 daily audit (P1-B) -- Opening Alpha 'submitted' terminology.

`submission_count` (rendered as "submitted N") has always measured probe
RESERVATION claims (graphs/nodes/monitor_node.py::record_probe_submission,
called at Monitor decision time, well before Commander approval or
execute_from_packet ever runs) -- not actual broker HTTP submissions. This
test proves the additive fix: new fields/line surface the real broker
outcome by cross-referencing each reservation's own executor.json, while
the original field and rendered line are byte-for-byte unchanged."""
from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.controlled_validation_daily import (
    build_controlled_validation_daily,
    render_controlled_validation_daily_lines,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_submission_count_unchanged_new_fields_reflect_actual_broker_outcome(tmp_path):
    day = "2026-01-01"
    reports_root = tmp_path / "reports"
    opening_root = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / day

    _write_json(
        opening_root / "probe_evaluations.json",
        {"evaluations": [{"run_id": "run-a", "eligible": True, "applied": True, "reason": "opening_rank1_controlled_probe_applied"}]},
    )
    _write_json(
        opening_root / "probe_submissions.json",
        {"submissions": [{"run_id": "run-a", "symbol": "004310"}]},
    )
    _write_json(
        reports_root / "canonical" / day / "run-a" / "executor.json",
        {"broker_outcome": "NOT_SENT", "submission_attempts": 0},
    )

    payload = build_controlled_validation_daily(reports_root=reports_root, day=day)
    opening = payload["opening_alpha"]

    # Backward compatibility: unchanged field, unchanged value.
    assert opening["submission_count"] == 1

    # New, additive fields reflect the real (NOT_SENT) broker outcome.
    assert opening["submission_candidate_count"] == 1
    assert opening["broker_submission_attempted_count"] == 0
    assert opening["broker_outcome_counts"] == {"NOT_SENT": 1}

    lines = render_controlled_validation_daily_lines(payload)
    assert any(line.startswith("- Opening Alpha: ") and "submitted 1" in line for line in lines)
    assert any("broker_submission_attempted 0" in line and "NOT_SENT=1" in line for line in lines)


def test_actual_broker_dispatch_is_reflected_as_attempted(tmp_path):
    day = "2026-01-02"
    reports_root = tmp_path / "reports"
    opening_root = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / day

    _write_json(opening_root / "probe_evaluations.json", {"evaluations": []})
    _write_json(
        opening_root / "probe_submissions.json",
        {"submissions": [{"run_id": "run-b", "symbol": "005930"}]},
    )
    _write_json(
        reports_root / "canonical" / day / "run-b" / "executor.json",
        {"broker_outcome": "ACCEPTED", "submission_attempts": 1},
    )

    payload = build_controlled_validation_daily(reports_root=reports_root, day=day)
    opening = payload["opening_alpha"]

    assert opening["submission_count"] == 1
    assert opening["broker_submission_attempted_count"] == 1
    assert opening["broker_outcome_counts"] == {"ACCEPTED": 1}


def test_lane_attempt_status_counts_separate_not_sent_from_broker_rejected(tmp_path):
    """2026-09-05 Codex audit T7: a lane's attempt-status breakdown must
    keep PRE_SUBMISSION_BLOCKED (Step5B NOT_SENT -- zero broker calls, e.g.
    order_notional_price_missing) in its own bucket, never folded into
    BROKER_REJECTED (an actual broker-side rejection)."""
    day = "2026-01-04"
    reports_root = tmp_path / "reports"
    controlled_root = tmp_path / "data" / "logs" / "controlled_mock_lanes" / day

    _write_json(
        controlled_root / "lane_attempts.json",
        {
            "attempts": [
                {"lane_id": "Q10_INDEX", "status": "PRE_SUBMISSION_BLOCKED", "execution": {"broker_outcome": "NOT_SENT"}},
                {"lane_id": "Q10_INDEX", "status": "PRE_SUBMISSION_BLOCKED", "execution": {"broker_outcome": "NOT_SENT"}},
                {"lane_id": "Q10_INDEX", "status": "BROKER_REJECTED", "execution": {"broker_outcome": "REJECTED"}},
            ]
        },
    )

    payload = build_controlled_validation_daily(reports_root=reports_root, day=day)
    q10_index = next(row for row in payload["lanes"] if row["lane_id"] == "Q10_INDEX")

    assert q10_index["attempt_count"] == 3
    assert q10_index["attempt_status_counts"] == {
        "PRE_SUBMISSION_BLOCKED": 2,
        "BROKER_REJECTED": 1,
    }
    # The rejected bucket alone must never include the NOT_SENT attempts.
    assert q10_index["attempt_status_counts"]["BROKER_REJECTED"] == 1


def test_missing_executor_artifact_is_handled_gracefully(tmp_path):
    day = "2026-01-03"
    reports_root = tmp_path / "reports"
    opening_root = tmp_path / "data" / "logs" / "opening_rank1_controlled_probe" / day

    _write_json(opening_root / "probe_evaluations.json", {"evaluations": []})
    _write_json(
        opening_root / "probe_submissions.json",
        {"submissions": [{"run_id": "run-missing", "symbol": "000660"}]},
    )
    # No executor.json written for run-missing.

    payload = build_controlled_validation_daily(reports_root=reports_root, day=day)
    opening = payload["opening_alpha"]

    assert opening["submission_count"] == 1
    assert opening["broker_submission_attempted_count"] == 0
    assert opening["broker_outcome_counts"] == {"UNKNOWN_ARTIFACT": 1}
