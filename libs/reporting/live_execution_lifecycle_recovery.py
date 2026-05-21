from __future__ import annotations

import re
from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.reporting.trade_story_pipeline import safe_int


RECOVERED_FULL_CLOSEOUT_MIN_QTY = 1000


def max_positive_int(*values: Any) -> int:
    out = 0
    for value in values:
        parsed = safe_int(value, 0)
        if parsed > out:
            out = parsed
    return int(out)


def remaining_qty_hint(*sources: Any) -> int | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("remaining_qty_hint", "remaining_qty", "position_remaining_qty"):
            if key not in source:
                continue
            parsed = safe_int(source.get(key), -1)
            if parsed >= 0:
                return int(parsed)
    return None


def hold_placeholder_reason(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = re.sub(r"^sell\s+was\s+triggered\s+because\s*", "", text, flags=re.IGNORECASE)
    normalized = normalized.strip().strip(".").strip().lower()
    return normalized in {"hold", "hold_position", "holding", "보유", "보유 유지"} or "because hold" in text.lower()


def refresh_closed_sell_lifecycle_summary(
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    summary_obj: Dict[str, Any],
    execution_details: Dict[str, Any],
    status: str,
) -> Dict[str, Any]:
    """Keep human-readable lifecycle text aligned after partial->closed reconciliation."""

    if str(status or "").strip().lower() != "closed":
        return dict(summary_obj or {})
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    bundle_execution = lifecycle_bundle.get("execution") if isinstance(lifecycle_bundle.get("execution"), dict) else {}
    action = str(
        exit_ctx.get("action")
        or (execution_details.get("action") if isinstance(execution_details, dict) else "")
        or bundle_execution.get("action")
        or ""
    ).strip().upper()
    if action != "SELL":
        return dict(summary_obj or {})

    out = dict(summary_obj or {})
    trade_id = str(lifecycle.get("trade_id") or lifecycle_bundle.get("trade_id") or "").strip()
    symbol = normalize_symbol(
        lifecycle.get("symbol") or lifecycle_bundle.get("symbol") or (lifecycle_bundle.get("execution") or {}).get("symbol") or "",
        allow_test_symbols=True,
    )
    entry_reason = str(out.get("entry_reason_human") or "").strip() or (
        "Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts."
    )
    execution_close_status = "sell_execution_full_close_confirmed"
    execution_close_status_human = "SELL 실행 및 잔여수량 0 확인으로 전량 청산됐습니다."
    raw_exit_reason = str(out.get("exit_reason_human") or exit_ctx.get("reason_human") or "").strip()
    exit_reason_missing = not raw_exit_reason or hold_placeholder_reason(raw_exit_reason)
    if exit_reason_missing:
        exit_reason = "exit_trigger_not_captured"
        exit_reason_human = "모니터 청산 트리거 미확인"
    else:
        exit_reason = raw_exit_reason
        exit_reason_human = raw_exit_reason

    lifecycle_summary = str(out.get("lifecycle_summary_human") or "").strip()
    stale_summary = (
        not lifecycle_summary
        or " is partial" in lifecycle_summary.lower()
        or "current lifecycle status is partial" in lifecycle_summary.lower()
        or hold_placeholder_reason(lifecycle_summary)
    )
    if stale_summary:
        out["lifecycle_summary_human"] = (
            f"Trade {trade_id or '-'} for {symbol or '-'} is closed. "
            f"Entry: {entry_reason} Exit trigger: {exit_reason_human}. Execution: {execution_close_status_human}"
        )
    out["status"] = "closed"
    out["action"] = "SELL"
    out["exit_reason_human"] = exit_reason_human
    out["exit_reason"] = exit_reason
    out["exit_execution_status"] = execution_close_status
    out["exit_execution_status_human"] = execution_close_status_human
    operator_text = str(out.get("operator_conclusion_human") or "").strip()
    if not operator_text or "partial" in operator_text.lower() or hold_placeholder_reason(operator_text):
        out["operator_conclusion_human"] = (
            f"현재 판단은 청산 완료입니다. {symbol or '해당 종목'}은 SELL 실행과 잔여수량 0 확인으로 종료됐습니다."
        )

    lifecycle["summary"] = dict(out)
    lifecycle["status"] = "closed"
    lifecycle["action"] = "SELL"
    lifecycle["exit_reason"] = exit_reason
    lifecycle["exit_reason_human"] = exit_reason_human
    lifecycle["exit_execution_status"] = execution_close_status
    lifecycle["exit_execution_status_human"] = execution_close_status_human
    lifecycle_bundle["trade_lifecycle_status"] = "closed"
    lifecycle_bundle["trade_lifecycle_summary"] = str(out.get("lifecycle_summary_human") or "")
    lifecycle_bundle["exit_execution_status"] = execution_close_status
    lifecycle_bundle["exit_execution_status_human"] = execution_close_status_human
    lifecycle_bundle["trade_lifecycle"] = lifecycle
    conclusion = lifecycle_bundle.get("operator_conclusion_human")
    if isinstance(conclusion, dict):
        summary = str(conclusion.get("summary") or "")
        if not summary or "partial" in summary.lower() or hold_placeholder_reason(summary):
            conclusion = dict(conclusion)
            conclusion["summary"] = str(out.get("operator_conclusion_human") or "")
            conclusion["current_action"] = "SELL"
            lifecycle_bundle["operator_conclusion_human"] = conclusion
    return out


def reconcile_partial_full_sell_lifecycle(
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    execution_details: Dict[str, Any],
) -> str:
    """Promote recovered partial SELL lifecycles to closed when quantity proves full liquidation."""

    status = str((lifecycle or {}).get("status") or "").strip().lower()
    if status != "partial":
        return status
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    if str(exit_ctx.get("action") or "").strip().upper() != "SELL":
        return status
    entry_reason = str(entry_ctx.get("reason_human") or "").strip().lower()
    entry_has_execution_evidence = bool(str(entry_ctx.get("ts") or "").strip()) and str(
        entry_ctx.get("action") or ""
    ).strip().upper() == "BUY"

    exit_execution_details = (
        exit_ctx.get("execution_details") if isinstance(exit_ctx.get("execution_details"), dict) else {}
    )
    exit_execution_context = (
        exit_ctx.get("execution_context") if isinstance(exit_ctx.get("execution_context"), dict) else {}
    )
    entry_qty = max_positive_int(
        entry_ctx.get("qty"),
        entry_ctx.get("filled_qty"),
        lifecycle.get("entry_qty"),
        lifecycle_bundle.get("entry_qty") if isinstance(lifecycle_bundle, dict) else None,
    )
    exit_qty = max_positive_int(
        exit_ctx.get("filled_qty"),
        exit_ctx.get("qty"),
        execution_details.get("filled_qty") if isinstance(execution_details, dict) else None,
        execution_details.get("qty") if isinstance(execution_details, dict) else None,
        exit_execution_details.get("filled_qty"),
        exit_execution_details.get("qty"),
        exit_execution_context.get("filled_qty"),
        exit_execution_context.get("qty"),
    )
    remaining_hint = remaining_qty_hint(
        lifecycle,
        lifecycle_bundle,
        execution_details,
        exit_execution_details,
        exit_execution_context,
    )
    closes_by_qty = bool(entry_qty > 0 and exit_qty > 0 and exit_qty >= entry_qty)
    closes_by_hint = bool(exit_qty > 0 and remaining_hint == 0)
    recovered_sell_only_large_closeout = bool(
        exit_qty >= RECOVERED_FULL_CLOSEOUT_MIN_QTY
        and (
            not entry_has_execution_evidence
            or "entry evidence was not captured" in entry_reason
        )
    )
    if (
        (not entry_has_execution_evidence or "entry evidence was not captured" in entry_reason)
        and not recovered_sell_only_large_closeout
    ):
        return status
    if not (closes_by_qty or closes_by_hint):
        return status

    lifecycle["status"] = "closed"
    lifecycle["remaining_qty"] = 0
    lifecycle["recovered_partial_closed_by_quantity"] = True
    if recovered_sell_only_large_closeout:
        lifecycle["recovered_partial_closed_by_large_closeout_qty"] = True
    lifecycle.setdefault("warnings", [])
    if isinstance(lifecycle.get("warnings"), list):
        lifecycle["warnings"].append("partial_status_reconciled_to_closed_full_sell")
    if isinstance(lifecycle_bundle, dict):
        lifecycle_bundle["trade_lifecycle_status"] = "closed"
        lifecycle_bundle["remaining_qty"] = 0
        lifecycle_bundle["recovered_partial_closed_by_quantity"] = True
        if recovered_sell_only_large_closeout:
            lifecycle_bundle["recovered_partial_closed_by_large_closeout_qty"] = True
    return "closed"
