from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.core.symbols import normalize_symbol
from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.reporter_analysis import generate_reporter_analysis_report
from libs.reporting.trade_explain import generate_trade_explain_report
from libs.reporting.trade_report_ai import build_ai_trade_report, render_trade_report_markdown
from libs.reporting.trade_story_pipeline import (
    build_execution_outcome_human,
    build_filters_human,
    build_guard_reason_human,
    build_market_context_human,
    build_monitor_reason_human,
    build_operator_conclusion_human,
    build_reporter_status_human,
    build_scanner_reason_human,
    build_story_contract,
    build_story_id,
    build_timeline,
    build_trade_story_input,
    classify_story_type as _classify_story_type,
    collect_story_warnings,
    execution_mode_label,
    render_bundle_markdown,
    render_summary_markdown,
    safe_int,
    utc_now_iso,
)


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_model_name(model: Any) -> str:
    raw = str(model or "").strip()
    lowered = raw.lower()
    if lowered == "free":
        return "openrouter/free"
    if lowered == "auto":
        return "openrouter/auto"
    return raw


def _sanitize_error_message(value: Any, *, max_len: int = 260) -> str:
    text = str(value or "").strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _report_reason_human(code: str) -> str:
    mapping = {
        "no_executed_lifecycle": "No executed trade lifecycle was created for this run.",
        "decision_only_run": "This run was decision-only, so a full AI trade report was not generated.",
        "hold_only_run": "This run only updated hold/monitor state, so a full AI trade report was not generated.",
        "execution_failed": "Execution did not complete successfully, so a full AI trade report was skipped.",
        "missing_story_input": "Trade story input was not created, so report generation could not continue.",
        "llm_generation_failed": "Trade story input existed, but AI report generation failed.",
        "artifact_write_failed": "AI report generation ran, but writing report artifacts failed.",
        "missing_report_linkage": "A linked AI trade report could not be found for this run.",
        "report_not_requested": "AI trade report generation was not requested for this run.",
        "still_open_lifecycle": "This trade lifecycle is still open, so the full AI report is pending.",
        "awaiting_exit_for_full_report": "This trade is still open. The full AI report is generated after exit/closure.",
    }
    return mapping.get(str(code or "").strip().lower(), "AI report diagnostics are not fully classified.")


def _report_next_step(code: str) -> str:
    mapping = {
        "no_executed_lifecycle": "Continue with Operator Brief. Generate full AI report only for executed lifecycles.",
        "decision_only_run": "Continue with Operator Brief. Generate full AI report after executed lifecycle events.",
        "hold_only_run": "Continue monitoring. Generate full AI report after entry/exit execution is formed.",
        "execution_failed": "Review execution failure details and rerun report generation after stabilization.",
        "missing_story_input": "Fix trade story input generation first, then retry.",
        "llm_generation_failed": "Check OpenRouter/model connectivity and retry report generation.",
        "artifact_write_failed": "Check filesystem write path and permissions, then retry.",
        "missing_report_linkage": "Regenerate lifecycle/report linkage for this run and retry.",
        "report_not_requested": "Enable AI report generation policy and rerun.",
        "still_open_lifecycle": "Generate the full AI report after lifecycle exit/closure.",
        "awaiting_exit_for_full_report": "Generate the final AI report after exit/closure.",
    }
    return mapping.get(str(code or "").strip().lower(), "Review diagnostics and continue with Operator Brief.")


def _base_diagnostics(model_hint: str) -> Dict[str, Any]:
    return {
        "report_status": "pending",
        "report_reason_code": "",
        "report_reason_human": "",
        "generation_attempted": False,
        "generation_ts": "",
        "story_input_available": False,
        "report_output_available": False,
        "report_artifact_available": False,
        "llm_provider": "OpenRouter",
        "llm_model_used": _normalize_model_name(model_hint) or "openrouter/free",
        "expected_generation_mode": "per-trade free model report",
        "last_error_message": "",
        "next_expected_step": "",
    }


def _seed_diagnostics_for_policy(
    *,
    lifecycle_status: str,
    story_type: str,
    report_requested: bool,
    story_input_available: bool,
    model_hint: str,
) -> Tuple[Dict[str, Any], bool]:
    diagnostics = _base_diagnostics(model_hint)
    diagnostics["story_input_available"] = bool(story_input_available)
    status = str(lifecycle_status or "").strip().lower()
    story = str(story_type or "").strip().lower()

    if not story_input_available:
        diagnostics["report_status"] = "failed"
        diagnostics["report_reason_code"] = "missing_story_input"
        diagnostics["report_reason_human"] = _report_reason_human("missing_story_input")
        diagnostics["next_expected_step"] = _report_next_step("missing_story_input")
        return diagnostics, False

    if not report_requested:
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "report_not_requested"
        diagnostics["report_reason_human"] = _report_reason_human("report_not_requested")
        diagnostics["next_expected_step"] = _report_next_step("report_not_requested")
        return diagnostics, False

    if story == "decision_only":
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "decision_only_run"
        diagnostics["report_reason_human"] = _report_reason_human("decision_only_run")
        diagnostics["next_expected_step"] = _report_next_step("decision_only_run")
        return diagnostics, False

    if story == "failed_execution":
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "execution_failed"
        diagnostics["report_reason_human"] = _report_reason_human("execution_failed")
        diagnostics["next_expected_step"] = _report_next_step("execution_failed")
        return diagnostics, False

    if status == "open":
        diagnostics["report_status"] = "pending"
        diagnostics["report_reason_code"] = "awaiting_exit_for_full_report"
        diagnostics["report_reason_human"] = _report_reason_human("awaiting_exit_for_full_report")
        diagnostics["next_expected_step"] = _report_next_step("awaiting_exit_for_full_report")
        return diagnostics, False

    return diagnostics, True


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


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


