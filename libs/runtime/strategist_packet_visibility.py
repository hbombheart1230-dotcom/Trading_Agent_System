from __future__ import annotations

from typing import Any, Dict, List


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def summarize_read_model_facts(read_model_facts: Any) -> Dict[str, Any]:
    facts = _dict(read_model_facts)
    recent_trades = _list(facts.get("recent_trades"))
    symbol_patterns = _dict(facts.get("symbol_patterns"))
    daily_summary = _dict(facts.get("daily_summary"))
    return {
        "present": bool(recent_trades or symbol_patterns or daily_summary),
        "recent_trade_count": len(recent_trades),
        "symbol_pattern_count": len(symbol_patterns),
        "symbols": [_text(sym, max_len=24) for sym in list(symbol_patterns.keys())[:5] if _text(sym, max_len=24)],
        "daily_summary_present": bool(daily_summary),
    }


def build_strategist_memory_packet_visibility(
    *,
    state: Dict[str, Any],
    strategist_output: Dict[str, Any],
) -> Dict[str, Any]:
    def _merge_packet(state_key: str, output_key: str) -> Dict[str, Any]:
        return {
            **_dict(state.get(state_key)),
            **_dict(strategist_output.get(output_key)),
        }

    read_model_facts = _dict(
        state.get("read_model_facts_summary")
        or strategist_output.get("read_model_facts_summary")
    )
    recent_strategy_feedback = _dict(
        state.get("recent_strategy_feedback")
        or strategist_output.get("recent_strategy_feedback")
    )
    reporter_feedback_packet = _merge_packet("reporter_feedback_packet", "reporter_feedback_packet")
    strategy_memory = {
        **_dict(state.get("strategy_memory")),
        **_dict(strategist_output.get("strategy_memory") or strategist_output.get("strategy_memory_snapshot")),
    }
    commander_refresh_context = _dict(
        strategist_output.get("commander_refresh_context")
        or _dict(strategist_output.get("commander_context_ref")).get("strategist_refresh_context")
    )
    commander_open_position_refresh_context = _dict(
        strategist_output.get("commander_open_position_refresh_context")
        or _dict(strategist_output.get("commander_context_ref")).get("open_position_refresh_context")
    )
    merged_refresh_context = {
        **commander_refresh_context,
        **commander_open_position_refresh_context,
    }
    selected_symbol_memory = _dict(
        strategist_output.get("selected_symbol_memory")
        or commander_open_position_refresh_context.get("selected_symbol_memory")
        or commander_refresh_context.get("selected_symbol_memory")
    )
    selected_symbol = _text(
        commander_open_position_refresh_context.get("selected_symbol")
        or commander_refresh_context.get("selected_symbol")
        or selected_symbol_memory.get("symbol"),
        max_len=24,
    )
    return {
        "read_model_facts": {
            "present": bool(read_model_facts.get("present")),
            "recent_trade_count": _safe_int(read_model_facts.get("recent_trade_count")),
            "symbol_pattern_count": _safe_int(read_model_facts.get("symbol_pattern_count")),
            "symbols": [_text(sym, max_len=24) for sym in _list(read_model_facts.get("symbols"))[:5] if _text(sym, max_len=24)],
            "daily_summary_present": bool(read_model_facts.get("daily_summary_present")),
        },
        "recent_strategy_feedback": {
            "present": bool(recent_strategy_feedback),
            "status": _text(
                recent_strategy_feedback.get("status")
                or ("ok" if _safe_int(recent_strategy_feedback.get("feedback_window_size")) > 0 else "empty"),
                max_len=40,
            ),
            "feedback_window_size": _safe_int(recent_strategy_feedback.get("feedback_window_size")),
            "strength_count": len(_list(recent_strategy_feedback.get("top_recent_strengths"))),
            "weakness_count": len(_list(recent_strategy_feedback.get("top_recent_weaknesses"))),
            "suggested_report_focus_count": len(_list(recent_strategy_feedback.get("suggested_report_focus"))),
            "advisory_only": bool(recent_strategy_feedback.get("advisory_only", True)),
        },
        "reporter_feedback_packet": {
            "present": bool(reporter_feedback_packet),
            "available": bool(reporter_feedback_packet.get("available")),
            "status": _text(reporter_feedback_packet.get("status"), max_len=40),
            "source_available": bool(reporter_feedback_packet.get("source_available")),
            "consumed": bool(reporter_feedback_packet.get("consumed")),
            "feedback_gate_reason": _text(reporter_feedback_packet.get("feedback_gate_reason"), max_len=40),
            "confidence": _text(reporter_feedback_packet.get("confidence"), max_len=24),
            "recommendation_count": len(_list(reporter_feedback_packet.get("recommendation"))),
        },
        "strategy_memory": {
            "present": bool(strategy_memory),
            "status": _text(strategy_memory.get("status"), max_len=40),
            "requested_day": _text(strategy_memory.get("requested_day"), max_len=16),
            "resolved_day": _text(strategy_memory.get("resolved_day") or strategy_memory.get("day"), max_len=16),
            "best_playbook_count": len(_list(strategy_memory.get("best_playbooks"))),
            "worst_playbook_count": len(_list(strategy_memory.get("worst_playbooks"))),
            "recent_failure_count": len(_list(strategy_memory.get("recent_failures"))),
            "recent_success_pattern_count": len(_list(strategy_memory.get("recent_success_patterns"))),
            "reporter_analysis_digest_present": bool(_dict(strategy_memory.get("reporter_analysis_digest"))),
        },
        "selected_symbol_memory": {
            "present": bool(selected_symbol_memory),
            "empty_state": bool(selected_symbol) and not bool(selected_symbol_memory),
            "symbol": selected_symbol,
            "trade_count": _safe_int(selected_symbol_memory.get("trade_count")),
            "closed_trade_count": _safe_int(selected_symbol_memory.get("closed_trade_count")),
            "win_rate": _safe_float(selected_symbol_memory.get("win_rate")),
            "dominant_playbook": _text(selected_symbol_memory.get("dominant_playbook"), max_len=40),
            "dominant_monitor_blocker": _text(selected_symbol_memory.get("dominant_monitor_blocker"), max_len=60),
        },
        "commander_refresh_context": {
            "present": bool(commander_refresh_context or commander_open_position_refresh_context),
            "requested": bool(
                merged_refresh_context.get("requested")
                if merged_refresh_context.get("requested") is not None
                else strategist_output.get("commander_refresh_requested")
            ),
            "reason": _text(
                merged_refresh_context.get("reason")
                or strategist_output.get("commander_refresh_reason"),
                max_len=80,
            ),
            "refresh_scope": _text(merged_refresh_context.get("refresh_scope"), max_len=60),
            "selected_symbol": selected_symbol,
            "hold_repeat_count_max": _safe_int(merged_refresh_context.get("hold_repeat_count_max")),
            "selected_hold_repeat_count": _safe_int(merged_refresh_context.get("selected_hold_repeat_count")),
            "requires_policy_delta": bool(
                merged_refresh_context.get("requires_policy_delta")
                if merged_refresh_context.get("requires_policy_delta") is not None
                else strategist_output.get("commander_refresh_requested")
            ),
            "carry_state": _text(merged_refresh_context.get("carry_state"), max_len=40),
            "carry_risk_bias": _text(merged_refresh_context.get("carry_risk_bias"), max_len=40),
            "carry_risk_reason": _text(merged_refresh_context.get("carry_risk_reason"), max_len=80),
            "session_open_recovery_evaluated": bool(
                _dict(merged_refresh_context.get("session_open_recovery_assessment")).get("evaluated")
            ),
        },
    }
