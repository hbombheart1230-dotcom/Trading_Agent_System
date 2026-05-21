from __future__ import annotations

from typing import Any, Dict, List, Tuple

from libs.runtime.quant.contracts import PULLBACK_SUBTYPES
from libs.runtime.quant.tactics import tactic_catalog


PLAYBOOKS: Tuple[str, ...] = ("breakout", "pullback", "reversal", "defensive")
SCANNER_BIASES: Tuple[str, ...] = ("large_cap", "leader", "momentum", "value")
TRADE_AGGRESSIVENESS_LEVELS: Tuple[str, ...] = ("low", "medium", "high")
RISK_TONES: Tuple[str, ...] = ("conservative", "normal", "aggressive")
MONITOR_GUIDANCE_VALUES: Tuple[str, ...] = ("hold_through_noise", "defensive_exit", "quick_take_profit")
MARKET_REGIMES: Tuple[str, ...] = ("risk_on", "neutral", "risk_off")
MARKET_SENTIMENTS: Tuple[str, ...] = ("bullish", "neutral", "bearish")

TACTICAL_SUBTYPES: Tuple[str, ...] = PULLBACK_SUBTYPES

PLAYBOOK_DEFAULT = "defensive"
SCANNER_BIAS_DEFAULT = "leader"
TRADE_AGGRESSIVENESS_DEFAULT = "medium"
RISK_TONE_DEFAULT = "normal"
MONITOR_GUIDANCE_DEFAULT = "defensive_exit"
MARKET_REGIME_DEFAULT = "neutral"
MARKET_SENTIMENT_DEFAULT = "neutral"


def normalize_contract_value(value: Any, *, allowed: Tuple[str, ...], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def playbook_inventory() -> Dict[str, List[str]]:
    quant_catalog = tactic_catalog()
    return {
        "playbooks": list(PLAYBOOKS),
        "scanner_biases": list(SCANNER_BIASES),
        "trade_aggressiveness_levels": list(TRADE_AGGRESSIVENESS_LEVELS),
        "risk_tones": list(RISK_TONES),
        "monitor_guidance_values": list(MONITOR_GUIDANCE_VALUES),
        "market_regimes": list(MARKET_REGIMES),
        "market_sentiments": list(MARKET_SENTIMENTS),
        "tactical_subtypes": list(TACTICAL_SUBTYPES),
        "tactic_ids": list(quant_catalog.get("tactic_ids") or []),
        "legacy_tactic_aliases": dict(quant_catalog.get("legacy_aliases") or {}),
        "default_tactic_by_playbook": dict(quant_catalog.get("default_tactic_by_playbook") or {}),
    }
