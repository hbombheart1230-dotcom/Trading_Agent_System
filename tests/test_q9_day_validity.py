from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from libs.reporting.evaluation.day_validity import build_q9_day_validity


KST = ZoneInfo("Asia/Seoul")


def test_no_trade_day_can_be_valid_q9_day() -> None:
    payload = build_q9_day_validity(
        day="2026-06-24",
        now=datetime(2026, 6, 24, 16, 0, tzinfo=KST),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "scanner_selection_window_count": 100,
                    "complete_pabc_window_count": 99,
                    "full_session_coverage": True,
                    "synthetic_window_count": 0,
                    "missing_selected_candidate_count": 0,
                    "pre_strategist_forward_candidate_count": 200,
                    "forward_observed_candidate_count": 190,
                    "forward_pending_candidate_count": 10,
                    "forward_invalid_candidate_count": 0,
                }
            }
        },
    )

    assert payload["status"] == "VALID"
    assert payload["counts_as_formal_day"] is True
    assert payload["trade_required"] is False


def test_small_invalid_measurement_is_excluded_without_losing_day() -> None:
    payload = build_q9_day_validity(
        day="2026-06-24",
        now=datetime(2026, 6, 24, 16, 0, tzinfo=KST),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "scanner_selection_window_count": 100,
                    "complete_pabc_window_count": 98,
                    "full_session_coverage": True,
                    "synthetic_window_count": 1,
                    "missing_selected_candidate_count": 0,
                    "pre_strategist_forward_candidate_count": 200,
                    "forward_observed_candidate_count": 199,
                    "forward_pending_candidate_count": 0,
                    "forward_invalid_candidate_count": 1,
                }
            }
        },
    )

    assert payload["status"] == "VALID"
    assert payload["blockers"] == []
    assert {row["code"] for row in payload["warnings"]} == {
        "synthetic_windows_excluded",
        "invalid_forward_observation",
    }


def test_low_forward_coverage_invalidates_only_that_day() -> None:
    payload = build_q9_day_validity(
        day="2026-06-24",
        now=datetime(2026, 6, 24, 16, 0, tzinfo=KST),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "scanner_selection_window_count": 100,
                    "complete_pabc_window_count": 98,
                    "full_session_coverage": True,
                    "synthetic_window_count": 0,
                    "missing_selected_candidate_count": 0,
                    "pre_strategist_forward_candidate_count": 200,
                    "forward_observed_candidate_count": 180,
                    "forward_pending_candidate_count": 0,
                    "forward_invalid_candidate_count": 20,
                }
            }
        },
    )

    assert payload["status"] == "INVALID"
    assert {row["code"] for row in payload["blockers"]} == {
        "invalid_forward_observation",
    }


def test_current_session_is_not_invalidated_before_close() -> None:
    payload = build_q9_day_validity(
        day="2026-06-24",
        now=datetime(2026, 6, 24, 12, 0, tzinfo=KST),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "scanner_selection_window_count": 5,
                    "complete_pabc_window_count": 5,
                    "full_session_coverage": False,
                    "pre_strategist_forward_candidate_count": 5,
                    "forward_pending_candidate_count": 5,
                }
            }
        },
    )

    assert payload["status"] == "IN_PROGRESS"
    assert payload["blockers"] == []
