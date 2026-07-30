from __future__ import annotations

from typing import Any, Mapping


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Structural Alpha Batch 1",
        "",
        "- Behavior effect: `research_only`",
        f"- Range: `{payload.get('range', {}).get('start')}` to `{payload.get('range', {}).get('end')}`",
        f"- Live cost: **{_fmt((payload.get('cost_model') or {}).get('live_cost_pct'), 6)}%**",
        "- July is retrospective screening, not an untouched final holdout.",
        "",
        "## Data Integrity",
        "",
        f"- Canonical decision windows: {(payload.get('window_extraction') or {}).get('canonical_window_count', 0)}",
        f"- Point-in-time universe symbols: {(payload.get('window_extraction') or {}).get('symbol_count', 0)}",
        f"- Historical symbols complete: {(payload.get('provider_summary') or {}).get('complete_symbol_count', 0)}/{(payload.get('provider_summary') or {}).get('symbol_count', 0)}",
        "",
        "## Result",
        "",
        "| Strategy | Calibration Obs/Coverage | Calibration Avg/PF | Retrospective Obs/Coverage | Retrospective Avg/PF | Win Rate | Positive Days | MDD | Decision |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for strategy_id, result in (payload.get("results") or {}).items():
        calibration = (
            ((result.get("splits") or {}).get("calibration") or {}).get("+30m")
            or {}
        )
        retrospective = (
            ((result.get("splits") or {}).get("retrospective") or {}).get("+30m")
            or {}
        )
        calibration_metrics = calibration.get("metrics") or {}
        retrospective_metrics = retrospective.get("metrics") or {}
        lines.append(
            "| {strategy} | {cobs}/{ccov:.1%} | {cavg}%/{cpf} | "
            "{robs}/{rcov:.1%} | {ravg}%/{rpf} | {win:.2%} | {days:.2%} | "
            "{mdd}% | {decision} |".format(
                strategy=strategy_id,
                cobs=calibration.get("observed_count", 0),
                ccov=float(calibration.get("coverage") or 0.0),
                cavg=_fmt(calibration_metrics.get("expectancy_pct")),
                cpf=_fmt(calibration_metrics.get("profit_factor")),
                robs=retrospective.get("observed_count", 0),
                rcov=float(retrospective.get("coverage") or 0.0),
                ravg=_fmt(retrospective_metrics.get("expectancy_pct")),
                rpf=_fmt(retrospective_metrics.get("profit_factor")),
                win=float(retrospective_metrics.get("win_rate") or 0.0),
                days=float(retrospective.get("positive_day_ratio") or 0.0),
                mdd=_fmt(retrospective_metrics.get("maximum_drawdown_pct")),
                decision=result.get("decision"),
            )
        )
    lines.extend(["", "## Gate Detail", ""])
    for strategy_id, result in (payload.get("results") or {}).items():
        lines.extend([f"### {strategy_id}", ""])
        if result.get("gate_results"):
            lines.extend(["| Gate | Result |", "| --- | --- |"])
            for gate, passed in result["gate_results"].items():
                lines.append(f"| {gate} | {'PASS' if passed else 'FAIL'} |")
        else:
            lines.append(f"- {result.get('reason') or result.get('decision')}")
        lines.append("")
    lines.extend(
        [
            "## Boundary",
            "",
            "- Signals use only completed candles before each decision.",
            "- Entry uses the next available minute open.",
            "- No current sector mapping was backfilled into historical dates.",
            "- No live or shadow behavior was changed.",
            "",
        ]
    )
    return "\n".join(lines)
