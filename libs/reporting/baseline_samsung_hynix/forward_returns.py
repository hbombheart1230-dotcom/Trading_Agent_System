from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes

from .contracts import HORIZONS


KST = timezone(timedelta(hours=9))


def decision_candidate_rows(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        for candidate in decision.get("ranked_candidates") or []:
            if not isinstance(candidate, Mapping):
                continue
            features = candidate.get("features")
            features = features if isinstance(features, Mapping) else {}
            rows.append(
                {
                    "symbol": candidate.get("symbol"),
                    "ticker": candidate.get("ticker"),
                    "rank": candidate.get("rank"),
                    "eligible": candidate.get("eligible"),
                    "action": candidate.get("action"),
                    "baseline_decision_id": decision.get("decision_id"),
                    "_payload_generated_at": decision.get("generated_at"),
                    "shadow_forward_base": {
                        "available": bool(features.get("available")),
                        "baseline_epoch": features.get("baseline_epoch"),
                        "baseline_price": features.get("baseline_price"),
                        "baseline_raw_ts": features.get("baseline_raw_ts"),
                        "source": "baseline_existing_candle_provider",
                    },
                }
            )
    return rows


def attach_baseline_forward_returns(
    decisions: list[dict[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    rows = attach_forward_outcomes(
        decision_candidate_rows(decisions),
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    output: list[dict[str, Any]] = []
    for row in rows:
        outcome = row.get("shadow_forward_outcome")
        outcome = outcome if isinstance(outcome, Mapping) else {}
        checkpoints = outcome.get("checkpoints")
        checkpoints = checkpoints if isinstance(checkpoints, Mapping) else {}
        selected_checkpoints = {
            horizon: dict(checkpoints.get(horizon) or {"status": "pending"})
            for horizon in HORIZONS
        }
        eod = selected_checkpoints["EOD"]
        symbol_rows = list(minute_rows_by_symbol.get(str(row.get("symbol") or "")) or [])
        same_day_rows = [
            candle
            for candle in symbol_rows
            if int(candle.get("ts") or 0) >= int(
                (row.get("shadow_forward_base") or {}).get("baseline_epoch") or 0
            )
        ]
        if eod.get("status") != "observed" and same_day_rows:
            last = same_day_rows[-1]
            last_epoch = int(last.get("ts") or 0)
            last_kst = datetime.fromtimestamp(last_epoch, tz=KST) if last_epoch > 0 else None
            if last_kst and (last_kst.hour, last_kst.minute) >= (15, 19):
                base_price = float((row.get("shadow_forward_base") or {}).get("baseline_price") or 0.0)
                close = float(last.get("close") or 0.0)
                if base_price > 0 and close > 0:
                    selected_checkpoints["EOD"] = {
                        "status": "observed",
                        "return_pct": round(((close / base_price) - 1.0) * 100.0, 4),
                        "price": close,
                        "observed_ts": last.get("raw_ts") or last_epoch,
                        "source": "last_regular_session_minute",
                    }
        output.append(
            {
                **{key: row.get(key) for key in (
                    "baseline_decision_id",
                    "symbol",
                    "ticker",
                    "rank",
                    "eligible",
                    "action",
                )},
                "baseline": row.get("shadow_forward_base"),
                "available": bool(outcome.get("available")),
                "reason": outcome.get("reason"),
                "returns": selected_checkpoints,
            }
        )
    return output


def _return(row: Mapping[str, Any], horizon: str) -> float | None:
    checkpoint = (row.get("returns") or {}).get(horizon)
    checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
    if checkpoint.get("status") != "observed":
        return None
    try:
        return float(checkpoint.get("return_pct"))
    except (TypeError, ValueError):
        return None


def summarize_forward_returns(
    rows: list[dict[str, Any]],
    *,
    cost_pct: float,
    slippage_pct: float,
) -> dict[str, Any]:
    drag = float(cost_pct) + float(slippage_pct)
    by_decision: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_decision[str(row.get("baseline_decision_id") or "")].append(row)
    horizons: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        top1_gross: list[float] = []
        both_gross: list[float] = []
        entered_gross: list[float] = []
        for decision_rows in by_decision.values():
            observed = [
                (row, value)
                for row in decision_rows
                for value in [_return(row, horizon)]
                if value is not None
            ]
            if not observed:
                continue
            top1 = next((value for row, value in observed if int(row.get("rank") or 0) == 1), None)
            if top1 is not None:
                top1_gross.append(top1)
            both_gross.append(sum(value for _, value in observed) / len(observed))
            entered_gross.extend(value for row, value in observed if bool(row.get("eligible")))
        horizons.append(
            {
                "horizon": horizon,
                "cost_pct": round(cost_pct, 6),
                "slippage_pct": round(slippage_pct, 6),
                "trade_count": len(entered_gross),
                "top1_observation_count": len(top1_gross),
                "both_symbol_window_count": len(both_gross),
                "top1_gross": performance_metrics(top1_gross),
                "top1_net": performance_metrics(value - drag for value in top1_gross),
                "both_symbol_average_gross": performance_metrics(both_gross),
                "both_symbol_average_net": performance_metrics(value - drag for value in both_gross),
                "eligible_entries_gross": performance_metrics(entered_gross),
                "eligible_entries_net": performance_metrics(value - drag for value in entered_gross),
                "top1_minus_both_average_net_pct": round(
                    (
                        performance_metrics(value - drag for value in top1_gross)["expectancy_pct"]
                        - performance_metrics(value - drag for value in both_gross)["expectancy_pct"]
                    ),
                    4,
                ),
            }
        )
    return {"horizons": horizons}
