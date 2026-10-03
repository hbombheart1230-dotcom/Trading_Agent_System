from __future__ import annotations

from typing import Any, Mapping

from .contracts import THRESHOLDS


EXPECTED_GAP_PCT = {
    "STRONG_POSITIVE": 2.0, "POSITIVE": 0.8, "NEUTRAL": 0.0,
    "NEGATIVE": -0.8, "STRONG_NEGATIVE": -2.0,
    "STRONG_RISK_ON": 2.0, "RISK_ON": 0.8,
    "RISK_OFF": -0.8, "STRONG_RISK_OFF": -2.0,
}


def classify_reaction(*, expected_state: str, opening_gap_pct: float | None) -> str:
    if opening_gap_pct is None:
        return "INSUFFICIENT_EVIDENCE"
    expected = EXPECTED_GAP_PCT.get(expected_state, 0.0)
    if expected == 0.0:
        return "FAIR_REACTION" if abs(opening_gap_pct) <= THRESHOLDS["neutral_fair_gap_pct"] else "DIVERGENCE"
    if opening_gap_pct * expected < 0 and abs(opening_gap_pct) >= THRESHOLDS["reaction_divergence_gap_pct"]:
        return "DIVERGENCE"
    ratio = abs(opening_gap_pct) / abs(expected)
    if ratio < 0.5:
        return "UNDERREACTION"
    if ratio > 1.5:
        return "OVERREACTION"
    return "FAIR_REACTION"


def build_expected_actual(
    *, signals: Mapping[str, Any], reactions: Mapping[str, Any], samsung_event: Mapping[str, Any]
) -> dict[str, Any]:
    states = {
        "samsung": str((signals.get("samsung") or {}).get("state") or "NEUTRAL"),
        "sk_hynix": str((signals.get("sk_hynix") or {}).get("state") or "NEUTRAL"),
        "kospi": str((signals.get("korea_market") or {}).get("state") or "NEUTRAL"),
        "kosdaq": str((signals.get("korea_market") or {}).get("state") or "NEUTRAL"),
    }
    rows = []
    targets = reactions.get("targets") or {}
    for key, expected_state in states.items():
        actual = targets.get(key) or {}
        event = bool(samsung_event.get("samsung_specific_event")) if key == "samsung" else False
        extension_state = (
            str((signals.get("hynix_extension") or {}).get("state") or "UNKNOWN")
            if key == "sk_hynix" else None
        )
        rows.append(
            {
                "target": key,
                "expected_state": expected_state,
                "expected_gap_pct": EXPECTED_GAP_PCT.get(expected_state, 0.0),
                "opening_gap_pct": actual.get("opening_gap_pct"),
                "reaction_state": classify_reaction(expected_state=expected_state, opening_gap_pct=actual.get("opening_gap_pct")),
                "evaluation_bucket": "SAMSUNG_SPECIFIC_EVENT" if event else "LEAD_MARKET_SIGNAL",
                "excluded_from_pure_signal_comparison": event,
                "extension_state": extension_state,
            }
        )
    return {"rows": rows}
