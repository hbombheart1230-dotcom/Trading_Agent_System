from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from libs.reporting.report_truth_surface import build_trade_report_truth_surface


def operator_pnl_pct(truth_pnl: Dict[str, Any], shared: Dict[str, Any]) -> tuple[Any, bool]:
    pct = truth_pnl.get("pct")
    if pct not in (None, ""):
        return pct, False
    if str(truth_pnl.get("pct_display_role") or "").strip() == "fallback_mark_only":
        display = truth_pnl.get("pct_display")
        if display not in (None, ""):
            return display, True
    shared_pct = shared.get("pnl_pct")
    if shared_pct not in (None, ""):
        return shared_pct, False
    return "", False


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def get_truth_surface(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    truth = as_dict(report.get("truth_surface"))
    if truth:
        return truth
    shared = as_dict(report.get("shared_facts"))
    return build_trade_report_truth_surface(shared)


def truth_source_label(
    value: Any,
    *,
    clip: Callable[..., str],
    metadata_value: Callable[[Any], str],
) -> str:
    lowered = clip(value, 80).lower()
    if lowered == "kiwoom.ka10170":
        return "키움 당일매매일지 기준(ka10170)"
    return {
        "broker_fill": "브로커 체결가 기준",
        "monitor_mark": "모니터 관측값 기준",
        "account_mark": "계좌 기준 마크 가격",
        "kiwoom.ka10077": "키움 당일 실현손익 기준(ka10077)",
        "broker_fill_account_snapshot_estimate": "브로커 체결가와 계좌 평가손익 역산 기준",
    }.get(lowered, metadata_value(value) or "-")


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def pnl_basis_label(
    truth_pnl: Dict[str, Any],
    shared: Dict[str, Any],
    *,
    clip: Callable[..., str],
    metadata_value: Callable[[Any], str],
    truth_source_label_fn: Callable[[Any], str],
) -> str:
    source_value = first_present(shared.get("pnl_truth_source"), truth_pnl.get("pnl_truth_source"))
    source_label = truth_source_label_fn(source_value)
    source_token = clip(source_value, 80).lower()
    authoritative = boolish(first_present(truth_pnl.get("broker_day_authoritative"), shared.get("broker_day_authoritative")))
    if source_token == "kiwoom.ka10077" and not authoritative:
        match_mode = metadata_value(first_present(truth_pnl.get("broker_day_match_mode"), shared.get("broker_day_match_mode")))
        row_count = metadata_value(first_present(truth_pnl.get("broker_day_row_count"), shared.get("broker_day_row_count")))
        details: List[str] = []
        if match_mode != "-":
            details.append(f"match={match_mode}")
        if row_count != "-":
            details.append(f"rows={row_count}")
        suffix = f": {', '.join(details)}" if details else ""
        return f"미확정 ({source_label} 매칭 미확정{suffix})"
    return source_label


def extract_trade_quantity(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    num_opt: Callable[[Any], Optional[float]],
) -> Optional[float]:
    shared = as_dict(report.get("shared_facts"))
    resolved = as_dict(shared.get("resolved_trade_facts"))
    fact_payload = as_dict(report.get("fact_payload"))
    fact_trade = as_dict(fact_payload.get("trade"))
    execution_details = as_dict(fact_trade.get("execution_details"))
    entry_execution_details = as_dict(fact_trade.get("entry_execution_details"))
    exit_execution_details = as_dict(fact_trade.get("exit_execution_details"))
    execution_outcome = as_dict(fact_trade.get("execution_outcome_human"))
    exit_summary = as_dict(fact_trade.get("exit_summary"))
    execution_context = as_dict(exit_summary.get("execution_context"))
    canonical = as_dict(fact_trade.get("canonical_agent_artifacts"))
    monitor_snapshot = as_dict(as_dict(canonical.get("monitor")).get("position_snapshot"))
    supervisor_order = as_dict(as_dict(canonical.get("supervisor")).get("order_request_summary"))
    executor = as_dict(canonical.get("executor"))
    executor_order = as_dict(executor.get("order_request_summary"))

    candidates = (
        shared.get("filled_qty"),
        shared.get("quantity"),
        shared.get("qty"),
        resolved.get("filled_qty"),
        resolved.get("quantity"),
        resolved.get("qty"),
        execution_details.get("filled_qty"),
        execution_details.get("quantity"),
        execution_details.get("qty"),
        entry_execution_details.get("filled_qty"),
        exit_execution_details.get("filled_qty"),
        execution_outcome.get("quantity"),
        execution_context.get("quantity"),
        execution_context.get("qty"),
        monitor_snapshot.get("qty"),
        supervisor_order.get("qty"),
        executor.get("filled_qty"),
        executor.get("qty"),
        executor_order.get("qty"),
    )
    for candidate in candidates:
        qty = num_opt(candidate)
        if qty is not None and qty > 0:
            return qty
    return None


def infer_trade_quantity_from_costs(
    *,
    buy_price: Any,
    sell_price: Any,
    pnl: Any,
    fee: Any,
    tax: Any,
    num_opt: Callable[[Any], Optional[float]],
) -> Optional[float]:
    buy = num_opt(buy_price)
    sell = num_opt(sell_price)
    pnl_num = num_opt(pnl)
    fee_num = num_opt(fee) or 0.0
    tax_num = num_opt(tax) or 0.0
    if buy is None or sell is None or pnl_num is None:
        return None
    price_delta = sell - buy
    if abs(price_delta) < 1e-9:
        return None
    gross_price_pnl = pnl_num + fee_num + tax_num
    qty = gross_price_pnl / price_delta
    if qty <= 0:
        return None
    rounded = round(qty)
    if rounded > 0 and abs(qty - rounded) <= 0.05:
        return float(rounded)
    return qty if qty < 1_000_000 else None


def build_trade_cost_analysis(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    num_opt: Callable[[Any], Optional[float]],
    get_truth_surface_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    extract_trade_quantity_fn: Callable[[Dict[str, Any]], Optional[float]],
) -> Dict[str, Any]:
    shared = as_dict(report.get("shared_facts"))
    truth = get_truth_surface_fn(report)
    truth_price = as_dict(truth.get("price"))
    truth_pnl = as_dict(truth.get("pnl"))

    buy = num_opt(first_present(truth_price.get("broker_buy_price"), shared.get("broker_buy_price")))
    sell = num_opt(first_present(truth_price.get("broker_fill_price"), shared.get("broker_fill_price")))
    pnl = num_opt(first_present(shared.get("pnl"), truth_pnl.get("value")))
    broker_pct = num_opt(truth_pnl.get("pct"))
    observed_pct, observed_pct_is_fallback = operator_pnl_pct(truth_pnl, shared)
    observed_pct_num = num_opt(observed_pct) if observed_pct_is_fallback else None
    fee_raw = first_present(shared.get("broker_fee"), truth_pnl.get("broker_fee"))
    tax_raw = first_present(shared.get("broker_tax"), truth_pnl.get("broker_tax"))
    fee_num = num_opt(fee_raw)
    tax_num = num_opt(tax_raw)
    fee_known = fee_num is not None
    tax_known = tax_num is not None
    fee = fee_num if fee_num is not None else 0.0
    tax = tax_num if tax_num is not None else 0.0
    total_cost = fee + tax
    if buy is None or buy <= 0:
        return {}
    price_move_pct = ((sell - buy) / buy) if sell is not None and sell > 0 else None

    qty = extract_trade_quantity_fn(report)
    qty_source = "artifact"
    if qty is None:
        qty = infer_trade_quantity_from_costs(
            buy_price=buy,
            sell_price=sell,
            pnl=pnl,
            fee=fee,
            tax=tax,
            num_opt=num_opt,
        )
        qty_source = "inferred_from_pnl_fee_tax"
    if qty is None or qty <= 0:
        out: Dict[str, Any] = {}
        if price_move_pct is not None:
            out["price_move_pct"] = price_move_pct
        if broker_pct is not None:
            out["broker_reported_pnl_pct"] = broker_pct
        elif observed_pct_num is not None:
            out["observed_pnl_pct"] = observed_pct_num
            out["observed_pnl_pct_role"] = "fallback_mark_only"
        if (fee_known or tax_known) and broker_pct is not None and price_move_pct is not None:
            drag = price_move_pct - broker_pct
            out["total_cost"] = total_cost
            out["cost_drag_pct"] = drag
            out["breakeven_move_pct"] = max(0.0, drag)
        return out

    buy_notional = buy * qty
    sell_notional = sell * qty if sell is not None and sell > 0 else None
    if buy_notional <= 0:
        return {}

    out: Dict[str, Any] = {
        "quantity": qty,
        "quantity_source": qty_source,
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
    }
    if fee_known:
        out["fee"] = fee
    if tax_known:
        out["tax"] = tax
    if fee_known or tax_known:
        out["total_cost"] = total_cost
        out["cost_drag_pct"] = total_cost / buy_notional if total_cost else 0.0
        out["breakeven_move_pct"] = total_cost / buy_notional if total_cost else 0.0
    if broker_pct is not None:
        out["broker_reported_pnl_pct"] = broker_pct
    elif observed_pct_num is not None:
        out["observed_pnl_pct"] = observed_pct_num
        out["observed_pnl_pct_role"] = "fallback_mark_only"
    if sell is not None and sell > 0:
        out["gross_price_pnl"] = (sell - buy) * qty
        out["price_move_pct"] = price_move_pct
    if pnl is not None:
        out["net_return_pct_on_buy_notional"] = pnl / buy_notional
        if broker_pct is not None:
            out["broker_pct_diff_abs"] = abs((pnl / buy_notional) - broker_pct)
    if fee:
        out["fee_drag_pct_on_buy_notional"] = fee / buy_notional
    if tax and sell_notional:
        out["tax_rate_on_sell_notional"] = tax / sell_notional

    fee_drag = num_opt(out.get("fee_drag_pct_on_buy_notional")) or 0.0
    broker_diff = num_opt(out.get("broker_pct_diff_abs")) or 0.0
    out["mock_cost_warning"] = bool(fee_known and fee_drag >= 0.002)
    out["broker_pct_display_warning"] = broker_diff >= 0.002
    return out


def trade_cost_analysis_lines(
    report: Dict[str, Any],
    *,
    bullet: str = "*",
    build_trade_cost_analysis_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    fmt_pct: Callable[[Any], str],
    summary_money: Callable[[Any], str],
) -> List[str]:
    cost = build_trade_cost_analysis_fn(report)
    if not cost:
        return []
    lines: List[str] = []
    broker_pct = cost.get("broker_reported_pnl_pct")
    observed_pct = cost.get("observed_pnl_pct")
    net_pct = cost.get("net_return_pct_on_buy_notional")
    total_cost = cost.get("total_cost")
    cost_drag = cost.get("cost_drag_pct")
    breakeven = cost.get("breakeven_move_pct")
    price_move = cost.get("price_move_pct")

    if broker_pct not in (None, ""):
        lines.append(f"{bullet} 키움 제공 손익률: {fmt_pct(broker_pct)}")
    elif observed_pct not in (None, ""):
        lines.append(f"{bullet} 관측 손익률(비용 미반영): {fmt_pct(observed_pct)}")
    if net_pct not in (None, ""):
        lines.append(f"{bullet} 거래금액 기준 순수익률: **{fmt_pct(net_pct)}**")
    if price_move not in (None, ""):
        lines.append(f"{bullet} 가격 변동률: {fmt_pct(price_move)}")
    if total_cost not in (None, "") and cost_drag not in (None, ""):
        lines.append(f"{bullet} 비용 드래그: {summary_money(total_cost)} ({fmt_pct(cost_drag)})")
    if breakeven not in (None, ""):
        lines.append(f"{bullet} 손익분기 필요 상승률: 약 {fmt_pct(breakeven)}")
    if cost.get("broker_pct_display_warning"):
        lines.append(f"{bullet} 표시 주의: 키움 제공 손익률은 거래금액 기준 순수익률과 다를 수 있습니다.")
    if cost.get("mock_cost_warning"):
        lines.append(f"{bullet} 모의투자 비용 주의: 현재 수수료는 실계좌 OpenAPI 기본 수수료보다 크게 반영될 수 있습니다.")
    return lines
