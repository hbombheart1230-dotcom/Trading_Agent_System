from __future__ import annotations

from typing import Any, Mapping

from .metrics import number


def opening_archetype(row: Mapping[str, Any]) -> str:
    kospi = number(row.get("kospi_pct"))
    extension = number(row.get("entry_vs_prior_close_pct"))
    seconds = number(row.get("decision_from_open_sec"))
    if (kospi is not None and kospi <= -3.0) or (
        extension is not None and extension <= -8.0
    ):
        return "DISLOCATION_REBOUND"
    if seconds is None:
        return "UNKNOWN_TIME"
    if seconds < 60:
        return "IMMEDIATE_0_1M"
    if seconds < 300:
        return "EARLY_1_5M"
    if seconds < 1200:
        return "MATURED_5_20M"
    return "OTHER"


def point_in_time_cohorts(row: Mapping[str, Any]) -> list[str]:
    seconds = number(row.get("decision_from_open_sec"))
    previous_rank = number(row.get("rank1_prev5m_observations")) or 0.0
    return_1m = number(row.get("precompleted_return_1m_pct"))
    relative_volume = number(row.get("opening_relative_volume"))
    kospi = number(row.get("kospi_pct"))
    extension = number(row.get("entry_vs_prior_close_pct"))
    confirmed = previous_rank >= 1 and return_1m is not None and return_1m > 0
    moderate_volume = relative_volume is not None and 0.5 <= relative_volume <= 4.0
    dislocation = bool(
        (kospi is not None and kospi <= -3.0)
        or (extension is not None and extension <= -8.0)
    )

    cohorts = []
    if seconds is not None and seconds < 300:
        cohorts.append("OPEN_0_5_ALL")
    if confirmed:
        cohorts.append("CONFIRMED_RANK_POSITIVE_1M")
        if moderate_volume:
            cohorts.append("CONFIRMED_RANK_POSITIVE_1M_MODERATE_VOLUME")
        if row.get("above_vwap") is True:
            cohorts.append("CONFIRMED_RANK_POSITIVE_1M_ABOVE_VWAP")
    if dislocation and moderate_volume:
        cohorts.append("DISLOCATION_MODERATE_VOLUME")
    return cohorts


def annotate_episode(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(row),
        "conditional_alpha_cohorts": point_in_time_cohorts(row),
        "opening_archetype": opening_archetype(row),
        "conditional_alpha_evidence": "POINT_IN_TIME_FEATURES_WITH_FORWARD_OUTCOMES",
    }
