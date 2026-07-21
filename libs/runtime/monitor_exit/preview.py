from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict

from libs.runtime.exit_policy import evaluate_exit_policy
from libs.runtime.monitor_exit.policy_map_builder import build_monitor_exit_policy_map
from libs.runtime.monitor_exit.position_tracking import position_hold_seconds, update_position_peak_price
from libs.runtime.monitor_exit.price_resolution import position_mark_price_with_source, resolve_price_with_source
from libs.runtime.monitor_exit.selected_snapshot import monitor_selected_snapshot_for_symbol


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def preview_exit_decision_for_symbol(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
    selected_snapshot_resolver: Callable[..., Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    qty = max(0, _to_int(position.get("qty")))
    avg_price = _to_float(position.get("avg_price"))
    snapshot_resolver = selected_snapshot_resolver or monitor_selected_snapshot_for_symbol
    selected_for_exit = snapshot_resolver(
        state,
        symbol,
        selected if isinstance(selected, dict) else None,
        position=position,
    )
    price, price_source = resolve_price_with_source(
        state,
        symbol,
        selected_for_exit,
        position=position,
    )
    if price is None or _to_float(price) <= 0.0:
        pos_mark, pos_mark_source = position_mark_price_with_source(position)
        if pos_mark is not None and pos_mark > 0.0:
            price = float(pos_mark)
            price_source = str(pos_mark_source or "position_mark")
    if _to_float(price) > 0.0 and avg_price > 0.0:
        peak_price = update_position_peak_price(
            state,
            symbol,
            avg_price=avg_price,
            observed_price=_to_float(price),
        )
    else:
        peak_price = 0.0

    features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
    feature_source = str(selected_for_exit.get("_monitor_feature_source") or "none")
    hold_sec = position_hold_seconds(state, symbol, position)
    if hold_sec <= 0:
        hold_sec = _to_int(state.get("position_hold_sec"))

    exit_policy_map = build_monitor_exit_policy_map(
        state=state,
        symbol=symbol,
        position=position,
        selected_for_exit=selected_for_exit,
        features=features,
        price=price,
        peak_price=peak_price,
        exit_policy_base=exit_policy_base,
    )

    decision = evaluate_exit_policy(
        price=price,
        avg_price=avg_price if avg_price > 0.0 else None,
        qty=qty,
        hold_sec=hold_sec if hold_sec > 0 else None,
        policy=exit_policy_map,
    )
    resolved_peak_price = _to_float(exit_policy_map.get("peak_price"))
    if resolved_peak_price <= 0.0:
        resolved_peak_price = float(peak_price)
    decision["_qty"] = int(qty)
    decision["_price"] = float(price) if price is not None and _to_float(price) > 0.0 else None
    decision["_avg_price"] = float(avg_price) if avg_price > 0.0 else None
    decision["_peak_price"] = float(resolved_peak_price) if resolved_peak_price > 0.0 else None
    decision["_hold_sec"] = int(hold_sec) if hold_sec > 0 else None
    decision["_pnl_ratio"] = _to_float(decision.get("pnl_ratio"))
    decision["_price_source"] = str(price_source or "unavailable")
    decision["_feature_source"] = str(feature_source or "none")
    decision["position_entry_risk_applied"] = bool(exit_policy_map.get("position_entry_risk_applied"))
    decision["position_entry_stop_loss_pct"] = exit_policy_map.get("position_entry_stop_loss_pct")
    decision["position_entry_stop_loss_source"] = str(exit_policy_map.get("position_entry_stop_loss_source") or "")
    decision["position_entry_invalidation_price"] = exit_policy_map.get("position_entry_invalidation_price")
    decision["etf_deviation_pct"] = exit_policy_map.get("etf_deviation_pct")
    decision["etf_deviation_source"] = str(exit_policy_map.get("etf_deviation_source") or "")
    decision["asset_class_detected"] = str(exit_policy_map.get("asset_class_detected") or "")
    decision["engine_vwap_distance_rejected"] = bool(exit_policy_map.get("engine_vwap_distance_rejected"))
    decision["engine_vwap_distance_rejected_value"] = exit_policy_map.get("engine_vwap_distance_rejected_value")
    decision["engine_vwap_distance_rejected_reason"] = str(
        exit_policy_map.get("engine_vwap_distance_rejected_reason") or ""
    )
    return decision
