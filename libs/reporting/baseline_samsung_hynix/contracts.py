from __future__ import annotations


SYMBOLS = (
    {"symbol": "005930", "ticker": "005930.KS", "name": "Samsung Electronics"},
    {"symbol": "000660", "ticker": "000660.KS", "name": "SK Hynix"},
)
SYMBOL_CODES = tuple(row["symbol"] for row in SYMBOLS)
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "+120m", "+180m", "EOD")
DEFAULT_SLIPPAGE_PCT = 0.05

DECISIONS_SCHEMA = "baseline_samsung_hynix_decisions.v1"
FORWARD_SCHEMA = "baseline_samsung_hynix_forward_returns.v1"
REPORT_SCHEMA = "baseline_samsung_hynix_daily_report.v1"

ENTRY_RULES = (
    "price_above_vwap_or_short_ma",
    "volume_spike_vs_recent_average",
    "market_not_sharply_negative",
)
EXIT_RULES = (
    "price_below_vwap_and_short_ma",
    "end_of_regular_session",
)
