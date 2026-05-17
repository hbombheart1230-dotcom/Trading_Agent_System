from __future__ import annotations

from typing import Any, Dict

from libs.runtime.monitor_exit.numeric import to_float


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def is_emergency_exit_reason(reason: str) -> bool:
    text = str(reason or "").strip().lower()
    return text in ("emergency_halt", "news_shock")


def is_hard_exit_reason(reason: str) -> bool:
    text = str(reason or "").strip().lower()
    return text in (
        "emergency_halt",
        "news_shock",
        "eod_flat",
        "hard_stop",
        "stop_loss",
        "intraday_low_break",
        "trend_breakdown",
        "vwap_breakdown",
        "volatility_expansion",
        "trailing_stop",
    )


def exit_reason_priority(reason: str) -> int:
    text = str(reason or "").strip().lower()
    order = {
        "emergency_halt": 100,
        "news_shock": 95,
        "eod_flat": 90,
        "time_stop": 80,
        "max_hold": 75,
        "hard_stop": 72,
        "stop_loss": 70,
        "intraday_low_break": 69,
        "trend_breakdown": 68,
        "peak_drawdown": 67,
        "vwap_breakdown": 66,
        "volatility_expansion": 65,
        "trailing_stop": 60,
        "volume_exhaustion_take_profit": 59,
        "opening_gap_profit_take": 59,
        "vwap_extension_take_profit": 58,
        "resistance_take_profit": 57,
        "risk_reward_take_profit": 56,
        "profit_ladder": 55,
        "partial_take_profit": 55,
        "time_decay_profit_exit": 55,
        "take_profit": 50,
        "hold": 10,
        "price_unavailable": 5,
        "no_position": 0,
    }
    return int(order.get(text, 1))


def is_soft_profit_exit_reason(reason: Any) -> bool:
    return str(reason or "").strip().lower() in {
        "take_profit",
        "partial_take_profit",
        "profit_ladder",
        "risk_reward_take_profit",
        "vwap_extension_take_profit",
        "resistance_take_profit",
        "volume_exhaustion_take_profit",
        "opening_gap_profit_take",
        "time_decay_profit_exit",
    }


def friendly_exit_axis(reason: Any) -> str:
    text = str(reason or "").strip().replace("_", " ")
    if not text:
        return "No trigger"
    return " ".join(part.capitalize() for part in text.split())


def monitor_watch_axes(thresholds: Dict[str, Any]) -> list[str]:
    if not isinstance(thresholds, dict):
        return []
    out: list[str] = []
    if to_float(thresholds.get("hard_stop_pct")) > 0.0:
        out.append("Hard stop")
    if to_float(thresholds.get("stop_loss_pct")) > 0.0:
        out.append("Adaptive stop")
    if to_float(thresholds.get("take_profit_pct")) > 0.0:
        out.append("Take profit")
    if _is_trueish(thresholds.get("cost_aware_profit_floor_enabled")) and to_float(
        thresholds.get("cost_aware_profit_floor_pct")
    ) > 0.0:
        out.append("Cost-aware profit floor")
    if to_float(thresholds.get("partial_take_profit_pct")) > 0.0:
        out.append("Partial take profit")
    if isinstance(thresholds.get("profit_ladder_levels_pct"), list) and thresholds.get("profit_ladder_levels_pct"):
        out.append("Profit ladder")
    if to_float(thresholds.get("risk_reward_take_profit_r")) > 0.0:
        out.append("Risk/reward take profit")
    elif isinstance(thresholds.get("risk_reward_take_profit_rungs"), list) and thresholds.get("risk_reward_take_profit_rungs"):
        out.append("Risk/reward take profit")
    if to_float(thresholds.get("vwap_extension_take_profit_pct")) > 0.0:
        out.append("VWAP extension take profit")
    if to_float(thresholds.get("resistance_take_profit_near_pct")) > 0.0:
        out.append("Resistance take profit")
    if to_float(thresholds.get("volume_exhaustion_take_profit_min_pct")) > 0.0:
        out.append("Volume exhaustion take profit")
    if to_float(thresholds.get("opening_gap_profit_take_min_pct")) > 0.0:
        out.append("Opening gap profit take")
    if to_float(thresholds.get("profit_time_stop_sec")) > 0.0:
        out.append("Time-decay profit exit")
    if to_float(thresholds.get("trailing_stop_pct")) > 0.0:
        out.append("Trailing stop")
    if to_float(thresholds.get("peak_drawdown_exit_pct")) > 0.0:
        out.append("Peak drawdown")
    if to_float(thresholds.get("vwap_breakdown_pct")) > 0.0:
        out.append("VWAP breakdown")
    if to_float(thresholds.get("intraday_low_break_pct")) > 0.0:
        out.append("Intraday low break")
    if to_float(thresholds.get("trend_strength_floor")) != 0.0:
        out.append("Trend breakdown")
    if to_float(thresholds.get("vol_expansion_ratio")) > 0.0:
        out.append("Volatility expansion")
    if to_float(thresholds.get("news_shock_threshold")) > 0.0:
        out.append("News shock")
    if bool(thresholds.get("use_eod_flat")):
        out.append("EOD flat")
    return out
