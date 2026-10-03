from __future__ import annotations

from statistics import median
from typing import Any, Mapping

from .contracts import SHADOW_ENTRY_POLICIES, THRESHOLDS


ENTRY_LABELS = {
    "ENTRY_0900": "09:00",
    "ENTRY_0903": "09:03",
    "ENTRY_0905": "09:05",
    "ENTRY_0910": "09:10",
}


def _direction(state: str) -> int:
    if state in {"STRONG_POSITIVE", "POSITIVE", "STRONG_RISK_ON", "RISK_ON"}:
        return 1
    if state in {"STRONG_NEGATIVE", "NEGATIVE", "STRONG_RISK_OFF", "RISK_OFF"}:
        return -1
    return 0


def _metric(values: list[float]) -> dict[str, Any]:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return {
        "trade_count": len(values),
        "win_rate": round(sum(value > 0 for value in values) / len(values) * 100.0, 4) if values else None,
        "average_return_pct": round(sum(values) / len(values), 6) if values else None,
        "median_return_pct": round(median(values), 6) if values else None,
        "profit_factor": round(gains / losses, 6) if losses else (None if not gains else "INF"),
        "max_drawdown_pct": round(drawdown, 6) if values else None,
    }


def _first_pullback_entry(reaction: Mapping[str, Any], direction: int) -> dict[str, Any] | None:
    path = list(reaction.get("path") or [])
    if not path or direction == 0:
        return None
    extreme = float(path[0].get("close") or 0.0)
    threshold = THRESHOLDS["pullback_retrace_pct"] / 100.0
    opening_epoch = int(path[0].get("ts") or 0)
    for row in path[1:]:
        if int(row.get("ts") or 0) > opening_epoch + 60 * 60:
            break
        price = float(row.get("close") or 0.0)
        if price <= 0:
            continue
        if direction > 0:
            extreme = max(extreme, price)
            triggered = price <= extreme * (1.0 - threshold)
        else:
            extreme = min(extreme, price)
            triggered = price >= extreme * (1.0 + threshold)
        if triggered:
            return {"ts": int(row.get("ts") or 0), "price": price}
    return None


def build_shadow_comparison(
    *, expected_actual: Mapping[str, Any], reactions: Mapping[str, Any], cost_pct: float, slippage_pct: float
) -> dict[str, Any]:
    actual_by_key = reactions.get("targets") or {}
    outcomes = []
    total_cost = float(cost_pct) + float(slippage_pct)
    for expected in expected_actual.get("rows") or []:
        key = str(expected.get("target") or "")
        state = str(expected.get("expected_state") or "NEUTRAL")
        direction = _direction(state)
        reaction = actual_by_key.get(key) or {}
        points = reaction.get("points") or {}
        close = (points.get("CLOSE") or {}).get("price")
        if direction == 0:
            continue
        entries: dict[str, Any] = {policy: points.get(label) for policy, label in ENTRY_LABELS.items()}
        entries["FIRST_PULLBACK_ENTRY"] = (
            _first_pullback_entry(reaction, direction)
            if expected.get("reaction_state") == "OVERREACTION"
            else None
        )
        path = list(reaction.get("path") or [])
        for policy in SHADOW_ENTRY_POLICIES:
            entry = entries.get(policy) or {}
            entry_price = entry.get("price")
            entry_ts = int(entry.get("ts") or 0)
            if entry_price in (None, 0) or close in (None, 0):
                outcomes.append({"target": key, "policy": policy, "status": "PENDING", "expected_state": state})
                continue
            future = [row for row in path if int(row.get("ts") or 0) >= entry_ts]
            prices = [float(row.get("close") or 0.0) for row in future if float(row.get("close") or 0.0) > 0]
            gross = direction * (float(close) / float(entry_price) - 1.0) * 100.0
            signed_moves = [direction * (price / float(entry_price) - 1.0) * 100.0 for price in prices]
            outcomes.append(
                {
                    "target": key,
                    "policy": policy,
                    "status": "OBSERVED",
                    "expected_state": state,
                    "reaction_state": expected.get("reaction_state"),
                    "evaluation_bucket": expected.get("evaluation_bucket"),
                    "extension_state": expected.get("extension_state"),
                    "entry_ts": entry_ts,
                    "entry_price": entry_price,
                    "exit_price": close,
                    "gross_eod_return_pct": round(gross, 6),
                    "net_eod_return_pct": round(gross - total_cost, 6),
                    "mfe_pct": round(max(signed_moves), 6) if signed_moves else None,
                    "mae_pct": round(min(signed_moves), 6) if signed_moves else None,
                }
            )
    summaries = []
    for key in actual_by_key:
        for policy in SHADOW_ENTRY_POLICIES:
            rows = [row for row in outcomes if row["target"] == key and row["policy"] == policy and row["status"] == "OBSERVED"]
            metrics = _metric([float(row["net_eod_return_pct"]) for row in rows])
            metrics.update(
                {
                    "target": key,
                    "policy": policy,
                    "average_mfe_pct": round(sum(float(row["mfe_pct"]) for row in rows) / len(rows), 6) if rows else None,
                    "average_mae_pct": round(sum(float(row["mae_pct"]) for row in rows) / len(rows), 6) if rows else None,
                    "average_eod_return_pct": metrics["average_return_pct"],
                }
            )
            summaries.append(metrics)
    return {
        "cost_model": {"round_trip_cost_pct": cost_pct, "slippage_pct": slippage_pct, "total_pct": total_cost},
        "outcomes": outcomes,
        "summary": summaries,
        "evidence_status": "AVAILABLE" if any(row["status"] == "OBSERVED" for row in outcomes) else "INSUFFICIENT_EVIDENCE",
    }
