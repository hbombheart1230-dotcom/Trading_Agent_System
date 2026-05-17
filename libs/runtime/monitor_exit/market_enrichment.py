from __future__ import annotations

from typing import Any, Dict

from libs.runtime.etf_deviation import extract_etf_deviation_signal
from libs.runtime.monitor_exit.adapters.state_data import quote_for_symbol
from libs.runtime.monitor_exit.numeric import to_float
from libs.runtime.monitor_exit.vwap_state_adapter import (
    fresh_minute_vwap_distance_for_symbol,
    vwap_breakdown_confirmation_for_symbol,
)


def enrich_exit_policy_with_market_inputs(
    *,
    state: Dict[str, Any],
    symbol: str,
    selected_for_exit: Dict[str, Any],
    features: Dict[str, Any],
    price: float | None,
    exit_policy_map: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(exit_policy_map or {})
    quote = quote_for_symbol(state, symbol)
    if quote:
        for source_key, policy_key in (
            ("best_bid", "expected_exit_best_bid"),
            ("bid", "expected_exit_best_bid"),
            ("bid_price", "expected_exit_best_bid"),
            ("best_ask", "expected_exit_best_ask"),
            ("ask", "expected_exit_best_ask"),
            ("ask_price", "expected_exit_best_ask"),
            ("spread_bps", "expected_exit_spread_bps"),
        ):
            value = quote.get(source_key)
            if value not in (None, "") and to_float(value) > 0.0:
                out.setdefault(policy_key, value)

    deviation_signal = extract_etf_deviation_signal(
        symbol=symbol,
        candidate=selected_for_exit,
        features=features,
        quote=quote,
        state=state,
        asset_class_detected=features.get("asset_class_detected") or selected_for_exit.get("asset_class_detected"),
    )
    if deviation_signal.get("etf_deviation_pct") is not None:
        out.setdefault("etf_deviation_pct", deviation_signal.get("etf_deviation_pct"))
        out.setdefault("etf_deviation_source", deviation_signal.get("etf_deviation_source"))
    if deviation_signal.get("asset_class_detected"):
        out.setdefault("asset_class_detected", deviation_signal.get("asset_class_detected"))

    fresh_vwap_distance, fresh_vwap_distance_source = fresh_minute_vwap_distance_for_symbol(
        state,
        symbol,
        price=price,
    )
    if fresh_vwap_distance is not None:
        out["vwap_distance"] = float(fresh_vwap_distance)
        out["vwap_distance_source"] = str(fresh_vwap_distance_source)
    elif features.get("engine_vwap_distance") is not None:
        out.setdefault("vwap_distance", features.get("engine_vwap_distance"))
        out.setdefault("vwap_distance_source", "selected.features.engine_vwap_distance")

    vwap_breakdown_pct = to_float(out.get("vwap_breakdown_pct"))
    if vwap_breakdown_pct > 0.0:
        confirmation = vwap_breakdown_confirmation_for_symbol(
            state,
            symbol,
            threshold=vwap_breakdown_pct,
            volume_ratio=(
                selected_for_exit.get("volume_ratio")
                if selected_for_exit.get("volume_ratio") not in (None, "")
                else features.get("volume_ratio")
            ),
            volume_ratio_min=out.get("vwap_breakdown_volume_ratio_min"),
            low_break_pct=out.get("vwap_breakdown_low_break_pct"),
        )
        for key, value in confirmation.items():
            out[key] = value

    if features.get("engine_trend_strength") is not None:
        out.setdefault("trend_strength", features.get("engine_trend_strength"))
    return out


def enrich_exit_policy_with_signal_inputs(
    *,
    state: Dict[str, Any],
    selected_for_exit: Dict[str, Any],
    features: Dict[str, Any],
    exit_policy_map: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(exit_policy_map or {})
    for signal_key in (
        "volume_ratio",
        "execution_strength",
        "trade_strength",
        "previous_close",
        "open_gap_pct",
        "prev_close_distance_pct",
        "opening_gap_chase_observed",
        "minutes_since_session_open",
    ):
        value = selected_for_exit.get(signal_key)
        if value in (None, ""):
            value = features.get(signal_key)
        if value in (None, ""):
            entry_info = state.get("monitor_entry") if isinstance(state.get("monitor_entry"), dict) else {}
            entry_metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
            value = entry_metrics.get(signal_key)
        if value not in (None, ""):
            out.setdefault(signal_key, value)

    for resistance_key in (
        "resistance_price",
        "target_resistance_price",
        "upper_resistance_price",
        "day_high",
        "intraday_high",
        "recent_high",
        "breakout_level",
        "prior_bar_high",
    ):
        value = selected_for_exit.get(resistance_key)
        if value in (None, ""):
            value = features.get(resistance_key)
        if value not in (None, "") and to_float(value) > 0.0:
            out.setdefault(resistance_key, value)
    prior_bar_low = to_float(selected_for_exit.get("_monitor_prior_bar_low"))
    if prior_bar_low > 0.0:
        out.setdefault("prior_bar_low", prior_bar_low)
    return out
