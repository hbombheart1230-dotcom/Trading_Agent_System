from __future__ import annotations

from typing import Final


SCHEMA_VERSION: Final = "rank1_feature_mart.v1"
BEHAVIOR_EFFECT: Final = "NONE_OFFLINE_RESEARCH_ONLY"
LIVE_COST_PCT: Final = 0.28
INTRADAY_HORIZONS: Final = (5, 15, 30, 60, 120, 180)
OUTCOME_LABELS: Final = (
    "+5m",
    "+15m",
    "+30m",
    "+60m",
    "+120m",
    "+180m",
    "EOD",
    "NEXT_OPEN",
    "D+1_30m",
    "D+1_EOD",
    "D+2_EOD",
    "D+3_EOD",
    "D+5_EOD",
)

CORE_FEATURE_PATHS: Final = (
    "identity.decision_epoch",
    "identity.symbol",
    "scanner.score_total",
    "scanner.sources",
    "market.market_return_pct",
    "chart.completed_bar_count",
    "chart.above_vwap",
    "chart.intraday_ma2_5_cross_state",
    "chart.daily_ma5_20_cross_state",
    "chart.support_state",
    "chart.resistance_state",
)
