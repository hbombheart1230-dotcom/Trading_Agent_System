from __future__ import annotations

from typing import Any

from .contracts import CONTRACT_VERSION, EvidenceClass, IntegrityStatus
from .horizon_contract import evaluate_horizon_contract


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_trade(model: dict[str, Any]) -> dict[str, Any]:
    integrity = str((model.get("integrity") or {}).get("status") or IntegrityStatus.FAIL.value)
    net_return = _number((model.get("outcome") or {}).get("net_return_pct"))
    holding_seconds = _number((model.get("outcome") or {}).get("holding_seconds"))
    exit_reason = str((model.get("exit") or {}).get("reason") or "")
    defects = list((model.get("integrity") or {}).get("defects") or [])
    watch_items = list((model.get("integrity") or {}).get("watch_items") or [])

    if net_return is None:
        result_label = "unavailable"
    elif net_return > 0:
        result_label = "win"
    elif net_return < 0:
        result_label = "loss"
    else:
        result_label = "flat"

    if holding_seconds is not None and holding_seconds < 60 and "hard" not in exit_reason.lower():
        watch_items.append("sub_60_second_exit")
    if net_return is not None and net_return < 0 and "profit" in exit_reason.lower():
        watch_items.append("exit_reason_outcome_conflict")

    broker_unresolved = "broker_closed_trade_unresolved" in defects
    partial_exit_duplicate = "broker_day_partial_exit_duplicate" in defects
    eligible = (
        integrity in {IntegrityStatus.PASS.value, IntegrityStatus.WATCH.value}
        and net_return is not None
        and not broker_unresolved
        and not partial_exit_duplicate
    )
    post_exit = (model.get("monitor") or {}).get("post_exit")
    post_exit = post_exit if isinstance(post_exit, dict) else {}
    checkpoints = post_exit.get("checkpoints") if isinstance(post_exit.get("checkpoints"), dict) else {}
    observed_checkpoints = {
        key: value
        for key, value in checkpoints.items()
        if isinstance(value, dict) and str(value.get("status") or "") == "observed"
    }
    horizon_alignment = evaluate_horizon_contract(
        contract=model.get("horizon_contract") or {},
        actual_hold_sec=holding_seconds,
        exit_reason=exit_reason,
        net_return_pct=net_return,
        post_exit=post_exit,
    )
    if horizon_alignment.get("horizon_violation_candidate"):
        watch_items.append("horizon_violation_candidate")
    if horizon_alignment.get("exited_before_min_hold"):
        watch_items.append("exit_before_strategy_min_hold")
    elif horizon_alignment.get("exited_before_target_hold"):
        watch_items.append("exit_before_strategy_target_hold")
    return {
        "schema_version": "trade_evaluation.v1",
        "contract_version": CONTRACT_VERSION,
        "trade_id": model.get("trade_id"),
        "day": model.get("day"),
        "symbol": model.get("symbol"),
        "evidence_class": EvidenceClass.REALIZED.value if eligible else EvidenceClass.UNAVAILABLE.value,
        "integrity": {
            "status": integrity,
            "promotion_metric_eligible": eligible,
            "defects": defects,
            "watch_items": sorted(set(watch_items)),
        },
        "realized_outcome": {
            "net_return_pct": net_return,
            "result_label": result_label,
            "holding_seconds": holding_seconds,
        },
        "entry_quality": {
            "status": "observed" if model.get("entry") else "unavailable",
            "reason": (model.get("entry") or {}).get("reason"),
        },
        "exit_quality": {
            "status": "observed" if observed_checkpoints else "diagnostic_only",
            "reason": exit_reason,
            "label": "ambiguous",
            "post_exit_comparison": "available" if observed_checkpoints else "unavailable",
            "observed_checkpoints": observed_checkpoints,
            "best_exit_offset": post_exit.get("best_exit_offset"),
            "best_exit_price": post_exit.get("best_exit_price"),
            "max_post_exit_upside_pct": post_exit.get("max_post_exit_upside_pct"),
            "max_post_exit_drawdown_pct": post_exit.get("max_post_exit_drawdown_pct"),
        },
        "horizon_alignment": horizon_alignment,
        "tactic_alignment": {
            "playbook": (model.get("selection") or {}).get("strategist_playbook"),
            "selected_rank": (model.get("selection") or {}).get("selected_rank"),
        },
        "selection_context": model.get("selection") or {},
        "evidence_references": model.get("provenance") or {},
    }
