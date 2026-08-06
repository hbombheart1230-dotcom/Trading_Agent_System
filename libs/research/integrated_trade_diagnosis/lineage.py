from __future__ import annotations

from typing import Any, Mapping


def _symbol(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(
            value.get("symbol")
            or value.get("selected_symbol")
            or value.get("candidate_symbol")
            or ""
        )
    return str(value or "")


def build_lineage(model: Mapping[str, Any]) -> dict[str, Any]:
    selection = model.get("selection")
    selection = selection if isinstance(selection, Mapping) else {}
    post = selection.get("post_strategist_top10") or []
    post_top1 = post[0] if post and isinstance(post[0], Mapping) else {}
    commander = selection.get("commander_final")
    commander = commander if isinstance(commander, Mapping) else {}
    stages = {
        "scanner_intrinsic_top1": _symbol(selection.get("raw_scanner_top1")),
        "post_strategist_top1": _symbol(post_top1),
        "selected_candidate": _symbol(selection.get("selected_symbol")),
        "commander_candidate": _symbol(commander),
        "executed_symbol": _symbol(model.get("symbol")),
    }
    known = [value for value in stages.values() if value]
    if not known:
        confidence = "UNKNOWN"
    elif selection.get("q9_decision_id") and stages["executed_symbol"]:
        confidence = "EXACT"
    elif stages["executed_symbol"] and len(known) >= 2:
        confidence = "TIME_MATCHED"
    else:
        confidence = "INFERRED"
    transitions = []
    previous_name = previous_symbol = ""
    for name, symbol in stages.items():
        if previous_symbol and symbol and previous_symbol != symbol:
            transitions.append(
                {
                    "from_stage": previous_name,
                    "to_stage": name,
                    "from_symbol": previous_symbol,
                    "to_symbol": symbol,
                    "reason": transition_reason(previous_name, name, selection),
                }
            )
        if symbol:
            previous_name, previous_symbol = name, symbol
    return {
        **stages,
        "confidence": confidence,
        "consistent": len(set(known)) <= 1 if known else None,
        "transitions": transitions,
    }


def transition_reason(
    from_stage: str,
    to_stage: str,
    selection: Mapping[str, Any],
) -> str:
    if from_stage == "scanner_intrinsic_top1" and to_stage == "post_strategist_top1":
        return "STRATEGY_CONTEXT_CHANGED"
    if to_stage == "selected_candidate":
        return "CANDIDATE_FILTERED"
    if to_stage == "commander_candidate":
        return "MONITOR_CANDIDATE_CHANGED"
    if to_stage == "executed_symbol":
        return "EXECUTION_OR_MAPPING_DIFFERENCE"
    if selection.get("selection_mismatch"):
        return "SELECTION_MISMATCH"
    return "UNCLASSIFIED_STAGE_CHANGE"
