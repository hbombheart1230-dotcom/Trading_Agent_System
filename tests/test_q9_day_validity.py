from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from libs.reporting.evaluation.artifact_inventory import build_artifact_inventory
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


def test_unavailable_forward_coverage_is_not_mislabeled_invalid() -> None:
    payload = build_q9_day_validity(
        day="2026-07-22",
        now=datetime(2026, 7, 22, 16, 0, tzinfo=KST),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "scanner_selection_window_count": 100,
                    "complete_pabc_window_count": 100,
                    "full_session_coverage": True,
                    "pre_strategist_forward_candidate_count": 200,
                    "forward_observed_candidate_count": 120,
                    "forward_pending_candidate_count": 20,
                    "forward_unavailable_candidate_count": 60,
                    "forward_invalid_candidate_count": 0,
                }
            }
        },
    )

    assert payload["status"] == "INVALID"
    assert payload["checks"]["forward_invalid_candidate_count"] == 0
    assert payload["checks"]["forward_unavailable_candidate_count"] == 60
    assert {row["code"] for row in payload["blockers"]} == {
        "forward_observation_unavailable",
    }


def test_complete_unified_comparison_keeps_day_valid_despite_raw_forward_gaps() -> None:
    payload = build_q9_day_validity(
        day="2026-06-24",
        now=datetime(2026, 6, 24, 16, 0, tzinfo=KST),
        inventory={
            "daily_artifacts": {
                "q9_decision_windows": {
                    "exists": True,
                    "schema_match": True,
                    "scanner_selection_window_count": 100,
                    "complete_pabc_window_count": 100,
                    "full_session_coverage": True,
                    "synthetic_window_count": 0,
                    "missing_selected_candidate_count": 0,
                    "pre_strategist_forward_candidate_count": 200,
                    "forward_observed_candidate_count": 100,
                    "forward_pending_candidate_count": 20,
                    "forward_invalid_candidate_count": 80,
                },
                "q9_vs_samsung_hynix_comparison": {
                    "exists": True,
                    "schema_version": "q9_baseline_unified_comparison.v1",
                    "evidence_status": "COMPLETE",
                    "forward_windows_complete": True,
                },
            }
        },
    )

    assert payload["status"] == "VALID"
    assert payload["blockers"] == []
    assert payload["checks"]["unified_comparison_complete_override"] is True
    warning = next(row for row in payload["warnings"] if row["code"] == "invalid_forward_observation")
    assert warning["comparison_complete_override"] is True
    assert warning["invalidates_day"] is False


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


