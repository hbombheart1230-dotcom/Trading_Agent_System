from __future__ import annotations

from typing import Any, Dict

from libs.runtime.monitor_policy import summarize_monitor_policy_deltas


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def resolve_monitor_memory_bias_payload(
    *,
    strategy_monitor_policy: Dict[str, Any],
    commander_context: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if (
        isinstance(strategy_monitor_policy.get("monitor_memory_bias"), dict)
        and strategy_monitor_policy.get("monitor_memory_bias")
    ):
        return dict(strategy_monitor_policy.get("monitor_memory_bias") or {})
    if isinstance(commander_context.get("monitor_memory_bias"), dict) and commander_context.get("monitor_memory_bias"):
        return dict(commander_context.get("monitor_memory_bias") or {})
    if isinstance(state.get("monitor_memory_bias"), dict):
        return dict(state.get("monitor_memory_bias") or {})
    return {}


def resolve_commander_entry_control_for_monitor(
    *,
    commander_context: Dict[str, Any],
    strategy_monitor_policy: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    applied_policy = (
        dict(strategy_monitor_policy.get("applied_policy") or {})
        if isinstance(strategy_monitor_policy.get("applied_policy"), dict)
        else {}
    )
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    scanner_policy = (
        dict(commander_decision.get("scanner_policy") or {})
        if isinstance(commander_decision.get("scanner_policy"), dict)
        else {}
    )
    candidates = [
        commander_context.get("commander_entry_control"),
        commander_context.get("entry_control"),
        strategy_monitor_policy.get("commander_entry_control"),
        strategy_monitor_policy.get("entry_control"),
        applied_policy.get("commander_entry_control"),
        applied_policy.get("entry_control"),
        commander_decision.get("entry_control"),
        scanner_policy.get("entry_control"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    if scanner_policy.get("max_priority_rank") not in (None, ""):
        max_priority_rank = int(_clamp(_to_float(scanner_policy.get("max_priority_rank")), 1, 10))
        return {
            "schema_version": "commander_entry_control.v1",
            "source": "commander_decision.scanner_policy",
            "mode": "scanner_policy_limits",
            "max_priority_rank": int(max_priority_rank),
            "max_runner_ups": int(max(0, max_priority_rank - 1)),
            "allow_dynamic_entry_band": False,
        }
    return {}


def resolve_entry_candidate_cascade_config(entry_control: Dict[str, Any]) -> Dict[str, Any]:
    raw_rank = entry_control.get("max_priority_rank") if isinstance(entry_control, dict) else None
    raw_runner_ups = entry_control.get("max_runner_ups") if isinstance(entry_control, dict) else None
    if raw_rank not in (None, ""):
        max_priority_rank = int(_clamp(_to_float(raw_rank), 1, 10))
    elif raw_runner_ups not in (None, ""):
        max_priority_rank = int(_clamp(_to_float(raw_runner_ups) + 1, 1, 10))
    else:
        max_priority_rank = 10
    max_runner_ups = int(max(0, max_priority_rank - 1))
    if raw_runner_ups not in (None, ""):
        max_runner_ups = int(_clamp(_to_float(raw_runner_ups), 0, max_runner_ups))
    commander_expanded_repeated_blocker = (
        str(entry_control.get("candidate_watch_policy_effect") or "").strip()
        == "commander_expanded_repeated_blocker"
        or str(entry_control.get("mode") or "").strip() == "expand_when_market_ok"
    )
    cascade_enabled = (
        _is_trueish(entry_control.get("cascade_enabled"))
        if isinstance(entry_control, dict) and entry_control.get("cascade_enabled") not in (None, "")
        else max_runner_ups > 0
    )
    if commander_expanded_repeated_blocker and max_runner_ups > 0:
        cascade_enabled = True
    if not cascade_enabled:
        max_runner_ups = 0
    return {
        "max_priority_rank": int(max_priority_rank),
        "max_runner_ups": int(max_runner_ups),
        "cascade_enabled": bool(cascade_enabled and max_runner_ups > 0),
        "cascade_allowed_reasons": list((entry_control or {}).get("cascade_allowed_reasons") or []),
        "cascade_blocked_reasons": list((entry_control or {}).get("cascade_blocked_reasons") or []),
        "source": str((entry_control or {}).get("source") or "default"),
        "mode": str((entry_control or {}).get("mode") or "default"),
    }


def monitor_policy_adjustment_inputs(frame: Dict[str, Any]) -> Dict[str, str]:
    return {
        "playbook": str(frame.get("playbook") or "").strip(),
        "monitor_guidance": str(frame.get("monitor_guidance") or "").strip(),
        "risk_tone": str(frame.get("risk_tone") or "").strip(),
        "trade_aggressiveness": str(frame.get("trade_aggressiveness") or "").strip(),
    }


def build_monitor_effective_policy_trace(
    *,
    received_policy: Dict[str, Any],
    effective_policy: Dict[str, Any],
    frame: Dict[str, Any],
    received_policy_source: str,
) -> Dict[str, Any]:
    adjustment_inputs = monitor_policy_adjustment_inputs(frame)
    deltas = summarize_monitor_policy_deltas(received_policy, effective_policy)
    changed_fields = [str((row or {}).get("field") or "") for row in deltas if str((row or {}).get("field") or "").strip()]
    applied_rules = [str(x or "").strip() for x in list(effective_policy.get("adjustments") or []) if str(x or "").strip()]
    frame_labels = [
        str(adjustment_inputs.get("playbook") or "").strip(),
        str(adjustment_inputs.get("monitor_guidance") or "").strip(),
        str(adjustment_inputs.get("risk_tone") or "").strip(),
        str(adjustment_inputs.get("trade_aggressiveness") or "").strip(),
    ]
    frame_labels = [x for x in frame_labels if x]
    if deltas:
        if frame_labels:
            summary = f"{' + '.join(frame_labels)} adjusted {', '.join(changed_fields[:4])}"
        else:
            summary = f"strategy frame adjusted {', '.join(changed_fields[:4])}"
        reasoning = (
            f"Monitor used an effective policy derived from the commander-confirmed baseline after "
            f"strategy-frame adjustment. Changed fields: {', '.join(changed_fields[:6])}."
        )
        effective_policy_source = "monitor_frame_adjusted"
        effective_policy_source_chain = [
            str(received_policy_source or "monitor_received_policy"),
            "strategy_frame_adjustment",
            "monitor_effective_policy",
        ]
    else:
        summary = "Monitor used the received policy without strategy-frame threshold changes."
        reasoning = "Monitor used the received baseline policy directly because strategy-frame adjustments did not change threshold fields."
        effective_policy_source = "monitor_received_policy"
        effective_policy_source_chain = [
            str(received_policy_source or "monitor_received_policy"),
            "monitor_effective_policy",
        ]
    return {
        "received_policy": dict(received_policy),
        "effective_policy": dict(effective_policy),
        "received_policy_source": str(received_policy_source or ""),
        "effective_policy_source": effective_policy_source,
        "effective_policy_source_chain": [str(x) for x in effective_policy_source_chain if str(x or "").strip()],
        "policy_adjustments": {
            "inputs": adjustment_inputs,
            "applied_rules": applied_rules,
            "changed_fields": changed_fields,
        },
        "policy_adjustment_summary": summary,
        "policy_adjustment_reasoning": reasoning,
        "effective_policy_deltas": deltas,
    }


def resolve_monitor_entry_scoring_config(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    monitor_policy = applied_policy.get("monitor") if isinstance(applied_policy.get("monitor"), dict) else {}
    entry_policy = monitor_policy.get("entry") if isinstance(monitor_policy.get("entry"), dict) else {}
    scoring_policy = entry_policy.get("scoring") if isinstance(entry_policy.get("scoring"), dict) else {}
    if isinstance(scoring_policy, dict) and scoring_policy:
        out = dict(scoring_policy)
        if out.get("entry_threshold") in (None, "") and out.get("threshold") not in (None, ""):
            out["entry_threshold"] = out.get("threshold")
        out.setdefault("policy_source", str(scoring_policy.get("policy_source") or "commander_applied_policy"))
        return out
    state_scoring = state.get("monitor_entry_scoring")
    if isinstance(state_scoring, dict) and state_scoring:
        out = dict(state_scoring)
        out.setdefault("policy_source", str(state_scoring.get("policy_source") or "state_fallback"))
        return out
    policy_scoring = policy.get("monitor_entry_scoring") if isinstance(policy.get("monitor_entry_scoring"), dict) else {}
    if isinstance(policy_scoring, dict) and policy_scoring:
        out = dict(policy_scoring)
        if out.get("entry_threshold") in (None, "") and out.get("threshold") not in (None, ""):
            out["entry_threshold"] = out.get("threshold")
        out.setdefault("policy_source", str(policy_scoring.get("policy_source") or "policy_fallback"))
        return out
    return {}
