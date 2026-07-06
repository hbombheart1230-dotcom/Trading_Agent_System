from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from .metrics import performance_metrics


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_key(evaluation: Mapping[str, Any]) -> tuple[str, str]:
    horizon = _mapping(evaluation.get("horizon_alignment"))
    exit_quality = _mapping(evaluation.get("exit_quality"))
    strategy_horizon = str(horizon.get("strategy_horizon") or "unknown")
    exit_reason = str(exit_quality.get("reason") or evaluation.get("exit_reason") or "unknown")
    return strategy_horizon, exit_reason


def build_horizon_compliance_report(
    evaluations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "returns": [],
            "before_min": 0,
            "before_target": 0,
            "beyond_max": 0,
            "target_improve": 0,
            "violation": 0,
            "hard_or_allowed": 0,
            "actual_hold_sec": [],
        }
    )
    horizon_counts: Counter[str] = Counter()
    for evaluation in evaluations:
        horizon = _mapping(evaluation.get("horizon_alignment"))
        outcome = _mapping(evaluation.get("realized_outcome"))
        strategy_horizon = str(horizon.get("strategy_horizon") or "unknown")
        exit_quality = _mapping(evaluation.get("exit_quality"))
        exit_reason = str(exit_quality.get("reason") or "unknown")
        actual_hold = _num(horizon.get("actual_hold_sec") or outcome.get("holding_seconds"))
        net_return = _num(outcome.get("net_return_pct"))
        row = {
            "trade_id": evaluation.get("trade_id"),
            "symbol": evaluation.get("symbol"),
            "strategy_horizon": strategy_horizon,
            "exit_reason": exit_reason,
            "bucket": str(horizon.get("bucket") or "unknown"),
            "actual_hold_sec": actual_hold,
            "expected_hold_window": _mapping(horizon.get("expected_hold_window")),
            "net_return_pct": net_return,
            "exited_before_min_hold": bool(horizon.get("exited_before_min_hold")),
            "exited_before_target_hold": bool(horizon.get("exited_before_target_hold")),
            "exited_beyond_max_hold": bool(horizon.get("exited_beyond_max_hold")),
            "horizon_violation_candidate": bool(horizon.get("horizon_violation_candidate")),
            "target_hold_would_improve_exit": bool(horizon.get("target_hold_would_improve_exit")),
            "valid_early_exit": bool(horizon.get("valid_early_exit")),
            "early_exit_allowed_match": list(horizon.get("early_exit_allowed_match") or []),
            "target_checkpoint": _mapping(horizon.get("target_checkpoint")),
            "max_post_exit_upside_pct": horizon.get("max_post_exit_upside_pct"),
            "max_post_exit_drawdown_pct": horizon.get("max_post_exit_drawdown_pct"),
        }
        rows.append(row)
        horizon_counts[strategy_horizon] += 1
        group = grouped[_bucket_key(evaluation)]
        group["count"] += 1
        if net_return is not None:
            group["returns"].append(float(net_return))
        if actual_hold is not None:
            group["actual_hold_sec"].append(float(actual_hold))
        if row["exited_before_min_hold"]:
            group["before_min"] += 1
        if row["exited_before_target_hold"]:
            group["before_target"] += 1
        if row["exited_beyond_max_hold"]:
            group["beyond_max"] += 1
        if row["target_hold_would_improve_exit"]:
            group["target_improve"] += 1
        if row["horizon_violation_candidate"]:
            group["violation"] += 1
        if row["valid_early_exit"] or row["early_exit_allowed_match"]:
            group["hard_or_allowed"] += 1

    group_rows: list[dict[str, Any]] = []
    for (strategy_horizon, exit_reason), group in sorted(grouped.items()):
        hold_values = group["actual_hold_sec"]
        metrics = performance_metrics(group["returns"])
        group_rows.append({
            "strategy_horizon": strategy_horizon,
            "exit_reason": exit_reason,
            "count": group["count"],
            "average_hold_sec": round(sum(hold_values) / len(hold_values), 2) if hold_values else None,
            "exit_before_min_hold_count": group["before_min"],
            "exit_before_target_hold_count": group["before_target"],
            "exit_beyond_max_hold_count": group["beyond_max"],
            "horizon_violation_candidate_count": group["violation"],
            "target_hold_would_improve_exit_count": group["target_improve"],
            "valid_or_allowed_early_exit_count": group["hard_or_allowed"],
            "performance": metrics,
        })

    return {
        "schema_version": "horizon_compliance_report.v1",
        "behavior_effect": "observation_only",
        "trade_count": len(rows),
        "horizon_counts": dict(horizon_counts),
        "group_rows": group_rows,
        "rows": rows,
        "policy_warning": (
            "Do not convert this into delayed exits directly. Promotion requires "
            "target-hold improvement by horizon and exit reason."
        ),
    }


def render_horizon_compliance_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Horizon Compliance Report",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Trades: {payload.get('trade_count', 0)}",
        f"- Policy warning: {payload.get('policy_warning', '')}",
        "",
        "## Horizon Counts",
        "",
    ]
    counts = _mapping(payload.get("horizon_counts"))
    if counts:
        for key in sorted(counts):
            lines.append(f"- `{key}`: {counts[key]}")
    else:
        lines.append("- No observed horizons.")
    lines.extend([
        "",
        "## By Horizon And Exit Reason",
        "",
        "| Horizon | Exit Reason | Count | Avg Hold Sec | Before Min | Before Target | Target Hold Better | Avg Return |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in payload.get("group_rows") or []:
        if not isinstance(row, Mapping):
            continue
        perf = _mapping(row.get("performance"))
        avg_return = perf.get("average_return_pct")
        lines.append(
            f"| {row.get('strategy_horizon')} | {row.get('exit_reason')} | "
            f"{row.get('count')} | {row.get('average_hold_sec')} | "
            f"{row.get('exit_before_min_hold_count')} | "
            f"{row.get('exit_before_target_hold_count')} | "
            f"{row.get('target_hold_would_improve_exit_count')} | "
            f"{'-' if avg_return is None else f'{float(avg_return):.4f}%'} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = ["build_horizon_compliance_report", "render_horizon_compliance_report"]
