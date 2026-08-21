from __future__ import annotations


PROGRAM_ID = "Q12_BTC_WOORI_TECH_BASELINE"
PROGRAM_NAME = "BTC-led Woori Technology Investment Baseline"
TARGET_SYMBOL = "041190"
TARGET_TICKER = "041190.KQ"
TARGET_NAME = "Woori Technology Investment"
HORIZONS = ("+5m", "+15m", "+30m", "EOD")
DEFAULT_SLIPPAGE_PCT = 0.05

DECISIONS_SCHEMA = "baseline_btc_woori_decisions.v2"
FORWARD_SCHEMA = "baseline_btc_woori_forward_returns.v1"
COMPARISON_SCHEMA = "baseline_btc_woori_comparison.v1"
REPORT_SCHEMA = "baseline_btc_woori_daily_report.v1"

ENTRY_RULES = (
    "btc_multihorizon_leading_signal_positive",
    "woori_volume_spike_or_breakout_confirmation",
    "woori_price_above_vwap_or_short_ma",
)
EXIT_RULES = (
    "forward_evaluation_horizons_only",
    "end_of_regular_session",
)
