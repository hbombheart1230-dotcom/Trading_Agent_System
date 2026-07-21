from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping
from zoneinfo import ZoneInfo

from libs.reporting.trade_report_symbol_metadata import SYMBOL_NAME_FALLBACKS, SYMBOL_THEME_FALLBACKS


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value or "").strip().replace(",", "")
        return int(float(text)) if text else int(default)
    except Exception:
        return int(default)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        text = str(value or "").strip().replace(",", "")
        return float(text) if text else float(default)
    except Exception:
        return float(default)


def _is_missing(value: Any) -> bool:
    if value in (None, "", [], {}):
        return True
    text = str(value).strip().lower()
    return text in {"none", "null", "unknown", "unavailable", "nan"}


def _symbol_from_trade_id(trade_id: str) -> str:
    match = re.search(r"TRD_\d{8}_([A-Z0-9]{6})_", str(trade_id or "").upper())
    return match.group(1) if match else ""


def _norm_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("A") and len(text) == 7:
        text = text[1:]
    return text[-6:] if len(text) >= 6 else text


def _order_time_value(row: Mapping[str, Any]) -> str:
    return str(row.get("cntr_tm") or row.get("ord_tm") or "").strip()


def _order_time_sort_key(row: Mapping[str, Any]) -> str:
    digits = re.sub(r"\D", "", _order_time_value(row))
    return digits[:6] if len(digits) >= 6 else digits


