from __future__ import annotations

from typing import Any, Mapping


def _metric(summary: Mapping[str, Any], name: str) -> Any:
    return ((summary.get("metrics") or {}).get(name))


def _comparison_table(title: str, rows: Mapping[str, Any], horizon: str = "+30m") -> list[str]:
    output = [
        f"## {title}",
        "",
        "| Group | Population | Observed | Coverage | Win Rate | Avg Net | PF | MDD | Avg MFE | Avg MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    ordered = sorted(
        rows.items(),
        key=lambda item: float(_metric((item[1] or {}).get(horizon) or {}, "expectancy_pct") or -999.0),
        reverse=True,
    )
    for name, horizons in ordered:
        summary = (horizons or {}).get(horizon) or {}
        metrics = summary.get("metrics") or {}
        output.append(
            "| {name} | {population} | {observed} | {coverage:.1%} | {win:.1%} | {avg:+.4f}% | "
            "{pf:.4f} | {mdd:+.4f}% | {mfe} | {mae} |".format(
                name=name,
                population=int(summary.get("population_count") or 0),
                observed=int(summary.get("observed_count") or 0),
                coverage=float(summary.get("coverage") or 0.0),
                win=float(metrics.get("win_rate") or 0.0),
                avg=float(metrics.get("average_return_pct") or 0.0),
                pf=float(metrics.get("profit_factor") or 0.0),
                mdd=float(metrics.get("maximum_drawdown_pct") or 0.0),
                mfe=(
                    f"{float(summary.get('average_mfe_pct')):+.4f}%"
                    if summary.get("average_mfe_pct") is not None
                    else "-"
                ),
                mae=(
                    f"{float(summary.get('average_mae_pct')):+.4f}%"
                    if summary.get("average_mae_pct") is not None
                    else "-"
                ),
            )
        )
    output.append("")
    return output


