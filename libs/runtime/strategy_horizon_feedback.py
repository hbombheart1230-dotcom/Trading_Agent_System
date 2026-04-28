from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


_ALLOWED_HORIZONS = {"scalp", "intraday", "overnight_probe", "1_2day_swing"}

_DEFAULT_WINDOWS = {
    "scalp": {"min_sec": 60, "target_sec": 300, "max_sec": 900},
    "intraday": {"min_sec": 300, "target_sec": 1800, "max_sec": 14400},
    "overnight_probe": {"min_sec": 1800, "target_sec": 14400, "max_sec": 86400},
    "1_2day_swing": {"min_sec": 3600, "target_sec": 86400, "max_sec": 172800},
}

_DEFAULT_EXIT_GUIDANCE = {
    "profit_take_style": "trail_after_first_push",
    "allow_early_exit": True,
    "early_exit_allowed_reasons": [
        "hard_stop",
        "broker_truth_mismatch",
        "liquidity_collapse",
        "theme_breakdown",
        "market_regime_flip",
        "data_quality_guard",
    ],
    "avoid_early_exit_reasons": [
        "small_noise_pullback",
        "minor_profit_without_momentum_loss",
    ],
}

_LONG_HORIZONS = {"overnight_probe", "1_2day_swing"}

_HARD_EXIT_REASON_MARKERS = (
    "hard_stop",
    "stop_loss",
    "emergency",
    "broker_truth",
    "truth_mismatch",
    "liquidity",
    "price_anomaly",
    "eod_flat",
    "market_regime_flip",
    "data_quality",
)

