from __future__ import annotations

from typing import Any, Mapping


def _pct(value: Any) -> str:
    return "-" if value is None else f"{float(value):.4f}%"


def render_daily_report(
    *,
    day: str,
    decisions: Mapping[str, Any],
    forward: Mapping[str, Any],
) -> str:
    cost = forward.get("cost_model") or {}
    summary = forward.get("summary") or {}
    comparison = forward.get("q9_comparison") or {}
    lines = [
        "# Samsung Electronics / SK Hynix Baseline Daily Report",
        "",
        f"- Day: `{day}`",
        "- Mode: `shadow_only`",
        "- Universe: `005930.KS`, `000660.KS`",
        "- LLM / Strategist / Commander / execution: disabled",
        (
            f"- Cost model: {float(cost.get('round_trip_cost_pct') or 0):.4f}% "
            f"+ slippage {float(cost.get('slippage_pct') or 0):.4f}%"
        ),
        "",
        "## Decisions",
        "",
        "| Time | Rank | Symbol | Action | Score | Momentum | Volume | Conditions |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for decision in decisions.get("decisions") or []:
        for row in decision.get("ranked_candidates") or []:
            features = row.get("features") or {}
            passed = sum(1 for value in (row.get("entry_conditions") or {}).values() if value)
            total = len(row.get("entry_conditions") or {})
            lines.append(
                f"| {decision.get('generated_at')} | {row.get('rank')} | "
                f"{row.get('ticker')} | {row.get('action')} | {float(row.get('score') or 0):.4f} | "
                f"{float(features.get('momentum_5m_pct') or 0):.4f}% | "
                f"{float(features.get('volume_ratio') or 0):.2f}x | {passed}/{total} |"
            )
    lines += [
        "",
        "## Forward Performance",
        "",
        "| Horizon | Shadow Trades | Top1 Obs | Top1 Win | Top1 Avg Net | PF | MDD | Both Avg Net | Top1-Both |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.get("horizons") or []:
        top1 = row.get("top1_net") or {}
        both = row.get("both_symbol_average_net") or {}
        lines.append(
            f"| {row.get('horizon')} | {row.get('trade_count')} | {top1.get('count')} | "
            f"{float(top1.get('win_rate') or 0):.1%} | "
            f"{float(top1.get('average_return_pct') or 0):.4f}% | "
            f"{top1.get('profit_factor')} | {float(top1.get('maximum_drawdown_pct') or 0):.4f}% | "
            f"{float(both.get('average_return_pct') or 0):.4f}% | "
            f"{float(row.get('top1_minus_both_average_net_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Comparison vs Q9 P/A/B/C",
        "",
        "| Role | Horizon | Q9 Count | Q9 Avg Net | Baseline Top1 Net | Delta |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in comparison.get("roles") or []:
        q9 = row.get("q9_net") or {}
        lines.append(
            f"| {row.get('role')} | {row.get('horizon')} | {q9.get('count')} | "
            f"{float(q9.get('average_return_pct') or 0):.4f}% | "
            f"{_pct(row.get('baseline_top1_net_expectancy_pct') if row.get('baseline_top1_count') else None)} | "
            f"{_pct(row.get('baseline_minus_q9_expectancy_pct'))} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- This is an independent control group and does not authorize trading-policy changes.",
        "- No orders are generated. All returns are hypothetical and cost/slippage adjusted.",
    ]
    return "\n".join(lines) + "\n"
