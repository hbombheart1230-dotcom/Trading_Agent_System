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
