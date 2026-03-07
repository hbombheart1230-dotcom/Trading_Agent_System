from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict


def _to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


@dataclass(frozen=True)
class RegimeMomentumV1Config:
    version: str = "regime_momentum_v1"
    buy_composite_threshold: float = 0.20
    sell_composite_threshold: float = -0.12
    min_signal_for_entry: float = 0.15
    min_news_for_entry: float = 0.00
    max_volatility_for_entry: float = 0.12
    invalidation_signal_floor: float = -0.08
    base_risk_per_trade_ratio: float = 0.01
    base_position_notional_ratio: float = 0.10
    min_confidence_for_entry: float = 0.35
    max_position_qty: int = 10
    min_position_qty: int = 1
    lot_size: int = 1


@dataclass(frozen=True)
class MeanReversionV1Config:
    version: str = "mean_reversion_v1"
    buy_rsi_ceiling: float = 35.0
    sell_rsi_floor: float = 62.0
    min_gap_for_entry: float = -0.015
    max_volatility_for_entry: float = 0.15
    stop_news_floor: float = -0.35
    base_risk_per_trade_ratio: float = 0.008
    base_position_notional_ratio: float = 0.08
    min_confidence_for_entry: float = 0.30
    max_position_qty: int = 10
    min_position_qty: int = 1
    lot_size: int = 1


@dataclass(frozen=True)
class NewsMomentumV1Config:
    version: str = "news_momentum_v1"
    buy_news_threshold: float = 0.30
    sell_news_threshold: float = -0.20
    min_signal_for_entry: float = 0.05
    max_volatility_for_entry: float = 0.20
    require_ok_status: bool = True
    base_risk_per_trade_ratio: float = 0.009
    base_position_notional_ratio: float = 0.09
    min_confidence_for_entry: float = 0.30
    max_position_qty: int = 10
    min_position_qty: int = 1
    lot_size: int = 1


def load_regime_momentum_v1_config(policy: Dict[str, Any] | None = None) -> RegimeMomentumV1Config:
    p = dict(policy or {})
    strategy = p.get("strategy_v1")
    sp = dict(strategy) if isinstance(strategy, dict) else {}

    return RegimeMomentumV1Config(
        buy_composite_threshold=_to_float(
            sp.get("buy_composite_threshold", os.getenv("STRATEGY_V1_BUY_COMPOSITE_THRESHOLD", 0.20)),
            0.20,
        ),
        sell_composite_threshold=_to_float(
            sp.get("sell_composite_threshold", os.getenv("STRATEGY_V1_SELL_COMPOSITE_THRESHOLD", -0.12)),
            -0.12,
        ),
        min_signal_for_entry=_to_float(
            sp.get("min_signal_for_entry", os.getenv("STRATEGY_V1_MIN_SIGNAL_FOR_ENTRY", 0.15)),
            0.15,
        ),
        min_news_for_entry=_to_float(
            sp.get("min_news_for_entry", os.getenv("STRATEGY_V1_MIN_NEWS_FOR_ENTRY", 0.00)),
            0.0,
        ),
        max_volatility_for_entry=_to_float(
            sp.get("max_volatility_for_entry", os.getenv("STRATEGY_V1_MAX_VOLATILITY_FOR_ENTRY", 0.12)),
            0.12,
        ),
        invalidation_signal_floor=_to_float(
            sp.get("invalidation_signal_floor", os.getenv("STRATEGY_V1_INVALIDATION_SIGNAL_FLOOR", -0.08)),
            -0.08,
        ),
        base_risk_per_trade_ratio=_to_float(
            sp.get("base_risk_per_trade_ratio", os.getenv("STRATEGY_V1_BASE_RISK_PER_TRADE_RATIO", 0.01)),
            0.01,
        ),
        base_position_notional_ratio=_to_float(
            sp.get("base_position_notional_ratio", os.getenv("STRATEGY_V1_BASE_POSITION_NOTIONAL_RATIO", 0.10)),
            0.10,
        ),
        min_confidence_for_entry=_to_float(
            sp.get("min_confidence_for_entry", os.getenv("STRATEGY_V1_MIN_CONFIDENCE_FOR_ENTRY", 0.35)),
            0.35,
        ),
        max_position_qty=max(
            1,
            _to_int(
                sp.get("max_position_qty", os.getenv("STRATEGY_V1_MAX_POSITION_QTY", 10)),
                10,
            ),
        ),
        min_position_qty=max(
            1,
            _to_int(
                sp.get("min_position_qty", os.getenv("STRATEGY_V1_MIN_POSITION_QTY", 1)),
                1,
            ),
        ),
        lot_size=max(
            1,
            _to_int(
                sp.get("lot_size", os.getenv("STRATEGY_V1_LOT_SIZE", 1)),
                1,
            ),
        ),
    )


