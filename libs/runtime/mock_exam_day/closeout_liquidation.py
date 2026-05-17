from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from libs.core.symbols import normalize_symbol
from libs.runtime.mock_exam_day.common import read_env_file, resolve_path, to_int, utc_now_iso
from libs.storage.state_store import StateStore


PortfolioReader = Callable[[Dict[str, Any], Dict[str, str]], List[Dict[str, Any]]]


def resolve_state_store_path(common: Dict[str, Any], *, root: Path) -> Path:
    explicit = common.get("state_path")
    if explicit:
        return Path(explicit)
    env_obj = read_env_file(Path(common["env_path"]))
    raw = str(env_obj.get("STATE_STORE_PATH", "")).strip()
    return resolve_path(raw, "data/state.json", root=root)


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def resolve_execution_mode_from_env(env_obj: Dict[str, str]) -> str:
    raw = str(env_obj.get("EXECUTION_MODE") or "").strip().lower()
    if raw in ("mock", "real"):
        return raw
    kiwoom_mode = str(env_obj.get("KIWOOM_MODE") or "mock").strip().lower()
    return "real" if kiwoom_mode == "real" else "mock"


def normalize_position_row(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = normalize_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
    qty = to_int(row.get("qty"), 0)
    out: Dict[str, Any] = {
        "symbol": symbol,
        "qty": qty,
        "avg_price": to_float(row.get("avg_price"), 0.0),
        "unrealized_pnl": to_float(row.get("unrealized_pnl"), 0.0),
    }
    if row.get("account_pnl_ratio") not in (None, ""):
        out["account_pnl_ratio"] = to_float(row.get("account_pnl_ratio"), 0.0)
        out["account_pnl_ratio_source"] = str(row.get("account_pnl_ratio_source") or "").strip()
    if row.get("current_price") not in (None, ""):
        current_price = to_float(row.get("current_price"), 0.0)
        if current_price > 0.0:
            out["current_price"] = float(current_price)
    if row.get("position_entry_epoch") not in (None, ""):
        entry_epoch = to_int(row.get("position_entry_epoch"), 0)
        if entry_epoch > 0:
            out["position_entry_epoch"] = int(entry_epoch)
    return out


def read_authoritative_portfolio_rows(common: Dict[str, Any], env_obj: Dict[str, str]) -> List[Dict[str, Any]]:
    old_env = {key: os.environ.get(key) for key in env_obj}
    try:
        for key, value in env_obj.items():
            os.environ[str(key)] = str(value)
        from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader

        snap = KiwoomPortfolioReader.from_env().get_portfolio_snapshot()
        rows = snap.to_dict().get("positions")
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    out: List[Dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        normalized = normalize_position_row(row)
        if normalized.get("symbol") and int(normalized.get("qty") or 0) > 0:
            out.append(normalized)
    return out


def merge_position_metadata(rows: List[Dict[str, Any]], state_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    state_by_symbol = {
        str(row.get("symbol") or "").strip(): dict(row)
        for row in state_rows
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    }
    out: List[Dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        local = state_by_symbol.get(str(row.get("symbol") or "").strip()) or {}
        for key in ("position_entry_epoch", "hold_sec", "position_age_seconds"):
            if row.get(key) in (None, "") and local.get(key) not in (None, ""):
                row[key] = local.get(key)
        out.append(row)
    return out


def filter_state_position_metadata(state: Dict[str, Any], symbols: List[str]) -> None:
    allowed = {str(sym or "").strip() for sym in symbols if str(sym or "").strip()}
    for key in ("position_peak_price", "position_strategy_context", "position_entry_epoch_by_symbol"):
        existing = state.get(key) if isinstance(state.get(key), dict) else {}
        filtered = {
            str(sym): value
            for sym, value in dict(existing).items()
            if str(sym) in allowed
        }
        if filtered:
            state[key] = filtered
        else:
            state.pop(key, None)


def closeout_backup_liquidation(
    common: Dict[str, Any],
    *,
    root: Path,
    portfolio_reader: PortfolioReader = read_authoritative_portfolio_rows,
) -> Dict[str, Any]:
    t0 = time.time()
    state_path = resolve_state_store_path(common, root=root)
    env_obj = read_env_file(Path(common["env_path"]))
    kiwoom_mode = str(env_obj.get("KIWOOM_MODE") or "mock").strip().lower()
    execution_mode = resolve_execution_mode_from_env(env_obj)
    broker_truth_authoritative = kiwoom_mode == "mock" and execution_mode == "real"
    out: Dict[str, Any] = {
        "step_id": "closeout.backup_liquidation",
        "mode": "noop",
        "ok": True,
        "rc": 0,
        "state_path": str(state_path),
        "portfolio_truth_source": "broker_reader_authoritative" if broker_truth_authoritative else "state_mock_positions",
        "kiwoom_mode": kiwoom_mode,
        "execution_mode": execution_mode,
        "positions_before": 0,
        "positions_after": 0,
        "qty_total_before": 0,
        "symbols_before": [],
        "symbols_after": [],
        "unresolved_flatten_symbols": [],
        "unresolved_flatten_requires_next_open_symbols": [],
        "requires_next_open_flatten": False,
        "overnight_carry_anomalies": [],
        "error": "",
        "duration_sec": 0.0,
    }
    try:
        store = StateStore(str(state_path))
        state = store.load()
        raw_positions = state.get("mock_positions")
        positions: List[Dict[str, Any]] = []
        carry_rows: List[Dict[str, Any]] = []
        flatten_rows: List[Dict[str, Any]] = []
        local_state_rows = [
            normalize_position_row(row)
            for row in (raw_positions if isinstance(raw_positions, list) else [])
            if isinstance(row, dict)
        ]
        if broker_truth_authoritative:
            try:
                broker_rows = portfolio_reader(common, env_obj)
            except Exception as ex:
                out["mode"] = "broker_truth_unavailable"
                out["ok"] = False
                out["rc"] = 3
                out["error"] = f"broker_truth_unavailable:{type(ex).__name__}: {ex}"
                out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
                return out
            raw_positions = merge_position_metadata(broker_rows, local_state_rows)
            out["broker_truth_available"] = True
            out["broker_positions_count"] = len(raw_positions if isinstance(raw_positions, list) else [])
        overnight_map = (
            state.get("overnight_decision_by_symbol")
            if isinstance(state.get("overnight_decision_by_symbol"), dict)
            else {}
        )
        for row in raw_positions if isinstance(raw_positions, list) else []:
            if not isinstance(row, dict):
                continue
            qty = to_int(row.get("qty"), 0)
            symbol = str(row.get("symbol") or "").strip()
            if qty <= 0 or not symbol:
                continue
            rec = {"symbol": symbol, "qty": qty, "row": dict(row)}
            positions.append(rec)
            decision = overnight_map.get(symbol) if isinstance(overnight_map, dict) else None
            if isinstance(decision, dict) and bool(decision.get("anomaly")):
                out["overnight_carry_anomalies"].append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "anomaly_reason": str(decision.get("anomaly_reason") or ""),
                        "decision_reason": str(decision.get("reason") or ""),
                    }
                )
                flatten_rows.append(rec)
            elif isinstance(decision, dict) and bool(decision.get("approved")):
                carry_rows.append(rec)
            else:
                flatten_rows.append(rec)
        out["positions_before"] = len(positions)
        out["qty_total_before"] = sum(int(row.get("qty") or 0) for row in positions)
        out["symbols_before"] = [str(row.get("symbol") or "") for row in positions]
        if not positions:
            state["mock_positions"] = []
            state["open_positions"] = 0
            state.pop("closeout_unresolved_flatten_by_symbol", None)
            filter_state_position_metadata(state, [])
            if broker_truth_authoritative:
                state["closeout_backup_liquidation"] = {
                    "applied": False,
                    "applied_at": utc_now_iso(),
                    "mode": "noop_broker_truth_already_flat",
                    "symbols": [],
                    "qty_total": 0,
                    "carry_forward_symbols": [],
                    "flattened_symbols": [],
                    "unresolved_flatten_symbols": [],
                    "unresolved_flatten_requires_next_open_symbols": [],
                    "requires_next_open_flatten": False,
                    "reason": "broker_truth_already_flat",
                }
                store.save(state)
                out["mode"] = "noop_broker_truth_already_flat"
                out["positions_after"] = 0
                out["symbols_after"] = []
                out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
                return out
            out["mode"] = "noop_already_flat"
            out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
            return out
        if kiwoom_mode != "mock":
            out["mode"] = "non_mock_requires_manual_flatten"
            out["ok"] = False
            out["rc"] = 2
            out["error"] = "backup_liquidation_non_mock_not_supported"
            out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
            return out

        carry_symbols = [str(row.get("symbol") or "") for row in carry_rows]
        flatten_symbols = [str(row.get("symbol") or "") for row in flatten_rows]
        if broker_truth_authoritative:
            unresolved_symbols = list(flatten_symbols)
            applied_at = utc_now_iso()
            unresolved_by_symbol = {
                str(row.get("symbol") or ""): {
                    "symbol": str(row.get("symbol") or ""),
                    "qty": int(row.get("qty") or 0),
                    "detected_at": applied_at,
                    "requires_immediate_flatten": True,
                    "approved_carry": False,
                    "reason": "closeout_unresolved_flatten_required",
                }
                for row in flatten_rows
                if str(row.get("symbol") or "").strip()
            }
            broker_position_rows = [dict(row.get("row") or {}) for row in positions]
            state["mock_positions"] = broker_position_rows
            state["open_positions"] = len(broker_position_rows)
            state["mock_position_desync_reconciled"] = True
            state["portfolio_reconcile_reason"] = "closeout_broker_truth_authoritative"
            filter_state_position_metadata(state, [str(row.get("symbol") or "") for row in broker_position_rows])
            if unresolved_by_symbol:
                state["closeout_unresolved_flatten_by_symbol"] = dict(unresolved_by_symbol)
            else:
                state.pop("closeout_unresolved_flatten_by_symbol", None)
            state["closeout_backup_liquidation"] = {
                "applied": False,
                "applied_at": applied_at,
                "mode": (
                    "noop_carry_forward"
                    if carry_rows and not flatten_rows
                    else "broker_truth_unresolved_positions_retained"
                ),
                "symbols": list(unresolved_symbols),
                "qty_total": int(sum(int(row.get("qty") or 0) for row in flatten_rows)),
                "carry_forward_symbols": list(carry_symbols),
                "flattened_symbols": [],
                "unresolved_flatten_symbols": list(unresolved_symbols),
                "unresolved_flatten_requires_next_open_symbols": list(unresolved_symbols),
                "requires_next_open_flatten": bool(unresolved_symbols),
                "overnight_carry_anomalies": list(out["overnight_carry_anomalies"]),
                "reason": (
                    "overnight_carry_approved"
                    if carry_rows and not flatten_rows
                    else "closeout_broker_truth_unresolved_positions_retained"
                ),
            }
            store.save(state)
            out["mode"] = str(state["closeout_backup_liquidation"]["mode"])
            out["positions_after"] = len(broker_position_rows)
            out["symbols_after"] = [str(row.get("symbol") or "") for row in broker_position_rows]
            out["carry_forward_symbols"] = list(carry_symbols)
            out["flattened_symbols"] = []
            out["unresolved_flatten_symbols"] = list(unresolved_symbols)
            out["unresolved_flatten_requires_next_open_symbols"] = list(unresolved_symbols)
            out["requires_next_open_flatten"] = bool(unresolved_symbols)
            out["state_reconciled_to_broker"] = True
            if unresolved_symbols:
                out["ok"] = False
                out["rc"] = 3
                out["error"] = "closeout_unresolved_positions:" + ",".join(unresolved_symbols)
            out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
            return out
        state["mock_positions"] = [dict(row.get("row") or {}) for row in carry_rows]
        state["open_positions"] = len(carry_rows)
        state.pop("closeout_unresolved_flatten_by_symbol", None)
        filter_state_position_metadata(state, carry_symbols)
        state["closeout_backup_liquidation"] = {
            "applied": bool(flatten_rows),
            "applied_at": utc_now_iso(),
            "mode": (
                "noop_carry_forward"
                if carry_rows and not flatten_rows
                else "mock_backup_partial_flatten"
                if carry_rows and flatten_rows
                else "mock_backup_flatten"
            ),
            "symbols": list(flatten_symbols or out["symbols_before"]),
            "qty_total": int(sum(int(row.get("qty") or 0) for row in flatten_rows) if flatten_rows else out["qty_total_before"]),
            "carry_forward_symbols": list(carry_symbols),
            "flattened_symbols": list(flatten_symbols),
            "unresolved_flatten_symbols": [],
            "unresolved_flatten_requires_next_open_symbols": [],
            "requires_next_open_flatten": False,
            "overnight_carry_anomalies": list(out["overnight_carry_anomalies"]),
            "reason": (
                "closeout_flattened_overnight_carry_anomaly"
                if out["overnight_carry_anomalies"] and not carry_rows
                else "closeout_respected_overnight_carry_with_anomaly_override"
                if out["overnight_carry_anomalies"] and carry_rows
                else "overnight_carry_approved"
                if carry_rows and not flatten_rows
                else "closeout_respected_overnight_carry"
                if carry_rows and flatten_rows
                else "closeout_forced_flatten_backup"
            ),
        }
        store.save(state)
        out["mode"] = str(state["closeout_backup_liquidation"]["mode"])
        out["positions_after"] = len(carry_rows)
        out["symbols_after"] = list(carry_symbols)
        out["carry_forward_symbols"] = list(carry_symbols)
        out["flattened_symbols"] = list(flatten_symbols)
    except Exception as ex:
        out["ok"] = False
        out["rc"] = 1
        out["error"] = f"{type(ex).__name__}: {ex}"
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out
