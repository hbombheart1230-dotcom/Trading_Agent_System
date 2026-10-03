from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import HYPOTHESIS_HORIZONS


MINUTES = {"+5m": 5, "+15m": 15, "+30m": 30, "+60m": 60}
KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def entry_forward_outcomes(
    entry_methods: Mapping[str, Any],
    *,
    candles: list[Mapping[str, Any]],
    drag_pct: float,
) -> dict[str, Any]:
    ordered = sorted(candles, key=lambda row: int(row.get("ts") or 0))
    output: dict[str, Any] = {}
    for method, raw in entry_methods.items():
        entry = raw if isinstance(raw, Mapping) else {}
        entry_epoch = int(entry.get("entry_epoch") or 0)
        entry_price = _number(entry.get("entry_price"))
        if entry.get("status") != "OBSERVED" or entry_epoch <= 0 or not entry_price:
            output[str(method)] = {
                "status": "MISSING",
                "reason": str(entry.get("reason") or "entry_observation_missing"),
                "returns": {},
            }
            continue
        returns: dict[str, Any] = {}
        for horizon in HYPOTHESIS_HORIZONS:
            if horizon == "EOD":
                observed = ordered[-1] if ordered else None
                window = [row for row in ordered if int(row.get("ts") or 0) >= entry_epoch]
                observed_kst = (
                    datetime.fromtimestamp(int(observed.get("ts") or 0), tz=KST)
                    if observed is not None
                    else None
                )
                if observed_kst is None or (observed_kst.hour, observed_kst.minute) < (15, 30):
                    observed = None
            else:
                target = entry_epoch + MINUTES[horizon] * 60
                observed = next(
                    (row for row in ordered if target <= int(row.get("ts") or 0) <= target + 90),
                    None,
                )
                window = [
                    row
                    for row in ordered
                    if entry_epoch <= int(row.get("ts") or 0) <= target
                ]
            close = _number((observed or {}).get("close"))
            if observed is None or close is None or not window:
                returns[horizon] = {"status": "PENDING"}
                continue
            high = max(_number(row.get("high") or row.get("close")) or entry_price for row in window)
            low = min(_number(row.get("low") or row.get("close")) or entry_price for row in window)
            gross = ((close / entry_price) - 1.0) * 100.0
            returns[horizon] = {
                "status": "OBSERVED",
                "gross_return_pct": round(gross, 6),
                "net_return_pct": round(gross - drag_pct, 6),
                "mfe_pct": round(((high / entry_price) - 1.0) * 100.0, 6),
                "mae_pct": round(((low / entry_price) - 1.0) * 100.0, 6),
                "observed_epoch": int(observed.get("ts") or 0),
                "observed_price": close,
            }
        output[str(method)] = {
            "status": "OBSERVED",
            "reason": "",
            "entry_epoch": entry_epoch,
            "entry_price": entry_price,
            "returns": returns,
        }
    return output


def summarize_outcomes(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    values = [_number(row.get("net_return_pct")) for row in rows]
    values = [value for value in values if value is not None]
    mfe = [_number(row.get("mfe_pct")) for row in rows]
    mae = [_number(row.get("mae_pct")) for row in rows]
    mfe = [value for value in mfe if value is not None]
    mae = [value for value in mae if value is not None]
    metric = performance_metrics(values)
    return {
        "sample_count": int(metric.get("count") or 0),
        "win_rate": metric.get("win_rate"),
        "avg_return_pct": metric.get("average_return_pct"),
        "profit_factor": metric.get("profit_factor"),
        "max_drawdown_pct": metric.get("maximum_drawdown_pct"),
        "avg_mfe_pct": round(sum(mfe) / len(mfe), 6) if mfe else None,
        "avg_mae_pct": round(sum(mae) / len(mae), 6) if mae else None,
    }
