from __future__ import annotations

from typing import Any, Mapping


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):+.3f}%"


def _ratio(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.3f}"


def _performance_table(rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Stage | N | Win rate | Average | Median | PF |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in rows.items():
        win_rate = row.get("win_rate")
        lines.append(
            f"| {name} | {row.get('count')} | "
            f"{_pct(float(win_rate) * 100) if win_rate is not None else 'N/A'} | "
            f"{_pct(row.get('average_pct'))} | {_pct(row.get('median_pct'))} | "
            f"{_ratio(row.get('profit_factor'))} |"
        )
    return lines


def _delayed_case_table(
    title: str,
    rows: list[Mapping[str, Any]],
) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Day | Symbol | Name | Playbook | +30m | EOD | D+1 high/close | D+3 high/close | D+5 high/close | Label |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('day')} | {row.get('symbol')} | "
            f"{row.get('symbol_name') or 'N/A'} | {row.get('playbook') or 'N/A'} | "
            f"{_pct(row.get('net_return_30m_pct'))} | "
            f"{_pct(row.get('same_day_close_net_pct'))} | "
            f"{_pct(row.get('d1_max_high_net_pct'))} / "
            f"{_pct(row.get('d1_close_net_pct'))} | "
            f"{_pct(row.get('d3_max_high_net_pct'))} / "
            f"{_pct(row.get('d3_close_net_pct'))} | "
            f"{_pct(row.get('d5_max_high_net_pct'))} / "
            f"{_pct(row.get('d5_close_net_pct'))} | "
            f"{row.get('selection_horizon_label')} |"
        )
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - | None |")
    lines.append("")
    return lines


def _stage_case_table(rows: list[Mapping[str, Any]]) -> list[str]:
    lines = [
        "## Stage Fate Detail",
        "",
        "| Decision | Intrinsic | +30m | Strategist selected / intrinsic rank | Monitor candidate | Commander | Executed / realized |",
        "|---|---|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {str(row.get('decision_time_kst') or '')[5:19]} | "
            f"{row.get('symbol')} {row.get('symbol_name') or ''} | "
            f"{_pct(row.get('intrinsic_30m_net_pct'))} | "
            f"{row.get('strategist_selected_symbol') or 'NONE'} / "
            f"{row.get('intrinsic_post_strategist_rank') or 'OUT'} | "
            f"{row.get('monitor_candidate_symbol') or 'NONE'} "
            f"({_pct(row.get('monitor_candidate_30m_net_pct'))}) | "
            f"{row.get('commander_decision') or 'MISSING'} | "
            f"{row.get('executed_symbol') or 'NONE'} / "
            f"{_pct(row.get('executed_realized_return_pct'))} |"
        )
    lines.append("")
    return lines


