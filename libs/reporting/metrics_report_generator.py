from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.reporting.event_log_reader import iter_jsonl_events
from libs.reporting.report_metadata import (
    build_data_freshness,
    build_route_provenance,
)
from libs.reporting.metrics_report.event_extractors import (
    extract_api_id as _extract_api_id,
    extract_guard_reason as _extract_guard_reason,
    extract_intent_action as _extract_intent_action,
    extract_skill_error_tag as _extract_skill_error_tag,
    is_429_error_row as _is_429_error_row,
    looks_like_429 as _looks_like_429,
    to_non_negative_int as _to_non_negative_int,
)
from libs.reporting.metrics_report.aggregators import (
    build_event_rows as _build_event_rows,
    epoch_to_iso as _epoch_to_iso,
    empty_metrics_summary as _empty_metrics_summary,
    latency_summary as _latency_summary,
    numeric_summary as _numeric_summary,
    utc_now_iso as _utc_now_iso,
)
from libs.reporting.metrics_report.markdown import (
    render_empty_metrics_markdown as _render_empty_metrics_markdown,
    render_metrics_markdown as _render_metrics_markdown,
)
from libs.reporting.report_source_helpers import build_commander_route_summary


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj

    return gen()


def generate_metrics_report(events_path: Path, out_dir: Path, day: str | None = None) -> Tuple[Path, Path]:
    """Generate daily metrics summary (MD + JSON) from events.jsonl."""
    out_dir.mkdir(parents=True, exist_ok=True)

    source_rows = iter_jsonl_events(events_path, day=day) if day else _iter_events(events_path)
    rows = _build_event_rows(source_rows)

    if not rows:
        day = day or date.today().isoformat()
        md_path = out_dir / f"metrics_{day}.md"
        js_path = out_dir / f"metrics_{day}.json"
        empty = _empty_metrics_summary(day)
        md_path.write_text(_render_empty_metrics_markdown(day), encoding="utf-8")
        js_path.write_text(json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_path, js_path

    day = day or sorted({str(r.get("_day")) for r in rows})[-1]
    day_rows = [r for r in rows if str(r.get("_day")) == day]

    run_ids = {str(r.get("run_id") or "") for r in day_rows if r.get("run_id")}

    intents_created = 0
    intents_approved = 0
    intents_blocked = 0
    intents_executed = 0
    blocks_by_reason: Counter[str] = Counter()
    api_errors_by_id: Counter[str] = Counter()
    api_429_total = 0
    llm_total = 0
    llm_ok_total = 0
    llm_fail_total = 0
    llm_error_by_type: Counter[str] = Counter()
    llm_prompt_version_total: Counter[str] = Counter()
    llm_schema_version_total: Counter[str] = Counter()
    llm_circuit_state_total: Counter[str] = Counter()
    llm_circuit_open_total = 0
    llm_latency_ms_values: List[float] = []
    llm_attempt_values: List[float] = []
    llm_prompt_tokens_total = 0
    llm_completion_tokens_total = 0
    llm_total_tokens_total = 0
    llm_estimated_cost_usd_total = 0.0
    skill_hydration_total = 0
    skill_hydration_used_runner_total = 0
    skill_hydration_fallback_hint_total = 0
    skill_hydration_errors_total_sum = 0
    skill_hydration_runner_source_total: Counter[str] = Counter()
    skill_hydration_attempted_total: Counter[str] = Counter()
    skill_hydration_ready_total: Counter[str] = Counter()
    skill_hydration_errors_by_skill: Counter[str] = Counter()
    commander_total = 0
    commander_cooldown_transition_total = 0
    commander_intervention_total = 0
    commander_error_total = 0
    commander_transition_total: Counter[str] = Counter()
    commander_runtime_status_total: Counter[str] = Counter()
    commander_cooldown_reason_total: Counter[str] = Counter()
    portfolio_guard_total = 0
    portfolio_guard_applied_total = 0
    portfolio_guard_approved_total_sum = 0
    portfolio_guard_blocked_total_sum = 0
    portfolio_guard_reason_total: Counter[str] = Counter()
    monitor_total = 0
    monitor_exit_policy_enabled_total = 0
    monitor_exit_evaluated_total = 0
    monitor_exit_trigger_total = 0
    monitor_exit_reason_total: Counter[str] = Counter()
    monitor_position_sizing_enabled_total = 0
    monitor_position_sizing_evaluated_total = 0
    monitor_position_sizing_computed_qty_sum = 0
    monitor_position_sizing_zero_qty_total = 0
    monitor_position_sizing_reason_total: Counter[str] = Counter()
    no_trade_reason_total: Counter[str] = Counter()
    dominant_blocker_total: Counter[str] = Counter()
    strategist_mode_total: Counter[str] = Counter()
    route_selected_total: Counter[str] = Counter()
    scanner_monitor_alignment_total: Counter[str] = Counter()
    near_ready_total = 0
    strategist_fallback_total = 0
    pre_intent_wait_total = 0
    pre_intent_noop_total = 0
    guard_block_total = 0
    route_selected_by_run: Dict[str, str] = {}
    latest_run_id = ""
    latest_run_epoch = 0

    for r in day_rows:
        stage = str(r.get("stage") or "")
        event = str(r.get("event") or "")
        run_id = str(r.get("run_id") or "").strip()
        epoch = int(r.get("_epoch") or 0)
        if run_id and epoch >= latest_run_epoch:
            latest_run_epoch = epoch
            latest_run_id = run_id

        if stage == "decision" and event == "trace":
            action = _extract_intent_action(r)
            if action in {"BUY", "SELL"}:
                intents_created += 1

        if stage == "execute_from_packet" and event == "verdict":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            allowed = payload.get("allowed")
            if allowed is True:
                intents_approved += 1
            elif allowed is False:
                intents_blocked += 1
                blocks_by_reason[_extract_guard_reason(r)] += 1

        if stage == "execute_from_packet" and event == "execution":
            intents_executed += 1

        if event == "error":
            api_errors_by_id[_extract_api_id(r)] += 1
            if _is_429_error_row(r):
                api_429_total += 1

        if stage == "strategist_llm" and event == "result":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            llm_total += 1
            ok = payload.get("ok") is True
            if ok:
                llm_ok_total += 1
            else:
                llm_fail_total += 1
                llm_error_by_type[str(payload.get("error_type") or "unknown")] += 1

            c_state = str(payload.get("circuit_state") or "").strip().lower()
            if c_state:
                llm_circuit_state_total[c_state] += 1
            if c_state == "open" or str(payload.get("error_type") or "") == "CircuitOpen":
                llm_circuit_open_total += 1

            llm_prompt_version_total[str(payload.get("prompt_version") or "unknown")] += 1
            llm_schema_version_total[str(payload.get("schema_version") or "unknown")] += 1

            latency_ms = payload.get("latency_ms")
            try:
                latency_val = float(latency_ms)
                if latency_val >= 0:
                    llm_latency_ms_values.append(latency_val)
            except Exception:
                pass

            attempts = payload.get("attempts")
            try:
                attempts_val = float(attempts)
                if attempts_val >= 0:
                    llm_attempt_values.append(attempts_val)
            except Exception:
                pass

            prompt_tokens = payload.get("prompt_tokens")
            try:
                prompt_tokens_val = int(float(prompt_tokens))
                if prompt_tokens_val >= 0:
                    llm_prompt_tokens_total += prompt_tokens_val
            except Exception:
                pass

            completion_tokens = payload.get("completion_tokens")
            try:
                completion_tokens_val = int(float(completion_tokens))
                if completion_tokens_val >= 0:
                    llm_completion_tokens_total += completion_tokens_val
            except Exception:
                pass

            total_tokens = payload.get("total_tokens")
            try:
                total_tokens_val = int(float(total_tokens))
                if total_tokens_val >= 0:
                    llm_total_tokens_total += total_tokens_val
            except Exception:
                pass

            estimated_cost_usd = payload.get("estimated_cost_usd")
            try:
                estimated_cost_usd_val = float(estimated_cost_usd)
                if estimated_cost_usd_val >= 0.0:
                    llm_estimated_cost_usd_total += estimated_cost_usd_val
            except Exception:
                pass

        if stage == "strategist" and event == "policy_resolution":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            mode = str(payload.get("strategy_generation_mode") or "").strip()
            if mode:
                strategist_mode_total[mode] += 1
            if bool(payload.get("fallback_used")):
                strategist_fallback_total += 1

        if stage == "monitor" and event == "entry_decision_detail":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            no_trade = payload.get("no_trade_surface") if isinstance(payload.get("no_trade_surface"), dict) else {}
            handoff = payload.get("scanner_monitor_handoff") if isinstance(payload.get("scanner_monitor_handoff"), dict) else {}
            if no_trade:
                reason_code = str(no_trade.get("no_trade_reason_code") or "").strip()
                dominant_blocker = str(no_trade.get("dominant_blocker") or "").strip()
                if reason_code:
                    no_trade_reason_total[reason_code] += 1
                if dominant_blocker:
                    dominant_blocker_total[dominant_blocker] += 1
                if bool(no_trade.get("near_ready_flag")):
                    near_ready_total += 1
                no_trade_stage = str(no_trade.get("no_trade_stage") or "").strip()
                if no_trade_stage == "pre_intent_wait":
                    pre_intent_wait_total += 1
                elif no_trade_stage == "pre_intent_noop":
                    pre_intent_noop_total += 1
                elif no_trade_stage == "guard_block":
                    guard_block_total += 1
            alignment = str(handoff.get("scanner_vs_monitor_alignment") or "").strip()
            if alignment:
                scanner_monitor_alignment_total[alignment] += 1

        if stage == "skill_hydration" and event == "summary":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            skill_hydration_total += 1
            if payload.get("used_runner") is True:
                skill_hydration_used_runner_total += 1

            runner_source = str(payload.get("runner_source") or "unknown")
            skill_hydration_runner_source_total[runner_source] += 1

            errors_total = _to_non_negative_int(payload.get("errors_total"))
            skill_hydration_errors_total_sum += errors_total

            fallback_hint = bool(payload.get("fallback_hint")) or errors_total > 0
            if fallback_hint:
                skill_hydration_fallback_hint_total += 1

            attempted = payload.get("attempted")
            if isinstance(attempted, dict):
                for k, v in attempted.items():
                    skill_hydration_attempted_total[str(k)] += _to_non_negative_int(v)

            ready = payload.get("ready")
            if isinstance(ready, dict):
                for k, v in ready.items():
                    skill_hydration_ready_total[str(k)] += _to_non_negative_int(v)

            errors = payload.get("errors")
            if isinstance(errors, list):
                for e in errors:
                    skill_hydration_errors_by_skill[_extract_skill_error_tag(e)] += 1

        if stage == "commander_router":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            commander_total += 1

            if event in {"route_selected", "end"} and run_id:
                route_obs = payload.get("route_observability") if isinstance(payload.get("route_observability"), dict) else {}
                route_selected = str(
                    payload.get("route_selected")
                    or route_obs.get("route_selected")
                    or ""
                ).strip()
                if route_selected:
                    route_selected_by_run[run_id] = route_selected

            status = str(payload.get("status") or "").strip()
            if status:
                commander_runtime_status_total[status] += 1

            pg = payload.get("portfolio_guard")
            if isinstance(pg, dict):
                portfolio_guard_total += 1
                if pg.get("applied") is True:
                    portfolio_guard_applied_total += 1
                portfolio_guard_approved_total_sum += _to_non_negative_int(pg.get("approved_total"))
                portfolio_guard_blocked_total_sum += _to_non_negative_int(pg.get("blocked_total"))
                reason_counts = pg.get("blocked_reason_counts")
                if isinstance(reason_counts, dict):
                    for k, v in reason_counts.items():
                        portfolio_guard_reason_total[str(k)] += _to_non_negative_int(v)

            if event == "transition":
                tr = str(payload.get("transition") or "unknown").strip().lower() or "unknown"
                commander_transition_total[tr] += 1
                if tr == "cooldown" or str(payload.get("reason") or "") == "cooldown_active":
                    commander_cooldown_transition_total += 1

            if event == "intervention":
                commander_intervention_total += 1

            if event == "error":
                commander_error_total += 1

            if event == "resilience":
                reason = str(payload.get("reason") or "unknown").strip() or "unknown"
                commander_cooldown_reason_total[reason] += 1

        if stage == "monitor" and event == "summary":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            monitor_total += 1

            if payload.get("exit_policy_enabled") is True:
                monitor_exit_policy_enabled_total += 1
            if payload.get("exit_evaluated") is True:
                monitor_exit_evaluated_total += 1
            if payload.get("exit_triggered") is True:
                monitor_exit_trigger_total += 1

            exit_reason = str(payload.get("exit_reason") or "").strip()
            if exit_reason:
                monitor_exit_reason_total[exit_reason] += 1

            if payload.get("position_sizing_enabled") is True:
                monitor_position_sizing_enabled_total += 1
            if payload.get("position_sizing_evaluated") is True:
                monitor_position_sizing_evaluated_total += 1

            sizing_qty = _to_non_negative_int(payload.get("position_sizing_qty"))
            monitor_position_sizing_computed_qty_sum += sizing_qty
            if payload.get("position_sizing_evaluated") is True and sizing_qty == 0:
                monitor_position_sizing_zero_qty_total += 1

            sizing_reason = str(payload.get("position_sizing_reason") or "").strip()
            if sizing_reason:
                monitor_position_sizing_reason_total[sizing_reason] += 1

    latency = _latency_summary(day_rows)
    llm_latency_ms = _numeric_summary(llm_latency_ms_values)
    llm_attempts = _numeric_summary(llm_attempt_values)
    llm_success_rate = (float(llm_ok_total) / float(llm_total)) if llm_total > 0 else 0.0
    llm_circuit_open_rate = (float(llm_circuit_open_total) / float(llm_total)) if llm_total > 0 else 0.0
    api_error_total = int(sum(int(v) for v in api_errors_by_id.values()))
    api_429_rate = (float(api_429_total) / float(api_error_total)) if api_error_total > 0 else 0.0
    skill_hydration_fallback_rate = (
        float(skill_hydration_fallback_hint_total) / float(skill_hydration_total)
        if skill_hydration_total > 0
        else 0.0
    )
    route_summary = build_commander_route_summary(
        reports_root=out_dir.parent,
        day=day,
        day_rows=day_rows,
    )
    canonical_route_selected_total = dict(route_summary.get("route_selected_total") or {})
    canonical_strategy_mode_total = dict(route_summary.get("strategy_generation_mode_total") or {})
    canonical_fallback_total = int(route_summary.get("strategist_fallback_total") or 0)

    summary = {
        "schema_version": "metrics.v1",
        "day": day,
        "generated_at": _utc_now_iso(),
        "source_run_count": int(len(run_ids)),
        "latest_run_id": latest_run_id,
        "latest_run_ts": _epoch_to_iso(latest_run_epoch),
        "events": len(day_rows),
        "runs": len(run_ids),
        "intents_created_total": intents_created,
        "intents_approved_total": intents_approved,
        "intents_blocked_total": intents_blocked,
        "intents_executed_total": intents_executed,
        "intents_blocked_by_reason": dict(blocks_by_reason),
        "execution": {
            "intents_created": int(intents_created),
            "intents_approved": int(intents_approved),
            "intents_blocked": int(intents_blocked),
            "intents_executed": int(intents_executed),
            "blocked_reason_topN": [
                {"reason": str(reason), "count": int(cnt)}
                for reason, cnt in blocks_by_reason.most_common(5)
            ],
        },
        "execution_latency_seconds": latency,
        "strategist_llm": {
            "total": llm_total,
            "ok_total": llm_ok_total,
            "fail_total": llm_fail_total,
            "success_rate": llm_success_rate,
            "circuit_open_total": int(llm_circuit_open_total),
            "circuit_open_rate": float(llm_circuit_open_rate),
            "circuit_state_total": dict(llm_circuit_state_total),
            "latency_ms": llm_latency_ms,
            "attempts": llm_attempts,
            "error_type_total": dict(llm_error_by_type),
            "prompt_version_total": dict(llm_prompt_version_total),
            "schema_version_total": dict(llm_schema_version_total),
            "token_usage": {
                "prompt_tokens_total": int(llm_prompt_tokens_total),
                "completion_tokens_total": int(llm_completion_tokens_total),
                "total_tokens_total": int(llm_total_tokens_total),
                "estimated_cost_usd_total": float(llm_estimated_cost_usd_total),
            },
        },
        "skill_hydration": {
            "total": int(skill_hydration_total),
            "used_runner_total": int(skill_hydration_used_runner_total),
            "fallback_hint_total": int(skill_hydration_fallback_hint_total),
            "fallback_hint_rate": float(skill_hydration_fallback_rate),
            "errors_total_sum": int(skill_hydration_errors_total_sum),
            "runner_source_total": dict(skill_hydration_runner_source_total),
            "attempted_total_by_skill": dict(skill_hydration_attempted_total),
            "ready_total_by_skill": dict(skill_hydration_ready_total),
            "errors_total_by_skill": dict(skill_hydration_errors_by_skill),
        },
        "commander_resilience": {
            "total": int(commander_total),
            "cooldown_transition_total": int(commander_cooldown_transition_total),
            "intervention_total": int(commander_intervention_total),
            "error_total": int(commander_error_total),
            "transition_total": dict(commander_transition_total),
            "runtime_status_total": dict(commander_runtime_status_total),
            "cooldown_reason_total": dict(commander_cooldown_reason_total),
        },
        "portfolio_guard": {
            "total": int(portfolio_guard_total),
            "applied_total": int(portfolio_guard_applied_total),
            "approved_total_sum": int(portfolio_guard_approved_total_sum),
            "blocked_total_sum": int(portfolio_guard_blocked_total_sum),
            "blocked_reason_total": dict(portfolio_guard_reason_total),
            "blocked_reason_topN": [
                {"reason": str(reason), "count": int(cnt)}
                for reason, cnt in portfolio_guard_reason_total.most_common(5)
            ],
        },
        "monitor_agent": {
            "total": int(monitor_total),
            "exit_policy_enabled_total": int(monitor_exit_policy_enabled_total),
            "exit_evaluated_total": int(monitor_exit_evaluated_total),
            "exit_trigger_total": int(monitor_exit_trigger_total),
            "exit_reason_total": dict(monitor_exit_reason_total),
            "position_sizing_enabled_total": int(monitor_position_sizing_enabled_total),
            "position_sizing_evaluated_total": int(monitor_position_sizing_evaluated_total),
            "position_sizing_computed_qty_sum": int(monitor_position_sizing_computed_qty_sum),
            "position_sizing_zero_qty_total": int(monitor_position_sizing_zero_qty_total),
            "position_sizing_reason_total": dict(monitor_position_sizing_reason_total),
        },
        "no_trade_reason_total": dict(no_trade_reason_total),
        "dominant_blocker_total": dict(dominant_blocker_total),
        "near_ready_total": int(near_ready_total),
        "strategist_fallback_total": int(canonical_fallback_total),
        "strategist_mode_total": dict(canonical_strategy_mode_total),
        "route_selected_total": dict(canonical_route_selected_total),
        "route_source": str(route_summary.get("route_source") or "canonical_commander_preferred"),
        "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
        "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
        "route_source_breakdown": dict(route_summary.get("route_source_breakdown") or {}),
        "scanner_monitor_alignment_total": dict(scanner_monitor_alignment_total),
        "pre_intent_wait_total": int(pre_intent_wait_total),
        "pre_intent_noop_total": int(pre_intent_noop_total),
        "guard_block_total": int(guard_block_total),
        "broker_api": {
            "api_error_total_by_api_id": dict(api_errors_by_id),
            "api_429_total": int(api_429_total),
            "api_429_rate": float(api_429_rate),
        },
        "api_error_total_by_api_id": dict(api_errors_by_id),
    }
    summary["data_freshness"] = build_data_freshness(
        generated_at=summary["generated_at"],
        source_run_count=summary["source_run_count"],
        latest_run_id=summary["latest_run_id"],
        latest_run_ts=summary["latest_run_ts"],
        stale=False,
    )
    summary["route_provenance"] = build_route_provenance(route_summary)

    md_text = _render_metrics_markdown(summary)

    md_path = out_dir / f"metrics_{day}.md"
    js_path = out_dir / f"metrics_{day}.json"
    md_path.write_text(md_text, encoding="utf-8")
    js_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path


def main() -> None:
    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/events.jsonl"))
    out_dir = Path(os.getenv("REPORT_DIR", "./reports")) / "metrics"
    day = os.getenv("METRICS_DAY")
    result = Reporter().generate_metrics_report(
        event_log_path=events_path,
        report_dir=out_dir,
        day=day,
    )
    print(f"Wrote: {result.report_md_path}")
    print(f"Wrote: {result.report_json_path}")


if __name__ == "__main__":
    main()
