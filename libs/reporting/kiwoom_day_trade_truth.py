from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

from libs.core.symbols import normalize_symbol
from libs.reporting.kiwoom_day_trade_match_estimate import (
    extract_buy_price_anchor_candidates,
    infer_buy_price_from_monitor_context,
    select_best_buy_price_match,
    select_best_buy_price_match_from_anchors,
)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def _normalize_kiwoom_pct_ratio(value: Any) -> Optional[float]:
    raw = _safe_float(value)
    if raw is None:
        return None
    return raw / 100.0


def _resolve_trade_day_hint(*values: Any) -> str:
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10].replace("-", "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 8:
            return digits[:8]
    return ""


def _normalize_execution_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    compact = text.replace("_", "").replace("-", "").replace(" ", "")
    if compact in {"sell", "s"}:
        return "sell"
    if compact in {"buy", "b"}:
        return "buy"
    if "매도" in text or "sell" in text:
        return "sell"
    if "매수" in text or "buy" in text:
        return "buy"
    return compact


def _trusted_order_fill_price(
    broker_order_status: Mapping[str, Any],
    execution_details: Mapping[str, Any],
    bundle_execution_details: Mapping[str, Any],
) -> Any:
    direct = broker_order_status.get("filled_price")
    if direct not in (None, ""):
        return direct
    if execution_details.get("broker_truth_source") == "kiwoom.order_status":
        trusted = execution_details.get("filled_price")
        if trusted not in (None, ""):
            return trusted
    if bundle_execution_details.get("broker_truth_source") == "kiwoom.order_status":
        trusted = bundle_execution_details.get("filled_price")
        if trusted not in (None, ""):
            return trusted
    return None


def _trusted_entry_fill_price(
    entry_execution_details: Mapping[str, Any],
    bundle_entry_execution_details: Mapping[str, Any],
) -> Any:
    if entry_execution_details.get("broker_truth_source") == "kiwoom.order_status":
        trusted = entry_execution_details.get("filled_price")
        if trusted not in (None, ""):
            return trusted
    if bundle_entry_execution_details.get("broker_truth_source") == "kiwoom.order_status":
        trusted = bundle_entry_execution_details.get("filled_price")
        if trusted not in (None, ""):
            return trusted
    return None


def _broker_day_truth_lookup_enabled(context_obj: Mapping[str, Any]) -> bool:
    explicit = context_obj.get("broker_day_truth_lookup_enabled")
    if explicit is not None:
        return bool(explicit)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "real"


def _price_matches(left: Any, right: Any) -> bool:
    left_value = _safe_float(left)
    right_value = _safe_float(right)
    if left_value is None or right_value is None:
        return False
    return abs(left_value - right_value) < 0.5


def _build_match_payload(
    row: Mapping[str, Any],
    *,
    symbol: str,
    row_count: int,
    match_mode: str,
    authoritative: bool,
) -> Dict[str, Any]:
    return {
        "symbol": normalize_symbol(symbol, allow_test_symbols=True),
        "filled_qty": _safe_int(row.get("filled_qty")),
        "filled_price": _safe_float(row.get("filled_price")),
        "buy_price": _safe_float(row.get("buy_price")),
        "realized_pnl": _safe_float(row.get("realized_pnl")),
        "pnl_ratio": _normalize_kiwoom_pct_ratio(row.get("pnl_ratio")),
        "fee": _safe_int(row.get("fee")),
        "tax": _safe_int(row.get("tax")),
        "source": "kiwoom.ka10077",
        "match_mode": match_mode,
        "row_count": int(row_count),
        "authoritative": bool(authoritative),
    }


def _match_detail_row(
    rows: List[Dict[str, Any]],
    *,
    symbol: str,
    filled_qty: Any = None,
    filled_price: Any = None,
    buy_price: Any = None,
    monitor_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol, allow_test_symbols=True)
    symbol_rows = [
        dict(row)
        for row in list(rows or [])
        if normalize_symbol((row or {}).get("symbol"), allow_test_symbols=True) == normalized_symbol
    ]
    row_count = len(symbol_rows)
    if not row_count:
        return {}

    qty_value = _safe_int(filled_qty)
    price_value = _safe_float(filled_price)
    buy_price_value = _safe_float(buy_price)

    def _exact_buy_sell_qty(row: Mapping[str, Any]) -> bool:
        return (
            qty_value is not None
            and buy_price_value is not None
            and _safe_int(row.get("filled_qty")) == qty_value
            and _price_matches(row.get("filled_price"), price_value)
            and _price_matches(row.get("buy_price"), buy_price_value)
        )

    def _exact_qty_and_price(row: Mapping[str, Any]) -> bool:
        return qty_value is not None and _safe_int(row.get("filled_qty")) == qty_value and _price_matches(row.get("filled_price"), price_value)

    def _exact_qty(row: Mapping[str, Any]) -> bool:
        return qty_value is not None and _safe_int(row.get("filled_qty")) == qty_value

    def _exact_price(row: Mapping[str, Any]) -> bool:
        return price_value is not None and _price_matches(row.get("filled_price"), price_value)

    exact_qty_price_matches = [row for row in symbol_rows if _exact_qty_and_price(row)]

    for match_mode, predicate in (
        ("symbol_buy_sell_qty_exact", _exact_buy_sell_qty),
        ("symbol_qty_price_exact", _exact_qty_and_price),
        ("symbol_qty_exact", _exact_qty),
        ("symbol_price_exact", _exact_price),
    ):
        matches = [row for row in symbol_rows if predicate(row)]
        if len(matches) == 1:
            return _build_match_payload(
                matches[0],
                symbol=normalized_symbol,
                row_count=row_count,
                match_mode=match_mode,
                authoritative=True,
            )

    if len(exact_qty_price_matches) > 1:
        implied_buy_price = infer_buy_price_from_monitor_context(monitor_context=monitor_context)
        best_estimated = select_best_buy_price_match(
            exact_qty_price_matches,
            implied_buy_price=implied_buy_price,
        )
        if best_estimated:
            payload = _build_match_payload(
                best_estimated["row"],
                symbol=normalized_symbol,
                row_count=row_count,
                match_mode="symbol_qty_price_estimated_buy_anchor",
                authoritative=True,
            )
            payload["estimated_buy_price"] = implied_buy_price
            payload["estimated_buy_price_diff"] = _safe_float(best_estimated.get("best_diff"))
            return payload

        anchor_candidates = extract_buy_price_anchor_candidates(monitor_context=monitor_context)
        best_anchor_match = select_best_buy_price_match_from_anchors(
            exact_qty_price_matches,
            anchors=anchor_candidates,
        )
        if best_anchor_match:
            payload = _build_match_payload(
                best_anchor_match["row"],
                symbol=normalized_symbol,
                row_count=row_count,
                match_mode="symbol_qty_price_monitor_buy_anchor",
                authoritative=True,
            )
            payload["monitor_buy_anchor_source"] = str(best_anchor_match.get("anchor_source") or "")
            payload["monitor_buy_anchor_price"] = _safe_float(best_anchor_match.get("anchor_price"))
            payload["monitor_buy_anchor_diff"] = _safe_float(best_anchor_match.get("best_diff"))
            return payload

    if row_count == 1:
        return _build_match_payload(
            symbol_rows[0],
            symbol=normalized_symbol,
            row_count=row_count,
            match_mode="single_symbol_row",
            authoritative=True,
        )

    return {
        "symbol": normalized_symbol,
        "source": "kiwoom.ka10077",
        "match_mode": "ambiguous_symbol_rows",
        "row_count": row_count,
        "authoritative": False,
    }


def _match_account_profit_row(
    rows: List[Dict[str, Any]],
    *,
    symbol: str,
) -> Dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol, allow_test_symbols=True)
    symbol_rows = [
        dict(row)
        for row in list(rows or [])
        if normalize_symbol((row or {}).get("symbol"), allow_test_symbols=True) == normalized_symbol
    ]
    row_count = len(symbol_rows)
    if row_count != 1:
        return {}
    row = symbol_rows[0]
    return {
        "symbol": normalized_symbol,
        "realized_pnl": _safe_float(row.get("today_sell_pnl")),
        "pnl_ratio": _normalize_kiwoom_pct_ratio(row.get("pnl_ratio")),
        "fee": _safe_int(row.get("today_fee")),
        "tax": _safe_int(row.get("today_tax")),
        "source": "kiwoom.ka10085",
        "match_mode": "symbol_account_profit_row",
        "row_count": row_count,
        "authoritative": True,
    }


