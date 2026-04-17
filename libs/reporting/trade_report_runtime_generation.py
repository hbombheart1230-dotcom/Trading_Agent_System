from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from libs.reporting.llm_artifacts import canonical_llm_status, write_json
from libs.reporting.trade_bundle_state import (
    build_ai_trade_report_generation_component,
    build_generation_state,
    build_operator_brief_generation_component,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}



def report_generation_state_path(trade_paths: Dict[str, Path]) -> Path:
    return trade_paths["reports_dir"] / "report_generation_state.json"



def load_report_generation_state(path: Path) -> Dict[str, Any]:
    payload = _read_json(path)
    if payload:
        payload.setdefault("schema_version", "report_generation_state.v1")
        payload.setdefault("components", {})
        return payload
    return {"schema_version": "report_generation_state.v1", "components": {}}



def write_report_generation_state(path: Path, payload: Dict[str, Any]) -> None:
    write_json(path, payload)



def apply_runtime_diagnostics_context(
    diagnostics: Dict[str, Any],
    *,
    holding_phase_observability: Dict[str, Any],
    same_day_reporter_linkage: Dict[str, Any],
    execution_details: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(diagnostics or {})
    out["holding_evidence_thin"] = bool(holding_phase_observability.get("hold_evidence_thin"))
    out["hold_events_count"] = int(holding_phase_observability.get("hold_events_count") or 0)
    out["hold_duration_sec"] = holding_phase_observability.get("hold_duration_sec")
    out["same_day_reporter_linkage_status"] = str(same_day_reporter_linkage.get("status") or "")
    out["same_day_reporter_linkage_reason"] = str(same_day_reporter_linkage.get("linkage_reason") or "")
    out["execution_fields_missing"] = [
        key
        for key in ("order_status", "order_id", "execution_mode", "broker_env", "filled_qty", "avg_price")
        if execution_details.get(key) in (None, "", [])
    ]
    return out



def build_live_generation_state_payload(
    *,
    current_state: Dict[str, Any],
    generation_components: Dict[str, Any],
    ai_trade_report_fingerprint: str,
    trade_id: str,
    run_id: str,
    diagnostics: Dict[str, Any],
    configured_report_model: str,
    trade_report_json_path: Path,
    trade_report_md_path: Path,
    ai_trade_report_llm_response_path: Path,
    ai_trade_report_llm_response_written: str,
    ai_trade_report_fingerprint_info: Dict[str, Any],
    operator_brief_json_path: Path,
    operator_brief_md_path: Path,
    brief_llm_response_path: Path,
) -> Dict[str, Any]:
    ai_generation_component = build_ai_trade_report_generation_component(
        fingerprint=ai_trade_report_fingerprint,
        trade_id=trade_id,
        run_id=run_id,
        status=str(diagnostics.get("ai_trade_report_status") or "skipped"),
        report_status=str(diagnostics.get("report_status") or ""),
        report_generation_reason=str(diagnostics.get("report_generation_reason") or ""),
        model=str(diagnostics.get("llm_model_used") or configured_report_model or ""),
        report_json_path=str(trade_report_json_path),
        report_md_path=str(trade_report_md_path),
        llm_response_path=str(ai_trade_report_llm_response_path if ai_trade_report_llm_response_written else ""),
        source_inputs=dict(ai_trade_report_fingerprint_info.get("source_inputs") or {}),
        updated_at=_utc_now_iso(),
    )
    operator_brief_generation_component = build_operator_brief_generation_component(
        trade_id=trade_id,
        run_id=run_id,
        llm_brief_status=str(diagnostics.get("llm_brief_status") or "skipped"),
        report_json_path=str(operator_brief_json_path),
        report_md_path=str(operator_brief_md_path),
        llm_response_path=str(brief_llm_response_path),
        brief_json_exists=bool(operator_brief_json_path.exists()),
        brief_md_exists=bool(operator_brief_md_path.exists()),
        brief_llm_exists=bool(brief_llm_response_path.exists()),
        updated_at=_utc_now_iso(),
    )
    generation_state = build_generation_state(
        current_state={
            **dict(current_state or {}),
            "components": dict(generation_components or {}),
        },
        ai_trade_report_component=ai_generation_component,
        operator_brief_component=operator_brief_generation_component,
    )
    return {
        "generation_state": generation_state,
        "generation_components": dict(generation_state.get("components") or {}),
        "ai_generation_component": ai_generation_component,
        "operator_brief_generation_component": operator_brief_generation_component,
    }



def _sanitize_generation_error(value: Any, *, max_len: int = 260) -> str:
    text = str(value or "").strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."



def plan_live_trade_report_generation(
    *,
    should_attempt_generation: bool,
    report_requested: bool,
    diagnostics: Mapping[str, Any] | None,
    deterministic_report: Mapping[str, Any] | None,
    existing_trade_report_artifact: Mapping[str, Any] | None,
    existing_ai_trade_report_llm_artifact: Mapping[str, Any] | None,
    ai_trade_report_generation_state: Mapping[str, Any] | None,
    ai_trade_report_fingerprint: str,
    trade_report_json_path: Path,
    trade_report_md_path: Path,
    configured_report_model: str,
    existing_report_noisy: bool = False,
) -> Dict[str, Any]:
    diagnostics_out = dict(diagnostics or {})
    deterministic_report_obj = dict(deterministic_report or {})
    existing_report_obj = dict(existing_trade_report_artifact or {})
    existing_llm_obj = dict(existing_ai_trade_report_llm_artifact or {})
    generation_state_obj = dict(ai_trade_report_generation_state or {})
    log_events: list[Dict[str, Any]] = []
    mode = "deterministic_only"
    trade_report = dict(deterministic_report_obj)
    ai_trade_report_llm_artifact: Dict[str, Any] = {}

    if should_attempt_generation:
        existing_generation = (
            existing_report_obj.get("generation")
            if isinstance(existing_report_obj.get("generation"), dict)
            else {}
        )
        existing_ai_status = canonical_llm_status(
            existing_llm_obj.get("llm_status")
            or existing_llm_obj.get("status")
            or existing_generation.get("status")
            or existing_report_obj.get("ai_trade_report_status")
            or "skipped",
            default="skipped",
        )
        fingerprint_match = (
            str(generation_state_obj.get("fingerprint") or "") == str(ai_trade_report_fingerprint or "")
        )
        existing_report_success = (
            fingerprint_match
            and existing_ai_status in {"ok", "salvaged", "partial"}
            and trade_report_json_path.exists()
            and trade_report_md_path.exists()
            and not existing_report_noisy
        )
        if existing_report_success and existing_report_obj:
            merged_existing = dict(deterministic_report_obj)
            merged_existing.update(existing_report_obj)
            trade_report = merged_existing
            ai_trade_report_llm_artifact = dict(existing_llm_obj)
            diagnostics_out["generation_attempted"] = False
            diagnostics_out["generation_ts"] = _utc_now_iso()
            diagnostics_out["ai_trade_report_status"] = existing_ai_status
            diagnostics_out["llm_model_used"] = str(
                existing_generation.get("model")
                or generation_state_obj.get("model")
                or configured_report_model
                or ""
            )
            diagnostics_out["report_status"] = "available"
            diagnostics_out["report_reason_code"] = ""
            diagnostics_out["report_reason_human"] = (
                "Existing AI trade report artifact was reused because inputs fingerprint matched."
            )
            diagnostics_out["report_generation_reason"] = "fingerprint_match_existing_success"
            diagnostics_out["next_expected_step"] = (
                "Open the existing full report for detailed lifecycle analysis."
            )
            log_events.append(
                {
                    "event": "report_generation_skipped_fingerprint_match",
                    "component": "ai_trade_report",
                    "fingerprint": str(ai_trade_report_fingerprint or ""),
                    "reason": "existing_successful_artifact_with_matching_inputs",
                }
            )
            mode = "reuse_existing_success"
        else:
            if fingerprint_match and existing_report_noisy:
                log_events.append(
                    {
                        "event": "report_generation_forced_regen_noisy_existing_report",
                        "component": "ai_trade_report",
                        "fingerprint": str(ai_trade_report_fingerprint or ""),
                        "reason": "existing_report_contains_text_corruption_markers",
                    }
                )
            diagnostics_out["generation_attempted"] = True
            diagnostics_out["generation_ts"] = _utc_now_iso()
            mode = "generate_ai"
    elif existing_report_obj:
        trade_report = (
            dict(existing_report_obj)
            if not report_requested
            else {**dict(deterministic_report_obj), **dict(existing_report_obj)}
        )
        status_source = dict(trade_report)
        generation_source = (
            status_source.get("generation") if isinstance(status_source.get("generation"), dict) else {}
        )
        diagnostics_out["ai_trade_report_status"] = canonical_llm_status(
            status_source.get("ai_trade_report_status")
            or generation_source.get("ai_trade_report_status")
            or existing_llm_obj.get("llm_status")
            or existing_llm_obj.get("status")
            or "skipped",
            default="skipped",
        )
        diagnostics_out["report_status"] = "available"
        diagnostics_out["report_reason_code"] = ""
        diagnostics_out["report_reason_human"] = (
            "Existing trade report artifact was preserved because AI generation was not requested."
            if not report_requested
            else "Existing trade report artifact was reused."
        )
        diagnostics_out["next_expected_step"] = "Open the full report for detailed lifecycle analysis."
        diagnostics_out["report_generation_reason"] = str(
            diagnostics_out.get("report_reason_human") or ""
        )
        mode = "reuse_existing_report"
    else:
        diagnostics_out["report_status"] = "available"
        diagnostics_out["report_reason_code"] = "deterministic_only"
        diagnostics_out["report_reason_human"] = "Deterministic report was generated without AI expansion."
        diagnostics_out["next_expected_step"] = "Review deterministic report sections and evidence linkage."
        diagnostics_out["report_generation_reason"] = str(
            diagnostics_out.get("report_reason_human") or ""
        )
        mode = "deterministic_only"

    return {
        "mode": mode,
        "trade_report": trade_report,
        "diagnostics": diagnostics_out,
        "ai_trade_report_llm_artifact": ai_trade_report_llm_artifact,
        "log_events": log_events,
    }



def apply_ai_trade_report_generation_result(
    *,
    diagnostics: Mapping[str, Any] | None,
    deterministic_report: Mapping[str, Any] | None,
    ai_trade_report: Mapping[str, Any] | None,
    configured_report_model: str,
) -> Dict[str, Any]:
    diagnostics_out = dict(diagnostics or {})
    deterministic_report_obj = dict(deterministic_report or {})
    ai_trade_report_obj = dict(ai_trade_report or {})
    ai_trade_report_llm_artifact = (
        dict(ai_trade_report_obj.get("llm_response_artifact"))
        if isinstance(ai_trade_report_obj.get("llm_response_artifact"), dict)
        else {}
    )
    generation = (
        ai_trade_report_obj.get("generation")
        if isinstance(ai_trade_report_obj.get("generation"), dict)
        else {}
    )
    ai_status = canonical_llm_status(
        ai_trade_report_obj.get("ai_trade_report_status")
        or generation.get("ai_trade_report_status")
        or generation.get("status")
        or ai_trade_report_obj.get("status")
        or "error",
        default="error",
    )
    diagnostics_out["ai_trade_report_status"] = ai_status
    diagnostics_out["llm_model_used"] = str(generation.get("model") or configured_report_model or "")
    if ai_status in {"ok", "salvaged", "partial"}:
        trade_report = dict(ai_trade_report_obj)
        diagnostics_out["report_status"] = "available"
        diagnostics_out["report_reason_code"] = ""
        diagnostics_out["report_reason_human"] = (
            "AI trade report was generated successfully."
            if ai_status == "ok"
            else "AI trade report was generated with recovery. Deterministic evidence remains the factual source."
        )
        diagnostics_out["next_expected_step"] = "Open the full report for detailed lifecycle analysis."
    else:
        trade_report = dict(deterministic_report_obj)
        diagnostics_out["report_status"] = "available"
        diagnostics_out["report_reason_code"] = "llm_generation_failed"
        diagnostics_out["report_reason_human"] = (
            "AI trade report generation failed. Deterministic report was preserved."
        )
        diagnostics_out["next_expected_step"] = (
            "Check OpenRouter/model connectivity and retry report generation."
        )
        diagnostics_out["last_error_message"] = _sanitize_generation_error(generation.get("reason"))
    diagnostics_out["report_generation_reason"] = str(
        diagnostics_out.get("report_reason_human") or ""
    )
    return {
        "trade_report": trade_report,
        "diagnostics": diagnostics_out,
        "ai_trade_report_llm_artifact": ai_trade_report_llm_artifact,
        "ai_status": ai_status,
    }



def execute_ai_trade_report_generation(
    *,
    trade_story_input: Mapping[str, Any] | None,
    diagnostics: Mapping[str, Any] | None,
    deterministic_report: Mapping[str, Any] | None,
    configured_report_model: str,
    ai_report_builder: Callable[..., Mapping[str, Any]],
    model: str,
    temperature: Any,
    max_tokens: Any,
) -> Dict[str, Any]:
    ai_trade_report = ai_report_builder(
        trade_story_input,
        enabled=True,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return apply_ai_trade_report_generation_result(
        diagnostics=dict(diagnostics or {}),
        deterministic_report=dict(deterministic_report or {}),
        ai_trade_report=dict(ai_trade_report or {}),
        configured_report_model=configured_report_model,
    )
