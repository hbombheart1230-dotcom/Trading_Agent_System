from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from libs.core.symbols import normalize_symbol
from libs.reporting.trade_story_pipeline import safe_int

_ORDER_ID_PATTERN = re.compile(r"(?:ord_no|order_id|order)\s*[:=]\s*([A-Za-z0-9_]+)", re.IGNORECASE)


def _null_if_empty(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _extract_order_id_from_texts(text_values: Iterable[Any]) -> Optional[str]:
    for text in list(text_values or []):
        if not isinstance(text, str) or not text.strip():
            continue
        match = _ORDER_ID_PATTERN.search(text)
        if match:
            return str(match.group(1) or "").strip() or None
    return None


def normalize_execution_row(
    payload: Mapping[str, Any] | None,
    *,
    run_id: str = "",
    ts: str = "",
    source: str = "",
) -> Dict[str, Any]:
    raw = dict(payload or {})
    order = raw.get("order") if isinstance(raw.get("order"), dict) else {}
    broker = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    response_payload = broker.get("response_payload") if isinstance(broker.get("response_payload"), dict) else {}
    broker_result = raw.get("broker_result") if isinstance(raw.get("broker_result"), dict) else {}
    order_request = raw.get("order_request_summary") if isinstance(raw.get("order_request_summary"), dict) else {}

    action = str(
        raw.get("action")
        or order.get("action")
        or order_request.get("action")
        or ""
    ).strip().upper()
    symbol = normalize_symbol(
        raw.get("symbol")
        or order.get("symbol")
        or order.get("stk_cd")
        or order_request.get("symbol")
        or order_request.get("stk_cd")
        or "",
        allow_test_symbols=True,
    )
    qty = safe_int(
        raw.get("qty"),
        safe_int(
            raw.get("filled_qty"),
            safe_int(
                order.get("qty"),
                safe_int(
                    order.get("ord_qty"),
                    safe_int(
                        order_request.get("qty"),
                        safe_int(order_request.get("ord_qty"), 0),
                    ),
                ),
            ),
        ),
    )

    order_id = _null_if_empty(
        raw.get("order_id")
        or raw.get("ord_no")
        or broker_result.get("order_id")
        or broker_result.get("ord_no")
        or broker.get("order_id")
        or response_payload.get("order_id")
        or response_payload.get("ord_no")
    )
    fill_status = _null_if_empty(
        raw.get("fill_status")
        or raw.get("fill_status_summary")
        or raw.get("status")
        or raw.get("final_execution_status")
        or broker_result.get("status")
        or broker.get("broker_message")
        or response_payload.get("return_msg")
    )
    filled_price = _null_if_empty(
        _safe_float(raw.get("filled_price"), None)
        if raw.get("filled_price") not in (None, "")
        else _safe_float(raw.get("avg_price"), None)
        if raw.get("avg_price") not in (None, "")
        else _safe_float(raw.get("price"), None)
        if raw.get("price") not in (None, "")
        else _safe_float(raw.get("order_price"), None)
        if raw.get("order_price") not in (None, "")
        else _safe_float(broker_result.get("avg_price"), None)
        if broker_result.get("avg_price") not in (None, "")
        else _safe_float(broker_result.get("price"), None)
        if broker_result.get("price") not in (None, "")
        else _safe_float(order_request.get("price"), None)
        if order_request.get("price") not in (None, "")
        else None
    )
    filled_qty = _null_if_empty(
        raw.get("filled_qty")
        if raw.get("filled_qty") not in (None, "")
        else raw.get("qty")
        if raw.get("qty") not in (None, "")
        else broker_result.get("qty")
        if broker_result.get("qty") not in (None, "")
        else order_request.get("qty")
    )
    order_id = order_id or _extract_order_id_from_texts(
        (
            raw.get("broker_message"),
            raw.get("status_text"),
            raw.get("summary"),
            broker.get("broker_message"),
            response_payload.get("return_msg"),
        )
    )

    resolved_run_id = str(raw.get("run_id") or run_id or "").strip()
    resolved_ts = str(raw.get("ts") or ts or "").strip()

    return {
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "status": str(fill_status or ""),
        "ord_no": str(order_id or ""),
        "order_id": order_id,
        "filled_qty": filled_qty,
        "filled_price": filled_price,
        "fill_status": fill_status,
        "run_id": resolved_run_id,
        "ts": resolved_ts,
        "source": str(source or ""),
    }


def score_execution_snapshot(snapshot: Mapping[str, Any] | None) -> int:
    snap = dict(snapshot or {})
    score = 0
    if str(snap.get("action") or "").strip():
        score += 12
    if str(snap.get("symbol") or "").strip():
        score += 12
    if _null_if_empty(snap.get("order_id")):
        score += 22
    if _null_if_empty(snap.get("fill_status")):
        score += 12
    if _null_if_empty(snap.get("filled_qty")) not in (None, 0, 0.0):
        score += 20
    if _null_if_empty(snap.get("filled_price")) is not None:
        score += 16
    if str(snap.get("run_id") or "").strip():
        score += 3
    if str(snap.get("ts") or "").strip():
        score += 3
    return score


def _is_snapshot_degraded_but_usable(snapshot: Mapping[str, Any] | None) -> bool:
    snap = dict(snapshot or {})
    action = str(snap.get("action") or "").strip()
    symbol = str(snap.get("symbol") or "").strip()
    has_exec_identity = bool(_null_if_empty(snap.get("order_id")) or _null_if_empty(snap.get("fill_status")))
    has_fill_evidence = (
        _null_if_empty(snap.get("filled_price")) is not None
        or _null_if_empty(snap.get("filled_qty")) not in (None, 0, 0.0)
    )
    return bool(action and symbol and (has_exec_identity or has_fill_evidence))


def merge_execution_snapshot_candidates(
    candidates: Iterable[Mapping[str, Any] | None],
    *,
    run_id: str = "",
    ts: str = "",
) -> Dict[str, Any]:
    normalized_rows: List[Dict[str, Any]] = []
    for idx, candidate in enumerate(list(candidates or [])):
        if not isinstance(candidate, Mapping):
            continue
        normalized = normalize_execution_row(
            candidate,
            run_id=run_id,
            ts=ts,
            source=str(candidate.get("source") or f"candidate_{idx}"),
        )
        normalized["_score"] = score_execution_snapshot(normalized)
        normalized_rows.append(normalized)
    if not normalized_rows:
        merged = normalize_execution_row({}, run_id=run_id, ts=ts, source="empty")
        merged["quality_score"] = 0
        merged["degraded_but_usable"] = False
        merged["merge_sources"] = []
        return merged

    normalized_rows.sort(
        key=lambda row: (
            int(row.get("_score") or 0),
            1 if _null_if_empty(row.get("order_id")) else 0,
            1 if _null_if_empty(row.get("filled_price")) is not None else 0,
            1 if _null_if_empty(row.get("filled_qty")) not in (None, 0, 0.0) else 0,
        ),
        reverse=True,
    )

    merged = dict(normalized_rows[0])
    for row in normalized_rows[1:]:
        for field in ("action", "symbol", "qty", "status", "ord_no", "order_id", "filled_qty", "filled_price", "fill_status", "run_id", "ts"):
            current = merged.get(field)
            incoming = row.get(field)
            if _null_if_empty(current) in (None, 0, 0.0, "") and _null_if_empty(incoming) not in (None, 0, 0.0, ""):
                merged[field] = incoming

    merged["quality_score"] = score_execution_snapshot(merged)
    merged["degraded_but_usable"] = _is_snapshot_degraded_but_usable(merged)
    merged["merge_sources"] = [str(row.get("source") or "") for row in normalized_rows if str(row.get("source") or "").strip()]
    merged.pop("_score", None)
    return merged


def build_execution_snapshot(
    *,
    primary: Mapping[str, Any] | None = None,
    secondary: Mapping[str, Any] | None = None,
    candidates: Iterable[Mapping[str, Any] | None] | None = None,
    run_id: str = "",
    ts: str = "",
) -> Dict[str, Any]:
    merged_candidates: List[Mapping[str, Any] | None] = []
    if candidates is not None:
        merged_candidates.extend(list(candidates or []))
    if primary is not None:
        merged_candidates.append(primary)
    if secondary is not None:
        merged_candidates.append(secondary)
    return merge_execution_snapshot_candidates(merged_candidates, run_id=run_id, ts=ts)


def build_execution_details(
    bundle: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    bundle_obj = dict(bundle or {})
    context_obj = dict(context or {})
    execution = bundle_obj.get("execution") if isinstance(bundle_obj.get("execution"), dict) else {}
    executor = bundle_obj.get("executor") if isinstance(bundle_obj.get("executor"), dict) else {}
    executor_broker_result = executor.get("broker_result") if isinstance(executor.get("broker_result"), dict) else {}
    order_request = executor.get("order_request_summary") if isinstance(executor.get("order_request_summary"), dict) else {}
    monitor_context = context_obj.get("monitor_context") if isinstance(context_obj.get("monitor_context"), dict) else {}
    if not monitor_context and isinstance(bundle_obj.get("monitor"), dict):
        monitor_context = dict(bundle_obj.get("monitor") or {})
    execution_context = context_obj.get("execution_context") if isinstance(context_obj.get("execution_context"), dict) else {}

    merged = merge_execution_snapshot_candidates(
        [
            execution,
            executor_broker_result,
            executor,
            order_request,
            execution_context,
        ]
    )

    order_status = _null_if_empty(
        merged.get("fill_status")
        or execution.get("status")
        or executor_broker_result.get("status")
        or executor.get("broker_message")
        or executor.get("final_execution_status")
        or execution_context.get("status_text")
        or execution_context.get("summary")
    )
    order_id = _null_if_empty(merged.get("order_id")) or _extract_order_id_from_texts(
        (
            executor.get("broker_message"),
            execution_context.get("summary"),
            execution_context.get("status_text"),
        )
    )
    execution_mode = _null_if_empty(
        executor.get("execution_mode")
        or executor.get("effective_mode")
        or executor.get("mode")
        or execution_context.get("execution_mode")
    )
    broker_env = _null_if_empty(
        executor.get("broker_env")
        or executor_broker_result.get("broker_env")
        or execution_context.get("broker_env")
    )
    filled_qty = _null_if_empty(
        merged.get("filled_qty")
        if merged.get("filled_qty") not in (None, "")
        else order_request.get("qty")
    )
    avg_price = _null_if_empty(
        _safe_float(merged.get("filled_price"), None)
        if merged.get("filled_price") not in (None, "")
        else _safe_float(context_obj.get("price"), None)
        if context_obj.get("price") not in (None, "")
        else _safe_float(monitor_context.get("average_price"), None)
        if monitor_context.get("average_price") not in (None, "")
        else _safe_float(monitor_context.get("avg_price"), None)
        if monitor_context.get("avg_price") not in (None, "")
        else _safe_float(monitor_context.get("current_price"), None)
    )

    return {
        "order_status": order_status,
        "order_id": order_id,
        "execution_mode": execution_mode,
        "broker_env": broker_env,
        "filled_qty": filled_qty,
        "avg_price": avg_price,
        "fill_status": _null_if_empty(merged.get("fill_status")),
        "filled_price": _null_if_empty(merged.get("filled_price")),
        "run_id": _null_if_empty(merged.get("run_id")),
        "ts": _null_if_empty(merged.get("ts")),
        "quality_score": int(merged.get("quality_score") or 0),
        "degraded_but_usable": bool(merged.get("degraded_but_usable")),
        "merge_sources": list(merged.get("merge_sources") or []),
    }


__all__ = [
    "build_execution_details",
    "build_execution_snapshot",
    "merge_execution_snapshot_candidates",
    "normalize_execution_row",
    "score_execution_snapshot",
]
