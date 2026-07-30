from __future__ import annotations

from typing import Any, Mapping


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def render_markdown(payload: Mapping[str, Any]) -> str:
    extraction = payload.get("episode_extraction") or {}
    decision = payload.get("promotion_decision") or {}
    lines = [
        "# Post-Reclaim Offline Alpha Research",
        "",
        f"- Range: `{payload.get('range', {}).get('start')}` to `{payload.get('range', {}).get('end')}`",
        "- Behavior effect: `research_only`",
        f"- Decision: **{decision.get('decision', 'UNKNOWN')}**",
        f"- Live cost: **{_fmt((payload.get('cost_model') or {}).get('live_cost_pct'), 6)}%**",
        f"- Mock cost: **{_fmt((payload.get('cost_model') or {}).get('mock_cost_pct'), 6)}%**",
        "",
        "## Episode Integrity",
        "",
        "| Measure | Value |",
        "| --- | ---: |",
        f"| Raw candidates | {extraction.get('raw_candidate_count', 0)} |",
        f"| Canonical candidates | {extraction.get('canonical_candidate_count', 0)} |",
        f"| Independent episodes | {extraction.get('episode_count', 0)} |",
        f"| Days | {extraction.get('episode_day_count', 0)} |",
        f"| Symbols | {extraction.get('episode_symbol_count', 0)} |",
        "",
        "## Horizon Performance",
        "",
        "| Horizon | Observed | Coverage | Gross Avg | Live Net Avg | Live PF | Live MDD | Avg MFE | Avg MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("horizon_summaries") or []:
        live = row.get("live_net") or {}
        gross = row.get("gross") or {}
        lines.append(
            "| {horizon} | {observed}/{episodes} | {coverage:.1%} | {gross}% | "
            "{live}% | {pf} | {mdd}% | {mfe}% | {mae}% |".format(
                horizon=row.get("horizon"),
                observed=row.get("observed_count", 0),
                episodes=row.get("episode_count", 0),
                coverage=float(row.get("coverage") or 0.0),
                gross=_fmt(gross.get("expectancy_pct")),
                live=_fmt(live.get("expectancy_pct")),
                pf=_fmt(live.get("profit_factor")),
                mdd=_fmt(live.get("maximum_drawdown_pct")),
                mfe=_fmt(row.get("average_mfe_pct")),
                mae=_fmt(row.get("average_mae_pct")),
            )
        )

    baseline = payload.get("scanner_rank1_baseline") or {}
    baseline30 = ((baseline.get("horizons") or {}).get("+30m") or {}).get("live_net") or {}
    post30 = next(
        (
            (row.get("live_net") or {})
            for row in payload.get("horizon_summaries") or []
            if row.get("horizon") == "+30m"
        ),
        {},
    )
    lines.extend(
        [
            "",
            "## Scanner Rank 1 Comparison",
            "",
            "| Population | Count | +30m Live Net | Profit Factor | Win Rate |",
            "| --- | ---: | ---: | ---: | ---: |",
            f"| Confirmed post-reclaim | {post30.get('count', 0)} | {_fmt(post30.get('expectancy_pct'))}% | {_fmt(post30.get('profit_factor'))} | {_fmt(float(post30.get('win_rate') or 0.0) * 100, 2)}% |",
            f"| Scanner Rank 1, same days | {baseline30.get('count', 0)} | {_fmt(baseline30.get('expectancy_pct'))}% | {_fmt(baseline30.get('profit_factor'))} | {_fmt(float(baseline30.get('win_rate') or 0.0) * 100, 2)}% |",
            "",
            "## Fixed Gates",
            "",
            "| Gate | Pass |",
            "| --- | --- |",
        ]
    )
    for name, passed in (decision.get("evidence_gates") or {}).items():
        lines.append(f"| evidence:{name} | {'PASS' if passed else 'FAIL'} |")
    for name, passed in (decision.get("performance_gates") or {}).items():
        lines.append(f"| performance:{name} | {'PASS' if passed else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This report reconstructs historical shadow episodes only.",
            "- It does not modify Scanner, Strategist, Commander, Monitor, orders, or execution.",
            "- The first qualifying observation in each 15-minute same-symbol episode is used.",
            "",
        ]
    )
    return "\n".join(lines)
