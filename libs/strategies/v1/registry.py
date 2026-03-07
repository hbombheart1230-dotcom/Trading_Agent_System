from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from .config import (
    load_mean_reversion_v1_config,
    load_news_momentum_v1_config,
    load_regime_momentum_v1_config,
)
from .mean_reversion_v1 import MeanReversionV1
from .news_momentum_v1 import NewsMomentumV1
from .regime_momentum_v1 import RegimeMomentumV1


STRATEGY_V1_DEFAULT = "regime_momentum_v1"
STRATEGY_V1_AUTO = "auto"
STRATEGY_V1_SUPPORTED = {
    "regime_momentum_v1",
    "mean_reversion_v1",
    "news_momentum_v1",
}


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _canonical_strategy_name(v: Any) -> str:
    name = str(v or "").strip().lower()
    if name in ("momentum", "regime_momentum", "regime_momentum_v1"):
        return "regime_momentum_v1"
    if name in ("mean_reversion", "mean_reversion_v1", "reversion"):
        return "mean_reversion_v1"
    if name in ("news_momentum", "news_momentum_v1", "news"):
        return "news_momentum_v1"
    if name in ("auto", STRATEGY_V1_AUTO):
        return STRATEGY_V1_AUTO
    return STRATEGY_V1_DEFAULT


def select_auto_strategy_v1(*, llm_context: Dict[str, Any] | None) -> str:
    ctx = dict(llm_context or {})
    technical = ctx.get("technical") if isinstance(ctx.get("technical"), dict) else {}
    news = ctx.get("news") if isinstance(ctx.get("news"), dict) else {}
    regime = str(technical.get("regime") or "").strip().lower()
    signal = _to_float(technical.get("signal_score"), 0.0)
    symbol_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
    symbol_status = str(news.get("symbol_sentiment_status") or "").strip().lower()

    # Strong, high-quality sentiment shock -> news momentum.
    if symbol_status == "ok" and abs(symbol_news) >= 0.35:
        return "news_momentum_v1"
    # Range/high-vol with weak directional signal -> mean reversion.
    if regime in ("range", "high_volatility") and abs(signal) <= 0.35:
        return "mean_reversion_v1"
    return STRATEGY_V1_DEFAULT


def resolve_strategy_v1_name(
    *,
    policy: Dict[str, Any] | None,
    llm_context: Dict[str, Any] | None,
) -> str:
    p = dict(policy or {})
    raw = p.get("strategy_v1_name")
    if raw is None:
        raw = os.getenv("STRATEGY_V1_NAME", STRATEGY_V1_DEFAULT)
    name = _canonical_strategy_name(raw)
    if name == STRATEGY_V1_AUTO:
        name = select_auto_strategy_v1(llm_context=llm_context)
    if name not in STRATEGY_V1_SUPPORTED:
        return STRATEGY_V1_DEFAULT
    return name


def build_strategy_v1(*, name: str, policy: Dict[str, Any] | None) -> Tuple[Any, str]:
    canonical = _canonical_strategy_name(name)
    if canonical not in STRATEGY_V1_SUPPORTED:
        canonical = STRATEGY_V1_DEFAULT

    if canonical == "mean_reversion_v1":
        cfg = load_mean_reversion_v1_config(policy=policy)
        return MeanReversionV1(config=cfg), canonical
    if canonical == "news_momentum_v1":
        cfg = load_news_momentum_v1_config(policy=policy)
        return NewsMomentumV1(config=cfg), canonical
    cfg = load_regime_momentum_v1_config(policy=policy)
    return RegimeMomentumV1(config=cfg), "regime_momentum_v1"
