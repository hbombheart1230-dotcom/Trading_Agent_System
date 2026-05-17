from __future__ import annotations

from collections import Counter
from typing import Any, Dict

from libs.reporting.report_metadata import render_data_freshness_markdown


def _counter_lines(values: Dict[str, Any], *, limit: int | None = None) -> list[str]:
    if not values:
        return ["- (none)"]
    rows = Counter(values).most_common(limit)
    return [f"- {name}: {count}" for name, count in rows]


def render_empty_metrics_markdown(day: str) -> str:
    return f"# Metrics Report ({day})\n\nNo events found.\n"


def render_metrics_markdown(summary: Dict[str, Any]) -> str:
    day = str(summary.get("day") or "")
    execution = summary.get("execution") if isinstance(summary.get("execution"), dict) else {}
    llm = summary.get("strategist_llm") if isinstance(summary.get("strategist_llm"), dict) else {}
    skill = summary.get("skill_hydration") if isinstance(summary.get("skill_hydration"), dict) else {}
    commander = summary.get("commander_resilience") if isinstance(summary.get("commander_resilience"), dict) else {}
    portfolio = summary.get("portfolio_guard") if isinstance(summary.get("portfolio_guard"), dict) else {}
    monitor = summary.get("monitor_agent") if isinstance(summary.get("monitor_agent"), dict) else {}
    broker_api = summary.get("broker_api") if isinstance(summary.get("broker_api"), dict) else {}
    latency = summary.get("execution_latency_seconds") if isinstance(summary.get("execution_latency_seconds"), dict) else {}
    llm_latency_ms = llm.get("latency_ms") if isinstance(llm.get("latency_ms"), dict) else {}
    llm_attempts = llm.get("attempts") if isinstance(llm.get("attempts"), dict) else {}
    token_usage = llm.get("token_usage") if isinstance(llm.get("token_usage"), dict) else {}

    lines = [
        f"# Metrics Report ({day})",
        "",
    ]
    lines += render_data_freshness_markdown(summary["data_freshness"])
    lines += [
        f"- events: **{summary['events']}**",
        f"- runs: **{summary['runs']}**",
        f"- intents_created: **{summary['intents_created_total']}**",
        f"- intents_approved: **{summary['intents_approved_total']}**",
        f"- intents_blocked: **{summary['intents_blocked_total']}**",
        f"- intents_executed: **{summary['intents_executed_total']}**",
        "",
        "## Execution",
        "",
        f"- intents_created: **{execution.get('intents_created', 0)}**",
        f"- intents_approved: **{execution.get('intents_approved', 0)}**",
        f"- intents_blocked: **{execution.get('intents_blocked', 0)}**",
        f"- intents_executed: **{execution.get('intents_executed', 0)}**",
        "",
        "## Strategist LLM",
        "",
        f"- total: **{int(llm.get('total') or 0)}**",
        f"- ok_total: **{int(llm.get('ok_total') or 0)}**",
        f"- fail_total: **{int(llm.get('fail_total') or 0)}**",
        f"- success_rate: **{float(llm.get('success_rate') or 0.0):.2%}**",
        f"- circuit_open_total: **{int(llm.get('circuit_open_total') or 0)}**",
        f"- circuit_open_rate: **{float(llm.get('circuit_open_rate') or 0.0):.2%}**",
        "",
        "### Circuit Breaker",
        "",
    ]
    circuit = llm.get("circuit_state_total") if isinstance(llm.get("circuit_state_total"), dict) else {}
    if circuit:
        for name, count in Counter(circuit).most_common():
            lines.append(f"- state[{name}]: {count}")
    else:
        lines.append("- state[(none)]: 0")

    lines += [
        "",
        "### Latency (ms)",
        "",
        f"- count: {int(llm_latency_ms.get('count') or 0)}",
        f"- avg: {float(llm_latency_ms.get('avg') or 0.0):.3f}ms",
        f"- p50: {float(llm_latency_ms.get('p50') or 0.0):.3f}ms",
        f"- p95: {float(llm_latency_ms.get('p95') or 0.0):.3f}ms",
        f"- max: {float(llm_latency_ms.get('max') or 0.0):.3f}ms",
        "",
        "### Attempts",
        "",
        f"- count: {int(llm_attempts.get('count') or 0)}",
        f"- avg: {float(llm_attempts.get('avg') or 0.0):.3f}",
        f"- p50: {float(llm_attempts.get('p50') or 0.0):.3f}",
        f"- p95: {float(llm_attempts.get('p95') or 0.0):.3f}",
        f"- max: {float(llm_attempts.get('max') or 0.0):.3f}",
        "",
        "### Errors By Type",
        "",
    ]
    lines += _counter_lines(llm.get("error_type_total") if isinstance(llm.get("error_type_total"), dict) else {})
    lines += ["", "### Prompt Versions", ""]
    lines += _counter_lines(llm.get("prompt_version_total") if isinstance(llm.get("prompt_version_total"), dict) else {})
    lines += ["", "### Schema Versions", ""]
    lines += _counter_lines(llm.get("schema_version_total") if isinstance(llm.get("schema_version_total"), dict) else {})
    lines += [
        "",
        "### Token Usage and Cost",
        "",
        f"- prompt_tokens_total: {int(token_usage.get('prompt_tokens_total') or 0)}",
        f"- completion_tokens_total: {int(token_usage.get('completion_tokens_total') or 0)}",
        f"- total_tokens_total: {int(token_usage.get('total_tokens_total') or 0)}",
        f"- estimated_cost_usd_total: {float(token_usage.get('estimated_cost_usd_total') or 0.0):.8f}",
        "",
        "## Skill Hydration",
        "",
        f"- total: **{int(skill.get('total') or 0)}**",
        f"- used_runner_total: **{int(skill.get('used_runner_total') or 0)}**",
        f"- fallback_hint_total: **{int(skill.get('fallback_hint_total') or 0)}**",
        f"- fallback_hint_rate: **{float(skill.get('fallback_hint_rate') or 0.0):.2%}**",
        f"- errors_total_sum: **{int(skill.get('errors_total_sum') or 0)}**",
        "",
        "### Runner Sources",
        "",
    ]
    lines += _counter_lines(skill.get("runner_source_total") if isinstance(skill.get("runner_source_total"), dict) else {})
    lines += ["", "### Attempted By Skill", ""]
    lines += _counter_lines(skill.get("attempted_total_by_skill") if isinstance(skill.get("attempted_total_by_skill"), dict) else {})
    lines += ["", "### Ready By Skill", ""]
    lines += _counter_lines(skill.get("ready_total_by_skill") if isinstance(skill.get("ready_total_by_skill"), dict) else {})
    lines += ["", "### Errors By Skill", ""]
    lines += _counter_lines(skill.get("errors_total_by_skill") if isinstance(skill.get("errors_total_by_skill"), dict) else {})

    lines += [
        "",
        "## Commander Resilience",
        "",
        f"- total: **{int(commander.get('total') or 0)}**",
        f"- cooldown_transition_total: **{int(commander.get('cooldown_transition_total') or 0)}**",
        f"- intervention_total: **{int(commander.get('intervention_total') or 0)}**",
        f"- error_total: **{int(commander.get('error_total') or 0)}**",
        "",
        "### Transition Total",
        "",
    ]
    lines += _counter_lines(commander.get("transition_total") if isinstance(commander.get("transition_total"), dict) else {})
    lines += ["", "### Runtime Status Total", ""]
    lines += _counter_lines(commander.get("runtime_status_total") if isinstance(commander.get("runtime_status_total"), dict) else {})
    lines += ["", "### Cooldown Reason Total", ""]
    lines += _counter_lines(commander.get("cooldown_reason_total") if isinstance(commander.get("cooldown_reason_total"), dict) else {})

    lines += [
        "",
        "## Portfolio Guard",
        "",
        f"- total: **{int(portfolio.get('total') or 0)}**",
        f"- applied_total: **{int(portfolio.get('applied_total') or 0)}**",
        f"- approved_total_sum: **{int(portfolio.get('approved_total_sum') or 0)}**",
        f"- blocked_total_sum: **{int(portfolio.get('blocked_total_sum') or 0)}**",
        "",
        "### blocked_reason_topN",
        "",
    ]
    lines += _counter_lines(portfolio.get("blocked_reason_total") if isinstance(portfolio.get("blocked_reason_total"), dict) else {}, limit=5)

    lines += [
        "",
        "## Monitor Agent",
        "",
        f"- total: **{int(monitor.get('total') or 0)}**",
        f"- exit_policy_enabled_total: **{int(monitor.get('exit_policy_enabled_total') or 0)}**",
        f"- exit_evaluated_total: **{int(monitor.get('exit_evaluated_total') or 0)}**",
        f"- exit_trigger_total: **{int(monitor.get('exit_trigger_total') or 0)}**",
        f"- position_sizing_enabled_total: **{int(monitor.get('position_sizing_enabled_total') or 0)}**",
        f"- position_sizing_evaluated_total: **{int(monitor.get('position_sizing_evaluated_total') or 0)}**",
        f"- position_sizing_computed_qty_sum: **{int(monitor.get('position_sizing_computed_qty_sum') or 0)}**",
        f"- position_sizing_zero_qty_total: **{int(monitor.get('position_sizing_zero_qty_total') or 0)}**",
        "",
        "### exit_reason_total",
        "",
    ]
    lines += _counter_lines(monitor.get("exit_reason_total") if isinstance(monitor.get("exit_reason_total"), dict) else {}, limit=5)
    lines += ["", "### position_sizing_reason_total", ""]
    lines += _counter_lines(monitor.get("position_sizing_reason_total") if isinstance(monitor.get("position_sizing_reason_total"), dict) else {}, limit=5)

    lines += [
        "",
        "## No-Trade Observability",
        "",
        f"- near_ready_total: **{int(summary.get('near_ready_total') or 0)}**",
        f"- strategist_fallback_total: **{int(summary.get('strategist_fallback_total') or 0)}**",
        f"- pre_intent_wait_total: **{int(summary.get('pre_intent_wait_total') or 0)}**",
        f"- pre_intent_noop_total: **{int(summary.get('pre_intent_noop_total') or 0)}**",
        f"- guard_block_total: **{int(summary.get('guard_block_total') or 0)}**",
        "",
        "### no_trade_reason_total",
        "",
    ]
    lines += _counter_lines(summary.get("no_trade_reason_total") if isinstance(summary.get("no_trade_reason_total"), dict) else {}, limit=5)
    lines += ["", "### dominant_blocker_total", ""]
    lines += _counter_lines(summary.get("dominant_blocker_total") if isinstance(summary.get("dominant_blocker_total"), dict) else {}, limit=5)
    lines += ["", "### strategist_mode_total", ""]
    lines += _counter_lines(summary.get("strategist_mode_total") if isinstance(summary.get("strategist_mode_total"), dict) else {})

    route_provenance = summary["route_provenance"] if isinstance(summary.get("route_provenance"), dict) else {}
    lines += ["", "## Route Provenance", ""]
    lines.append(f"- route_source: `{route_provenance.get('route_source') or summary['route_source']}`")
    lines.append(f"- route_source_run_count: {int(route_provenance.get('route_source_run_count') or summary['route_source_run_count'])}")
    lines.append(f"- route_source_missing_count: {int(route_provenance.get('route_source_missing_count') or summary['route_source_missing_count'])}")
    lines.append(f"- route_source_breakdown: `{dict(route_provenance.get('route_source_breakdown') or summary.get('route_source_breakdown') or {})}`")
    lines += ["", "### route_selected_total", ""]
    lines += _counter_lines(summary.get("route_selected_total") if isinstance(summary.get("route_selected_total"), dict) else {})
    lines += ["", "### scanner_monitor_alignment_total", ""]
    lines += _counter_lines(summary.get("scanner_monitor_alignment_total") if isinstance(summary.get("scanner_monitor_alignment_total"), dict) else {})

    lines += [
        "",
        "## Latency (execute_from_packet)",
        "",
        f"- count: {int(latency.get('count') or 0)}",
        f"- avg: {float(latency.get('avg') or 0.0):.3f}s",
        f"- p50: {float(latency.get('p50') or 0.0):.3f}s",
        f"- p95: {float(latency.get('p95') or 0.0):.3f}s",
        f"- max: {float(latency.get('max') or 0.0):.3f}s",
        "",
        "## Blocked By Reason",
        "",
    ]
    lines += _counter_lines(summary.get("intents_blocked_by_reason") if isinstance(summary.get("intents_blocked_by_reason"), dict) else {})
    lines += ["", "## API Errors By API ID", ""]
    lines += _counter_lines(summary.get("api_error_total_by_api_id") if isinstance(summary.get("api_error_total_by_api_id"), dict) else {})
    api_error_total = sum(int(value or 0) for value in dict(broker_api.get("api_error_total_by_api_id") or {}).values())
    lines += [
        "",
        "## Broker API (Schema v1)",
        "",
        f"- api_error_total: **{api_error_total}**",
        f"- api_429_total: **{int(broker_api.get('api_429_total') or 0)}**",
        f"- api_429_rate: **{float(broker_api.get('api_429_rate') or 0.0):.2%}**",
    ]
    return "\n".join(lines) + "\n"