def _cohort_table(rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Cohort | N | Decision sec | Gap | Entry vs prior | Rel volume | "
        "Same-day close | D+1 close | D+5 close | Playbooks | Paths |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for name, row in rows.items():
        lines.append(
            f"| {name} | {row.get('count', 0)} | "
            f"{row.get('decision_from_open_sec_avg') or 'N/A'} | "
            f"{_pct(row.get('opening_gap_pct_avg'))} | "
            f"{_pct(row.get('entry_vs_prior_close_pct_avg'))} | "
            f"{_ratio(row.get('opening_relative_volume_avg'))} | "
            f"{_pct(row.get('same_day_close_net_pct_avg'))} | "
            f"{_pct(row.get('d1_close_net_pct_avg'))} | "
            f"{_pct(row.get('d5_close_net_pct_avg'))} | "
            f"`{row.get('playbooks') or {}}` | "
            f"`{row.get('path_types') or {}}` |"
        )
    return lines


def _universe_table(rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Rank bucket | N | +30m avg | D+5 high avg | D+5 close avg | "
        "Negative +30m | Later +5% high | Rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in rows.items():
        lines.append(
            f"| {name} | {row.get('row_count', 0)} | "
            f"{_pct((row.get('return_30m') or {}).get('average_pct'))} | "
            f"{_pct((row.get('d5_high') or {}).get('average_pct'))} | "
            f"{_pct((row.get('d5_close') or {}).get('average_pct'))} | "
            f"{row.get('negative_30m_count', 0)} | "
            f"{row.get('delayed_high_count', 0)} | "
            f"{_pct((row.get('delayed_high_rate') or 0) * 100)} |"
        )
    return lines


def render_markdown(payload: Mapping[str, Any]) -> str:
    stage = payload.get("stage_analysis") or {}
    longitudinal = payload.get("longitudinal_analysis") or {}
    universe = payload.get("universe_control_analysis") or {}
    horizons = longitudinal.get("horizons") or {}
    lines = [
        "# Opening Rank-1 Stage Fate And Longitudinal Review",
        "",
        "## Scope",
        "",
        "- Input: 65 opening pre-Strategist intrinsic Rank-1 decisions.",
        "- Stage comparison: intrinsic, Strategist selection, Monitor candidate, Commander decision, and execution.",
        "- Longitudinal comparison: 60 deduplicated symbol-day selection events.",
        "- Cost: 0.28% round trip at every shadow return.",
        "- Delayed high opportunity: +30m non-positive and a D+5-window high at least +5%.",
        "- Delayed close confirmation: +30m non-positive and D+5 close at least +3%.",
        "- This is retrospective observation only.",
        "",
        "## Evidence Coverage",
        "",
        f"- Q9 decisions: **{stage.get('decision_count', 0)}**",
        f"- Deduplicated events: **{longitudinal.get('event_count', 0)}**",
        f"- Full D+5 coverage: **{longitudinal.get('d5_observed_count', 0)}**",
        f"- Delayed high opportunities: **{longitudinal.get('delayed_high_count', 0)}**",
        f"- Delayed close confirmations: "
        f"**{longitudinal.get('delayed_close_confirmation_count', 0)}**",
        f"- D+5-complete cases with non-positive +30m: "
        f"**{longitudinal.get('negative_d5_complete_count', 0)}**",
        "",
        "## Stage Performance",
        "",
        *_performance_table(stage.get("stage_performance") or {}),
        "",
        "Stage samples differ because later-stage candidates and executions were not",
        "available for every intrinsic decision. Do not compare unmatched sample means",
        "as a causal estimate.",
        "",
        "## Intrinsic Candidate Fate",
        "",
        f"- Strategist relation: `{stage.get('strategist_relation') or {}}`",
        f"- Monitor relation: `{stage.get('monitor_relation') or {}}`",
        f"- Commander decisions: `{stage.get('commander_decisions') or {}}`",
        f"- Intrinsic candidate preserved through execution: "
        f"**{stage.get('intrinsic_preserved_to_execution_count', 0)}**",
        f"- Paired stage deltas: `{stage.get('paired_stage_delta') or {}}`",
        f"- Commander-rejected intrinsic performance: "
        f"`{stage.get('rejected_intrinsic_performance') or {}}`",
        "",
        "## Longitudinal Performance",
        "",
        *_performance_table(horizons),
        "",
        f"- Horizon labels: `{longitudinal.get('label_counts') or {}}`",
        f"- Delayed-high playbooks: "
        f"`{longitudinal.get('delayed_high_by_playbook') or {}}`",
        f"- Delayed-high scenarios: "
        f"`{longitudinal.get('delayed_high_by_scenario') or {}}`",
        f"- Delayed-high rate among non-positive +30m cases: "
        f"**{_pct((longitudinal.get('delayed_high_rate_among_negative') or 0) * 100)}**",
        f"- Durable D+5 close-confirmation rate among non-positive +30m cases: "
        f"**{_pct((longitudinal.get('delayed_close_rate_among_negative') or 0) * 100)}**",
        f"- Durable close retention among delayed-high cases: "
        f"**{_pct((longitudinal.get('delayed_close_retention_rate') or 0) * 100)}**",
        f"- Delayed highs already reached by D+1: "
        f"**{longitudinal.get('delayed_next_day_high_count', 0)}**",
        "",
        "## Immediate Versus Delayed Cohorts",
        "",
        *_cohort_table(longitudinal.get("cohort_comparison") or {}),
        "",
        "## Scanner Rank Universe Control",
        "",
        f"- Candidate paths: **{universe.get('path_count', 0)}**",
        f"- D+5-complete paths: **{universe.get('d5_complete_count', 0)}**",
        f"- Decisions represented: **{universe.get('decision_count', 0)}**",
        "",
        *_universe_table(universe.get("rank_buckets") or {}),
        "",
        f"- Paired Rank-1 minus same-decision alternative mean: "
        f"`{universe.get('paired_top1_minus_alternative_mean') or {}}`",
        "",
    ]
    lines += _delayed_case_table(
        "Delayed High Opportunities",
        list(longitudinal.get("delayed_high_cases") or []),
    )
    lines += _delayed_case_table(
        "Delayed Close Confirmations",
        list(longitudinal.get("delayed_close_cases") or []),
    )
    lines += _stage_case_table(list(payload.get("stage_rows") or []))
    lines += [
        "## Interpretation Rules",
        "",
        "- A future intraday high is opportunity evidence, not proof that a practical",
        "  exit could capture that price.",
        "- Close confirmation is stronger evidence that the selected symbol was right",
        "  but the original horizon was too short.",
        "- Repeated observations of the same symbol on the same day count as one",
        "  longitudinal event.",
        "- Missing future days remain missing and are not treated as failures.",
        "",
    ]
    return "\n".join(lines)
