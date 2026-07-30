from __future__ import annotations


SCHEMA_VERSION = "structural_alpha_batch1.v1"
BEHAVIOR_EFFECT = "research_only"
START = "2026-06-24"
END = "2026-07-30"
CALIBRATION_START = "2026-06-24"
CALIBRATION_END = "2026-07-10"
RETROSPECTIVE_START = "2026-07-13"
RETROSPECTIVE_END = "2026-07-30"
TOP_K = 5
EPISODE_GAP_SEC = 15 * 60
LIVE_COST_PCT = 0.28
PRIMARY_HORIZON = "+30m"
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")

HYPOTHESES = {
    "H4_CROSS_SECTIONAL_RELATIVE_STRENGTH": "Cross-Sectional Relative Strength",
    "H5_POINT_IN_TIME_SECTOR_LEADER": "Point-In-Time Sector Leader",
    "H6_VOLATILITY_CONTRACTION_BREAKOUT": "Volatility Contraction Breakout",
}

GATES = {
    "minimum_calibration_observed_count": 15,
    "minimum_retrospective_observed_count": 25,
    "minimum_forward_coverage": 0.90,
    "minimum_calibration_expectancy_pct": 0.0,
    "minimum_retrospective_expectancy_pct": 0.0,
    "minimum_retrospective_profit_factor": 1.20,
    "minimum_retrospective_positive_day_ratio": 0.55,
    "minimum_retrospective_mdd_pct": -6.0,
    "maximum_retrospective_single_day_share": 0.30,
    "maximum_retrospective_single_symbol_share": 0.40,
}
