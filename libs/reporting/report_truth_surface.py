from __future__ import annotations

from typing import Any, Dict


def _num_opt(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _has_truth_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {
        "",
        "-",
        "none",
        "null",
        "unavailable",
        "not_available",
    }


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


def _fallback_mark_pct(*, buy_price: Any, account_mark_price: Any, monitor_mark_price: Any) -> float | None:
    buy = _num_opt(buy_price)
    mark = _num_opt(account_mark_price)
    if mark is None or mark <= 0:
        mark = _num_opt(monitor_mark_price)
    if buy is None or buy <= 0 or mark is None or mark <= 0:
        return None
    return (mark - buy) / buy


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
    raw_pnl_pct = facts.get("pnl_pct")
    pnl_data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}
    broker_day_authoritative = bool(facts.get("broker_day_authoritative"))
    match_mode = facts.get("broker_day_match_mode")
    match_confidence = _broker_day_match_confidence(match_mode, broker_day_authoritative)
    pnl_pct_source = str(pnl_data_source.get("pnl_pct") or "").strip().lower()
    fill_snapshot_estimate_without_valid_fill = (
        pnl_pct_source == "broker_fill_account_snapshot_estimate"
        and (broker_fill_price_num is None or broker_fill_price_num <= 0)
    )
    pnl_pct_is_fallback = pnl_pct_source == "fallback" or fill_snapshot_estimate_without_valid_fill
    if pnl_pct_is_fallback:
        mark_pct = _fallback_mark_pct(
            buy_price=broker_buy_price,
            account_mark_price=account_mark_price,
            monitor_mark_price=monitor_mark_price,
        )
        raw_pnl_pct = mark_pct
    pnl_value_present = _has_truth_value(pnl_value)
    broker_pnl_present = pnl_value_present or (
        broker_day_authoritative
        and _has_truth_value(raw_pnl_pct)
        and not pnl_pct_is_fallback
        and pnl_truth_source not in {"", "unavailable", "not_available"}
    )
    pnl_pct_is_unconfirmed = pnl_pct_is_fallback or (not broker_day_authoritative and not pnl_value_present)
    if (
        not broker_pnl_present
        and not pnl_value_present
        and pnl_pct_is_unconfirmed
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
