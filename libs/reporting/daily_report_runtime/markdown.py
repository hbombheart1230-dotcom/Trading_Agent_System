from __future__ import annotations

import json
from collections import Counter
from typing import Any, Callable, Dict, List

from libs.reporting.narrative_axes import narrative_axis_policy
from libs.reporting.report_metadata import render_data_freshness_markdown


ResidualRenderer = Callable[[Dict[str, Any]], List[str]]


def render_operator_summary_snapshot(
    operator_summary_snapshot: Dict[str, Any],
    *,
    include_system_status: bool,
) -> List[str]:
    executive = (
        operator_summary_snapshot.get("executive_summary")
        if isinstance(operator_summary_snapshot.get("executive_summary"), dict)
        else {}
    )
    if not executive.get("summary_lines"):
        return []

    lines = ["", "## Operator Summary Snapshot", ""]
    if include_system_status and executive.get("system_status"):
        lines.append(f"- system_status: **{executive['system_status']}**")
    for line in executive.get("summary_lines") or []:
        lines.append(f"- {line}")
    return lines


def render_route_and_narrative_sections(payload: Dict[str, Any]) -> List[str]:
    route_summary = payload.get("route_summary") if isinstance(payload.get("route_summary"), dict) else {}
    narrative_policy = (
        payload.get("narrative_axis_policy")
        if isinstance(payload.get("narrative_axis_policy"), dict)
        else narrative_axis_policy()
    )
    return [
        "",
        "## Route Provenance",
        "",
        f"- route_source: `{route_summary.get('route_source') or '-'}`",
        f"- route_source_run_count: **{int(route_summary.get('route_source_run_count') or 0)}**",
        f"- route_source_missing_count: **{int(route_summary.get('route_source_missing_count') or 0)}**",
        f"- route_source_breakdown: `{json.dumps(route_summary.get('route_source_breakdown') or {}, ensure_ascii=False)}`",
        f"- route_selected_total: `{json.dumps(route_summary.get('route_selected_total') or {}, ensure_ascii=False)}`",
        "",
        "## Narrative Axis Policy",
        "",
        f"- entry_primary_for: `{narrative_policy.get('entry_primary_for') or []}`",
        f"- exit_primary_for: `{narrative_policy.get('exit_primary_for') or []}`",
        f"- mixed_only_for_ambiguous_cases: **{bool(narrative_policy.get('mixed_only_for_ambiguous_cases'))}**",
        f"- runtime_semantics_unchanged: **{bool(narrative_policy.get('runtime_semantics_unchanged'))}**",
    ]


def render_trade_report_integrity(payload: Dict[str, Any]) -> List[str]:
    integrity = payload.get("trade_report_integrity") if isinstance(payload.get("trade_report_integrity"), dict) else {}
    if not integrity:
        return []
    missing = integrity.get("missing") if isinstance(integrity.get("missing"), list) else []
    lines = [
        "",
        "## Trade Report Integrity",
        "",
        f"- status: **{str(integrity.get('status') or 'unknown').upper()}**",
        f"- expected_trade_count: **{int(integrity.get('expected_trade_count') or 0)}**",
        f"- summary_md_count: **{int(integrity.get('summary_md_count') or 0)}**",
        f"- summary_json_count: **{int(integrity.get('summary_json_count') or 0)}**",
        f"- summary_input_count: **{int(integrity.get('summary_input_count') or 0)}**",
        f"- missing_count: **{int(integrity.get('missing_count') or 0)}**",
    ]
    for row in missing[:10]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- missing `{row.get('trade_id') or '-'}` {row.get('symbol') or ''}: "
            f"`{json.dumps(row.get('missing') or [], ensure_ascii=False)}`"
        )
    return lines


