from __future__ import annotations


SCHEMA_VERSION = "opening_rank1_shadow.v1"
BEHAVIOR_EFFECT = "observation_only"
COHORT_ID = "OPEN_0_20_RANK1_30M"
FIRST_ELIGIBLE_DAY = "2026-08-03"
OPEN_START_MINUTE = 9 * 60
OPEN_END_MINUTE = 9 * 60 + 20
EPISODE_GAP_SEC = 15 * 60
PRIMARY_HORIZON = "+30m"
LIVE_COST_PCT = 0.28
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")

PROMOTION_GATES = {
    "minimum_observed_count": 25,
    "minimum_observed_day_count": 10,
    "minimum_coverage": 0.90,
    "minimum_win_rate": 0.50,
    "minimum_average_net_return_pct": 0.0,
    "minimum_profit_factor": 1.20,
    "minimum_positive_day_ratio": 0.55,
    "maximum_largest_day_share": 0.25,
    "maximum_largest_symbol_share": 0.25,
}

NEXT_STAGE = "CONTROLLED_SHADOW_ONLY"