def test_runtime_shadow_evidence_confirms_session_after_last_scanner_window(
    tmp_path,
) -> None:
    reports = tmp_path / "reports"
    daily = reports / "operator_summary" / "daily" / "2026-06-25"
    daily.mkdir(parents=True)
    (daily / "q9_decision_windows.json").write_text(
        """
        {
          "schema_version": "q9_decision_windows.v1",
          "windows": [
            {
              "decision_id": "Q9_20260625_open",
              "generated_at": "2026-06-25T00:05:00+00:00",
              "scanner_control": {},
              "scanner_pre_strategist_universe": {},
              "strategist_selection": {},
              "commander_final": {}
            },
            {
              "decision_id": "Q9_20260625_last_scanner",
              "generated_at": "2026-06-25T06:14:00+00:00",
              "scanner_control": {},
              "scanner_pre_strategist_universe": {},
              "strategist_selection": {},
              "commander_final": {}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    shadow = (
        tmp_path
        / "data"
        / "logs"
        / "quant_shadow_candidates"
        / "2026-06-25"
    )
    shadow.mkdir(parents=True)
    (shadow / "close.json").write_text(
        """
        {
          "generated_at": "2026-06-25T06:29:00+00:00",
          "q9_decision_candidates": [
            {"q9_decision_role": "C_COMMANDER_FINAL", "symbol": "005930"}
          ]
        }
        """,
        encoding="utf-8",
    )

    inventory = build_artifact_inventory(reports, "2026-06-25")
    decision = inventory["daily_artifacts"]["q9_decision_windows"]

    assert decision["full_session_coverage"] is True
    assert decision["session_coverage_source"] == "scanner_selection_plus_q9_shadow_runtime"
    assert decision["last_q9_runtime_evidence_kst"].endswith("15:29:00+09:00")


def test_manual_post_close_validation_preserves_late_session_coverage(
    tmp_path,
) -> None:
    reports = tmp_path / "reports"
    daily = reports / "operator_summary" / "daily" / "2026-07-01"
    daily.mkdir(parents=True)
    (daily / "q9_decision_windows.json").write_text(
        """
        {
          "schema_version": "q9_decision_windows.v1",
          "windows": [
            {
              "decision_id": "Q9_20260701_open",
              "generated_at": "2026-07-01T00:00:06+00:00",
              "scanner_control": {},
              "scanner_pre_strategist_universe": {},
              "strategist_selection": {},
              "commander_final": {}
            },
            {
              "decision_id": "Q9_20260701_late",
              "generated_at": "2026-07-01T06:14:49+00:00",
              "scanner_control": {},
              "scanner_pre_strategist_universe": {},
              "strategist_selection": {},
              "commander_final": {}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    (daily / "closeout_maintenance.json").write_text(
        """
        {
          "schema_version": "closeout_maintenance.v1",
          "ok": true,
          "trigger": "q9_compact_validation_20260701",
          "steps": {
            "account_snapshot": {"ok": true},
            "closeout_residual_position_reconciliation": {
              "ok": true,
              "requires_next_open_flatten": false
            }
          }
        }
        """,
        encoding="utf-8",
    )

    inventory = build_artifact_inventory(reports, "2026-07-01")
    decision = inventory["daily_artifacts"]["q9_decision_windows"]

    assert decision["full_session_coverage"] is True
    assert decision["late_session_runtime_evidence"] is True
    assert decision["post_close_account_snapshot_ok"] is True
    assert decision["post_close_trigger"] == "q9_compact_validation_20260701"


def test_inventory_excludes_post_session_and_non_krx_test_windows(
    tmp_path,
) -> None:
    reports = tmp_path / "reports"
    daily = reports / "operator_summary" / "daily" / "2026-07-30"
    daily.mkdir(parents=True)
    (daily / "q9_decision_windows.json").write_text(
        """
        {
          "schema_version": "q9_decision_windows.v1",
          "windows": [
            {
              "decision_id": "Q9_20260730_live",
              "generated_at": "2026-07-30T06:15:00+00:00",
              "scanner_pre_strategist_universe": {
                "intrinsic_ranked_top20": [{"symbol": "005930"}]
              },
              "scanner_control": {"top1_symbol": "005930"},
              "strategist_selection": {"selected_symbol": "005930"},
              "commander_final": {"decision": "approve"}
            },
            {
              "decision_id": "Q9_20260730_after_close",
              "generated_at": "2026-07-30T06:36:00+00:00",
              "scanner_pre_strategist_universe": {
                "intrinsic_ranked_top20": [{"symbol": "005930"}]
              },
              "scanner_control": {"top1_symbol": "005930"},
              "strategist_selection": {"selected_symbol": "005930"}
            },
            {
              "decision_id": "Q9_20260730_unmarked",
              "generated_at": "2026-07-30T06:20:00+00:00",
              "scanner_pre_strategist_universe": {
                "intrinsic_ranked_top20": [{"symbol": "AAA"}]
              },
              "scanner_control": {"top1_symbol": "AAA"},
              "strategist_selection": {"selected_symbol": "AAA"},
              "commander_final": {"decision": "approve"}
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    inventory = build_artifact_inventory(reports, "2026-07-30")
    decision = inventory["daily_artifacts"]["q9_decision_windows"]

    assert decision["scanner_selection_window_count"] == 1
    assert decision["complete_pabc_window_count"] == 1
    assert decision["post_session_window_count"] == 1
    assert decision["synthetic_window_count"] == 1


def test_inventory_does_not_treat_memory_packet_ids_as_symbols(tmp_path) -> None:
    reports = tmp_path / "reports"
    daily = reports / "operator_summary" / "daily" / "2026-08-27"
    daily.mkdir(parents=True)
    (daily / "q9_decision_windows.json").write_text(
        """
        {
          "schema_version": "q9_decision_windows.v1",
          "windows": [
            {
              "decision_id": "Q9_20260827_live",
              "generated_at": "2026-08-27T00:05:00+00:00",
              "scanner_pre_strategist_universe": {
                "intrinsic_ranked_top20": [{"symbol": "005930"}]
              },
              "scanner_control": {"top1_symbol": "005930"},
              "strategist_selection": {"selected_symbol": "005930"},
              "strategist_provenance": {
                "memory": {
                  "layer_packet_ids": {
                    "symbol": "memory_95807bfb862d7452b0ea"
                  }
                }
              },
              "commander_final": {"decision": "approve"}
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    inventory = build_artifact_inventory(reports, "2026-08-27")
    decision = inventory["daily_artifacts"]["q9_decision_windows"]

    assert decision["scanner_selection_window_count"] == 1
    assert decision["complete_pabc_window_count"] == 1
    assert decision["synthetic_window_count"] == 0