def _utc_day(ts: Any) -> str:
    epoch = _to_epoch(ts)
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _normalize_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"action": "", "symbol": "", "qty": 0, "status": "", "ord_no": ""}
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    broker = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    response_payload = broker.get("response_payload") if isinstance(broker.get("response_payload"), dict) else {}
    return {
        "action": str(payload.get("action") or order.get("action") or "").upper(),
        "symbol": normalize_symbol(
            payload.get("symbol") or order.get("symbol") or order.get("stk_cd") or "",
            allow_test_symbols=True,
        ),
        "qty": safe_int(payload.get("qty"), safe_int(order.get("qty"), safe_int(order.get("ord_qty"), 0))),
        "status": str(
            payload.get("fill_status_summary")
            or payload.get("status")
            or broker.get("broker_message")
            or response_payload.get("return_msg")
            or ""
        ),
        "ord_no": str(payload.get("ord_no") or broker.get("order_id") or response_payload.get("ord_no") or ""),
    }


def _latest_execution_day(event_log_path: Path) -> str:
    best_day = ""
    best_epoch = -1
    for row in _iter_jsonl(event_log_path):
        if str(row.get("stage") or "") != "execute_from_packet" or str(row.get("event") or "") != "execution":
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"}:
            continue
        if not str(execution.get("symbol") or "").strip():
            continue
        epoch = _to_epoch(row.get("ts"))
        if epoch is None or epoch < best_epoch:
            continue
        best_epoch = epoch
        best_day = _utc_day(row.get("ts"))
    return best_day


