from __future__ import annotations

import os
from typing import Any, Dict


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _first_mapping(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _config_float(config: Dict[str, Any], key: str, env_key: str, default: float) -> float:
    if isinstance(config, dict) and config.get(key) not in (None, ""):
        return _to_float(config.get(key))
    raw = str(os.getenv(env_key, "") or "").strip()
    if raw:
        return _to_float(raw, default)
    return float(default)


def _config_bool(config: Dict[str, Any], key: str, env_key: str, default: bool) -> bool:
    if isinstance(config, dict) and config.get(key) not in (None, ""):
        return _is_trueish(config.get(key))
    raw = str(os.getenv(env_key, "") or "").strip()
    if raw:
        return _is_trueish(raw)
    return bool(default)


def resolve_entry_cost_filter_config(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    strategy_monitor_policy: Dict[str, Any],
    entry_policy_input: Dict[str, Any],
    commander_entry_control: Dict[str, Any],
) -> Dict[str, Any]:
    policy_monitor = policy.get("monitor_policy") if isinstance(policy.get("monitor_policy"), dict) else {}
    config = _first_mapping(
        state.get("entry_cost_filter"),
        state.get("cost_filter"),
        commander_entry_control.get("cost_filter") if isinstance(commander_entry_control, dict) else {},
        entry_policy_input.get("cost_filter") if isinstance(entry_policy_input, dict) else {},
        strategy_monitor_policy.get("entry_cost_filter") if isinstance(strategy_monitor_policy, dict) else {},
        monitor_policy.get("entry_cost_filter") if isinstance(monitor_policy, dict) else {},
        policy_monitor.get("entry_cost_filter") if isinstance(policy_monitor, dict) else {},
        policy.get("entry_cost_filter") if isinstance(policy, dict) else {},
    )
    return {
        "schema_version": "entry_cost_filter.v1",
        "enabled": _config_bool(config, "enabled", "MONITOR_ENTRY_COST_FILTER_ENABLED", True),
        "buy_fee_rate": _config_float(config, "buy_fee_rate", "MONITOR_ENTRY_BUY_FEE_RATE", 0.00015),
        "sell_fee_rate": _config_float(config, "sell_fee_rate", "MONITOR_ENTRY_SELL_FEE_RATE", 0.00015),
        "sell_tax_rate": _config_float(config, "sell_tax_rate", "MONITOR_ENTRY_SELL_TAX_RATE", 0.0018),
        "min_buy_fee": _config_float(config, "min_buy_fee", "MONITOR_ENTRY_MIN_BUY_FEE", 0.0),
        "min_sell_fee": _config_float(config, "min_sell_fee", "MONITOR_ENTRY_MIN_SELL_FEE", 0.0),
        "max_cost_drag_pct": _config_float(config, "max_cost_drag_pct", "MONITOR_ENTRY_MAX_COST_DRAG_PCT", 0.006),
        "round_trip_cost_floor_pct": _config_float(
            config,
            "round_trip_cost_floor_pct",
            "MONITOR_ENTRY_ROUND_TRIP_COST_FLOOR_PCT",
            0.009,
        ),
        "min_net_profit_buffer_pct": _config_float(
            config,
            "min_net_profit_buffer_pct",
            "MONITOR_ENTRY_MIN_NET_PROFIT_BUFFER_PCT",
            0.003,
        ),
        "gross_edge_cost_multiplier": _config_float(
            config,
            "gross_edge_cost_multiplier",
            "MONITOR_ENTRY_GROSS_EDGE_COST_MULTIPLIER",
            1.5,
        ),
        "min_cost_adjusted_edge_pct": _config_float(
            config,
            "min_cost_adjusted_edge_pct",
            "MONITOR_ENTRY_MIN_COST_ADJUSTED_EDGE_PCT",
            0.001,
        ),
        "edge_scale_pct": _config_float(config, "edge_scale_pct", "MONITOR_ENTRY_EDGE_SCALE_PCT", 0.035),
        "quality_proxy_max_edge_pct": _config_float(
            config,
            "quality_proxy_max_edge_pct",
            "MONITOR_ENTRY_QUALITY_PROXY_MAX_EDGE_PCT",
            0.012,
        ),
        "require_directional_edge_evidence": _config_bool(
            config,
            "require_directional_edge_evidence",
            "MONITOR_ENTRY_REQUIRE_DIRECTIONAL_EDGE_EVIDENCE",
            True,
        ),
        "allow_volatility_proxy_edge": _config_bool(
            config,
            "allow_volatility_proxy_edge",
            "MONITOR_ENTRY_ALLOW_VOLATILITY_PROXY_EDGE",
            False,
        ),
        "allow_quality_proxy_edge": _config_bool(
            config,
            "allow_quality_proxy_edge",
            "MONITOR_ENTRY_ALLOW_QUALITY_PROXY_EDGE",
            False,
        ),
        "allow_triggered_signal_proxy_edge": _config_bool(
            config,
            "allow_triggered_signal_proxy_edge",
            "MONITOR_ENTRY_ALLOW_TRIGGERED_SIGNAL_PROXY_EDGE",
            True,
        ),
        "triggered_proxy_confidence_tolerance": _config_float(
            config,
            "triggered_proxy_confidence_tolerance",
            "MONITOR_ENTRY_TRIGGERED_PROXY_CONFIDENCE_TOLERANCE",
            0.0,
        ),
        "proxy_edge_haircut": _config_float(
            config,
            "proxy_edge_haircut",
            "MONITOR_ENTRY_PROXY_EDGE_HAIRCUT",
            0.35,
        ),
        "min_proxy_quality_score": _config_float(
            config,
            "min_proxy_quality_score",
            "MONITOR_ENTRY_MIN_PROXY_QUALITY_SCORE",
            0.80,
        ),
        "min_estimated_gross_edge_pct": _config_float(
            config,
            "min_estimated_gross_edge_pct",
            "MONITOR_ENTRY_MIN_ESTIMATED_GROSS_EDGE_PCT",
            0.0,
        ),
    }


def evaluate_entry_cost_filter(
    *,
    entry_info: Dict[str, Any],
    selected: Dict[str, Any],
    qty: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    enabled = bool(config.get("enabled"))
    metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
    scores = entry_info.get("condition_scores") if isinstance(entry_info.get("condition_scores"), dict) else {}
    price = _to_float(selected.get("price") or metrics.get("current_price") or metrics.get("price"))
    quantity = max(0, int(qty))
    notional = float(price * quantity) if price > 0.0 and quantity > 0 else 0.0
    raw_quality = scores.get("entry_quality_score")
    if raw_quality in (None, ""):
        raw_quality = metrics.get("entry_quality_score")
    quality_available = raw_quality not in (None, "")
    quality_score = _clamp(_to_float(raw_quality), 0.0, 1.0) if quality_available else 0.0

    buy_fee = max(float(notional) * _to_float(config.get("buy_fee_rate")), _to_float(config.get("min_buy_fee"))) if notional > 0.0 else 0.0
    sell_fee = max(float(notional) * _to_float(config.get("sell_fee_rate")), _to_float(config.get("min_sell_fee"))) if notional > 0.0 else 0.0
    sell_tax = float(notional) * _to_float(config.get("sell_tax_rate")) if notional > 0.0 else 0.0
    total_cost = float(buy_fee + sell_fee + sell_tax)
    cost_drag_pct = float(total_cost / notional) if notional > 0.0 else None
    round_trip_cost_floor_pct = _to_float(config.get("round_trip_cost_floor_pct"))
    effective_cost_drag_pct = (
        max(float(cost_drag_pct), float(round_trip_cost_floor_pct))
        if cost_drag_pct is not None
        else float(round_trip_cost_floor_pct)
        if round_trip_cost_floor_pct > 0.0
        else None
    )

    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    directional_candidates, proxy_candidates = _edge_candidates(
        selected=selected,
        metrics=metrics,
        features=features,
        price=price,
    )
    quality_proxy_raw = (
        max(0.0, quality_score - 0.50) * _to_float(config.get("edge_scale_pct"))
        if quality_available
        else 0.0
    )
    quality_proxy_cap = _to_float(config.get("quality_proxy_max_edge_pct"))
    quality_proxy_edge_pct = (
        min(float(quality_proxy_raw), float(quality_proxy_cap))
        if quality_proxy_cap > 0.0
        else float(quality_proxy_raw)
    )
    quality_modifier = float(0.50 + (0.50 * quality_score)) if quality_available else 0.0
    min_estimated_gross_edge_pct = _to_float(config.get("min_estimated_gross_edge_pct"))
    require_directional_edge_evidence = bool(config.get("require_directional_edge_evidence"))
    allow_volatility_proxy_edge = bool(config.get("allow_volatility_proxy_edge"))
    allow_quality_proxy_edge = bool(config.get("allow_quality_proxy_edge"))
    allow_triggered_signal_proxy_edge = bool(config.get("allow_triggered_signal_proxy_edge"))
    proxy_edge_haircut = _clamp(_to_float(config.get("proxy_edge_haircut")), 0.0, 1.0)
    min_proxy_quality_score = _clamp(_to_float(config.get("min_proxy_quality_score")), 0.0, 1.0)
    confidence_score = _to_float(scores.get("confidence_score") if scores.get("confidence_score") not in (None, "") else metrics.get("confidence_score"))
    confidence_threshold = _to_float(
        scores.get("confidence_threshold")
        if scores.get("confidence_threshold") not in (None, "")
        else metrics.get("confidence_threshold")
    )
    confidence_tolerance = max(0.0, _to_float(config.get("triggered_proxy_confidence_tolerance")))
    directional_candidates = [(name, value) for name, value in directional_candidates if value > 0.0]
    proxy_candidates = [(name, value) for name, value in proxy_candidates if value > 0.0]
    proxy_quality_ok = bool((not quality_available) or quality_score >= min_proxy_quality_score)
    confidence_gate_ok = bool(
        confidence_threshold <= 0.0
        or (
            confidence_score > 0.0
            and confidence_score + confidence_tolerance >= confidence_threshold
        )
    )
    triggered_signal_proxy_allowed = bool(
        allow_triggered_signal_proxy_edge
        and bool(entry_info.get("triggered"))
        and confidence_gate_ok
        and proxy_candidates
        and proxy_quality_ok
    )
    effective_allow_volatility_proxy_edge = bool(allow_volatility_proxy_edge or triggered_signal_proxy_allowed)
    effective_require_directional_edge_evidence = bool(
        require_directional_edge_evidence and not triggered_signal_proxy_allowed
    )
    estimated_gross_edge_pct, estimated_gross_edge_source, edge_evidence_type = _estimated_gross_edge(
        directional_candidates=directional_candidates,
        proxy_candidates=proxy_candidates,
        quality_available=quality_available,
        quality_modifier=quality_modifier,
        min_estimated_gross_edge_pct=min_estimated_gross_edge_pct,
        effective_allow_volatility_proxy_edge=effective_allow_volatility_proxy_edge,
        proxy_quality_ok=proxy_quality_ok,
        proxy_edge_haircut=proxy_edge_haircut,
        allow_quality_proxy_edge=allow_quality_proxy_edge,
        quality_proxy_edge_pct=quality_proxy_edge_pct,
        quality_proxy_raw=quality_proxy_raw,
    )
    cost_adjusted_edge_pct = (
        float(estimated_gross_edge_pct - float(effective_cost_drag_pct))
        if estimated_gross_edge_pct is not None and effective_cost_drag_pct is not None
        else None
    )
    gross_edge_cost_multiplier = max(1.0, _to_float(config.get("gross_edge_cost_multiplier"), 1.0))
    required_gross_edge_pct = (
        (float(effective_cost_drag_pct) * float(gross_edge_cost_multiplier))
        + _to_float(config.get("min_net_profit_buffer_pct"))
        if effective_cost_drag_pct is not None
        else None
    )
    fail_reasons = _entry_cost_fail_reasons(
        enabled=enabled,
        notional=notional,
        cost_drag_pct=cost_drag_pct,
        config=config,
        effective_require_directional_edge_evidence=effective_require_directional_edge_evidence,
        edge_evidence_type=edge_evidence_type,
        estimated_gross_edge_pct=estimated_gross_edge_pct,
        required_gross_edge_pct=required_gross_edge_pct,
        cost_adjusted_edge_pct=cost_adjusted_edge_pct,
    )

    passed = (not enabled) or not fail_reasons
    return {
        "schema_version": "entry_cost_filter_result.v1",
        "enabled": bool(enabled),
        "passed": bool(passed),
        "cost_adjusted_edge_ok": bool(passed),
        "fail_reasons": fail_reasons,
        "price": price if price > 0.0 else None,
        "qty": int(quantity),
        "notional": round(notional, 4),
        "buy_fee_est": round(buy_fee, 4),
        "sell_fee_est": round(sell_fee, 4),
        "sell_tax_est": round(sell_tax, 4),
        "round_trip_cost_est": round(total_cost, 4),
        "cost_drag_pct": round(float(cost_drag_pct), 6) if cost_drag_pct is not None else None,
        "round_trip_cost_floor_pct": round(float(round_trip_cost_floor_pct), 6),
        "effective_cost_drag_pct": (
            round(float(effective_cost_drag_pct), 6) if effective_cost_drag_pct is not None else None
        ),
        "cost_floor_applied": bool(
            cost_drag_pct is not None
            and effective_cost_drag_pct is not None
            and effective_cost_drag_pct > cost_drag_pct
        ),
        "min_net_profit_buffer_pct": float(config.get("min_net_profit_buffer_pct") or 0.0),
        "gross_edge_cost_multiplier": round(float(gross_edge_cost_multiplier), 6),
        "required_gross_edge_pct": (
            round(float(required_gross_edge_pct), 6) if required_gross_edge_pct is not None else None
        ),
        "entry_quality_available": bool(quality_available),
        "entry_quality_score": round(float(quality_score), 4),
        "quality_modifier": round(float(quality_modifier), 6),
        "quality_proxy_edge_pct": round(float(quality_proxy_edge_pct), 6),
        "directional_edge_required": bool(require_directional_edge_evidence),
        "effective_directional_edge_required": bool(effective_require_directional_edge_evidence),
        "directional_edge_available": bool(directional_candidates),
        "proxy_edge_available": bool(proxy_candidates),
        "proxy_edge_allowed": bool(allow_volatility_proxy_edge),
        "effective_proxy_edge_allowed": bool(effective_allow_volatility_proxy_edge),
        "quality_proxy_edge_allowed": bool(allow_quality_proxy_edge),
        "triggered_signal_proxy_edge_allowed": bool(triggered_signal_proxy_allowed),
        "allow_triggered_signal_proxy_edge": bool(allow_triggered_signal_proxy_edge),
        "confidence_score": round(float(confidence_score), 4) if confidence_score > 0.0 else None,
        "confidence_threshold": round(float(confidence_threshold), 4) if confidence_threshold > 0.0 else None,
        "triggered_proxy_confidence_tolerance": round(float(confidence_tolerance), 6),
        "proxy_quality_ok": bool(proxy_quality_ok),
        "proxy_edge_haircut": round(float(proxy_edge_haircut), 6),
        "min_proxy_quality_score": round(float(min_proxy_quality_score), 6),
        "edge_evidence_type": str(edge_evidence_type),
        "estimated_gross_edge_pct": round(float(estimated_gross_edge_pct), 6) if estimated_gross_edge_pct is not None else None,
        "estimated_gross_edge_source": str(estimated_gross_edge_source),
        "directional_edge_candidates": [
            {"source": str(name), "pct": round(float(value), 6)}
            for name, value in directional_candidates[:8]
        ],
        "proxy_edge_candidates": [
            {"source": str(name), "pct": round(float(value), 6)}
            for name, value in proxy_candidates[:8]
        ],
        "expected_move_candidates": [
            {"source": str(name), "pct": round(float(value), 6), "evidence_type": "directional"}
            for name, value in directional_candidates[:8]
        ]
        + [
            {"source": str(name), "pct": round(float(value), 6), "evidence_type": "proxy"}
            for name, value in proxy_candidates[:8]
        ],
        "cost_adjusted_edge_pct": round(float(cost_adjusted_edge_pct), 6) if cost_adjusted_edge_pct is not None else None,
        "max_cost_drag_pct": float(config.get("max_cost_drag_pct") or 0.0),
        "min_cost_adjusted_edge_pct": float(config.get("min_cost_adjusted_edge_pct") or 0.0),
    }


def _as_ratio(value: Any) -> float:
    ratio = _to_float(value)
    if ratio <= 0.0:
        return 0.0
    if ratio > 1.0:
        ratio = ratio / 100.0
    return float(ratio)


def _edge_candidates(
    *,
    selected: Dict[str, Any],
    metrics: Dict[str, Any],
    features: Dict[str, Any],
    price: float,
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    def _ratio_from_price(value: Any) -> float:
        target = _to_float(value)
        if price <= 0.0 or target <= price:
            return 0.0
        return float((target / price) - 1.0)

    directional_candidates: list[tuple[str, float]] = []
    proxy_candidates: list[tuple[str, float]] = []
    directional_ratio_keys = (
        "expected_gross_edge_pct",
        "expected_move_pct",
        "target_move_pct",
        "target_profit_pct",
        "take_profit_pct",
    )
    proxy_ratio_keys = ("recent_realized_move_pct", "recent_range_pct", "intraday_range_pct")
    directional_price_keys = ("target_price", "resistance_price", "target_resistance_price", "upper_resistance_price")
    for source_name, source in (("selected", selected), ("metrics", metrics), ("features", features)):
        if not isinstance(source, dict):
            continue
        for key in directional_ratio_keys:
            ratio = _as_ratio(source.get(key))
            if ratio > 0.0:
                directional_candidates.append((f"{source_name}.{key}", ratio))
        for key in directional_price_keys:
            ratio = _ratio_from_price(source.get(key))
            if ratio > 0.0:
                directional_candidates.append((f"{source_name}.{key}", ratio))
        for key in proxy_ratio_keys:
            ratio = _as_ratio(source.get(key))
            if ratio > 0.0:
                proxy_candidates.append((f"{source_name}.{key}", ratio))

    atr = _to_float(features.get("engine_atr14") or features.get("atr14") or metrics.get("atr14"))
    if atr > 0.0 and price > 0.0:
        proxy_candidates.append(("features.atr14_ratio", float(atr / price)))
    volatility_ratio = _as_ratio(features.get("engine_volatility20") or features.get("volatility20"))
    if volatility_ratio > 0.0:
        proxy_candidates.append(("features.volatility20", volatility_ratio))
    return directional_candidates, proxy_candidates


def _estimated_gross_edge(
    *,
    directional_candidates: list[tuple[str, float]],
    proxy_candidates: list[tuple[str, float]],
    quality_available: bool,
    quality_modifier: float,
    min_estimated_gross_edge_pct: float,
    effective_allow_volatility_proxy_edge: bool,
    proxy_quality_ok: bool,
    proxy_edge_haircut: float,
    allow_quality_proxy_edge: bool,
    quality_proxy_edge_pct: float,
    quality_proxy_raw: float,
) -> tuple[float | None, str, str]:
    if directional_candidates and quality_available:
        candidate_name, candidate_value = min(directional_candidates, key=lambda row: float(row[1]))
        return (
            max(float(min_estimated_gross_edge_pct), float(candidate_value) * float(quality_modifier)),
            f"{candidate_name}*quality_modifier",
            "directional",
        )
    if directional_candidates:
        candidate_name, candidate_value = min(directional_candidates, key=lambda row: float(row[1]))
        return max(float(min_estimated_gross_edge_pct), float(candidate_value)), str(candidate_name), "directional"
    if effective_allow_volatility_proxy_edge and proxy_candidates and proxy_quality_ok:
        candidate_name, candidate_value = min(proxy_candidates, key=lambda row: float(row[1]))
        proxy_modifier = float(proxy_edge_haircut)
        source = f"{candidate_name}*proxy_haircut"
        if quality_available:
            proxy_modifier *= float(quality_modifier)
            source = f"{source}*quality_modifier"
        return max(float(min_estimated_gross_edge_pct), float(candidate_value) * proxy_modifier), source, "proxy"
    if allow_quality_proxy_edge and quality_available and proxy_quality_ok:
        source = "quality_proxy_capped" if quality_proxy_edge_pct < quality_proxy_raw else "quality_proxy"
        return max(float(min_estimated_gross_edge_pct), float(quality_proxy_edge_pct)), source, "quality_proxy"
    return None, "", ""


def _entry_cost_fail_reasons(
    *,
    enabled: bool,
    notional: float,
    cost_drag_pct: float | None,
    config: Dict[str, Any],
    effective_require_directional_edge_evidence: bool,
    edge_evidence_type: str,
    estimated_gross_edge_pct: float | None,
    required_gross_edge_pct: float | None,
    cost_adjusted_edge_pct: float | None,
) -> list[str]:
    fail_reasons = []
    if not enabled:
        return fail_reasons
    if notional <= 0.0:
        fail_reasons.append("cost_filter_price_or_qty_missing")
    if cost_drag_pct is not None and cost_drag_pct > _to_float(config.get("max_cost_drag_pct")):
        fail_reasons.append("cost_drag_too_high")
    if effective_require_directional_edge_evidence and edge_evidence_type != "directional":
        fail_reasons.append("directional_edge_evidence_missing")
    if estimated_gross_edge_pct is None:
        fail_reasons.append("estimated_gross_edge_missing")
    if (
        estimated_gross_edge_pct is not None
        and required_gross_edge_pct is not None
        and estimated_gross_edge_pct < required_gross_edge_pct
    ):
        fail_reasons.append("estimated_gross_edge_below_cost_floor")
    if cost_adjusted_edge_pct is not None and cost_adjusted_edge_pct < _to_float(config.get("min_cost_adjusted_edge_pct")):
        fail_reasons.append("cost_adjusted_edge_below_min")
    return fail_reasons
