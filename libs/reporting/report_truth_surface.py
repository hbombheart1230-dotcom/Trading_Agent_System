from __future__ import annotations

from typing import Any, Dict

from libs.reporting.trade_truth_resolver import resolve_trade_truth


def _num_opt(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _broker_day_match_confidence(match_mode: Any, authoritative: bool) -> Dict[str, str]:
    mode = str(match_mode or "").strip().lower()
    if not mode:
        return {"broker_day_match_status": "missing", "broker_day_match_confidence": "unknown"}
    if "ambiguous" in mode:
        return {"broker_day_match_status": "ambiguous", "broker_day_match_confidence": "low"}
    if "estimated" in mode or "monitor_buy_anchor" in mode:
        return {
            "broker_day_match_status": "estimated" if authoritative else "ambiguous",
            "broker_day_match_confidence": "medium" if authoritative else "low",
        }
    if authoritative:
        if "exact" in mode or mode in {"single_symbol_row", "symbol_account_profit_row"}:
            return {"broker_day_match_status": "exact", "broker_day_match_confidence": "high"}
        return {"broker_day_match_status": "matched", "broker_day_match_confidence": "medium"}
    return {"broker_day_match_status": "unconfirmed", "broker_day_match_confidence": "low"}


def build_trade_report_truth_surface(shared_facts: Dict[str, Any] | None) -> Dict[str, Any]:
    facts = shared_facts if isinstance(shared_facts, dict) else {}
    raw_broker_fill_price = facts.get("broker_fill_price")
    broker_fill_price_num = _num_opt(raw_broker_fill_price)
    broker_fill_price = None if broker_fill_price_num is not None and broker_fill_price_num <= 0 else raw_broker_fill_price
    broker_buy_price = facts.get("broker_buy_price")
    account_mark_price = facts.get("account_mark_price")
    monitor_mark_price = facts.get("monitor_mark_price")
    pnl_truth_source = str(facts.get("pnl_truth_source") or "").strip() or "unavailable"
    pnl_value = facts.get("pnl")
    broker_day_authoritative = bool(facts.get("broker_day_authoritative"))
    match_mode = facts.get("broker_day_match_mode")
    match_confidence = _broker_day_match_confidence(match_mode, broker_day_authoritative)
    truth_resolution = resolve_trade_truth(facts)
    broker_pnl_present = bool(truth_resolution.get("broker_pnl_present"))
    pnl_pct = truth_resolution.get("pnl_pct")
    pnl_pct_display = truth_resolution.get("pnl_pct_display")
    pnl_pct_display_role = str(truth_resolution.get("pnl_pct_display_role") or "truth")

    return {
        "status": {
            "symbol": facts.get("symbol"),
            "trade_id": facts.get("trade_id"),
            "action": facts.get("action"),
            "status": facts.get("status"),
            "holding_duration": facts.get("holding_duration"),
            "exit_reason": facts.get("exit_reason"),
        },
        "price": {
            "broker_fill_price": broker_fill_price,
            "broker_buy_price": broker_buy_price,
            "account_mark_price": account_mark_price,
            "monitor_mark_price": monitor_mark_price,
            "price_truth_source": facts.get("price_truth_source"),
            "monitor_price_source": facts.get("monitor_price_source"),
        },
        "pnl": {
            "value": pnl_value,
            "pct": pnl_pct,
            "pct_display": pnl_pct_display,
            "pct_display_role": pnl_pct_display_role,
            "broker_fee": facts.get("broker_fee"),
            "broker_tax": facts.get("broker_tax"),
            "pnl_truth_source": pnl_truth_source,
            "broker_day_truth_source": facts.get("broker_day_truth_source"),
            "broker_day_match_mode": match_mode,
            "broker_day_authoritative": broker_day_authoritative,
            "broker_day_row_count": facts.get("broker_day_row_count"),
            **match_confidence,
            "broker_truth_error": facts.get("broker_truth_error"),
            "broker_day_truth_error": facts.get("broker_day_truth_error"),
        },
        "availability": {
            "broker_fill_present": broker_fill_price not in (None, ""),
            "broker_buy_present": broker_buy_price not in (None, ""),
            "account_mark_present": account_mark_price not in (None, ""),
            "monitor_mark_present": monitor_mark_price not in (None, ""),
            "broker_pnl_present": broker_pnl_present,
            "broker_day_authoritative": broker_day_authoritative,
            **match_confidence,
            "broker_truth_attempted": bool(facts.get("broker_truth_attempted")),
            "broker_day_truth_attempted": bool(facts.get("broker_day_truth_attempted")),
        },
    }
