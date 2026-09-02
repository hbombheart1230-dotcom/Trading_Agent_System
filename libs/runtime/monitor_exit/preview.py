from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any, Dict

from libs.runtime.exit_policy import evaluate_exit_policy
from libs.runtime.monitor_exit.policy_map_builder import build_monitor_exit_policy_map
from libs.runtime.monitor_exit.position_tracking import position_hold_seconds, update_position_peak_price
from libs.runtime.monitor_exit.price_resolution import (
    position_live_price_with_source,
    position_mark_price_with_source,
    resolve_price_with_source,
)
from libs.runtime.monitor_exit.selected_snapshot import monitor_selected_snapshot_for_symbol


HARD_STOP_CONFLICT_REVALIDATION_AFTER_SEC = 60


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


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    for key in ("tick_ts", "ts"):
        try:
            value = int(float(state.get(key)))
        except Exception:
            continue
        if value > 0:
            return value
    return int(time.time())


def _replace_stale_quote_with_position_price(
    *,
    state: Dict[str, Any],
    symbol: str,
    selected_for_exit: Dict[str, Any],
    position: Dict[str, Any],
    price: float | None,
    price_source: str,
) -> tuple[float | None, str, Dict[str, Any]]:
    observed_epoch = _to_int(selected_for_exit.get("_monitor_quote_observed_epoch"))
    now_epoch = _resolve_now_epoch(state)
    quote_age_sec = max(0, now_epoch - observed_epoch) if observed_epoch > 0 else None
    position_price, position_source = position_live_price_with_source(
        position, requested_symbol=symbol
    )
    current = _to_float(price)
    account_price = _to_float(position_price)
    divergence_pct = (
        abs(current / account_price - 1.0)
        if current > 0.0 and account_price > 0.0
        else None
    )
    quote_source = str(price_source or "").startswith("market.quote.")
    quote_stale = bool(quote_source and quote_age_sec is not None and quote_age_sec > 90)
    quote_unverifiable_and_divergent = bool(
        quote_source
        and quote_age_sec is None
        and divergence_pct is not None
        and divergence_pct > 0.015
    )
    replaced = bool(
        account_price > 0.0 and (quote_stale or quote_unverifiable_and_divergent)
    )
    rejected = bool(quote_stale and account_price <= 0.0)
    evidence = {
        "quote_observed_epoch": observed_epoch or None,
        "quote_age_sec": quote_age_sec,
        "quote_stale": quote_stale,
        "quote_account_divergence_pct": divergence_pct,
        "quote_freshness_unverifiable": bool(quote_source and quote_age_sec is None),
        "stale_quote_replaced": replaced,
        "stale_quote_rejected": rejected,
        "replacement_source": position_source if replaced else "",
    }
    if replaced:
        return float(account_price), str(position_source), evidence
    if rejected:
        return None, "stale_market_quote_rejected", evidence
    return price, price_source, evidence


def _revalidate_conflicting_hard_stop_price(
    *,
    symbol: str,
    position: Dict[str, Any],
    price: float | None,
    price_source: str,
    price_freshness: Dict[str, Any],
    avg_price: float,
    qty: int,
    hold_sec: int,
    policy: Dict[str, Any],
    initial_decision: Dict[str, Any],
) -> tuple[Dict[str, Any], float | None, str, Dict[str, Any]]:
    evidence = dict(price_freshness or {})
    evidence.setdefault(
        "hard_stop_conflict_revalidation_after_sec",
        HARD_STOP_CONFLICT_REVALIDATION_AFTER_SEC,
    )
    evidence.setdefault("hard_stop_conflict_revalidation_applied", False)
    quote_age_sec = evidence.get("quote_age_sec")
    try:
        quote_age = int(float(quote_age_sec))
    except Exception:
        quote_age = 0
    if (
        not str(price_source or "").startswith("market.quote.")
        or quote_age <= HARD_STOP_CONFLICT_REVALIDATION_AFTER_SEC
    ):
        return initial_decision, price, price_source, evidence

    account_price, account_source = position_live_price_with_source(
        position, requested_symbol=symbol
    )
    account_value = _to_float(account_price)
    if account_value <= 0.0:
        evidence["hard_stop_conflict_revalidation_reason"] = (
            "account_current_price_unavailable"
        )
        return initial_decision, price, price_source, evidence

    account_decision = evaluate_exit_policy(
        price=account_value,
        avg_price=avg_price if avg_price > 0.0 else None,
        qty=qty,
        hold_sec=hold_sec if hold_sec > 0 else None,
        policy=policy,
    )
    cached_says_stop = str(initial_decision.get("reason") or "") == "hard_stop"
    account_says_stop = str(account_decision.get("reason") or "") == "hard_stop"
    evidence["hard_stop_cached_quote_says_stop"] = cached_says_stop
    evidence["hard_stop_account_price_says_stop"] = account_says_stop
    evidence["hard_stop_account_price"] = float(account_value)
    evidence["hard_stop_account_price_source"] = str(account_source)
    if cached_says_stop == account_says_stop:
        evidence["hard_stop_conflict_revalidation_reason"] = "stop_outcome_aligned"
        return initial_decision, price, price_source, evidence

    evidence["hard_stop_conflict_revalidation_applied"] = True
    evidence["hard_stop_conflict_revalidation_reason"] = (
        "cached_and_account_stop_outcome_conflict"
    )
    evidence["replacement_source"] = str(account_source)
    return account_decision, float(account_value), str(account_source), evidence


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
    price, price_source, price_freshness = _replace_stale_quote_with_position_price(
        state=state,
        symbol=symbol,
        selected_for_exit=selected_for_exit,
        position=position,
        price=price,
        price_source=price_source,
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
            observed_price_symbol=str(selected_for_exit.get("symbol") or symbol),
            observed_price_source=str(price_source or ""),
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
    decision, price, price_source, price_freshness = (
        _revalidate_conflicting_hard_stop_price(
            symbol=symbol,
            position=position,
            price=price,
            price_source=price_source,
            price_freshness=price_freshness,
            avg_price=avg_price,
            qty=qty,
            hold_sec=hold_sec,
            policy=exit_policy_map,
            initial_decision=decision,
        )
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
    decision["price_freshness"] = dict(price_freshness)
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