def _order_time_to_utc(day: str, value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 6:
        return ""
    try:
        local = datetime.strptime(f"{day[:10]} {digits[:6]}", "%Y-%m-%d %H%M%S").replace(
            tzinfo=ZoneInfo("Asia/Seoul")
        )
    except ValueError:
        return ""
    return local.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds")


def _side(row: Mapping[str, Any]) -> str:
    text = str(row.get("io_tp_nm") or "").strip()
    if "매도" in text:
        return "sell"
    if "매수" in text:
        return "buy"
    if "매도" in text:
        return "sell"
    if "매수" in text:
        return "buy"
    if "매도" in text or "sell" in text.lower():
        return "sell"
    if "매수" in text or "buy" in text.lower():
        return "buy"
    return ""


def _iter_snapshot_rows(snapshot: Mapping[str, Any], key: str) -> Iterable[Dict[str, Any]]:
    for call in list(snapshot.get("calls") or []):
        if not isinstance(call, dict):
            continue
        payload = call.get("payload") if isinstance(call.get("payload"), dict) else {}
        rows = payload.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield dict(row)


def _day_trade_diary_rows(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for call in list(snapshot.get("calls") or []):
        if not isinstance(call, dict) or str(call.get("api_id") or "").strip() != "ka10170":
            continue
        payload = call.get("payload") if isinstance(call.get("payload"), dict) else {}
        for row in list(payload.get("tdy_trde_diary") or []):
            if isinstance(row, dict):
                rows.append(dict(row))
    return rows


def _load_latest_snapshot(day: str, root: Path) -> Dict[str, Any]:
    path = root.parent / "data" / "logs" / "kiwoom_account_snapshots" / str(day)[:10] / "latest.json"
    payload = _read_json(path)
    if payload:
        payload["_snapshot_path"] = str(path)
    return payload


def _find_buy_order(orders: List[Dict[str, Any]], *, order_id: str, symbol: str) -> Dict[str, Any]:
    normalized_order = str(order_id or "").strip().lstrip("0")
    for row in orders:
        if _side(row) != "buy":
            continue
        if symbol and _norm_symbol(row.get("stk_cd")) != symbol:
            continue
        if str(row.get("ord_no") or "").strip().lstrip("0") == normalized_order:
            return dict(row)
    return {}


def _find_order_by_id(
    orders: List[Dict[str, Any]],
    *,
    order_id: str,
    symbol: str,
    side: str = "",
) -> Dict[str, Any]:
    normalized_order = str(order_id or "").strip().lstrip("0")
    if not normalized_order:
        return {}
    side_text = str(side or "").strip().lower()
    for row in orders:
        if side_text and _side(row) != side_text:
            continue
        if symbol and _norm_symbol(row.get("stk_cd")) != symbol:
            continue
        if str(row.get("ord_no") or "").strip().lstrip("0") == normalized_order:
            return dict(row)
    return {}


def _find_sell_after_buy(orders: List[Dict[str, Any]], *, buy: Mapping[str, Any], symbol: str) -> Dict[str, Any]:
    qty = _to_int(buy.get("cntr_qty") or buy.get("cnfm_qty") or buy.get("ord_qty"))
    buy_time = _order_time_sort_key(buy)
    candidates = []
    for row in orders:
        if _side(row) != "sell":
            continue
        if symbol and _norm_symbol(row.get("stk_cd")) != symbol:
            continue
        if qty and _to_int(row.get("cntr_qty") or row.get("cnfm_qty") or row.get("ord_qty")) != qty:
            continue
        row_time = _order_time_sort_key(row)
        if buy_time and row_time and row_time <= buy_time:
            continue
        candidates.append(dict(row))
    candidates.sort(key=_order_time_sort_key)
    return candidates[0] if candidates else {}


def _find_buy_before_sell(orders: List[Dict[str, Any]], *, sell: Mapping[str, Any], symbol: str) -> Dict[str, Any]:
    qty = _to_int(sell.get("cntr_qty") or sell.get("cnfm_qty") or sell.get("ord_qty"))
    sell_time = _order_time_sort_key(sell)
    candidates = []
    for row in orders:
        if _side(row) != "buy":
            continue
        if symbol and _norm_symbol(row.get("stk_cd")) != symbol:
            continue
        if qty and _to_int(row.get("cntr_qty") or row.get("cnfm_qty") or row.get("ord_qty")) != qty:
            continue
        row_time = _order_time_sort_key(row)
        if sell_time and row_time and row_time >= sell_time:
            continue
        candidates.append(dict(row))
    candidates.sort(key=_order_time_sort_key, reverse=True)
    return candidates[0] if candidates else {}


def _fee_tax_for_order(order_rows: List[Dict[str, Any]], order_no: Any) -> int:
    normalized = str(order_no or "").strip().lstrip("0")
    for row in order_rows:
        if str(row.get("ord_no") or "").strip().lstrip("0") != normalized:
            continue
        return _to_int(row.get("tdy_trde_cmsn")) + _to_int(row.get("tdy_trde_tax"))
    return 0


def _build_truth_payload(*, symbol: str, buy: Mapping[str, Any], sell: Mapping[str, Any], order_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    qty = _to_int(sell.get("cntr_qty") or sell.get("cnfm_qty") or sell.get("ord_qty"))
    buy_price = _to_float(buy.get("cntr_uv") or buy.get("cntr_pric"))
    sell_price = _to_float(sell.get("cntr_uv") or sell.get("cntr_pric"))
    buy_notional = buy_price * qty
    sell_notional = sell_price * qty
    fee_tax = _fee_tax_for_order(order_rows, buy.get("ord_no")) + _fee_tax_for_order(order_rows, sell.get("ord_no"))
    pnl = sell_notional - buy_notional - fee_tax
    pnl_pct = pnl / buy_notional if buy_notional else 0.0
    return {
        "symbol": symbol,
        "qty": qty,
        "buy_order_no": str(buy.get("ord_no") or ""),
        "sell_order_no": str(sell.get("ord_no") or ""),
        "buy_time": _order_time_value(buy),
        "sell_time": _order_time_value(sell),
        "buy_price": buy_price,
        "sell_price": sell_price,
        "fee_tax": fee_tax,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "pnl_pct_text": f"{pnl_pct * 100.0:.2f}%",
        "result_label": "profit" if pnl > 0 else "loss" if pnl < 0 else "breakeven",
        "source": "kiwoom.order_pair_snapshot",
        "match_mode": "entry_order_id_next_same_symbol_qty_sell",
        "authoritative": True,
    }


def _build_order_pair_truth(
    *,
    symbol: str,
    entry: Mapping[str, Any],
    exit_payload: Mapping[str, Any],
    order_rows: List[Dict[str, Any]],
    fee_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    buy = _find_order_by_id(
        order_rows,
        order_id=str(entry.get("order_id") or ""),
        symbol=symbol,
        side="buy",
    )
    sell = _find_order_by_id(
        order_rows,
        order_id=str(exit_payload.get("order_id") or ""),
        symbol=symbol,
        side="sell",
    )
    if buy and not sell:
        sell = _find_sell_after_buy(order_rows, buy=buy, symbol=symbol)
    if sell and not buy:
        buy = _find_buy_before_sell(order_rows, sell=sell, symbol=symbol)
    if not buy or not sell:
        return {}
    return _build_truth_payload(symbol=symbol, buy=buy, sell=sell, order_rows=fee_rows)


def _build_truth_payload_from_day_diary(row: Mapping[str, Any], *, symbol: str) -> Dict[str, Any]:
    buy_qty = _to_int(row.get("buy_qty"))
    sell_qty = _to_int(row.get("sell_qty"))
    qty = min(buy_qty, sell_qty) if buy_qty and sell_qty else sell_qty or buy_qty
    buy_price = _to_float(row.get("buy_avg_pric") or row.get("buy_avg_price"))
    sell_price = _to_float(row.get("sel_avg_pric") or row.get("sell_avg_price"))
    pnl = _to_float(row.get("pl_amt") or row.get("realized_pnl"))
    pnl_pct = _to_float(row.get("prft_rt") or row.get("pnl_ratio")) / 100.0
    fee_tax = _to_int(row.get("cmsn_alm_tax") or row.get("fee_tax"))
    return {
        "symbol": symbol,
        "qty": qty,
        "buy_order_no": "",
        "sell_order_no": "",
        "buy_time": "",
        "sell_time": "",
        "buy_price": buy_price,
        "sell_price": sell_price,
        "fee_tax": fee_tax,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "pnl_pct_text": f"{pnl_pct * 100.0:.2f}%",
        "result_label": "profit" if pnl > 0 else "loss" if pnl < 0 else "breakeven",
        "source": "kiwoom.ka10170",
        "match_mode": "ka10170_symbol_buy_sell_qty_exact",
        "authoritative": True,
    }


def _merge_day_diary_with_order_pair(
    day_diary_truth: Mapping[str, Any],
    order_pair_truth: Mapping[str, Any],
) -> Dict[str, Any]:
    """Keep exact ka10170 PnL while retaining order-level timing evidence."""
    truth = dict(day_diary_truth or {})
    pair = dict(order_pair_truth or {})
    for key in ("buy_order_no", "sell_order_no", "buy_time", "sell_time"):
        if pair.get(key):
            truth[key] = pair[key]
    if pair:
        truth["match_mode"] = "ka10170_with_order_pair_time"
    return truth


def _symbol_metadata(symbol: Any) -> Dict[str, Any]:
    normalized = _norm_symbol(symbol)
    themes = list(SYMBOL_THEME_FALLBACKS.get(normalized, []))
    return {
        "symbol": normalized,
        "symbol_name": SYMBOL_NAME_FALLBACKS.get(normalized, ""),
        "themes": themes,
        "theme": ", ".join(themes),
    }


def _find_closed_day_diary_row(rows: List[Dict[str, Any]], *, symbol: str, entry: Mapping[str, Any]) -> Dict[str, Any]:
    qty = _to_int(entry.get("qty") or entry.get("filled_qty"))
    buy_price = _to_float(entry.get("filled_price") or entry.get("avg_price") or entry.get("price"))
    matches: List[Dict[str, Any]] = []
    for row in rows:
        if _norm_symbol(row.get("stk_cd") or row.get("stk_cd_1")) != symbol:
            continue
        buy_qty = _to_int(row.get("buy_qty"))
        sell_qty = _to_int(row.get("sell_qty"))
        if buy_qty <= 0 or sell_qty < buy_qty:
            continue
        if qty and sell_qty != qty:
            continue
        row_buy_price = _to_float(row.get("buy_avg_pric") or row.get("buy_avg_price"))
        if buy_price and row_buy_price and abs(row_buy_price - buy_price) >= 0.5:
            continue
        matches.append(dict(row))
    return matches[0] if len(matches) == 1 else {}


def _patch_report_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    metadata = _symbol_metadata(truth.get("symbol"))
    out["status"] = "closed"
    out["action"] = "SELL"
    out["symbol"] = truth.get("symbol") or out.get("symbol")
    if _is_missing(out.get("symbol_name")) and metadata.get("symbol_name"):
        out["symbol_name"] = metadata.get("symbol_name")
    truth_surface = dict(out.get("truth_surface") or {})
    truth_surface["status"] = {
        **dict(truth_surface.get("status") or {}),
        "symbol": truth.get("symbol"),
        "action": "SELL",
        "status": "closed",
        "exit_reason": "broker truth closed after post-close reconciliation",
    }
    truth_surface["price"] = {
        **dict(truth_surface.get("price") or {}),
        "broker_fill_price": truth.get("sell_price"),
        "broker_buy_price": truth.get("buy_price"),
        "price_truth_source": truth.get("source"),
    }
    truth_surface["pnl"] = {
        **dict(truth_surface.get("pnl") or {}),
        "value": truth.get("pnl"),
        "pct": truth.get("pnl_pct"),
        "pct_display": truth.get("pnl_pct"),
        "pct_display_role": "broker_truth",
        "broker_fee": truth.get("fee_tax"),
        "pnl_truth_source": truth.get("source"),
        "broker_day_truth_source": truth.get("source"),
        "broker_day_match_mode": truth.get("match_mode"),
        "broker_day_authoritative": True,
        "broker_day_match_status": "matched",
        "broker_day_match_confidence": "high",
    }
    truth_surface["availability"] = {
        **dict(truth_surface.get("availability") or {}),
        "broker_fill_present": True,
        "broker_pnl_present": True,
        "broker_day_authoritative": True,
        "broker_day_match_status": "matched",
        "broker_day_match_confidence": "high",
    }
    out["truth_surface"] = truth_surface
    shared = dict(out.get("shared_facts") or {})
    shared.update(
        {
            "action": "SELL",
            "status": "closed",
            "pnl": truth.get("pnl"),
            "pnl_pct": truth.get("pnl_pct"),
            "broker_fee": truth.get("fee_tax"),
            "pnl_truth_source": truth.get("source"),
            "broker_day_truth_source": truth.get("source"),
            "broker_day_match_mode": truth.get("match_mode"),
            "broker_day_authoritative": True,
            "broker_day_match_status": "matched",
            "broker_fill_price": truth.get("sell_price"),
            "broker_buy_price": truth.get("buy_price"),
            "price_truth_source": truth.get("source"),
        }
    )
    if _is_missing(shared.get("symbol_name")) and metadata.get("symbol_name"):
        shared["symbol_name"] = metadata.get("symbol_name")
    if _is_missing(shared.get("theme")) and metadata.get("theme"):
        shared["theme"] = metadata.get("theme")
        shared["themes"] = list(metadata.get("themes") or [])
    out["shared_facts"] = shared
    return out


def _patch_summary_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    metadata = _symbol_metadata(truth.get("symbol"))
    trade = dict(out.get("trade") or {})
    trade.update({"status": "종결", "action": "매도"})
    trade["symbol"] = truth.get("symbol") or trade.get("symbol")
    if _is_missing(trade.get("symbol_name")) and metadata.get("symbol_name"):
        trade["symbol_name"] = metadata.get("symbol_name")
    if _is_missing(trade.get("theme")) and metadata.get("theme"):
        trade["theme"] = metadata.get("theme")
        trade["themes"] = list(metadata.get("themes") or [])
    out["trade"] = trade
    out["truth_surface"] = {
        **dict(out.get("truth_surface") or {}),
        "result_label": truth.get("result_label"),
        "pnl": truth.get("pnl"),
        "pnl_pct": truth.get("pnl_pct"),
        "pnl_pct_text": truth.get("pnl_pct_text"),
        "buy_price": truth.get("buy_price"),
        "sell_price": truth.get("sell_price"),
        "fee": truth.get("fee_tax"),
        "truth_source": truth.get("source"),
        "cost_analysis": {
            "quantity": truth.get("qty"),
            "buy_notional": truth.get("buy_price") * truth.get("qty"),
            "sell_notional": truth.get("sell_price") * truth.get("qty"),
            "fee": truth.get("fee_tax"),
            "total_cost": truth.get("fee_tax"),
            "net_return_pct_on_buy_notional": truth.get("pnl_pct"),
            "broker_reported_pnl_pct": truth.get("pnl_pct"),
        },
    }
    decision = dict(out.get("decision_flow") or {})
    decision.update(
        {
            "exit_reason": decision.get("exit_reason") or "broker truth closed",
            "exit_trigger": decision.get("exit_trigger") or "broker truth closed",
            "exit_trigger_basis": "post_close_broker_order_pair_reconciliation",
        }
    )
    out["decision_flow"] = decision
    return out


def _patch_exit_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    out.update(
        {
            "action": "SELL",
            "symbol": truth.get("symbol"),
            "price": truth.get("sell_price"),
            "qty": truth.get("qty"),
            "filled_qty": truth.get("qty"),
            "ts": truth.get("exit_ts"),
            "timestamp": truth.get("exit_ts"),
            "order_id": truth.get("sell_order_no"),
            "summary": "Position closed using authoritative Kiwoom broker truth.",
            "reason_human": "SELL reconciled from Kiwoom day trade diary.",
            "broker_day_authoritative": True,
            "broker_realized_pnl": truth.get("pnl"),
            "broker_realized_pnl_pct": truth.get("pnl_pct"),
            "broker_fee": truth.get("fee_tax"),
            "broker_tax": 0,
            "broker_buy_price": truth.get("buy_price"),
            "broker_day_truth_source": truth.get("source"),
            "broker_day_match_mode": truth.get("match_mode"),
        }
    )
    details = dict(out.get("execution_details") or {})
    details.update(
        {
            "broker_day_authoritative": True,
            "broker_day_truth_source": truth.get("source"),
            "broker_day_match_mode": truth.get("match_mode"),
            "broker_realized_pnl": truth.get("pnl"),
            "broker_realized_pnl_pct": truth.get("pnl_pct"),
            "broker_fee": truth.get("fee_tax"),
            "broker_tax": 0,
            "broker_buy_price": truth.get("buy_price"),
            "pnl_truth_source": truth.get("source"),
            "filled_qty": truth.get("qty"),
            "filled_price": truth.get("sell_price"),
            "avg_price": truth.get("sell_price"),
            "quality_score": 100,
            "degraded_but_usable": True,
        }
    )
    out["execution_details"] = details
    return out


def _patch_entry_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    buy_price = truth.get("buy_price")
    out["symbol"] = truth.get("symbol") or out.get("symbol")
    if _is_missing(out.get("qty")):
        out["qty"] = truth.get("qty")
    if _is_missing(out.get("filled_qty")):
        out["filled_qty"] = truth.get("qty")
    if _is_missing(out.get("price")):
        out["price"] = buy_price
    if _is_missing(out.get("filled_price")):
        out["filled_price"] = buy_price
    if _is_missing(out.get("avg_price")):
        out["avg_price"] = buy_price

    details = dict(out.get("execution_details") or {})
    details.update(
        {
            "broker_day_authoritative": True,
            "broker_day_truth_source": truth.get("source"),
            "broker_day_match_mode": truth.get("match_mode"),
            "broker_buy_price": buy_price,
            "filled_qty": truth.get("qty"),
        }
    )
    if _is_missing(details.get("filled_price")):
        details["filled_price"] = buy_price
    if _is_missing(details.get("avg_price")):
        details["avg_price"] = buy_price
    out["execution_details"] = details
    out["broker_day_authoritative"] = True
    out["broker_day_truth_source"] = truth.get("source")
    out["broker_day_match_mode"] = truth.get("match_mode")
    out["broker_buy_price"] = buy_price
    return out


def _patch_lifecycle_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    out["trade_lifecycle_status"] = "closed"
    out["status"] = "closed"
    out["symbol"] = truth.get("symbol") or out.get("symbol")
    entry = _patch_entry_payload(dict(out.get("entry") or {}), truth)
    out["entry"] = entry
    out["entry_execution_details"] = dict(entry.get("execution_details") or {})
    out["exit"] = _patch_exit_payload(dict(out.get("exit") or {}), truth)
    out["exit_execution_details"] = dict(out["exit"].get("execution_details") or {})
    out["execution_details"] = dict(out["exit_execution_details"])
    shared = dict(out.get("shared_facts") or {})
    shared.update(
        {
            "action": "SELL",
            "status": "closed",
            "exit_reason": "broker truth closed from Kiwoom day trade diary",
            "pnl": truth.get("pnl"),
            "pnl_pct": truth.get("pnl_pct"),
            "broker_fee": truth.get("fee_tax"),
            "broker_tax": 0,
            "pnl_truth_source": truth.get("source"),
            "broker_day_truth_source": truth.get("source"),
            "broker_day_match_mode": truth.get("match_mode"),
            "broker_day_authoritative": True,
            "broker_fill_price": truth.get("sell_price"),
            "broker_buy_price": truth.get("buy_price"),
            "price_truth_source": truth.get("source"),
        }
    )
    data_source = dict(shared.get("data_source") or {})
    data_source.update(
        {
            "action": truth.get("source"),
            "status": truth.get("source"),
            "exit_reason": truth.get("source"),
            "pnl": truth.get("source"),
            "pnl_pct": truth.get("source"),
        }
    )
    shared["data_source"] = data_source
    out["shared_facts"] = shared
    nested_lifecycle = dict(out.get("lifecycle") or {})
    nested_lifecycle.update(
        {
            "entry": dict(entry),
            "exit": dict(out["exit"]),
            "status": "closed",
        }
    )
    out["lifecycle"] = nested_lifecycle
    if isinstance(out.get("trade_lifecycle"), dict):
        out["trade_lifecycle"] = dict(nested_lifecycle)
    out["broker_reconciliation"] = {
        "status": "closed_by_broker_day_trade_diary",
        "source": truth.get("source"),
        "match_mode": truth.get("match_mode"),
        "pnl": truth.get("pnl"),
        "pnl_pct": truth.get("pnl_pct"),
    }
    return out


def _patch_health_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    out["lifecycle_status"] = "closed"
    out["broker_reconciliation"] = {
        "status": "closed_by_broker_day_trade_diary",
        "source": truth.get("source"),
        "match_mode": truth.get("match_mode"),
    }
    return out


def _pair_same_symbol_round_trips(order_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        dict(row)
        for row in order_rows
        if _side(row) in {"buy", "sell"} and _norm_symbol(row.get("stk_cd"))
    ]
    rows.sort(key=lambda row: (_norm_symbol(row.get("stk_cd")), _order_time_sort_key(row), str(row.get("ord_no") or "")))
    open_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    pairs: List[Dict[str, Any]] = []
    for row in rows:
        symbol = _norm_symbol(row.get("stk_cd"))
        side = _side(row)
        if side == "buy":
            open_by_symbol.setdefault(symbol, []).append(row)
            continue
        buys = open_by_symbol.setdefault(symbol, [])
        if not buys:
            continue
        sell_qty = _to_int(row.get("cntr_qty") or row.get("cnfm_qty") or row.get("ord_qty"))
        match_index = 0
        for idx, buy in enumerate(buys):
            buy_qty = _to_int(buy.get("cntr_qty") or buy.get("cnfm_qty") or buy.get("ord_qty"))
            if not sell_qty or not buy_qty or buy_qty == sell_qty:
                match_index = idx
                break
        buy = buys.pop(match_index)
        pairs.append({"symbol": symbol, "buy": buy, "sell": row})
    pairs.sort(key=lambda row: _order_time_sort_key(row["sell"]))
    return pairs


def _order_pair_key(truth: Mapping[str, Any]) -> str:
    return f"{str(truth.get('buy_order_no') or '').strip()}:{str(truth.get('sell_order_no') or '').strip()}"


def _truth_from_pair(pair: Mapping[str, Any], *, fee_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _build_truth_payload(
        symbol=str(pair.get("symbol") or ""),
        buy=pair.get("buy") if isinstance(pair.get("buy"), Mapping) else {},
        sell=pair.get("sell") if isinstance(pair.get("sell"), Mapping) else {},
        order_rows=fee_rows,
    )


def _trade_hour_from_order_time(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 2:
        return "unknown"
    return f"{digits[:2]}00"


def _next_trade_id(day: str, symbol: str, trade_dirs: List[Path]) -> str:
    prefix = f"TRD_{day.replace('-', '')}_{symbol}_"
    max_seq = 0
    for path in trade_dirs:
        if not path.name.startswith(prefix):
            continue
        suffix = path.name[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{prefix}{max_seq + 1:02d}"


def _write_synthetic_trade_bundle(
    *,
    reports_root: Path,
    day: str,
    truth: Mapping[str, Any],
    trade_id: str,
) -> Path:
    symbol = str(truth.get("symbol") or "")
    trade_dir = reports_root / "trades" / day / _trade_hour_from_order_time(truth.get("sell_time")) / trade_id
    metadata = _symbol_metadata(symbol)
    base = {
        "schema_version": "broker_synthesized_trade_bundle.v1",
        "trade_id": trade_id,
        "day": day,
        "symbol": symbol,
        "symbol_name": metadata.get("symbol_name"),
        "theme": metadata.get("theme"),
        "themes": metadata.get("themes"),
        "recovery_source": "broker_synthesized_missing_trade_bundle",
    }
    entry = _patch_entry_payload(
        {
            **base,
            "action": "BUY",
            "order_id": truth.get("buy_order_no"),
            "timestamp": _order_time_to_utc(day, truth.get("buy_time")),
            "ts": _order_time_to_utc(day, truth.get("buy_time")),
            "qty": truth.get("qty"),
            "price": truth.get("buy_price"),
        },
        truth,
    )
    exit_payload = _patch_exit_payload(
        {
            **base,
            "action": "SELL",
            "order_id": truth.get("sell_order_no"),
            "timestamp": _order_time_to_utc(day, truth.get("sell_time")),
            "ts": _order_time_to_utc(day, truth.get("sell_time")),
        },
        truth,
    )
    lifecycle = _patch_lifecycle_payload(
        {
            **base,
            "trade_lifecycle_status": "closed",
            "status": "closed",
            "entry": entry,
            "exit": exit_payload,
            "lifecycle": {"status": "closed", "entry": entry, "exit": exit_payload},
            "shared_facts": {
                "symbol": symbol,
                "symbol_name": metadata.get("symbol_name"),
                "theme": metadata.get("theme"),
                "themes": metadata.get("themes"),
            },
        },
        truth,
    )
    _write_json(trade_dir / "entry.json", entry)
    _write_json(trade_dir / "exit.json", exit_payload)
    _write_json(trade_dir / "lifecycle_bundle.json", lifecycle)
    _write_json(trade_dir / "_health.json", _patch_health_payload(base, truth))
    evidence_dir = trade_dir / "evidence"
    for name in ("scanner_evidence", "strategist_evidence", "commander_evidence", "monitor_evidence"):
        _write_json(
            evidence_dir / f"{name}.json",
            {
                "schema_version": f"{name}.v1",
                "trade_id": trade_id,
                "symbol": symbol,
                "recovery_source": "broker_synthesized_missing_trade_bundle",
                "events": [],
            },
        )
    _write_json(trade_dir / "ai_trade_report_input.json", _patch_report_payload(base, truth))
    return trade_dir


def reconcile_broker_closed_trade_reports(*, reports_root: Path = Path("reports"), day: str) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    snapshot = _load_latest_snapshot(normalized_day, reports_root)
    if not snapshot:
        return {"ok": False, "reason": "account_snapshot_missing", "patched_count": 0}
    orders = list(_iter_snapshot_rows(snapshot, "acnt_ord_cntr_prst_array"))
    fee_rows = list(_iter_snapshot_rows(snapshot, "cntr"))
    fill_orders = fee_rows + orders
    day_diary_rows = _day_trade_diary_rows(snapshot)
    patched: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    synthesized: List[Dict[str, Any]] = []
    used_order_pairs: set[str] = set()
    day_root = reports_root / "trades" / normalized_day
    trade_dirs = [
        path
        for path in sorted(day_root.glob("*/*"))
        if path.is_dir() and path.name.startswith("TRD_")
    ]
    symbol_trade_counts: Dict[str, int] = {}
    for path in trade_dirs:
        symbol = _symbol_from_trade_id(path.name)
        symbol_trade_counts[symbol] = symbol_trade_counts.get(symbol, 0) + 1
    for trade_dir in trade_dirs:
        trade_id = trade_dir.name
        symbol = _symbol_from_trade_id(trade_id)
        report_path = trade_dir / "reports" / "ai_trade_report.json"
        summary_path = trade_dir / "reports" / "ai_trade_summary.json"
        report_input_path = trade_dir / "ai_trade_report_input.json"
        compact_input_path = trade_dir / "ai_trade_report_compact_input.json"
        lifecycle_path = trade_dir / "lifecycle_bundle.json"
        exit_path = trade_dir / "exit.json"
        health_path = trade_dir / "_health.json"
        entry_path = trade_dir / "entry.json"
        if not entry_path.exists() or not lifecycle_path.exists():
            continue
        report = _read_json(report_path) if report_path.exists() else {}
        entry = _read_json(entry_path)
        lifecycle = _read_json(lifecycle_path)
        broker_reconciliation = (
            lifecycle.get("broker_reconciliation")
            if isinstance(lifecycle.get("broker_reconciliation"), dict)
            else {}
        )
        nested_lifecycle = (
            lifecycle.get("lifecycle")
            if isinstance(lifecycle.get("lifecycle"), dict)
            else {}
        )
        lifecycle_exit = (
            lifecycle.get("exit")
            if isinstance(lifecycle.get("exit"), dict)
            else {}
        )
        lifecycle_entry = (
            lifecycle.get("entry")
            if isinstance(lifecycle.get("entry"), dict)
            else {}
        )
        entry_price_available = not _is_missing(
            entry.get("price")
            or entry.get("filled_price")
            or (entry.get("execution_details") or {}).get("filled_price")
            or lifecycle_entry.get("price")
            or lifecycle_entry.get("filled_price")
            or (lifecycle_entry.get("execution_details") or {}).get("filled_price")
        )
        expected_metadata = _symbol_metadata(_symbol_from_trade_id(trade_dir.name))
        summary_payload = _read_json(summary_path) if summary_path.exists() else {}
        summary_trade = (
            summary_payload.get("trade")
            if isinstance(summary_payload.get("trade"), dict)
            else {}
        )
        report_shared = report.get("shared_facts") if isinstance(report.get("shared_facts"), dict) else {}
        metadata_available = bool(
            (
                not expected_metadata.get("symbol_name")
                or not _is_missing(
                    report.get("symbol_name")
                    or report_shared.get("symbol_name")
                    or summary_trade.get("symbol_name")
                )
            )
            and (
                not expected_metadata.get("theme")
                or not _is_missing(
                    report_shared.get("theme")
                    or summary_trade.get("theme")
                )
            )
        )
        already_authoritative_and_consistent = bool(
            str(broker_reconciliation.get("source") or "") == "kiwoom.ka10170"
            and str(nested_lifecycle.get("status") or "").lower() == "closed"
            and str(lifecycle_exit.get("broker_day_truth_source") or "") == "kiwoom.ka10170"
            and lifecycle_exit.get("timestamp")
            and entry_price_available
            and metadata_available
            and int(symbol_trade_counts.get(symbol) or 0) <= 1
        )
        if (
            str(
                report.get("status")
                or lifecycle.get("trade_lifecycle_status")
                or lifecycle.get("status")
                or ""
            ).lower()
            == "closed"
            and already_authoritative_and_consistent
        ):
            continue
        buy = _find_buy_order(fill_orders, order_id=str(entry.get("order_id") or ""), symbol=symbol)
        sell = _find_sell_after_buy(fill_orders, buy=buy, symbol=symbol) if buy else {}
        order_pair_truth = _build_order_pair_truth(
            symbol=symbol,
            entry=entry,
            exit_payload=lifecycle_exit if lifecycle_exit else _read_json(exit_path),
            order_rows=fill_orders,
            fee_rows=fee_rows,
        )
        day_diary_row = (
            _find_closed_day_diary_row(day_diary_rows, symbol=symbol, entry=entry)
            if symbol_trade_counts.get(symbol) == 1
            else {}
        )
        if day_diary_row:
            truth = _merge_day_diary_with_order_pair(
                _build_truth_payload_from_day_diary(day_diary_row, symbol=symbol),
                order_pair_truth,
            )
        elif order_pair_truth:
            truth = order_pair_truth
        elif buy and sell:
            truth = _build_truth_payload(symbol=symbol, buy=buy, sell=sell, order_rows=fee_rows)
        else:
            if not day_diary_row:
                skipped.append({"trade_id": trade_id, "symbol": symbol, "reason": "order_pair_or_day_diary_row_not_found"})
                continue
        truth["exit_ts"] = _order_time_to_utc(normalized_day, truth.get("sell_time"))
        used_order_pairs.add(_order_pair_key(truth))
        if report_input_path.exists():
            _write_json(report_input_path, _patch_report_payload(_read_json(report_input_path), truth))
        if compact_input_path.exists():
            _write_json(compact_input_path, _patch_report_payload(_read_json(compact_input_path), truth))
        if report_path.exists():
            _write_json(report_path, _patch_report_payload(report, truth))
        if summary_path.exists():
            _write_json(summary_path, _patch_summary_payload(_read_json(summary_path), truth))
        _write_json(lifecycle_path, _patch_lifecycle_payload(lifecycle, truth))
        _write_json(entry_path, _patch_entry_payload(_read_json(entry_path), truth))
        _write_json(exit_path, _patch_exit_payload(_read_json(exit_path), truth))
        if health_path.exists():
            _write_json(health_path, _patch_health_payload(_read_json(health_path), truth))
        patched.append({"trade_id": trade_id, "symbol": symbol, **truth})
        try:
            from libs.reporting.trade_report_ai import render_trade_summary_markdown_with_evaluation

            summary_md = trade_dir / "reports" / "ai_trade_summary.md"
            summary_md.write_text(
                render_trade_summary_markdown_with_evaluation(_read_json(report_path), _read_json(summary_path)),
                encoding="utf-8-sig",
                newline="\n",
            )
        except Exception:
            pass
    for pair in _pair_same_symbol_round_trips(fee_rows):
        truth = _truth_from_pair(pair, fee_rows=fee_rows)
        if not truth:
            continue
        key = _order_pair_key(truth)
        if key in used_order_pairs:
            continue
        truth["exit_ts"] = _order_time_to_utc(normalized_day, truth.get("sell_time"))
        trade_id = _next_trade_id(normalized_day, str(truth.get("symbol") or ""), trade_dirs)
        trade_dir = _write_synthetic_trade_bundle(
            reports_root=reports_root,
            day=normalized_day,
            truth=truth,
            trade_id=trade_id,
        )
        trade_dirs.append(trade_dir)
        used_order_pairs.add(key)
        synthesized.append({"trade_id": trade_id, "trade_dir": str(trade_dir), **truth})
    return {
        "ok": True,
        "snapshot_path": str(snapshot.get("_snapshot_path") or ""),
        "patched_count": len(patched),
        "patched": patched,
        "synthesized_count": len(synthesized),
        "synthesized": synthesized,
        "skipped": skipped[:20],
    }


__all__ = ["reconcile_broker_closed_trade_reports"]
