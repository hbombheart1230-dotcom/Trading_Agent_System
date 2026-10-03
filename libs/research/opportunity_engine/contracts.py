from __future__ import annotations


PROGRAM_ID = "Q11_OPENING_SURGE_MARKET_REVERSAL"
PROGRAM_NAME = "Q11 Opening Surge & Market Reversal Research"
SIGNALS_SCHEMA = "opportunity_engine_signals.v1"
# UEF-4B-5 FIX1 source-contract repair: v2 adds `observed_price` to every
# OBSERVED forward/EOD checkpoint in `_forward_returns()` (simulator.py)
# -- the exact candle close each checkpoint's own return/MFE/MAE were
# computed from, never persisted in v1. Additive only; return/MFE/MAE/
# observed_epoch selection semantics are byte-for-byte unchanged. v1
# artifacts remain real primary evidence but cannot be losslessly
# canonicalized (no persisted observed_price for a PRICE_BASED
# checkpoint) -- see `virtual_probe_adapter.py`'s own explicit v1 block.
TRADES_SCHEMA = "opportunity_engine_virtual_trades.v2"
TRADES_SCHEMA_LEGACY_V1 = "opportunity_engine_virtual_trades.v1"
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
