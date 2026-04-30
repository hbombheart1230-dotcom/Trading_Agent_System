from __future__ import annotations

from typing import Any, Dict


def build_trade_report_truth_surface(shared_facts: Dict[str, Any] | None) -> Dict[str, Any]:
    facts = shared_facts if isinstance(shared_facts, dict) else {}
    broker_fill_price = facts.get("broker_fill_price")
    broker_buy_price = facts.get("broker_buy_price")
    account_mark_price = facts.get("account_mark_price")
    monitor_mark_price = facts.get("monitor_mark_price")
    pnl_truth_source = str(facts.get("pnl_truth_source") or "").strip() or "unavailable"
    pnl_value = facts.get("pnl")
    raw_pnl_pct = facts.get("pnl_pct")
    pnl_data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}
    broker_pnl_present = pnl_truth_source not in {"", "unavailable", "not_available"}
    pnl_pct_is_fallback = str(pnl_data_source.get("pnl_pct") or "").strip().lower() == "fallback"
    if (
        not broker_pnl_present
        and str(pnl_value or "").strip().lower() in {"", "unavailable", "not_available", "none", "-"}
        and pnl_pct_is_fallback
    ):
        pnl_pct = None
        pnl_pct_display = raw_pnl_pct
        pnl_pct_display_role = "fallback_mark_only"
    else:
        pnl_pct = raw_pnl_pct
        pnl_pct_display = raw_pnl_pct
        pnl_pct_display_role = "truth"

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
            "broker_day_match_mode": facts.get("broker_day_match_mode"),
            "broker_day_authoritative": bool(facts.get("broker_day_authoritative")),
            "broker_day_row_count": facts.get("broker_day_row_count"),
            "broker_truth_error": facts.get("broker_truth_error"),
            "broker_day_truth_error": facts.get("broker_day_truth_error"),
        },
        "availability": {
            "broker_fill_present": broker_fill_price not in (None, ""),
            "broker_buy_present": broker_buy_price not in (None, ""),
            "account_mark_present": account_mark_price not in (None, ""),
            "monitor_mark_present": monitor_mark_price not in (None, ""),
            "broker_pnl_present": broker_pnl_present,
            "broker_day_authoritative": bool(facts.get("broker_day_authoritative")),
            "broker_truth_attempted": bool(facts.get("broker_truth_attempted")),
            "broker_day_truth_attempted": bool(facts.get("broker_day_truth_attempted")),
        },
    }
