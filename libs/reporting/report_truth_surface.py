from __future__ import annotations

from typing import Any, Dict


def build_trade_report_truth_surface(shared_facts: Dict[str, Any] | None) -> Dict[str, Any]:
    facts = shared_facts if isinstance(shared_facts, dict) else {}
    broker_fill_price = facts.get("broker_fill_price")
    account_mark_price = facts.get("account_mark_price")
    monitor_mark_price = facts.get("monitor_mark_price")
    pnl_truth_source = str(facts.get("pnl_truth_source") or "").strip() or "unavailable"

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
            "account_mark_price": account_mark_price,
            "monitor_mark_price": monitor_mark_price,
            "price_truth_source": facts.get("price_truth_source"),
            "monitor_price_source": facts.get("monitor_price_source"),
        },
        "pnl": {
            "value": facts.get("pnl"),
            "pct": facts.get("pnl_pct"),
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
            "account_mark_present": account_mark_price not in (None, ""),
            "monitor_mark_present": monitor_mark_price not in (None, ""),
            "broker_pnl_present": pnl_truth_source not in {"", "unavailable", "not_available"},
            "broker_day_authoritative": bool(facts.get("broker_day_authoritative")),
            "broker_truth_attempted": bool(facts.get("broker_truth_attempted")),
            "broker_day_truth_attempted": bool(facts.get("broker_day_truth_attempted")),
        },
    }
