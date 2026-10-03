from __future__ import annotations


SCHEMA_VERSION = "short_alpha_discriminator.v1"
BEHAVIOR_EFFECT = "NONE_OBSERVATION_ONLY"
PROSPECTIVE_START_DAY = "2026-08-25"
LIVE_ROUND_TRIP_COST_PCT = 0.28
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")

PRIMARY_COHORT_ID = "HIGH_COMMON_SHORT_ALPHA_V1"
NEGATIVE_CONTROL_ID = "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1"

PROFIT_LOCK_PROXIES = (
    {
        "policy_id": "MFE_2_LOCK_0_5_PROXY",
        "trigger_mfe_pct": 2.0,
        "floor_net_return_pct": 0.5,
    },
    {
        "policy_id": "MFE_3_LOCK_1_0_PROXY",
        "trigger_mfe_pct": 3.0,
        "floor_net_return_pct": 1.0,
    },
)
