from __future__ import annotations

from typing import Any, Dict, Mapping


_RISK_OFF_RAIL_MARKERS = (
    "risk_off",
    "global_risk_off",
    "krx_night_futures_gap_down",
    "breadth_collapse",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _is_risk_off_context(*, market_regime: Any, market_regime_rail: Any) -> bool:
    regime = _lower(market_regime)
    rail = _lower(market_regime_rail)
    return regime == "risk_off" or any(marker in rail for marker in _RISK_OFF_RAIL_MARKERS)


def _commander_exception_approved(commander_context: Mapping[str, Any] | None) -> bool:
    ctx = _as_mapping(commander_context)
    for key in (
        "risk_off_defensive_observe_entry_override",
        "risk_off_exception_approved",
        "commander_risk_off_exception_approved",
    ):
        raw = ctx.get(key)
        if isinstance(raw, bool):
            return bool(raw)
        if _lower(raw) in {"1", "true", "yes", "on", "approved"}:
            return True
    entry_control = _as_mapping(ctx.get("entry_control") or ctx.get("commander_entry_control"))
    raw = entry_control.get("risk_off_defensive_observe_entry_override") or entry_control.get(
        "risk_off_exception_approved"
    )
    if isinstance(raw, bool):
        return bool(raw)
    return _lower(raw) in {"1", "true", "yes", "on", "approved"}


def evaluate_risk_off_defensive_observe_policy(
    *,
    tactic_id: str,
    market_regime: Any = "",
    market_regime_rail: Any = "",
    entry_info: Mapping[str, Any] | None = None,
    commander_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Block live entries when defensive_observe is being used as the entry tactic in risk-off rails."""
    tactic = _lower(tactic_id)
    entry = _as_mapping(entry_info)
    risk_off = _is_risk_off_context(market_regime=market_regime, market_regime_rail=market_regime_rail)
    triggered = bool(entry.get("triggered"))
    override_approved = _commander_exception_approved(commander_context)
    blocked = bool(risk_off and tactic == "defensive_observe" and triggered and not override_approved)
    reason = "risk_off_defensive_observe_no_entry" if blocked else ""
    return {
        "schema_version": "risk_off_defensive_observe_policy.v1",
        "policy": "risk_off_defensive_observe_no_entry_policy",
        "behavior_effect": "entry_guard_enforced",
        "risk_off_active": bool(risk_off),
        "tactic_id": tactic,
        "market_regime": _text(market_regime),
        "market_regime_rail": _text(market_regime_rail),
        "entry_triggered": bool(triggered),
        "commander_exception_approved": bool(override_approved),
        "blocked": bool(blocked),
        "reason": reason,
    }


__all__ = ["evaluate_risk_off_defensive_observe_policy"]
