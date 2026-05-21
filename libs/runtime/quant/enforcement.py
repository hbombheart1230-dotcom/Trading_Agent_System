from __future__ import annotations

import os
from typing import Any, Dict, Mapping


DEFAULT_ENTRY_ENFORCED_BLOCKERS = (
    "cost_edge_fail",
    "same_symbol_position_open",
    "directional_edge_evidence_missing",
    "volume_confirmation_missing",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mode(value: Any = None) -> str:
    raw = _text(value or os.getenv("QUANT_ENTRY_DECISION_MODE") or "enforce").lower()
    if raw in {"off", "disabled", "observe", "observation", "observation_only"}:
        return "observe"
    if raw in {"advisory", "warn", "warning"}:
        return "advisory"
    if raw in {"enforce", "hard", "hard_veto"}:
        return "enforce"
    return "enforce"


def _csv_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {_text(item) for item in value if _text(item)}
    text = _text(value)
    if not text:
        return set()
    return {_text(item) for item in text.split(",") if _text(item)}


def _enforced_blockers(value: Any = None) -> set[str]:
    configured = _csv_set(value or os.getenv("QUANT_ENTRY_ENFORCED_BLOCKERS"))
    return configured or set(DEFAULT_ENTRY_ENFORCED_BLOCKERS)


def build_entry_quant_enforcement(
    entry_quant_decision: Mapping[str, Any] | None,
    *,
    mode: Any = None,
    enforced_blockers: Any = None,
) -> Dict[str, Any]:
    decision = dict(entry_quant_decision or {}) if isinstance(entry_quant_decision, Mapping) else {}
    active_mode = _mode(mode)
    configured_blockers = _enforced_blockers(enforced_blockers)
    blockers = [_text(item) for item in list(decision.get("blockers") or []) if _text(item)]
    matched = [item for item in blockers if item in configured_blockers]
    enforce = bool(active_mode == "enforce" and matched)
    return {
        "schema_version": "quant_entry_enforcement.v1",
        "mode": active_mode,
        "enforced_blockers": sorted(configured_blockers),
        "matched_blockers": matched,
        "blocked": enforce,
        "reason": f"quant_entry_block:{matched[0]}" if enforce else "",
        "source_decision": _text(decision.get("decision")),
        "behavior_effect": "entry_guard_enforced" if enforce else "observation_only",
    }

