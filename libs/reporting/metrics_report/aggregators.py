from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from libs.reporting.metrics_report.event_extractors import to_epoch, utc_day


def numeric_summary(values: List[float]) -> Dict[str, float]:
    vals = sorted(float(value) for value in values if float(value) >= 0.0)
    if not vals:
        return {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}

    n = len(vals)

    def pct(p: float) -> float:
        if n == 1:
            return float(vals[0])
        idx = int(round((n - 1) * p))
        idx = max(0, min(n - 1, idx))
        return float(vals[idx])

    return {
        "count": float(n),
        "avg": float(sum(vals) / n),
        "p50": pct(0.50),
        "p95": pct(0.95),
        "max": float(vals[-1]),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def epoch_to_iso(epoch: Any) -> str:
    try:
        number = int(float(epoch))
    except Exception:
        return ""
    if number <= 0:
        return ""
    return datetime.fromtimestamp(number, tz=timezone.utc).isoformat(timespec="seconds")


def latency_summary(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    start_by_run: Dict[str, int] = {}
    latencies: List[float] = []

    sorted_rows = sorted(rows, key=lambda row: int(row.get("_epoch") or 0))
    for row in sorted_rows:
        run_id = str(row.get("run_id") or "")
        if not run_id:
            continue

        stage = str(row.get("stage") or "")
        event = str(row.get("event") or "")
        epoch = row.get("_epoch")
        if epoch is None:
            continue

        if stage != "execute_from_packet":
            continue

        if event == "start":
            start_by_run[run_id] = int(epoch)
            continue

        if event in ("end", "error"):
            start = start_by_run.pop(run_id, None)
            if start is None:
                continue
            delta = float(int(epoch) - int(start))
            if delta >= 0:
                latencies.append(delta)

    return numeric_summary(latencies)


def build_event_rows(source_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in source_rows:
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        epoch = to_epoch(ts)
        rows.append({**raw, "_epoch": epoch, "_day": utc_day(ts)})
    return rows


def empty_metrics_summary(day: str) -> Dict[str, Any]:
    return {
        "schema_version": "metrics.v1",
        "day": day,
        "events": 0,
        "runs": 0,
        "intents_created_total": 0,
        "intents_approved_total": 0,
        "intents_blocked_total": 0,
        "intents_executed_total": 0,
        "intents_blocked_by_reason": {},
        "execution": {
            "intents_created": 0,
            "intents_approved": 0,
            "intents_blocked": 0,
            "intents_executed": 0,
            "blocked_reason_topN": [],
        },
        "execution_latency_seconds": {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
        "strategist_llm": {
            "total": 0,
            "ok_total": 0,
            "fail_total": 0,
            "success_rate": 0.0,
            "circuit_open_total": 0,
            "circuit_open_rate": 0.0,
            "circuit_state_total": {},
            "latency_ms": {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
            "attempts": {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
            "error_type_total": {},
            "prompt_version_total": {},
            "schema_version_total": {},
            "token_usage": {
                "prompt_tokens_total": 0,
                "completion_tokens_total": 0,
                "total_tokens_total": 0,
                "estimated_cost_usd_total": 0.0,
            },
        },
        "skill_hydration": {
            "total": 0,
            "used_runner_total": 0,
            "fallback_hint_total": 0,
            "fallback_hint_rate": 0.0,
            "errors_total_sum": 0,
            "runner_source_total": {},
            "attempted_total_by_skill": {},
            "ready_total_by_skill": {},
            "errors_total_by_skill": {},
        },
        "commander_resilience": {
            "total": 0,
            "cooldown_transition_total": 0,
            "intervention_total": 0,
            "error_total": 0,
            "transition_total": {},
            "runtime_status_total": {},
            "cooldown_reason_total": {},
        },
        "portfolio_guard": {
            "total": 0,
            "applied_total": 0,
            "approved_total_sum": 0,
            "blocked_total_sum": 0,
            "blocked_reason_total": {},
            "blocked_reason_topN": [],
        },
        "monitor_agent": {
            "total": 0,
            "exit_policy_enabled_total": 0,
            "exit_evaluated_total": 0,
            "exit_trigger_total": 0,
            "exit_reason_total": {},
            "position_sizing_enabled_total": 0,
            "position_sizing_evaluated_total": 0,
            "position_sizing_computed_qty_sum": 0,
            "position_sizing_zero_qty_total": 0,
            "position_sizing_reason_total": {},
        },
        "no_trade_reason_total": {},
        "dominant_blocker_total": {},
        "near_ready_total": 0,
        "strategist_fallback_total": 0,
        "strategist_mode_total": {},
        "route_selected_total": {},
        "route_source": "canonical_commander_preferred",
        "route_source_run_count": 0,
        "route_source_missing_count": 0,
        "route_source_breakdown": {},
        "scanner_monitor_alignment_total": {},
        "pre_intent_wait_total": 0,
        "pre_intent_noop_total": 0,
        "guard_block_total": 0,
        "broker_api": {
            "api_error_total_by_api_id": {},
            "api_429_total": 0,
            "api_429_rate": 0.0,
        },
        "api_error_total_by_api_id": {},
    }
