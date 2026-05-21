from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.core.symbols import normalize_symbol
from libs.reporting.llm_artifacts import iter_trade_dirs
from libs.reporting.trade_fallback_text import (
    ENTRY_REASON_NOT_CAPTURED,
    EXIT_REASON_NOT_CAPTURED,
    HOLDING_DURATION_UNAVAILABLE,
    OPEN_POSITION_WATCHING,
    PARTIAL_EXIT_EVIDENCE_MISSING,
)
from libs.reporting.trade_story_pipeline import classify_story_type as _classify_story_type, execution_mode_label, safe_int

def _is_placeholder_entry_reason(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {
        "",
        "no_position",
        "entry reasoning was not captured.",
        "entry reasoning was not captured",
        "진입 이유는 기록되지 않았습니다.",
        "-",
        "n/a",
    }



def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}



def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    raw = str(ts).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        pass
    stamped = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(stamped)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None



def _format_duration_human(seconds: int) -> str:
    if seconds <= 0:
        return "0m"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds / 60.0:.1f}m"
    return f"{seconds / 3600.0:.1f}h"



def _build_trade_id(day: str, symbol: str, seq: int) -> str:
    compact_day = str(day or "").replace("-", "")
    clean_symbol = normalize_symbol(symbol or "", allow_test_symbols=True) or "UNKNOWN"
    return f"TRD_{compact_day}_{clean_symbol}_{int(seq):02d}"



def _trade_id_sequence(trade_id: str) -> int:
    text = str(trade_id or "").strip()
    if not text:
        return 10**9
    tail = text.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except Exception:
        return 10**9



