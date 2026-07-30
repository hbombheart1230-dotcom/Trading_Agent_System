from __future__ import annotations


SCHEMA_VERSION = "alpha_hypothesis_competition.v1"
BEHAVIOR_EFFECT = "research_only"
START = "2026-06-01"
END = "2026-07-30"
TRAIN_START = "2026-06-01"
TRAIN_END = "2026-06-30"
VALIDATION_START = "2026-07-01"
VALIDATION_END = "2026-07-30"
EPISODE_GAP_SEC = 15 * 60
LIVE_COST_PCT = 0.28
PRIMARY_HORIZON = "+30m"
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")

RISK_OFF_RAILS = frozenset(
    {
        "krx_night_futures_gap_down",
        "risk_off_breadth_collapse",
        "global_risk_off_pressure",
    }
)

HYPOTHESES = {
    "H1_OPENING_RISK_OFF_RECLAIM": {
        "name": "Opening Risk-Off Reclaim",
        "conditions": (
            "09:05-10:00 KST and risk-off rail",
            "vwap_reclaim_progress >= 0.95",
            "volume_ratio >= 0.80",
        ),
    },
    "H2_CONFIRMED_VOLUME_BREAKOUT": {
        "name": "Confirmed Volume Breakout",
        "conditions": (
            "breakout_ok is true",
            "volume_ratio >= 1.20",
            "vwap_distance_pct >= 0",
        ),
    },
    "H3_CONFIRMED_VWAP_PULLBACK": {
        "name": "Confirmed VWAP Pullback",
        "conditions": (
            "reclaim_ok is true",
            "pullback_ok is true",
            "volume_ratio >= 0.80",
        ),
    },
}

GATES = {
    "minimum_train_observed_count": 8,
    "minimum_validation_observed_count": 20,
    "minimum_forward_coverage": 0.90,
    "minimum_train_live_expectancy_pct": 0.0,
    "minimum_validation_live_expectancy_pct": 0.0,
    "minimum_validation_profit_factor": 1.20,
    "minimum_validation_positive_day_ratio": 0.55,
    "minimum_validation_mdd_pct": -6.0,
    "maximum_validation_single_day_share": 0.30,
    "maximum_validation_single_symbol_share": 0.40,
}
