from __future__ import annotations

from typing import Any, Mapping, Sequence


def render_report(
    *,
    day: str,
    signals: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    data_quality: Mapping[str, Any],
) -> str:
    probes = [row for row in signals if bool((row.get("opportunity") or {}).get("probe_candidate"))]
    lines = [
        f"# Q11 Opening Surge & Market Reversal Shadow Report - {day}",
        "",
        "## Isolation",
        "",
        "- Behavior effect: `shadow_only`",
        "- Evaluation program: `Q11_OPENING_SURGE_MARKET_REVERSAL`",
        "- Research window: `09:00-10:00 KST`",
        "- Order execution: disabled",
        "- Q9 integration: none",
        "- Strategist / Commander / Monitor integration: none",
        "",
        "## Data Quality",
        "",
        f"- Symbols requested: {data_quality.get('symbol_count', 0)}",
        f"- Symbols with candles: {data_quality.get('symbols_with_candles', 0)}",
        f"- Candle rows: {data_quality.get('candle_row_count', 0)}",
        f"- Market snapshots: {data_quality.get('market_snapshot_count', 0)}",
        "",
        "## Shadow Results",
        "",
        f"- Signal rows: {len(signals)}",
        f"- Probe candidates: {len(probes)}",
        f"- Virtual trades: {summary.get('trade_count', 0)}",
        f"- Win rate: {summary.get('win_rate')}",
        f"- Average net return: {summary.get('average_net_return_pct')}",
        f"- Profit factor: {summary.get('profit_factor')}",
        f"- Average MFE: {summary.get('average_mfe_pct')}",
        f"- Average MAE: {summary.get('average_mae_pct')}",
        "",
        "## Probe Candidates",
        "",
        "| Time | Symbol | Score | Market state | 3m momentum | Relative strength | Robust volume | VWAP distance |",
        "|---:|---|---:|---|---:|---:|---:|---:|",
    ]
    for row in probes[:100]:
        market = row.get("market") or {}
        features = row.get("symbol_features") or {}
        opportunity = row.get("opportunity") or {}
        lines.append(
            f"| {row.get('as_of_epoch')} | {row.get('symbol')} | {float(opportunity.get('score') or 0.0):.4f} "
            f"| {market.get('state')} | {float(features.get('momentum_3m_pct') or 0.0):.4f}% "
            f"| {float(features.get('market_relative_strength_proxy_pct') or 0.0):.4f}% "
            f"| {float(features.get('robust_volume_ratio') or 0.0):.3f} "
            f"| {float(features.get('vwap_distance_pct') or 0.0):.4f}% |"
        )
    if not probes:
        lines.append("| - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "The `probe_v0` result is a research baseline, not an approved trading policy.",
            "Entry threshold, stop placement, hold time, and position sizing require",
            "out-of-sample comparison before promotion.",
            "",
        ]
    )
    return "\n".join(lines)
