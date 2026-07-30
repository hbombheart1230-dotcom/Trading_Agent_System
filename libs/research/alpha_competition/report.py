from __future__ import annotations

from typing import Any, Mapping


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Alpha Hypothesis Competition v1",
        "",
        f"- Range: `{payload.get('range', {}).get('start')}` to `{payload.get('range', {}).get('end')}`",
        "- Behavior effect: `research_only`",
        f"- Live cost: **{_fmt((payload.get('cost_model') or {}).get('live_cost_pct'), 6)}%**",
        "- Primary decision horizon: `+30m`",
        "",
        "## Data Integrity",
        "",
        f"- Raw candidate rows: {(payload.get('candidate_extraction') or {}).get('raw_candidate_count', 0)}",
        f"- Canonical candidate rows: {(payload.get('candidate_extraction') or {}).get('canonical_candidate_count', 0)}",
        f"- Historical symbols: {(payload.get('provider_summary') or {}).get('symbol_count', 0)}",
        f"- Complete historical symbols: {(payload.get('provider_summary') or {}).get('complete_symbol_count', 0)}",
        "",
        "## Result",
        "",
        "| Hypothesis | Train Obs/Coverage | Train Avg | Train PF | Validation Obs/Coverage | Validation Avg | Validation PF | Validation Win | Positive Days | Validation MDD | Decision |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    results = payload.get("results") or {}
    for hypothesis_id, result in results.items():
        train = ((result.get("splits") or {}).get("train") or {}).get("+30m") or {}
        validation = (
            ((result.get("splits") or {}).get("validation") or {}).get("+30m")
            or {}
        )
        train_metrics = train.get("metrics") or {}
        validation_metrics = validation.get("metrics") or {}
        lines.append(
            "| {hypothesis} | {train_count}/{train_coverage:.1%} | "
            "{train_avg}% | {train_pf} | "
            "{validation_count}/{validation_coverage:.1%} | {validation_avg}% | "
            "{validation_pf} | {validation_win:.2%} | {positive_days:.2%} | "
            "{validation_mdd}% | {decision} |".format(
                hypothesis=hypothesis_id,
                train_count=train.get("observed_count", 0),
                train_coverage=float(train.get("coverage") or 0.0),
                train_avg=_fmt(train_metrics.get("expectancy_pct")),
                train_pf=_fmt(train_metrics.get("profit_factor")),
                validation_count=validation.get("observed_count", 0),
                validation_coverage=float(validation.get("coverage") or 0.0),
                validation_avg=_fmt(validation_metrics.get("expectancy_pct")),
                validation_pf=_fmt(validation_metrics.get("profit_factor")),
                validation_win=float(validation_metrics.get("win_rate") or 0.0),
                positive_days=float(validation.get("positive_day_ratio") or 0.0),
                validation_mdd=_fmt(
                    validation_metrics.get("maximum_drawdown_pct")
                ),
                decision=result.get("decision"),
            )
        )
    lines.extend(["", "## Gate Detail", ""])
    for hypothesis_id, result in results.items():
        lines.extend(
            [
                f"### {hypothesis_id}",
                "",
                "| Gate | Result |",
                "| --- | --- |",
            ]
        )
        for gate, passed in (result.get("gate_results") or {}).items():
            lines.append(f"| {gate} | {'PASS' if passed else 'FAIL'} |")
        lines.append("")
    eligible = [
        hypothesis_id
        for hypothesis_id, result in results.items()
        if result.get("decision") == "ELIGIBLE_FOR_SHADOW_INTEGRATION"
    ]
    lines.extend(
        [
            "## Final Decision",
            "",
            (
                f"- Shadow integration candidates: {', '.join(eligible)}"
                if eligible
                else "- No hypothesis is eligible for shadow integration."
            ),
            "- A rejected hypothesis is not extended automatically.",
            "- No live trading behavior was changed.",
            "",
            "## Boundary",
            "",
            "- This is a candidate-space study, not a whole-market backtest.",
            "- Signals use only fields present at the candidate timestamp.",
            "- Forward returns are reconstructed from Kiwoom historical minute data.",
            "",
        ]
    )
    return "\n".join(lines)
