from __future__ import annotations

from typing import Any, Dict


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def infer_exit_fill_pnl_pct_from_account_snapshot(story_input: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = story_input if isinstance(story_input, dict) else {}
    exit_details = payload.get("exit_execution_details") if isinstance(payload.get("exit_execution_details"), dict) else {}
    canonical_monitor = payload.get("canonical_monitor") if isinstance(payload.get("canonical_monitor"), dict) else {}
    monitor_reason = payload.get("monitor_reason_human") if isinstance(payload.get("monitor_reason_human"), dict) else {}

    exit_fill_price = _safe_float(exit_details.get("filled_price"))
    current_price = (
        _safe_float(canonical_monitor.get("current_price"))
        or _safe_float(monitor_reason.get("current_price"))
    )
    account_pnl_ratio = (
        _safe_float(canonical_monitor.get("account_pnl_ratio"))
        if canonical_monitor.get("account_pnl_ratio") not in (None, "")
        else _safe_float(canonical_monitor.get("effective_pnl_ratio"))
    )
    if account_pnl_ratio is None:
        account_pnl_ratio = _safe_float(monitor_reason.get("account_pnl_ratio"))

    if exit_fill_price is None or current_price is None or account_pnl_ratio is None:
        return {}
    if current_price <= 0 or account_pnl_ratio <= -0.999:
        return {}

    implied_entry_basis = current_price / (1.0 + account_pnl_ratio)
    if implied_entry_basis <= 0:
        return {}

    inferred_pct = (exit_fill_price / implied_entry_basis) - 1.0
    return {
        "pnl_pct": inferred_pct,
        "pnl_truth_source": "broker_fill_account_snapshot_estimate",
        "implied_entry_basis": implied_entry_basis,
        "estimate_inputs": {
            "exit_fill_price": exit_fill_price,
            "current_price": current_price,
            "account_pnl_ratio": account_pnl_ratio,
        },
    }