_PRICE_CHECKPOINT_MINUTES = {
    "+5m": 5,
    "+15m": 15,
    "+30m": 30,
    "+60m": 60,
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _as_list(value: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()][:limit]


def _symbol_from_trade_id(value: Any) -> str:
    raw = str(value or "").strip()
    parts = raw.split("_")
    if len(parts) < 3:
        return ""
    symbol = parts[2].strip().upper()
    if symbol.startswith("A") and len(symbol) == 7 and symbol[1:].isdigit():
        return symbol[1:]
    return symbol if len(symbol) == 6 and symbol.isdigit() else ""


def _exit_vs_strategy_from_surface(value: Any) -> dict[str, Any]:
    obj = _as_dict(value)
    direct = _as_dict(obj.get("exit_vs_strategy_intent"))
    if direct:
        return direct
    monitor_context = _as_dict(obj.get("monitor_context"))
    return _as_dict(monitor_context.get("exit_vs_strategy_intent"))


def _monitor_context_from_surface(value: Any) -> dict[str, Any]:
    obj = _as_dict(value)
    monitor_context = _as_dict(obj.get("monitor_context"))
    if monitor_context:
        return monitor_context
    if obj.get("current_price") not in (None, "") or isinstance(obj.get("exit_vs_strategy_intent"), Mapping):
        return obj
    return {}


def _latest_exit_vs_strategy_intent(*surfaces: Any) -> dict[str, Any]:
    for surface in surfaces:
        found = _exit_vs_strategy_from_surface(surface)
        if found:
            return found
    for surface in surfaces:
        if not isinstance(surface, list):
            continue
        for item in reversed(surface):
            found = _exit_vs_strategy_from_surface(item)
            if found:
                return found
    return {}


def _latest_monitor_context(*surfaces: Any) -> dict[str, Any]:
    for surface in surfaces:
        found = _monitor_context_from_surface(surface)
        if found:
            return found
    for surface in surfaces:
        if not isinstance(surface, list):
            continue
        for item in reversed(surface):
            found = _monitor_context_from_surface(item)
            if found:
                return found
    return {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _epoch_seconds(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        return raw / 1000.0 if raw > 10_000_000_000 else raw
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.isdigit():
            if len(text) == 14:
                return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
            raw = float(text)
            return raw / 1000.0 if raw > 10_000_000_000 else raw
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _row_epoch_seconds(row: Mapping[str, Any]) -> float | None:
    return _epoch_seconds(row.get("ts") or row.get("timestamp") or row.get("datetime") or row.get("raw_ts"))


def _row_price(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(row.get(key))
        if value is not None and value > 0:
            return value
    return None


def _format_epoch(value: float | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _choose_default_horizon(*, playbook: str = "", monitor_guidance: str = "", trade_aggressiveness: str = "") -> str:
    guidance = str(monitor_guidance or "").strip().lower()
    playbook_text = str(playbook or "").strip().lower()
    aggressiveness = str(trade_aggressiveness or "").strip().lower()
    if guidance == "quick_take_profit" or aggressiveness in {"very_high", "high"}:
        return "scalp"
    if guidance == "hold_through_noise":
        return "intraday"
    if playbook_text in {"pullback", "breakout", "reversal"}:
        return "intraday"
    return "intraday"


def build_strategy_horizon_feedback(
    raw: Mapping[str, Any] | None = None,
    *,
    playbook: str = "",
    monitor_guidance: str = "",
    trade_aggressiveness: str = "",
    risk_tone: str = "",
    source: str = "strategist_node",
) -> dict[str, Any]:
    """Build an observability-only strategy horizon payload.

    This payload is advisory metadata. It must not change entry/exit thresholds
    or force holding behavior.
    """

    raw_obj = _as_dict(raw)
    raw_window = _as_dict(raw_obj.get("expected_hold_window"))
    raw_exit_guidance = _as_dict(raw_obj.get("exit_guidance"))
    raw_monitor_handoff = _as_dict(raw_obj.get("monitor_handoff"))
    horizon = str(
        raw_obj.get("strategy_horizon")
        or raw_obj.get("horizon")
        or _choose_default_horizon(
            playbook=playbook,
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
        )
    ).strip()
    if horizon not in _ALLOWED_HORIZONS:
        horizon = _choose_default_horizon(
            playbook=playbook,
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
        )
    default_window = dict(_DEFAULT_WINDOWS[horizon])
    expected_hold_window = {
        "min_sec": _safe_int(raw_window.get("min_sec"), default_window["min_sec"]),
        "target_sec": _safe_int(raw_window.get("target_sec"), default_window["target_sec"]),
        "max_sec": _safe_int(raw_window.get("max_sec"), default_window["max_sec"]),
    }
    if expected_hold_window["target_sec"] < expected_hold_window["min_sec"]:
        expected_hold_window["target_sec"] = expected_hold_window["min_sec"]
    if expected_hold_window["max_sec"] < expected_hold_window["target_sec"]:
        expected_hold_window["max_sec"] = expected_hold_window["target_sec"]
    exit_guidance = {
        **dict(_DEFAULT_EXIT_GUIDANCE),
        **raw_exit_guidance,
    }
    exit_guidance["allow_early_exit"] = bool(exit_guidance.get("allow_early_exit", True))
    exit_guidance["early_exit_allowed_reasons"] = (
        _as_list(exit_guidance.get("early_exit_allowed_reasons"), limit=10)
        or list(_DEFAULT_EXIT_GUIDANCE["early_exit_allowed_reasons"])
    )
    exit_guidance["avoid_early_exit_reasons"] = (
        _as_list(exit_guidance.get("avoid_early_exit_reasons"), limit=10)
        or list(_DEFAULT_EXIT_GUIDANCE["avoid_early_exit_reasons"])
    )
    monitor_handoff = {
        "hold_bias": str(raw_monitor_handoff.get("hold_bias") or "neutral").strip() or "neutral",
        "preferred_exit": str(raw_monitor_handoff.get("preferred_exit") or "respect_existing_exit_policy").strip()
        or "respect_existing_exit_policy",
        "do_not_force_hold": True,
    }
    return {
        "schema_version": "strategy_horizon_feedback.v1",
        "observability_only": True,
        "strategy_horizon": horizon,
        "expected_hold_window": expected_hold_window,
        "exit_guidance": exit_guidance,
        "invalidation_conditions": _as_list(raw_obj.get("invalidation_conditions"), limit=8),
        "monitor_handoff": monitor_handoff,
        "playbook": str(playbook or raw_obj.get("playbook") or "").strip(),
        "monitor_guidance": str(monitor_guidance or raw_obj.get("monitor_guidance") or "").strip(),
        "trade_aggressiveness": str(trade_aggressiveness or raw_obj.get("trade_aggressiveness") or "").strip(),
        "risk_tone": str(risk_tone or raw_obj.get("risk_tone") or "").strip(),
        "source": str(raw_obj.get("source") or source or "strategist_node"),
    }


def build_commander_horizon_policy(
    strategist_horizon_feedback: Mapping[str, Any] | None = None,
    *,
    commander_context: Mapping[str, Any] | None = None,
    memory_packets: Mapping[str, Any] | None = None,
    selected_symbol_memory: Mapping[str, Any] | None = None,
    post_exit_shadow_memory: Mapping[str, Any] | None = None,
    runtime_phase: str = "",
    live_validation_mode: bool = True,
    source: str = "commander_runtime",
) -> dict[str, Any]:
    """Build the Commander-owned operational horizon policy.

    Strategist proposes a horizon; Commander decides the operational horizon
    Monitor/Reporter should use. This is still observability-only and must not
    force hold behavior or change thresholds.
    """

    context = _as_dict(commander_context)
    packets = _as_dict(memory_packets)
    symbol_memory = _as_dict(selected_symbol_memory) or _as_dict(packets.get("symbol_memory_packet"))
    shadow_memory = _as_dict(post_exit_shadow_memory) or _as_dict(packets.get("post_exit_shadow_memory"))
    proposal = build_strategy_horizon_feedback(
        strategist_horizon_feedback or {},
        playbook=str(context.get("playbook") or ""),
        monitor_guidance=str(context.get("monitor_guidance") or ""),
        trade_aggressiveness=str(context.get("trade_aggressiveness") or ""),
        risk_tone=str(context.get("risk_tone") or ""),
        source=str(_as_dict(strategist_horizon_feedback).get("source") or "strategist_horizon_proposal"),
    )
    source_horizon = str(proposal.get("strategy_horizon") or "intraday")
    operational_horizon = source_horizon if source_horizon in _ALLOWED_HORIZONS else "intraday"
    memory_adjustments: list[dict[str, Any]] = []
    if bool(live_validation_mode) and operational_horizon in _LONG_HORIZONS:
        operational_horizon = "intraday"
        memory_adjustments.append(
            {
                "type": "live_validation_cap",
                "from_horizon": source_horizon,
                "to_horizon": operational_horizon,
                "reason": "long_horizon_requires_more_post_exit_shadow_samples_before_behavior_change",
                "behavior_change": False,
            }
        )
    commander_memory_policy = _as_dict(context.get("commander_memory_policy"))
    active_layers = _as_list(commander_memory_policy.get("active_layers"), limit=8)
    if not active_layers:
        active_layers = _as_list(_as_dict(packets.get("commander_memory_policy")).get("active_layers"), limit=8)
    if active_layers:
        memory_adjustments.append(
            {
                "type": "memory_context_present",
                "active_layers": active_layers,
                "behavior_change": False,
            }
        )
    if symbol_memory:
        memory_adjustments.append(
            {
                "type": "symbol_memory_observed",
                "symbol": str(symbol_memory.get("symbol") or ""),
                "trade_count": _safe_int(symbol_memory.get("trade_count"), 0),
                "win_rate": symbol_memory.get("win_rate"),
                "behavior_change": False,
            }
        )
    if shadow_memory:
        memory_adjustments.append(
            {
                "type": "post_exit_shadow_memory_observed",
                "status": str(shadow_memory.get("status") or ""),
                "behavior_change": False,
            }
        )
    expected_hold_window = dict(proposal.get("expected_hold_window") or {})
    if operational_horizon != source_horizon or not expected_hold_window:
        expected_hold_window = dict(_DEFAULT_WINDOWS.get(operational_horizon, _DEFAULT_WINDOWS["intraday"]))
    decision_reason = "commander_accepts_strategist_horizon_proposal_observability_only"
    if operational_horizon != source_horizon:
        decision_reason = "commander_caps_long_horizon_during_live_validation_observability_only"
    elif not strategist_horizon_feedback:
        decision_reason = "commander_default_intraday_horizon_without_strategist_proposal"
    return {
        "schema_version": "commander_horizon_policy.v1",
        "owner": "commander",
        "observability_only": True,
        "allow_behavior_change": False,
        "do_not_force_hold": True,
        "live_validation_mode": bool(live_validation_mode),
        "strategy_horizon": operational_horizon,
        "expected_hold_window": expected_hold_window,
        "exit_guidance": dict(proposal.get("exit_guidance") or {}),
        "invalidation_conditions": list(proposal.get("invalidation_conditions") or []),
        "monitor_handoff": {
            **_as_dict(proposal.get("monitor_handoff")),
            "do_not_force_hold": True,
        },
        "source_strategy_horizon": source_horizon,
        "source_expected_hold_window": dict(proposal.get("expected_hold_window") or {}),
        "strategist_horizon_proposal": dict(proposal),
        "proposal": dict(proposal),
        "memory_adjustments": memory_adjustments,
        "decision_reason": decision_reason,
        "runtime_context": {
            "runtime_phase": str(runtime_phase or context.get("runtime_phase") or ""),
            "session_bias": str(context.get("session_bias") or ""),
            "risk_mode": str(context.get("risk_mode") or ""),
            "market_regime": str(context.get("market_regime") or ""),
            "strategist_refresh_requested": bool(context.get("strategist_refresh_requested")),
            "strategist_refresh_reason": str(context.get("strategist_refresh_reason") or ""),
            "carry_state": str(context.get("carry_state") or ""),
            "carry_risk_bias": str(context.get("carry_risk_bias") or ""),
        },
        "source": str(source or "commander_runtime"),
    }


def extract_commander_horizon_policy(surface: Mapping[str, Any] | None) -> dict[str, Any]:
    obj = _as_dict(surface)
    for key in ("commander_horizon_policy", "horizon_policy"):
        if isinstance(obj.get(key), Mapping):
            found = dict(obj.get(key) or {})
            if str(found.get("owner") or "").strip().lower() == "commander" or str(
                found.get("schema_version") or ""
            ).startswith("commander_horizon_policy"):
                return found
    applied_policy = _as_dict(obj.get("applied_policy"))
    for key in ("horizon", "commander_horizon_policy"):
        if isinstance(applied_policy.get(key), Mapping):
            found = dict(applied_policy.get(key) or {})
            if str(found.get("owner") or "").strip().lower() == "commander" or str(
                found.get("schema_version") or ""
            ).startswith("commander_horizon_policy"):
                return found
    strategy_policy = _as_dict(obj.get("strategy_policy"))
    if strategy_policy:
        found = extract_commander_horizon_policy(strategy_policy)
        if found:
            return found
    monitor_policy = _as_dict(obj.get("monitor_policy"))
    if monitor_policy:
        found = extract_commander_horizon_policy(monitor_policy)
        if found:
            return found
    commander_context = _as_dict(obj.get("commander_context"))
    if commander_context:
        found = extract_commander_horizon_policy(commander_context)
        if found:
            return found
    commander_context_ref = _as_dict(obj.get("commander_context_ref"))
    if commander_context_ref:
        found = extract_commander_horizon_policy(commander_context_ref)
        if found:
            return found
    return {}


def extract_commander_horizon_policy_from_state(state: Mapping[str, Any] | None) -> dict[str, Any]:
    obj = _as_dict(state)
    direct = extract_commander_horizon_policy(obj)
    if direct:
        return direct
    for key in (
        "commander_decision",
        "strategist_output",
        "strategy_policy",
        "entry_strategy_context",
        "monitor_policy",
        "applied_policy",
    ):
        surface = obj.get(key)
        if isinstance(surface, Mapping):
            found = extract_commander_horizon_policy(surface)
            if found:
                return found
    return {}


def extract_strategy_horizon_feedback(surface: Mapping[str, Any] | None) -> dict[str, Any]:
    obj = _as_dict(surface)
    if isinstance(obj.get("strategy_horizon_feedback"), Mapping):
        return dict(obj.get("strategy_horizon_feedback") or {})
    strategy_policy = _as_dict(obj.get("strategy_policy"))
    if not strategy_policy and isinstance(obj.get("monitor_policy"), Mapping):
        strategy_policy = dict(obj)
    monitor_policy = _as_dict(strategy_policy.get("monitor_policy"))
    if isinstance(monitor_policy.get("strategy_horizon_feedback"), Mapping):
        return dict(monitor_policy.get("strategy_horizon_feedback") or {})
    if obj.get("strategy_horizon") not in (None, ""):
        return build_strategy_horizon_feedback(
            {
                "strategy_horizon": obj.get("strategy_horizon"),
                "expected_hold_window": _as_dict(obj.get("expected_hold_window")),
                "exit_guidance": _as_dict(obj.get("exit_guidance")),
                "invalidation_conditions": obj.get("invalidation_conditions"),
                "monitor_handoff": _as_dict(obj.get("monitor_handoff")),
            },
            playbook=str(obj.get("playbook") or ""),
            monitor_guidance=str(obj.get("monitor_guidance") or ""),
            trade_aggressiveness=str(obj.get("trade_aggressiveness") or ""),
            risk_tone=str(obj.get("risk_tone") or ""),
            source="extracted_surface",
        )
    return {}


def extract_strategy_horizon_feedback_from_state(state: Mapping[str, Any] | None) -> dict[str, Any]:
    obj = _as_dict(state)
    for key in ("strategist_output", "strategy_policy", "entry_strategy_context"):
        surface = obj.get(key)
        if isinstance(surface, Mapping):
            found = extract_strategy_horizon_feedback(surface)
            if found:
                return found
    return build_strategy_horizon_feedback(
        {},
        playbook=str(obj.get("playbook") or ""),
        monitor_guidance=str(obj.get("monitor_guidance") or ""),
        trade_aggressiveness=str(obj.get("trade_aggressiveness") or ""),
        risk_tone=str(obj.get("risk_tone") or ""),
        source="state_default",
    )


def _is_hard_exit(reason: str, exit_info: Mapping[str, Any]) -> bool:
    if bool(exit_info.get("hard_exit")) or bool(exit_info.get("emergency_exit")):
        return True
    reason_text = str(reason or "").strip().lower()
    return any(marker in reason_text for marker in _HARD_EXIT_REASON_MARKERS)


def build_exit_vs_strategy_intent(
    *,
    state: Mapping[str, Any] | None,
    exit_info: Mapping[str, Any] | None,
    sell_submitted: bool,
) -> dict[str, Any]:
    exit_obj = _as_dict(exit_info)
    commander_horizon = extract_commander_horizon_policy_from_state(state)
    horizon = commander_horizon or extract_strategy_horizon_feedback_from_state(state)
    horizon_owner = "commander" if commander_horizon else "strategist"
    strategist_proposal = (
        _as_dict(commander_horizon.get("strategist_horizon_proposal"))
        or _as_dict(commander_horizon.get("proposal"))
        if commander_horizon
        else horizon
    )
    expected = _as_dict(horizon.get("expected_hold_window"))
    actual_hold_sec = _safe_int(
        exit_obj.get("position_age_seconds")
        if exit_obj.get("position_age_seconds") not in (None, "")
        else exit_obj.get("hold_sec"),
        0,
    )
    min_sec = _safe_int(expected.get("min_sec"), 0)
    reason = str(exit_obj.get("reason") or exit_obj.get("monitor_reason") or "").strip()
    hard_exit = _is_hard_exit(reason, exit_obj)
    exit_triggered = bool(exit_obj.get("triggered") or exit_obj.get("exit_signal_detected") or sell_submitted)
    early_exit = bool(exit_triggered and actual_hold_sec > 0 and min_sec > 0 and actual_hold_sec < min_sec)
    if not exit_triggered:
        alignment = "unknown"
        alignment_reason = "no_exit_trigger_recorded"
    elif hard_exit:
        alignment = "early_but_justified" if early_exit else "aligned"
        alignment_reason = f"hard_exit:{reason or 'unknown'}"
    elif early_exit:
        alignment = "early_unproven"
        alignment_reason = "actual_hold_sec_below_strategy_min_without_hard_exit"
    else:
        alignment = "aligned"
        alignment_reason = "exit_not_earlier_than_strategy_min_window"
    return {
        "schema_version": "exit_vs_strategy_intent.v1",
        "observability_only": True,
        "horizon_owner": horizon_owner,
        "strategy_horizon": str(horizon.get("strategy_horizon") or "intraday"),
        "source_strategy_horizon": str(
            horizon.get("source_strategy_horizon")
            or strategist_proposal.get("strategy_horizon")
            or horizon.get("strategy_horizon")
            or "intraday"
        ),
        "expected_hold_window": expected,
        "source_expected_hold_window": dict(
            horizon.get("source_expected_hold_window")
            or strategist_proposal.get("expected_hold_window")
            or expected
        ),
        "commander_horizon_policy": dict(commander_horizon),
        "strategist_horizon_proposal": dict(strategist_proposal),
        "commander_decision_reason": str(horizon.get("decision_reason") or ""),
        "actual_hold_sec": actual_hold_sec if actual_hold_sec > 0 else None,
        "early_exit_flag": early_exit,
        "exit_alignment": alignment,
        "alignment_reason": alignment_reason,
        "hard_exit": hard_exit,
        "hard_exit_reason": reason if hard_exit else "",
        "exit_reason": reason,
        "sell_submitted": bool(sell_submitted),
        "exit_triggered": exit_triggered,
        "source": "monitor_node",
    }


def build_post_exit_shadow_placeholder(
    *,
    lifecycle_bundle: Mapping[str, Any] | None,
    lifecycle: Mapping[str, Any] | None = None,
    status: str = "",
    exit_execution_details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if str(status or "").strip().lower() != "closed":
        return {}
    bundle = _as_dict(lifecycle_bundle)
    lifecycle_obj = _as_dict(lifecycle)
    exit_ctx = _as_dict(lifecycle_obj.get("exit"))
    entry_ctx = _as_dict(lifecycle_obj.get("entry"))
    exit_monitor = _as_dict(exit_ctx.get("monitor_context"))
    holding_obj = _as_dict(lifecycle_obj.get("holding"))
    if not exit_monitor:
        exit_monitor = _latest_monitor_context(
            lifecycle_obj.get("hold"),
            holding_obj.get("monitor_context_snapshots"),
            bundle.get("monitor_context_snapshots"),
        )
    exit_vs_strategy = _latest_exit_vs_strategy_intent(
        exit_ctx,
        exit_monitor,
        lifecycle_obj.get("hold"),
        holding_obj.get("monitor_context_snapshots"),
        bundle.get("monitor_context_snapshots"),
    )
    details = _as_dict(exit_execution_details) or _as_dict(bundle.get("exit_execution_details"))
    commander_horizon = extract_commander_horizon_policy(bundle)
    if not commander_horizon and exit_vs_strategy:
        commander_horizon = extract_commander_horizon_policy(exit_vs_strategy)
    horizon = commander_horizon or extract_strategy_horizon_feedback(bundle)
    if not horizon and exit_vs_strategy:
        horizon = {
            "strategy_horizon": str(exit_vs_strategy.get("strategy_horizon") or "intraday"),
            "source_strategy_horizon": str(
                exit_vs_strategy.get("source_strategy_horizon")
                or exit_vs_strategy.get("strategy_horizon")
                or "intraday"
            ),
            "expected_hold_window": dict(exit_vs_strategy.get("expected_hold_window") or {}),
        }
    if not horizon and isinstance(bundle.get("strategist"), Mapping):
        horizon = extract_strategy_horizon_feedback(bundle.get("strategist"))
    if not horizon:
        horizon = build_strategy_horizon_feedback({}, source="post_exit_shadow_default")
    symbol = str(
        details.get("symbol")
        or exit_ctx.get("symbol")
        or lifecycle_obj.get("symbol")
        or entry_ctx.get("symbol")
        or bundle.get("symbol")
        or _symbol_from_trade_id(lifecycle_obj.get("trade_id"))
        or _symbol_from_trade_id(bundle.get("trade_id"))
        or bundle.get("selected_symbol")
        or ""
    ).strip()
    exit_price = (
        details.get("filled_price")
        if details.get("filled_price") not in (None, "")
        else details.get("avg_price")
        if details.get("avg_price") not in (None, "")
        else exit_monitor.get("current_price")
        if exit_monitor.get("current_price") not in (None, "")
        else None
    )
    return {
        "schema_version": "post_exit_shadow.v1",
        "observability_only": True,
        "status": "pending",
        "symbol": symbol,
        "exit_ts": str(exit_ctx.get("ts") or details.get("ts") or ""),
        "exit_price": exit_price,
        "horizon_owner": "commander" if commander_horizon else "strategist",
        "strategy_horizon": str(horizon.get("strategy_horizon") or "intraday"),
        "source_strategy_horizon": str(horizon.get("source_strategy_horizon") or horizon.get("strategy_horizon") or "intraday"),
        "expected_hold_window": dict(horizon.get("expected_hold_window") or {}),
        "commander_horizon_policy": dict(commander_horizon),
        "checkpoints": {
            "+5m": {"status": "pending"},
            "+15m": {"status": "pending"},
            "+30m": {"status": "pending"},
            "+60m": {"status": "pending"},
            "EOD": {"status": "pending"},
            "T+1": {"status": "pending"},
            "T+2": {"status": "pending"},
        },
        "would_hit_target": None,
        "would_hit_stop_first": None,
        "best_exit_offset": "",
        "best_exit_price": None,
        "post_exit_label": "pending",
        "source": "live_trade_context_placeholder",
    }


def update_post_exit_shadow_with_price_observations(
    post_exit_shadow: Mapping[str, Any] | None,
    *,
    minute_rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fill post-exit checkpoints from minute OHLCV rows.

    This is still observability-only. It updates artifact evidence only and must
    not feed back into live hold behavior until the Commander policy allows it.
    """

    shadow = _as_dict(post_exit_shadow)
    if not shadow:
        return {}
    rows_in = list(minute_rows or [])
    exit_epoch = _epoch_seconds(shadow.get("exit_ts"))
    exit_price = _safe_float(shadow.get("exit_price"))
    if exit_epoch is None or exit_price is None or exit_price <= 0:
        shadow["price_observation_status"] = "pending"
        shadow["price_observation_reason"] = "missing_exit_time_or_price"
        return shadow
    if not rows_in:
        shadow["price_observation_status"] = "pending"
        shadow["price_observation_reason"] = "no_minute_rows"
        return shadow

    normalized_rows: list[dict[str, Any]] = []
    for raw in rows_in:
        if not isinstance(raw, Mapping):
            continue
        ts = _row_epoch_seconds(raw)
        close = _row_price(raw, "close", "price", "current_price", "cur_price")
        if ts is None or close is None:
            continue
        high = _row_price(raw, "high", "high_price") or close
        low = _row_price(raw, "low", "low_price") or close
        normalized_rows.append(
            {
                "ts": float(ts),
                "price": float(close),
                "high": float(high),
                "low": float(low),
                "volume": _safe_float(raw.get("volume") or raw.get("vol")),
                "raw_ts": str(raw.get("raw_ts") or raw.get("ts") or ""),
            }
        )
    rows = sorted((row for row in normalized_rows if row["ts"] >= exit_epoch), key=lambda row: row["ts"])
    if not rows:
        shadow["price_observation_status"] = "pending"
        shadow["price_observation_reason"] = "no_rows_after_exit"
        if normalized_rows:
            shadow["latest_observed_ts"] = _format_epoch(max(row["ts"] for row in normalized_rows))
        return shadow

    checkpoints = _as_dict(shadow.get("checkpoints"))
    observed_offsets: list[dict[str, Any]] = []
    for label, minutes in _PRICE_CHECKPOINT_MINUTES.items():
        target_epoch = exit_epoch + (minutes * 60)
        prior_rows = [row for row in rows if row["ts"] <= target_epoch]
        checkpoint_row = next((row for row in rows if row["ts"] >= target_epoch), None)
        if checkpoint_row is None:
            current = _as_dict(checkpoints.get(label))
            current.update(
                {
                    "status": "pending",
                    "target_ts": _format_epoch(target_epoch),
                    "latest_observed_ts": _format_epoch(rows[-1]["ts"]),
                    "observation_count": len(prior_rows) or len(rows),
                }
            )
            checkpoints[label] = current
            continue
        window_rows = [row for row in rows if row["ts"] <= checkpoint_row["ts"]]
        high_since_exit = max(float(row["high"]) for row in window_rows)
        low_since_exit = min(float(row["low"]) for row in window_rows)
        price = float(checkpoint_row["price"])
        payload = {
            "status": "observed",
            "target_ts": _format_epoch(target_epoch),
            "observed_ts": _format_epoch(checkpoint_row["ts"]),
            "raw_ts": str(checkpoint_row.get("raw_ts") or ""),
            "price": price,
            "observed_price": price,
            "high_since_exit": high_since_exit,
            "low_since_exit": low_since_exit,
            "max_upside_pct": (high_since_exit / exit_price) - 1.0,
            "max_drawdown_pct": (low_since_exit / exit_price) - 1.0,
            "return_pct": (price / exit_price) - 1.0,
            "observation_count": len(window_rows),
        }
        if checkpoint_row.get("volume") is not None:
            payload["volume"] = checkpoint_row.get("volume")
        checkpoints[label] = payload
        observed_offsets.append({"label": label, **payload})

    # EOD is only marked observed when the cached minute rows actually reach
    # the regular-session close area. Before then it stays pending.
    eod_rows = [row for row in rows if str(row.get("raw_ts") or "")[8:12] >= "1530"]
    if eod_rows:
        close_row = eod_rows[-1]
        high_since_exit = max(float(row["high"]) for row in rows if row["ts"] <= close_row["ts"])
        low_since_exit = min(float(row["low"]) for row in rows if row["ts"] <= close_row["ts"])
        price = float(close_row["price"])
        eod_payload = {
            "status": "observed",
            "observed_ts": _format_epoch(close_row["ts"]),
            "raw_ts": str(close_row.get("raw_ts") or ""),
            "close": price,
            "price": price,
            "observed_price": price,
            "high_since_exit": high_since_exit,
            "low_since_exit": low_since_exit,
            "max_upside_pct": (high_since_exit / exit_price) - 1.0,
            "max_drawdown_pct": (low_since_exit / exit_price) - 1.0,
            "return_pct": (price / exit_price) - 1.0,
            "observation_count": len([row for row in rows if row["ts"] <= close_row["ts"]]),
        }
        checkpoints["EOD"] = eod_payload
        observed_offsets.append({"label": "EOD", **eod_payload})
    elif "EOD" in checkpoints:
        current = _as_dict(checkpoints.get("EOD"))
        current.update({"status": "pending", "latest_observed_ts": _format_epoch(rows[-1]["ts"])})
        checkpoints["EOD"] = current

    shadow["checkpoints"] = checkpoints
    shadow["price_observation_status"] = "observed" if observed_offsets else "pending"
    shadow["price_observation_reason"] = "" if observed_offsets else "checkpoint_targets_not_reached"
    shadow["price_observation_source"] = "minute_ohlcv"
    shadow["latest_observed_ts"] = _format_epoch(rows[-1]["ts"])
    if observed_offsets:
        best = max(observed_offsets, key=lambda item: float(item.get("high_since_exit") or item.get("price") or 0.0))
        shadow["best_exit_offset"] = str(best.get("label") or "")
        shadow["best_exit_price"] = float(best.get("high_since_exit") or best.get("price") or 0.0)
        shadow["max_post_exit_upside_pct"] = max(float(item.get("max_upside_pct") or 0.0) for item in observed_offsets)
        shadow["max_post_exit_drawdown_pct"] = min(float(item.get("max_drawdown_pct") or 0.0) for item in observed_offsets)
    return shadow
