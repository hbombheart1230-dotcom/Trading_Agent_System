from __future__ import annotations

from typing import Any, Mapping


def render_report(
    *,
    day: str,
    decisions: Mapping[str, Any],
    forward: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> str:
    cost = forward.get("cost_model") or {}
    lines = [
        "# Q12 BTC / Woori Technology Investment Baseline",
        "",
        f"- Day: `{day}`",
        "- Mode: `shadow_only`",
        "- Target: `041190.KQ` Woori Technology Investment",
        "- Q9/Q10/main execution integration: none",
        "- OrderIntent / execution: disabled",
        f"- Evidence status: `{forward.get('evidence_status')}`",
        (
            f"- Cost: {float(cost.get('round_trip_cost_pct') or 0):.4f}% "
            f"+ slippage {float(cost.get('slippage_pct') or 0):.4f}%"
        ),
        "",
        "## Decisions",
        "",
        "| Time | Action | BTC 5m | BTC Sources | Woori Volume | Breakout | Trend | Conditions |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in decisions.get("decisions") or []:
        btc = row.get("btc_signal") or {}
        local = row.get("local_features") or {}
        conditions = row.get("entry_conditions") or {}
        lines.append(
            f"| {row.get('generated_at')} | {row.get('action')} | "
            f"{float(btc.get('momentum_5m_pct') or 0):.4f}% | {btc.get('source_count') or 0} | "
            f"{float(local.get('volume_ratio') or 0):.2f}x | "
            f"{bool(local.get('breakout_confirmed'))} | "
            f"{bool(local.get('price_above_vwap_or_short_ma'))} | "
            f"{sum(bool(v) for v in conditions.values())}/{len(conditions)} |"
        )
    lines += [
        "",
        "## Forward Performance",
        "",
        "| Horizon | Trades | Win Rate | Avg Net | Profit Factor | Max Drawdown |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in (forward.get("summary") or {}).get("horizons") or []:
        metrics = row.get("eligible_entries_net") or {}
        lines.append(
            f"| {row.get('horizon')} | {metrics.get('count')} | "
            f"{float(metrics.get('win_rate') or 0):.1%} | "
            f"{float(metrics.get('average_return_pct') or 0):.4f}% | "
            f"{float(metrics.get('profit_factor') or 0):.4f} | "
            f"{float(metrics.get('maximum_drawdown_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Comparison",
        "",
        "| Horizon | Q12 | BTC Momentum Only | Woori Buy/Hold | Samsung/Hynix Top1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in comparison.get("horizons") or []:
        lines.append(
            f"| {row.get('horizon')} | "
            f"{float((row.get('q12_confirmed_entry') or {}).get('avg_return_pct') or 0):.4f}% | "
            f"{float((row.get('btc_momentum_only') or {}).get('avg_return_pct') or 0):.4f}% | "
            f"{float((row.get('woori_buy_and_hold') or {}).get('avg_return_pct') or 0):.4f}% | "
            f"{float((row.get('samsung_hynix_top1') or {}).get('avg_return_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Boundary",
        "",
        "- This module is an independent control group.",
        "- It cannot create OrderIntent or execute orders.",
        "- Results do not authorize Q9 or production strategy changes.",
    ]
    return "\n".join(lines) + "\n"

