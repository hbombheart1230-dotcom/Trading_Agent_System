from __future__ import annotations

from typing import Any, Dict

from libs.reporting.trade_report_common import is_empty_placeholder


def has_substantive_exit_evidence(exit_payload: Any) -> bool:
    exit_ctx = exit_payload if isinstance(exit_payload, dict) else {}
    if not exit_ctx:
        return False
    if str(exit_ctx.get("run_id") or "").strip():
        return True
    if str(exit_ctx.get("ts") or "").strip():
        return True
    if str(exit_ctx.get("reason_human") or "").strip():
        return True
    for key in ("price", "avg_price", "qty"):
        if exit_ctx.get(key) not in (None, "", 0, 0.0):
            return True
    execution_details = exit_ctx.get("execution_details") if isinstance(exit_ctx.get("execution_details"), dict) else {}
    if str(execution_details.get("order_status") or "").strip():
        return True
    if str(execution_details.get("order_id") or "").strip():
        return True
    monitor_context = exit_ctx.get("monitor_context") if isinstance(exit_ctx.get("monitor_context"), dict) else {}
    if str(monitor_context.get("trigger_type") or "").strip():
        return True
    return False


def set_or_replace_placeholder(target: Dict[str, Any], key: str, value: Any) -> None:
    if not isinstance(target, dict):
        return
    if key not in target or is_empty_placeholder(target.get(key)):
        target[key] = value


def derive_evidence_provenance(bundle_out: Dict[str, Any]) -> Dict[str, Any]:
    evidence = dict(bundle_out.get("evidence_provenance") or {})
    artifacts = bundle_out.get("artifacts") if isinstance(bundle_out.get("artifacts"), dict) else {}
    canonical_agent_artifacts = (
        bundle_out.get("canonical_agent_artifacts")
        if isinstance(bundle_out.get("canonical_agent_artifacts"), dict)
        else {}
    )

    for agent in ("commander", "strategist", "scanner", "monitor", "supervisor", "executor"):
        if not is_empty_placeholder(evidence.get(agent)):
            continue
        canonical_key = f"canonical_{agent}_json"
        canonical_path = str(artifacts.get(canonical_key) or "").strip()
        canonical_payload = canonical_agent_artifacts.get(agent)
        if canonical_path or (
            isinstance(canonical_payload, dict) and bool(canonical_payload)
        ) or (
            isinstance(canonical_payload, str) and canonical_payload.strip()
        ):
            evidence[agent] = "canonical"
            continue
        direct_payload = bundle_out.get(agent)
        if isinstance(direct_payload, dict) and bool(direct_payload):
            evidence[agent] = "direct_artifact"

    if is_empty_placeholder(evidence.get("reporter")):
        reporter_path = str(artifacts.get("reporter_analysis_json") or "").strip()
        same_day_linkage = (
            bundle_out.get("same_day_reporter_linkage")
            if isinstance(bundle_out.get("same_day_reporter_linkage"), dict)
            else {}
        )
        reporter_status = str((same_day_linkage or {}).get("status") or "").strip().lower()
        if reporter_path or reporter_status in {"linked_run", "linked_day_fallback"}:
            evidence["reporter"] = "direct_artifact"

    return evidence
