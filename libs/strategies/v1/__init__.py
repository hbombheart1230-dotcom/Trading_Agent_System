"""Versioned strategy implementations (v1)."""

from .config import (
    MeanReversionV1Config,
    NewsMomentumV1Config,
    RegimeMomentumV1Config,
    load_mean_reversion_v1_config,
    load_news_momentum_v1_config,
    load_regime_momentum_v1_config,
)
from .mean_reversion_v1 import MeanReversionV1
from .news_momentum_v1 import NewsMomentumV1
from .regime_momentum_v1 import RegimeMomentumV1
from .registry import (
    STRATEGY_V1_SUPPORTED,
    build_strategy_v1,
    resolve_strategy_v1_name,
    select_auto_strategy_v1,
)

__all__ = [
    "RegimeMomentumV1Config",
    "MeanReversionV1Config",
    "NewsMomentumV1Config",
    "load_regime_momentum_v1_config",
    "load_mean_reversion_v1_config",
    "load_news_momentum_v1_config",
    "RegimeMomentumV1",
    "MeanReversionV1",
    "NewsMomentumV1",
    "STRATEGY_V1_SUPPORTED",
    "resolve_strategy_v1_name",
    "select_auto_strategy_v1",
    "build_strategy_v1",
]
