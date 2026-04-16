from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_fingerprint(payload: Any) -> str:
    import hashlib

    return hashlib.sha256(stable_json_text(payload).encode("utf-8")).hexdigest()


def build_component_fingerprint(
    *,
    component: str,
    trade_id: str,
    run_id: str,
    lifecycle_status: str,
    story_type: str,
    model: str,
    story_input: Mapping[str, Any] | None,
    compact_input: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    story_hash = payload_fingerprint(dict(story_input or {}))
    compact_hash = payload_fingerprint(dict(compact_input or {}))
    payload = {
        "component": str(component or ""),
        "trade_id": str(trade_id or ""),
        "run_id": str(run_id or ""),
        "lifecycle_status": str(lifecycle_status or ""),
        "story_type": str(story_type or ""),
        "model": str(model or ""),
        "story_input_sha256": story_hash,
        "compact_input_sha256": compact_hash,
    }
    return {
        "fingerprint": payload_fingerprint(payload),
        "source_inputs": {
            "story_input_sha256": story_hash,
            "compact_input_sha256": compact_hash,
        },
        "payload": payload,
    }


def build_ai_trade_report_generation_component(
    *,
    fingerprint: str,
    trade_id: str,
    run_id: str,
    status: str,
    report_status: str,
    report_generation_reason: str,
    model: str,
    report_json_path: str,
    report_md_path: str,
    llm_response_path: str,
    source_inputs: Mapping[str, Any] | None = None,
    updated_at: str = "",
) -> Dict[str, Any]:
    return {
        "fingerprint": str(fingerprint or ""),
        "component": "ai_trade_report",
        "status": str(status or "skipped"),
        "report_status": str(report_status or ""),
        "skip_reason": (
            "fingerprint_match_existing_success"
            if str(report_generation_reason or "") == "fingerprint_match_existing_success"
            else ""
        ),
        "trade_id": str(trade_id or ""),
        "run_id": str(run_id or ""),
        "updated_at": str(updated_at or _utc_now_iso()),
        "model": str(model or ""),
        "report_json_path": str(report_json_path or ""),
        "report_md_path": str(report_md_path or ""),
        "llm_response_path": str(llm_response_path or ""),
        "source_inputs": dict(source_inputs or {}),
    }


def build_operator_brief_generation_component(
    *,
    trade_id: str,
    run_id: str,
    llm_brief_status: str,
    report_json_path: str,
    report_md_path: str,
    llm_response_path: str,
    brief_json_exists: bool,
    brief_md_exists: bool,
    brief_llm_exists: bool,
    updated_at: str = "",
) -> Dict[str, Any]:
    fingerprint_payload = {
        "component": "operator_brief",
        "trade_id": str(trade_id or ""),
        "run_id": str(run_id or ""),
        "brief_json_exists": bool(brief_json_exists),
        "brief_md_exists": bool(brief_md_exists),
        "brief_llm_exists": bool(brief_llm_exists),
        "brief_llm_status": str(llm_brief_status or "skipped"),
    }
    return {
        "fingerprint": payload_fingerprint(fingerprint_payload),
        "component": "operator_brief",
        "status": str(llm_brief_status or "skipped"),
        "skip_reason": (
            "existing_artifact_state_reused"
            if brief_json_exists or brief_md_exists or brief_llm_exists
            else "missing_brief_artifact"
        ),
        "trade_id": str(trade_id or ""),
        "run_id": str(run_id or ""),
        "updated_at": str(updated_at or _utc_now_iso()),
        "report_json_path": str(report_json_path or ""),
        "report_md_path": str(report_md_path or ""),
        "llm_response_path": str(llm_response_path or ""),
    }


def build_generation_state(
    *,
    current_state: Mapping[str, Any] | None,
    ai_trade_report_component: Mapping[str, Any],
    operator_brief_component: Mapping[str, Any],
) -> Dict[str, Any]:
    state = dict(current_state or {})
    state["schema_version"] = str(state.get("schema_version") or "report_generation_state.v1")
    components = dict(state.get("components") or {}) if isinstance(state.get("components"), Mapping) else {}
    components["ai_trade_report"] = dict(ai_trade_report_component or {})
    components["operator_brief"] = dict(operator_brief_component or {})
    state["components"] = components
    return state


def _source_type(raw_source: Any, source_path: Any) -> str:
    src = str(raw_source or "").strip().lower()
    path_text = str(source_path or "").strip()
    if src == "canonical":
        return "canonical"
    if src in {"normalized_trade_artifact", "normalized_trade", "direct_artifact", "direct"}:
        return "trade"
    if src in {"event_log"}:
        return "events"
    if path_text:
        return "trade"
    return "missing"


def build_bundle_provenance(
    *,
    trade_id: str,
    run_id: str,
    day: str,
    lifecycle_status: str,
    recovery_metadata: Mapping[str, Any] | None,
    strategy_anchor_run_id: str,
    evidence_source: str,
    agent_sources: Mapping[str, Any] | None,
    section_provenance: Mapping[str, Any] | None,
    artifacts: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    section_map = dict(section_provenance or {})
    artifact_map = dict(artifacts or {})
    recovery = dict(recovery_metadata or {})
    return {
        "schema_version": "trade_provenance.v1",
        "trade_id": str(trade_id or ""),
        "run_id": str(run_id or ""),
        "day": str(day or ""),
        "lifecycle_status": str(lifecycle_status or ""),
        "trade_origin": str(recovery.get("trade_origin") or ""),
        "lifecycle_completeness": str(recovery.get("lifecycle_completeness") or ""),
        "evidence_recovery_used": bool(recovery.get("evidence_recovery_used")),
        "recovery_missing_sections": list(recovery.get("recovery_missing_sections") or []),
        "recovery_sources": list(recovery.get("recovery_sources") or []),
        "entry_strategist_run_id": str(strategy_anchor_run_id or ""),
        "strategy_anchor_run_id": str(strategy_anchor_run_id or ""),
        "evidence_source": str(evidence_source or "fallback"),
        "agent_sources": dict(agent_sources or {}),
        "section_provenance": section_map,
        "read_precedence": [
            "normalized_trade_artifact",
            "canonical_artifact",
            "event_log",
            "missing",
        ],
        "section_resolution": {
            str(key): {
                "source_type": _source_type((value or {}).get("source"), (value or {}).get("artifact_path")),
                "source_path": str((value or {}).get("artifact_path") or ""),
                "confidence": str((value or {}).get("confidence") or "low"),
            }
            for key, value in section_map.items()
        },
        "canonical_agent_artifact_paths": {
            key: str(value or "")
            for key, value in artifact_map.items()
            if str(key).startswith("canonical_") and str(key).endswith("_json")
        },
    }


def build_bundle_health(
    *,
    trade_id: str,
    run_id: str,
    day: str,
    lifecycle_status: str,
    recovery_metadata: Mapping[str, Any] | None,
    diagnostics: Mapping[str, Any] | None,
    report_generation: Mapping[str, Any] | None,
    evidence_completeness_missing_sections: Iterable[str] | None,
    phase3_missing_sections: Iterable[str] | None,
    phase3_completeness_score: float,
    artifact_presence: Mapping[str, Any] | None,
    ai_trade_report_llm_artifact: Mapping[str, Any] | None,
    strategist_event_count: int,
    scanner_event_count: int,
    monitor_event_count: int,
    operator_brief_json_exists: bool,
) -> Dict[str, Any]:
    recovery = dict(recovery_metadata or {})
    diagnostics_obj = dict(diagnostics or {})
    llm_artifact = dict(ai_trade_report_llm_artifact or {})
    missing_sections = [
        str(x or "")
        for x in list(phase3_missing_sections or [])
        + [str(x or "") for x in list(evidence_completeness_missing_sections or []) if str(x or "").strip()]
        if str(x or "").strip()
    ]
    return {
        "schema_version": "trade_health.v1",
        "trade_id": str(trade_id or ""),
        "run_id": str(run_id or ""),
        "day": str(day or ""),
        "lifecycle_status": str(lifecycle_status or ""),
        "trade_origin": str(recovery.get("trade_origin") or ""),
        "lifecycle_completeness": str(recovery.get("lifecycle_completeness") or ""),
        "evidence_recovery_used": bool(recovery.get("evidence_recovery_used")),
        "recovery_missing_sections": list(recovery.get("recovery_missing_sections") or []),
        "recovery_sources": list(recovery.get("recovery_sources") or []),
        "ai_report_diagnostics": diagnostics_obj,
        "report_generation": dict(report_generation or {}),
        "deterministic_report_status": str(diagnostics_obj.get("deterministic_report_status") or "skipped"),
        "llm_brief_status": str(diagnostics_obj.get("llm_brief_status") or "skipped"),
        "ai_trade_report_status": str(diagnostics_obj.get("ai_trade_report_status") or "skipped"),
        "llm_trade_report_status": str(diagnostics_obj.get("ai_trade_report_status") or "skipped"),
        "report_generation_status": str(diagnostics_obj.get("report_status") or "skipped"),
        "operator_brief_status": (
            str(diagnostics_obj.get("llm_brief_status") or "skipped")
            if bool(operator_brief_json_exists)
            else "missing"
        ),
        "report_generation_reason": str(diagnostics_obj.get("report_generation_reason") or diagnostics_obj.get("report_reason_human") or ""),
        "missing_sections": missing_sections,
        "completeness_score": float(phase3_completeness_score or 0.0),
        "artifact_presence": dict(artifact_presence or {}),
        "llm_response_status": str(llm_artifact.get("status") or ""),
        "llm_parse_mode": str(llm_artifact.get("parse_mode") or ""),
        "llm_completeness_score": float(llm_artifact.get("completeness_score") or 0.0),
        "llm_required_keys_missing": [str(x or "") for x in list(llm_artifact.get("required_keys_missing") or []) if str(x or "").strip()],
        "evidence_counts": {
            "strategist_events": int(strategist_event_count or 0),
            "scanner_events": int(scanner_event_count or 0),
            "monitor_events": int(monitor_event_count or 0),
        },
    }


def finalize_bundle_health(
    health_payload: MutableMapping[str, Any],
    *,
    artifact_presence: Mapping[str, Any] | None,
    diagnostics: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    out = dict(health_payload or {})
    diagnostics_obj = dict(diagnostics or {})
    presence = dict(artifact_presence or {})
    out["artifact_presence"] = presence
    out["llm_trade_report_status"] = str(
        diagnostics_obj.get("ai_trade_report_status")
        or out.get("ai_trade_report_status")
        or "skipped"
    )
    out["report_generation_status"] = (
        "available"
        if bool(presence.get("ai_trade_report_json")) or bool(presence.get("ai_trade_report_md"))
        else str(diagnostics_obj.get("report_status") or "skipped")
    )
    out["operator_brief_status"] = (
        str(diagnostics_obj.get("llm_brief_status") or "skipped")
        if bool(presence.get("operator_brief_json"))
        else "missing"
    )
    out["llm_brief_status"] = str(
        out.get("operator_brief_status") or diagnostics_obj.get("llm_brief_status") or "skipped"
    )
    out["ai_trade_report_status"] = str(
        out.get("llm_trade_report_status") or diagnostics_obj.get("ai_trade_report_status") or "skipped"
    )
    return out


def build_trade_bundle_state(
    *,
    provenance_kwargs: Mapping[str, Any],
    health_kwargs: Mapping[str, Any],
) -> Dict[str, Any]:
    provenance = build_bundle_provenance(**dict(provenance_kwargs or {}))
    health = build_bundle_health(**dict(health_kwargs or {}))
    return {
        "provenance": provenance,
        "health": health,
    }


__all__ = [
    "build_ai_trade_report_generation_component",
    "build_bundle_health",
    "build_bundle_provenance",
    "build_component_fingerprint",
    "build_generation_state",
    "build_operator_brief_generation_component",
    "build_trade_bundle_state",
    "finalize_bundle_health",
    "payload_fingerprint",
    "stable_json_text",
]

