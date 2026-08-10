from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import HORIZONS


def _checkpoint(row: Mapping[str, Any], horizon: str) -> Mapping[str, Any]:
    outcome = row.get("shadow_forward_outcome")
    outcome = outcome if isinstance(outcome, Mapping) else {}
    points = outcome.get("checkpoints")
    points = points if isinstance(points, Mapping) else {}
    value = points.get(horizon)
    return value if isinstance(value, Mapping) else {}


def _metric_rows(
    episodes: list[Mapping[str, Any]], cost_bases: Mapping[str, Any], *, unit: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in episodes:
        grouped[str(row.get("blocker_family") or "OTHER")].append(row)
    drags = {
        "gross": 0.0,
        "live_net": float((cost_bases.get("live_deployment_equity") or {}).get("total_drag_with_slippage_pct") or 0.0),
        "mock_net": float((cost_bases.get("mock_observed") or {}).get("total_drag_with_slippage_pct") or 0.0),
    }
    result = []
    for blocker, rows in sorted(grouped.items()):
        for horizon in HORIZONS:
            gross = [
                float(_checkpoint(row, horizon).get("return_pct"))
                for row in rows
                if _checkpoint(row, horizon).get("status") == "observed"
            ]
            result.append({
                "blocker_family": blocker,
                "evaluation_unit": unit,
                "horizon": horizon,
                "episode_count": len(rows),
                "observed_count": len(gross),
                "gross": performance_metrics(gross),
                "live_net": performance_metrics(value - drags["live_net"] for value in gross),
                "mock_net": performance_metrics(value - drags["mock_net"] for value in gross),
                "average_mfe_pct": round(sum(float(_checkpoint(row, horizon).get("mfe_pct") or 0.0) for row in rows if _checkpoint(row, horizon).get("status") == "observed") / len(gross), 4) if gross else None,
                "average_mae_pct": round(sum(float(_checkpoint(row, horizon).get("mae_pct") or 0.0) for row in rows if _checkpoint(row, horizon).get("status") == "observed") / len(gross), 4) if gross else None,
            })
    return result


def _first_day_symbol(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(episodes, key=lambda item: int(item.get("first_decision_epoch") or 0)):
        key = (
            str(row.get("day") or ""),
            str(row.get("symbol") or ""),
            str(row.get("blocker_family") or "OTHER"),
        )
        selected.setdefault(key, row)
    return list(selected.values())


def _decision(metrics: list[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = []
    for row in metrics:
        if row.get("evaluation_unit") != "first_day_symbol" or row.get("horizon") != "+30m":
            continue
        live = row.get("live_net") if isinstance(row.get("live_net"), Mapping) else {}
        if (
            int(row.get("observed_count") or 0) >= 12
            and float(live.get("average_return_pct") or 0.0) > 0.0
            and float(live.get("profit_factor") or 0.0) >= 1.2
            and float(live.get("win_rate") or 0.0) >= 0.45
        ):
            candidates.append(str(row.get("blocker_family") or ""))
    return {
        "decision": "RETAIN_CURRENT_MONITOR_GATES" if not candidates else "REVIEW_SINGLE_RELAXATION_CANDIDATE",
        "eligible_relaxation_candidates": candidates,
        "criteria": {
            "horizon": "+30m",
            "evaluation_unit": "first_day_symbol",
            "minimum_observed_count": 12,
            "minimum_live_net_expectancy_pct": "greater_than_0",
            "minimum_live_net_profit_factor": 1.2,
            "minimum_live_net_win_rate": 0.45,
        },
        "behavior_change_authorized": False,
    }


def build_report_payload(
    *, start: str, end: str, cycles: list[Mapping[str, Any]], episodes: list[dict[str, Any]], cost_bases: Mapping[str, Any], candle_meta: Mapping[str, Any]
) -> dict[str, Any]:
    observed = sum(bool((row.get("shadow_forward_outcome") or {}).get("available")) for row in episodes)
    metrics = _metric_rows(episodes, cost_bases, unit="episode") + _metric_rows(
        _first_day_symbol(episodes), cost_bases, unit="first_day_symbol"
    )
    return {
        "schema_version": "monitor_noop_attribution.v1",
        "behavior_effect": "observation_only",
        "range": {"start": start, "end": end},
        "episode_contract": {
            "cohort": "commander_approve_and_monitor_noop_regular_session",
            "representative_time": "first_decision_in_episode",
            "dedupe": "same_day_symbol_blocker_family_contiguous_within_300_seconds",
        },
        "cycle_count": len(cycles),
        "episode_count": len(episodes),
        "forward_available_count": observed,
        "forward_coverage": round(observed / len(episodes), 4) if episodes else 0.0,
        "evidence_status": "READY" if episodes and observed / len(episodes) >= 0.8 else "INSUFFICIENT_EVIDENCE",
        "cost_bases": dict(cost_bases),
        "candle_provider": dict(candle_meta),
        "metrics": metrics,
        "decision": _decision(metrics),
        "episodes": episodes,
        "policy_change_authorized": False,
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") or {}
    lines = [
        "# Monitor NOOP Opportunity Attribution",
        "",
        f"- Range: `{date_range.get('start')}` through `{date_range.get('end')}`",
        f"- Evidence: **{payload.get('evidence_status')}**",
        f"- Raw cycles: {payload.get('cycle_count', 0)}",
        f"- Independent episodes: {payload.get('episode_count', 0)}",
        f"- Forward coverage: {float(payload.get('forward_coverage') or 0):.2%}",
        f"- Decision: **{(payload.get('decision') or {}).get('decision')}**",
        "- Trading behavior changed: **false**",
        "",
        "| Unit | Blocker | Horizon | Units/Observed | Gross Avg | Live Net Avg | Mock Net Avg | Live PF | MFE | MAE |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("metrics") or []:
        gross = row.get("gross") or {}
        live = row.get("live_net") or {}
        mock = row.get("mock_net") or {}
        lines.append(
            f"| {row.get('evaluation_unit')} | {row.get('blocker_family')} | {row.get('horizon')} | {row.get('episode_count')}/{row.get('observed_count')} | "
            f"{float(gross.get('average_return_pct') or 0):+.4f}% | {float(live.get('average_return_pct') or 0):+.4f}% | "
            f"{float(mock.get('average_return_pct') or 0):+.4f}% | {float(live.get('profit_factor') or 0):.4f} | "
            f"{row.get('average_mfe_pct') if row.get('average_mfe_pct') is not None else '-'} | "
            f"{row.get('average_mae_pct') if row.get('average_mae_pct') is not None else '-'} |"
        )
    lines += [
        "",
        "Live and mock cost bases are displayed separately. This report cannot authorize a policy change by itself.",
        "",
    ]
    return "\n".join(lines)


__all__ = ["build_report_payload", "render_markdown"]
