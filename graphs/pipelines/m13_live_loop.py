from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Type aliases for dependency injection (keeps this pipeline unit-testable).
NodeFn = Callable[[Dict[str, Any]], Dict[str, Any]]

_PER_RUN_TRANSIENT_KEYS = (
    # Core decision/execution outputs should be rebuilt every cycle.
    "run_id",
    "decision_packet",
    "decision_trace",
    "execution",
    # Route/runtime hints are cycle-scoped and should not bleed forward.
    "runtime_fast_path",
    "commander_decision",
    "commander_decision_frame",
    "commander_shadow_runtime",
    "path",
    # Strategist/scanner/monitor artifacts are recomputed or rehydrated per cycle.
    "strategist_output",
    "strategist_llm",
    "strategist_blocked",
    "strategist_output_cache_meta",
    "strategy_policy",
    "selected",
    "selected_symbol",
    "top_stock",
    "scan_results",
    "ranked_candidates",
    "scanner_output",
    "risk",
    "intents",
    "monitor",
    "monitor_output",
    "monitor_exit",
    "monitor_entry_decision_detail",
    "monitor_exit_decision_detail",
    "monitor_action_decision",
    "q9_decision_id",
    "q9_decision_snapshot",
    "q9_decision_snapshot_path",
    "q9_scanner_snapshot_result",
    "q9_commander_snapshot_result",
    # Reporting/debug mirrors should reflect the current cycle only.
    "intraday_trade_report",
    "reasoning_trace",
    "reasoning_trace_provenance",
)


def _clear_per_run_transient_state(state: Dict[str, Any]) -> None:
    for key in _PER_RUN_TRANSIENT_KEYS:
        state.pop(key, None)


def _resolve_report_day(state: Dict[str, Any]) -> str:
    market_status = (
        state.get("kiwoom_market_status")
        if isinstance(state.get("kiwoom_market_status"), dict)
        else {}
    )
    days = []
    for value in (
        state.get("started_at"),
        state.get("ts"),
        state.get("now_iso"),
        state.get("tick_ts"),
        market_status.get("received_at"),
    ):
        text = str(value or "").strip()
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            days.append(text[:10])
    if days:
        return max(days)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _rewrite_state_llm_refs(state: Dict[str, Any], *, day: str, run_id: str, category: str) -> None:
    llm_map = state.get("llm_artifacts") if isinstance(state.get("llm_artifacts"), dict) else {}
    if not llm_map or not category:
        return
    replacements = {
        f"reports\\llm\\{day}\\{run_id}\\": f"reports\\llm\\{day}\\{category}\\{run_id}\\",
        f"reports/llm/{day}/{run_id}/": f"reports/llm/{day}/{category}/{run_id}/",
        f"\\llm\\{day}\\{run_id}\\": f"\\llm\\{day}\\{category}\\{run_id}\\",
        f"/llm/{day}/{run_id}/": f"/llm/{day}/{category}/{run_id}/",
    }
    updated: Dict[str, Any] = {}
    for key, value in dict(llm_map).items():
        text = str(value)
        for old, new in replacements.items():
            text = text.replace(old, new)
        updated[key] = text
    state["llm_artifacts"] = updated


def _classify_current_llm_report(state: Dict[str, Any]) -> None:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return
    reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports") or "reports"))
    day = _resolve_report_day(state)
    try:
        from libs.runtime.llm_report_classifier import organize_llm_run

        result = organize_llm_run(reports_root, day=day, run_id=run_id, dry_run=False, update_day_index=True)
        state["llm_report_classification"] = dict(result)
        _rewrite_state_llm_refs(state, day=day, run_id=run_id, category=str(result.get("category") or ""))
    except Exception as exc:
        state["llm_report_classification_error"] = f"{type(exc).__name__}: {exc}"[:300]


def run_m13_once(
    state: Dict[str, Any],
    *,
    dt: Optional[datetime] = None,
    load_state_fn: Optional[NodeFn] = None,
    save_state_fn: Optional[NodeFn] = None,
    tick_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    eod_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    market_status_fn: Optional[NodeFn] = None,
) -> Dict[str, Any]:
    """M13-3: one-iteration live loop (test-first).

    Default wiring (when fns are not injected):
      - graphs.nodes.load_state.load_state
      - graphs.pipelines.m13_tick.run_m13_tick
      - graphs.pipelines.m13_eod_report.run_m13_eod_report
      - graphs.nodes.save_state.save_state

    The goal is to make a minimal, deterministic 'one loop' unit you can call from CLI.
    """
    if load_state_fn is None:
        from graphs.nodes.load_state import load_state as load_state_fn  # lazy import
    if save_state_fn is None:
        from graphs.nodes.save_state import save_state as save_state_fn  # lazy import
    if tick_fn is None:
        from graphs.pipelines.m13_tick import run_m13_tick as tick_fn  # lazy import
    if eod_fn is None:
        from graphs.pipelines.m13_eod_report import run_m13_eod_report as eod_fn  # lazy import

    # Load persisted state first (state_store_path is read from env by node)
    state = load_state_fn(state)
    try:
        if market_status_fn is None:
            from libs.runtime.market_status_closeout import (
                apply_market_status_closeout_events as market_status_fn,
            )

        state = market_status_fn(state)
    except Exception as exc:
        state["market_status_closeout_error"] = f"{type(exc).__name__}: {exc}"[:300]
    # Each tick should produce a fresh runtime/decision/report trace.
    # Keep durable config + persisted_state, but drop cycle-scoped artifacts.
    _clear_per_run_transient_state(state)
    # One tick (runs M10 only if market open)
    state = tick_fn(state, dt=dt)  # type: ignore[arg-type]
    # End-of-day report trigger (runs only after close, once per day)
    state = eod_fn(state, dt=dt)  # type: ignore[arg-type]
    # Keep LLM audit artifacts grouped for operator review after each completed cycle.
    _classify_current_llm_report(state)
    # Persist state at end
    state = save_state_fn(state)
    return state
