from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, MutableMapping

from libs.reporting.llm_artifacts import persist_llm_artifact_refs, write_json
from libs.reporting.trade_bundle_state import finalize_bundle_health


def persist_trade_llm_artifacts(
    *,
    reports_root: Path,
    day: str,
    strategy_anchor_run_id: str,
    anchor_run_id: str,
    strategist_llm_artifact_raw: Mapping[str, Any] | None,
    strategist_llm_response_path: Path,
    ai_trade_report_llm_artifact: Mapping[str, Any] | None,
    ai_trade_report_llm_response_path: Path,
) -> Dict[str, Any]:
    strategist_llm_artifact = persist_llm_artifact_refs(
        artifact=dict(strategist_llm_artifact_raw or {}),
        reports_root=reports_root,
        day=day,
        run_id=str(strategy_anchor_run_id or anchor_run_id or ""),
        component="strategist",
    )
    write_json(strategist_llm_response_path, strategist_llm_artifact)

    ai_trade_report_llm_compact: Dict[str, Any] = dict(ai_trade_report_llm_artifact or {})
    ai_trade_report_llm_response_written = ""
    if ai_trade_report_llm_compact:
        ai_trade_report_llm_compact = persist_llm_artifact_refs(
            artifact=ai_trade_report_llm_compact,
            reports_root=reports_root,
            day=day,
            run_id=str(anchor_run_id or ""),
            component="ai_trade_report",
        )
        ai_trade_report_llm_response_written = str(
            write_json(ai_trade_report_llm_response_path, ai_trade_report_llm_compact)
        )
    elif ai_trade_report_llm_response_path.exists():
        ai_trade_report_llm_response_written = str(ai_trade_report_llm_response_path)

    return {
        "strategist_llm_artifact": strategist_llm_artifact,
        "strategist_llm_response_written": str(strategist_llm_response_path),
        "ai_trade_report_llm_artifact": ai_trade_report_llm_compact,
        "ai_trade_report_llm_response_written": ai_trade_report_llm_response_written,
    }


