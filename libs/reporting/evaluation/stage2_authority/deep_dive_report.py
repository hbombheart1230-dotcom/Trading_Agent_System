from __future__ import annotations

from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.4f}%"
    except (TypeError, ValueError):
        return "-"


def _rate(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _horizon_table(title: str, payload: Mapping[str, Any]) -> list[str]:
    lines = [f"## {title}", "", "| Horizon | N / Days | R1 Avg / Win | R2 Avg / Win | R2-R1 Avg / Median | Delta Win |", "|---|---:|---:|---:|---:|---:|"]
    for horizon in ("+5m", "+15m", "+30m", "+60m", "EOD"):
        row = _mapping(payload.get(horizon))
        lines.append(
            f"| {horizon} | {row.get('comparison_count', 0)} / {row.get('day_count', 0)} | "
            f"{_pct(row.get('before_average_return_pct'))} / {_rate(row.get('before_positive_rate'))} | "
            f"{_pct(row.get('after_average_return_pct'))} / {_rate(row.get('after_positive_rate'))} | "
            f"{_pct(row.get('average_delta_pct'))} / {_pct(row.get('median_delta_pct'))} | "
            f"{_rate(row.get('positive_delta_rate'))} |"
        )
    return lines + [""]


def _single_role_table(title: str, payload: Mapping[str, Any]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Horizon | Observed / Days | Gross Avg / Median | Net Avg / Median | Net Win / PF | Max Day Share |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    by_horizon = _mapping(payload.get("by_horizon"))
    for horizon in ("+5m", "+15m", "+30m", "+60m", "EOD"):
        row = _mapping(by_horizon.get(horizon))
        lines.append(
            f"| {horizon} | {row.get('observed_count', 0)} / {row.get('day_count', 0)} | "
            f"{_pct(row.get('average_return_pct'))} / {_pct(row.get('median_return_pct'))} | "
            f"{_pct(row.get('average_live_net_return_pct'))} / {_pct(row.get('median_live_net_return_pct'))} | "
            f"{_rate(row.get('live_net_positive_rate'))} / {row.get('live_net_profit_factor', '-')} | "
            f"{_rate(row.get('max_single_day_share'))} |"
        )
    return lines + ["", f"Live-account comparison subtracts a {float(payload.get('live_round_trip_cost_pct') or 0):.2f}% round-trip cost.", ""]


def _sensitivity_table(payload: Mapping[str, Any]) -> list[str]:
    labels = {
        "exclude_top_change_rate_source": "Exclude top_change_rate source",
        "exclude_abs_gross_return_gte_15pct": "Exclude |gross return| >= 15%",
    }
    lines = [
        "## Stage-1 R1 Sensitivity",
        "",
        "| Variant | Horizon | N | Net Avg / Median | Net Win / PF |",
        "|---|---|---:|---:|---:|",
    ]
    for key, label in labels.items():
        rows = _mapping(payload.get(key))
        for horizon in ("+5m", "+30m", "EOD"):
            row = _mapping(rows.get(horizon))
            lines.append(
                f"| {label} | {horizon} | {row.get('observed_count', 0)} | "
                f"{_pct(row.get('average_live_net_return_pct'))} / {_pct(row.get('median_live_net_return_pct'))} | "
                f"{_rate(row.get('live_net_positive_rate'))} / {row.get('live_net_profit_factor', '-')} |"
            )
    return lines + [""]


def render_stage2_effectiveness_deep_dive(payload: Mapping[str, Any]) -> str:
    date_range = _mapping(payload.get("range"))
    coverage = _mapping(payload.get("coverage"))
    lines = [
        f"# Strategist Stage-2 Effectiveness Deep Dive ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "Evaluation-only. R1 is the first Scanner Top-1 after Stage-1; R2 is the Scanner Top-1 after the Stage-2 refresh and rerun.",
        "",
        "## Coverage",
        "",
        f"- Refresh records: **{coverage.get('refresh_records', 0)}**",
        f"- Directly linked Stage-2 records: **{coverage.get('stage2_attributable_records', 0)}**",
        f"- R1=R2: **{coverage.get('same_symbol_records', 0)}**",
        f"- R1!=R2: **{coverage.get('changed_symbol_records', 0)}**",
        f"- Independent Stage-2 episodes (30m cooldown): **{coverage.get('independent_stage2_episodes_30m', 0)}**",
        f"- Independent changed-symbol episodes (30m cooldown): **{coverage.get('independent_changed_symbol_episodes_30m', 0)}**",
        "",
    ]
    lines += _single_role_table(
        "Stage-1 R1 Absolute Outcome Across All Refresh Windows",
        _mapping(payload.get("stage1_r1_absolute_all_refresh")),
    )
    lines += _sensitivity_table(_mapping(payload.get("stage1_r1_sensitivity")))
    lines += _single_role_table(
        "Stage-1 R1 Absolute Outcome, Independent 30-Minute Episodes",
        _mapping(payload.get("stage1_r1_absolute_independent_30m")),
    )
    lines += _horizon_table("All Directly Linked Stage-2 Windows", _mapping(payload.get("overall_by_horizon")))
    lines += _horizon_table("R1=R2 Consensus Windows", _mapping(payload.get("same_symbol_by_horizon")))
    lines += _horizon_table("R1!=R2 Candidate-Change Windows", _mapping(payload.get("changed_symbol_by_horizon")))
    independent = _mapping(payload.get("independent_30m_cooldown"))
    lines += _horizon_table(
        "Independent R1!=R2 Episodes (30-Minute Cooldown)",
        _mapping(independent.get("changed_symbol_by_horizon")),
    )
    lines += [
        "## Candidate-Change Discriminators (+30m)",
        "",
        "These are exploratory separators, not promotion decisions.",
        "",
        "| Dimension | Value | N / Days | R1 Avg | R2 Avg | Delta Avg / Median | Max Day |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    dimensions = _mapping(payload.get("dimensions"))
    independent_dimensions = _mapping(independent.get("changed_dimensions"))
    for dimension in (
        "time_bucket",
        "stage2_latency",
        "r1_score_margin",
        "r1_rank_after_refresh",
        "r2_rank_before_refresh",
        "r1_risk",
        "r1_volume_surge",
        "r1_vwap_alignment",
        "r1_trading_value",
        "market_regime_rail",
        "market_direction",
        "stage2_decision",
        "watch_intensity",
        "memory_effect",
        "r1_source_family",
        "r1_source_signature",
        "target_alignment",
    ):
        section = _mapping(dimensions.get(dimension))
        for item in list(section.get("candidate_changed_only") or [])[:12]:
            row = _mapping(_mapping(item.get("by_horizon")).get("+30m"))
            if int(row.get("comparison_count") or 0) <= 0:
                continue
            lines.append(
                f"| {dimension} | {item.get('value')} | {row.get('comparison_count')} / {row.get('day_count')} | "
                f"{_pct(row.get('before_average_return_pct'))} | {_pct(row.get('after_average_return_pct'))} | "
                f"{_pct(row.get('average_delta_pct'))} / {_pct(row.get('median_delta_pct'))} | "
                f"{_rate(row.get('max_single_day_share'))} |"
            )
    lines += [
        "",
        "## Independent-Episode Discriminators (+30m)",
        "",
        "| Dimension | Value | N / Days | R1 Avg | R2 Avg | Delta Avg / Median | Max Day |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for dimension in ("time_bucket", "stage2_latency", "r1_score_margin", "market_direction", "stage2_decision", "memory_effect", "r1_source_family", "r1_source_signature"):
        for item in list(independent_dimensions.get(dimension) or [])[:12]:
            row = _mapping(_mapping(item.get("by_horizon")).get("+30m"))
            if int(row.get("comparison_count") or 0) <= 0:
                continue
            lines.append(
                f"| {dimension} | {item.get('value')} | {row.get('comparison_count')} / {row.get('day_count')} | "
                f"{_pct(row.get('before_average_return_pct'))} | {_pct(row.get('after_average_return_pct'))} | "
                f"{_pct(row.get('average_delta_pct'))} / {_pct(row.get('median_delta_pct'))} | "
                f"{_rate(row.get('max_single_day_share'))} |"
            )
    lines += [
        "",
        "## Interpretation Boundaries",
        "",
    ]
    lines.extend(f"- {value}" for value in payload.get("interpretation_contract") or [])
    lines.append("")
    return "\n".join(lines)
