from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "monitor_directional_edge_estimate.v1"

_HORIZON_EVIDENCE = {
    "scalp": ("5m", "avg_return_5m_pct"),
    "intraday": ("30m", "avg_return_30m_pct"),
    "overnight_probe": ("next_open", "avg_return_next_open_pct"),
    "1_2day_swing": ("1d", "avg_return_1d_pct"),
}

_HORIZON_ALIASES = {
    "overnight": "overnight_probe",
    "swing": "1_2day_swing",
    "swing_1_2day": "1_2day_swing",
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _setup_lane(reason: str, pattern: str) -> str:
    text = f"{reason} {pattern}".lower()
    if "opening" in text:
        return "opening_momentum"
    if "breakout" in text or "recent_high" in text:
        return "breakout_readiness"
    if "pullback" in text or "reclaim" in text or "vwap" in text:
        return "vwap_reclaim"
    if "volume" in text:
        return "volume_confirmation"
    if "human_chart" in text:
        return "human_chart_sanity"
    return "confirmed_or_other"


def _memory_packets(state: Mapping[str, Any]) -> dict[str, Any]:
    strategist_output = _mapping(state.get("strategist_output"))
    packets = _mapping(strategist_output.get("memory_packets"))
    if packets:
        return packets

    strategist_cache = _mapping(state.get("strategist_output_cache"))
    output = _mapping(strategist_cache.get("output")) or strategist_cache
    packets = _mapping(output.get("memory_packets"))
    if packets:
        return packets

    persisted = _mapping(state.get("persisted_state"))
    strategist_cache = _mapping(persisted.get("strategist_output_cache"))
    output = _mapping(strategist_cache.get("output")) or strategist_cache
    return _mapping(output.get("memory_packets"))


def _performance_memory(state: Mapping[str, Any]) -> dict[str, Any]:
    packets = _memory_packets(state)
    monthly = _mapping(packets.get("monthly_strategy_memory"))
    operator = _mapping(monthly.get("operator_summary"))
    shadow = _mapping(operator.get("quant_shadow_candidate_evaluation"))
    return _mapping(shadow.get("entry_lane_forward_outcomes"))


def _profile(rows: Any, name: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {}
    return next(
        (
            dict(row)
            for row in rows
            if isinstance(row, Mapping) and str(row.get("name") or "") == name
        ),
        {},
    )


def estimate_horizon_directional_edge(
    *,
    state: Mapping[str, Any],
    selected: Mapping[str, Any],
    entry_info: Mapping[str, Any],
    strategy_frame: Mapping[str, Any],
    min_observed_count: int = 20,
    min_observed_days: int = 5,
    min_coverage: float = 0.70,
    max_sample_concentration: float = 0.70,
) -> dict[str, Any]:
    """Estimate directional edge from prior shadow outcomes only.

    ATR, volatility, desired take-profit, and current-day forward data are not
    accepted as directional evidence.
    """

    requested_horizon = str(
        strategy_frame.get("strategy_horizon")
        or strategy_frame.get("horizon")
        or "intraday"
    ).strip().lower()
    horizon = _HORIZON_ALIASES.get(requested_horizon, requested_horizon)
    horizon_evidence = _HORIZON_EVIDENCE.get(horizon)
    reason = str(entry_info.get("reason") or "")
    pattern = str(entry_info.get("pattern") or "")
    lane = _setup_lane(reason, pattern)
    memory = _performance_memory(state)

    if horizon_evidence is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "behavior_effect": "entry_cost_evidence",
            "available": False,
            "strategy_horizon": horizon,
            "requested_strategy_horizon": requested_horizon,
            "forward_horizon": None,
            "return_field": None,
            "setup_lane": lane,
            "source_period": "monthly_strategy_memory",
            "expected_move_pct": None,
            "expected_move_ratio": None,
            "reason": "unsupported_strategy_horizon",
            "failed_requirements": ["canonical_horizon_mapping_missing"],
        }

    horizon_label, return_field = horizon_evidence
    subtype = _profile(memory.get("by_subtype"), reason) if reason else {}
    lane_profile = _profile(memory.get("by_primary_lane"), lane)
    profile = subtype or lane_profile
    profile_scope = "subtype" if subtype else "primary_lane"
    profile_name = str(profile.get("name") or lane)

    base = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "entry_cost_evidence",
        "available": False,
        "strategy_horizon": horizon,
        "requested_strategy_horizon": requested_horizon,
        "forward_horizon": horizon_label,
        "return_field": return_field,
        "setup_lane": lane,
        "profile_scope": profile_scope,
        "profile_name": profile_name,
        "source_period": "monthly_strategy_memory",
        "expected_move_pct": None,
        "expected_move_ratio": None,
    }
    if not profile:
        return {**base, "reason": "matching_performance_profile_missing"}

    observed_count = _int(profile.get("observed_count"))
    observed_days = _int(profile.get("observed_day_count"))
    coverage = _float(profile.get("coverage"))
    concentration = _float(profile.get("sample_concentration"), 1.0)
    expectancy_pct = profile.get(return_field)
    evidence = {
        "observed_count": observed_count,
        "observed_day_count": observed_days,
        "coverage": coverage,
        "sample_concentration": concentration,
    }
    if expectancy_pct in (None, ""):
        return {
            **base,
            **evidence,
            "reason": "horizon_matched_expectancy_missing",
            "failed_requirements": [f"{return_field}_missing"],
        }

    failed = []
    if observed_count < int(min_observed_count):
        failed.append("observed_count_below_minimum")
    if observed_days < int(min_observed_days):
        failed.append("observed_days_below_minimum")
    low_coverage_override = bool(
        coverage < float(min_coverage)
        and observed_count >= 100
        and observed_days >= 10
        and concentration <= 0.50
    )
    if coverage < float(min_coverage) and not low_coverage_override:
        failed.append("coverage_below_minimum")
    if concentration > float(max_sample_concentration):
        failed.append("sample_concentration_above_maximum")
    expectancy = _float(expectancy_pct)
    if expectancy <= 0.0:
        failed.append("historical_expectancy_not_positive")
    if failed:
        return {
            **base,
            **evidence,
            "historical_expectancy_pct": expectancy,
            "reason": "evidence_not_eligible",
            "failed_requirements": failed,
        }

    expected_move_ratio = round(expectancy / 100.0, 8)
    return {
        **base,
        **evidence,
        "available": True,
        "reason": "eligible_historical_directional_expectancy",
        "historical_expectancy_pct": expectancy,
        "expected_move_pct": expected_move_ratio,
        "expected_move_ratio": expected_move_ratio,
        "low_coverage_override": low_coverage_override,
        "source": (
            f"performance_memory.monthly.{profile_scope}.{profile_name}."
            f"{return_field}"
        ),
    }


def apply_horizon_directional_edge(
    *,
    state: Mapping[str, Any],
    selected: Mapping[str, Any],
    entry_info: dict[str, Any],
    strategy_frame: Mapping[str, Any],
) -> dict[str, Any]:
    estimate = estimate_horizon_directional_edge(
        state=state,
        selected=selected,
        entry_info=entry_info,
        strategy_frame=strategy_frame,
    )
    metrics = _mapping(entry_info.get("metrics"))
    if estimate.get("available") and metrics.get("expected_move_pct") in (None, ""):
        metrics["expected_move_pct"] = estimate.get("expected_move_pct")
        metrics["expected_move_source"] = estimate.get("source")
    entry_info["metrics"] = metrics
    entry_info["directional_edge_estimate"] = dict(estimate)
    return estimate


__all__ = [
    "apply_horizon_directional_edge",
    "estimate_horizon_directional_edge",
]