def render_broker_alignment(payload: Dict[str, Any]) -> List[str]:
    alignment = payload.get("broker_alignment") if isinstance(payload.get("broker_alignment"), dict) else {}
    if not alignment:
        return []
    summary = alignment.get("summary") if isinstance(alignment.get("summary"), dict) else {}
    status = str(alignment.get("status") or "unknown")
    lines = [
        "",
        "## Broker Alignment",
        "",
        f"- status: **{status.upper()}**",
        f"- generated_at: `{alignment.get('generated_at') or '-'}`",
        f"- local_total: **{int(summary.get('local_total') or 0)}**",
        f"- broker_total: **{int(summary.get('broker_total') or 0)}**",
        f"- matched_by_ord_no: **{int(summary.get('matched_by_ord_no') or 0)}**",
        f"- missing_in_local: **{int(summary.get('missing_in_local_total') or 0)}**",
        f"- missing_in_broker: **{int(summary.get('missing_in_broker_total') or 0)}**",
    ]
    if alignment.get("error"):
        lines.append(f"- error: `{alignment.get('error')}`")
    if alignment.get("report_json_path"):
        lines.append(f"- report_json: `{alignment.get('report_json_path')}`")
    snapshot = alignment.get("account_snapshot") if isinstance(alignment.get("account_snapshot"), dict) else {}
    if snapshot:
        lines.append(f"- account_snapshot_status: **{str(snapshot.get('status') or 'unknown').upper()}**")
        if snapshot.get("path"):
            lines.append(f"- account_snapshot_json: `{snapshot.get('path')}`")
        if snapshot.get("api_call_count") not in (None, ""):
            lines.append(
                f"- account_snapshot_calls: **{int(snapshot.get('ok_count') or 0)}"
                f"/{int(snapshot.get('api_call_count') or 0)} ok**"
            )
        if snapshot.get("error"):
            lines.append(f"- account_snapshot_error: `{snapshot.get('error')}`")
    for title, key in (("missing broker-only rows", "missing_in_local"), ("missing local-only rows", "missing_in_broker")):
        rows = summary.get(key) if isinstance(summary.get(key), list) else []
        if not rows:
            continue
        lines.append(f"- {title}:")
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"  - ord_no={row.get('ord_no') or '-'} symbol={row.get('symbol') or '-'} "
                f"side={row.get('side') or '-'} qty={row.get('filled_qty') or row.get('qty') or row.get('order_qty') or 0}"
            )
    return lines


def render_policy_surface_sections(payload: Dict[str, Any]) -> List[str]:
    policy_surface_summary = (
        payload.get("policy_surface_quality_summary")
        if isinstance(payload.get("policy_surface_quality_summary"), dict)
        else {}
    )
    policy_surface_exec = (
        payload.get("policy_surface_quality_executive_summary")
        if isinstance(payload.get("policy_surface_quality_executive_summary"), dict)
        else {}
    )
    chart_structure_summary = (
        payload.get("chart_structure_decision_hint_summary")
        if isinstance(payload.get("chart_structure_decision_hint_summary"), dict)
        else {}
    )
    chart_structure_exec = (
        payload.get("chart_structure_decision_hint_executive_summary")
        if isinstance(payload.get("chart_structure_decision_hint_executive_summary"), dict)
        else {}
    )
    policy_surface_source = (
        payload.get("policy_surface_quality_source")
        if isinstance(payload.get("policy_surface_quality_source"), dict)
        else {}
    )
    chart_structure_source = (
        payload.get("chart_structure_decision_hint_source")
        if isinstance(payload.get("chart_structure_decision_hint_source"), dict)
        else {}
    )
    chart_structure_examples = (
        chart_structure_summary.get("applied_examples")
        if isinstance(chart_structure_summary.get("applied_examples"), list)
        else []
    )

    lines = [
        "",
        "## Policy Surface Executive Summary",
        "",
        f"- status: **{str(policy_surface_exec.get('status') or 'unknown').upper()}**",
        f"- headline: {str(policy_surface_exec.get('headline') or 'Policy surface unknown')}",
        "",
        "## Policy Surface Quality",
        "",
        f"- schema_available_rate: **{float(policy_surface_summary.get('schema_available_rate') or 0.0):.4f}**",
        f"- normalized_policy_rate: **{float(policy_surface_summary.get('normalized_policy_rate') or 0.0):.4f}**",
        f"- invalid_spec_rate: **{float(policy_surface_summary.get('invalid_spec_rate') or 0.0):.4f}**",
        f"- total_invalid_specs: **{int(policy_surface_summary.get('total_invalid_specs') or 0)}**",
        f"- run_count: **{int(policy_surface_source.get('run_count') or 0)}**",
        "",
        "## Chart Structure Decision Hint Executive Summary",
        "",
        f"- status: **{str(chart_structure_exec.get('status') or 'unknown').upper()}**",
        f"- headline: {str(chart_structure_exec.get('headline') or 'Chart structure guard unknown')}",
        "",
        "## Chart Structure Decision Hint",
        "",
        f"- available_run_count: **{int(chart_structure_summary.get('available_run_count') or 0)}**",
        f"- applied_count: **{int(chart_structure_summary.get('applied_count') or 0)}**",
        f"- applied_rate: **{float(chart_structure_summary.get('applied_rate') or 0.0):.4f}**",
        f"- top_blocking_features: `{json.dumps(chart_structure_summary.get('top_blocking_features') or [], ensure_ascii=False)}`",
        f"- run_count: **{int(chart_structure_source.get('run_count') or 0)}**",
    ]
    if chart_structure_examples:
        lines += ["", "## Chart Structure Decision Hint Applied Examples", ""]
        for example in chart_structure_examples[:3]:
            if not isinstance(example, dict):
                continue
            lines.append(
                f"- `{example.get('run_id') or '-'}` "
                f"[{str(example.get('entry_style') or '-').upper()}] "
                f"{example.get('reason_transition') or '-'} "
                f"blockers=`{json.dumps(example.get('blocking_features') or [], ensure_ascii=False)}`"
            )
    return lines


