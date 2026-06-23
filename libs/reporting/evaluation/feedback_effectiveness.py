from __future__ import annotations

from typing import Any

from .contracts import CONTRACT_VERSION, DecisionClass


def build_feedback_effectiveness(trade_models: list[dict[str, Any]]) -> dict[str, Any]:
    exposed = 0
    adopted = 0
    records: list[dict[str, Any]] = []
    for model in trade_models:
        references = model.get("provenance") if isinstance(model.get("provenance"), dict) else {}
        fields = references.get("field_sources") if isinstance(references.get("field_sources"), dict) else {}
        feedback_source = str(fields.get("strategy_policy_source") or "")
        if "feedback" not in feedback_source.lower():
            continue
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
        "missing_requirement": "canonical feedback_id and later_decision_id linkage",
    }
