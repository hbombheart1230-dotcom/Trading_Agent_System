from __future__ import annotations

from typing import Any, Dict, List


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


def _fallback_mark_pct(*, buy_price: Any, account_mark_price: Any, monitor_mark_price: Any) -> float | None:
    buy = _num_opt(buy_price)
    mark = _num_opt(account_mark_price)
    if mark is None or mark <= 0:
        mark = _num_opt(monitor_mark_price)
    if buy is None or buy <= 0 or mark is None or mark <= 0:
        return None
    return (mark - buy) / buy


def resolve_trade_truth(shared_facts: Dict[str, Any] | None) -> Dict[str, Any]:
    facts = shared_facts if isinstance(shared_facts, dict) else {}
    pnl_value = facts.get("pnl")
    raw_pnl_pct = facts.get("pnl_pct")
    pnl_data_source = facts.get("data_source") if isinstance(facts.get("data_source"), dict) else {}
    pnl_truth_source = str(facts.get("pnl_truth_source") or "").strip() or "unavailable"
    broker_day_authoritative = bool(facts.get("broker_day_authoritative"))
    pnl_pct_source = str(pnl_data_source.get("pnl_pct") or "").strip().lower()
    broker_fill_price_num = _num_opt(facts.get("broker_fill_price"))
    fill_snapshot_estimate_without_valid_fill = (
        pnl_pct_source == "broker_fill_account_snapshot_estimate"
        and (broker_fill_price_num is None or broker_fill_price_num <= 0)
    )
    pnl_pct_is_fallback = pnl_pct_source == "fallback" or fill_snapshot_estimate_without_valid_fill
    if pnl_pct_is_fallback:
        raw_pnl_pct = _fallback_mark_pct(
            buy_price=facts.get("broker_buy_price"),
            account_mark_price=facts.get("account_mark_price"),
            monitor_mark_price=facts.get("monitor_mark_price"),
        )

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

    warnings: List[str] = []
    if pnl_pct_display_role == "fallback_mark_only":
        warnings.append("realized_pnl_pct_unavailable_fallback_mark_only")
    if not broker_day_authoritative and _has_truth_value(raw_pnl_pct) and not pnl_value_present:
        warnings.append("broker_day_pct_observation_only")

    authority = "broker_day" if broker_day_authoritative and broker_pnl_present else ""
    if not authority and pnl_value_present:
        authority = str(pnl_truth_source or "local_realized")
    if not authority and pnl_pct_display_role == "fallback_mark_only":
        authority = "fallback_mark_only"
    if not authority:
        authority = "unavailable"

    confidence = "high" if broker_day_authoritative and broker_pnl_present else "low"
    if pnl_value_present and confidence == "low":
        confidence = "medium"

    return {
        "schema_version": "trade_truth_resolution.v1",
        "authoritative_pnl_krw": pnl_value if pnl_value_present else None,
        "authoritative_pct": pnl_pct,
        "pct_basis": pnl_pct_display_role,
        "authority": authority,
        "fallback_pct": pnl_pct_display if pnl_pct_display_role != "truth" else None,
        "fallback_role": pnl_pct_display_role if pnl_pct_display_role != "truth" else "",
        "confidence": confidence,
        "warnings": warnings,
        "broker_pnl_present": bool(broker_pnl_present),
        "pnl_value_present": bool(pnl_value_present),
        "pnl_pct": pnl_pct,
        "pnl_pct_display": pnl_pct_display,
        "pnl_pct_display_role": pnl_pct_display_role,
        "pnl_pct_is_fallback": bool(pnl_pct_is_fallback),
        "pnl_pct_is_unconfirmed": bool(pnl_pct_is_unconfirmed),
    }
