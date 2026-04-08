from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "-":
        return ""
    return text


def _first_text(candidates: Iterable[Tuple[Any, str]]) -> Tuple[str, str]:
    for value, source in candidates:
        text = _clean_text(value)
        if text:
            return text, str(source or "").strip()
    return "", ""


def narrative_axis_policy() -> Dict[str, Any]:
    return {
        "entry_primary_for": ["BUY", "WAIT", "NOOP", "NO_TRADE"],
        "exit_primary_for": ["SELL", "EXIT"],
        "mixed_only_for_ambiguous_cases": True,
        "runtime_semantics_unchanged": True,
    }


def build_narrative_explanation(
    *,
    action: Any = "",
    decision_outcome: Any = "",
    final_outcome: Any = "",
    key_reason: Any = "",
    no_trade_reason_summary: Any = "",
    dominant_blocker: Any = "",
    distance_to_ready: Any = "",
    exit_reason: Any = "",
    exit_monitor_reason: Any = "",
    decision_rationale: Any = "",
    decision_reason: Any = "",
    entry_reason: Any = "",
) -> Dict[str, Any]:
    action_upper = _clean_text(action).upper()
    outcome_upper = _clean_text(decision_outcome).upper()
    final_outcome_text = _clean_text(final_outcome)
    key_reason_text = _clean_text(key_reason)
    no_trade_reason_text = _clean_text(no_trade_reason_summary)
    dominant_blocker_text = _clean_text(dominant_blocker)
    distance_text = _clean_text(distance_to_ready)
    exit_like = action_upper == "SELL" or outcome_upper in {"SELL", "EXIT"}
    entry_like = action_upper == "BUY" or outcome_upper in {"BUY", "WAIT", "NOOP"} or bool(no_trade_reason_text or dominant_blocker_text)

    entry_text, entry_source = _first_text(
        [
            (entry_reason, "entry_reason"),
            (no_trade_reason_summary if not exit_like else "", "no_trade_reason_summary"),
            (decision_rationale if action_upper == "BUY" else "", "decision_rationale"),
            (decision_reason if action_upper == "BUY" else "", "decision_reason"),
            (key_reason if not exit_like else "", "key_reason"),
            (dominant_blocker, "dominant_blocker"),
            (final_outcome if not exit_like else "", "final_outcome"),
        ]
    )
    exit_text, exit_source = _first_text(
        [
            (exit_reason, "exit_reason"),
            (exit_monitor_reason, "exit_monitor_reason"),
            (decision_reason if action_upper == "SELL" else "", "decision_reason"),
            (decision_rationale if action_upper == "SELL" else "", "decision_rationale"),
            (key_reason if (exit_like or not entry_like) else "", "key_reason"),
            (final_outcome if (exit_like or not entry_like) else "", "final_outcome"),
        ]
    )

    axis = "unknown"
    mixed_reason = ""
    if action_upper == "SELL" or outcome_upper in {"SELL", "EXIT"}:
        axis = "exit"
    elif action_upper == "BUY" or outcome_upper in {"BUY", "WAIT", "NOOP"} or no_trade_reason_text or dominant_blocker_text:
        axis = "entry"
    elif entry_text and exit_text:
        axis = "mixed"
        mixed_reason = "both_entry_and_exit_context_present_without_strong_action_signal"
    elif exit_text:
        axis = "exit"
    elif entry_text:
        axis = "entry"

    primary_explanation = ""
    primary_source = ""
    narrative_order: List[str] = []
    explanation_mode = "unknown"
    why_not_buy_summary = "-"
    why_exit_summary = "-"
    dominant_blocker_display = dominant_blocker_text or "-"
    entry_context_blocker = dominant_blocker_text or "-"
    narrative_consistency_flag = True

    if axis == "exit":
        primary_explanation, primary_source = _first_text(
            [
                (exit_text, exit_source or "exit_reason"),
                (final_outcome_text, "final_outcome"),
                (key_reason_text, "key_reason"),
            ]
        )
        why_exit_summary = exit_text or primary_explanation or "-"
        why_not_buy_summary = "-"
        dominant_blocker_display = "-"
        narrative_order = ["exit"]
        if dominant_blocker_text:
            narrative_order.append("entry_context")
        explanation_mode = "exit_first"
        narrative_consistency_flag = bool(primary_explanation)
    elif axis == "entry":
        primary_explanation, primary_source = _first_text(
            [
                (entry_text, entry_source or "entry_reason"),
                (dominant_blocker_text, "dominant_blocker"),
                (final_outcome_text, "final_outcome"),
                (key_reason_text, "key_reason"),
            ]
        )
        why_not_buy_summary = no_trade_reason_text or entry_text or primary_explanation or "-"
        why_exit_summary = "-"
        narrative_order = ["entry"]
        if exit_text:
            narrative_order.append("exit_context")
        explanation_mode = "entry_first"
        narrative_consistency_flag = bool(primary_explanation)
    elif axis == "mixed":
        primary_explanation, primary_source = _first_text(
            [
                (exit_text, exit_source or "exit_reason"),
                (entry_text, entry_source or "entry_reason"),
                (final_outcome_text, "final_outcome"),
                (key_reason_text, "key_reason"),
            ]
        )
        why_not_buy_summary = no_trade_reason_text or entry_text or "-"
        why_exit_summary = exit_text or "-"
        dominant_blocker_display = dominant_blocker_text or "-"
        narrative_order = ["exit", "entry"] if exit_text else ["entry", "exit"]
        explanation_mode = "mixed"
        narrative_consistency_flag = bool(primary_explanation and (entry_text or exit_text))
    else:
        primary_explanation, primary_source = _first_text(
            [
                (final_outcome_text, "final_outcome"),
                (key_reason_text, "key_reason"),
                (entry_text, entry_source or "entry_reason"),
                (exit_text, exit_source or "exit_reason"),
            ]
        )
        why_not_buy_summary = "-"
        why_exit_summary = "-"
        dominant_blocker_display = "-"
        narrative_order = ["unknown"]
        explanation_mode = "unknown"
        narrative_consistency_flag = bool(primary_explanation)

    return {
        "decision_axis": axis,
        "primary_explanation": primary_explanation or "-",
        "entry_narrative": entry_text or "-",
        "exit_narrative": exit_text or "-",
        "why_not_buy_summary": why_not_buy_summary or "-",
        "why_exit_summary": why_exit_summary or "-",
        "dominant_blocker": dominant_blocker_text or "-",
        "dominant_blocker_display": dominant_blocker_display or "-",
        "entry_context_blocker": entry_context_blocker or "-",
        "distance_to_ready": distance_text or "-",
        "narrative_order": list(narrative_order),
        "narrative_order_text": " -> ".join(narrative_order) if narrative_order else "-",
        "narrative_consistency_flag": bool(narrative_consistency_flag),
        "explanation_source": primary_source or "-",
        "explanation_mode": explanation_mode,
        "mixed_reason": mixed_reason or "-",
    }
