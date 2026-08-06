from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics


CHECKPOINTS = ("actual_exit", "+5m", "+15m", "+30m", "+60m", "EOD", "T+1", "T+2")
PROXY_BY_ENTRY_HORIZON = {
    "scalp": "+5m",
    "intraday": "+30m",
    "overnight_probe": "EOD",
    "1_2day_swing": "T+1",
}


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _checkpoint_map(row: Mapping[str, Any]) -> dict[str, Any]:
    recap = row.get("post_exit_recap")
    recap = recap if isinstance(recap, Mapping) else {}
    nested = recap.get("post_exit_shadow")
    nested = nested if isinstance(nested, Mapping) else {}
    checkpoints = nested.get("checkpoints") or recap.get("checkpoints")
    if isinstance(checkpoints, Mapping):
        return dict(checkpoints)
    evaluation = row.get("evaluation")
    evaluation = evaluation if isinstance(evaluation, Mapping) else {}
    quality = evaluation.get("exit_quality")
    quality = quality if isinstance(quality, Mapping) else {}
    checkpoints = quality.get("observed_checkpoints")
    return dict(checkpoints) if isinstance(checkpoints, Mapping) else {}


def build_trade_scenarios(
    observations: list[dict[str, Any]],
    *,
    live_cost_pct: float,
    mock_cost_pct: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in observations:
        model = source.get("model") or {}
        entry = model.get("entry") or {}
        exit_data = model.get("exit") or {}
        outcome = model.get("outcome") or {}
        contract = model.get("horizon_contract") or {}
        entry_price = _number(entry.get("price"))
        exit_price = _number(exit_data.get("price"))
        if not entry_price or entry_price <= 0 or not exit_price or exit_price <= 0:
            continue
        prices: dict[str, float] = {"actual_exit": exit_price}
        for label, checkpoint in _checkpoint_map(source).items():
            if not isinstance(checkpoint, Mapping) or checkpoint.get("status") != "observed":
                continue
            price = _number(checkpoint.get("price") or checkpoint.get("observed_price"))
            if price and price > 0:
                prices[str(label)] = price
        scenario_returns = {}
        for label in CHECKPOINTS:
            price = prices.get(label)
            if price is None:
                continue
            gross = ((price / entry_price) - 1.0) * 100.0
            scenario_returns[label] = {
                "price": price,
                "gross_return_pct": round(gross, 4),
                "live_net_return_pct": round(gross - live_cost_pct, 4),
                "mock_net_return_pct": round(gross - mock_cost_pct, 4),
            }
        entry_horizon = str(contract.get("strategy_horizon") or "unknown")
        proxy_label = PROXY_BY_ENTRY_HORIZON.get(entry_horizon, "")
        realized_net = _number(outcome.get("net_return_pct"))
        available_live = {
            label: values["live_net_return_pct"] for label, values in scenario_returns.items()
        }
        oracle_label = max(available_live, key=available_live.get) if available_live else ""
        rows.append(
            {
                "trade_id": source.get("trade_id"),
                "day": source.get("day"),
                "symbol": source.get("symbol"),
                "entry_horizon": entry_horizon,
                "holding_seconds": _number(outcome.get("holding_seconds")),
                "exit_reason": str(exit_data.get("reason") or ""),
                "broker_realized_net_return_pct": realized_net,
                "scenario_returns": scenario_returns,
                "horizon_extension_proxy": proxy_label,
                "horizon_extension_proxy_available": proxy_label in scenario_returns,
                "oracle_best_label": oracle_label,
                "oracle_best_live_net_return_pct": available_live.get(oracle_label),
            }
        )
    return rows


def _scenario_metrics(rows: list[dict[str, Any]], *, cost_basis: str) -> list[dict[str, Any]]:
    output = []
    key = f"{cost_basis}_net_return_pct"
    for label in CHECKPOINTS:
        values = [
            float(row["scenario_returns"][label][key])
            for row in rows
            if label in row.get("scenario_returns", {})
        ]
        output.append({"checkpoint": label, **performance_metrics(values)})
    return output


def _grouped_proxy(rows: list[dict[str, Any]], *, cost_basis: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("entry_horizon") or "unknown")].append(row)
    result = []
    key = f"{cost_basis}_net_return_pct"
    for horizon, members in sorted(grouped.items()):
        proxy = PROXY_BY_ENTRY_HORIZON.get(horizon, "")
        actual = [
            float(row["scenario_returns"]["actual_exit"][key])
            for row in members
            if "actual_exit" in row.get("scenario_returns", {})
        ]
        extended = [
            float(row["scenario_returns"][proxy][key])
            for row in members
            if proxy and proxy in row.get("scenario_returns", {})
        ]
        actual_comparable = [
            float(row["scenario_returns"]["actual_exit"][key])
            for row in members
            if proxy and proxy in row.get("scenario_returns", {})
        ]
        paired = [
            (
                float(row["scenario_returns"]["actual_exit"][key]),
                float(row["scenario_returns"][proxy][key]),
            )
            for row in members
            if proxy and proxy in row.get("scenario_returns", {})
        ]
        result.append(
            {
                "entry_horizon": horizon,
                "proxy_checkpoint_after_actual_exit": proxy,
                "trade_count": len(members),
                "proxy_observed_count": len(extended),
                "coverage": round(len(extended) / len(members), 4) if members else 0.0,
                "all_actual": performance_metrics(actual),
                "comparable_actual": performance_metrics(actual_comparable),
                "extension_proxy": performance_metrics(extended),
                "average_delta_pct": round(
                    performance_metrics(extended)["average_return_pct"]
                    - performance_metrics(actual_comparable)["average_return_pct"],
                    4,
                )
                if extended
                else None,
                "improved_count": sum(extended_value > actual_value for actual_value, extended_value in paired),
                "worsened_count": sum(extended_value < actual_value for actual_value, extended_value in paired),
                "loss_to_win_count": sum(
                    actual_value <= 0 < extended_value for actual_value, extended_value in paired
                ),
                "win_to_loss_count": sum(
                    actual_value > 0 >= extended_value for actual_value, extended_value in paired
                ),
            }
        )
    return result