def _extract_lifecycle_entry(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    if entry:
        return dict(entry)
    lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    return dict(entry)


def _extract_lifecycle_exit(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    exit_ctx = payload.get("exit") if isinstance(payload.get("exit"), dict) else {}
    if exit_ctx:
        return dict(exit_ctx)
    lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    return dict(exit_ctx)


def _extract_lifecycle_holding(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    holding = payload.get("hold") if isinstance(payload.get("hold"), dict) else {}
    if holding:
        return dict(holding)
    holding = payload.get("holding") if isinstance(payload.get("holding"), dict) else {}
    if holding:
        return dict(holding)
    lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    if holding:
        return dict(holding)
    hold = lifecycle.get("hold") if isinstance(lifecycle.get("hold"), dict) else {}
    return dict(hold)


def _load_existing_open_lifecycle_candidates(
    *,
    reports_root: Path,
    day: str,
) -> Dict[str, List[Dict[str, Any]]]:
    candidates: Dict[str, List[Dict[str, Any]]] = {}
    day_text = str(day or "").strip()
    days_to_scan: List[str] = []
    if day_text:
        days_to_scan.append(day_text)
        try:
            parsed_day = datetime.strptime(day_text, "%Y-%m-%d").date()
            for offset in range(1, 4):
                previous = (parsed_day - timedelta(days=offset)).isoformat()
                if previous not in days_to_scan:
                    days_to_scan.append(previous)
        except Exception:
            pass

    seen_trade_ids: set[str] = set()
    for scan_day in days_to_scan:
        day_root = Path(reports_root) / "trades" / scan_day
        if not day_root.exists():
            continue
        for trade_dir in iter_trade_dirs(day_root):
            trade_id = str(trade_dir.name or "").strip()
            if trade_id and trade_id in seen_trade_ids:
                continue
            if trade_id:
                seen_trade_ids.add(trade_id)
            _add_existing_open_lifecycle_candidate(
                candidates=candidates,
                trade_dir=trade_dir,
                source_day=scan_day,
            )
    for symbol, rows in candidates.items():
        rows.sort(
            key=lambda row: (
                str(row.get("source_day") or ""),
                _trade_id_sequence(str(row.get("trade_id") or "")),
                float(row.get("entry_ts_epoch") or 0.0),
            ),
            reverse=True,
        )
    return candidates


def _add_existing_open_lifecycle_candidate(
    *,
    candidates: Dict[str, List[Dict[str, Any]]],
    trade_dir: Path,
    source_day: str,
) -> None:
    lifecycle_path = trade_dir / "lifecycle_bundle.json"
    if not lifecycle_path.exists():
        return
    payload = _read_json_if_exists(lifecycle_path)
    if not isinstance(payload, dict) or not payload:
        return
    status = str(payload.get("trade_lifecycle_status") or payload.get("status") or "").strip().lower()
    if status not in {"open", "partial"}:
        return
    entry_ctx = _extract_lifecycle_entry(payload)
    if not _has_substantive_entry_evidence(entry_ctx):
        return
    exit_ctx = _extract_lifecycle_exit(payload)
    if str(exit_ctx.get("run_id") or "").strip():
        # Closed lifecycle should not be reused.
        return
    symbol = normalize_symbol(
        payload.get("symbol")
        or entry_ctx.get("symbol")
        or (payload.get("execution") or {}).get("symbol")
        or "",
        allow_test_symbols=True,
    )
    if not symbol:
        return
    holding = _extract_lifecycle_holding(payload)
    run_ids_all = [str(x or "").strip() for x in list(payload.get("linked_run_ids") or []) if str(x or "").strip()]
    entry_run_id = str(entry_ctx.get("run_id") or "").strip()
    if entry_run_id and entry_run_id not in run_ids_all:
        run_ids_all.append(entry_run_id)
    for item in list(holding.get("run_ids") or []):
        rid = str(item or "").strip()
        if rid and rid not in run_ids_all:
            run_ids_all.append(rid)
    candidate = {
        "trade_id": str(payload.get("trade_id") or trade_dir.name or "").strip(),
        "symbol": symbol,
        "status": status,
        "entry": dict(entry_ctx),
        "holding": dict(holding),
        "run_ids_all": run_ids_all,
        "story_type": str(payload.get("story_type") or "simulation"),
        "execution_mode_label": str(payload.get("execution_mode_label") or "simulation (mock broker)"),
        "timeline": [dict(row) for row in list(payload.get("timeline") or []) if isinstance(row, dict)],
        "warnings": [str(x or "") for x in list(payload.get("warnings") or []) if str(x or "").strip()],
        "entry_ts_epoch": _to_epoch(entry_ctx.get("ts")) or 0.0,
        "source_day": str(source_day or ""),
        "source_trade_dir": str(trade_dir),
    }
    candidates.setdefault(symbol, []).append(candidate)


def _snapshot_execution_debug(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
    return {
        "execution_symbol": str(snapshot.get("symbol") or execution.get("symbol") or ""),
        "execution_ts": str(snapshot.get("ts_start") or ""),
        "execution_side": str(snapshot.get("execution_action") or execution.get("action") or "").upper(),
        "execution_order_id": str(
            execution.get("ord_no")
            or snapshot.get("execution_ord_no")
            or execution.get("order_id")
            or ""
        ),
        "execution_run_id": str(snapshot.get("run_id") or ""),
        "execution_filled_qty": safe_int(
            execution.get("qty")
            if execution.get("qty") not in (None, "")
            else snapshot.get("execution_qty"),
            0,
        ),
        "execution_filled_price": (
            execution.get("price")
            if execution.get("price") not in (None, "")
            else snapshot.get("execution_price")
        ),
    }


def _build_lifecycle_from_seed(
    *,
    trade_id: str,
    symbol: str,
    day: str,
    execution_mode_label_text: str,
    story_type: str,
) -> Dict[str, Any]:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "day": day,
        "status": "open",
        "execution_mode_label": execution_mode_label_text,
        "story_type": story_type,
        "entry": {},
        "holding": {
            "run_ids": [],
            "holding_events": [],
            "posture_history": [],
            "monitor_updates": [],
            "noteworthy_changes": [],
        },
        "exit": {},
        "run_ids_all": [],
        "summary": {},
        "reporter": {},
        "timeline": [],
        "warnings": [],
    }


def _has_substantive_entry_evidence(entry: Dict[str, Any]) -> bool:
    entry_obj = entry if isinstance(entry, dict) else {}
    if not entry_obj:
        return False
    if str(entry_obj.get("run_id") or "").strip():
        return True
    if str(entry_obj.get("ts") or "").strip():
        return True
    for key in ("price", "avg_price", "qty"):
        value = entry_obj.get(key)
        if value not in (None, "", 0, 0.0):
            return True
    scanner_context = entry_obj.get("scanner_context") if isinstance(entry_obj.get("scanner_context"), dict) else {}
    if str(scanner_context.get("selected_symbol") or "").strip():
        return True
    if str(scanner_context.get("summary") or "").strip():
        return True
    execution_context = entry_obj.get("execution_context") if isinstance(entry_obj.get("execution_context"), dict) else {}
    execution_details = entry_obj.get("execution_details") if isinstance(entry_obj.get("execution_details"), dict) else {}
    if str(execution_context.get("order_status") or execution_details.get("order_status") or "").strip():
        return True
    if str(execution_context.get("order_id") or execution_details.get("order_id") or "").strip():
        return True
    return False


def _holding_partial_exit_total(holding: Dict[str, Any]) -> int:
    if not isinstance(holding, dict):
        return 0
    total = 0
    for row in list(holding.get("partial_exits") or []):
        if isinstance(row, dict):
            total += max(0, safe_int(row.get("qty"), 0))
    return int(total)


def _exit_closure_quantity_state(lifecycle: Dict[str, Any], exit_ctx: Dict[str, Any]) -> Dict[str, Any]:
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    entry_qty = max(0, safe_int(entry.get("qty"), 0))
    filled_qty_present = exit_ctx.get("filled_qty") not in (None, "")
    exit_qty = max(
        0,
        safe_int(exit_ctx.get("filled_qty") if filled_qty_present else exit_ctx.get("qty"), 0),
    )
    previous_partial_exit_qty = _holding_partial_exit_total(holding)
    cumulative_exit_qty = int(previous_partial_exit_qty + exit_qty)
    remaining_qty = max(0, int(entry_qty - cumulative_exit_qty)) if entry_qty > 0 else 0
    return {
        "entry_qty": int(entry_qty),
        "exit_qty": int(exit_qty),
        "previous_partial_exit_qty": int(previous_partial_exit_qty),
        "cumulative_exit_qty": int(cumulative_exit_qty),
        "remaining_qty": int(remaining_qty),
        "closes_position": bool(
            (not filled_qty_present and entry_qty <= 0)
            or (exit_qty > 0 and cumulative_exit_qty >= entry_qty)
        ),
    }


def _record_partial_exit(
    lifecycle: Dict[str, Any],
    *,
    exit_ctx: Dict[str, Any],
    run_id: str,
    ts: str,
    closure_state: Dict[str, Any],
) -> None:
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    holding.setdefault("run_ids", [])
    holding.setdefault("holding_events", [])
    holding.setdefault("posture_history", [])
    holding.setdefault("monitor_updates", [])
    holding.setdefault("partial_exits", [])
    if run_id and run_id not in holding["run_ids"]:
        holding["run_ids"].append(run_id)
    partial_exit = {
        "run_id": str(run_id or ""),
        "ts": str(ts or ""),
        "qty": int(closure_state.get("exit_qty") or 0),
        "entry_qty": int(closure_state.get("entry_qty") or 0),
        "cumulative_exit_qty": int(closure_state.get("cumulative_exit_qty") or 0),
        "remaining_qty": int(closure_state.get("remaining_qty") or 0),
        "reason_human": str(exit_ctx.get("reason_human") or ""),
        "exit_context": dict(exit_ctx or {}),
    }
    holding["partial_exits"].append(partial_exit)
    holding["holding_events"].append(
        {
            "run_id": str(run_id or ""),
            "ts": str(ts or ""),
            "posture": "PARTIAL_EXIT",
            "monitor_reason": str(exit_ctx.get("reason_human") or ""),
            "exit_reason": str(exit_ctx.get("reason_human") or ""),
            "monitor_context": dict(exit_ctx.get("monitor_context") or {}),
            "summary": (
                f"Partial SELL {partial_exit['qty']} recorded; "
                f"remaining qty {partial_exit['remaining_qty']} before full trade report."
            ),
        }
    )
    holding["posture_history"].append({"ts": str(ts or ""), "posture": "PARTIAL_EXIT"})
    holding["monitor_updates"].append("partial_exit_recorded")
    lifecycle["holding"] = holding
    lifecycle["partial_exit_qty"] = int(closure_state.get("cumulative_exit_qty") or 0)
    lifecycle["remaining_qty"] = int(closure_state.get("remaining_qty") or 0)


def _build_trade_lifecycles(
    *,
    day: str,
    run_snapshots: List[Dict[str, Any]],
    run_bundles: Dict[str, Dict[str, Any]],
    existing_open_lifecycles_by_symbol: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    symbol_seq: Dict[str, int] = {}
    active_by_symbol: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []
    existing_candidates = (
        existing_open_lifecycles_by_symbol
        if isinstance(existing_open_lifecycles_by_symbol, dict)
        else {}
    )
    consumed_existing_open_trade_ids: set[str] = set()

    def _next_trade_id(symbol: str) -> str:
        key = normalize_symbol(symbol, allow_test_symbols=True) or "UNKNOWN"
        symbol_seq[key] = int(symbol_seq.get(key, 0) + 1)
        return _build_trade_id(day, key, symbol_seq[key])

    def _bundle_story_type(bundle: Dict[str, Any]) -> str:
        story_contract = bundle.get("story_contract") if isinstance(bundle.get("story_contract"), dict) else {}
        return str(story_contract.get("story_type") or "").strip().lower()

    def _bundle_mode_label(bundle: Dict[str, Any]) -> str:
        story_contract = bundle.get("story_contract") if isinstance(bundle.get("story_contract"), dict) else {}
        return str(story_contract.get("execution_mode_label") or "").strip()

    def _infer_story_contract_from_snapshot(snapshot: Dict[str, Any]) -> Tuple[str, str]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        action = str(snapshot.get("execution_action") or execution.get("action") or "").strip().upper()
        verdict_allowed = bool(snapshot.get("verdict_allowed"))
        executor_stub = {
            "execution_attempted": bool(action),
            "execution_ok": bool(action) and verdict_allowed,
        }
        story_type = _classify_story_type(
            {
                "action": action,
                "symbol": str(snapshot.get("symbol") or execution.get("symbol") or ""),
                "qty": safe_int(execution.get("qty"), 0),
            },
            executor_stub,
        )
        mode_label = execution_mode_label(executor_stub)
        return story_type, mode_label

    def _resolve_story_contract(bundle: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[str, str]:
        bundle_story_type = _bundle_story_type(bundle)
        bundle_mode_label = _bundle_mode_label(bundle)
        if bundle_story_type:
            return bundle_story_type, bundle_mode_label or "decision only"
        inferred_story_type, inferred_mode_label = _infer_story_contract_from_snapshot(snapshot)
        return inferred_story_type or "decision_only", inferred_mode_label or "decision only"

    def _entry_context(snapshot: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        execution_details = (
            dict(bundle.get("execution_details") or {})
            if isinstance(bundle.get("execution_details"), dict)
            else dict(execution)
        )
        strategist_payload = bundle.get("strategist") if isinstance(bundle.get("strategist"), dict) else {}
        strategist_summary_payload = bundle.get("strategist_summary") if isinstance(bundle.get("strategist_summary"), dict) else {}
        strategist_policy = (
            strategist_payload.get("policy_selected")
            if isinstance(strategist_payload.get("policy_selected"), dict)
            else strategist_summary_payload.get("policy_selected")
            if isinstance(strategist_summary_payload.get("policy_selected"), dict)
            else {}
        )
        scanner_payload = bundle.get("scanner") if isinstance(bundle.get("scanner"), dict) else {}
        scanner_source_refs = scanner_payload.get("source_refs") if isinstance(scanner_payload.get("source_refs"), dict) else {}
        scanner_reason_human = bundle.get("scanner_reason_human") if isinstance(bundle.get("scanner_reason_human"), dict) else {}
        monitor_reason_human = bundle.get("monitor_reason_human") if isinstance(bundle.get("monitor_reason_human"), dict) else {}
        scanner_context = dict(scanner_reason_human)
        if not scanner_context and scanner_payload:
            scanner_context = {
                "selected_symbol": str(scanner_payload.get("selected_symbol") or scanner_payload.get("top_stock") or ""),
                "selected_rank": safe_int(scanner_payload.get("selected_rank"), 0),
                "selected_score": scanner_payload.get("top_score"),
                "summary": str(
                    scanner_payload.get("selection_reason")
                    or (scanner_payload.get("selected_candidate") or {}).get("why")
                    or ""
                ),
            }
        monitor_context = dict(monitor_reason_human)
        if not monitor_context and isinstance(bundle.get("monitor"), dict):
            monitor_payload = dict(bundle.get("monitor") or {})
            monitor_context = {
                "summary": str(monitor_payload.get("monitor_reason") or monitor_payload.get("entry_reason") or ""),
                "active_exit_axis": str(monitor_payload.get("active_exit_axis") or ""),
            }
        entry_price = execution.get("price")
        if entry_price is None or entry_price == "":
            entry_price = execution.get("order_price") or execution.get("avg_price")
        entry_reason = str(
            scanner_context.get("summary")
            or monitor_context.get("summary")
            or snapshot.get("monitor_reason")
            or ""
        ).strip()
        if _is_placeholder_entry_reason(entry_reason):
            entry_reason = str(
                (bundle.get("execution_outcome_human") or {}).get("summary")
                or scanner_context.get("summary")
                or monitor_context.get("summary")
                or snapshot.get("execution_reason")
                or snapshot.get("decision_reason")
                or snapshot.get("monitor_reason")
                or "Entry reasoning was not captured."
            ).strip()
        playbook = str(
            strategist_payload.get("playbook")
            or strategist_summary_payload.get("playbook")
            or strategist_policy.get("playbook")
            or scanner_source_refs.get("strategist_playbook")
            or ""
        )
        themes_raw = (
            strategist_payload.get("themes")
            or strategist_summary_payload.get("themes")
            or strategist_policy.get("themes")
            or []
        )
        themes = [str(item or "").strip() for item in list(themes_raw or []) if str(item or "").strip()]
        return {
            "run_id": str(snapshot.get("run_id") or ""),
            "ts": str(snapshot.get("ts_start") or ""),
            "action": str(execution.get("action") or "BUY"),
            "price": entry_price,
            "qty": safe_int(execution.get("qty"), 0),
            "reason_human": entry_reason,
            "strategist_context": {
                "playbook": playbook,
                "themes": themes[:6],
                "market_context_summary": str((bundle.get("market_context_human") or {}).get("summary") or ""),
            },
            "scanner_context": scanner_context,
            "monitor_context": monitor_context,
            "guard_context": dict(bundle.get("guard_reason_human") or {}),
            "execution_context": dict(bundle.get("execution_outcome_human") or {}),
            "execution_details": execution_details,
        }

    def _exit_context(snapshot: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        execution_details = (
            dict(bundle.get("execution_details") or {})
            if isinstance(bundle.get("execution_details"), dict)
            else dict(execution)
        )
        filled_qty = (
            execution_details.get("filled_qty")
            if execution_details.get("filled_qty") not in (None, "")
            else execution.get("filled_qty")
        )
        has_exit_monitor_trace = bool(
            str(snapshot.get("exit_reason") or "").strip()
            or str(snapshot.get("monitor_reason") or "").strip()
        )
        monitor_context = dict(bundle.get("monitor_reason_human") or {}) if has_exit_monitor_trace else {}
        return {
            "run_id": str(snapshot.get("run_id") or ""),
            "ts": str(snapshot.get("ts_start") or ""),
            "action": str(execution.get("action") or "SELL"),
            "price": execution.get("price"),
            "qty": safe_int(execution.get("qty"), 0),
            "filled_qty": safe_int(filled_qty, 0) if filled_qty not in (None, "") else None,
            "reason_human": str(
                (monitor_context or {}).get("summary")
                or (bundle.get("execution_outcome_human") or {}).get("summary")
                or snapshot.get("exit_reason")
                or snapshot.get("monitor_reason")
                or "Exit reasoning was not captured."
            ),
            "monitor_context": monitor_context,
            "guard_context": dict(bundle.get("guard_reason_human") or {}),
            "execution_context": dict(bundle.get("execution_outcome_human") or {}),
            "execution_details": execution_details,
        }

    for snapshot in sorted(run_snapshots, key=lambda row: int(row.get("ts_epoch") or 0)):
        run_id = str(snapshot.get("run_id") or "").strip()
        symbol = normalize_symbol(snapshot.get("symbol") or "", allow_test_symbols=True)
        if not run_id or not symbol:
            continue
        bundle = run_bundles.get(run_id) if isinstance(run_bundles.get(run_id), dict) else {}
        action = str(snapshot.get("execution_action") or "").upper()
        if action == "BUY":
            if symbol in active_by_symbol and isinstance(active_by_symbol.get(symbol), dict):
                prev = active_by_symbol[symbol]
                if str(prev.get("status") or "") == "open":
                    prev["status"] = "partial"
                    prev.setdefault("warnings", []).append(
                        "A new BUY was detected while a previous lifecycle for the same symbol was still open."
                    )
                    prev.setdefault("timeline", []).append(
                        {
                            "event": "entry_overlap",
                            "ts": str(snapshot.get("ts_start") or ""),
                            "description": f"New BUY run {run_id} overlapped existing open lifecycle.",
                        }
                    )
            trade_id = _next_trade_id(symbol)
            story_type, mode_label = _resolve_story_contract(bundle, snapshot)
            lifecycle = _build_lifecycle_from_seed(
                trade_id=trade_id,
                symbol=symbol,
                day=day,
                execution_mode_label_text=mode_label,
                story_type=story_type,
            )
            lifecycle["entry"] = _entry_context(snapshot, bundle)
            lifecycle["run_ids_all"] = [run_id]
            lifecycle["timeline"].append(
                {
                    "event": "entry",
                    "ts": str(snapshot.get("ts_start") or ""),
                    "description": f"Entry BUY was executed by run {run_id}.",
                }
            )
            active_by_symbol[symbol] = lifecycle
            out.append(lifecycle)
            continue

        if action == "SELL":
            attach_debug: Dict[str, Any] = {
                **_snapshot_execution_debug(snapshot),
                "matched_open_trade_id": "",
                "candidate_open_trade_ids": [],
                "attach_match_reason": "",
                "new_trade_created_reason": "",
                "recovered_lifecycle_reason": "",
            }
            lifecycle = active_by_symbol.get(symbol)
            if lifecycle:
                attach_debug["candidate_open_trade_ids"] = [str(lifecycle.get("trade_id") or "")]
            if not lifecycle:
                sell_ts_epoch = float(snapshot.get("ts_epoch") or 0.0)
                symbol_candidates = [
                    dict(row)
                    for row in list(existing_candidates.get(symbol) or [])
                    if isinstance(row, dict)
                ]
                attach_debug["candidate_open_trade_ids"] = [
                    str(row.get("trade_id") or "")
                    for row in symbol_candidates
                    if str(row.get("trade_id") or "").strip()
                ]
                matched_candidate: Dict[str, Any] = {}
                for candidate in symbol_candidates:
                    candidate_trade_id = str(candidate.get("trade_id") or "").strip()
                    if candidate_trade_id and candidate_trade_id in consumed_existing_open_trade_ids:
                        continue
                    entry_ts_epoch = float(candidate.get("entry_ts_epoch") or 0.0)
                    if sell_ts_epoch > 0.0 and entry_ts_epoch > 0.0 and entry_ts_epoch > sell_ts_epoch:
                        continue
                    matched_candidate = candidate
                    break
                if matched_candidate:
                    lifecycle = _build_lifecycle_from_seed(
                        trade_id=str(matched_candidate.get("trade_id") or _next_trade_id(symbol)),
                        symbol=symbol,
                        day=day,
                        execution_mode_label_text=str(matched_candidate.get("execution_mode_label") or "simulation (mock broker)"),
                        story_type=str(matched_candidate.get("story_type") or "simulation"),
                    )
                    lifecycle["entry"] = dict(matched_candidate.get("entry") or {})
                    lifecycle["holding"] = dict(matched_candidate.get("holding") or lifecycle.get("holding") or {})
                    lifecycle["run_ids_all"] = [
                        str(x or "").strip()
                        for x in list(matched_candidate.get("run_ids_all") or [])
                        if str(x or "").strip()
                    ]
                    lifecycle["timeline"] = [dict(row) for row in list(matched_candidate.get("timeline") or []) if isinstance(row, dict)]
                    lifecycle["warnings"] = [
                        str(x or "")
                        for x in list(matched_candidate.get("warnings") or [])
                        if str(x or "").strip()
                    ]
                    lifecycle["status"] = "open"
                    attach_debug["matched_open_trade_id"] = str(lifecycle.get("trade_id") or "")
                    attach_debug["attach_match_reason"] = "matched_existing_open_lifecycle_by_symbol_and_time"
                    attach_debug["recovered_lifecycle_reason"] = "reused_existing_open_lifecycle_artifact"
                    if str(lifecycle.get("trade_id") or "").strip():
                        consumed_existing_open_trade_ids.add(str(lifecycle.get("trade_id") or "").strip())
                    out.append(lifecycle)
                    active_by_symbol[symbol] = lifecycle
                else:
                    trade_id = _next_trade_id(symbol)
                    story_type, mode_label = _resolve_story_contract(bundle, snapshot)
                    lifecycle = _build_lifecycle_from_seed(
                        trade_id=trade_id,
                        symbol=symbol,
                        day=day,
                        execution_mode_label_text=mode_label,
                        story_type=story_type,
                    )
                    lifecycle["status"] = "partial"
                    attach_debug["new_trade_created_reason"] = "no_active_or_existing_open_lifecycle"
                    attach_debug["recovered_lifecycle_reason"] = "sell_without_attachable_open_entry"
                    out.append(lifecycle)
            exit_ctx = _exit_context(snapshot, bundle)
            lifecycle.setdefault("run_ids_all", [])
            if run_id not in lifecycle["run_ids_all"]:
                lifecycle["run_ids_all"].append(run_id)
            if lifecycle.get("entry"):
                closure_state = _exit_closure_quantity_state(lifecycle, exit_ctx)
                attach_debug["entry_qty"] = int(closure_state.get("entry_qty") or 0)
                attach_debug["exit_qty"] = int(closure_state.get("exit_qty") or 0)
                attach_debug["previous_partial_exit_qty"] = int(closure_state.get("previous_partial_exit_qty") or 0)
                attach_debug["cumulative_exit_qty"] = int(closure_state.get("cumulative_exit_qty") or 0)
                attach_debug["remaining_qty"] = int(closure_state.get("remaining_qty") or 0)
                attach_debug["closes_position"] = bool(closure_state.get("closes_position"))
                if bool(closure_state.get("closes_position")):
                    lifecycle["exit"] = exit_ctx
                    lifecycle["status"] = "closed"
                    lifecycle["remaining_qty"] = 0
                    lifecycle["timeline"].append(
                        {
                            "event": "exit",
                            "ts": str(snapshot.get("ts_start") or ""),
                            "description": f"Exit SELL was executed by run {run_id}.",
                        }
                    )
                    active_by_symbol.pop(symbol, None)
                else:
                    lifecycle["status"] = "open"
                    _record_partial_exit(
                        lifecycle,
                        exit_ctx=exit_ctx,
                        run_id=run_id,
                        ts=str(snapshot.get("ts_start") or ""),
                        closure_state=closure_state,
                    )
                    lifecycle["timeline"].append(
                        {
                            "event": "partial_exit",
                            "ts": str(snapshot.get("ts_start") or ""),
                            "description": (
                                f"Partial SELL was executed by run {run_id}; "
                                f"remaining qty {int(closure_state.get('remaining_qty') or 0)}."
                            ),
                        }
                    )
                    if not attach_debug.get("attach_match_reason"):
                        attach_debug["matched_open_trade_id"] = str(lifecycle.get("trade_id") or "")
                        attach_debug["attach_match_reason"] = "partial_sell_kept_lifecycle_open"
                    lifecycle.setdefault("lifecycle_attach_debug", [])
                    if isinstance(lifecycle.get("lifecycle_attach_debug"), list):
                        lifecycle["lifecycle_attach_debug"].append(attach_debug)
                    active_by_symbol[symbol] = lifecycle
                    continue
                if not attach_debug.get("attach_match_reason"):
                    attach_debug["matched_open_trade_id"] = str(lifecycle.get("trade_id") or "")
                    attach_debug["attach_match_reason"] = "matched_active_open_lifecycle_in_current_pass"
                resolved_story_type, resolved_mode_label = _resolve_story_contract(bundle, snapshot)
                if resolved_story_type and resolved_story_type != "decision_only":
                    lifecycle["story_type"] = resolved_story_type
                elif str(lifecycle.get("story_type") or "").strip().lower() == "decision_only":
                    inferred_story_type, inferred_mode_label = _infer_story_contract_from_snapshot(snapshot)
                    if inferred_story_type and inferred_story_type != "decision_only":
                        lifecycle["story_type"] = inferred_story_type
                        if inferred_mode_label:
                            lifecycle["execution_mode_label"] = inferred_mode_label
                if resolved_mode_label and resolved_mode_label != "decision only":
                    lifecycle["execution_mode_label"] = resolved_mode_label
            else:
                lifecycle["exit"] = exit_ctx
                lifecycle["timeline"].append(
                    {
                        "event": "exit",
                        "ts": str(snapshot.get("ts_start") or ""),
                        "description": f"Exit SELL was executed by run {run_id}.",
                    }
                )
                lifecycle["status"] = "partial"
                if not attach_debug.get("new_trade_created_reason"):
                    attach_debug["new_trade_created_reason"] = "entry_missing_after_sell_attach"
                if not attach_debug.get("recovered_lifecycle_reason"):
                    attach_debug["recovered_lifecycle_reason"] = "sell_processed_without_substantive_entry"
            lifecycle.setdefault("lifecycle_attach_debug", [])
            if isinstance(lifecycle.get("lifecycle_attach_debug"), list):
                lifecycle["lifecycle_attach_debug"].append(attach_debug)
            continue

        lifecycle = active_by_symbol.get(symbol)
        if not lifecycle:
            continue
        lifecycle.setdefault("run_ids_all", [])
        if run_id not in lifecycle["run_ids_all"]:
            lifecycle["run_ids_all"].append(run_id)
        monitor_reason = str(snapshot.get("monitor_reason") or "")
        exit_reason = str(snapshot.get("exit_reason") or "")
        holding_event = {
            "run_id": run_id,
            "ts": str(snapshot.get("ts_start") or ""),
            "posture": str(snapshot.get("posture") or "HOLD"),
            "monitor_reason": monitor_reason,
            "exit_reason": exit_reason,
            "monitor_context": dict(snapshot.get("monitor") or {}),
            "summary": f"Monitor posture={snapshot.get('posture') or 'HOLD'} reason={monitor_reason or '-'} exit={exit_reason or '-'}",
        }
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        holding.setdefault("run_ids", [])
        holding.setdefault("holding_events", [])
        holding.setdefault("posture_history", [])
        holding.setdefault("monitor_updates", [])
        if run_id not in holding["run_ids"]:
            holding["run_ids"].append(run_id)
        holding["holding_events"].append(holding_event)
        holding["posture_history"].append({"ts": str(snapshot.get("ts_start") or ""), "posture": str(snapshot.get("posture") or "HOLD")})
        holding["monitor_updates"].append(monitor_reason or exit_reason or "monitor update captured")
        lifecycle["holding"] = holding
        lifecycle["timeline"].append(
            {
                "event": "holding",
                "ts": str(snapshot.get("ts_start") or ""),
                "description": holding_event["summary"],
            }
        )

    for lifecycle in out:
        entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        entry_has_execution_evidence = _has_substantive_entry_evidence(entry)
        entry_ts = _to_epoch(entry.get("ts")) if entry_has_execution_evidence else None
        end_ts = _to_epoch(exit_ctx.get("ts"))
        duration_sec: Optional[int] = None
        if end_ts is None:
            latest_hold_ts = max((_to_epoch((row or {}).get("ts")) or 0 for row in list(holding.get("holding_events") or [])), default=0)
            end_ts = latest_hold_ts or entry_ts or 0
        if entry_ts is not None:
            duration_sec = int(max(0, (end_ts or 0) - (entry_ts or end_ts or 0)))
        holding_duration = _format_duration_human(duration_sec) if duration_sec is not None else ""
        entry_reason_human = str(entry.get("reason_human") or ENTRY_REASON_NOT_CAPTURED)
        if lifecycle.get("status") == "open":
            exit_reason_human = OPEN_POSITION_WATCHING
        elif lifecycle.get("status") == "partial" and not exit_ctx:
            exit_reason_human = PARTIAL_EXIT_EVIDENCE_MISSING
        else:
            exit_reason_human = str(exit_ctx.get("reason_human") or EXIT_REASON_NOT_CAPTURED)
        holding_duration_clause = (
            f"Holding duration is {holding_duration}. "
            if holding_duration
            else f"{HOLDING_DURATION_UNAVAILABLE} "
        )
        partial_exit_qty = _holding_partial_exit_total(holding)
        remaining_qty = safe_int(lifecycle.get("remaining_qty"), 0)
        partial_exit_clause = (
            f" Partial exits recorded: {partial_exit_qty}; remaining qty: {remaining_qty}."
            if partial_exit_qty > 0 and lifecycle.get("status") == "open"
            else ""
        )
        lifecycle_summary = (
            f"Trade {lifecycle.get('trade_id')} for {lifecycle.get('symbol')} is {lifecycle.get('status')}. "
            f"{holding_duration_clause}"
            f"Entry: {entry_reason_human} "
            f"Exit: {exit_reason_human}"
            f"{partial_exit_clause}"
        )
        operator_conclusion_human = (
            f"Current lifecycle status is {lifecycle.get('status')}. "
            f"{'Position remains open and requires monitoring.' if lifecycle.get('status') == 'open' else 'Entry and exit are connected in one lifecycle story.'}"
            f"{' Entry execution evidence is partially recovered.' if not entry_has_execution_evidence and lifecycle.get('status') != 'open' else ''}"
        )

        reporter_summary = ""
        reporter_grade = "N/A"
        reporter_status = "missing"
        improvement_points: List[str] = []
        entry_run_id = str(entry.get("run_id") or "")
        exit_run_id = str(exit_ctx.get("run_id") or "")
        entry_bundle = run_bundles.get(entry_run_id) if isinstance(run_bundles.get(entry_run_id), dict) else {}
        exit_bundle = run_bundles.get(exit_run_id) if isinstance(run_bundles.get(exit_run_id), dict) else {}
        reporter_human = (
            entry_bundle.get("reporter_status_human")
            if isinstance(entry_bundle.get("reporter_status_human"), dict)
            else exit_bundle.get("reporter_status_human")
            if isinstance(exit_bundle.get("reporter_status_human"), dict)
            else {}
        )
        if isinstance(reporter_human, dict):
            reporter_summary = str(reporter_human.get("summary") or "")
            reporter_grade = str(reporter_human.get("grade") or "N/A")
            reporter_status = str(reporter_human.get("status") or "missing")
        if reporter_status != "linked":
            improvement_points.append("Link same-day reporter analysis to this lifecycle for a complete quality review.")
        if lifecycle.get("status") == "open":
            improvement_points.append("Capture additional monitor runs so hold behavior quality can be evaluated.")
        if not holding.get("run_ids"):
            improvement_points.append("Holding-phase evidence is thin; preserve more monitor context between entry and exit.")
        if not entry_has_execution_evidence and lifecycle.get("status") != "open":
            improvement_points.append("Entry execution evidence is incomplete; preserve BUY linkage for closed-trade diagnosis.")

        lifecycle["summary"] = {
            "holding_duration": holding_duration,
            "entry_reason_human": entry_reason_human,
            "exit_reason_human": exit_reason_human,
            "lifecycle_summary_human": lifecycle_summary,
            "operator_conclusion_human": operator_conclusion_human,
        }
        lifecycle["reporter"] = {
            "status_human": reporter_status,
            "summary": reporter_summary or "Reporter linkage is pending or missing for this lifecycle.",
            "grade": reporter_grade,
            "improvement_points": improvement_points[:6],
        }
        if str(lifecycle.get("story_type") or "") == "failed_execution":
            lifecycle["status"] = "failed"
        lifecycle.setdefault("warnings", [])
        if lifecycle.get("status") == "partial":
            lifecycle["warnings"].append("Lifecycle is partial because entry or exit evidence is incomplete.")
        if lifecycle.get("status") == "open":
            lifecycle["warnings"].append("Lifecycle is open; no closing SELL execution has been recorded yet.")
        if partial_exit_qty > 0 and lifecycle.get("status") == "open":
            lifecycle["warnings"].append("Partial SELL was recorded, but the full position is not closed; final trade report is pending.")
        if not entry_has_execution_evidence and lifecycle.get("status") != "open":
            lifecycle["warnings"].append("Entry execution evidence is incomplete; lifecycle entry was partially recovered.")

    return out



def has_substantive_entry_evidence(entry: Dict[str, Any]) -> bool:
    return _has_substantive_entry_evidence(entry)

def load_existing_open_lifecycle_candidates(*, reports_root: Path, day: str) -> Dict[str, List[Dict[str, Any]]]:
    return _load_existing_open_lifecycle_candidates(reports_root=reports_root, day=day)

def build_trade_lifecycles(*, day: str, run_snapshots: List[Dict[str, Any]], run_bundles: Dict[str, Dict[str, Any]], existing_open_lifecycles_by_symbol: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
    return _build_trade_lifecycles(
        day=day,
        run_snapshots=run_snapshots,
        run_bundles=run_bundles,
        existing_open_lifecycles_by_symbol=existing_open_lifecycles_by_symbol,
    )

__all__ = [
    "build_trade_lifecycles",
    "has_substantive_entry_evidence",
    "load_existing_open_lifecycle_candidates",
]
