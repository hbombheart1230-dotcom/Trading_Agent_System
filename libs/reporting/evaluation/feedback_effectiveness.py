from __future__ import annotations

from typing import Any

from .contracts import CONTRACT_VERSION, DecisionClass


def build_feedback_effectiveness(
    trade_models: list[dict[str, Any]],
    q9_windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    exposed = 0
    adopted = 0
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for window in list(q9_windows or []):
        provenance = window.get("strategist_provenance") if isinstance(window.get("strategist_provenance"), dict) else {}
        feedback = provenance.get("feedback") if isinstance(provenance.get("feedback"), dict) else {}
        feedback_id = str(feedback.get("feedback_id") or "")
        if not feedback_id:
            continue
        decision_id = str(window.get("decision_id") or window.get("q9_decision_id") or "")
        identity = (feedback_id, decision_id)
        if identity in seen:
            continue
        seen.add(identity)
        exposed += 1
        adoption_status = str(feedback.get("adoption_status") or "")
        adoption_candidate = adoption_status == "CHANGE_OBSERVED_WITH_FEEDBACK_EXPOSURE"
        adopted += int(adoption_candidate)
        records.append({
            "feedback_id": feedback_id,
            "later_decision_id": decision_id,
            "source_day": str(feedback.get("source_day") or ""),
            "consumed": bool(feedback.get("consumed")),
            "adoption_status": adoption_status,
            "adoption_candidate": adoption_candidate,
            "changed_fields": list(feedback.get("changed_fields") or []),
            "causal_attribution": False,
            "performance_delta_pct": None,
        })
    for model in trade_models:
        references = model.get("provenance") if isinstance(model.get("provenance"), dict) else {}
        fields = references.get("field_sources") if isinstance(references.get("field_sources"), dict) else {}
        feedback_source = str(fields.get("strategy_policy_source") or "")
        if "feedback" not in feedback_source.lower():
            continue
        identity = (feedback_source, str(model.get("trade_id") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        exposed += 1
        records.append({
            "trade_id": model.get("trade_id"),
            "feedback_source": feedback_source,
            "adopted": False,
            "performance_delta_pct": None,
        })
    return {
        "schema_version": "feedback_effectiveness.v1",
        "contract_version": CONTRACT_VERSION,
        "decision_class": DecisionClass.INSUFFICIENT_EVIDENCE.value,
        "exposure_count": exposed,
        "adoption_count": adopted,
        "adoption_rate": round(adopted / exposed, 4) if exposed else 0.0,
        "usefulness_score": None,
        "records": records,
        "provenance_linkage_status": "ACTIVE" if records else "AWAITING_NEW_RUNTIME_ARTIFACTS",
        "missing_requirement": "paired feedback-disabled control outcomes for causal performance delta",
        "causal_claim_allowed": False,
    }
