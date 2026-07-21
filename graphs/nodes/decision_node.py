from __future__ import annotations

from typing import Any, Dict, Tuple


def _monitor_exit_guard_blocks_sell(state: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    monitor_exit = state.get("monitor_exit") if isinstance(state.get("monitor_exit"), dict) else {}
    if not monitor_exit:
        return False, "", {"guard_applied": False}

    trigger_details = (
        monitor_exit.get("trigger_details")
        if isinstance(monitor_exit.get("trigger_details"), dict)
        else {}
    )
    guard_reason = str(
        trigger_details.get("sell_guard_reason")
        or monitor_exit.get("sell_guard_reason")
        or monitor_exit.get("guard_reason")
        or ""
    ).strip()
    exit_reason = str(monitor_exit.get("reason") or monitor_exit.get("exit_reason") or "").strip()
    monitor_reason = str(monitor_exit.get("monitor_reason") or "").strip()
    guard_blocked = bool(
        trigger_details.get("sell_guard_blocked")
        or monitor_exit.get("sell_guard_blocked")
        or monitor_exit.get("guard_blocked")
    )

    pending_reason = (
        guard_reason.startswith("exit_confirmation_pending:")
        or exit_reason.startswith("exit_confirmation_pending:")
        or monitor_reason == "exit_signal_pending_confirmation"
    )
    if not guard_blocked and not pending_reason:
        return False, "", {"guard_applied": True, "blocked": False}

    details = {
        "guard_applied": True,
        "blocked": True,
        "monitor_exit_triggered": bool(monitor_exit.get("triggered")),
        "monitor_exit_reason": exit_reason,
        "monitor_reason": monitor_reason,
        "sell_guard_reason": guard_reason,
        "sell_guard_blocked": guard_blocked,
    }
    return True, guard_reason or exit_reason or monitor_reason or "monitor_exit_not_confirmed", details


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

    # The graph may reuse state across a re-scan. Decision-specific narrative
    # must not leak from a prior reject into the current decision snapshot.
    state.pop("decision_detail", None)

    policy = state.get("policy") or {}
    min_confidence = float(policy.get("min_confidence") or 0.6)
    max_risk = float(policy.get("max_risk") or 0.7)
    max_scan_retries = int(policy.get("max_scan_retries") or 1)

    intents = state.get("intents") or []
    has_any_intent = isinstance(intents, list) and len(intents) > 0
    has_selected = bool(state.get("selected"))

    if has_any_intent:
        first_intent = intents[0] if isinstance(intents[0], dict) else {}
        raw_side = str(first_intent.get("side") or first_intent.get("action") or "").strip().upper()
        meta = first_intent.get("meta") if isinstance(first_intent.get("meta"), dict) else {}
        entry_signal_source = str(meta.get("entry_signal_source") or "").strip().lower()
        monitor_output = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
        monitor_intent_side = str(monitor_output.get("intent_side") or "").strip().upper()
        if raw_side in ("SELL", "CLOSE", "EXIT"):
            blocked, reason, details = _monitor_exit_guard_blocks_sell(state)
            if blocked:
                state["decision"] = "reject"
                state["decision_reason"] = "monitor_exit_not_confirmed"
                state["decision_detail"] = reason
                state["monitor_exit_execution_guard"] = details
                state["risk"] = {
                    "risk_score": float(first_intent.get("risk_score") or 0.0),
                    "confidence": float(first_intent.get("confidence") or 1.0),
                }
                return state
            state["decision"] = "approve"
            state["decision_reason"] = "exit_within_policy"
            state["risk"] = {
                "risk_score": float(first_intent.get("risk_score") or 0.0),
                "confidence": float(first_intent.get("confidence") or 1.0),
            }
            return state
        if raw_side == "BUY" and (
            entry_signal_source == "monitor_intraday_entry" or monitor_intent_side == "BUY"
        ):
            # Monitor BUY intent already passed intraday entry gates.
            # Decision node should not re-reject it with scanner-only risk defaults.
            state["decision"] = "approve"
            state["decision_reason"] = "monitor_entry_within_policy"
            state["risk"] = {
                "risk_score": float(first_intent.get("risk_score") or 0.0),
                "confidence": float(first_intent.get("confidence") or 1.0),
            }
            return state

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
