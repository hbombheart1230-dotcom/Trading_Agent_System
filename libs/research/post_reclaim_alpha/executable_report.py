from __future__ import annotations

from typing import Any, Mapping


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def render_executable_policy_markdown(payload: Mapping[str, Any]) -> str:
    policy = payload.get("policy") or {}
    lines = [
        "# Post-Reclaim Executable Policy v0",
        "",
        f"- Decision: **{payload.get('decision', 'UNKNOWN')}**",
        "- Behavior effect: `research_only`",
        f"- Target: `{payload.get('target_subtype')}`",
        f"- Entry filter: {policy.get('entry_filter')}",
        f"- Exit: {policy.get('exit_rule')}",
        f"- Cost: **{_fmt(policy.get('cost_pct'), 6)}%**",
        "",
        "## Train / Validation",
        "",
        "| Split | Eligible | Observed | Coverage | Avg Net | PF | Win Rate | MDD | Positive Days | Bootstrap P10 / Median / P90 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name in ("train", "validation"):
        row = payload.get(name) or {}
        metrics = row.get("metrics") or {}
        bootstrap = row.get("bootstrap") or {}
        lines.append(
            "| {name} | {eligible} | {observed} | {coverage:.1%} | {avg}% | "
            "{pf} | {win:.2%} | {mdd}% | {days:.2%} | {p10}% / {median}% / "
            "{p90}% |".format(
                name=name.title(),
                eligible=row.get("eligible_count", 0),
                observed=row.get("observed_count", 0),
                coverage=float(row.get("coverage") or 0.0),
                avg=_fmt(metrics.get("expectancy_pct")),
                pf=_fmt(metrics.get("profit_factor")),
                win=float(metrics.get("win_rate") or 0.0),
                mdd=_fmt(metrics.get("maximum_drawdown_pct")),
                days=float(row.get("positive_day_ratio") or 0.0),
                p10=_fmt(bootstrap.get("p10_expectancy_pct")),
                median=_fmt(bootstrap.get("median_expectancy_pct")),
                p90=_fmt(bootstrap.get("p90_expectancy_pct")),
            )
        )
    lines.extend(
        [
            "",
            "## Filter Effect",
            "",
            "| Split | Population | Observed | Avg Net | PF | Win Rate |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for name in ("train", "validation"):
        for population, row in (
            ("Unfiltered", ((payload.get("unfiltered_comparison") or {}).get(name) or {})),
            ("Executable", payload.get(name) or {}),
        ):
            metrics = row.get("metrics") or {}
            lines.append(
                "| {split} | {population} | {count} | {avg}% | {pf} | "
                "{win:.2%} |".format(
                    split=name.title(),
                    population=population,
                    count=row.get("observed_count", 0),
                    avg=_fmt(metrics.get("expectancy_pct")),
                    pf=_fmt(metrics.get("profit_factor")),
                    win=float(metrics.get("win_rate") or 0.0),
                )
            )
    lines.extend(
        [
            "",
            "## Frozen Gates",
            "",
            "| Gate | Result |",
            "| --- | --- |",
        ]
    )
    for name, passed in (payload.get("gate_results") or {}).items():
        lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} |")
    failed = [
        name
        for name, passed in (payload.get("gate_results") or {}).items()
        if not passed
    ]
    lines.extend(
        [
            "",
            "## Final Interpretation",
            "",
            (
                "- The frozen executable policy passed every predeclared gate."
                if not failed
                else f"- Rejected by frozen gates: {', '.join(failed)}."
            ),
            "- No threshold grid or post-outcome parameter selection was used.",
            "- The liquidity filter uses only prints strictly before entry.",
            "- This result does not change live trading behavior.",
            "",
        ]
    )
    return "\n".join(lines)
