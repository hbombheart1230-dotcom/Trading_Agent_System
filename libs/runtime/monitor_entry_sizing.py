from __future__ import annotations

from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.price_resolution import resolve_price


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


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _is_falseish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("0", "false", "no", "n", "off")


def _has_strategy_policy_content(strategy_policy: Any) -> bool:
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


def position_by_symbol(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    snapshot = state.get("portfolio_snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("positions"), list):
        for row in snapshot.get("positions") or []:
            _add_position_row(out, row)
        return out

    snaps = state.get("snapshots")
    if isinstance(snaps, dict):
        port = snaps.get("portfolio")
        if isinstance(port, dict) and isinstance(port.get("positions"), list):
            for row in port.get("positions") or []:
                _add_position_row(out, row)
    return out


def _add_position_row(out: Dict[str, Dict[str, Any]], row: Any) -> None:
    if not isinstance(row, dict):
        return
    symbol = normalize_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
    if not symbol:
        return
    normalized_row = dict(row)
    normalized_row["symbol"] = symbol
    out[symbol] = normalized_row


def resolve_cash(state: Dict[str, Any]) -> float:
    risk_context = state.get("risk_context")
    if isinstance(risk_context, dict):
        cash = _to_float(risk_context.get("capital_available_for_sizing"))
        if cash > 0.0:
            return cash
    snapshot = state.get("portfolio_snapshot")
    if isinstance(snapshot, dict):
        cash = _to_float(snapshot.get("cash"))
        if cash > 0.0:
            return cash
    snaps = state.get("snapshots")
    if isinstance(snaps, dict):
        port = snaps.get("portfolio")
        if isinstance(port, dict):
            cash = _to_float(port.get("cash"))
            if cash > 0.0:
                return cash
    return 0.0


def portfolio_exposure(state: Dict[str, Any], price_fallback: float = 0.0) -> float:
    cash = resolve_cash(state)
    pos_map = position_by_symbol(state)
    invested = 0.0
    for row in pos_map.values():
        qty = max(0, _to_int(row.get("qty")))
        if qty <= 0:
            continue
        price = _to_float(row.get("price"))
        if price <= 0.0:
            price = _to_float(row.get("avg_price"))
        if price <= 0.0:
            price = price_fallback
        if price <= 0.0:
            continue
        invested += float(qty) * float(price)
    denom = cash + invested
    if denom <= 0.0:
        return 0.0
    return float(invested / denom)


def build_sizing_risk_context(state: Dict[str, Any], selected: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    risk_context = dict(state.get("risk_context") or {}) if isinstance(state.get("risk_context"), dict) else {}
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    if not _has_strategy_policy_content(strategy_policy) and isinstance(state.get("strategy_policy"), dict):
        strategy_policy = dict(state.get("strategy_policy") or {})
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    monitor_policy = state.get("monitor_policy") if isinstance(state.get("monitor_policy"), dict) else {}
    if isinstance(strategy_monitor_policy.get("position_guards"), dict):
        monitor_policy = {**dict(strategy_monitor_policy.get("position_guards") or {}), **monitor_policy}
    if isinstance(strategist_output.get("monitor_policy"), dict):
        monitor_policy = {**dict(strategist_output.get("monitor_policy") or {}), **monitor_policy}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    regime = str(features.get("engine_regime") or selected.get("regime") or policy.get("regime") or "").strip().lower()
    vol20 = _to_float(features.get("engine_volatility20"))
    vol_pct = _to_float(policy.get("volatility_percentile"))
    if vol_pct <= 0.0 and vol20 > 0.0:
        vol_pct = min(max(vol20 / 0.05, 0.0), 1.0)

    price = resolve_price(state, symbol, selected) or 0.0
    exposure = portfolio_exposure(state, price_fallback=float(price))
    corr_bucket = str(policy.get("correlation_bucket") or "medium").strip().lower()
    daily_pnl_ratio = _to_float(risk_context.get("daily_pnl_ratio"))
    daily_loss_limit = abs(_to_float(policy.get("risk_daily_loss_limit")))
    if daily_loss_limit <= 0.0:
        daily_loss_limit = 0.02
    daily_loss_state = daily_pnl_ratio <= -daily_loss_limit if daily_loss_limit > 0 else False
    degrade_mode = bool(state.get("degrade_mode"))
    resilience_state = state.get("resilience_state") if isinstance(state.get("resilience_state"), dict) else {}
    if str(resilience_state.get("mode") or "").strip().lower() == "degrade":
        degrade_mode = True

    risk_context.update(
        {
            "regime": regime or None,
            "volatility_percentile": float(vol_pct),
            "portfolio_exposure": float(exposure),
            "correlation_bucket": corr_bucket,
            "daily_loss_state": bool(daily_loss_state),
            "degrade_mode": bool(degrade_mode),
        }
    )
    return risk_context


def resolve_position_sizing_config(
    state: Dict[str, Any],
    *,
    policy: Dict[str, Any],
    strategy_policy: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    def _merge(candidate: Any, out: Dict[str, Any]) -> None:
        if isinstance(candidate, dict):
            out.update(dict(candidate))

    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_monitor = applied_policy.get("monitor") if isinstance(applied_policy.get("monitor"), dict) else {}
    applied_entry = applied_monitor.get("entry") if isinstance(applied_monitor.get("entry"), dict) else {}
    strategy_entry = strategy_policy.get("entry_policy") if isinstance(strategy_policy.get("entry_policy"), dict) else {}

    sizing_policy: Dict[str, Any] = {}
    _merge(applied_entry.get("position_sizing"), sizing_policy)
    _merge(applied_policy.get("position_sizing"), sizing_policy)
    _merge(strategy_entry.get("position_sizing"), sizing_policy)
    _merge(policy.get("position_sizing"), sizing_policy)
    _merge(state.get("position_sizing"), sizing_policy)

    for key in (
        "risk_per_trade_ratio",
        "stop_loss_pct",
        "use_structure_stop_loss",
        "use_structure_stop_loss_for_sizing",
        "min_structure_stop_loss_pct",
        "invalidation_price",
        "stop_price",
        "structural_stop_price",
        "position_notional_ratio",
        "max_position_qty",
        "max_order_qty",
        "max_position_notional",
        "max_order_notional",
        "min_position_qty",
        "lot_size",
    ):
        if key in policy and policy.get(key) not in (None, ""):
            sizing_policy[key] = policy.get(key)

    explicit_enabled = None
    if state.get("use_position_sizing") is not None:
        explicit_enabled = _is_trueish(state.get("use_position_sizing"))
    elif policy.get("use_position_sizing") is not None:
        explicit_enabled = _is_trueish(policy.get("use_position_sizing"))

    enabled = bool(explicit_enabled) if explicit_enabled is not None else _is_trueish(sizing_policy.get("enabled"))
    return bool(enabled), sizing_policy


def derive_position_sizing_stop_context(
    *,
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any],
    entry_info: Dict[str, Any],
    price: float | None,
    sizing_policy: Dict[str, Any],
) -> Dict[str, Any]:
    px = _to_float(price)
    out: Dict[str, Any] = {
        "applied": False,
        "reason": "unavailable",
        "stop_loss_pct": None,
        "invalidation_price": None,
        "stop_loss_source": "",
        "raw_stop_loss_pct": None,
        "min_structure_stop_loss_pct": None,
        "candidates": [],
    }
    if px <= 0.0:
        out["reason"] = "price_unavailable"
        return out
    if _is_falseish(sizing_policy.get("use_structure_stop_loss_for_sizing")) or _is_falseish(
        sizing_policy.get("use_structure_stop_loss")
    ):
        out["reason"] = "disabled_by_policy"
        return out

    candidates: list[Dict[str, Any]] = []

    def add_candidate(name: str, raw: Any, source: str, *, explicit: bool = False) -> None:
        anchor = _to_float(raw)
        if anchor <= 0.0 or anchor >= px:
            return
        pct = (px - anchor) / px
        if pct <= 0.0:
            return
        candidates.append(
            {
                "name": str(name),
                "price": float(anchor),
                "stop_loss_pct": float(pct),
                "source": str(source),
                "explicit": bool(explicit),
            }
        )

    for key in ("invalidation_price", "stop_price", "structural_stop_price"):
        add_candidate(key, sizing_policy.get(key), f"position_sizing.{key}", explicit=True)
        add_candidate(key, selected.get(key), f"selected.{key}", explicit=True)
    explicit_candidates = [row for row in candidates if bool(row.get("explicit"))]
    if explicit_candidates:
        chosen = max(explicit_candidates, key=lambda row: float(row.get("price") or 0.0))
    else:
        metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
        text_bits = [
            str(entry_info.get("pattern") or ""),
            str(entry_info.get("reason") or ""),
            str(entry_info.get("entry_condition_path") or ""),
            " ".join(str(x or "") for x in list(entry_info.get("signal_chain") or [])),
            " ".join(str(x or "") for x in list(entry_info.get("entry_condition_paths_passed") or [])),
        ]
        entry_text = " ".join(text_bits).lower()
        vwap, vwap_source = _entry_context_float(selected, entry_info, "vwap")
        thresholds = entry_info.get("thresholds") if isinstance(entry_info.get("thresholds"), dict) else {}
        reclaim_tolerance_pct = max(0.0, _to_float(thresholds.get("reclaim_tolerance_pct")))
        if vwap > 0.0:
            add_candidate("vwap_floor", vwap * (1.0 - reclaim_tolerance_pct), f"{vwap_source}.reclaim_tolerance")
        for key in ("breakout_level", "recent_high", "prior_bar_high", "prior_bar_low", "current_low"):
            value, source = _entry_context_float(selected, entry_info, key)
            if value > 0.0:
                add_candidate(key, value, source)

        has_breakout = "breakout" in entry_text
        has_vwap = "vwap" in entry_text or bool(metrics.get("vwap_structure_ok"))
        has_pullback = "pullback" in entry_text or "rebound" in entry_text
        preferred_names: set[str] = set()
        if has_breakout:
            preferred_names.update({"breakout_level", "recent_high", "vwap_floor", "prior_bar_low"})
        if has_vwap:
            preferred_names.update({"vwap_floor", "prior_bar_low", "current_low"})
        if has_pullback:
            preferred_names.update({"prior_bar_low", "current_low", "vwap_floor"})
        scoped = [row for row in candidates if str(row.get("name") or "") in preferred_names] if preferred_names else []
        chosen_pool = scoped or candidates
        if not chosen_pool:
            out["reason"] = "no_structure_anchor_below_price"
            return out
        chosen = max(chosen_pool, key=lambda row: float(row.get("price") or 0.0))

    raw_stop_loss_pct = float(chosen.get("stop_loss_pct") or 0.0)
    if raw_stop_loss_pct <= 0.0:
        out["reason"] = "invalid_structure_stop_loss_pct"
        return out
    min_stop_loss_pct = max(0.0, _to_float(sizing_policy.get("min_structure_stop_loss_pct")))
    if min_stop_loss_pct <= 0.0:
        min_stop_loss_pct = 0.008
    stop_loss_pct = max(raw_stop_loss_pct, min_stop_loss_pct)
    invalidation_price = float(px * (1.0 - stop_loss_pct)) if stop_loss_pct > raw_stop_loss_pct else float(chosen["price"])
    stop_loss_source = str(chosen.get("source") or chosen.get("name") or "structure")
    if stop_loss_pct > raw_stop_loss_pct:
        stop_loss_source = f"{stop_loss_source}:min_structure_stop_floor"

    out.update(
        {
            "applied": True,
            "reason": "structure_stop_loss_derived",
            "stop_loss_pct": float(stop_loss_pct),
            "invalidation_price": float(invalidation_price),
            "stop_loss_source": stop_loss_source,
            "raw_stop_loss_pct": float(raw_stop_loss_pct),
            "min_structure_stop_loss_pct": float(min_stop_loss_pct),
            "candidates": candidates[:8],
        }
    )
    return out


def _entry_context_float(
    selected: Dict[str, Any],
    entry_info: Dict[str, Any],
    key: str,
) -> tuple[float, str]:
    metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    candidates = [
        (metrics.get(key), f"entry.metrics.{key}"),
        (selected.get(key), f"selected.{key}"),
        (features.get(key), f"selected.features.{key}"),
    ]
    if key == "prior_bar_low":
        candidates.append((selected.get("_monitor_prior_bar_low"), "selected._monitor_prior_bar_low"))
    for raw, source in candidates:
        value = _to_float(raw)
        if value > 0.0:
            return float(value), source
    return 0.0, ""
