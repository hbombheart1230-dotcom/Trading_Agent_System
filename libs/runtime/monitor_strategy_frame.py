from __future__ import annotations

from typing import Any, Dict, List

from libs.core.symbols import normalize_symbol

from libs.runtime.monitor_exit.price_resolution import position_mark_price, resolve_price
from libs.strategies.contracts import coerce_strategist_output


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    try:
        num = float(value)
    except Exception:
        num = low
    return max(low, min(high, num))


def extract_monitor_strategy_frame(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output_raw = state.get("strategist_output")
    strategist_output = (
        coerce_strategist_output(strategist_output_raw)
        if isinstance(strategist_output_raw, dict)
        else {}
    )
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    if not has_strategy_policy_content(strategy_policy) and isinstance(state.get("strategy_policy"), dict):
        strategy_policy = dict(state.get("strategy_policy") or {})
    market_policy = (
        dict(strategy_policy.get("market_policy") or {})
        if isinstance(strategy_policy.get("market_policy"), dict)
        else {}
    )
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    commander_context = (
        dict(strategy_policy.get("commander_context") or {})
        if isinstance(strategy_policy.get("commander_context"), dict)
        else {}
    )
    strategist_plan = (
        dict(strategy_policy.get("strategist_plan") or {})
        if isinstance(strategy_policy.get("strategist_plan"), dict)
        else {}
    )
    policy_provenance = (
        dict(strategy_policy.get("provenance") or {})
        if isinstance(strategy_policy.get("provenance"), dict)
        else {}
    )
    commander_horizon_policy = {}
    for candidate in (
        state.get("commander_horizon_policy"),
        strategy_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("horizon_policy"),
        commander_context.get("commander_horizon_policy"),
        strategist_output.get("commander_horizon_policy"),
    ):
        if isinstance(candidate, dict) and candidate:
            commander_horizon_policy = dict(candidate)
            break
    return {
        "playbook": str(
            state.get("playbook")
            or market_policy.get("playbook")
            or strategist_plan.get("selected_playbook")
            or strategist_output.get("playbook")
            or ""
        ).strip().lower(),
        "monitor_guidance": str(
            state.get("monitor_guidance")
            or market_policy.get("monitor_guidance")
            or strategist_output.get("monitor_guidance")
            or ""
        ).strip().lower(),
        "risk_tone": str(
            state.get("risk_tone")
            or market_policy.get("risk_tone")
            or strategist_output.get("risk_tone")
            or ""
        ).strip().lower(),
        "trade_aggressiveness": str(
            state.get("trade_aggressiveness")
            or market_policy.get("trade_aggressiveness")
            or strategist_output.get("trade_aggressiveness")
            or ""
        ).strip().lower(),
        "commander_context": commander_context,
        "commander_horizon_policy": commander_horizon_policy,
        "strategy_horizon": str(commander_horizon_policy.get("strategy_horizon") or strategy_monitor_policy.get("strategy_horizon") or strategist_output.get("strategy_horizon") or "").strip(),
        "source_strategy_horizon": str(commander_horizon_policy.get("source_strategy_horizon") or "").strip(),
        "strategist_plan": strategist_plan,
        "policy_provenance": policy_provenance,
    }


def position_strategy_frame_for_symbol(
    state: Dict[str, Any],
    symbol: str,
    base_frame: Dict[str, Any],
) -> Dict[str, Any]:
    """Pin exit controls to the strategy frame captured when the position opened."""
    sym = normalize_symbol(symbol)
    if not sym:
        return dict(base_frame or {})
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    position_context = (
        persisted.get("position_strategy_context")
        if isinstance(persisted.get("position_strategy_context"), dict)
        else {}
    )
    row = position_context.get(sym) if isinstance(position_context.get(sym), dict) else {}
    output = row.get("output") if isinstance(row.get("output"), dict) else {}
    if not output:
        return dict(base_frame or {})
    pinned_state = dict(state)
    pinned_state["strategist_output"] = dict(output)
    for key in ("playbook", "monitor_guidance", "risk_tone", "trade_aggressiveness"):
        pinned_state.pop(key, None)
    pinned = extract_monitor_strategy_frame(pinned_state)
    out = dict(base_frame or {})
    for key in (
        "playbook",
        "monitor_guidance",
        "risk_tone",
        "trade_aggressiveness",
        "commander_context",
        "commander_horizon_policy",
        "strategy_horizon",
        "source_strategy_horizon",
        "strategist_plan",
        "policy_provenance",
    ):
        value = pinned.get(key)
        if value not in (None, "", {}, []):
            out[key] = value
    if isinstance(output.get("commander_horizon_policy"), dict) and output.get("commander_horizon_policy"):
        out["commander_horizon_policy"] = dict(output.get("commander_horizon_policy") or {})
    out["position_strategy_context_applied"] = True
    out["position_strategy_context_symbol"] = sym
    out["position_strategy_context_source"] = str(row.get("source") or "position_strategy_context")
    out["position_strategy_context_generated_epoch"] = _to_int(row.get("generated_epoch"))
    out["position_strategy_context_output"] = dict(output)
    return out


def build_monitor_policy_trace(
    *,
    commander_context: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    strategist_plan: Dict[str, Any],
    policy_provenance: Dict[str, Any],
    entry_info: Dict[str, Any],
    exit_info: Dict[str, Any],
    current_reason: str,
) -> Dict[str, Any]:
    consumed_fields: List[str] = []
    for key in (
        "monitor_mission",
        "flow_instruction",
        "command_intent",
        "risk_mode",
        "no_trade_reason_code",
        "llm_policy",
        "source_priority",
        "entry_control",
        "commander_entry_control",
    ):
        value = commander_context.get(key)
        if value not in (None, "", [], {}):
            consumed_fields.append(key)
    commander_context_consumed = bool(consumed_fields)

    strategy_fields: List[str] = []
    for key in ("selected_playbook", "entry_plan", "exit_plan", "symbol_constraints", "strategy_summary"):
        value = strategist_plan.get(key)
        if value not in (None, "", [], {}):
            strategy_fields.append(key)

    flow_instruction = str(commander_context.get("flow_instruction") or "").strip()
    no_trade_reason_code = str(commander_context.get("no_trade_reason_code") or "").strip()
    monitor_mission = str(commander_context.get("monitor_mission") or "").strip()
    entry_plan = dict(strategist_plan.get("entry_plan") or {})
    exit_plan = dict(strategist_plan.get("exit_plan") or {})

    def _policy_meta_value(key: str, default: Any = "") -> Any:
        commander_value = commander_context.get(key)
        if commander_value not in (None, "", [], {}):
            return commander_value
        monitor_value = monitor_policy.get(key)
        if monitor_value not in (None, "", [], {}):
            return monitor_value
        return default

    entry_blockers = list(
        dict.fromkeys(
            [
                no_trade_reason_code,
                str(entry_info.get("guard_reason") or "").strip(),
                str(entry_info.get("reason") or "").strip(),
                *[str(x or "").strip() for x in list(entry_info.get("failed_checks") or []) if str(x or "").strip()],
            ]
        )
    )
    entry_blockers = [item for item in entry_blockers if item][:8]

    summary_parts: List[str] = []
    if monitor_mission:
        summary_parts.append(f"mission={monitor_mission}")
    if flow_instruction:
        summary_parts.append(f"flow={flow_instruction}")
    if str(strategist_plan.get("selected_playbook") or "").strip():
        summary_parts.append(f"playbook={str(strategist_plan.get('selected_playbook') or '').strip()}")
    if current_reason:
        summary_parts.append(f"reason={current_reason}")

    return {
        "commander_context_consumed": commander_context_consumed,
        "consumed_fields": consumed_fields + strategy_fields,
        "flow_instruction_applied": bool(flow_instruction),
        "no_trade_reason_applied": bool(no_trade_reason_code),
        "shadow_used": bool(
            commander_context.get("shadow_used")
            if commander_context.get("shadow_used") is not None
            else policy_provenance.get("shadow_used")
        ),
        "strategist_fallback_used": bool(
            commander_context.get("strategist_fallback_used")
            if commander_context.get("strategist_fallback_used") is not None
            else policy_provenance.get("strategist_fallback_used")
        ),
        "policy_ref": {
            "monitor_mission": monitor_mission,
            "flow_instruction": flow_instruction,
            "command_intent": str(commander_context.get("command_intent") or ""),
            "risk_mode": str(commander_context.get("risk_mode") or ""),
            "no_trade_reason_code": no_trade_reason_code,
            "llm_policy": str(commander_context.get("llm_policy") or ""),
            "source_priority": list(commander_context.get("source_priority") or []),
            "entry_control": dict(commander_context.get("entry_control") or {})
            if isinstance(commander_context.get("entry_control"), dict)
            else {},
            "applied_policy": dict(commander_context.get("applied_policy") or {})
            if isinstance(commander_context.get("applied_policy"), dict)
            else dict(monitor_policy.get("applied_policy") or {})
            if isinstance(monitor_policy.get("applied_policy"), dict)
            else {},
            "policy_source": str(_policy_meta_value("policy_source", "")),
            "policy_validation_status": str(_policy_meta_value("policy_validation_status", "")),
            "policy_fallback_used": bool(_policy_meta_value("policy_fallback_used", False)),
            "policy_fallback_reason": str(_policy_meta_value("policy_fallback_reason", "")),
            "policy_partial_normalized": bool(_policy_meta_value("policy_partial_normalized", False)),
            "policy_default_filled_fields": list(_policy_meta_value("policy_default_filled_fields", [])),
            "policy_validation_missing_fields": list(_policy_meta_value("policy_validation_missing_fields", [])),
            "policy_validation_invalid_fields": list(_policy_meta_value("policy_validation_invalid_fields", [])),
            "override_reason": str(_policy_meta_value("override_reason", "")),
            "applied_policy_source_chain": list(_policy_meta_value("applied_policy_source_chain", [])),
            "selected_playbook": str(strategist_plan.get("selected_playbook") or ""),
            "entry_plan": entry_plan,
            "exit_plan": exit_plan,
            "symbol_constraints": dict(strategist_plan.get("symbol_constraints") or {}),
            "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
        },
        "entry_check_summary": " | ".join(summary_parts) if summary_parts else str(current_reason or entry_info.get("reason") or ""),
        "entry_blockers": entry_blockers,
        "timing_assessment": {
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_reason": str(entry_info.get("reason") or ""),
            "entry_plan": entry_plan,
            "monitor_mission": monitor_mission,
            "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
        },
        "exit_trigger_basis": {
            "exit_reason": str(exit_info.get("reason") or ""),
            "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
            "final_exit_thresholds": dict(exit_info.get("final_exit_thresholds") or {}),
            "exit_threshold_source": str(exit_info.get("exit_threshold_source") or ""),
            "hold_block_reason": str(exit_info.get("hold_block_reason") or ""),
            "hold_limit_sec": exit_info.get("hold_limit_sec"),
            "max_hold_reached": bool(exit_info.get("max_hold_reached")),
            "time_stop_reached": bool(exit_info.get("time_stop_reached")),
            "time_limit_reached": bool(exit_info.get("time_limit_reached")),
            "time_limit_reason": str(exit_info.get("time_limit_reason") or ""),
            "time_limit_reassessment_required": bool(exit_info.get("time_limit_reassessment_required")),
            "time_limit_reassessment_blocked": bool(exit_info.get("time_limit_reassessment_blocked")),
            "time_limit_reassessment_blocked_reason": str(
                exit_info.get("time_limit_reassessment_blocked_reason") or ""
            ),
            "max_runup_pct": exit_info.get("max_runup_pct"),
            "peak_drawdown_from_peak": exit_info.get("peak_drawdown_from_peak"),
            "peak_drawdown_armed": bool(exit_info.get("peak_drawdown_armed")),
            "peak_drawdown_mode": str(exit_info.get("peak_drawdown_mode") or ""),
            "peak_drawdown_blocked": bool(exit_info.get("peak_drawdown_blocked")),
            "peak_drawdown_block_reason": str(exit_info.get("peak_drawdown_block_reason") or ""),
            "peak_drawdown_profit_floor_required_pct": exit_info.get("peak_drawdown_profit_floor_required_pct"),
            "peak_drawdown_profit_floor_met": bool(exit_info.get("peak_drawdown_profit_floor_met")),
            "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
            "peak_drawdown_source": str(exit_info.get("peak_drawdown_source") or ""),
            "exit_trigger_metric_name": str(exit_info.get("exit_trigger_metric_name") or ""),
            "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
            "exit_trigger_metric_source": str(exit_info.get("exit_trigger_metric_source") or ""),
            "gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
            "technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
            "stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
            "stop_pnl_ratio_source": str(exit_info.get("stop_pnl_ratio_source") or ""),
            "hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
            "hard_stop_pnl_ratio_source": str(exit_info.get("hard_stop_pnl_ratio_source") or ""),
            "cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
            "cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
            "cost_drag_pressure_reason": str(exit_info.get("cost_drag_pressure_reason") or ""),
            "stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
            "stop_loss_cost_drag_blocked_reason": str(exit_info.get("stop_loss_cost_drag_blocked_reason") or ""),
            "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
            "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
            "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
            "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
            "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
            "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
            "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
            "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
            "protective_exit_hard_invalidation_reason": str(
                exit_info.get("protective_exit_hard_invalidation_reason") or ""
            ),
            "exit_plan": exit_plan,
            "monitor_mission": monitor_mission,
        },
    }


def has_strategy_policy_content(strategy_policy: Any) -> bool:
    if not isinstance(strategy_policy, dict):
        return False
    for key in (
        "market_policy",
        "scanner_policy",
        "monitor_policy",
        "decision_policy",
        "commander_context",
        "strategist_plan",
        "provenance",
    ):
        value = strategy_policy.get(key)
        if isinstance(value, dict) and value:
            return True
    return False

def apply_monitor_strategy_frame(
    *,
    min_hold_sec: int,
    sell_cooldown_sec: int,
    confirm_ticks: int,
    frame: Dict[str, str],
) -> Dict[str, Any]:
    min_hold = max(0, int(min_hold_sec))
    cooldown = max(0, int(sell_cooldown_sec))
    confirm = max(1, int(confirm_ticks))
    adjustments: list[str] = []

    playbook = str(frame.get("playbook") or "").strip().lower()
    mode = str(frame.get("monitor_guidance") or "").strip().lower()
    horizon_policy = (
        dict(frame.get("commander_horizon_policy") or {})
        if isinstance(frame.get("commander_horizon_policy"), dict)
        else {}
    )
    behavior_translation = (
        dict(horizon_policy.get("behavior_translation") or {})
        if isinstance(horizon_policy.get("behavior_translation"), dict)
        else {}
    )
    strategy_horizon = str(
        horizon_policy.get("strategy_horizon")
        or frame.get("strategy_horizon")
        or behavior_translation.get("strategy_horizon")
        or ""
    ).strip().lower()
    if not mode:
        if playbook == "breakout":
            mode = "hold_through_noise"
            adjustments.append("playbook:breakout->monitor_guidance")
        elif playbook == "defensive":
            mode = "defensive_exit"
            adjustments.append("playbook:defensive->monitor_guidance")
        elif playbook in ("pullback", "reversal"):
            mode = "quick_take_profit"
            adjustments.append(f"playbook:{playbook}->monitor_guidance")

    if mode == "hold_through_noise":
        min_hold += 300
        confirm += 1
        cooldown += 60
        adjustments.append("monitor_guidance:hold_through_noise")
    elif mode == "defensive_exit":
        min_hold = max(0, min_hold - 120)
        confirm = max(1, confirm - 1)
        adjustments.append("monitor_guidance:defensive_exit")
    elif mode == "quick_take_profit":
        min_hold = max(0, min_hold - 300)
        confirm = 1
        cooldown = max(60, min(cooldown, 180))
        adjustments.append("monitor_guidance:quick_take_profit")

    tone = str(frame.get("risk_tone") or "").strip().lower()
    if tone == "conservative":
        min_hold += 120
        confirm += 1
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        min_hold = max(0, min_hold - 60)
        confirm = max(1, confirm - 1)
        adjustments.append("risk_tone:aggressive")

    aggr = str(frame.get("trade_aggressiveness") or "").strip().lower()
    if aggr == "low":
        confirm = max(confirm, 3)
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        confirm = max(1, confirm - 1)
        adjustments.append("trade_aggressiveness:high")

    if bool(behavior_translation.get("applied")) or strategy_horizon:
        if strategy_horizon == "scalp":
            min_hold = max(0, min(min_hold, 180))
            confirm = 1
            cooldown = max(30, min(cooldown, 120))
            adjustments.append("strategy_horizon:scalp_hold_controls")
        elif strategy_horizon == "intraday":
            confirm = max(1, min(confirm, 3))
            adjustments.append("strategy_horizon:intraday_hold_controls")
        elif strategy_horizon in {"overnight_probe", "1_2day_swing"}:
            min_hold += 600 if strategy_horizon == "overnight_probe" else 900
            confirm = max(confirm, 2)
            cooldown += 120
            adjustments.append(f"strategy_horizon:{strategy_horizon}_hold_controls")
    if bool(frame.get("position_strategy_context_applied")):
        adjustments.append(
            "position_strategy_context_pinned:"
            + str(frame.get("position_strategy_context_symbol") or "")
        )

    return {
        "min_hold_sec": max(0, int(min_hold)),
        "sell_cooldown_sec": max(0, int(cooldown)),
        "confirm_ticks": max(1, min(6, int(confirm))),
        "playbook": playbook,
        "monitor_guidance": mode,
        "risk_tone": tone,
        "trade_aggressiveness": aggr,
        "strategy_horizon": strategy_horizon,
        "source_strategy_horizon": str(horizon_policy.get("source_strategy_horizon") or frame.get("source_strategy_horizon") or ""),
        "commander_horizon_policy": dict(horizon_policy),
        "horizon_behavior_translation": dict(behavior_translation),
        "position_strategy_context_applied": bool(frame.get("position_strategy_context_applied")),
        "position_strategy_context_symbol": str(frame.get("position_strategy_context_symbol") or ""),
        "position_strategy_context_source": str(frame.get("position_strategy_context_source") or ""),
        "position_strategy_context_generated_epoch": frame.get("position_strategy_context_generated_epoch"),
        "position_strategy_context_output": (
            dict(frame.get("position_strategy_context_output") or {})
            if isinstance(frame.get("position_strategy_context_output"), dict)
            else {}
        ),
        "adjustments": list(adjustments),
    }


def apply_exit_policy_strategy_frame(
    *,
    state: Dict[str, Any],
    exit_policy_base: Dict[str, Any],
    selected: Dict[str, Any] | None,
    position: Dict[str, Any] | None,
    frame: Dict[str, str],
) -> Dict[str, Any]:
    out = dict(exit_policy_base or {})
    adjustments: list[str] = []

    pinned_strategy_output = (
        dict(frame.get("position_strategy_context_output") or {})
        if isinstance(frame.get("position_strategy_context_output"), dict)
        else {}
    )
    position_strategy_pinned = bool(frame.get("position_strategy_context_applied")) and bool(pinned_strategy_output)
    strategist_output_raw = pinned_strategy_output if position_strategy_pinned else state.get("strategist_output")
    strategist_output = (
        coerce_strategist_output(strategist_output_raw)
        if isinstance(strategist_output_raw, dict)
        else {}
    )
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    strategist_exit_policy = {}
    if isinstance(strategy_monitor_policy.get("adaptive_exit"), dict):
        strategist_exit_policy.update(dict(strategy_monitor_policy.get("adaptive_exit") or {}))
    elif isinstance(strategy_monitor_policy.get("exit_policy"), dict):
        strategist_exit_policy.update(dict(strategy_monitor_policy.get("exit_policy") or {}))
    if isinstance(strategist_output.get("exit_policy"), dict):
        strategist_exit_policy.update(dict(strategist_output.get("exit_policy") or {}))
    if isinstance(state.get("strategist_exit_policy"), dict):
        strategist_exit_policy.update(dict(state.get("strategist_exit_policy") or {}))
    if strategist_exit_policy:
        for key in (
            "hard_stop_pct",
            "stop_loss_pct",
            "take_profit_pct",
            "partial_take_profit_pct",
            "partial_take_profit_fraction",
            "profit_ladder_levels_pct",
            "profit_ladder_fraction",
            "risk_reward_take_profit_r",
            "risk_reward_take_profit_rungs",
            "risk_reward_take_profit_fraction",
            "risk_reward_take_profit_min_pct",
            "vwap_extension_take_profit_pct",
            "vwap_extension_take_profit_min_pct",
            "resistance_take_profit_near_pct",
            "resistance_take_profit_min_pct",
            "profit_time_stop_sec",
            "profit_time_stop_min_pct",
            "profit_time_stop_peak_giveback_pct",
            "volume_exhaustion_take_profit_min_pct",
            "volume_exhaustion_volume_ratio_max",
            "volume_exhaustion_strength_max",
            "opening_gap_profit_take_min_pct",
            "opening_gap_profit_take_window_sec",
            "opening_gap_profit_take_fraction",
            "cost_aware_profit_floor_enabled",
            "round_trip_cost_floor_pct",
            "min_net_profit_buffer_pct",
            "cost_aware_profit_floor_pct",
            "max_hold_sec",
            "time_stop_sec",
            "trailing_stop_pct",
            "vol_expansion_ratio",
            "news_shock_threshold",
            "peak_drawdown_exit_pct",
            "profit_protection_activation_pct",
            "peak_drawdown_mode",
            "confirm_required_for_peak_drawdown",
            "vwap_breakdown_pct",
            "intraday_low_break_pct",
            "trend_strength_floor",
            "use_eod_flat",
            "eod_flat_cutoff_min",
            "emergency_halt",
        ):
            if strategist_exit_policy.get(key) not in (None, ""):
                out[key] = strategist_exit_policy.get(key)
        adjustments.append("strategist_exit_policy_override")

    commander_horizon_policy = {}
    for candidate in (
        state.get("commander_horizon_policy"),
        strategy_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("horizon_policy"),
        frame.get("commander_horizon_policy") if isinstance(frame, dict) else {},
    ):
        if isinstance(candidate, dict) and candidate:
            commander_horizon_policy = dict(candidate)
            break
    behavior_translation = (
        dict(commander_horizon_policy.get("behavior_translation") or {})
        if isinstance(commander_horizon_policy.get("behavior_translation"), dict)
        else {}
    )
    if not behavior_translation and isinstance(frame, dict) and isinstance(frame.get("horizon_behavior_translation"), dict):
        behavior_translation = dict(frame.get("horizon_behavior_translation") or {})

    raw_playbook = str(
        ("" if position_strategy_pinned else state.get("playbook"))
        or ((strategist_output_raw or {}).get("playbook") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()
    raw_guidance = str(
        ("" if position_strategy_pinned else state.get("monitor_guidance"))
        or ((strategist_output_raw or {}).get("monitor_guidance") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()
    raw_tone = str(
        ("" if position_strategy_pinned else state.get("risk_tone"))
        or ((strategist_output_raw or {}).get("risk_tone") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()
    raw_aggr = str(
        ("" if position_strategy_pinned else state.get("trade_aggressiveness"))
        or ((strategist_output_raw or {}).get("trade_aggressiveness") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()

    playbook = raw_playbook
    guidance = raw_guidance or str(frame.get("monitor_guidance") or "").strip().lower()
    tone = raw_tone or str(frame.get("risk_tone") or "").strip().lower()
    aggr = raw_aggr or str(frame.get("trade_aggressiveness") or "").strip().lower()

    if not strategist_exit_policy and not commander_horizon_policy and not any((raw_playbook, raw_guidance, raw_tone, raw_aggr)):
        return {"policy": out, "adjustments": adjustments}

    features = selected.get("features") if isinstance(selected, dict) and isinstance(selected.get("features"), dict) else {}
    price = resolve_price(
        state,
        str((selected or {}).get("symbol") or ""),
        selected,
        position=position if isinstance(position, dict) else None,
    )
    if price is None or _to_float(price) <= 0.0:
        price = position_mark_price(position)
    price_num = _to_float(price)
    atr14 = _to_float((features or {}).get("engine_atr14"))
    volatility20 = _to_float((features or {}).get("engine_volatility20"))
    trend_strength = _to_float((features or {}).get("engine_trend_strength"))
    vwap_distance = _to_float((features or {}).get("engine_vwap_distance"))
    hard_risk_rails = (
        dict(strategy_monitor_policy.get("hard_risk_rails") or {})
        if isinstance(strategy_monitor_policy.get("hard_risk_rails"), dict)
        else {}
    )

    stop_loss_pct = _to_float(out.get("stop_loss_pct"))
    if stop_loss_pct <= 0.0:
        stop_loss_pct = 0.03
    hard_stop_pct = _to_float(out.get("hard_stop_pct"))
    if hard_stop_pct <= 0.0:
        hard_stop_pct = _to_float(hard_risk_rails.get("hard_stop_pct"))
    take_profit_pct = _to_float(out.get("take_profit_pct"))
    if take_profit_pct <= 0.0:
        take_profit_pct = 0.05
    trailing_stop_pct = _to_float(out.get("trailing_stop_pct"))
    vol_expansion_ratio = _to_float(out.get("vol_expansion_ratio"))
    risk_reward_take_profit_r = _to_float(out.get("risk_reward_take_profit_r"))
    vwap_extension_take_profit_min_pct = _to_float(out.get("vwap_extension_take_profit_min_pct"))
    profit_time_stop_sec = _to_int(out.get("profit_time_stop_sec"))
    max_hold_sec = _to_int(out.get("max_hold_sec"))

    strategy_horizon = str(
        commander_horizon_policy.get("strategy_horizon")
        or frame.get("strategy_horizon")
        or behavior_translation.get("strategy_horizon")
        or ""
    ).strip().lower()
    expected_window = (
        dict(commander_horizon_policy.get("expected_hold_window") or {})
        if isinstance(commander_horizon_policy.get("expected_hold_window"), dict)
        else {}
    )
    if bool(behavior_translation.get("applied")) or strategy_horizon:
        if strategy_horizon == "scalp":
            take_profit_pct *= 0.88
            trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.85)
            if risk_reward_take_profit_r > 0.0:
                risk_reward_take_profit_r = min(risk_reward_take_profit_r, 0.85)
            profit_time_stop_sec = 300 if profit_time_stop_sec <= 0 else min(profit_time_stop_sec, 300)
            max_hold_sec = 900 if max_hold_sec <= 0 else min(max_hold_sec, 900)
            adjustments.append("strategy_horizon:scalp_exit_policy")
        elif strategy_horizon == "intraday":
            if profit_time_stop_sec <= 0:
                profit_time_stop_sec = 900
            window_max = _to_int(expected_window.get("max_sec"))
            if window_max > 0:
                max_hold_sec = window_max if max_hold_sec <= 0 else min(max_hold_sec, window_max)
            adjustments.append("strategy_horizon:intraday_exit_policy")
        elif strategy_horizon in {"overnight_probe", "1_2day_swing"}:
            take_profit_pct *= 1.10 if strategy_horizon == "overnight_probe" else 1.18
            trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
            window_max = _to_int(expected_window.get("max_sec"))
            if window_max > 0:
                max_hold_sec = max(max_hold_sec, window_max)
            out["allow_overnight_from_strategy_horizon"] = bool(behavior_translation.get("overnight_allowed"))
            adjustments.append(f"strategy_horizon:{strategy_horizon}_exit_policy")

    if playbook == "breakout":
        take_profit_pct *= 1.10
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.90)
        adjustments.append("playbook:breakout_exit")
    elif playbook == "pullback":
        stop_loss_pct *= 1.05
        take_profit_pct *= 1.08
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.75)
        adjustments.append("playbook:pullback_exit")
    elif playbook == "reversal":
        stop_loss_pct *= 0.92
        take_profit_pct *= 0.95
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        adjustments.append("playbook:reversal_exit")
    elif playbook == "defensive":
        stop_loss_pct *= 0.90
        take_profit_pct *= 0.90
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.65)
        adjustments.append("playbook:defensive_exit")

    if guidance == "hold_through_noise":
        stop_loss_pct *= 1.05
        take_profit_pct *= 1.05
        adjustments.append("monitor_guidance:hold_through_noise_exit")
    elif guidance == "quick_take_profit":
        take_profit_pct *= 0.90
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.80)
        if risk_reward_take_profit_r > 0.0:
            risk_reward_take_profit_r = min(risk_reward_take_profit_r, 0.85)
        if vwap_extension_take_profit_min_pct > 0.0:
            vwap_extension_take_profit_min_pct = min(vwap_extension_take_profit_min_pct, 0.004)
        if profit_time_stop_sec > 0:
            profit_time_stop_sec = min(profit_time_stop_sec, 600)
        adjustments.append("monitor_guidance:quick_take_profit_exit")
    elif guidance == "defensive_exit":
        stop_loss_pct *= 0.95
        take_profit_pct *= 0.92
        adjustments.append("monitor_guidance:defensive_exit_exit")

    if tone == "conservative":
        stop_loss_pct *= 0.92
        take_profit_pct *= 0.96
        adjustments.append("risk_tone:conservative_exit")
    elif tone == "aggressive":
        stop_loss_pct *= 1.08
        take_profit_pct *= 1.05
        adjustments.append("risk_tone:aggressive_exit")

    if aggr == "low":
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        adjustments.append("trade_aggressiveness:low_exit")
    elif aggr == "high":
        take_profit_pct *= 1.05
        adjustments.append("trade_aggressiveness:high_exit")

    if atr14 > 0.0 and price_num > 0.0:
        atr_ratio = float(atr14 / price_num)
        atr_mult = 1.2
        if playbook == "breakout":
            atr_mult = 1.4
        elif playbook == "pullback":
            atr_mult = 1.8
        elif playbook == "reversal":
            atr_mult = 1.3
        atr_stop = _clamp(atr_ratio * atr_mult, 0.005, 0.08)
        if atr_stop > stop_loss_pct:
            stop_loss_pct = atr_stop
            adjustments.append(f"atr_stop_floor:{atr_stop:.4f}")

    if volatility20 > 0.0:
        vol_stop = _clamp(volatility20 * (1.15 if tone == "aggressive" else 0.95), 0.005, 0.08)
        if vol_stop > stop_loss_pct:
            stop_loss_pct = vol_stop
            adjustments.append(f"volatility_stop_floor:{vol_stop:.4f}")
        if vol_expansion_ratio <= 0.0:
            vol_expansion_ratio = 1.8 if playbook in ("defensive", "pullback") else 2.2
            adjustments.append("vol_expansion_ratio:auto")

    if vwap_distance > 0.02 and guidance == "quick_take_profit":
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.90)
        adjustments.append("vwap_distance:extended_profit_lock")

    if trend_strength > 0.5 and playbook in ("breakout", "pullback"):
        take_profit_pct = max(take_profit_pct, stop_loss_pct * 1.6)
        adjustments.append("trend_strength:extend_take_profit")

    stop_loss_pct = _clamp(stop_loss_pct, 0.003, 0.10)
    if hard_stop_pct > 0.0:
        hard_stop_pct = _clamp(hard_stop_pct, 0.003, 0.10)
    if take_profit_pct <= 0.0:
        take_profit_pct = max(0.005, stop_loss_pct * 1.05)
    take_profit_pct = _clamp(take_profit_pct, 0.005, 0.25)
    trailing_stop_pct = _clamp(max(trailing_stop_pct, stop_loss_pct * 0.50 if trailing_stop_pct > 0.0 else 0.0), 0.0, 0.15)
    vol_expansion_ratio = _clamp(vol_expansion_ratio, 0.0, 5.0)
    max_stop_pct_cap = _to_float(hard_risk_rails.get("max_stop_pct_cap"))
    if max_stop_pct_cap > 0.0 and stop_loss_pct > max_stop_pct_cap:
        stop_loss_pct = max_stop_pct_cap
        adjustments.append(f"strategy_policy:max_stop_pct_cap:{max_stop_pct_cap:.4f}")
    if hard_stop_pct > 0.0:
        adjustments.append(f"strategy_policy:hard_stop_pct:{hard_stop_pct:.4f}")

    out["hard_stop_pct"] = float(hard_stop_pct)
    out["stop_loss_pct"] = float(stop_loss_pct)
    out["take_profit_pct"] = float(take_profit_pct)
    out["trailing_stop_pct"] = float(trailing_stop_pct)
    out["vol_expansion_ratio"] = float(vol_expansion_ratio)
    if risk_reward_take_profit_r > 0.0:
        out["risk_reward_take_profit_r"] = float(_clamp(risk_reward_take_profit_r, 0.0, 3.0))
    if vwap_extension_take_profit_min_pct > 0.0:
        out["vwap_extension_take_profit_min_pct"] = float(_clamp(vwap_extension_take_profit_min_pct, 0.001, 0.05))
    if profit_time_stop_sec > 0:
        out["profit_time_stop_sec"] = int(profit_time_stop_sec)
    if max_hold_sec > 0:
        out["max_hold_sec"] = int(max_hold_sec)
    if strategy_horizon:
        out["strategy_horizon"] = strategy_horizon
        out["source_strategy_horizon"] = str(commander_horizon_policy.get("source_strategy_horizon") or frame.get("source_strategy_horizon") or "")
        out["horizon_behavior_translation_applied"] = bool(behavior_translation.get("applied"))
        out["horizon_exit_policy_bias"] = str(behavior_translation.get("exit_policy_bias") or "")
    if position_strategy_pinned:
        out["position_strategy_context_applied"] = True
        out["position_strategy_context_symbol"] = str(frame.get("position_strategy_context_symbol") or "")
        out["position_strategy_context_source"] = str(frame.get("position_strategy_context_source") or "")
        adjustments.append(
            "position_strategy_context_pinned:"
            + str(frame.get("position_strategy_context_symbol") or "")
        )
    return {"policy": out, "adjustments": adjustments}

def harmonize_exit_policy_with_monitor_guards(
    *,
    exit_policy_base: Dict[str, Any],
    min_hold_sec: int,
) -> Dict[str, Any]:
    out = dict(exit_policy_base or {})
    adjustments: list[str] = []
    min_hold = max(0, int(min_hold_sec or 0))
    if min_hold <= 0:
        return {"policy": out, "adjustments": adjustments}

    max_hold = _to_int(out.get("max_hold_sec"))
    if max_hold > 0 and max_hold < min_hold:
        out["max_hold_sec"] = int(min_hold)
        adjustments.append(f"max_hold_sec_raised_to_min_hold:{max_hold}->{min_hold}")

    time_stop = _to_int(out.get("time_stop_sec"))
    if time_stop > 0 and time_stop < min_hold:
        out["time_stop_sec"] = int(min_hold)
        adjustments.append(f"time_stop_sec_raised_to_min_hold:{time_stop}->{min_hold}")

    return {"policy": out, "adjustments": adjustments}



