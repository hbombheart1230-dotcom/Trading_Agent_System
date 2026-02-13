from __future__ import annotations

from typing import Any, Dict, Tuple


def _extract_risk_confidence(state: Dict[str, Any]) -> Tuple[float, float]:
    """Extract (risk_score, confidence) from state.

    Priority (new values first):
      1) selected (preferred)
      2) intents[0] (backward compat + test injection)
      3) risk field (cached/previous; lowest priority)

    Rationale:
      - `risk` is a derived/cached field that may be stale after a re-scan.
      - Tests (and some injection paths) update `intents` directly.
    """
    # 1) selected
    sel = state.get("selected") or {}
    if isinstance(sel, dict):
        r = sel.get("risk_score")
        c = sel.get("confidence")
        if r is not None or c is not None:
            return float(r or 0.0), float(c or 0.0)
        # sometimes nested
        sr = sel.get("risk") or {}
        if isinstance(sr, dict) and (sr.get("risk_score") is not None or sr.get("confidence") is not None):
            return float(sr.get("risk_score") or 0.0), float(sr.get("confidence") or 0.0)

    # 2) backward compat: first intent
    intents = state.get("intents") or []
    if isinstance(intents, list) and intents:
        it0 = intents[0] if isinstance(intents[0], dict) else {}
        return float(it0.get("risk_score") or 0.0), float(it0.get("confidence") or 0.0)

    # 3) explicit risk field (cached)
    risk = state.get("risk") or {}
    if isinstance(risk, dict) and (risk.get("risk_score") is not None or risk.get("confidence") is not None):
        return float(risk.get("risk_score") or 0.0), float(risk.get("confidence") or 0.0)

    return 0.0, 0.0


def decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Decision (risk/confidence based).

    Rules (deterministic):
      - if no candidate selected and no intents -> noop
      - if risk_score >= max_risk -> reject (reason: risk_too_high)
      - if confidence < min_confidence -> retry_scan (reason: low_confidence_retry) until max_scan_retries,
        then reject (reason: low_confidence_reject)
      - else -> approve (reason: within_policy)

    NOTE:
      - approve means 'eligible to proceed', not 'execute'.
      - Execution is still governed by Supervisor/ApprovalService + guards.
    """

    policy = state.get("policy") or {}
    min_confidence = float(policy.get("min_confidence") or 0.6)
    max_risk = float(policy.get("max_risk") or 0.7)
    max_scan_retries = int(policy.get("max_scan_retries") or 1)

    intents = state.get("intents") or []
    has_any_intent = isinstance(intents, list) and len(intents) > 0
    has_selected = bool(state.get("selected"))

    if not has_selected and not has_any_intent:
        state["decision"] = "noop"
        state["decision_reason"] = "no_candidate"
        return state

    risk_score, confidence = _extract_risk_confidence(state)
    state["risk"] = {"risk_score": float(risk_score), "confidence": float(confidence)}

    retry_count = int(state.get("retry_count_scan") or 0)

    if risk_score >= max_risk:
        state["decision"] = "reject"
        state["decision_reason"] = "risk_too_high"
        state["decision_detail"] = f"risk_score({risk_score:.3f})>=max_risk({max_risk:.3f})"
        return state

    if confidence < min_confidence:
        if retry_count < max_scan_retries:
            state["decision"] = "retry_scan"
            state["decision_reason"] = "low_confidence_retry"
            state["decision_detail"] = (
                f"confidence({confidence:.3f})<min_confidence({min_confidence:.3f});"
                f" retry {retry_count+1}/{max_scan_retries}"
            )
            state["retry_count_scan"] = retry_count + 1
        else:
            state["decision"] = "reject"
            state["decision_reason"] = "low_confidence_reject"
            state["decision_detail"] = (
                f"confidence({confidence:.3f})<min_confidence({min_confidence:.3f});"
                f" retries_exhausted({max_scan_retries})"
            )
        return state

    state["decision"] = "approve"
    state["decision_reason"] = "within_policy"
    return state
