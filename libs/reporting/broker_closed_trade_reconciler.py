from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


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


def _side(row: Mapping[str, Any]) -> str:
    text = str(row.get("io_tp_nm") or "").strip()
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


def _find_sell_after_buy(orders: List[Dict[str, Any]], *, buy: Mapping[str, Any], symbol: str) -> Dict[str, Any]:
    qty = _to_int(buy.get("cntr_qty") or buy.get("cnfm_qty") or buy.get("ord_qty"))
    buy_time = _order_time_value(buy)
    candidates = []
    for row in orders:
        if _side(row) != "sell":
            continue
        if symbol and _norm_symbol(row.get("stk_cd")) != symbol:
            continue
        if qty and _to_int(row.get("cntr_qty") or row.get("cnfm_qty") or row.get("ord_qty")) != qty:
            continue
        row_time = _order_time_value(row)
        if buy_time and row_time and row_time <= buy_time:
            continue
        candidates.append(dict(row))
    candidates.sort(key=_order_time_value)
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


def _find_closed_day_diary_row(rows: List[Dict[str, Any]], *, symbol: str, entry: Mapping[str, Any]) -> Dict[str, Any]:
    qty = _to_int(entry.get("qty") or entry.get("filled_qty"))
    buy_price = _to_float(entry.get("price") or entry.get("avg_price") or entry.get("filled_price"))
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
    out["status"] = "closed"
    out["action"] = "SELL"
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
    out["shared_facts"] = shared
    return out


def _patch_summary_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    trade = dict(out.get("trade") or {})
    trade.update({"status": "종결", "action": "매도"})
    trade.update({"status": "종결", "action": "매도"})
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
            "filled_qty": truth.get("qty"),
            "filled_price": truth.get("sell_price"),
            "avg_price": truth.get("sell_price"),
            "quality_score": 100,
            "degraded_but_usable": True,
        }
    )
    out["execution_details"] = details
    return out


def _patch_lifecycle_payload(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    out["trade_lifecycle_status"] = "closed"
    out["status"] = "closed"
    out["symbol"] = truth.get("symbol") or out.get("symbol")
    entry = dict(out.get("entry") or {})
    entry.setdefault("symbol", truth.get("symbol"))
    entry.setdefault("qty", truth.get("qty"))
    entry.setdefault("price", truth.get("buy_price"))
    out["entry"] = entry
    out["exit"] = _patch_exit_payload(dict(out.get("exit") or {}), truth)
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
    out["shared_facts"] = shared
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


def reconcile_broker_closed_trade_reports(*, reports_root: Path = Path("reports"), day: str) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    snapshot = _load_latest_snapshot(normalized_day, reports_root)
    if not snapshot:
        return {"ok": False, "reason": "account_snapshot_missing", "patched_count": 0}
    orders = list(_iter_snapshot_rows(snapshot, "acnt_ord_cntr_prst_array"))
    fee_rows = list(_iter_snapshot_rows(snapshot, "cntr"))
    day_diary_rows = _day_trade_diary_rows(snapshot)
    patched: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    day_root = reports_root / "trades" / normalized_day
    for trade_dir in sorted(day_root.glob("*/*")):
        if not trade_dir.is_dir() or not trade_dir.name.startswith("TRD_"):
            continue
        report_path = trade_dir / "reports" / "ai_trade_report.json"
        summary_path = trade_dir / "reports" / "ai_trade_summary.json"
        lifecycle_path = trade_dir / "lifecycle_bundle.json"
        exit_path = trade_dir / "exit.json"
        health_path = trade_dir / "_health.json"
        entry_path = trade_dir / "entry.json"
        if not entry_path.exists() or not lifecycle_path.exists():
            continue
        report = _read_json(report_path) if report_path.exists() else {}
        lifecycle = _read_json(lifecycle_path)
        if str(report.get("status") or lifecycle.get("trade_lifecycle_status") or lifecycle.get("status") or "").lower() == "closed":
            continue
        trade_id = trade_dir.name
        symbol = _symbol_from_trade_id(trade_id)
        entry = _read_json(entry_path)
        buy = _find_buy_order(orders, order_id=str(entry.get("order_id") or ""), symbol=symbol)
        sell = _find_sell_after_buy(orders, buy=buy, symbol=symbol) if buy else {}
        day_diary_row = _find_closed_day_diary_row(day_diary_rows, symbol=symbol, entry=entry)
        if day_diary_row:
            truth = _build_truth_payload_from_day_diary(day_diary_row, symbol=symbol)
            if buy and sell:
                truth["buy_order_no"] = str(buy.get("ord_no") or "")
                truth["sell_order_no"] = str(sell.get("ord_no") or "")
                truth["buy_time"] = _order_time_value(buy)
                truth["sell_time"] = _order_time_value(sell)
                truth["match_mode"] = "ka10170_with_order_pair_time"
        elif buy and sell:
            truth = _build_truth_payload(symbol=symbol, buy=buy, sell=sell, order_rows=fee_rows)
        else:
            if not day_diary_row:
                skipped.append({"trade_id": trade_id, "symbol": symbol, "reason": "order_pair_or_day_diary_row_not_found"})
                continue
        if report_path.exists():
            _write_json(report_path, _patch_report_payload(report, truth))
        if summary_path.exists():
            _write_json(summary_path, _patch_summary_payload(_read_json(summary_path), truth))
        _write_json(lifecycle_path, _patch_lifecycle_payload(lifecycle, truth))
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
    return {
        "ok": True,
        "snapshot_path": str(snapshot.get("_snapshot_path") or ""),
        "patched_count": len(patched),
        "patched": patched,
        "skipped": skipped[:20],
    }


__all__ = ["reconcile_broker_closed_trade_reports"]
