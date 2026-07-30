from __future__ import annotations


SCHEMA_VERSION = "post_reclaim_offline_research.v1"
TARGET_SUBTYPE = "confirmed_post_reclaim_pullback"
EPISODE_GAP_SEC = 15 * 60
FORWARD_MAX_DELAY_SEC = 180
HORIZONS_MINUTES = (5, 15, 30, 60)
LIVE_COST_PCT = 0.28
MOCK_COST_PCT = 1.086849

EVIDENCE_GATES = {
    "minimum_episode_count": 20,
    "minimum_day_count": 10,
    "minimum_symbol_count": 5,
    "minimum_forward_coverage": 0.90,
    "maximum_single_day_share": 0.30,
    "maximum_single_symbol_share": 0.40,
}

PERFORMANCE_GATES = {
    "minimum_live_net_expectancy_15m_pct": 0.0,
    "minimum_live_net_expectancy_30m_pct": 0.0,
    "minimum_live_net_profit_factor_30m": 1.20,
    "minimum_positive_day_ratio_30m": 0.60,
    "minimum_live_net_mdd_30m_pct": -6.0,
}
