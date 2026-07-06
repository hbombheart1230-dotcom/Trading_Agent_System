from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import HORIZONS


ROLE_LABELS = {
    "P_SCANNER_PRE_STRATEGIST_UNIVERSE": "Q9 P: Scanner Source Universe",
    "A_SCANNER_CONTROL": "Q9 A: Scanner Intrinsic Control",
    "B_STRATEGIST_RANKED": "Q9 B: Strategy-Weighted Scanner",
    "C_COMMANDER_FINAL": "Q9 C: Commander Approval/Veto Candidate",
    "BASELINE_TOP1": "Samsung/Hynix Baseline Top1",
}
Q9_ROLES = tuple(key for key in ROLE_LABELS if key != "BASELINE_TOP1")
PRIMARY_HORIZON = "+30m"


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trade_count": int(row.get("count") or 0),
        "win_rate": float(row.get("win_rate") or 0.0),
        "avg_return_pct": float(
            row.get("average_return_pct")
            if row.get("average_return_pct") is not None
            else row.get("expectancy_pct")
            or 0.0
        ),
        "profit_factor": float(row.get("profit_factor") or 0.0),
        "max_drawdown_pct": float(row.get("maximum_drawdown_pct") or 0.0),
    }


def _root_cause(
    *,
    baseline: Mapping[str, Any],
    role_metrics: Mapping[str, Mapping[str, Any]],
) -> str:
    commander = role_metrics.get("C_COMMANDER_FINAL") or {}
    if int(baseline.get("trade_count") or 0) <= 0 or int(commander.get("trade_count") or 0) <= 0:
        return "insufficient_comparable_forward_samples"
    baseline_avg = float(baseline.get("avg_return_pct") or 0.0)
    p = role_metrics.get("P_SCANNER_PRE_STRATEGIST_UNIVERSE") or {}
    b = role_metrics.get("B_STRATEGIST_RANKED") or {}
    c = commander
    p_avg = float(p.get("avg_return_pct") or 0.0)
    b_avg = float(b.get("avg_return_pct") or 0.0)
    c_avg = float(c.get("avg_return_pct") or 0.0)
    if int(p.get("trade_count") or 0) > 0 and p_avg <= baseline_avg:
        return "scanner_candidate_set_or_intrinsic_ranking_underperformed_fixed_baseline"
    if int(b.get("trade_count") or 0) > 0 and b_avg < p_avg:
        return "strategy_weighting_degraded_scanner_intrinsic_edge"
    if int(c.get("trade_count") or 0) > 0 and c_avg < b_avg:
        return "commander_approval_or_veto_candidate_degraded_strategy_weighted_edge"
    if c_avg <= baseline_avg:
        return "multi_agent_complexity_did_not_exceed_fixed_baseline"
    return ""


def build_unified_comparison(forward_payload: Mapping[str, Any]) -> dict[str, Any]:
    baseline_by_horizon = {
        str(row.get("horizon") or ""): _metrics(row.get("top1_net") or {})
        for row in (forward_payload.get("summary") or {}).get("horizons") or []
        if isinstance(row, Mapping)
    }
    q9_by_key = {
        (str(row.get("role") or ""), str(row.get("horizon") or "")): _metrics(
            row.get("q9_net") or {}
        )
        for row in (forward_payload.get("q9_comparison") or {}).get("roles") or []
        if isinstance(row, Mapping)
    }
    horizons: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        performers: list[dict[str, Any]] = []
        role_metrics: dict[str, dict[str, Any]] = {}
        for role in Q9_ROLES:
            metrics = q9_by_key.get((role, horizon), _metrics({}))
            role_metrics[role] = metrics
            performers.append({"performer": role, "label": ROLE_LABELS[role], **metrics})
        baseline = baseline_by_horizon.get(horizon, _metrics({}))
        performers.append(
            {
                "performer": "BASELINE_TOP1",
                "label": ROLE_LABELS["BASELINE_TOP1"],
                **baseline,
            }
        )
        comparable = [row for row in performers if int(row.get("trade_count") or 0) > 0]
        best = (
            max(
                comparable,
                key=lambda row: (
                    float(row.get("avg_return_pct") or 0.0),
                    float(row.get("profit_factor") or 0.0),
                    str(row.get("performer") or ""),
                ),
            )
            if comparable
            else None
        )
        commander = role_metrics["C_COMMANDER_FINAL"]
        comparable_alpha = bool(
            int(commander.get("trade_count") or 0) > 0
            and int(baseline.get("trade_count") or 0) > 0
        )
        alpha_pct = (
            round(
                float(commander.get("avg_return_pct") or 0.0)
                - float(baseline.get("avg_return_pct") or 0.0),
                4,
            )
            if comparable_alpha
            else None
        )
        adds_alpha = bool(alpha_pct is not None and alpha_pct > 0.0)
        horizons.append(
            {
                "horizon": horizon,
                "evidence_status": (
                    "COMPARABLE"
                    if comparable_alpha
                    else "INSUFFICIENT_EVIDENCE"
                ),
                "performers": performers,
                "best_performer": (
                    {
                        "performer": best.get("performer"),
                        "label": best.get("label"),
                        "avg_return_pct": best.get("avg_return_pct"),
                    }
                    if best
                    else None
                ),
                "multi_agent_alpha": {
                    "status": (
                        "ADDS_ALPHA"
                        if adds_alpha
                        else "NO_ALPHA"
                        if alpha_pct is not None
                        else "INSUFFICIENT_EVIDENCE"
                    ),
                    "commander_minus_baseline_pct": alpha_pct,
                    "adds_alpha": adds_alpha if alpha_pct is not None else None,
                    "root_cause": (
                        ""
                        if adds_alpha
                        else _root_cause(baseline=baseline, role_metrics=role_metrics)
                    ),
                },
            }
        )
    primary = next(row for row in horizons if row["horizon"] == PRIMARY_HORIZON)
    all_comparable = all(
        row.get("evidence_status") == "COMPARABLE"
        for row in horizons
    )
    return {
        "schema_version": "q9_baseline_unified_comparison.v1",
        "behavior_effect": "evaluation_only",
        "day": str(forward_payload.get("day") or ""),
        "metric_basis": (
            "cost-and-slippage-adjusted forward observations; trade_count is the "
            "number of observations used for each performer and horizon"
        ),
        "cost_model": dict(forward_payload.get("cost_model") or {}),
        "evidence_status": (
            "COMPLETE"
            if all_comparable
            else "INSUFFICIENT_EVIDENCE"
        ),
        "forward_windows_complete": all_comparable,
        "horizons": horizons,
        "overall": {
            "primary_horizon": PRIMARY_HORIZON,
            "best_performer": primary.get("best_performer"),
            "multi_agent_alpha": primary.get("multi_agent_alpha"),
        },
    }