def render_markdown(payload: Mapping[str, Any]) -> str:
    extraction = payload.get("q9_extraction") or {}
    integrity = payload.get("candidate_integrity") or {}
    actual = payload.get("actual_trade_analysis") or {}
    lines = [
        "# Existing Evidence Mining Result",
        "",
        "## Boundary",
        "",
        "- Offline and research-only.",
        "- No Scanner, Strategist, Commander, Monitor, order, or execution behavior changed.",
        "- July data has already been inspected. Positive findings are screening results, not promotion evidence.",
        "- Candidate outcomes use the fixed 0.28% live round-trip cost.",
        "",
        "## Evidence Inventory",
        "",
        f"- Raw Q9 scanner windows: {int(extraction.get('raw_window_count') or 0):,}",
        f"- Canonical valid windows: {int(extraction.get('canonical_window_count') or 0):,}",
        f"- Valid trading days: {int(extraction.get('day_count') or 0)}",
        f"- Symbols in point-in-time universe: {int(extraction.get('symbol_count') or 0)}",
        f"- Minute-cache complete symbols: "
        f"{int((payload.get('provider_summary') or {}).get('complete_symbol_count') or 0)} / "
        f"{int((payload.get('provider_summary') or {}).get('symbol_count') or 0)}",
        f"- Reconstructed candidate episodes: {int(payload.get('episode_count') or 0):,}",
        f"- Q16 blocked samples with forward paths: {int((payload.get('blocked_samples') or {}).get('sample_count') or 0):,}",
        f"- Quant-shadow source files: "
        f"{int((payload.get('quant_shadow_inventory') or {}).get('source_file_count') or 0):,}",
        f"- Deterministic 15-minute source snapshots read: "
        f"{int((payload.get('quant_shadow_inventory') or {}).get('sampled_source_file_count') or 0):,}",
        f"- Candidate rows in sampled snapshots: "
        f"{int((payload.get('quant_shadow_inventory') or {}).get('raw_candidate_count') or 0):,}",
        f"- Quant-shadow minute-deduped rows: "
        f"{int((payload.get('quant_shadow_inventory') or {}).get('minute_deduped_count') or 0):,}",
        f"- Quant-shadow 15-minute-spaced episodes: "
        f"{int((payload.get('quant_shadow_inventory') or {}).get('spaced_sample_count') or 0):,}",
        f"- Trade evaluations: {int((payload.get('trade_inventory') or {}).get('trade_count') or 0):,}",
        "",
        "## Candidate-Universe Integrity",
        "",
        f"- Sector-theme-only windows: {int(integrity.get('sector_theme_only_window_count') or 0):,} "
        f"({float(integrity.get('sector_theme_only_window_rate') or 0.0):.1%})",
        f"- Windows containing market-native candidates: {int(integrity.get('market_native_window_count') or 0):,} "
        f"({float(integrity.get('market_native_window_rate') or 0.0):.1%})",
        f"- Candidate rows without a retained source: "
        f"{int(integrity.get('missing_source_candidate_count') or 0):,} "
        f"({float(integrity.get('missing_source_candidate_rate') or 0.0):.1%})",
        "",
        "The historical Q9 universe is therefore not a clean full-market control when sector-theme-only coverage is high. "
        "Rank and strategy results below describe the captured candidate universe, not the entire Korean market.",
        "",
    ]
    lines.extend(_comparison_table("Rank Performance", payload.get("by_rank_bucket") or {}))
    lines.extend(_comparison_table("Candidate Source Class", payload.get("by_source_class") or {}))
    lines.extend(_comparison_table("Individual Candidate Sources", payload.get("by_source") or {}))
    lines.extend(_comparison_table("Decision Time Bucket", payload.get("by_time_bucket") or {}))
    lines.extend(
        [
            "## Discovery Cohort: Opening Rank 1",
            "",
            "| Split | Horizon | Observed | Coverage | Win Rate | Avg Net | PF | Positive Days | Largest Day | Largest Symbol |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    opening = (payload.get("discovery_cohorts") or {}).get("opening_rank1") or {}
    for split in ("overall", "calibration", "retrospective"):
        for horizon in ("+5m", "+15m", "+30m", "+60m", "EOD"):
            row = (opening.get(split) or {}).get(horizon) or {}
            metrics = row.get("metrics") or {}
            lines.append(
                f"| {split} | {horizon} | {int(row.get('observed_count') or 0)} | "
                f"{float(row.get('coverage') or 0.0):.1%} | {float(metrics.get('win_rate') or 0.0):.1%} | "
                f"{float(metrics.get('average_return_pct') or 0.0):+.4f}% | "
                f"{float(metrics.get('profit_factor') or 0.0):.4f} | "
                f"{float(row.get('positive_day_ratio') or 0.0):.1%} | "
                f"{float(row.get('largest_day_share') or 0.0):.1%} | "
                f"{float(row.get('largest_symbol_share') or 0.0):.1%} |"
            )
    lines.extend(
        [
            "",
            "This cohort was discovered after inspecting June-July outcomes. It is not a pre-registered "
            "production strategy and requires genuinely later confirmation.",
            "",
        ]
    )

    lines.extend(
        [
            "## Score Component Diagnostics",
            "",
            "| Component | Median | Low Expectancy | High Expectancy | High-Low Delta |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    components = payload.get("score_component_diagnostics") or {}
    for name, row in sorted(
        components.items(),
        key=lambda item: float((item[1] or {}).get("high_minus_low_expectancy_pct") or 0.0),
        reverse=True,
    ):
        low = ((row.get("low") or {}).get("metrics") or {}).get("expectancy_pct") or 0.0
        high = ((row.get("high") or {}).get("metrics") or {}).get("expectancy_pct") or 0.0
        lines.append(
            f"| {name} | {float(row.get('median') or 0.0):.6f} | {float(low):+.4f}% | "
            f"{float(high):+.4f}% | {float(row.get('high_minus_low_expectancy_pct') or 0.0):+.4f}% |"
        )
    lines.extend(["", "## Opportunity Disposition", ""])
    lines.extend(
        [
            "| Disposition | Samples | Observed +30m | Coverage | Average Net | Win Rate | Profit Factor |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    dispositions = (payload.get("blocked_opportunity_analysis") or {}).get("by_disposition") or {}
    for disposition, horizons in sorted(dispositions.items()):
        row = (horizons or {}).get("+30m") or {}
        metrics = row.get("net_metrics") or {}
        lines.append(
            f"| {disposition} | {int(row.get('population_count') or 0)} | "
            f"{int(row.get('observed_count') or 0)} | {float(row.get('coverage') or 0.0):.1%} | "
            f"{float(metrics.get('average_return_pct') or 0.0):+.4f}% | "
            f"{float(metrics.get('win_rate') or 0.0):.1%} | "
            f"{float(metrics.get('profit_factor') or 0.0):.4f} |"
        )
    lines.extend(["", "## Blocked Opportunity Cost", ""])
    blocked = (payload.get("blocked_opportunity_analysis") or {}).get("by_reason") or {}
    lines.extend(
        [
            "| Block Reason | Samples | +15m Avg Net | +15m Winner Rate | +30m Avg Net | +30m Winner Rate | Days | Largest Day |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for reason, horizons in sorted(
        blocked.items(),
        key=lambda item: int(((item[1] or {}).get("+30m") or {}).get("observed_count") or 0),
        reverse=True,
    ):
        row15 = (horizons or {}).get("+15m") or {}
        row30 = (horizons or {}).get("+30m") or {}
        lines.append(
            f"| {reason} | {int(row30.get('population_count') or 0)} | "
            f"{float(((row15.get('net_metrics') or {}).get('average_return_pct')) or 0.0):+.4f}% | "
            f"{float(row15.get('blocked_net_winner_rate') or 0.0):.1%} | "
            f"{float(((row30.get('net_metrics') or {}).get('average_return_pct')) or 0.0):+.4f}% | "
            f"{float(row30.get('blocked_net_winner_rate') or 0.0):.1%} | "
            f"{int(row30.get('day_count') or 0)} | {float(row30.get('largest_day_share') or 0.0):.1%} |"
        )
    lines.extend(["", "## Fixed Path Policy Diagnostics", ""])
    lines.extend(
        [
            "| Policy | Count | Win Rate | Avg Net | PF | MDD | Target | Stop | Time Exit |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy, row in (payload.get("path_policy_analysis") or {}).items():
        metrics = row.get("metrics") or {}
        reasons = row.get("exit_reasons") or {}
        lines.append(
            f"| {policy} | {int(metrics.get('count') or 0)} | {float(metrics.get('win_rate') or 0.0):.1%} | "
            f"{float(metrics.get('average_return_pct') or 0.0):+.4f}% | "
            f"{float(metrics.get('profit_factor') or 0.0):.4f} | "
            f"{float(metrics.get('maximum_drawdown_pct') or 0.0):+.4f}% | "
            f"{int(reasons.get('target') or 0)} | {int(reasons.get('stop') or 0)} | "
            f"{int(reasons.get('time_exit') or 0)} |"
        )
    lines.extend(["", "### Opening Rank 1 Path Policies", ""])
    lines.extend(
        [
            "| Policy | Count | Win Rate | Avg Net | PF | MDD | Target | Stop | Time Exit |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy, row in (payload.get("path_policy_opening_rank1") or {}).items():
        metrics = row.get("metrics") or {}
        reasons = row.get("exit_reasons") or {}
        lines.append(
            f"| {policy} | {int(metrics.get('count') or 0)} | {float(metrics.get('win_rate') or 0.0):.1%} | "
            f"{float(metrics.get('average_return_pct') or 0.0):+.4f}% | "
            f"{float(metrics.get('profit_factor') or 0.0):.4f} | "
            f"{float(metrics.get('maximum_drawdown_pct') or 0.0):+.4f}% | "
            f"{int(reasons.get('target') or 0)} | {int(reasons.get('stop') or 0)} | "
            f"{int(reasons.get('time_exit') or 0)} |"
        )
    lines.extend(
        [
            "",
            "## Actual Trade Diagnostics",
            "",
            f"- Realized trades: {int(actual.get('trade_count') or 0)}",
            f"- Average realized return: {float((actual.get('all_realized') or {}).get('average_return_pct') or 0.0):+.4f}%",
            f"- Promotion-eligible evidence rate: {float(actual.get('promotion_eligible_rate') or 0.0):.1%}",
            f"- Exited before minimum hold: {int(actual.get('before_min_hold_count') or 0)} "
            f"({float(actual.get('before_min_hold_rate') or 0.0):.1%})",
            f"- Horizon violation candidates: {int(actual.get('horizon_violation_count') or 0)} "
            f"({float(actual.get('horizon_violation_rate') or 0.0):.1%})",
            f"- Early-exit average return: "
            f"{float((actual.get('early_exit_metrics') or {}).get('average_return_pct') or 0.0):+.4f}%",
            f"- Minimum-hold-compliant average return: "
            f"{float((actual.get('min_hold_compliant_metrics') or {}).get('average_return_pct') or 0.0):+.4f}%",
            "",
            "| Hold Bucket | Count | Win Rate | Average Return | PF |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for bucket, metrics in (actual.get("by_hold_bucket") or {}).items():
        lines.append(
            f"| {bucket} | {int(metrics.get('count') or 0)} | "
            f"{float(metrics.get('win_rate') or 0.0):.1%} | "
            f"{float(metrics.get('average_return_pct') or 0.0):+.4f}% | "
            f"{float(metrics.get('profit_factor') or 0.0):.4f} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            str(payload.get("decision_summary") or ""),
            "",
        ]
    )
    return "\n".join(lines)
