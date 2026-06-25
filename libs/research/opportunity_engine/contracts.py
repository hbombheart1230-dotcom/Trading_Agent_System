from __future__ import annotations


PROGRAM_ID = "Q11_OPENING_SURGE_MARKET_REVERSAL"
PROGRAM_NAME = "Q11 Opening Surge & Market Reversal Research"
SIGNALS_SCHEMA = "opportunity_engine_signals.v1"
TRADES_SCHEMA = "opportunity_engine_virtual_trades.v1"
REPORT_SCHEMA = "opportunity_engine_daily_report.v1"

DEFAULT_SYMBOLS = ("005930", "000660", "009150")
DEFAULT_SLIPPAGE_PCT = 0.05
OPENING_WINDOW_START_MINUTE = 9 * 60
OPENING_WINDOW_END_MINUTE = 10 * 60

PROHIBITED_RUNTIME_DEPENDENCIES = (
    "graphs.nodes",
    "libs.runtime.commander",
    "libs.runtime.execution",
    "libs.runtime.quant.shadow_candidates",
    "libs.reporting.evaluation",
)
