from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.llm_artifacts import trade_artifact_paths
from scripts.run_ai_trade_report_batch import (
    _finalize_report_diagnostics,
    _normalize_trade_id_filters,
    _resolve_story_input_for_regeneration,
    _sync_report_diagnostics,
    _sync_report_generation_state,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_ai_trade_report_batch_syncs_salvaged_diagnostics_to_all_artifacts(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")

    for key in (
        "lifecycle_bundle_json",
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
        "lifecycle_bundle_json",
        "ai_trade_report_input_json",
        "trade_health_json",
    ):
        payload = _read_json(trade_paths[key])
        diag = payload.get("ai_report_diagnostics") or {}
        assert diag["report_status"] == "available"
        assert diag["report_output_available"] is True


def test_run_ai_trade_report_batch_normalizes_multiple_trade_id_filters() -> None:
    values = _normalize_trade_id_filters(
        ["TRD_1", "TRD_2,TRD_3", "TRD_2", "", "  TRD_4  "]
    )

    assert values == ["TRD_1", "TRD_2", "TRD_3", "TRD_4"]


def test_run_ai_trade_report_batch_syncs_generation_state_without_clobbering_other_components(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_paths = trade_artifact_paths(reports_root, "2026-03-19", "TRD_20260319_000660_01")

    _write_json(
        trade_paths["reports_dir"] / "report_generation_state.json",
        {
            "schema_version": "report_generation_state.v1",
            "components": {
                "ai_trade_report": {
                    "component": "ai_trade_report",
                    "status": "error",
                    "report_status": "missing",
                    "trade_id": "TRD_20260319_000660_01",
                    "run_id": "RUN_OLD",
                },
                "operator_brief": {
                    "component": "operator_brief",
                    "status": "skipped",
                    "skip_reason": "missing_brief_artifact",
                    "trade_id": "TRD_20260319_000660_01",
                },
            },
        },
    )
    _write_json(trade_paths["ai_trade_report_json"], {"schema_version": "test.v1"})
    _write_json(trade_paths["ai_trade_report_md"], {"schema_version": "test.v1"})

    story_input = {
        "trade_id": "TRD_20260319_000660_01",
        "run_id": "RUN_NEW",
        "story_id": "STORY_1",
    }
    compact_input = {"trade": {"symbol": "000660"}}
    report = {
        "ai_trade_report_status": "ok",
        "generation": {
            "status": "ok",
            "mode": "ai",
            "model": "openrouter/test-model",
        },
    }
    llm_artifact = {"status": "ok", "model": "openrouter/test-model"}

    payload = _sync_report_generation_state(
        trade_paths,
        story_input=story_input,
        compact_input=compact_input,
        report=report,
        llm_artifact=llm_artifact,
        llm_response_path=str(trade_paths["ai_trade_report_llm_response_json"]),
    )

    persisted = _read_json(trade_paths["reports_dir"] / "report_generation_state.json")
    ai_state = persisted["components"]["ai_trade_report"]

    assert payload == persisted
    assert ai_state["status"] == "ok"
    assert ai_state["report_status"] == "available"
    assert ai_state["trade_id"] == "TRD_20260319_000660_01"
    assert ai_state["run_id"] == "RUN_NEW"
    assert ai_state["model"] == "openrouter/test-model"
    assert ai_state["llm_response_path"] == str(trade_paths["ai_trade_report_llm_response_json"])
    assert "story_input_sha256" in ai_state["source_inputs"]
    assert "compact_input_sha256" in ai_state["source_inputs"]
    assert persisted["components"]["operator_brief"]["status"] == "skipped"


def test_run_ai_trade_report_batch_prefers_rebuilt_story_input_when_lifecycle_is_richer(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-19"
    trade_id = "TRD_20260319_000660_01"
    trade_paths = trade_artifact_paths(reports_root, day, trade_id)
    trade_dir = reports_root / "trades" / day / trade_id
    trade_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        trade_paths["ai_trade_report_input_json"],
        {
            "schema_version": "trade_story_input.v2",
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "000660",
            "status": "closed",
            "action": "SELL",
            "selected_symbol": None,
            "candidate_count": None,
        },
    )
    _write_json(
        trade_paths["lifecycle_bundle_json"],
        {
            "day": day,
            "trade_id": trade_id,
            "run_id": "RUN_EXIT",
            "symbol": "000660",
            "trade_lifecycle_status": "closed",
            "lifecycle": {
                "entry": {
                    "run_id": "RUN_ENTRY",
                    "ts": "2026-03-19T00:10:00+00:00",
                    "action": "BUY",
                    "reason_human": "entry",
                    "scanner_context": {"selected_symbol": "000660"},
                },
                "hold": {"run_ids": ["RUN_MONITOR"]},
                "exit": {
                    "run_id": "RUN_EXIT",
                    "ts": "2026-03-19T00:11:00+00:00",
                    "action": "SELL",
                    "reason_human": "exit",
                },
            },
            "market_context_human": {"summary": "market"},
            "scanner_reason_human": {
                "summary": "scanner",
                "selected_symbol": "000660",
                "selected_rank": 1,
                "candidate_count": 5,
                "top_candidates": [{"symbol": "000660", "score": 1.2}],
            },
            "filters_human": {"summary": "filters"},
            "monitor_reason_human": {"summary": "monitor"},
            "guard_reason_human": {"summary": "guard"},
            "execution_outcome_human": {"summary": "execution"},
            "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
            "operator_conclusion_human": {"summary": "conclusion"},
            "timeline": [],
            "warnings": [],
            "scanner_evidence": {
                "candidate_ranking_table": {"rows": [{"symbol": "000660", "score_total": 1.2}]}
            },
            "monitor_timeline": {},
        },
    )

    story_input, story_input_path, source, existing_score, rebuilt_score = _resolve_story_input_for_regeneration(
        trade_dir,
        trade_paths,
    )

    assert source == "rebuilt_from_lifecycle_bundle"
    assert story_input_path == str(trade_paths["ai_trade_report_input_json"])
    assert rebuilt_score >= existing_score
    assert story_input["scanner_reason_human"]["selected_symbol"] == "000660"
    assert story_input["scanner_selection_trace"]["selected_symbol"] == "000660"
    assert len(story_input["scanner_selection_trace"]["ranked_candidates"]) >= 1
