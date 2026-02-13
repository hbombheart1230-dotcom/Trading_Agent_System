"""Global market sentiment signals.

M18-3: Strategist can incorporate broad market regime (risk-on / risk-off)
using external data sources (e.g., yfinance, rates, FX).

In tests/DRY_RUN, callers should inject `state["mock_global_sentiment"]`
in [-1.0, +1.0]. Live integration can be added later without changing callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class GlobalSentiment:
    """Normalized market sentiment in [-1, +1]."""
    score: float
    notes: str = ""


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def get_global_sentiment(state: Dict[str, Any]) -> GlobalSentiment:
    """Return GlobalSentiment.

    Priority:
      1) state['mock_global_sentiment'] (tests / DRY_RUN)
      2) state['global_sentiment'] (precomputed upstream)
      3) default 0.0 (neutral)
    """
    if "mock_global_sentiment" in state:
        try:
            s = float(state["mock_global_sentiment"])
        except Exception:
            s = 0.0
        return GlobalSentiment(score=clamp(s, -1.0, 1.0), notes="mock")
    if isinstance(state.get("global_sentiment"), dict) and "score" in state["global_sentiment"]:
        try:
            s = float(state["global_sentiment"]["score"])
        except Exception:
            s = 0.0
        notes = str(state["global_sentiment"].get("notes") or "precomputed")
        return GlobalSentiment(score=clamp(s, -1.0, 1.0), notes=notes)
    return GlobalSentiment(score=0.0, notes="default_neutral")


def adjust_policy_by_sentiment(policy: Dict[str, Any], sentiment: GlobalSentiment) -> Dict[str, Any]:
    """Adjust risk thresholds based on market regime.

    The intent is: in risk-off (score < 0), be more conservative:
      - lower max_risk
      - increase min_confidence

    In risk-on (score > 0), slightly relax:
      - higher max_risk
      - lower min_confidence

    This returns a NEW dict (does not mutate input).
    """
    max_risk = float(policy.get("max_risk", 0.7))
    min_conf = float(policy.get("min_confidence", 0.6))

    # scale factor: up to 20% adjustment at extremes
    k = 0.20 * float(sentiment.score)

    # risk-on -> increase max_risk, risk-off -> decrease
    max_risk_adj = clamp(max_risk * (1.0 + k), 0.05, 1.0)

    # risk-on -> decrease min_confidence, risk-off -> increase
    min_conf_adj = clamp(min_conf * (1.0 - k), 0.05, 0.99)

    out = dict(policy)
    out["max_risk"] = max_risk_adj
    out["min_confidence"] = min_conf_adj
    out["global_sentiment"] = {"score": sentiment.score, "notes": sentiment.notes}
    return out
