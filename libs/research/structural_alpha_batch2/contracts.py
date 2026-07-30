from __future__ import annotations

from libs.research.structural_alpha.contracts import (
    BEHAVIOR_EFFECT,
    CALIBRATION_END,
    CALIBRATION_START,
    END,
    EPISODE_GAP_SEC,
    GATES,
    HORIZONS,
    LIVE_COST_PCT,
    PRIMARY_HORIZON,
    RETROSPECTIVE_END,
    RETROSPECTIVE_START,
    START,
)


SCHEMA_VERSION = "structural_alpha_batch2.v1"
MARKET_PROXY_SYMBOLS = ("069500", "229200")
HYPOTHESES = {
    "H7_MARKET_SHOCK_RELATIVE_STRENGTH_REVERSAL": (
        "Market Shock Relative-Strength Reversal"
    ),
    "H8_OVERSOLD_MEAN_REVERSION": "Oversold Mean Reversion",
    "H9_TREND_PULLBACK_RESUMPTION": "Trend Pullback Resumption",
}