def _resolve_execution_runs(event_log_path: Path, day: str) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    rows = sorted(_iter_jsonl(event_log_path), key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    for row in rows:
        if str(row.get("stage") or "") != "execute_from_packet" or str(row.get("event") or "") != "execution":
            continue
        if day and _utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id or run_id in seen:
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"} or not str(execution.get("symbol") or "").strip():
            continue
        seen.add(run_id)
        out.append(
            {
                "run_id": run_id,
                "ts": str(row.get("ts") or ""),
                "action": str(execution.get("action") or "").upper(),
                "symbol": str(execution.get("symbol") or ""),
                "qty": safe_int(execution.get("qty"), 0),
                "status": str(execution.get("status") or ""),
                "ord_no": str(execution.get("ord_no") or ""),
            }
        )
    out.sort(key=lambda row: _to_epoch(row.get("ts")) or 0)
    return out


def _build_run_snapshots(event_log_path: Path, day: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in _iter_jsonl(event_log_path):
        if day and _utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        grouped.setdefault(run_id, []).append(row)

    out: List[Dict[str, Any]] = []
    for run_id, rows in grouped.items():
        rows = sorted(rows, key=lambda row: _to_epoch(row.get("ts")) or 0)
        route_row = next(
            (
                row
                for row in rows
                if str(row.get("stage") or "") == "commander_router"
                and str(row.get("event") or "") == "route"
            ),
            {},
        )
        scanner_summary = next(
            (
                row.get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "scanner"
                and str(row.get("event") or "") == "summary"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        monitor_summary = next(
            (
                row.get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "monitor"
                and str(row.get("event") or "") == "summary"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        verdict_payload = next(
            (
                row.get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "execute_from_packet"
                and str(row.get("event") or "") == "verdict"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        execution_row = next(
            (
                row
                for row in reversed(rows)
                if str(row.get("stage") or "") == "execute_from_packet"
                and str(row.get("event") or "") == "execution"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        execution = _normalize_execution_payload(execution_row.get("payload") if isinstance(execution_row.get("payload"), dict) else {})
        candidate_selection = next(
            (
                (row.get("payload") or {}).get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "decision_trace"
                and str(row.get("event") or "") == "candidate_selection"
                and isinstance(row.get("payload"), dict)
                and str((row.get("payload") or {}).get("agent") or "") == "scanner"
            ),
            {},
        )
        selected_symbol = (
            (candidate_selection.get("selected_candidate") or {}).get("symbol")
            if isinstance(candidate_selection.get("selected_candidate"), dict)
            else candidate_selection.get("selected_symbol")
        )
        symbol = normalize_symbol(
            execution.get("symbol")
            or selected_symbol
            or scanner_summary.get("top_stock")
            or monitor_summary.get("symbol")
            or "",
            allow_test_symbols=True,
        )
        execution_action = str(execution.get("action") or "").upper()
        monitor_reason = str(monitor_summary.get("monitor_reason") or "").strip()
        exit_reason = str(monitor_summary.get("exit_reason") or "").strip()
        if execution_action in {"BUY", "SELL"}:
            posture = execution_action
        elif "hold" in monitor_reason.lower() or "hold" in exit_reason.lower():
            posture = "HOLD"
        elif "exit" in exit_reason.lower():
            posture = "EXIT_SIGNAL"
        else:
            posture = "WAIT"
        ts_start = str(route_row.get("ts") or rows[0].get("ts") or "")
        ts_end = str(rows[-1].get("ts") or ts_start)
        out.append(
            {
                "run_id": run_id,
                "ts_start": ts_start,
                "ts_end": ts_end,
                "ts_epoch": _to_epoch(ts_start) or 0,
                "symbol": symbol,
                "execution_action": execution_action,
                "posture": posture,
                "execution": execution,
                "monitor_reason": monitor_reason,
                "exit_reason": exit_reason,
                "phase": str((route_row.get("payload") or {}).get("phase") or ""),
                "mode": str((route_row.get("payload") or {}).get("mode") or ""),
                "verdict_allowed": bool(verdict_payload.get("allowed")),
                "verdict_reason": str(verdict_payload.get("reason") or ""),
            }
        )
    out.sort(key=lambda row: int(row.get("ts_epoch") or 0))
    return out


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


def _build_trade_lifecycles(
    *,
    day: str,
    run_snapshots: List[Dict[str, Any]],
    run_bundles: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    symbol_seq: Dict[str, int] = {}
    active_by_symbol: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []

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

    def _entry_context(snapshot: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        return {
            "run_id": str(snapshot.get("run_id") or ""),
            "ts": str(snapshot.get("ts_start") or ""),
            "action": str(execution.get("action") or "BUY"),
            "price": execution.get("price"),
            "qty": safe_int(execution.get("qty"), 0),
            "reason_human": str(
                (bundle.get("scanner_reason_human") or {}).get("summary")
                or (bundle.get("monitor_reason_human") or {}).get("summary")
                or snapshot.get("monitor_reason")
                or "Entry reasoning was not captured."
            ),
            "strategist_context": {
                "playbook": str((bundle.get("strategist") or {}).get("playbook") or ""),
                "themes": list((bundle.get("strategist") or {}).get("themes") or [])[:6],
                "market_context_summary": str((bundle.get("market_context_human") or {}).get("summary") or ""),
            },
            "scanner_context": dict(bundle.get("scanner_reason_human") or {}),
            "monitor_context": dict(bundle.get("monitor_reason_human") or {}),
            "guard_context": dict(bundle.get("guard_reason_human") or {}),
            "execution_context": dict(bundle.get("execution_outcome_human") or {}),
        }

    def _exit_context(snapshot: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        return {
            "run_id": str(snapshot.get("run_id") or ""),
            "ts": str(snapshot.get("ts_start") or ""),
            "action": str(execution.get("action") or "SELL"),
            "price": execution.get("price"),
            "qty": safe_int(execution.get("qty"), 0),
            "reason_human": str(
                (bundle.get("monitor_reason_human") or {}).get("summary")
                or (bundle.get("execution_outcome_human") or {}).get("summary")
                or snapshot.get("exit_reason")
                or snapshot.get("monitor_reason")
                or "Exit reasoning was not captured."
            ),
            "monitor_context": dict(bundle.get("monitor_reason_human") or {}),
            "guard_context": dict(bundle.get("guard_reason_human") or {}),
            "execution_context": dict(bundle.get("execution_outcome_human") or {}),
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
            story_type = _bundle_story_type(bundle) or "decision_only"
            mode_label = _bundle_mode_label(bundle) or "decision only"
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
            lifecycle = active_by_symbol.get(symbol)
            if not lifecycle:
                trade_id = _next_trade_id(symbol)
                story_type = _bundle_story_type(bundle) or "decision_only"
                mode_label = _bundle_mode_label(bundle) or "decision only"
                lifecycle = _build_lifecycle_from_seed(
                    trade_id=trade_id,
                    symbol=symbol,
                    day=day,
                    execution_mode_label_text=mode_label,
                    story_type=story_type,
                )
                lifecycle["status"] = "partial"
                out.append(lifecycle)
            lifecycle["exit"] = _exit_context(snapshot, bundle)
            lifecycle.setdefault("run_ids_all", [])
            if run_id not in lifecycle["run_ids_all"]:
                lifecycle["run_ids_all"].append(run_id)
            lifecycle["timeline"].append(
                {
                    "event": "exit",
                    "ts": str(snapshot.get("ts_start") or ""),
                    "description": f"Exit SELL was executed by run {run_id}.",
                }
            )
            if lifecycle.get("entry"):
                lifecycle["status"] = "closed"
            else:
                lifecycle["status"] = "partial"
            active_by_symbol.pop(symbol, None)
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
        entry_ts = _to_epoch(entry.get("ts"))
        end_ts = _to_epoch(exit_ctx.get("ts"))
        if end_ts is None:
            latest_hold_ts = max((_to_epoch((row or {}).get("ts")) or 0 for row in list(holding.get("holding_events") or [])), default=0)
            end_ts = latest_hold_ts or entry_ts or 0
        duration_sec = int(max(0, (end_ts or 0) - (entry_ts or end_ts or 0)))
        holding_duration = _format_duration_human(duration_sec)
        entry_reason_human = str(entry.get("reason_human") or "Entry reason was not captured.")
        if lifecycle.get("status") == "open":
            exit_reason_human = "Position is still open; monitor is watching for exit triggers."
        elif lifecycle.get("status") == "partial" and not exit_ctx:
            exit_reason_human = "Lifecycle is partial because exit evidence is missing."
        else:
            exit_reason_human = str(exit_ctx.get("reason_human") or "Exit reason was not captured.")
        lifecycle_summary = (
            f"Trade {lifecycle.get('trade_id')} for {lifecycle.get('symbol')} is {lifecycle.get('status')}. "
            f"Holding duration is {holding_duration}. "
            f"Entry: {entry_reason_human} "
            f"Exit: {exit_reason_human}"
        )
        operator_conclusion_human = (
            f"Current lifecycle status is {lifecycle.get('status')}. "
            f"{'Position remains open and requires monitoring.' if lifecycle.get('status') == 'open' else 'Entry and exit are connected in one lifecycle story.'}"
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

    return out


def _resolve_existing_day_artifact(report_dir: Path, prefix: str, day: str) -> Tuple[Path, Path]:
    return report_dir / f"{prefix}_{day}.md", report_dir / f"{prefix}_{day}.json"


def _load_or_generate_trade_explain(event_log_path: Path, analysis_root: Path, day: str) -> Tuple[Path, Path, Dict[str, Any]]:
    report_dir = analysis_root / "trade_explain"
    md_path, js_path = _resolve_existing_day_artifact(report_dir, "trade_explain", day)
    if js_path.exists() and md_path.exists():
        return md_path, js_path, _read_json(js_path)
    return generate_trade_explain_report(event_log_path, report_dir, day=day)


def _load_or_generate_reporter_analysis(
    event_log_path: Path,
    analysis_root: Path,
    reports_root: Path,
    intents_path: Optional[Path],
    day: str,
) -> Tuple[Path, Path, Dict[str, Any]]:
    report_dir = analysis_root / "reporter_analysis"
    md_path, js_path = _resolve_existing_day_artifact(report_dir, "reporter_analysis", day)
    if js_path.exists() and md_path.exists():
        return md_path, js_path, _read_json(js_path)
    return generate_reporter_analysis_report(
        event_log_path,
        report_dir,
        day=day,
        intents_path=intents_path if intents_path and intents_path.exists() else None,
        reports_root=reports_root,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate run-level aggregated execution bundles and per-trade reports.")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--evidence-log-path", default="data/evidence_ledger/events.jsonl")
    p.add_argument("--report-dir", default="reports/dev/analysis/live_execution_bundles")
    p.add_argument("--reports-root", default="reports")
    p.add_argument("--intents-path", default="data/logs/intents.jsonl")
    p.add_argument("--day", default=None)
    p.add_argument("--max-runs", type=int, default=50)
    ai = p.add_mutually_exclusive_group()
    ai.add_argument("--trade-report-ai", dest="trade_report_ai", action="store_true")
    ai.add_argument("--no-trade-report-ai", dest="trade_report_ai", action="store_false")
    p.set_defaults(trade_report_ai=None)
    p.add_argument("--trade-report-ai-model", default=None)
    p.add_argument("--trade-report-ai-temperature", type=float, default=None)
    p.add_argument("--trade-report-ai-max-tokens", type=int, default=None)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    load_env_file(str(args.env_path).strip() or ".env")
    event_log_path = Path(str(args.event_log_path).strip())
    evidence_log_path = Path(str(args.evidence_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    reports_root = Path(str(args.reports_root).strip())
    intents_path = Path(str(args.intents_path).strip()) if str(args.intents_path or "").strip() else None
    day = str(args.day).strip() if args.day else _latest_execution_day(event_log_path)
    analysis_root = report_dir.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    report_requested = bool(args.trade_report_ai) if args.trade_report_ai is not None else _env_bool("TRADE_REPORT_AI_ENABLED", True)
    configured_report_model = _normalize_model_name(
        str(args.trade_report_ai_model).strip()
        if args.trade_report_ai_model
        else os.getenv("TRADE_REPORT_AI_MODEL", "")
        or os.getenv("OPENROUTER_MODEL_TRADE_REPORT", "")
        or os.getenv("OPENROUTER_DEFAULT_MODEL", "")
        or "openrouter/free"
    )

    if not day:
        out = {
            "schema_version": "live_execution_bundles.v2",
            "ok": False,
            "error": "no_execution_day_detected",
            "event_log_path": str(event_log_path),
            "evidence_log_path": str(evidence_log_path),
            "bundle_count": 0,
            "bundles": [],
        }
        print(json.dumps(out, ensure_ascii=False) if bool(args.json) else "ok=false error=no_execution_day_detected")
        return 3

    execution_runs = _resolve_execution_runs(event_log_path, day)[: max(1, int(args.max_runs))]
    trade_md, trade_js, trade_obj = _load_or_generate_trade_explain(event_log_path, analysis_root, day)
    reporter_md, reporter_js, reporter_obj = _load_or_generate_reporter_analysis(event_log_path, analysis_root, reports_root, intents_path, day)
    operator_summary_json = reports_root / "operator_summary" / f"operator_summary_{day}.json"
    operator_summary_md = reports_root / "operator_summary" / f"operator_summary_{day}.md"
    canonical_trades_root = reports_root / "trades"
    year_part, month_part = (day.split("-") + ["01", "01"])[:2]

    run_bundles_by_run: Dict[str, Dict[str, Any]] = {}
    run_bundle_rows: List[Dict[str, Any]] = []
    run_story_type_counts: Dict[str, int] = {}
    for execution in execution_runs:
        run_id = str(execution.get("run_id") or "").strip()
        trace_md, trace_js, trace_out = generate_agent_pipeline_trace_report(
            event_log_path=event_log_path,
            evidence_log_path=evidence_log_path,
            report_dir=report_dir / "agent_pipeline_trace",
            run_id=run_id,
            day=day,
            reports_root=analysis_root,
        )
        bundle_out: Dict[str, Any] = {
            "schema_version": "live_execution_bundle.v2",
            "artifact_type": "aggregated_execution_bundle",
            "ts": utc_now_iso(),
            "day": day,
            "run_id": run_id,
            "execution": dict(execution),
            "commander": dict(trace_out.get("commander") or {}),
            "strategist": dict(trace_out.get("strategist") or {}),
            "scanner": dict(trace_out.get("scanner") or {}),
            "monitor": dict(trace_out.get("monitor") or {}),
            "supervisor": dict(trace_out.get("supervisor") or {}),
            "executor": dict(trace_out.get("executor") or {}),
            "reporter": {
                **dict(trace_out.get("reporter") or {}),
                "reporter_analysis_summary": str(reporter_obj.get("ai_summary") or ""),
                "reporter_analysis_grade": str(reporter_obj.get("ai_run_grade") or "N/A"),
            },
            "artifacts": {
                "agent_pipeline_trace_json": str(trace_js),
                "agent_pipeline_trace_md": str(trace_md),
                "trade_explain_json": str(trade_js),
                "trade_explain_md": str(trade_md),
                "reporter_analysis_json": str(reporter_js),
                "reporter_analysis_md": str(reporter_md),
                "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
                "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
            },
            "trade_explain_summary": {
                "executions_total": safe_int((trade_obj.get("execution_summary") or {}).get("executions_total"), 0)
                if isinstance(trade_obj.get("execution_summary"), dict)
                else 0
            },
        }

        story_contract = build_story_contract(bundle_out)
        market_context_human = build_market_context_human(bundle_out["strategist"])
        scanner_reason_human = build_scanner_reason_human(bundle_out["scanner"], bundle_out["strategist"])
        filters_human = build_filters_human(bundle_out["scanner"], bundle_out["strategist"], bundle_out["supervisor"])
        monitor_reason_human = build_monitor_reason_human(bundle_out["monitor"], bundle_out["execution"])
        guard_reason_human = build_guard_reason_human(bundle_out["supervisor"])
        execution_outcome_human = build_execution_outcome_human(
            bundle_out["execution"],
            bundle_out["executor"],
            story_type=str(story_contract.get("story_type") or ""),
            mode_label=execution_mode_label(bundle_out["executor"]),
        )
        reporter_status_human = build_reporter_status_human(bundle_out["reporter"], reporter_obj)
        operator_conclusion_human = build_operator_conclusion_human(
            execution=bundle_out["execution"],
            scanner_reason_human=scanner_reason_human,
            filters_human=filters_human,
            monitor_reason_human=monitor_reason_human,
            execution_outcome_human=execution_outcome_human,
            reporter_status_human=reporter_status_human,
        )
        timeline = build_timeline(
            commander=bundle_out["commander"],
            market_context_human=market_context_human,
            scanner_reason_human=scanner_reason_human,
            monitor_reason_human=monitor_reason_human,
            guard_reason_human=guard_reason_human,
            execution_outcome_human=execution_outcome_human,
            reporter_status_human=reporter_status_human,
            execution=bundle_out["execution"],
        )
        warnings = collect_story_warnings(
            story_contract=story_contract,
            market_context_human=market_context_human,
            filters_human=filters_human,
            reporter_status_human=reporter_status_human,
            execution_outcome_human=execution_outcome_human,
        )
        story_contract["warnings"] = warnings

        story_id = build_story_id(day, bundle_out["execution"])
        bundle_out.update(
            {
                "trade_id": "",
                "story_id": story_id,
                "story_contract": story_contract,
                "market_context_human": market_context_human,
                "scanner_reason_human": scanner_reason_human,
                "filters_human": filters_human,
                "monitor_reason_human": monitor_reason_human,
                "guard_reason_human": guard_reason_human,
                "execution_outcome_human": execution_outcome_human,
                "reporter_status_human": reporter_status_human,
                "operator_conclusion_human": operator_conclusion_human,
                "timeline": timeline,
                "warnings": warnings,
            }
        )

        bundle_json = report_dir / f"live_execution_bundle_{run_id}.json"
        bundle_md = report_dir / f"live_execution_bundle_{run_id}.md"
        bundle_out["report_json_path"] = str(bundle_json)
        bundle_out["report_md_path"] = str(bundle_md)
        bundle_json.write_text(json.dumps(bundle_out, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_md.write_text(render_bundle_markdown(bundle_out), encoding="utf-8")
        run_bundles_by_run[run_id] = bundle_out

        story_type = str(story_contract.get("story_type") or "unknown")
        run_story_type_counts[story_type] = int(run_story_type_counts.get(story_type, 0) + 1)
        run_bundle_rows.append(
            {
                "run_id": run_id,
                "trade_id": "",
                "story_id": story_id,
                "story_type": story_type,
                "action": execution.get("action"),
                "symbol": execution.get("symbol"),
                "qty": execution.get("qty"),
                "status": execution.get("status"),
                "report_json_path": str(bundle_json),
                "report_md_path": str(bundle_md),
                "trade_story_input_path": "",
                "trade_report_json_path": "",
                "trade_report_md_path": "",
                "trade_lifecycle_json_path": "",
                "trade_report_summary": "",
                "report_status": "failed",
                "report_reason_code": "missing_report_linkage",
                "report_reason_human": _report_reason_human("missing_report_linkage"),
                "report_next_expected_step": _report_next_step("missing_report_linkage"),
                "report_generation_model": configured_report_model,
                "report_generation_attempted": False,
            }
        )

    run_snapshots = _build_run_snapshots(event_log_path, day)
    trade_lifecycles = _build_trade_lifecycles(
        day=day,
        run_snapshots=run_snapshots,
        run_bundles=run_bundles_by_run,
    )
    lifecycle_rows: List[Dict[str, Any]] = []
    lifecycle_story_type_counts: Dict[str, int] = {}
    run_bundle_lookup = {str(row.get("run_id") or ""): row for row in run_bundle_rows}

    for lifecycle in trade_lifecycles:
        trade_id = str(lifecycle.get("trade_id") or "").strip()
        if not trade_id:
            continue
        symbol = normalize_symbol(lifecycle.get("symbol") or "", allow_test_symbols=True)
        status = str(lifecycle.get("status") or "open").strip().lower()
        story_type = str(lifecycle.get("story_type") or "decision_only").strip().lower()
        execution_mode_label_text = str(lifecycle.get("execution_mode_label") or "decision only").strip()

        entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        entry_run_id = str(entry_ctx.get("run_id") or "")
        exit_run_id = str(exit_ctx.get("run_id") or "")
        linked_run_ids = [str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        hold_run_ids = [str(x or "").strip() for x in list(holding.get("run_ids") or []) if str(x or "").strip()]

        anchor_run_id = entry_run_id or exit_run_id or (linked_run_ids[0] if linked_run_ids else "")
        anchor_bundle = run_bundles_by_run.get(anchor_run_id) if isinstance(run_bundles_by_run.get(anchor_run_id), dict) else {}
        anchor_execution = anchor_bundle.get("execution") if isinstance(anchor_bundle.get("execution"), dict) else {}
        if not anchor_execution:
            anchor_execution = {
                "run_id": anchor_run_id,
                "action": str(entry_ctx.get("action") or exit_ctx.get("action") or ("BUY" if status == "open" else "WAIT")),
                "symbol": symbol,
                "qty": safe_int(entry_ctx.get("qty"), safe_int(exit_ctx.get("qty"), 0)),
                "status": str((exit_ctx.get("execution_context") or {}).get("outcome") or ""),
                "ord_no": "",
                "ts": str(entry_ctx.get("ts") or exit_ctx.get("ts") or ""),
            }

        summary_obj = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
        reporter_obj = lifecycle.get("reporter") if isinstance(lifecycle.get("reporter"), dict) else {}
        story_contract = {
            "story_available": True,
            "story_type": story_type,
            "execution_mode_label": execution_mode_label_text,
            "story_anchor": f"{anchor_execution.get('action') or 'WAIT'} {symbol or '-'} x{safe_int(anchor_execution.get('qty'), 0)} | trade {trade_id}",
            "warnings": list(lifecycle.get("warnings") or []),
        }
        lifecycle_bundle: Dict[str, Any] = {
            "schema_version": "live_execution_bundle.v3",
            "artifact_type": "aggregated_execution_bundle",
            "ts": utc_now_iso(),
            "day": day,
            "run_id": anchor_run_id,
            "trade_id": trade_id,
            "story_id": trade_id,
            "linked_run_ids": linked_run_ids,
            "trade_lifecycle_status": status,
            "trade_lifecycle_summary": str(summary_obj.get("lifecycle_summary_human") or ""),
            "story_contract": story_contract,
            "execution": dict(anchor_execution),
            "commander": dict(anchor_bundle.get("commander") or {}),
            "strategist": dict(anchor_bundle.get("strategist") or {}),
            "scanner": dict(anchor_bundle.get("scanner") or {}),
            "monitor": dict(anchor_bundle.get("monitor") or {}),
            "supervisor": dict(anchor_bundle.get("supervisor") or {}),
            "executor": dict(anchor_bundle.get("executor") or {}),
            "reporter": dict(anchor_bundle.get("reporter") or {}),
            "market_context_human": dict(anchor_bundle.get("market_context_human") or entry_ctx.get("strategist_context") or {}),
            "scanner_reason_human": dict(anchor_bundle.get("scanner_reason_human") or entry_ctx.get("scanner_context") or {}),
            "filters_human": dict(anchor_bundle.get("filters_human") or {}),
            "monitor_reason_human": dict(anchor_bundle.get("monitor_reason_human") or exit_ctx.get("monitor_context") or {}),
            "guard_reason_human": dict(anchor_bundle.get("guard_reason_human") or exit_ctx.get("guard_context") or {}),
            "execution_outcome_human": dict(anchor_bundle.get("execution_outcome_human") or exit_ctx.get("execution_context") or {}),
            "reporter_status_human": {
                "status": str(reporter_obj.get("status_human") or "missing"),
                "summary": str(reporter_obj.get("summary") or ""),
                "grade": str(reporter_obj.get("grade") or "N/A"),
                "bullets": [str(x or "") for x in list(reporter_obj.get("improvement_points") or [])[:6]],
            },
            "operator_conclusion_human": {
                "current_action": str(anchor_execution.get("action") or ("HOLD" if status == "open" else "WAIT")),
                "summary": str(summary_obj.get("operator_conclusion_human") or ""),
                "watch_next": [f"Lifecycle status: {status}", "Monitor trigger changes", "Macro/news shifts"],
                "thesis_invalidation": ["stop-loss breach", "monitor and scanner divergence", "negative macro regime shift"],
            },
            "timeline": list(lifecycle.get("timeline") or []),
            "warnings": list(story_contract.get("warnings") or []),
            "trade_lifecycle": lifecycle,
            "artifacts": {
                "agent_pipeline_trace_json": str(anchor_bundle.get("artifacts", {}).get("agent_pipeline_trace_json") or ""),
                "agent_pipeline_trace_md": str(anchor_bundle.get("artifacts", {}).get("agent_pipeline_trace_md") or ""),
                "trade_explain_json": str(trade_js),
                "trade_explain_md": str(trade_md),
                "reporter_analysis_json": str(reporter_js),
                "reporter_analysis_md": str(reporter_md),
                "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
                "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
            },
            "trade_explain_summary": {
                "executions_total": safe_int((trade_obj.get("execution_summary") or {}).get("executions_total"), 0)
                if isinstance(trade_obj.get("execution_summary"), dict)
                else 0
            },
        }

        canonical_dir = canonical_trades_root / year_part / month_part / trade_id
        canonical_dir.mkdir(parents=True, exist_ok=True)
        trade_lifecycle_path = canonical_dir / "trade_lifecycle.json"
        aggregated_bundle_path = canonical_dir / "aggregated_execution_bundle.json"
        story_input_path = canonical_dir / "trade_story_input.json"
        trade_report_json_path = canonical_dir / "trade_report.json"
        trade_report_md_path = canonical_dir / "trade_report.md"

        trade_story_input = build_trade_story_input(lifecycle_bundle, trade_lifecycle=lifecycle)
        diagnostics, should_attempt_generation = _seed_diagnostics_for_policy(
            lifecycle_status=status,
            story_type=story_type,
            report_requested=report_requested,
            story_input_available=bool(trade_story_input),
            model_hint=configured_report_model,
        )

        trade_report: Dict[str, Any] = {}
        if should_attempt_generation:
            diagnostics["generation_attempted"] = True
            diagnostics["generation_ts"] = utc_now_iso()
            trade_report = build_ai_trade_report(
                trade_story_input,
                enabled=True,
                model=str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else configured_report_model,
                temperature=args.trade_report_ai_temperature,
                max_tokens=args.trade_report_ai_max_tokens,
            )
            generation = trade_report.get("generation") if isinstance(trade_report.get("generation"), dict) else {}
            generation_status = str(generation.get("status") or "").strip().lower()
            generation_mode = str(generation.get("mode") or "").strip().lower()
            diagnostics["llm_model_used"] = _normalize_model_name(generation.get("model") or configured_report_model) or "openrouter/free"
            if generation_status == "ok" and generation_mode == "ai":
                diagnostics["report_status"] = "available"
                diagnostics["report_reason_code"] = ""
                diagnostics["report_reason_human"] = "AI trade report was generated successfully."
                diagnostics["next_expected_step"] = "Open the full report for detailed lifecycle analysis."
            else:
                diagnostics["report_status"] = "failed"
                diagnostics["report_reason_code"] = "llm_generation_failed"
                diagnostics["report_reason_human"] = _report_reason_human("llm_generation_failed")
                diagnostics["next_expected_step"] = _report_next_step("llm_generation_failed")
                diagnostics["last_error_message"] = _sanitize_error_message(generation.get("reason"))

        diagnostics["report_output_available"] = False
        diagnostics["report_artifact_available"] = False

        lifecycle["ai_report_diagnostics"] = dict(diagnostics)
        lifecycle_bundle["ai_report_diagnostics"] = dict(diagnostics)
        trade_story_input["ai_report_diagnostics"] = dict(diagnostics)
        if trade_report:
            trade_report["ai_report_diagnostics"] = dict(diagnostics)

        trade_report_json_written = ""
        trade_report_md_written = ""
        if should_attempt_generation and trade_report:
            try:
                trade_report_json_path.write_text(json.dumps(trade_report, ensure_ascii=False, indent=2), encoding="utf-8")
                trade_report_md_path.write_text(render_trade_report_markdown(trade_report), encoding="utf-8")
                trade_report_json_written = str(trade_report_json_path)
                trade_report_md_written = str(trade_report_md_path)
                diagnostics["report_output_available"] = bool(diagnostics.get("report_status") == "available")
                diagnostics["report_artifact_available"] = bool(diagnostics.get("report_status") == "available")
            except Exception as exc:
                diagnostics["report_status"] = "failed"
                diagnostics["report_reason_code"] = "artifact_write_failed"
                diagnostics["report_reason_human"] = _report_reason_human("artifact_write_failed")
                diagnostics["next_expected_step"] = _report_next_step("artifact_write_failed")
                diagnostics["last_error_message"] = _sanitize_error_message(exc)
                diagnostics["report_output_available"] = False
                diagnostics["report_artifact_available"] = False
        else:
            if trade_report_json_path.exists():
                trade_report_json_path.unlink()
            if trade_report_md_path.exists():
                trade_report_md_path.unlink()

        lifecycle["ai_report_diagnostics"] = dict(diagnostics)
        lifecycle_bundle["ai_report_diagnostics"] = dict(diagnostics)
        trade_story_input["ai_report_diagnostics"] = dict(diagnostics)
        if trade_report:
            trade_report["ai_report_diagnostics"] = dict(diagnostics)
            if trade_report_json_written:
                trade_report_json_path.write_text(json.dumps(trade_report, ensure_ascii=False, indent=2), encoding="utf-8")
                trade_report_md_path.write_text(render_trade_report_markdown(trade_report), encoding="utf-8")

        trade_lifecycle_path.write_text(json.dumps(lifecycle, ensure_ascii=False, indent=2), encoding="utf-8")
        aggregated_bundle_path.write_text(json.dumps(lifecycle_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        story_input_path.write_text(json.dumps(trade_story_input, ensure_ascii=False, indent=2), encoding="utf-8")

        lifecycle_bundle["artifacts"].update(
            {
                "trade_lifecycle_json": str(trade_lifecycle_path),
                "aggregated_execution_bundle_json": str(aggregated_bundle_path),
                "trade_story_input_json": str(story_input_path),
                "trade_report_json": trade_report_json_written,
                "trade_report_md": trade_report_md_written,
            }
        )

        lifecycle_story_type_counts[story_type] = int(lifecycle_story_type_counts.get(story_type, 0) + 1)
        lifecycle_rows.append(
            {
                "trade_id": trade_id,
                "story_id": trade_id,
                "status": status,
                "story_type": story_type,
                "execution_mode_label": execution_mode_label_text,
                "symbol": symbol,
                "entry_run_id": entry_run_id,
                "hold_run_ids": hold_run_ids,
                "exit_run_id": exit_run_id,
                "linked_run_ids": linked_run_ids,
                "lifecycle_summary": str(summary_obj.get("lifecycle_summary_human") or ""),
                "report_json_path": str(aggregated_bundle_path),
                "trade_lifecycle_json_path": str(trade_lifecycle_path),
                "trade_story_input_path": str(story_input_path),
                "trade_report_json_path": trade_report_json_written,
                "trade_report_md_path": trade_report_md_written,
                "trade_report_summary": str((trade_report.get("executive_summary") or {}).get("summary") or ""),
                "report_status": str(diagnostics.get("report_status") or ""),
                "report_reason_code": str(diagnostics.get("report_reason_code") or ""),
                "report_reason_human": str(diagnostics.get("report_reason_human") or ""),
                "report_next_expected_step": str(diagnostics.get("next_expected_step") or ""),
                "report_generation_model": str(diagnostics.get("llm_model_used") or ""),
                "report_generation_attempted": bool(diagnostics.get("generation_attempted")),
            }
        )

        for rid in linked_run_ids:
            row = run_bundle_lookup.get(rid)
            if isinstance(row, dict):
                row["trade_id"] = trade_id
                row["story_id"] = trade_id
                row["trade_lifecycle_json_path"] = str(trade_lifecycle_path)
                row["trade_story_input_path"] = str(story_input_path)
                row["trade_report_json_path"] = trade_report_json_written
                row["trade_report_md_path"] = trade_report_md_written
                row["trade_report_summary"] = str((trade_report.get("executive_summary") or {}).get("summary") or "")
                row["report_status"] = str(diagnostics.get("report_status") or "")
                row["report_reason_code"] = str(diagnostics.get("report_reason_code") or "")
                row["report_reason_human"] = str(diagnostics.get("report_reason_human") or "")
                row["report_next_expected_step"] = str(diagnostics.get("next_expected_step") or "")
                row["report_generation_model"] = str(diagnostics.get("llm_model_used") or "")
                row["report_generation_attempted"] = bool(diagnostics.get("generation_attempted"))
            bundle = run_bundles_by_run.get(rid)
            if isinstance(bundle, dict):
                bundle["trade_id"] = trade_id
                bundle["story_id"] = trade_id
                bundle["ai_report_diagnostics"] = dict(diagnostics)
                bundle.setdefault("artifacts", {})
                bundle["artifacts"].update(
                    {
                        "trade_lifecycle_json": str(trade_lifecycle_path),
                        "trade_story_input_json": str(story_input_path),
                        "trade_report_json": trade_report_json_written,
                        "trade_report_md": trade_report_md_written,
                    }
                )
                report_json_path = Path(str(bundle.get("report_json_path") or ""))
                if report_json_path.exists():
                    report_json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
                report_md_path = Path(str(bundle.get("report_md_path") or ""))
                if report_md_path.exists():
                    report_md_path.write_text(render_bundle_markdown(bundle), encoding="utf-8")

    report_status_counts: Dict[str, int] = {}
    for row in lifecycle_rows:
        key = str(row.get("report_status") or "").strip().lower() or "unknown"
        report_status_counts[key] = int(report_status_counts.get(key, 0) + 1)

    summary_out: Dict[str, Any] = {
        "schema_version": "live_execution_bundles.v3",
        "ok": True,
        "ts": utc_now_iso(),
        "day": day,
        "event_log_path": str(event_log_path),
        "evidence_log_path": str(evidence_log_path),
        "bundle_count": len(lifecycle_rows),
        "trade_lifecycle_count": len(lifecycle_rows),
        "run_bundle_count": len(run_bundle_rows),
        "story_type_counts": lifecycle_story_type_counts,
        "report_status_counts": report_status_counts,
        "run_story_type_counts": run_story_type_counts,
        "canonical_trades_root": str(canonical_trades_root),
        "bundles": lifecycle_rows,
        "run_bundles": run_bundle_rows,
        "day_artifacts": {
            "trade_explain_json": str(trade_js),
            "trade_explain_md": str(trade_md),
            "reporter_analysis_json": str(reporter_js),
            "reporter_analysis_md": str(reporter_md),
            "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
            "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
        },
    }
    summary_json = report_dir / f"live_execution_bundles_{day}.json"
    summary_md = report_dir / f"live_execution_bundles_{day}.md"
    summary_out["report_json_path"] = str(summary_json)
    summary_out["report_md_path"] = str(summary_md)
    summary_json.write_text(json.dumps(summary_out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md.write_text(render_summary_markdown(summary_out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(summary_out, ensure_ascii=False))
    else:
        print(f"day={day} bundle_count={len(lifecycle_rows)} report_json={summary_json} report_md={summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
