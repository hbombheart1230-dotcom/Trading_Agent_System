from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.trade_bundle_persistence import (
    persist_trade_report_outputs,
    refresh_trade_report_outputs_if_written,
    persist_trade_bundle_outputs,
    persist_trade_llm_artifacts,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_persist_trade_bundle_outputs_writes_files_and_finalizes_health(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "trades" / "2026-04-16" / "TRD_TEST"
    reports_dir = base / "reports"
    evidence_dir = base / "evidence"

    result = persist_trade_bundle_outputs(
        entry_artifact_path=base / "entry.json",
        hold_artifact_path=base / "hold.json",
        exit_artifact_path=base / "exit.json",
        lifecycle_bundle_path=base / "lifecycle_bundle.json",
        trade_provenance_path=base / "_provenance.json",
        trade_health_path=base / "_health.json",
        trade_artifact_links_path=base / "_artifact_links.json",
        story_input_path=base / "ai_trade_report_input.json",
        story_compact_input_path=base / "ai_trade_report_compact_input.json",
        trade_report_json_path=reports_dir / "ai_trade_report.json",
        trade_report_md_path=reports_dir / "ai_trade_report.md",
        strategist_evidence_path=evidence_dir / "strategist_evidence.json",
        scanner_evidence_path=evidence_dir / "scanner_evidence.json",
        monitor_evidence_path=evidence_dir / "monitor_evidence.json",
        commander_evidence_path=evidence_dir / "commander_evidence.json",
        strategist_llm_response_path=reports_dir / "strategist_llm_response.json",
        ai_trade_report_llm_response_path=reports_dir / "ai_trade_report_llm_response.json",
        brief_llm_response_path=reports_dir / "brief_llm_response.json",
        operator_brief_json_path=reports_dir / "operator_brief.json",
        operator_brief_md_path=reports_dir / "operator_brief.md",
        entry_payload={"status": "entry"},
        holding_payload={"status": "holding"},
        exit_payload={"status": "exit"},
        lifecycle_bundle_payload={"schema_version": "live_execution_bundle.v3"},
        trade_provenance_payload={"schema_version": "trade_provenance.v1"},
        trade_health_payload={"schema_version": "trade_health.v1"},
        trade_artifact_links_payload={"schema_version": "trade_artifact_links.v2"},
        diagnostics={"ai_trade_report_status": "ok", "report_status": "available", "llm_brief_status": "skipped"},
    )

    assert (base / "entry.json").exists()
    assert (base / "hold.json").exists()
    assert (base / "exit.json").exists()
    assert (base / "lifecycle_bundle.json").exists()
    assert (base / "_provenance.json").exists()
    assert (base / "_health.json").exists()
    assert (base / "_artifact_links.json").exists()

    health = _read_json(base / "_health.json")
    assert health["llm_trade_report_status"] == "ok"
    assert health["report_generation_status"] == "available"
    assert health["operator_brief_status"] == "missing"
    assert health["artifact_presence"]["entry_json"] is True
    assert health["artifact_presence"]["ai_trade_report_json"] is False
    assert result["artifact_presence"]["lifecycle_bundle_json"] is True
    assert result["trade_health_payload"]["report_generation_status"] == "available"


def test_persist_trade_llm_artifacts_writes_strategist_and_ai_refs(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_reports_dir = reports_root / "trades" / "2026-04-16" / "TRD_TEST" / "reports"
    strategist_path = trade_reports_dir / "strategist_llm_response.json"
    ai_path = trade_reports_dir / "ai_trade_report_llm_response.json"

    result = persist_trade_llm_artifacts(
        reports_root=reports_root,
        day="2026-04-16",
        strategy_anchor_run_id="run-strat",
        anchor_run_id="run-ai",
        strategist_llm_artifact_raw={
            "schema_version": "llm_response_artifact.v1",
            "component": "strategist",
            "status": "ok",
            "response_text": "strategist raw response",
            "prompt_text": "strategist prompt",
        },
        strategist_llm_response_path=strategist_path,
        ai_trade_report_llm_artifact={
            "schema_version": "llm_response_artifact.v1",
            "component": "ai_trade_report",
            "status": "ok",
            "response_text": "ai raw response",
            "prompt_text": "ai prompt",
        },
        ai_trade_report_llm_response_path=ai_path,
    )

    assert strategist_path.exists() is True
    assert ai_path.exists() is True
    strategist_payload = _read_json(strategist_path)
    ai_payload = _read_json(ai_path)
    assert strategist_payload["component"] == "strategist"
    assert strategist_payload["status"] == "ok"
    assert strategist_payload["response_ref"]
    assert ai_payload["component"] == "ai_trade_report"
    assert ai_payload["status"] == "ok"
    assert ai_payload["response_ref"]
    assert result["strategist_llm_response_written"].endswith("strategist_llm_response.json")
    assert result["ai_trade_report_llm_response_written"].endswith("ai_trade_report_llm_response.json")


def test_persist_trade_report_outputs_writes_report_and_sets_diagnostics(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    json_path = reports_dir / "ai_trade_report.json"
    md_path = reports_dir / "ai_trade_report.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)

    result = persist_trade_report_outputs(
        trade_report={"headline": "report"},
        diagnostics={
            "deterministic_report_status": "ok",
            "llm_brief_status": "skipped",
            "ai_trade_report_status": "ok",
            "report_status": "available",
        },
        trade_report_json_path=json_path,
        trade_report_md_path=md_path,
        markdown_renderer=lambda payload: f"# {payload['headline']}\n",
        write_failure_reason_human="write failed",
        write_failure_next_step="retry",
        error_sanitizer=lambda exc: str(exc),
    )

    diagnostics = result["diagnostics"]
    payload = _read_json(json_path)
    assert payload["headline"] == "report"
    assert payload["deterministic_report_status"] == "ok"
    assert md_path.exists() is True
    assert diagnostics["report_output_available"] is True
    assert diagnostics["report_artifact_available"] is True
    assert result["trade_report_json_written"].endswith("ai_trade_report.json")


def test_refresh_trade_report_outputs_if_written_overwrites_with_new_payload(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    json_path = reports_dir / "ai_trade_report.json"
    md_path = reports_dir / "ai_trade_report.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"headline": "old"}, ensure_ascii=False), encoding="utf-8")
    md_path.write_text("# old\n", encoding="utf-8")

    result = refresh_trade_report_outputs_if_written(
        trade_report={"headline": "new", "ai_report_diagnostics": {"report_status": "available"}},
        trade_report_json_written=str(json_path),
        trade_report_json_path=json_path,
        trade_report_md_path=md_path,
        markdown_renderer=lambda payload: f"# {payload['headline']}\n",
    )

    payload = _read_json(json_path)
    assert result["refreshed"] is True
    assert payload["headline"] == "new"
    assert "available" in json.dumps(payload, ensure_ascii=False)
