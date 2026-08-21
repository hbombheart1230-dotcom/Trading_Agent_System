from __future__ import annotations

from statistics import fmean
from typing import Any, Mapping

from .contracts import (
    ENTRY_RULES,
    EXIT_RULES,
    TARGET_NAME,
    TARGET_SYMBOL,
    TARGET_TICKER,
)
from .data_provider import signal_at


def _features(rows: list[Mapping[str, Any]], *, epoch: int) -> dict[str, Any]:
    usable = [row for row in rows if int(row.get("ts") or 0) <= epoch]
    if len(usable) < 6:
        return {"available": False, "reason": "insufficient_woori_candles", "candle_count": len(usable)}
    current = usable[-1]
    close = float(current.get("close") or 0.0)
    recent = usable[-21:]
    volumes = [float(row.get("volume") or 0.0) for row in recent[:-1] if float(row.get("volume") or 0.0) > 0]
    volume_mean = fmean(volumes) if volumes else 0.0
    volume_ratio = float(current.get("volume") or 0.0) / volume_mean if volume_mean else 0.0
    ma5 = fmean(float(row.get("close") or close) for row in usable[-5:])
    weighted = [row for row in usable if float(row.get("volume") or 0.0) > 0]
    volume_sum = sum(float(row.get("volume") or 0.0) for row in weighted)
    vwap = (
        sum(float(row.get("close") or 0.0) * float(row.get("volume") or 0.0) for row in weighted)
        / volume_sum
        if volume_sum
        else ma5
    )
    prior_high = max(float(row.get("high") or row.get("close") or 0.0) for row in usable[-6:-1])
    return {
        "available": True,
        "candle_count": len(usable),
        "baseline_epoch": int(current.get("ts") or epoch),
        "baseline_price": close,
        "baseline_raw_ts": current.get("raw_ts"),
        "volume_ratio": round(volume_ratio, 6),
        "short_ma5": round(ma5, 6),
        "vwap": round(vwap, 6),
        "breakout_confirmed": close > prior_high,
        "price_above_vwap_or_short_ma": bool(close >= vwap or close >= ma5),
    }


def build_decision_snapshot(
    *,
    day: str,
    as_of_epoch: int,
    woori_candles: list[Mapping[str, Any]],
    btc_signals: Mapping[str, Any],
    crypto_fear_greed: Mapping[str, Any] | None = None,
    volume_ratio_min: float = 1.2,
) -> dict[str, Any]:
    local = _features(woori_candles, epoch=as_of_epoch)
    btc = signal_at(btc_signals, epoch=as_of_epoch)
    local_confirmation = bool(
        local.get("available")
        and (
            float(local.get("volume_ratio") or 0.0) >= volume_ratio_min
            or bool(local.get("breakout_confirmed"))
        )
    )
    conditions = {
        ENTRY_RULES[0]: bool(btc.get("leading_positive", btc.get("positive"))),
        ENTRY_RULES[1]: local_confirmation,
        ENTRY_RULES[2]: bool(local.get("price_above_vwap_or_short_ma")),
    }
    eligible = bool(local.get("available") and btc.get("available") and all(conditions.values()))
    btc_momentum = float(btc.get("momentum_5m_pct") or 0.0)
    volume_edge = max(0.0, float(local.get("volume_ratio") or 0.0) - 1.0)
    score = (0.7 * max(-3.0, min(3.0, btc_momentum))) + (0.3 * min(3.0, volume_edge))
    return {
        "schema_version": "baseline_btc_woori_decision.v2",
        "evaluation_program_id": "Q12_BTC_WOORI_TECH_BASELINE",
        "behavior_effect": "shadow_only",
        "decision_policy_version": "q12_btc_multihorizon_leading_signal.v2",
        "decision_id": f"BTW_{day.replace('-', '')}_{as_of_epoch}",
        "day": day,
        "as_of_epoch": as_of_epoch,
        "target": {"symbol": TARGET_SYMBOL, "ticker": TARGET_TICKER, "name": TARGET_NAME},
        "btc_signal": btc,
        "crypto_fear_greed": dict(crypto_fear_greed or {}),
        "crypto_fear_greed_behavior_effect": "observation_only",
        "local_features": local,
        "entry_rules": list(ENTRY_RULES),
        "entry_rule_count": len(ENTRY_RULES),
        "entry_conditions": conditions,
        "exit_rules": list(EXIT_RULES),
        "exit_rule_count": len(EXIT_RULES),
        "score": round(score, 6),
        "eligible": eligible,
        "action": "SHADOW_ENTER" if eligible else "NO_ENTRY",
        "reason": (
            "all_entry_conditions_passed"
            if eligible
            else btc.get("reason")
            if not btc.get("available")
            else "entry_condition_failed"
        ),
        "order_execution_allowed": False,
        "order_intent": None,
        "llm_used": False,
        "strategist_used": False,
        "commander_used": False,
    }