def analyze_horizon_revision(
    observations: list[dict[str, Any]],
    *,
    live_cost_pct: float,
    mock_cost_pct: float,
    stage_inventory: Mapping[str, Any],
    q16_review: Mapping[str, Any],
) -> dict[str, Any]:
    rows = build_trade_scenarios(
        observations,
        live_cost_pct=live_cost_pct,
        mock_cost_pct=mock_cost_pct,
    )
    broker_values = [
        float(row["broker_realized_net_return_pct"])
        for row in rows
        if row.get("broker_realized_net_return_pct") is not None
    ]
    oracle_values = [
        float(row["oracle_best_live_net_return_pct"])
        for row in rows
        if row.get("oracle_best_live_net_return_pct") is not None
    ]
    return {
        "schema_version": "horizon_revision_historical_comparison.v1",
        "behavior_effect": "offline_evaluation_only",
        "cost_bases": {
            "live_total_drag_pct": live_cost_pct,
            "mock_total_drag_pct": mock_cost_pct,
        },
        "coverage": {
            "trade_model_count": len(observations),
            "price_comparable_trade_count": len(rows),
            "checkpoint_observed": {
                label: sum(label in row.get("scenario_returns", {}) for row in rows)
                for label in CHECKPOINTS
            },
            **dict(stage_inventory),
        },
        "broker_realized_performance": performance_metrics(broker_values),
        "live_cost_scenarios": _scenario_metrics(rows, cost_basis="live"),
        "mock_cost_scenarios": _scenario_metrics(rows, cost_basis="mock"),
        "live_horizon_extension_proxy": _grouped_proxy(rows, cost_basis="live"),
        "mock_horizon_extension_proxy": _grouped_proxy(rows, cost_basis="mock"),
        "oracle_upper_bound_live": performance_metrics(oracle_values),
        "q16_candidate_opportunity_reference": {
            "source_schema": q16_review.get("schema_version"),
            "start_day": q16_review.get("start_day"),
            "end_day": q16_review.get("end_day"),
            "evidence_status": q16_review.get("evidence_status"),
            "decision": q16_review.get("decision"),
            "counts": q16_review.get("counts") or {},
            "horizons": q16_review.get("horizons") or [],
        },
        "limitations": [
            "Checkpoint scenarios extend from the actual exit, not from the original entry timestamp.",
            "The oracle row is an in-sample upper bound and is not a tradable policy.",
            "Historical Stage 3 outputs did not use the new revision contract, so the exact new adaptive policy cannot be replayed.",
            "EOD/T+1/T+2 are reported only when the stored post-exit artifact contains an observed price.",
        ],
        "trade_rows": rows,
    }
