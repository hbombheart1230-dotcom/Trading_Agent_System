from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.q9_artifact_repair import repair_q9_day_artifacts


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_repair_q9_day_artifacts_normalizes_windows_and_backfills_c(tmp_path) -> None:
    reports = tmp_path / "reports"
    _write(
        reports / "operator_summary" / "daily" / "2026-06-23" / "q9_decision_windows.json",
        {
            "windows": [{
                "decision_id": "D1",
                "generated_at": "1782173100",
                "scanner_control": {"top10": [{"symbol": "000660"}]},
                "strategist_selection": {"selected_symbol": "005930"},
                "commander_final": {
                    "candidate_symbol": "005930",
                    "decision": "reject",
                    "no_trade": True,
                },
            }]
        },
    )
    shadow = tmp_path / "data" / "logs" / "quant_shadow_candidates" / "2026-06-23" / "one.json"
    _write(
        shadow,
        {
            "q9_decision_id": "D1",
            "q9_decision_candidates": [{
                "symbol": "005930",
                "q9_decision_role": "B_STRATEGIST_RANKED",
            }],
            "candidates": [{"symbol": "005930"}],
        },
    )

    result = repair_q9_day_artifacts(reports_root=reports, day="2026-06-23")
    decision = json.loads(
        (
            reports
            / "operator_summary"
            / "daily"
            / "2026-06-23"
            / "q9_decision_windows.json"
        ).read_text(encoding="utf-8")
    )
    repaired = json.loads(shadow.read_text(encoding="utf-8"))

    assert result["normalized_window_count"] == 1
    assert decision["windows"][0]["window_type"] == "scanner_selection"
    assert decision["windows"][0]["decision_epoch"] == 1782173100
    assert repaired["q9_sync_status"]["status"] == "complete"
    assert repaired["q9_decision_candidates"][-1]["q9_decision_role"] == "C_COMMANDER_FINAL"


def test_repair_reconstructs_missing_decision_window_from_shadow(tmp_path) -> None:
    reports = tmp_path / "reports"
    shadow = (
        tmp_path
        / "data"
        / "logs"
        / "quant_shadow_candidates"
        / "2026-06-25"
        / "window.json"
    )
    _write(
        shadow,
        {
            "q9_decision_id": "Q9_20260625_run-1",
            "run_id": "run-1",
            "generated_at": "2026-06-25T00:05:00+00:00",
            "q9_decision_candidates": [
                {
                    "symbol": "005930",
                    "rank": 1,
                    "score_total": 1.1,
                    "q9_decision_role": role,
                    "q9_selected": role == "B_STRATEGIST_RANKED",
                    "q9_commander_decision": (
                        "approve" if role == "C_COMMANDER_FINAL" else ""
                    ),
                }
                for role in (
                    "P_SCANNER_PRE_STRATEGIST_UNIVERSE",
                    "A_SCANNER_CONTROL",
                    "B_STRATEGIST_RANKED",
                    "C_COMMANDER_FINAL",
                )
            ],
        },
    )

    result = repair_q9_day_artifacts(reports_root=reports, day="2026-06-25")
    payload = json.loads(
        (
            reports
            / "operator_summary"
            / "daily"
            / "2026-06-25"
            / "q9_decision_windows.json"
        ).read_text(encoding="utf-8")
    )

    assert result["recovered_window_count"] == 1
    assert payload["window_count"] == 1
    window = payload["windows"][0]
    assert window["scanner_control"]["top1_symbol"] == "005930"
    assert window["strategist_selection"]["selected_symbol"] == "005930"
    assert window["commander_final"]["decision"] == "approve"


def test_repair_enriches_candidate_price_from_canonical_scanner(tmp_path) -> None:
    reports = tmp_path / "reports"
    day = "2026-07-24"
    _write(
        reports / "operator_summary" / "daily" / day / "q9_decision_windows.json",
        {
            "windows": [{
                "decision_id": "D1",
                "run_id": "run-1",
                "generated_at": "2026-07-24T00:05:00+00:00",
                "scanner_control": {
                    "top20": [{"symbol": "005930", "rank": 1}],
                },
            }]
        },
    )
    _write(
        reports / "canonical" / day / "run-1" / "scanner.json",
        {
            "ranking_table": [{"symbol": "005930", "rank": 1}],
            "selected_candidate": {
                "symbol": "005930",
                "feature_snapshot": {
                    "skill_quote_price": 70100,
                    "engine_close_last": 70000,
                    "quote_payload_available": True,
                    "quote_source": "skill_quote",
                    "quote_evidence_status": "OBSERVED",
                },
            },
        },
    )

    result = repair_q9_day_artifacts(reports_root=reports, day=day)
    payload = json.loads(
        (
            reports
            / "operator_summary"
            / "daily"
            / day
            / "q9_decision_windows.json"
        ).read_text(encoding="utf-8")
    )

    assert result["canonical_enriched_window_count"] == 1
    candidate = payload["windows"][0]["scanner_control"]["top20"][0]
    assert candidate["compact_feature_snapshot"]["skill_quote_price"] == 70100
    assert candidate["compact_feature_snapshot"]["quote_payload_available"] is True
    assert candidate["compact_feature_snapshot"]["quote_source"] == "skill_quote"
    assert candidate["compact_feature_snapshot"]["quote_evidence_status"] == "OBSERVED"


def test_repair_backfills_monitor_noop_reason_from_shadow_top_pick(tmp_path) -> None:
    reports = tmp_path / "reports"
    day = "2026-07-28"
    _write(
        reports / "operator_summary" / "daily" / day / "q9_decision_windows.json",
        {
            "windows": [{
                "decision_id": "D1",
                "generated_at": "2026-07-28T00:05:00+00:00",
                "commander_final": {
                    "decision": "approve",
                    "candidate_symbol": "005930",
                    "monitor_intent": "NOOP",
                },
            }]
        },
    )
    shadow = (
        tmp_path
        / "data"
        / "logs"
        / "quant_shadow_candidates"
        / day
        / "sample.json"
    )
    _write(
        shadow,
        {
            "q9_decision_id": "D1",
            "generated_at": "2026-07-28T00:05:00+00:00",
            "q9_decision_candidates": [{
                "symbol": "005930",
                "q9_decision_role": "C_COMMANDER_FINAL",
                "q9_commander_decision": "approve",
            }],
            "candidates": [{
                "symbol": "005930",
                "shadow_role": "top_pick",
                "triggered": True,
                "guard_blocked": True,
                "guard_reason": "quant_entry_block:cost_edge_fail",
                "entry_quant_cost_floor_state": "not_met",
            }],
        },
    )

    repair_q9_day_artifacts(reports_root=reports, day=day)

    payload = json.loads(
        (
            reports
            / "operator_summary"
            / "daily"
            / day
            / "q9_decision_windows.json"
        ).read_text(encoding="utf-8")
    )
    commander = payload["windows"][0]["commander_final"]
    assert commander["monitor_reason"] == "quant_entry_block:cost_edge_fail"
    assert commander["monitor_observation"]["recovery_source"] == (
        "quant_shadow_candidates.top_pick"
    )
