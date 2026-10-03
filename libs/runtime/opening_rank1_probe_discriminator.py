from __future__ import annotations

from typing import Any


def _value(value: Any, fallback: str = "MISSING") -> str:
    text = str(value or "").strip()
    return text.upper() if text else fallback


def _asset_family(asset_class: Any) -> str:
    value = _value(asset_class, "UNKNOWN")
    if value == "COMMON_STOCK":
        return "COMMON_STOCK"
    if "ETF" in value:
        return "ETF"
    return value


def build_opening_probe_discriminator(
    *,
    lane_condition: Any,
    asset_class: Any,
    risk_band: Any,
    candidate_setup: Any,
    strategy_horizon: Any,
) -> dict[str, Any]:
    """Stable pre-outcome identity for one controlled Opening Alpha cell."""
    dimensions = {
        "lane_condition": _value(lane_condition, "NOT_ELIGIBLE"),
        "asset_family": _asset_family(asset_class),
        "risk_band": _value(risk_band),
        "candidate_setup": _value(candidate_setup),
        "strategy_horizon": _value(strategy_horizon),
    }
    return {
        "schema_version": "opening_probe_discriminator.v1",
        "behavior_effect": "OBSERVATION_ONLY",
        "eligibility_effect": "NONE",
        "cell_id": "|".join(dimensions.values()),
        **dimensions,
    }


__all__ = ["build_opening_probe_discriminator"]
