from __future__ import annotations

from typing import Any

from libs.core.evidence_identity import stable_evidence_id


def build_feedback_application_trace(
    *,
    feedback_packet: dict[str, Any] | None,
    strategist_output: dict[str, Any],
) -> dict[str, Any]:
    packet = dict(feedback_packet or {})
    feedback_id = str(packet.get("feedback_id") or "").strip()
    if packet and not feedback_id:
        feedback_id = stable_evidence_id("feedback", packet)
    consumed = bool(packet.get("consumed"))
    comparisons = {
        "playbook": (
            strategist_output.get("pre_llm_playbook"),
            strategist_output.get("final_playbook") or strategist_output.get("playbook"),
        ),
        "market_regime": (
            strategist_output.get("pre_llm_market_regime"),
            strategist_output.get("market_regime"),
        ),
        "risk_tone": (
            strategist_output.get("pre_llm_risk_tone"),
            strategist_output.get("risk_tone"),
        ),
        "trade_aggressiveness": (
            strategist_output.get("pre_llm_trade_aggressiveness"),
            strategist_output.get("trade_aggressiveness"),
        ),
    }
    changed_fields = [
        key
        for key, (before, after) in comparisons.items()
        if before not in (None, "") and after not in (None, "") and before != after
    ]
    if not feedback_id:
        adoption_status = "NO_FEEDBACK_PACKET"
    elif not consumed:
        adoption_status = "NOT_CONSUMED"
    elif changed_fields:
        adoption_status = "CHANGE_OBSERVED_WITH_FEEDBACK_EXPOSURE"
    else:
        adoption_status = "EXPOSED_NO_OBSERVED_FRAME_CHANGE"
    return {
        "schema_version": "strategist.feedback_application_trace.v1",
        "behavior_effect": "observation_only",
        "feedback_id": feedback_id,
        "source_day": str(packet.get("source_day") or ""),
        "available": bool(packet.get("available")),
        "consumed": consumed,
        "gate_reason": str(packet.get("feedback_gate_reason") or ""),
        "adoption_status": adoption_status,
        "changed_fields": changed_fields,
        "before_after": {
            key: {"before": before, "after": after}
            for key, (before, after) in comparisons.items()
        },
        "causal_attribution": False,
        "causal_limitation": (
            "A frame change during feedback exposure is an adoption candidate, not proof that feedback caused it."
        ),
        "strategist_run_id": str(
            strategist_output.get("run_id") or strategist_output.get("strategist_run_id") or ""
        ),
    }


__all__ = ["build_feedback_application_trace"]