def persist_trade_report_outputs(
    *,
    trade_report: Mapping[str, Any] | None,
    diagnostics: Mapping[str, Any] | None,
    trade_report_json_path: Path,
    trade_report_md_path: Path,
    markdown_renderer: Callable[[Dict[str, Any]], str],
    write_failure_reason_human: str,
    write_failure_next_step: str,
    error_sanitizer: Callable[[Any], str],
) -> Dict[str, Any]:
    diagnostics_out = dict(diagnostics or {})
    diagnostics_out["report_output_available"] = False
    diagnostics_out["report_artifact_available"] = False
    trade_report_json_written = ""
    trade_report_md_written = ""
    try:
        trade_report_payload = dict(trade_report or {})
        trade_report_payload.setdefault(
            "deterministic_report_status",
            diagnostics_out.get("deterministic_report_status", "ok"),
        )
        trade_report_payload.setdefault(
            "llm_brief_status",
            diagnostics_out.get("llm_brief_status", "skipped"),
        )
        trade_report_payload.setdefault(
            "ai_trade_report_status",
            diagnostics_out.get("ai_trade_report_status", "skipped"),
        )
        trade_report_json_path.write_text(
            json.dumps(trade_report_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        trade_report_md_path.write_text(
            markdown_renderer(trade_report_payload),
            encoding="utf-8",
        )
        trade_report_json_written = str(trade_report_json_path)
        trade_report_md_written = str(trade_report_md_path)
        diagnostics_out["report_output_available"] = True
        diagnostics_out["report_artifact_available"] = True
    except Exception as exc:
        diagnostics_out["deterministic_report_status"] = "error"
        diagnostics_out["report_status"] = "failed"
        diagnostics_out["report_reason_code"] = "artifact_write_failed"
        diagnostics_out["report_reason_human"] = str(write_failure_reason_human or "")
        diagnostics_out["report_generation_reason"] = str(
            diagnostics_out.get("report_reason_human") or ""
        )
        diagnostics_out["next_expected_step"] = str(write_failure_next_step or "")
        diagnostics_out["last_error_message"] = error_sanitizer(exc)
        diagnostics_out["report_output_available"] = False
        diagnostics_out["report_artifact_available"] = False
    return {
        "diagnostics": diagnostics_out,
        "trade_report_json_written": trade_report_json_written,
        "trade_report_md_written": trade_report_md_written,
    }


def refresh_trade_report_outputs_if_written(
    *,
    trade_report: Mapping[str, Any] | None,
    trade_report_json_written: str,
    trade_report_json_path: Path,
    trade_report_md_path: Path,
    markdown_renderer: Callable[[Dict[str, Any]], str],
) -> Dict[str, Any]:
    if not str(trade_report_json_written or "").strip():
        return {"refreshed": False}
    trade_report_payload = dict(trade_report or {})
    trade_report_json_path.write_text(
        json.dumps(trade_report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    trade_report_md_path.write_text(
        markdown_renderer(trade_report_payload),
        encoding="utf-8",
    )
    return {"refreshed": True}


def persist_trade_bundle_outputs(
    *,
    entry_artifact_path: Path,
    hold_artifact_path: Path,
    exit_artifact_path: Path,
    lifecycle_bundle_path: Path,
    trade_provenance_path: Path,
    trade_health_path: Path,
    trade_artifact_links_path: Path,
    story_input_path: Path,
    story_compact_input_path: Path,
    trade_report_json_path: Path,
    trade_report_md_path: Path,
    strategist_evidence_path: Path,
    scanner_evidence_path: Path,
    monitor_evidence_path: Path,
    commander_evidence_path: Path,
    strategist_llm_response_path: Path,
    ai_trade_report_llm_response_path: Path,
    brief_llm_response_path: Path,
    operator_brief_json_path: Path,
    operator_brief_md_path: Path,
    entry_payload: Mapping[str, Any],
    holding_payload: Mapping[str, Any],
    exit_payload: Mapping[str, Any],
    lifecycle_bundle_payload: Mapping[str, Any],
    trade_provenance_payload: Mapping[str, Any],
    trade_health_payload: MutableMapping[str, Any],
    trade_artifact_links_payload: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
) -> Dict[str, Any]:
    write_json(entry_artifact_path, dict(entry_payload or {}))
    write_json(hold_artifact_path, dict(holding_payload or {}))
    write_json(exit_artifact_path, dict(exit_payload or {}))
    write_json(lifecycle_bundle_path, dict(lifecycle_bundle_payload or {}))
    write_json(trade_provenance_path, dict(trade_provenance_payload or {}))

    artifact_presence = {
        "lifecycle_bundle_json": lifecycle_bundle_path.exists(),
        "entry_json": entry_artifact_path.exists(),
        "hold_json": hold_artifact_path.exists(),
        "exit_json": exit_artifact_path.exists(),
        "ai_trade_report_input_json": story_input_path.exists(),
        "ai_trade_report_compact_input_json": story_compact_input_path.exists(),
        "ai_trade_report_json": trade_report_json_path.exists(),
        "ai_trade_report_md": trade_report_md_path.exists(),
        "strategist_evidence_json": strategist_evidence_path.exists(),
        "scanner_evidence_json": scanner_evidence_path.exists(),
        "monitor_evidence_json": monitor_evidence_path.exists(),
        "commander_evidence_json": commander_evidence_path.exists(),
        "strategist_llm_response_json": strategist_llm_response_path.exists(),
        "ai_trade_report_llm_response_json": ai_trade_report_llm_response_path.exists(),
        "brief_llm_response_json": brief_llm_response_path.exists(),
        "operator_brief_json": operator_brief_json_path.exists(),
        "operator_brief_md": operator_brief_md_path.exists(),
    }

    finalized_trade_health_payload = finalize_bundle_health(
        trade_health_payload,
        artifact_presence=artifact_presence,
        diagnostics=dict(diagnostics or {}),
    )
    write_json(trade_health_path, finalized_trade_health_payload)
    write_json(trade_artifact_links_path, dict(trade_artifact_links_payload or {}))

    return {
        "artifact_presence": artifact_presence,
        "trade_health_payload": finalized_trade_health_payload,
    }
