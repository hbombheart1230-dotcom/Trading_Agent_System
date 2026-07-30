from __future__ import annotations

from typing import Any, Mapping


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Structural Alpha Batch 2",
        "",
        "- Behavior effect: `research_only`",
        f"- Range: `{payload['range']['start']}` to `{payload['range']['end']}`",
        f"- Live cost: **{_fmt(payload['cost_model']['live_cost_pct'], 6)}%**",
        "- July is retrospective screening, not an untouched final holdout.",
        "",
        "## Data Integrity",
        "",
        f"- Canonical decision windows: {payload['window_extraction']['canonical_window_count']}",
        f"- Historical symbols complete: {payload['provider_summary']['complete_symbol_count']}/{payload['provider_summary']['symbol_count']}",
        "",
        "## Result",
        "",
        "| Strategy | Calibration Obs/Coverage | Calibration Avg/PF | Retrospective Obs/Coverage | Retrospective Avg/PF | Win Rate | Positive Days | MDD | Decision |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for strategy_id, result in payload["results"].items():
        calibration = result["splits"]["calibration"]["+30m"]
        retrospective = result["splits"]["retrospective"]["+30m"]
        calibration_metrics = calibration["metrics"]
        retrospective_metrics = retrospective["metrics"]
        lines.append(
            "| {strategy} | {cobs}/{ccov:.1%} | {cavg}%/{cpf} | "
            "{robs}/{rcov:.1%} | {ravg}%/{rpf} | {win:.2%} | {days:.2%} | "
            "{mdd}% | {decision} |".format(
                strategy=strategy_id,
                cobs=calibration["observed_count"],
                ccov=float(calibration["coverage"]),
                cavg=_fmt(calibration_metrics.get("expectancy_pct")),
                cpf=_fmt(calibration_metrics.get("profit_factor")),
                robs=retrospective["observed_count"],
                rcov=float(retrospective["coverage"]),
                ravg=_fmt(retrospective_metrics.get("expectancy_pct")),
                rpf=_fmt(retrospective_metrics.get("profit_factor")),
                win=float(retrospective_metrics.get("win_rate") or 0.0),
                days=float(retrospective["positive_day_ratio"]),
                mdd=_fmt(retrospective_metrics.get("maximum_drawdown_pct")),
                decision=result["decision"],
            )
        )
    lines.extend(["", "## Gate Detail", ""])
    for strategy_id, result in payload["results"].items():
        lines.extend(
            [
                f"### {strategy_id}",
                "",
                "| Gate | Result |",
                "| --- | --- |",
            ]
        )
        for gate, passed in result["gate_results"].items():
            lines.append(f"| {gate} | {'PASS' if passed else 'FAIL'} |")
        lines.append("")
    lines.extend(
        [
            "## Boundary",
            "",
            "- Signals use only completed candles before each decision.",
            "- Entry uses the next available minute open.",
            "- No live or shadow behavior was changed.",
            "",
        ]
    )
    return "\n".join(lines)