def render_top_issues(operator_summary_snapshot: Dict[str, Any]) -> List[str]:
    top_issues = (
        operator_summary_snapshot.get("top_issues")
        if isinstance(operator_summary_snapshot.get("top_issues"), list)
        else []
    )
    if not top_issues:
        return []
    lines = ["", "## Top Issues", ""]
    for issue in top_issues:
        if not isinstance(issue, dict):
            continue
        lines.append(f"- [{issue.get('severity') or '-'}] {issue.get('code') or '-'}: {issue.get('detail') or '-'}")
    return lines


def render_recommended_operator_actions(operator_summary_snapshot: Dict[str, Any]) -> List[str]:
    recommended_actions = (
        operator_summary_snapshot.get("recommended_operator_actions")
        if isinstance(operator_summary_snapshot.get("recommended_operator_actions"), list)
        else []
    )
    if not recommended_actions:
        return []
    lines = ["", "## Recommended Operator Actions", ""]
    for action in recommended_actions:
        lines.append(f"- {action}")
    return lines


def render_no_event_daily_markdown(
    *,
    day: str,
    payload: Dict[str, Any],
    operator_snapshot_freshness: Dict[str, Any],
    render_residual_positions: ResidualRenderer,
) -> str:
    operator_summary_snapshot = (
        payload.get("operator_summary_snapshot")
        if isinstance(payload.get("operator_summary_snapshot"), dict)
        else {}
    )
    residual_positions = payload.get("residual_positions") if isinstance(payload.get("residual_positions"), dict) else {}
    lines = [
        f"# Daily Report ({day})",
        "",
        "No events found.",
    ]
    lines += [""] + render_data_freshness_markdown(payload["data_freshness"])
    lines += [f"- operator_summary_snapshot_stale: **{operator_snapshot_freshness['stale']}**"]
    lines += render_operator_summary_snapshot(operator_summary_snapshot, include_system_status=False)
    lines += render_residual_positions(residual_positions)
    lines += render_trade_report_integrity(payload)
    lines += render_broker_alignment(payload)
    lines += render_route_and_narrative_sections(payload)
    lines += render_policy_surface_sections(payload)
    return "\n".join(lines) + "\n"


def render_daily_markdown(
    *,
    day: str,
    summary: Dict[str, Any],
    operator_summary_snapshot_freshness: Dict[str, Any],
    approvals: int,
    blocks: int,
    symbols_for_day: List[str],
    actions: Counter,
    stage_counter: Counter,
    render_residual_positions: ResidualRenderer,
) -> str:
    operator_summary_snapshot = (
        summary.get("operator_summary_snapshot")
        if isinstance(summary.get("operator_summary_snapshot"), dict)
        else {}
    )
    residual_positions = summary.get("residual_positions") if isinstance(summary.get("residual_positions"), dict) else {}
    lines = [
        f"# Daily Report ({day})",
        "",
        *render_data_freshness_markdown(summary["data_freshness"]),
        f"- operator_summary_snapshot_stale: **{operator_summary_snapshot_freshness['stale']}**",
        "",
        f"- events: **{summary['events']}**",
        f"- approvals: **{approvals}** / blocks: **{blocks}**",
        f"- symbols observed: **{len(symbols_for_day)}**",
        "",
        "## Decision actions",
        "",
    ]
    if actions:
        for key, value in actions.most_common():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- (none)")

    lines += ["", "## Stage counts", ""]
    for key, value in stage_counter.most_common():
        lines.append(f"- {key}: {value}")

    lines += render_operator_summary_snapshot(operator_summary_snapshot, include_system_status=True)
    lines += render_residual_positions(residual_positions)
    lines += render_trade_report_integrity(summary)
    lines += render_broker_alignment(summary)
    lines += render_route_and_narrative_sections(summary)
    lines += render_policy_surface_sections(summary)
    lines += render_top_issues(operator_summary_snapshot)
    lines += render_recommended_operator_actions(operator_summary_snapshot)
    return "\n".join(lines) + "\n"
