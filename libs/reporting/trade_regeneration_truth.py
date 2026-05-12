from __future__ import annotations

from typing import Any, Dict, Mapping
from libs.reporting.trade_execution_truth_merge import (
    merge_preferred_execution_details,
    prefer_richer_execution_details,
)


def _minimal_rebuild_execution_details(details: Mapping[str, Any] | None) -> Dict[str, Any]:
    details_obj = dict(details or {})
    out: Dict[str, Any] = {}
    for key in (
        "order_id",
        "order_status",
        "filled_qty",
        "filled_price",
        "avg_price",
        "fill_status",
        "symbol",
        "action",
        "side",
        "ts",
        "broker_truth_source",
    ):
        if details_obj.get(key) not in (None, "", [], {}):
            out[key] = details_obj.get(key)
    return out


def _rehydrate_side_execution_details(
    side_ctx: Mapping[str, Any] | None,
    *,
    trade_day: str,
    entry_execution_details: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    from libs.reporting.trade_bundle_assembly import build_execution_details_from_bundle

    side_obj = dict(side_ctx or {})
    return build_execution_details_from_bundle(
        {
            "execution": dict(side_obj.get("execution") or {}),
            "executor": dict(side_obj.get("executor") or {}),
            "monitor": dict(side_obj.get("monitor_context") or {}),
            "execution_details": _minimal_rebuild_execution_details(side_obj.get("execution_details")),
        },
        context={
            "trade_day": trade_day,
            "action": side_obj.get("action"),
            "symbol": side_obj.get("symbol"),
            "ts": side_obj.get("ts"),
            "broker_fill_lookup_enabled": True,
            "broker_day_truth_lookup_enabled": True,
            "monitor_context": dict(side_obj.get("monitor_context") or {}),
            "execution_context": {},
            "execution_details": _minimal_rebuild_execution_details(side_obj.get("execution_details")),
            "entry_execution_details": dict(entry_execution_details or {}),
        },
    )


def rehydrate_lifecycle_bundle_execution_truth(
    lifecycle_bundle: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    bundle_obj = dict(lifecycle_bundle or {})
    trade_day = str(bundle_obj.get("day") or "").strip()
    status = str(bundle_obj.get("trade_lifecycle_status") or "").strip().lower()

    entry_ctx = dict(bundle_obj.get("entry") or {}) if isinstance(bundle_obj.get("entry"), dict) else {}
    exit_ctx = dict(bundle_obj.get("exit") or {}) if isinstance(bundle_obj.get("exit"), dict) else {}

    if entry_ctx:
        rebuilt_entry = _rehydrate_side_execution_details(entry_ctx, trade_day=trade_day)
        if prefer_richer_execution_details(entry_ctx.get("execution_details"), rebuilt_entry):
            entry_ctx["execution_details"] = merge_preferred_execution_details(entry_ctx.get("execution_details"), rebuilt_entry)
            bundle_obj["entry"] = entry_ctx
            bundle_obj["entry_execution_details"] = dict(entry_ctx.get("execution_details") or {})

    if exit_ctx:
        effective_entry_execution = (
            dict(bundle_obj.get("entry_execution_details") or {})
            if isinstance(bundle_obj.get("entry_execution_details"), dict)
            else dict((entry_ctx.get("execution_details") or {}) if isinstance(entry_ctx.get("execution_details"), dict) else {})
        )
        rebuilt_exit = _rehydrate_side_execution_details(
            exit_ctx,
            trade_day=trade_day,
            entry_execution_details=effective_entry_execution,
        )
        if prefer_richer_execution_details(exit_ctx.get("execution_details"), rebuilt_exit):
            exit_ctx["execution_details"] = merge_preferred_execution_details(exit_ctx.get("execution_details"), rebuilt_exit)
            bundle_obj["exit"] = exit_ctx
            bundle_obj["exit_execution_details"] = dict(exit_ctx.get("execution_details") or {})

    if status == "closed" and isinstance(bundle_obj.get("exit_execution_details"), dict):
        bundle_obj["execution_details"] = dict(bundle_obj.get("exit_execution_details") or {})
    elif isinstance(bundle_obj.get("entry_execution_details"), dict):
        bundle_obj["execution_details"] = dict(bundle_obj.get("entry_execution_details") or {})

    lifecycle = dict(bundle_obj.get("lifecycle") or {}) if isinstance(bundle_obj.get("lifecycle"), dict) else {}
    if lifecycle:
        if isinstance(lifecycle.get("entry"), dict) and isinstance(bundle_obj.get("entry_execution_details"), dict):
            lifecycle_entry = dict(lifecycle.get("entry") or {})
            lifecycle_entry["execution_details"] = dict(bundle_obj.get("entry_execution_details") or {})
            lifecycle["entry"] = lifecycle_entry
        if isinstance(lifecycle.get("exit"), dict) and isinstance(bundle_obj.get("exit_execution_details"), dict):
            lifecycle_exit = dict(lifecycle.get("exit") or {})
            lifecycle_exit["execution_details"] = dict(bundle_obj.get("exit_execution_details") or {})
            lifecycle["exit"] = lifecycle_exit
        if isinstance(bundle_obj.get("execution_details"), dict):
            lifecycle["execution_details"] = dict(bundle_obj.get("execution_details") or {})
        bundle_obj["lifecycle"] = lifecycle

    return bundle_obj


__all__ = ["rehydrate_lifecycle_bundle_execution_truth"]