def _pct(value: Any, *, ratio: bool = False) -> str:
    if value is None:
        return "-"
    return f"{float(value):.1%}" if ratio else f"{float(value):.4f}%"


def render_unified_comparison(payload: Mapping[str, Any]) -> str:
    overall = payload.get("overall") or {}
    alpha = overall.get("multi_agent_alpha") or {}
    best = overall.get("best_performer") or {}
    lines = [
        "# Q9 vs Samsung/Hynix Baseline Daily Comparison",
        "",
        f"- Day: `{payload.get('day')}`",
        f"- Primary horizon: `{overall.get('primary_horizon')}`",
        f"- Primary best performer: **{best.get('label') or '-'}**",
        f"- Multi-agent alpha status: **{alpha.get('status') or 'INSUFFICIENT_EVIDENCE'}**",
        f"- Commander minus baseline: {_pct(alpha.get('commander_minus_baseline_pct'))}",
        f"- Root cause: `{alpha.get('root_cause') or '-'}`",
        f"- Metric basis: {payload.get('metric_basis')}",
        "",
        "## Unified Metrics",
        "",
        "| Horizon | Performer | Trade Count | Win Rate | Avg Return | Profit Factor | Max Drawdown |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in payload.get("horizons") or []:
        for row in horizon.get("performers") or []:
            lines.append(
                f"| {horizon.get('horizon')} | {row.get('label')} | "
                f"{row.get('trade_count')} | {_pct(row.get('win_rate'), ratio=True)} | "
                f"{_pct(row.get('avg_return_pct'))} | "
                f"{float(row.get('profit_factor') or 0):.4f} | "
                f"{_pct(row.get('max_drawdown_pct'))} |"
            )
    lines += [
        "",
        "## Horizon Decisions",
        "",
        "| Horizon | Best Performer | Best Avg Return | Multi-Agent Alpha | Alpha vs Baseline | Root Cause |",
        "|---|---|---:|---|---:|---|",
    ]
    for horizon in payload.get("horizons") or []:
        best = horizon.get("best_performer") or {}
        alpha = horizon.get("multi_agent_alpha") or {}
        lines.append(
            f"| {horizon.get('horizon')} | {best.get('label') or '-'} | "
            f"{_pct(best.get('avg_return_pct'))} | {alpha.get('status')} | "
            f"{_pct(alpha.get('commander_minus_baseline_pct'))} | "
            f"`{alpha.get('root_cause') or '-'}` |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- Multi-agent alpha is measured as Q9 C Commander Approval/Veto Candidate average net return minus baseline Top1 average net return.",
        "- Q9 B is the Scanner ranking after strategy/tactic weighting; it is not an LLM-selected new universe.",
        "- Q9 C is the Commander approval/veto candidate; it is not a Commander-selected new universe.",
        "- Compare Q9 P/A against Q9 B/C separately to detect strategy-weighting degradation even when baseline alpha is positive.",
        "- P/A/B/C and baseline rows use the same broker cost and evaluation slippage assumptions.",
        "- `INSUFFICIENT_EVIDENCE` means one side has no comparable observation for that horizon.",
        "- This report is evaluation-only and does not authorize trading behavior changes.",
    ]
    return "\n".join(lines) + "\n"


def write_unified_comparison(
    *,
    forward_path: Path,
    output_dir: Path,
) -> dict[str, str]:
    forward_payload = _read(forward_path)
    payload = build_unified_comparison(forward_payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "q9_vs_samsung_hynix_daily_comparison.json"
    markdown_path = output_dir / "q9_vs_samsung_hynix_daily_comparison.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_unified_comparison(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


__all__ = [
    "build_unified_comparison",
    "render_unified_comparison",
    "write_unified_comparison",
]
