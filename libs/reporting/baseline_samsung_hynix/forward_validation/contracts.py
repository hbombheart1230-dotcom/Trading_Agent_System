from __future__ import annotations


PROGRAM_ID = "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION"
ACTIVATION_DAY = "2026-08-31"
SCHEMA_VERSION = "q10_korea_lead_market_forward_validation.v1"

TARGETS = (
    {"key": "samsung", "symbol": "005930", "ticker": "005930.KS", "name": "Samsung Electronics", "kind": "stock"},
    {"key": "sk_hynix", "symbol": "000660", "ticker": "000660.KS", "name": "SK Hynix", "kind": "stock"},
    {"key": "kospi", "symbol": "KOSPI", "ticker": "^KS11", "name": "KOSPI", "kind": "index"},
    {"key": "kosdaq", "symbol": "KOSDAQ", "ticker": "^KQ11", "name": "KOSDAQ", "kind": "index"},
)

CHECKPOINTS = ("09:00", "09:03", "09:05", "09:10", "09:15", "09:30", "10:00", "CLOSE")
SHADOW_ENTRY_POLICIES = (
    "ENTRY_0900",
    "ENTRY_0903",
    "ENTRY_0905",
    "ENTRY_0910",
    "FIRST_PULLBACK_ENTRY",
)
SEMICONDUCTOR_STATES = (
    "STRONG_POSITIVE",
    "POSITIVE",
    "NEUTRAL",
    "NEGATIVE",
    "STRONG_NEGATIVE",
)
MARKET_STATES = (
    "STRONG_RISK_ON",
    "RISK_ON",
    "NEUTRAL",
    "RISK_OFF",
    "STRONG_RISK_OFF",
)
REACTION_STATES = ("UNDERREACTION", "FAIR_REACTION", "OVERREACTION", "DIVERGENCE")

# Frozen v1 thresholds. Changing any value requires closing this validation cohort.
THRESHOLDS = {
    "sox_positive_pct": 3.0,
    "sox_strong_positive_pct": 5.0,
    "sox_negative_pct": -3.0,
    "sox_strong_negative_pct": -5.0,
    "hynix_extended_3d_abs_pct": 8.0,
    "confirming_equity_bonus": 0.20,
    "opposing_nasdaq_futures_penalty": 0.50,
    "usdkrw_adverse_move_pct": 0.20,
    "usdkrw_adverse_penalty": 0.25,
    "samsung_sox_sensitivity": 0.65,
    "market_equity_move_pct": 0.75,
    "market_sox_move_pct": 3.0,
    "market_futures_move_pct": 0.30,
    "market_usdkrw_move_pct": 0.30,
    "market_us10y_delta": 0.05,
    "market_vix_move_pct": 5.0,
    "market_risk_on_score": 1.5,
    "market_strong_risk_on_score": 4.0,
    "pullback_retrace_pct": 0.50,
    "reaction_divergence_gap_pct": 0.30,
    "neutral_fair_gap_pct": 0.50,
}

PREOPEN_CAPTURE_TIME = "08:50"
PREOPEN_CAPTURE_DEADLINE = "08:59:59"

EXPERIMENT_GUARDS = {
    "prospective_only": True,
    "historical_backfill_allowed": False,
    "threshold_optimization_allowed": False,
    "machine_learning_allowed": False,
    "order_intent_allowed": False,
    "executor_connection_allowed": False,
    "main_strategy_change_allowed": False,
}
