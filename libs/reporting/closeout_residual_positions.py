from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


KST = timezone(timedelta(hours=9))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return int(default)
        return int(float(text))
    except Exception:
        return int(default)


def _safe_float(value: Any) -> float | None:
    try:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("A") and len(text) == 7:
        text = text[1:]
    return text


def _read_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_call_payload(snapshot: Dict[str, Any], api_id: str) -> Dict[str, Any]:
    for call in list(snapshot.get("calls") or []):
        if not isinstance(call, dict):
            continue
        if str(call.get("api_id") or "").strip() != api_id:
            continue
        payload = call.get("payload")
        return payload if isinstance(payload, dict) else {}
    return {}


def _day_trade_rows(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    payload = _first_call_payload(snapshot, "ka10170")
    out: Dict[str, Dict[str, Any]] = {}
    for row in list(payload.get("tdy_trde_diary") or []):
        if not isinstance(row, dict):
            continue
        symbol = _normalize_symbol(row.get("stk_cd"))
        if not symbol:
            continue
        buy_qty = _safe_int(row.get("buy_qty"))
        sell_qty = _safe_int(row.get("sell_qty"))
        out[symbol] = {
            "symbol": symbol,
            "symbol_name": str(row.get("stk_nm") or "").strip(),
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "open_qty": max(0, buy_qty - sell_qty),
            "avg_price": _safe_float(row.get("buy_avg_pric")),
            "current_price": _safe_float(row.get("cur_prc")),
            "fee_tax": _safe_int(row.get("cmsn_alm_tax")),
            "source": "kiwoom.ka10170",
            "raw": dict(row),
        }
    return out


def _order_rows(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for api_id, key in (
        ("ka10076", "cntr"),
        ("kt00007", "acnt_ord_cntr_prps_dtl"),
        ("kt00009", "acnt_ord_cntr_prst_array"),
    ):
        payload = _first_call_payload(snapshot, api_id)
        rows = payload.get(key) if isinstance(payload.get(key), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("stk_cd"))
            side_text = str(row.get("io_tp_nm") or row.get("trde_tp") or "").strip()
            if not symbol or ("매수" not in side_text and "+매수" not in side_text and "BUY" not in side_text.upper()):
                continue
            out.setdefault(
                symbol,
                {
                    "order_id": str(row.get("ord_no") or row.get("cntr_no") or "").strip(),
                    "order_time": str(row.get("ord_tm") or row.get("cntr_tm") or row.get("cnfm_tm") or "").strip(),
                    "filled_price": _safe_float(row.get("cntr_pric") or row.get("cntr_uv")),
                    "filled_qty": _safe_int(row.get("cntr_qty") or row.get("cnfm_qty") or row.get("ord_qty")),
                    "source": f"kiwoom.{api_id}",
                    "raw": dict(row),
                },
            )
    return out


def _position_rows(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for api_id, key in (
        ("kt00018", "acnt_evlt_remn_indv_tot"),
        ("kt00004", "stk_acnt_evlt_prst"),
    ):
        payload = _first_call_payload(snapshot, api_id)
        rows = payload.get(key) if isinstance(payload.get(key), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("stk_cd"))
            qty = _safe_int(row.get("rmnd_qty"))
            if not symbol or qty <= 0:
                continue
            out[symbol] = {
                "symbol": symbol,
                "symbol_name": str(row.get("stk_nm") or "").strip(),
                "qty": qty,
                "avg_price": _safe_float(row.get("pur_pric") or row.get("avg_prc")),
                "current_price": _safe_float(row.get("cur_prc")),
                "unrealized_pnl": _safe_float(row.get("evltv_prft") or row.get("pl_amt")),
                "account_pnl_ratio": (
                    (_safe_float(row.get("prft_rt") or row.get("pl_rt")) or 0.0) / 100.0
                    if _safe_float(row.get("prft_rt") or row.get("pl_rt")) is not None
                    else None
                ),
                "source": f"kiwoom.{api_id}",
                "raw": dict(row),
            }
    return out


def extract_unclosed_positions_from_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    positions = _position_rows(snapshot)
    day_rows = _day_trade_rows(snapshot)
    order_rows = _order_rows(snapshot)
    out: List[Dict[str, Any]] = []
    for symbol, position in sorted(positions.items()):
        day_row = day_rows.get(symbol, {})
        order_row = order_rows.get(symbol, {})
        buy_qty = _safe_int(day_row.get("buy_qty"), _safe_int(position.get("qty")))
        sell_qty = _safe_int(day_row.get("sell_qty"))
        open_qty = _safe_int(day_row.get("open_qty"), _safe_int(position.get("qty")))
        if open_qty <= 0:
            open_qty = _safe_int(position.get("qty"))
        row = {
            **position,
            "qty": open_qty,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "order_id": str(order_row.get("order_id") or "").strip(),
            "order_time": str(order_row.get("order_time") or "").strip(),
            "entry_price": order_row.get("filled_price") or day_row.get("avg_price") or position.get("avg_price"),
            "entry_qty": order_row.get("filled_qty") or open_qty,
            "day_trade_source": day_row.get("source") or "",
            "order_source": order_row.get("source") or "",
            "unclosed_reason": "broker_snapshot_position_without_same_day_sell",
        }
        out.append(row)
    return out


def _entry_ts_from_order_time(day: str, order_time: str) -> str:
    digits = "".join(ch for ch in str(order_time or "") if ch.isdigit())
    if len(digits) >= 6:
        hh, mm, ss = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    elif len(digits) >= 4:
        hh, mm, ss = int(digits[:2]), int(digits[2:4]), 0
    else:
        hh, mm, ss = 15, 20, 0
    local = datetime.strptime(str(day)[:10], "%Y-%m-%d").replace(
        hour=hh,
        minute=mm,
        second=ss,
        tzinfo=KST,
    )
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def _time_bucket_from_order_time(order_time: str) -> str:
    digits = "".join(ch for ch in str(order_time or "") if ch.isdigit())
    if len(digits) >= 2:
        return f"{int(digits[:2]):02d}00"
    return "1500"


def _existing_lifecycle_symbols(reports_root: Path, day: str) -> set[str]:
    symbols: set[str] = set()
    root = reports_root / "trades" / str(day)[:10]
    for path in root.glob("*/*/lifecycle_bundle.json"):
        payload = _read_json(path)
        if isinstance(payload, dict):
            symbol = _normalize_symbol(payload.get("symbol"))
            if symbol:
                symbols.add(symbol)
    return symbols


def _next_trade_id(reports_root: Path, day: str, symbol: str) -> str:
    root = reports_root / "trades" / str(day)[:10]
    prefix = f"TRD_{str(day).replace('-', '')}_{symbol}_"
    max_idx = 0
    for path in root.glob(f"*/*{symbol}*"):
        name = path.name
        if not name.startswith(prefix):
            continue
        try:
            max_idx = max(max_idx, int(name.rsplit("_", 1)[-1]))
        except Exception:
            continue
    return f"{prefix}{max_idx + 1:02d}"


def backfill_open_lifecycle_reports(
    *,
    reports_root: Path,
    day: str,
    positions: List[Dict[str, Any]],
    snapshot_path: str = "",
    trigger: str = "closeout_residual_backfill",
) -> Dict[str, Any]:
    existing = _existing_lifecycle_symbols(reports_root, day)
    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for row in positions:
        symbol = _normalize_symbol(row.get("symbol"))
        if not symbol:
            continue
        if symbol in existing:
            skipped.append({"symbol": symbol, "reason": "lifecycle_already_exists"})
            continue
        trade_id = _next_trade_id(reports_root, day, symbol)
        bucket = _time_bucket_from_order_time(str(row.get("order_time") or ""))
        trade_dir = reports_root / "trades" / str(day)[:10] / bucket / trade_id
        entry_ts = _entry_ts_from_order_time(day, str(row.get("order_time") or ""))
        entry_payload = {
            "run_id": str(row.get("order_id") or ""),
            "ts": entry_ts,
            "action": "BUY",
            "price": row.get("entry_price") or row.get("avg_price"),
            "qty": _safe_int(row.get("qty")),
            "filled_qty": _safe_int(row.get("qty")),
            "order_id": str(row.get("order_id") or ""),
            "reason_human": "Recovered open position from Kiwoom broker truth after closeout.",
            "execution_details": {
                "order_status": "체결",
                "order_id": str(row.get("order_id") or ""),
                "filled_qty": _safe_int(row.get("qty")),
                "avg_price": row.get("entry_price") or row.get("avg_price"),
                "broker_truth_source": row.get("order_source") or row.get("source") or "kiwoom.account_snapshot",
                "broker_day_truth_source": row.get("day_trade_source") or "",
                "broker_day_authoritative": True,
            },
        }
        hold_payload = {
            "status": "open",
            "reason": "closeout_unresolved_position",
            "current_price": row.get("current_price"),
            "unrealized_pnl": row.get("unrealized_pnl"),
            "account_pnl_ratio": row.get("account_pnl_ratio"),
        }
        lifecycle = {
            "schema_version": "lifecycle_bundle.v1",
            "trade_id": trade_id,
            "symbol": symbol,
            "symbol_name": str(row.get("symbol_name") or ""),
            "day": str(day)[:10],
            "trade_lifecycle_status": "open",
            "status": "open",
            "entry": dict(entry_payload),
            "hold": dict(hold_payload),
            "exit": {},
            "lifecycle": {
                "entry": dict(entry_payload),
                "holding": dict(hold_payload),
                "exit": {},
            },
            "execution_details": {
                "order_status": "체결",
                "order_id": str(row.get("order_id") or ""),
                "filled_qty": _safe_int(row.get("qty")),
                "avg_price": row.get("entry_price") or row.get("avg_price"),
                "broker_truth_source": row.get("order_source") or row.get("source") or "kiwoom.account_snapshot",
                "broker_day_truth_source": row.get("day_trade_source") or "",
                "broker_day_authoritative": True,
            },
            "closeout_residual_recovery": {
                "trigger": str(trigger or ""),
                "snapshot_path": str(snapshot_path or ""),
                "reason": str(row.get("unclosed_reason") or "broker_snapshot_position_without_same_day_sell"),
                "requires_next_open_flatten": True,
            },
        }
        trade_dir.mkdir(parents=True, exist_ok=True)
        _write_json(trade_dir / "lifecycle_bundle.json", lifecycle)
        _write_json(trade_dir / "entry.json", lifecycle["entry"])
        _write_json(trade_dir / "hold.json", lifecycle["hold"])
        _write_json(trade_dir / "_health.json", {"ok": False, "status": "open_unclosed_position_recovered"})
        _write_json(
            trade_dir / "_provenance.json",
            {
                "source": "closeout_residual_positions",
                "trigger": str(trigger or ""),
                "snapshot_path": str(snapshot_path or ""),
            },
        )
        created.append({"symbol": symbol, "trade_id": trade_id, "trade_root_path": str(trade_dir)})
    return {"created_count": len(created), "created": created, "skipped": skipped}


def mark_unresolved_positions_in_state(
    *,
    state_path: Path,
    positions: List[Dict[str, Any]],
    day: str,
    snapshot_path: str = "",
    trigger: str = "closeout_residual_reconcile",
) -> Dict[str, Any]:
    state = _read_json(state_path)
    if not isinstance(state, dict):
        state = {}
    detected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    normalized_positions: List[Dict[str, Any]] = []
    unresolved: Dict[str, Dict[str, Any]] = {}
    for row in positions:
        symbol = _normalize_symbol(row.get("symbol"))
        qty = _safe_int(row.get("qty"))
        if not symbol or qty <= 0:
            continue
        normalized = {
            "symbol": symbol,
            "qty": qty,
            "avg_price": row.get("avg_price") or row.get("entry_price"),
            "current_price": row.get("current_price"),
            "unrealized_pnl": row.get("unrealized_pnl"),
            "account_pnl_ratio": row.get("account_pnl_ratio"),
            "position_entry_epoch": None,
        }
        normalized_positions.append(normalized)
        unresolved[symbol] = {
            "symbol": symbol,
            "qty": qty,
            "detected_at": detected_at,
            "detected_day": str(day)[:10],
            "snapshot_path": str(snapshot_path or ""),
            "requires_immediate_flatten": True,
            "requires_next_open_flatten": True,
            "approved_carry": False,
            "reason": "closeout_broker_truth_unresolved_position",
        }
    state["mock_positions"] = normalized_positions
    state["open_positions"] = len(normalized_positions)
    if unresolved:
        state["closeout_unresolved_flatten_by_symbol"] = unresolved
    else:
        state.pop("closeout_unresolved_flatten_by_symbol", None)
    state["closeout_backup_liquidation"] = {
        "applied": False,
        "applied_at": detected_at,
        "mode": "broker_truth_unresolved_positions_retained" if unresolved else "noop_broker_truth_already_flat",
        "symbols": list(unresolved.keys()),
        "qty_total": sum(_safe_int(row.get("qty")) for row in normalized_positions),
        "carry_forward_symbols": [],
        "flattened_symbols": [],
        "unresolved_flatten_symbols": list(unresolved.keys()),
        "unresolved_flatten_requires_next_open_symbols": list(unresolved.keys()),
        "requires_next_open_flatten": bool(unresolved),
        "reason": "closeout_broker_truth_unresolved_positions_retained" if unresolved else "broker_truth_already_flat",
        "snapshot_path": str(snapshot_path or ""),
        "trigger": str(trigger or ""),
    }
    state["broker_truth_position_reconciliation"] = {
        "authoritative": True,
        "generated_at": detected_at,
        "day": str(day)[:10],
        "snapshot_path": str(snapshot_path or ""),
        "trigger": str(trigger or ""),
        "position_count": len(normalized_positions),
        "symbols": list(unresolved.keys()),
    }
    _write_json(state_path, state)
    return {
        "ok": not bool(unresolved),
        "state_path": str(state_path),
        "unresolved_symbols": list(unresolved.keys()),
        "position_count": len(normalized_positions),
        "requires_next_open_flatten": bool(unresolved),
    }


def reconcile_closeout_residual_positions(
    *,
    reports_root: Path,
    day: str,
    snapshot: Dict[str, Any],
    state_path: Path,
    trigger: str = "closeout_residual_reconcile",
) -> Dict[str, Any]:
    snapshot_path = str(snapshot.get("path") or "")
    positions = extract_unclosed_positions_from_snapshot(snapshot)
    lifecycle = backfill_open_lifecycle_reports(
        reports_root=reports_root,
        day=day,
        positions=positions,
        snapshot_path=snapshot_path,
        trigger=trigger,
    )
    state = mark_unresolved_positions_in_state(
        state_path=state_path,
        positions=positions,
        day=day,
        snapshot_path=snapshot_path,
        trigger=trigger,
    )
    return {
        "ok": not bool(positions),
        "position_count": len(positions),
        "positions": positions,
        "unresolved_symbols": [str(row.get("symbol") or "") for row in positions],
        "requires_next_open_flatten": bool(positions),
        "lifecycle_backfill": lifecycle,
        "state_reconciliation": state,
        "snapshot_path": snapshot_path,
    }


__all__ = [
    "extract_unclosed_positions_from_snapshot",
    "reconcile_closeout_residual_positions",
    "backfill_open_lifecycle_reports",
    "mark_unresolved_positions_in_state",
]
