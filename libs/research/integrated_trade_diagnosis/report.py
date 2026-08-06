from __future__ import annotations

from typing import Any, Mapping


def _pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.4f}%"


def _metric_table(title: str, groups: Mapping[str, Any]) -> list[str]:
    lines = [f"## {title}", "", "| Policy | N | Win | Avg | PF | MDD |", "|---|---:|---:|---:|---:|---:|"]
    for name, payload in groups.items():
        metrics = payload.get("performance", payload) if isinstance(payload, Mapping) else {}
        lines.append(
            "| {name} | {n} | {win} | {avg} | {pf} | {mdd} |".format(
                name=name,
                n=metrics.get("trade_count", 0),
                win=_pct(
                    float(metrics["win_rate"]) * 100
                    if metrics.get("win_rate") is not None
                    else None
                ),
                avg=_pct(metrics.get("average_return_pct")),
                pf=metrics.get("profit_factor", "N/A"),
                mdd=_pct(metrics.get("max_drawdown_pct")),
            )
        )
    return lines


def render(payload: Mapping[str, Any]) -> str:
    coverage = payload.get("evidence_coverage") or {}
    lines = [
        "# Integrated Trade Diagnosis",
        "",
        "> Offline reconstruction only. No trading behavior was changed.",
        "",
        "## Evidence Coverage",
        "",
        f"- Trade rows: {coverage.get('trade_row_count', 0)}",
        f"- Symbol-day sequences: {coverage.get('symbol_day_sequence_count', 0)}",
        f"- Opening decisions: {coverage.get('opening_decision_count', 0)}",
        f"- Exact lineage: {coverage.get('exact_lineage_count', 0)}",
        f"- Inferred/unknown lineage: {coverage.get('non_exact_lineage_count', 0)}",
        "",
    ]
    opening = payload.get("opening_policies") or {}
    lines.extend(_metric_table("Opening 09:00-09:30 Shadow", opening))
    lines.extend(["", "Policy rules use only fields available at decision time.", ""])
    lines.extend(_metric_table("Same-Symbol Reentry Shadow", payload.get("reentry_policies") or {}))
    horizon = payload.get("horizon_policies") or {}
    lines.extend(
        [
            "",
            "## Horizon and Exit",
            "",
            f"- Horizon contracts available: {horizon.get('horizon_contract_available_count', 0)}",
            f"- Violation candidates: {horizon.get('violation_candidate_count', 0)}",
            f"- Persisted target-hold improvements: {horizon.get('target_hold_improvement_count', 0)}",
            f"- Counterfactual status: {horizon.get('policy_counterfactual_status')}",
            "",
            "## D+1 to D+5 Reactivation",
            "",
        ]
    )
    for label, summary in (payload.get("reactivation") or {}).get("labels", {}).items():
        lines.append(
            f"- {label}: {summary.get('count', 0)} cases, "
            f"D5 close avg {_pct((summary.get('d5_close') or {}).get('average_return_pct'))}"
        )
    decision = payload.get("decision_readiness") or {}
    lines.extend(
        [
            "",
            "## Decision Readiness",
            "",
            f"- Status: **{decision.get('status')}**",
            f"- Leading candidate: **{decision.get('leading_candidate')}**",
            f"- Reason: {decision.get('reason')}",
            "",
            "## Prospective Runtime Gate",
            "",
            "Run for three full trading days without behavior changes. Require exact stage lineage, "
            "forward observations, sequence rows, and all four shadow sections. Missing historical "
            "fields remain INSUFFICIENT_EVIDENCE and are not inferred.",
            "",
        ]
    )
    return "\n".join(lines)
