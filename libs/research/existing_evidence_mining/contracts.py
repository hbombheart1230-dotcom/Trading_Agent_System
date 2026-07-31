from __future__ import annotations


SCHEMA_VERSION = "existing_evidence_mining.v1"
BEHAVIOR_EFFECT = "research_only"
START = "2026-06-01"
END = "2026-07-31"
LIVE_COST_PCT = 0.28
EPISODE_GAP_SEC = 15 * 60
TOP_K = 10
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")
PRIMARY_HORIZON = "+30m"

CALIBRATION_END = "2026-07-10"
RETROSPECTIVE_START = "2026-07-13"

MARKET_NATIVE_SOURCES = frozenset(
    {
        "top_value",
        "top_volume",
        "top_change_rate",
        "condition_search",
        "operator_watchlist",
    }
)

PATH_POLICIES = (
    {"policy_id": "target_1.0_stop_0.5_30m", "target_pct": 1.0, "stop_pct": 0.5, "max_minutes": 30},
    {"policy_id": "target_1.5_stop_0.75_30m", "target_pct": 1.5, "stop_pct": 0.75, "max_minutes": 30},
    {"policy_id": "target_2.0_stop_1.0_30m", "target_pct": 2.0, "stop_pct": 1.0, "max_minutes": 30},
)
