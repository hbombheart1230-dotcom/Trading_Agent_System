from __future__ import annotations

from typing import Any, Dict, Mapping


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return bool(value)
    if value in (None, ""):
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def evaluate_promoted_entry_policy(
    *,
    tactic_id: str,
    suitability_tier: str,
    suitability_score: Any,
    factors: Mapping[str, Any] | None,
    cost_ok: bool,
) -> Dict[str, Any]:
    """Return promoted Q8 entry blockers that are deterministic before order placement."""
    tactic = str(tactic_id or "").strip()
    tier = str(suitability_tier or "unavailable").strip().lower() or "unavailable"
    score = _to_float(suitability_score, -1.0)
    f = dict(factors or {}) if isinstance(factors, Mapping) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    positives: list[str] = []

    if tactic != "vwap_reclaim_pullback":
        return {
            "schema_version": "promoted_entry_policy.v1",
            "blockers": blockers,
            "warnings": warnings,
            "positive_reasons": positives,
            "policy": "none",
            "behavior_effect": "entry_guard_enforced",
        }

    volume_ok = _to_bool(f.get("volume_ok"))
    pullback_ok = _to_bool(f.get("pullback_ok"))
    reclaim_ok = _to_bool(f.get("reclaim_ok"))
    breakout_ok = _to_bool(f.get("breakout_ok"))
    confidence = _to_float(f.get("confidence_score"), 0.0)
    threshold = _to_float(f.get("confidence_threshold"), 0.55)
    mature_confirmed = bool(
        cost_ok
        and volume_ok
        and (pullback_ok or breakout_ok)
        and reclaim_ok
        and confidence >= max(0.0, threshold + 0.03)
    )
    strong_suitability = bool(tier == "strong" or score >= 0.75)

    if not strong_suitability and not mature_confirmed:
        _append_unique(blockers, "vwap_pullback_promoted_quality_gate")
    elif mature_confirmed:
        _append_unique(positives, "vwap_pullback_mature_confirmed")
    else:
        _append_unique(warnings, "vwap_pullback_requires_active_monitor_confirmation")

    return {
        "schema_version": "promoted_entry_policy.v1",
        "blockers": blockers,
        "warnings": warnings,
        "positive_reasons": positives,
        "policy": "vwap_pullback_q8_quality_gate",
        "inputs": {
            "tactic_id": tactic,
            "suitability_tier": tier,
            "suitability_score": score if score >= 0.0 else None,
            "cost_ok": bool(cost_ok),
            "volume_ok": bool(volume_ok),
            "pullback_ok": bool(pullback_ok),
            "reclaim_ok": bool(reclaim_ok),
            "breakout_ok": bool(breakout_ok),
            "confidence_score": confidence,
            "confidence_threshold": threshold,
            "mature_confirmed": bool(mature_confirmed),
        },
        "behavior_effect": "entry_guard_enforced",
    }
