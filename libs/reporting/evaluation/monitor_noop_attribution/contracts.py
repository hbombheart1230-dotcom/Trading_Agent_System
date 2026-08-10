from __future__ import annotations

from typing import Any, Mapping


HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")
EPISODE_GAP_SECONDS = 300


def blocker_family(commander: Mapping[str, Any]) -> str:
    observation = commander.get("monitor_observation")
    observation = observation if isinstance(observation, Mapping) else {}
    axis = str(observation.get("entry_primary_failure_axis") or "").lower()
    reason = str(
        commander.get("monitor_reason") or observation.get("reason") or ""
    ).lower()
    text = f"{axis} {reason}"
    if "cost" in text or "directional_edge" in text or "gross_edge" in text:
        return "COST_EDGE"
    if "vwap" in text and "reclaim" in text:
        return "VWAP_RECLAIM"
    if "pullback" in text or "mature" in text:
        return "PULLBACK_MATURITY"
    if "volume" in text:
        return "VOLUME_CONFIRMATION"
    if "breakout" in text:
        return "BREAKOUT_READINESS"
    if "chart" in text or "structure" in text or "low_break" in text:
        return "CHART_STRUCTURE"
    return "OTHER"