def attach_broker_day_pnl(
    bundle: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    bundle_obj = dict(bundle or {})
    context_obj = dict(context or {})
    execution_context = (
        dict(context_obj.get("execution_context") or {})
        if isinstance(context_obj.get("execution_context"), dict)
        else {}
    )
    execution_details = (
        dict(context_obj.get("execution_details") or {})
        if isinstance(context_obj.get("execution_details"), dict)
        else {}
    )
    bundle_execution_details = (
        dict(bundle_obj.get("execution_details") or {})
        if isinstance(bundle_obj.get("execution_details"), dict)
        else {}
    )
    entry_execution_details = (
        dict(context_obj.get("entry_execution_details") or {})
        if isinstance(context_obj.get("entry_execution_details"), dict)
        else {}
    )
    if not entry_execution_details and isinstance(bundle_obj.get("entry_execution_details"), dict):
        entry_execution_details = dict(bundle_obj.get("entry_execution_details") or {})
    bundle_entry_execution_details = (
        dict(bundle_obj.get("entry_execution_details") or {})
        if isinstance(bundle_obj.get("entry_execution_details"), dict)
        else {}
    )
    if not bundle_entry_execution_details and isinstance(bundle_obj.get("entry"), dict):
        bundle_entry_execution_details = (
            dict((bundle_obj.get("entry") or {}).get("execution_details") or {})
            if isinstance((bundle_obj.get("entry") or {}).get("execution_details"), dict)
            else {}
        )
    if isinstance(execution_context.get("broker_day_pnl"), dict) and execution_context.get("broker_day_pnl"):
        context_obj["execution_context"] = execution_context
        return context_obj

    broker_order_status = (
        execution_context.get("broker_order_status")
        if isinstance(execution_context.get("broker_order_status"), dict)
        else {}
    )
    execution = bundle_obj.get("execution") if isinstance(bundle_obj.get("execution"), dict) else {}
    executor = bundle_obj.get("executor") if isinstance(bundle_obj.get("executor"), dict) else {}
    broker_result = executor.get("broker_result") if isinstance(executor.get("broker_result"), dict) else {}
    order_request = executor.get("order_request_summary") if isinstance(executor.get("order_request_summary"), dict) else {}

    side = _normalize_execution_side(
        broker_order_status.get("side")
        or context_obj.get("action")
        or context_obj.get("side")
        or execution_details.get("side")
        or execution_details.get("action")
        or bundle_execution_details.get("side")
        or bundle_execution_details.get("action")
        or execution.get("action")
        or broker_result.get("action")
        or order_request.get("action")
        or execution_context.get("action")
        or ""
    )
    if side not in {"sell", "s"}:
        context_obj["execution_context"] = execution_context
        return context_obj

    symbol = normalize_symbol(
        broker_order_status.get("symbol")
        or context_obj.get("symbol")
        or execution_details.get("symbol")
        or bundle_execution_details.get("symbol")
        or execution.get("symbol")
        or broker_result.get("symbol")
        or order_request.get("symbol")
        or execution_context.get("symbol")
        or "",
        allow_test_symbols=True,
    )
    trade_day = _resolve_trade_day_hint(
        context_obj.get("trade_day"),
        context_obj.get("ts"),
        execution_context.get("ts"),
        execution.get("ts"),
        broker_result.get("ts"),
        bundle_obj.get("ts"),
    )
    if not (symbol and trade_day):
        context_obj["execution_context"] = execution_context
        return context_obj

    filled_qty = broker_order_status.get("filled_qty")
    if filled_qty in (None, ""):
        filled_qty = execution_details.get("filled_qty")
    if filled_qty in (None, ""):
        filled_qty = bundle_execution_details.get("filled_qty")
    filled_price = _trusted_order_fill_price(
        broker_order_status,
        execution_details,
        bundle_execution_details,
    )
    buy_price = _trusted_entry_fill_price(
        entry_execution_details,
        bundle_entry_execution_details,
    )
    reader = context_obj.get("broker_day_pnl_reader")
    if reader is None:
        if not _broker_day_truth_lookup_enabled(context_obj):
            context_obj["execution_context"] = execution_context
            return context_obj
        try:
            from libs.read.kiwoom_day_pnl_reader import KiwoomDayPnlReader

            reader = KiwoomDayPnlReader.from_env()
        except Exception as exc:
            execution_context["broker_day_pnl_error"] = str(exc)
            context_obj["execution_context"] = execution_context
            return context_obj

    try:
        payload = reader.get_day_realized_details(symbol=symbol)
    except Exception as exc:
        execution_context["broker_day_pnl_error"] = str(exc)
        context_obj["execution_context"] = execution_context
        return context_obj

    matched = _match_detail_row(
        list(payload.get("rows") or []),
        symbol=symbol,
        filled_qty=filled_qty,
        filled_price=filled_price,
        buy_price=buy_price,
        monitor_context=(
            context_obj.get("monitor_context")
            if isinstance(context_obj.get("monitor_context"), dict)
            else {}
        ),
    )
    if (not matched or not bool(matched.get("authoritative"))) and hasattr(reader, "get_account_profit_rate_rows"):
        try:
            profit_payload = reader.get_account_profit_rate_rows()
        except Exception as exc:
            execution_context["broker_day_pnl_error"] = str(exc)
            context_obj["execution_context"] = execution_context
            return context_obj
        profit_match = _match_account_profit_row(
            list(profit_payload.get("rows") or []),
            symbol=symbol,
        )
        if profit_match:
            matched = profit_match
    if matched:
        matched["day"] = trade_day
        execution_context["broker_day_pnl"] = matched
    context_obj["execution_context"] = execution_context
    return context_obj


__all__ = ["attach_broker_day_pnl"]
