from __future__ import annotations

from typing import Any, Mapping

from .contracts import PERSISTENT_TREND_POLICY_ID, STRONG_BTC_POLICY_ID


def render_report(
    *,
    day: str,
    decisions: Mapping[str, Any],
    forward: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> str:
    cost = forward.get("cost_model") or {}
    fear_greed = decisions.get("crypto_fear_greed") if isinstance(decisions.get("crypto_fear_greed"), Mapping) else {}
    lines = [
        "# Q12 BTC / Woori Technology Investment Baseline",
        "",
        f"- Day: `{day}`",
        "- Mode: `shadow_only`",
        "- Target: `041190.KQ` Woori Technology Investment",
        "- Q9/Q10/main execution integration: none",
        "- OrderIntent / execution: disabled",
        f"- Decision policy: `{decisions.get('decision_policy_version') or 'legacy'}`",
        f"- Evidence status: `{forward.get('evidence_status')}`",
        (
            "- Crypto Fear & Greed: "
            f"`{fear_greed.get('value')}` / `{fear_greed.get('classification') or fear_greed.get('regime')}` "
            f"(available={bool(fear_greed.get('available'))}, effect=`observation_only`)"
        ),
        (
            f"- Cost: {float(cost.get('round_trip_cost_pct') or 0):.4f}% "
            f"+ slippage {float(cost.get('slippage_pct') or 0):.4f}%"
        ),
        "",
        "## Decisions",
        "",
        "| Time | Action | BTC 5m | BTC 15m | BTC 60m | BTC 24h | KRX Session | Regime | Recent trend | Trend score | BTC Sources | Woori Volume | Breakout | Trend | Conditions |",
        "|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in decisions.get("decisions") or []:
        btc = row.get("btc_signal") or {}
        recent_trend = (
            btc.get("recent_trend")
            if isinstance(btc.get("recent_trend"), Mapping)
            else {}
        )
        local = row.get("local_features") or {}
        conditions = row.get("entry_conditions") or {}
        lines.append(
            f"| {row.get('generated_at')} | {row.get('action')} | "
            f"{float(btc.get('momentum_5m_pct') or 0):.4f}% | "
            f"{float(btc.get('momentum_15m_pct') or 0):.4f}% | "
            f"{float(btc.get('momentum_60m_pct') or 0):.4f}% | "
            f"{float(btc.get('momentum_24h_pct') or 0):.4f}% | "
            f"{float(btc.get('momentum_since_krx_open_pct') or 0):.4f}% | "
            f"{btc.get('market_regime') or 'insufficient_evidence'} | "
            f"{recent_trend.get('state') or 'insufficient_evidence'} | "
            f"{float(recent_trend.get('trend_score') or 0):.3f} | "
            f"{btc.get('source_count') or 0} | "
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
        "## Strong BTC Rise Shadow Variant",
        "",
        "- Contract: BTC strong-bull regime (60m >= 1.0% or 24h >= 3.0%) plus positive leading signal and Woori local confirmation.",
        "- This is an additive shadow comparison. The existing Q12 series is not overwritten.",
        "",
        "| Horizon | Trades | Win Rate | Avg Net | Profit Factor | Max Drawdown |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    variant = (forward.get("policy_variant_summaries") or {}).get(
        STRONG_BTC_POLICY_ID
    ) or {}
    for row in variant.get("horizons") or []:
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
        "## Persistent BTC Trend Shadow Variant",
        "",
        "- Contract: strong BTC rise plus persistent/accelerating recent trend and Woori local confirmation.",
        "- Prospective evidence starts on `2026-08-26`; earlier regenerated rows are historical reconstruction only.",
        "- Recent trend score uses multi-horizon alignment, positive 5m persistence, acceleration, and drawdown from recent highs; realized volatility is recorded as separate observation evidence.",
        "- This is additive observation only and cannot create an order.",
        "",
        "| Horizon | Trades | Win Rate | Avg Net | Profit Factor | Max Drawdown |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    persistent_variant = (forward.get("policy_variant_summaries") or {}).get(
        PERSISTENT_TREND_POLICY_ID
    ) or {}
    for row in persistent_variant.get("horizons") or []:
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
