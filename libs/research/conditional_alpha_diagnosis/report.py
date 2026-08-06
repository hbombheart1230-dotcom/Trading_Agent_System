from __future__ import annotations

from typing import Any, Mapping


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.3f}%"
    except (TypeError, ValueError):
        return "-"


def _candidate_table(rows: list[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Dimension | Value | Horizon | N | Days | Symbols | Win | Avg | Avg ex Top3 | PF |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:30]:
        lines.append(
            f"| {row.get('dimension')} | {row.get('value')} | {row.get('horizon')} | "
            f"{row.get('count')} | {row.get('day_count')} | {row.get('symbol_count')} | "
            f"{_pct((row.get('win_rate') or 0) * 100)} | {_pct(row.get('average_pct'))} | "
            f"{_pct(row.get('average_without_top3_pct'))} | {row.get('profit_factor')} |"
        )
    return lines


def _stage_table(stage: Mapping[str, Any]) -> list[str]:
    rows = stage.get("stage_performance") or {}
    lines = [
        "| Stage | N | Win | Avg | Median | PF |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in (
        "intrinsic",
        "strategist_selected",
        "monitor_candidate",
        "executed_shadow_30m",
        "executed_realized",
    ):
        row = rows.get(key) or {}
        lines.append(
            f"| {key} | {row.get('count')} | {_pct((row.get('win_rate') or 0) * 100)} | "
            f"{_pct(row.get('average_pct'))} | {_pct(row.get('median_pct'))} | {row.get('profit_factor')} |"
        )
    return lines


def _root_cause_table(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "| Diagnostic Root Cause | N | Win | Intrinsic 30m Avg | PF | Evidence |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report.get("summary") or []:
        lines.append(
            f"| {row.get('root_cause')} | {row.get('count')} | "
            f"{_pct((row.get('win_rate') or 0) * 100)} | {_pct(row.get('average_pct'))} | "
            f"{row.get('profit_factor')} | {row.get('evidence_status')} |"
        )
    return lines


def _horizon_table(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "| Conditional Group | Robust Horizon | Avg | Avg ex Top3 | Evidence |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report.get("recommendations") or []:
        lines.append(
            f"| {row.get('group_id')} | {row.get('best_robust_horizon') or '-'} | "
            f"{_pct(row.get('average_pct'))} | {_pct(row.get('average_without_top3_pct'))} | "
            f"{row.get('evidence_status')} |"
        )
    return lines


def _reactivation_table(rows: list[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Initial Day | Symbol | Name | Trigger Day | Pre-trigger Occurrences | Classification |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('initial_day')} | {row.get('symbol')} | {row.get('symbol_name') or '-'} | "
            f"{row.get('trigger_day')} | {row.get('pre_threshold_occurrence_count')} | "
            f"{row.get('classification')} |"
        )
    return lines


def _contrast_table(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "| Comparison | Left N | Right N | Score Delta | Confidence Delta | Prior-rank Delta | 1m Delta | Volume Delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.get("comparisons") or []:
        delta = row.get("left_minus_right_numeric") or {}
        lines.append(
            f"| {row.get('comparison')} | {(row.get('left') or {}).get('count')} | "
            f"{(row.get('right') or {}).get('count')} | {delta.get('scanner_score')} | "
            f"{delta.get('confidence')} | {delta.get('rank1_prev5m_observations')} | "
            f"{delta.get('precompleted_return_1m_pct')} | {delta.get('opening_relative_volume')} |"
        )
    return lines


def render(payload: Mapping[str, Any]) -> str:
    coverage = payload.get("coverage") or {}
    stage = payload.get("selection_stage_analysis") or {}
    root_causes = payload.get("conditional_stage_attribution") or {}
    horizons = payload.get("conditional_horizon_report") or {}
    contrasts = payload.get("conditional_contrast_report") or {}
    lines = [
        "# Conditional Alpha Diagnosis",
        "",
        "## Scope",
        "",
        "- Offline evidence reconstruction only. No trading behavior is changed.",
        "- Point-in-time inputs are separated from forward outcomes and oracle upper bounds.",
        "- A conditional group is a research screen, not an approved trading policy.",
        "",
        "## Evidence Coverage",
        "",
        f"- Opening Rank-1 cases: {coverage.get('opening_case_count')}",
        f"- D+1 to D+5 longitudinal events: {coverage.get('longitudinal_event_count')}",
        f"- Actual-trade horizon rows: {coverage.get('horizon_trade_count')}",
        f"- Actual-trade context joins: {coverage.get('horizon_context_count')}",
        "",
        "## Screenable Conditional Candidates",
        "",
        *_candidate_table(payload.get("research_candidates") or []),
        "",
        "## Pipeline Stage Performance",
        "",
        *_stage_table(stage),
        "",
        "## Conditional Stage Attribution",
        "",
        *_root_cause_table(root_causes),
        "",
        "The root-cause labels describe where observed 30-minute opportunity changed. "
        "They do not authorize a behavior patch.",
        "",
        "## Success-Failure Contrasts",
        "",
        *_contrast_table(contrasts),
        "",
        f"- Approved/no-execution rows: {(contrasts.get('noop_observability') or {}).get('approved_no_execution_count')}",
        f"- Missing NOOP reason: {(contrasts.get('noop_observability') or {}).get('missing_reason_count')} "
        f"({(contrasts.get('noop_observability') or {}).get('missing_reason_rate')})",
        "- Missing reason is an observability gap, not proof of an incorrect Monitor decision.",
        "",
        "## Conditional Horizon Matrix",
        "",
        *_horizon_table(horizons),
        "",
        "Robust horizon selects the highest cohort average after excluding the top three outcomes. "
        "It is not a per-trade best-exit oracle.",
        "",
        "## Delayed Reactivation Lineage",
        "",
        *_reactivation_table(payload.get("reactivation_lineage") or []),
        "",
        "## Current Interpretation",
        "",
        "1. Opening expansion, horizon extension, and later reactivation are distinct hypotheses.",
        "2. Scanner strategy names alone do not explain outcomes; point-in-time confirmation and volume context matter more.",
        "3. A later high does not imply that holding the original position was executable or profitable.",
        "4. Exact decision-ID links are authoritative. Same-day/symbol links are context only.",
        "5. Any behavior change must be selected after prospective shadow validation.",
        "",
    ]
    return "\n".join(lines)
