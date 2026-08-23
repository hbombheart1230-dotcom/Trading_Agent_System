from __future__ import annotations

from statistics import fmean
from typing import Any, Mapping

from .contracts import ENTRY_RULES, EXIT_RULES, SYMBOLS


def _mean(values: list[float]) -> float | None:
    return fmean(values) if values else None


def _features(rows: list[Mapping[str, Any]], *, as_of_epoch: int) -> dict[str, Any]:
    usable = [row for row in rows if int(row.get("ts") or 0) <= as_of_epoch]
    if len(usable) < 6:
        return {"available": False, "reason": "insufficient_candles", "candle_count": len(usable)}
    current = usable[-1]
    close = float(current.get("close") or 0.0)
    lookback = usable[-21:]
    prior_volume = [float(row.get("volume") or 0.0) for row in lookback[:-1] if float(row.get("volume") or 0.0) > 0]
    average_volume = _mean(prior_volume)
    volume_ratio = (
        float(current.get("volume") or 0.0) / average_volume
        if average_volume and average_volume > 0
        else 0.0
    )
    ma5 = _mean([float(row.get("close") or 0.0) for row in usable[-5:]])
    weighted_rows = [row for row in usable if float(row.get("volume") or 0.0) > 0]
    weighted_volume = sum(float(row.get("volume") or 0.0) for row in weighted_rows)
    vwap = (
        sum(float(row.get("close") or 0.0) * float(row.get("volume") or 0.0) for row in weighted_rows)
        / weighted_volume
        if weighted_volume > 0
        else ma5
    )
    def momentum(minutes: int) -> float | None:
        if len(usable) <= minutes:
            return None
        base = float(usable[-(minutes + 1)].get("close") or 0.0)
        return ((close / base) - 1.0) * 100.0 if base > 0.0 else None

    momentum_pct = momentum(5) or 0.0
    return {
        "available": True,
        "candle_count": len(usable),
        "baseline_epoch": int(current.get("ts") or as_of_epoch),
        "baseline_price": close,
        "baseline_raw_ts": current.get("raw_ts"),
        "momentum_5m_pct": round(momentum_pct, 4),
        "momentum_15m_pct": round(value, 4) if (value := momentum(15)) is not None else None,
        "momentum_30m_pct": round(value, 4) if (value := momentum(30)) is not None else None,
        "momentum_60m_pct": round(value, 4) if (value := momentum(60)) is not None else None,
        "volume_ratio": round(volume_ratio, 4),
        "short_ma5": round(float(ma5 or close), 4),
        "vwap": round(float(vwap or close), 4),
    }


def build_decision_snapshot(
    *,
    day: str,
    as_of_epoch: int,
    candles: Mapping[str, list[Mapping[str, Any]]],
    market_change_pct: float | None,
    market_snapshot: Mapping[str, Any] | None = None,
    volume_ratio_min: float = 1.2,
    sharp_negative_threshold_pct: float = -2.0,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for symbol_meta in SYMBOLS:
        symbol = symbol_meta["symbol"]
        features = _features(list(candles.get(symbol) or []), as_of_epoch=as_of_epoch)
        if not features.get("available"):
            rows.append(
                {
                    **symbol_meta,
                    "eligible": False,
                    "action": "NO_ENTRY",
                    "reason": features.get("reason"),
                    "features": features,
                    "entry_conditions": {},
                }
            )
            continue
        price = float(features["baseline_price"])
        trend_ok = bool(price >= float(features["vwap"]) or price >= float(features["short_ma5"]))
        volume_ok = bool(float(features["volume_ratio"]) >= volume_ratio_min)
        market_ok = bool(
            market_change_pct is None
            or float(market_change_pct) > sharp_negative_threshold_pct
        )
        conditions = {
            ENTRY_RULES[0]: trend_ok,
            ENTRY_RULES[1]: volume_ok,
            ENTRY_RULES[2]: market_ok,
        }
        momentum_component = max(-3.0, min(3.0, float(features["momentum_5m_pct"])))
        volume_component = max(0.0, min(3.0, float(features["volume_ratio"]) - 1.0))
        score = (0.75 * momentum_component) + (0.25 * volume_component)
        eligible = all(conditions.values())
        rows.append(
            {
                **symbol_meta,
                "eligible": eligible,
                "action": "SHADOW_ENTER" if eligible else "NO_ENTRY",
                "reason": "all_entry_conditions_passed" if eligible else "entry_condition_failed",
                "score": round(score, 6),
                "features": features,
                "entry_conditions": conditions,
            }
        )
    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row.get("score") or -999.0),
            str(row.get("symbol") or ""),
        ),
    )
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
        row["top1"] = rank == 1
    decision_id = f"BSH_{day.replace('-', '')}_{as_of_epoch}"
    return {
        "schema_version": "baseline_samsung_hynix_decision.v1",
        "behavior_effect": "shadow_only",
        "decision_id": decision_id,
        "day": day,
        "as_of_epoch": as_of_epoch,
        "market_change_pct": market_change_pct,
        "market_snapshot": dict(market_snapshot or {}),
        "universe": [row["ticker"] for row in SYMBOLS],
        "entry_rule_count": len(ENTRY_RULES),
        "entry_rules": list(ENTRY_RULES),
        "exit_rule_count": len(EXIT_RULES),
        "exit_rules": list(EXIT_RULES),
        "ranking_formula": "0.75 * clipped_5m_momentum_pct + 0.25 * clipped(volume_ratio - 1)",
        "ranked_candidates": ranked,
        "selected_symbol": str(ranked[0].get("symbol") or "") if ranked else "",
        "selected_action": str(ranked[0].get("action") or "") if ranked else "NO_ENTRY",
        "order_execution_allowed": False,
        "llm_used": False,
        "strategist_used": False,
        "commander_used": False,
    }