def load_mean_reversion_v1_config(policy: Dict[str, Any] | None = None) -> MeanReversionV1Config:
    p = dict(policy or {})
    strategy = p.get("strategy_v1")
    sp = dict(strategy) if isinstance(strategy, dict) else {}

    return MeanReversionV1Config(
        buy_rsi_ceiling=_to_float(
            sp.get("buy_rsi_ceiling", os.getenv("STRATEGY_V1_MR_BUY_RSI_CEILING", 35.0)),
            35.0,
        ),
        sell_rsi_floor=_to_float(
            sp.get("sell_rsi_floor", os.getenv("STRATEGY_V1_MR_SELL_RSI_FLOOR", 62.0)),
            62.0,
        ),
        min_gap_for_entry=_to_float(
            sp.get("min_gap_for_entry", os.getenv("STRATEGY_V1_MR_MIN_GAP_FOR_ENTRY", -0.015)),
            -0.015,
        ),
        max_volatility_for_entry=_to_float(
            sp.get("max_volatility_for_entry", os.getenv("STRATEGY_V1_MR_MAX_VOLATILITY_FOR_ENTRY", 0.15)),
            0.15,
        ),
        stop_news_floor=_to_float(
            sp.get("stop_news_floor", os.getenv("STRATEGY_V1_MR_STOP_NEWS_FLOOR", -0.35)),
            -0.35,
        ),
        base_risk_per_trade_ratio=_to_float(
            sp.get("base_risk_per_trade_ratio", os.getenv("STRATEGY_V1_MR_BASE_RISK_PER_TRADE_RATIO", 0.008)),
            0.008,
        ),
        base_position_notional_ratio=_to_float(
            sp.get("base_position_notional_ratio", os.getenv("STRATEGY_V1_MR_BASE_POSITION_NOTIONAL_RATIO", 0.08)),
            0.08,
        ),
        min_confidence_for_entry=_to_float(
            sp.get("min_confidence_for_entry", os.getenv("STRATEGY_V1_MR_MIN_CONFIDENCE_FOR_ENTRY", 0.30)),
            0.30,
        ),
        max_position_qty=max(
            1,
            _to_int(
                sp.get("max_position_qty", os.getenv("STRATEGY_V1_MR_MAX_POSITION_QTY", 10)),
                10,
            ),
        ),
        min_position_qty=max(
            1,
            _to_int(
                sp.get("min_position_qty", os.getenv("STRATEGY_V1_MR_MIN_POSITION_QTY", 1)),
                1,
            ),
        ),
        lot_size=max(
            1,
            _to_int(
                sp.get("lot_size", os.getenv("STRATEGY_V1_MR_LOT_SIZE", 1)),
                1,
            ),
        ),
    )


def load_news_momentum_v1_config(policy: Dict[str, Any] | None = None) -> NewsMomentumV1Config:
    p = dict(policy or {})
    strategy = p.get("strategy_v1")
    sp = dict(strategy) if isinstance(strategy, dict) else {}

    return NewsMomentumV1Config(
        buy_news_threshold=_to_float(
            sp.get("buy_news_threshold", os.getenv("STRATEGY_V1_NEWS_BUY_THRESHOLD", 0.30)),
            0.30,
        ),
        sell_news_threshold=_to_float(
            sp.get("sell_news_threshold", os.getenv("STRATEGY_V1_NEWS_SELL_THRESHOLD", -0.20)),
            -0.20,
        ),
        min_signal_for_entry=_to_float(
            sp.get("min_signal_for_entry", os.getenv("STRATEGY_V1_NEWS_MIN_SIGNAL_FOR_ENTRY", 0.05)),
            0.05,
        ),
        max_volatility_for_entry=_to_float(
            sp.get("max_volatility_for_entry", os.getenv("STRATEGY_V1_NEWS_MAX_VOLATILITY_FOR_ENTRY", 0.20)),
            0.20,
        ),
        require_ok_status=str(
            sp.get("require_ok_status", os.getenv("STRATEGY_V1_NEWS_REQUIRE_OK_STATUS", "true"))
        ).strip().lower()
        in ("1", "true", "yes", "y", "on"),
        base_risk_per_trade_ratio=_to_float(
            sp.get("base_risk_per_trade_ratio", os.getenv("STRATEGY_V1_NEWS_BASE_RISK_PER_TRADE_RATIO", 0.009)),
            0.009,
        ),
        base_position_notional_ratio=_to_float(
            sp.get("base_position_notional_ratio", os.getenv("STRATEGY_V1_NEWS_BASE_POSITION_NOTIONAL_RATIO", 0.09)),
            0.09,
        ),
        min_confidence_for_entry=_to_float(
            sp.get("min_confidence_for_entry", os.getenv("STRATEGY_V1_NEWS_MIN_CONFIDENCE_FOR_ENTRY", 0.30)),
            0.30,
        ),
        max_position_qty=max(
            1,
            _to_int(
                sp.get("max_position_qty", os.getenv("STRATEGY_V1_NEWS_MAX_POSITION_QTY", 10)),
                10,
            ),
        ),
        min_position_qty=max(
            1,
            _to_int(
                sp.get("min_position_qty", os.getenv("STRATEGY_V1_NEWS_MIN_POSITION_QTY", 1)),
                1,
            ),
        ),
        lot_size=max(
            1,
            _to_int(
                sp.get("lot_size", os.getenv("STRATEGY_V1_NEWS_LOT_SIZE", 1)),
                1,
            ),
        ),
    )
