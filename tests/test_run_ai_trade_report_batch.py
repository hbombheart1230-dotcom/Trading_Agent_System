from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.llm_artifacts import trade_artifact_paths
from scripts.run_ai_trade_report_batch import _finalize_report_diagnostics, _sync_report_diagnostics


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_ai_trade_report_batch_syncs_salvaged_diagnostics_to_all_artifacts(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")

    for key in (
        "trade_lifecycle_json",
        "aggregated_execution_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        _write_json(trade_paths[key], {"schema_version": "test.v1"})

    report = {
        "trade_id": "TRD_20260319_000660_01",
        "generation": {
            "status": "salvaged",
            "mode": "ai",
            "model": "stepfun/step-3.5-flash:free",
            "reason": "trade_report_ai returned truncated or partial JSON",
        },
    }
    llm_artifact = {
        "status": "salvaged",
        "model": "stepfun/step-3.5-flash:free",
        "error": "trade_report_ai returned truncated or partial JSON",
    }

    diagnostics = _sync_report_diagnostics(trade_paths, report, llm_artifact)
    _write_json(trade_paths["ai_trade_report_json"], report)
    _finalize_report_diagnostics(trade_paths, trade_paths["ai_trade_report_json"], diagnostics)

    assert diagnostics["report_status"] == "available"
    assert diagnostics["report_reason_code"] == "llm_generation_salvaged"

    for key in (
        "ai_trade_report_json",
        "trade_lifecycle_json",
        "aggregated_execution_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        payload = _read_json(trade_paths[key])
        diag = payload.get("ai_report_diagnostics") or {}
        assert diag["report_status"] == "available"
        assert diag["report_output_available"] is True
