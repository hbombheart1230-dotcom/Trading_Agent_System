from __future__ import annotations

from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _metric_cell(value: Any) -> str:
    row = _mapping(value)
    count = int(row.get("sample_count") or 0)
    if not count:
        return "-"
    win_rate = row.get("win_rate")
    return (
        f"N={count}, WR {float(win_rate or 0) * 100:.1f}%, "
        f"avg {float(row.get('avg_net_return_pct') or 0):+.4f}%, "
        f"PF {float(row.get('profit_factor') or 0):.4f}"
    )


def render_short_alpha_discriminator(payload: Mapping[str, Any]) -> str:
    cohort_review = _mapping(payload.get("cohort_review"))
    prospective = _mapping(cohort_review.get("prospective"))
    contract = _mapping(cohort_review.get("prospective_contract"))
    sensitivity = _mapping(cohort_review.get("historical_sensitivity"))
    profit_fade = _mapping(payload.get("profit_fade_review"))
    scanner = _mapping(payload.get("scanner_diagnostics"))
    strategist = _mapping(payload.get("strategist_stage2_review"))
    integrity = _mapping(payload.get("integrity"))
    lines = [
        "# Short Alpha Discriminator",
        "",
        f"- Through day: `{payload.get('through_day')}`",
        f"- Behavior effect: `{payload.get('behavior_effect')}`",
        f"- Integrity: `{integrity.get('status')}`",
        f"- Fixed prospective start: `{contract.get('first_eligible_day')}`",
        "- Strategist Stage-2 authority changed: **No**",
        "",
        "## Cohort Comparison",
        "",
        "| Cohort | Day-symbol N | +5m | +15m | +30m | EOD |",
        "|---|---:|---|---|---|---|",
    ]
    for raw in cohort_review.get("cohorts") or []:
        row = _mapping(raw)
        horizons = _mapping(row.get("horizons"))
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                row.get("cohort_id"),
                int(row.get("independent_day_symbol_count") or 0),
                _metric_cell(horizons.get("+5m")),
                _metric_cell(horizons.get("+15m")),
                _metric_cell(horizons.get("+30m")),
                _metric_cell(horizons.get("EOD")),
            )
        )
    lines.extend(
        [
            "",
            "## Historical Sensitivity",
            "",
            "Expanded canonical history is discovery evidence, not prospective validation.",
            "",
        ]
    )
    without_best = _mapping(sensitivity.get("without_best_observation"))
    lines.extend(
        [
            f"- Removed best observation: `{without_best.get('excluded_day')}` / `{without_best.get('excluded_symbol')}`",
            f"- Without best +5m: {_metric_cell(without_best.get('+5m'))}",
            f"- Without best +30m: {_metric_cell(without_best.get('+30m'))}",
            f"- Leave-one-symbol cases: **{len(sensitivity.get('by_symbol_leave_one_out') or [])}**",
            f"- Leave-one-day cases: **{len(sensitivity.get('by_day_leave_one_out') or [])}**",
            "",
            "## Prospective Status",
            "",
            f"- Candidate: `{contract.get('candidate_id')}`",
            f"- Conditions: `{', '.join(str(value) for value in contract.get('conditions') or [])}`",
            f"- Prospective episodes: **{int(prospective.get('episode_count') or 0)}**",
            "- Historical reference and prospective evidence are stored separately.",
            "",
            "## Profit Fade",
            "",
            f"- Cohort episodes: **{int(profit_fade.get('cohort_episode_count') or 0)}**",
            f"- Positive at +5m but non-positive at EOD: **{int(profit_fade.get('positive_5m_to_negative_eod_count') or 0)}**",
            f"- Average best-checkpoint to EOD fade: **{float(profit_fade.get('avg_checkpoint_to_eod_fade_pct') or 0):.4f}%p**",
            "",
            "| Fixed horizon | Result |",
            "|---|---|",
        ]
    )
    for horizon, metrics in _mapping(profit_fade.get("fixed_horizon_comparison")).items():
        lines.append(f"| `{horizon}` | {_metric_cell(metrics)} |")
    lines.extend(["", "### Profit-Lock Proxies", ""])
    for raw in profit_fade.get("profit_lock_proxies") or []:
        row = _mapping(raw)
        lines.append(
            f"- `{row.get('policy_id')}`: triggered {int(row.get('triggered_count') or 0)}, "
            f"{_metric_cell(row.get('metrics'))}"
        )
    lines.extend(
        [
            "",
            "Profit-lock values are optimistic observational proxies, not executable backtests.",
            "",
            "## Scanner Diagnostics",
            "",
            "| Horizon | Total-score correlation |",
            "|---|---:|",
        ]
    )
    for horizon, value in _mapping(scanner.get("score_return_correlation")).items():
        lines.append(f"| `{horizon}` | {float(value):.4f} |" if value is not None else f"| `{horizon}` | - |")
    lines.extend(
        [
            "",
            "### Candidate Setup",
            "",
            "| Setup | N | +15m | +30m | EOD |",
            "|---|---:|---|---|---|",
        ]
    )
    for raw in scanner.get("by_candidate_setup") or []:
        row = _mapping(raw)
        horizons = _mapping(row.get("horizons"))
        lines.append(
            "| `{}` | {} | {} | {} | {} |".format(
                row.get("value"),
                int(row.get("sample_count") or 0),
                _metric_cell(horizons.get("+15m")),
                _metric_cell(horizons.get("+30m")),
                _metric_cell(horizons.get("EOD")),
            )
        )
    market_coverage = _mapping(scanner.get("market_snapshot_coverage"))
    market_coverage_value = float(market_coverage.get("coverage") or 0)
    lines.extend(
        [
            "",
            f"- Point-in-time market snapshot coverage: **{market_coverage_value * 100:.1f}%**",
            f"- Fresh within 300 seconds: **{float(market_coverage.get('fresh_coverage') or 0) * 100:.1f}%**",
            (
                "- Promotion evidence gate: **BLOCKED_BY_MARKET_SNAPSHOT_COVERAGE**"
                if market_coverage_value < 0.8
                else "- Promotion evidence gate: **MARKET_SNAPSHOT_COVERAGE_OK**"
            ),
            "",
            "## Strategist Stage-2 ROI",
            "",
            f"- Official ranking overlay: `{_mapping(strategist.get('official_ranking_overlay')).get('state') or 'NOT_MEASURABLE'}`",
            f"- Official post-Scanner refresh: `{_mapping(strategist.get('official_post_scanner_refresh')).get('state') or 'NOT_MEASURABLE'}`",
            "- The table below is observational and does not authorize removal of Stage-2 authority.",
            "",
            "| Dimension | Value | Episodes | +30m | EOD |",
            "|---|---|---:|---|---|",
        ]
    )
    for raw in strategist.get("observational_splits") or []:
        row = _mapping(raw)
        horizons = _mapping(row.get("horizons"))
        lines.append(
            "| `{}` | `{}` | {} | {} | {} |".format(
                row.get("dimension"),
                row.get("value"),
                int(row.get("episode_count") or 0),
                _metric_cell(horizons.get("+30m")),
                _metric_cell(horizons.get("EOD")),
            )
        )
    lines.extend(
        [
            "",
            "## Decision Boundary",
            "",
            "- No Scanner, Strategist, Monitor, Commander, or execution behavior changed.",
            "- `HIGH_COMMON_SHORT_ALPHA_V1` is a fixed prospective shadow only.",
            "- Market snapshot coverage below 80% blocks promotion, regardless of historical return.",
            "- Profit-lock proxies cannot be promoted without minute-path execution simulation.",
            "- Stage-2 authority removal remains a separate single behavior patch candidate.",
            "",
        ]
    )
    return "\n".join(lines)
