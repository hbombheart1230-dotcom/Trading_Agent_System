from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _source_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_account_price_source(value: Any) -> bool:
    token = _source_text(value)
    if not token:
        return False
    return any(marker in token for marker in ("account", "portfolio", "kt00018"))


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def resolve_trade_price_truth(story_input: Mapping[str, Any] | None) -> Dict[str, Any]:
    story = dict(story_input or {})
    execution_details = _mapping(story.get("exit_execution_details")) or _mapping(story.get("execution_details"))
    entry_execution_details = _mapping(story.get("entry_execution_details"))
    monitor_snapshot = _mapping(story.get("monitor_reason_human"))
    broker_fill_price = _safe_float(
        execution_details.get("filled_price")
        if execution_details.get("broker_truth_source")
        else None
    )
    broker_buy_price = _safe_float(
        execution_details.get("broker_buy_price")
        if execution_details.get("broker_day_authoritative") or execution_details.get("broker_day_truth_source")
        else None
    )
    if broker_buy_price is None and entry_execution_details.get("broker_truth_source"):
        broker_buy_price = _safe_float(entry_execution_details.get("filled_price"))
    monitor_current_price = _safe_float(monitor_snapshot.get("current_price"))
    price_source = _source_text(monitor_snapshot.get("price_source"))

    account_mark_price = monitor_current_price if _is_account_price_source(price_source) else None
    monitor_mark_price = monitor_current_price if monitor_current_price is not None and account_mark_price is None else None

    if broker_fill_price is not None:
        price_truth_source = "broker_fill"
    elif account_mark_price is not None:
        price_truth_source = "account_mark"
    elif monitor_mark_price is not None:
        price_truth_source = "monitor_mark"
    else:
        price_truth_source = "unavailable"

    return {
        "broker_fill_price": broker_fill_price,
        "broker_buy_price": broker_buy_price,
        "account_mark_price": account_mark_price,
        "monitor_mark_price": monitor_mark_price,
        "price_truth_source": price_truth_source,
        "monitor_price_source": price_source or "unavailable",
    }


__all__ = ["resolve_trade_price_truth"]
