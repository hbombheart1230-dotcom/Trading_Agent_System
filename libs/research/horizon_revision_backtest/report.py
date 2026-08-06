from __future__ import annotations

from typing import Any, Mapping


def _metric_row(label: str, metrics: Mapping[str, Any]) -> str:
    return (
        f"| {label} | {metrics.get('count', 0)} | {float(metrics.get('win_rate') or 0):.1%} | "
        f"{float(metrics.get('average_return_pct') or 0):.4f}% | "
        f"{metrics.get('profit_factor', 0)} | {float(metrics.get('maximum_drawdown_pct') or 0):.4f}% |"
    )


def render_report(payload: Mapping[str, Any], *, start_day: str, end_day: str) -> str:
    coverage = payload.get("coverage") or {}
    costs = payload.get("cost_bases") or {}
    lines = [
        f"# Horizon Revision Historical Comparison ({start_day} ~ {end_day})",
        "",
        "This is an offline comparison. It does not modify entry or exit behavior.",
        "",
        "## Evidence Coverage",
        "",
        f"- trade models: {coverage.get('trade_model_count', 0)}",
        f"- price-comparable trades: {coverage.get('price_comparable_trade_count', 0)}",
        f"- Stage 3 calls/days: {coverage.get('stage3_call_count', 0)} / {coverage.get('stage3_day_count', 0)}",
        f"- Stage 4 calls/days: {coverage.get('stage4_call_count', 0)} / {coverage.get('stage4_day_count', 0)}",
        f"- live total drag: {float(costs.get('live_total_drag_pct') or 0):.4f}%",
        f"- mock total drag: {float(costs.get('mock_total_drag_pct') or 0):.4f}%",
        "",
        "| Checkpoint | Observed |",
        "|---|---:|",
    ]
    for label, count in (coverage.get("checkpoint_observed") or {}).items():
        lines.append(f"| {label} | {count} |")
    lines += [
        "",
        "## Historical Broker-Realized Baseline",
        "",
        "This row uses the broker-realized return stored in the trade artifact, including the mock-account cost basis.",
        "",
        "| Scenario | N | Win Rate | Avg Net | PF | MDD |",
        "|---|---:|---:|---:|---:|---:|",
        _metric_row("broker_realized", payload.get("broker_realized_performance") or {}),
        "",
        "## All Trade Checkpoints: Live-Cost Basis",
        "",
        "| Scenario | N | Win Rate | Avg Net | PF | MDD |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("live_cost_scenarios") or []:
        lines.append(_metric_row(str(row.get("checkpoint")), row))
    lines += [
        "",
        "## All Trade Checkpoints: Mock-Cost Basis",
        "",
        "| Scenario | N | Win Rate | Avg Net | PF | MDD |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("mock_cost_scenarios") or []:
        lines.append(_metric_row(str(row.get("checkpoint")), row))
    lines += [
        "",
        "## Entry Horizon Extension Proxy: Live-Cost Basis",
        "",
        "The proxy checkpoint is measured after the actual exit. It tests whether the exit was early; it is not an exact replay of the new Stage 3 policy.",
        "",
        "| Entry Horizon | Proxy | Trades/Observed | Coverage | Actual Avg | Proxy Avg | Delta | Better/Worse | Loss->Win / Win->Loss |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("live_horizon_extension_proxy") or []:
        actual = row.get("comparable_actual") or {}
        proxy = row.get("extension_proxy") or {}
        delta = row.get("average_delta_pct")
        lines.append(
            f"| {row.get('entry_horizon')} | {row.get('proxy_checkpoint_after_actual_exit') or '-'} | "
            f"{row.get('trade_count')}/{row.get('proxy_observed_count')} | {float(row.get('coverage') or 0):.1%} | "
            f"{float(actual.get('average_return_pct') or 0):.4f}% | "
            f"{float(proxy.get('average_return_pct') or 0):.4f}% | "
            f"{float(delta or 0):+.4f}% | {row.get('improved_count')}/{row.get('worsened_count')} | "
            f"{row.get('loss_to_win_count')}/{row.get('win_to_loss_count')} |"
        )
    lines += [
        "",
        "## Entry Horizon Extension Proxy: Mock-Cost Basis",
        "",
        "| Entry Horizon | Proxy | Trades/Observed | Coverage | Actual Avg | Proxy Avg | Delta | Better/Worse | Loss->Win / Win->Loss |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("mock_horizon_extension_proxy") or []:
        actual = row.get("comparable_actual") or {}
        proxy = row.get("extension_proxy") or {}
        delta = row.get("average_delta_pct")
        lines.append(
            f"| {row.get('entry_horizon')} | {row.get('proxy_checkpoint_after_actual_exit') or '-'} | "
            f"{row.get('trade_count')}/{row.get('proxy_observed_count')} | {float(row.get('coverage') or 0):.1%} | "
            f"{float(actual.get('average_return_pct') or 0):.4f}% | "
            f"{float(proxy.get('average_return_pct') or 0):.4f}% | "
            f"{float(delta or 0):+.4f}% | {row.get('improved_count')}/{row.get('worsened_count')} | "
            f"{row.get('loss_to_win_count')}/{row.get('win_to_loss_count')} |"
        )
    lines += [
        "",
        "## In-Sample Oracle Upper Bound: Live-Cost Basis",
        "",
        "| Scenario | N | Win Rate | Avg Net | PF | MDD |",
        "|---|---:|---:|---:|---:|---:|",
        _metric_row("best stored checkpoint per trade", payload.get("oracle_upper_bound_live") or {}),
        "",
        "The oracle selects the best checkpoint after seeing the future. It measures available upside only and is not a deployable rule.",
        "",
        "## Interpretation Boundary",
        "",
        "- Actual exit is the historical baseline.",
        "- Extension checkpoints answer whether holding longer after the actual exit improved the result.",
        "- Oracle best is only an upper bound and must never be treated as a realizable strategy.",
        "- The new mutable horizon contract requires prospective Stage 3/4 decisions before causal performance can be measured.",
        "",
        "## Q16 Candidate Opportunity Reference",
        "",
    ]
    q16 = payload.get("q16_candidate_opportunity_reference") or {}
    lines += [
        f"- period: {q16.get('start_day')} ~ {q16.get('end_day')}",
        f"- evidence: `{q16.get('evidence_status') or 'unavailable'}`",
        f"- decision: `{q16.get('decision') or 'unavailable'}`",
        "- This is candidate opportunity evidence, not held-position horizon performance.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in payload.get("limitations") or [])
    return "\n".join(lines) + "\n"
