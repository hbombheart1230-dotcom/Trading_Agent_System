from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None

    if isinstance(ts, (int, float)):
        return int(ts)

    s = str(ts).strip()
    if not s:
        return None

    try:
        return int(float(s))
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> str:
    epoch = _to_epoch(ts)
    if epoch is None:
        return date.today().isoformat()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _extract_intent_action(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return ""

    packet = payload.get("decision_packet")
    if isinstance(packet, dict):
        intent = packet.get("intent")
        if isinstance(intent, dict):
            action = intent.get("action") or intent.get("intent")
            return str(action or "").upper()

    action = payload.get("action") or payload.get("intent")
    return str(action or "").upper()


def _extract_guard_reason(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return "unknown"

    reason = payload.get("reason")
    if reason:
        return str(reason)

    details = payload.get("details")
    if isinstance(details, dict) and details.get("reason"):
        return str(details["reason"])

    return "unknown"


def _extract_api_id(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return "unknown"

    for key in ("api_id", "order_api_id"):
        v = payload.get(key)
        if v:
            return str(v)

    order = payload.get("order")
    if isinstance(order, dict):
        for key in ("api_id", "order_api_id"):
            v = order.get(key)
            if v:
                return str(v)

    packet = payload.get("decision_packet")
    if isinstance(packet, dict):
        intent = packet.get("intent")
        if isinstance(intent, dict):
            for key in ("order_api_id", "api_id"):
                v = intent.get(key)
                if v:
                    return str(v)

    skill = payload.get("skill")
    if skill:
        return f"skill:{skill}"

    return "unknown"


def _looks_like_429(value: Any) -> bool:
    if value is None:
        return False
    try:
        if int(float(value)) == 429:
            return True
    except Exception:
        pass

    s = str(value).strip().lower()
    if not s:
        return False
    if s == "429":
        return True
    if "429" in s:
        return True
    return False


def _is_429_error_row(row: Dict[str, Any]) -> bool:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return False

    for key in ("status_code", "http_status", "http_status_code", "code", "error_code"):
        if _looks_like_429(payload.get(key)):
            return True

    nested = payload.get("response")
    if isinstance(nested, dict):
        for key in ("status_code", "http_status", "code"):
            if _looks_like_429(nested.get(key)):
                return True

    if _looks_like_429(payload.get("error")):
        return True
    if _looks_like_429(payload.get("error_type")):
        return True
    return False


def _numeric_summary(values: List[float]) -> Dict[str, float]:
    vals = sorted(float(v) for v in values if float(v) >= 0.0)
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


def _to_non_negative_int(v: Any) -> int:
    try:
        n = int(float(v))
    except Exception:
        return 0
    return n if n >= 0 else 0


def _extract_skill_error_tag(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return "unknown"
    if "(" in s:
        return (s.split("(", 1)[0] or "unknown").strip() or "unknown"
    return (s.split(":", 1)[0] or "unknown").strip() or "unknown"


def _latency_summary(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    start_by_run: Dict[str, int] = {}
    latencies: List[float] = []

    sorted_rows = sorted(rows, key=lambda r: int(r.get("_epoch") or 0))
    for r in sorted_rows:
        run_id = str(r.get("run_id") or "")
        if not run_id:
            continue

        stage = str(r.get("stage") or "")
        event = str(r.get("event") or "")
        epoch = r.get("_epoch")
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
            dt = float(int(epoch) - int(start))
            if dt >= 0:
                latencies.append(dt)

    return _numeric_summary(latencies)


def generate_metrics_report(events_path: Path, out_dir: Path, day: str | None = None) -> Tuple[Path, Path]:
    """Generate daily metrics summary (MD + JSON) from events.jsonl."""
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for raw in _iter_events(events_path):
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        epoch = _to_epoch(ts)
        rows.append({**raw, "_epoch": epoch, "_day": _utc_day(ts)})

    if not rows:
        day = day or date.today().isoformat()
        md_path = out_dir / f"metrics_{day}.md"
        js_path = out_dir / f"metrics_{day}.json"
        empty = {
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
            "broker_api": {
                "api_error_total_by_api_id": {},
                "api_429_total": 0,
                "api_429_rate": 0.0,
            },
            "api_error_total_by_api_id": {},
        }
        md_path.write_text(f"# Metrics Report ({day})\n\nNo events found.\n", encoding="utf-8")
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

    for r in day_rows:
        stage = str(r.get("stage") or "")
        event = str(r.get("event") or "")

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
                if tr == "cooldown":
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

    summary = {
        "schema_version": "metrics.v1",
        "day": day,
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
        "broker_api": {
            "api_error_total_by_api_id": dict(api_errors_by_id),
            "api_429_total": int(api_429_total),
            "api_429_rate": float(api_429_rate),
        },
        "api_error_total_by_api_id": dict(api_errors_by_id),
    }

    md_lines = [
        f"# Metrics Report ({day})",
        "",
        f"- schema_version: **{summary['schema_version']}**",
        f"- events: **{summary['events']}**",
        f"- runs: **{summary['runs']}**",
        f"- intents_created_total: **{intents_created}**",
        f"- intents_approved_total: **{intents_approved}**",
        f"- intents_blocked_total: **{intents_blocked}**",
        f"- intents_executed_total: **{intents_executed}**",
        "",
        "## Execution (Schema v1)",
        "",
        f"- intents_created: **{intents_created}**",
        f"- intents_approved: **{intents_approved}**",
        f"- intents_blocked: **{intents_blocked}**",
        f"- intents_executed: **{intents_executed}**",
        "",
        "### blocked_reason_topN",
        "",
    ]

    if blocks_by_reason:
        for reason, cnt in blocks_by_reason.most_common(5):
            md_lines.append(f"- {reason}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Strategist LLM",
        "",
        f"- total: **{llm_total}**",
        f"- ok_total: **{llm_ok_total}**",
        f"- fail_total: **{llm_fail_total}**",
        f"- success_rate: **{llm_success_rate:.2%}**",
        f"- circuit_open_total: **{int(llm_circuit_open_total)}**",
        f"- circuit_open_rate: **{llm_circuit_open_rate:.2%}**",
        "",
        "### Circuit Breaker",
        "",
    ]

    if llm_circuit_state_total:
        for st_name, cnt in llm_circuit_state_total.most_common():
            md_lines.append(f"- state[{st_name}]: {cnt}")
    else:
        md_lines.append("- state[(none)]: 0")

    md_lines += [
        "",
        "### Latency (ms)",
        "",
        f"- count: {int(llm_latency_ms['count'])}",
        f"- avg: {llm_latency_ms['avg']:.3f}ms",
        f"- p50: {llm_latency_ms['p50']:.3f}ms",
        f"- p95: {llm_latency_ms['p95']:.3f}ms",
        f"- max: {llm_latency_ms['max']:.3f}ms",
        "",
        "### Attempts",
        "",
        f"- count: {int(llm_attempts['count'])}",
        f"- avg: {llm_attempts['avg']:.3f}",
        f"- p50: {llm_attempts['p50']:.3f}",
        f"- p95: {llm_attempts['p95']:.3f}",
        f"- max: {llm_attempts['max']:.3f}",
        "",
        "### Errors By Type",
        "",
    ]

    if llm_error_by_type:
        for et, cnt in llm_error_by_type.most_common():
            md_lines.append(f"- {et}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Prompt Versions", ""]
    if llm_prompt_version_total:
        for v, cnt in llm_prompt_version_total.most_common():
            md_lines.append(f"- {v}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Schema Versions", ""]
    if llm_schema_version_total:
        for v, cnt in llm_schema_version_total.most_common():
            md_lines.append(f"- {v}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "### Token Usage and Cost",
        "",
        f"- prompt_tokens_total: {int(llm_prompt_tokens_total)}",
        f"- completion_tokens_total: {int(llm_completion_tokens_total)}",
        f"- total_tokens_total: {int(llm_total_tokens_total)}",
        f"- estimated_cost_usd_total: {llm_estimated_cost_usd_total:.8f}",
    ]

    md_lines += [
        "",
        "## Skill Hydration",
        "",
        f"- total: **{int(skill_hydration_total)}**",
        f"- used_runner_total: **{int(skill_hydration_used_runner_total)}**",
        f"- fallback_hint_total: **{int(skill_hydration_fallback_hint_total)}**",
        f"- fallback_hint_rate: **{skill_hydration_fallback_rate:.2%}**",
        f"- errors_total_sum: **{int(skill_hydration_errors_total_sum)}**",
        "",
        "### Runner Sources",
        "",
    ]
    if skill_hydration_runner_source_total:
        for name, cnt in skill_hydration_runner_source_total.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Attempted By Skill", ""]
    if skill_hydration_attempted_total:
        for name, cnt in skill_hydration_attempted_total.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Ready By Skill", ""]
    if skill_hydration_ready_total:
        for name, cnt in skill_hydration_ready_total.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Errors By Skill", ""]
    if skill_hydration_errors_by_skill:
        for name, cnt in skill_hydration_errors_by_skill.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Commander Resilience",
        "",
        f"- total: **{int(commander_total)}**",
        f"- cooldown_transition_total: **{int(commander_cooldown_transition_total)}**",
        f"- intervention_total: **{int(commander_intervention_total)}**",
        f"- error_total: **{int(commander_error_total)}**",
        "",
        "### Transition Total",
        "",
    ]
    if commander_transition_total:
        for name, cnt in commander_transition_total.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Runtime Status Total", ""]
    if commander_runtime_status_total:
        for name, cnt in commander_runtime_status_total.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### Cooldown Reason Total", ""]
    if commander_cooldown_reason_total:
        for name, cnt in commander_cooldown_reason_total.most_common():
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Portfolio Guard",
        "",
        f"- total: **{int(portfolio_guard_total)}**",
        f"- applied_total: **{int(portfolio_guard_applied_total)}**",
        f"- approved_total_sum: **{int(portfolio_guard_approved_total_sum)}**",
        f"- blocked_total_sum: **{int(portfolio_guard_blocked_total_sum)}**",
        "",
        "### blocked_reason_topN",
        "",
    ]
    if portfolio_guard_reason_total:
        for name, cnt in portfolio_guard_reason_total.most_common(5):
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Monitor Agent",
        "",
        f"- total: **{int(monitor_total)}**",
        f"- exit_policy_enabled_total: **{int(monitor_exit_policy_enabled_total)}**",
        f"- exit_evaluated_total: **{int(monitor_exit_evaluated_total)}**",
        f"- exit_trigger_total: **{int(monitor_exit_trigger_total)}**",
        f"- position_sizing_enabled_total: **{int(monitor_position_sizing_enabled_total)}**",
        f"- position_sizing_evaluated_total: **{int(monitor_position_sizing_evaluated_total)}**",
        f"- position_sizing_computed_qty_sum: **{int(monitor_position_sizing_computed_qty_sum)}**",
        f"- position_sizing_zero_qty_total: **{int(monitor_position_sizing_zero_qty_total)}**",
        "",
        "### exit_reason_total",
        "",
    ]
    if monitor_exit_reason_total:
        for name, cnt in monitor_exit_reason_total.most_common(5):
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "### position_sizing_reason_total", ""]
    if monitor_position_sizing_reason_total:
        for name, cnt in monitor_position_sizing_reason_total.most_common(5):
            md_lines.append(f"- {name}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Latency (execute_from_packet)",
        "",
        f"- count: {int(latency['count'])}",
        f"- avg: {latency['avg']:.3f}s",
        f"- p50: {latency['p50']:.3f}s",
        f"- p95: {latency['p95']:.3f}s",
        f"- max: {latency['max']:.3f}s",
        "",
        "## Blocked By Reason",
        "",
    ]

    if blocks_by_reason:
        for reason, cnt in blocks_by_reason.most_common():
            md_lines.append(f"- {reason}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "## API Errors By API ID", ""]
    if api_errors_by_id:
        for api_id, cnt in api_errors_by_id.most_common():
            md_lines.append(f"- {api_id}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Broker API (Schema v1)",
        "",
        f"- api_error_total: **{api_error_total}**",
        f"- api_429_total: **{int(api_429_total)}**",
        f"- api_429_rate: **{api_429_rate:.2%}**",
    ]

    md_path = out_dir / f"metrics_{day}.md"
    js_path = out_dir / f"metrics_{day}.json"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    js_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path


def main() -> None:
    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/events.jsonl"))
    out_dir = Path(os.getenv("REPORT_DIR", "./reports")) / "metrics"
    day = os.getenv("METRICS_DAY")
    md, js = generate_metrics_report(events_path, out_dir, day=day)
    print(f"Wrote: {md}")
    print(f"Wrote: {js}")


if __name__ == "__main__":
    main()
