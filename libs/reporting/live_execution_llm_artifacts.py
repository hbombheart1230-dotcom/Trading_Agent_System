from __future__ import annotations

from typing import Any, Dict, List

from libs.reporting.live_execution_strategist_artifacts import latest_strategist_evidence_ledger_row
from libs.reporting.llm_artifacts import build_llm_response_artifact, split_prompt_text


def latest_event_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    payload = rows[-1].get("payload") if isinstance(rows[-1], dict) else {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def build_strategist_llm_response_artifact(
    bundle_out: Dict[str, Any],
    *,
    day: str,
    trade_id: str,
    strategist_evidence: Dict[str, Any] | None = None,
    evidence_rows: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    strategist = bundle_out.get("strategist") if isinstance(bundle_out.get("strategist"), dict) else {}
    strategist_evidence = strategist_evidence if isinstance(strategist_evidence, dict) else {}
    evidence_row = latest_strategist_evidence_ledger_row(
        list(evidence_rows or []),
        list(strategist_evidence.get("run_ids") or []),
    )
    llm_saved = latest_event_payload(list(strategist_evidence.get("llm_response_saved") or []))
    llm_prompt = strategist.get("llm_prompt") or evidence_row.get("llm_prompt") or ""
    system_prompt, user_prompt = split_prompt_text(llm_prompt)
    has_direct_strategist_llm_fields = any(
        (
            bool(str(strategist.get("llm_prompt") or "").strip()),
            bool(str(strategist.get("llm_response") or "").strip()),
            bool(str(strategist.get("llm_error") or "").strip()),
        )
    )
    parsed_output = strategist.get("llm_parsed_output") if isinstance(strategist.get("llm_parsed_output"), dict) else {}
    if (not has_direct_strategist_llm_fields or not parsed_output) and isinstance(evidence_row.get("parsed_output"), dict):
        parsed_output = dict(evidence_row.get("parsed_output") or {})
    if not parsed_output and isinstance(llm_saved.get("parsed_output"), dict):
        parsed_output = dict(llm_saved.get("parsed_output") or {})
    raw_response = str(strategist.get("llm_response") or evidence_row.get("llm_response") or "")
    llm_error = str(strategist.get("llm_error") or "")
    if not llm_error:
        llm_error = str(llm_saved.get("blocked_reason") or llm_saved.get("error") or "")
    llm_ok = strategist.get("llm_ok")
    saved_status = str(llm_saved.get("status") or "").strip().lower()
    if saved_status and (not has_direct_strategist_llm_fields or "llm_ok" not in strategist):
        llm_ok = saved_status == "ok"
    elif evidence_row and not has_direct_strategist_llm_fields:
        llm_ok = bool(raw_response or parsed_output) and not str(raw_response).startswith("ERROR:")
    elif llm_ok is None and evidence_row:
        llm_ok = bool(raw_response or parsed_output) and not str(raw_response).startswith("ERROR:")
    llm_model = str(strategist.get("llm_model") or llm_saved.get("model") or "")
    llm_provider = str(strategist.get("llm_provider") or llm_saved.get("provider") or "OpenRouter")
    llm_latency_ms = int(strategist.get("llm_latency_ms") or 0)
    has_linked_llm_evidence = any(
        (
            bool(system_prompt),
            bool(user_prompt),
            bool(raw_response),
            bool(parsed_output),
            bool(llm_model),
            bool(llm_provider),
            bool(llm_latency_ms),
            llm_ok is not None,
            bool(llm_error),
        )
    )
    source_run_id = str(evidence_row.get("run_id") or "")
    bundle_run_id = str(bundle_out.get("run_id") or "")
    reconstructed_from_evidence = bool(evidence_row and not has_direct_strategist_llm_fields)
    source_run_mismatch = bool(source_run_id and bundle_run_id and source_run_id != bundle_run_id)
    source_run_suspect = "strategist-llm-test" in source_run_id.lower()
    original_status = "ok" if bool(llm_ok) else "fallback"
    if raw_response.startswith("ERROR:"):
        original_status = "error"
    if reconstructed_from_evidence and source_run_suspect and original_status == "ok":
        original_status = "salvaged"
        if not llm_error:
            llm_error = "reconstructed_source_mismatch"
    attempts = []
    if has_linked_llm_evidence:
        attempts.append(
            {
                "step": "primary",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_response_text": raw_response,
                "parsed_output": parsed_output,
                "model_info": {
                    "provider": llm_provider,
                    "model": llm_model,
                },
                "latency_ms": llm_latency_ms,
                "status": original_status,
                "error": llm_error,
            }
        )
    meta: Dict[str, Any] = {}
    if not has_linked_llm_evidence:
        meta = {
            "synthetic_placeholder": True,
            "reason_code": "no_linked_strategist_llm_evidence",
            "reason": "No linked strategist LLM evidence was available for this trade bundle.",
            "evidence_available": False,
        }
    elif evidence_row:
        meta["reconstructed_from_evidence_ledger"] = reconstructed_from_evidence
        meta["source_run_id"] = source_run_id
        meta["source_stage"] = str(evidence_row.get("stage") or "")
        if source_run_mismatch:
            meta["source_run_mismatch"] = True
            meta["expected_run_id"] = bundle_run_id
        if source_run_suspect:
            meta["source_run_suspect"] = True
            meta["source_quality"] = "reconstructed_untrusted_source"
    return build_llm_response_artifact(
        component="strategist",
        run_id=str(bundle_out.get("run_id") or ""),
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        status=original_status if has_linked_llm_evidence else "fallback",
        attempts=attempts,
        parsed_output=parsed_output,
        model_info={
            "provider": llm_provider,
            "model": llm_model,
        },
        latency_ms=llm_latency_ms,
        meta=meta,
    )
