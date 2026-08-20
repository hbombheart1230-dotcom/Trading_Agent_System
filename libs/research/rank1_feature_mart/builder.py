from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .chart_features import build_rank1_chart_snapshot
from .contracts import BEHAVIOR_EFFECT, SCHEMA_VERSION
from .loaders import canonical_scanner_candidate, intrinsic_candidate, iso_epoch
from .outcomes import build_original_hold_path
from .strategy_choice_observation import build_strategy_choice_observation


KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _band(value: float | None, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    if value is None:
        return "MISSING"
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def _historical_identity(row: Mapping[str, Any]) -> tuple[int, int, float]:
    decision_epoch = iso_epoch(row.get("decision_time_kst"))
    baseline_epoch = iso_epoch(row.get("virtual_buy_time_kst"))
    return decision_epoch, baseline_epoch, float(row.get("virtual_buy_price") or 0.0)


def _prospective_identity(row: Mapping[str, Any]) -> tuple[int, int, float]:
    return (
        int(row.get("decision_epoch") or 0),
        int(row.get("baseline_epoch") or 0),
        float(row.get("baseline_price") or 0.0),
    )


def _prospective_fallback(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    mapping = {"+5m": "return_5m_pct", "+15m": "return_15m_pct", "+30m": "net_return_30m_pct", "+60m": "return_60m_pct", "EOD": "return_eod_pct"}
    checkpoints = row.get("checkpoints") if isinstance(row.get("checkpoints"), Mapping) else {}
    for label, field in mapping.items():
        checkpoint = checkpoints.get(label) if isinstance(checkpoints.get(label), Mapping) else {}
        if str(checkpoint.get("status") or "").lower() == "observed":
            result[field] = checkpoint.get("live_net_return_pct")
    return result


def _market_snapshot(row: Mapping[str, Any], *, prospective: bool) -> dict[str, Any]:
    observation = row.get("opening_observability") if prospective and isinstance(row.get("opening_observability"), Mapping) else {}
    point_in_time = row.get("market_snapshot") if prospective and isinstance(row.get("market_snapshot"), Mapping) else {}
    if not point_in_time and isinstance(observation.get("market_snapshot"), Mapping):
        point_in_time = observation.get("market_snapshot")
    asset = observation.get("asset_observation") if isinstance(observation.get("asset_observation"), Mapping) else {}
    market_return = _number(point_in_time.get("kospi_pct")) if prospective else _number(row.get("kospi_pct"))
    if market_return is None and prospective:
        market_return = _number(observation.get("market_return_pct"))
    exposure = str(asset.get("exposure_direction") or "LONG_RISK_OR_OTHER")
    aligned = None
    if market_return not in (None, 0.0):
        inverse = "INVERSE" in exposure.upper()
        aligned = bool((market_return > 0.0 and not inverse) or (market_return < 0.0 and inverse))
    return {
        "market_return_pct": market_return,
        "kospi_pct": _number(point_in_time.get("kospi_pct")) if prospective else _number(row.get("kospi_pct")),
        "kosdaq_pct": _number(point_in_time.get("kosdaq_pct")) if prospective else _number(row.get("kosdaq_pct")),
        "kospi200_pct": _number(point_in_time.get("kospi200_pct")) if prospective else _number(row.get("kospi200_pct")),
        "krx_night_futures_pct": _number(point_in_time.get("krx_night_futures_pct")) if prospective else _number(row.get("krx_night_futures_pct")),
        "snapshot_epoch": int(point_in_time.get("snapshot_epoch") or 0) or None,
        "snapshot_time_kst": str(point_in_time.get("snapshot_time_kst") or ""),
        "snapshot_age_sec": int(point_in_time.get("snapshot_age_sec") or 0) if point_in_time.get("snapshot_age_sec") is not None else None,
        "snapshot_source_path": str(point_in_time.get("source_path") or ""),
        "snapshot_selection_policy": str(point_in_time.get("selection_policy") or ""),
        "snapshot_evidence_status": str(point_in_time.get("evidence_status") or ""),
        "nasdaq_pct": _number(row.get("nasdaq_pct")),
        "vix_level": _number(row.get("vix_level")),
        "market_rising": _number(row.get("market_rising")),
        "market_falling": _number(row.get("market_falling")),
        "engine_regime": str(row.get("engine_regime") or "MISSING"),
        "asset_class": str(asset.get("asset_class") or "MISSING"),
        "exposure_direction": exposure,
        "exposure_alignment": aligned,
    }


def _scanner_snapshot(
    row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    prospective: bool,
    canonical_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    observation = row.get("opening_observability") if prospective and isinstance(row.get("opening_observability"), Mapping) else {}
    sources = candidate.get("sources") if isinstance(candidate.get("sources"), list) else row.get("sources")
    sources = [str(value) for value in sources or []]
    score = _number(candidate.get("score_total"))
    if score is None:
        score = _number(row.get("score_total" if prospective else "scanner_score"))
    risk = _number(candidate.get("risk_score"))
    if risk is None:
        risk = _number(row.get("risk_score"))
    relative_volume = _number(observation.get("opening_relative_volume")) if prospective else _number(row.get("opening_relative_volume"))
    breakdown = dict(
        candidate.get("score_breakdown")
        or canonical_candidate.get("score_breakdown")
        or row.get("score_breakdown")
        or {}
    )
    directional_keys = (
        "momentum",
        "trend",
        "ma_alignment",
        "adx_trend",
        "volume_surge",
        "intraday_strength",
        "theme_boost",
    )
    directional_component_count = sum(
        (_number(breakdown.get(key)) or 0.0) > 0.0 for key in directional_keys
    )
    theme_match = canonical_candidate.get("theme_match")
    if not isinstance(theme_match, bool):
        theme_match = None
    if "top_change_rate" in sources:
        candidate_setup = "FRESH_CHANGE_ACTIVATION"
    elif directional_component_count >= 4:
        candidate_setup = "DIRECTIONAL_BREADTH"
    elif set(sources).issubset({"top_value", "top_volume"}):
        candidate_setup = "LIQUIDITY_ONLY"
    else:
        candidate_setup = "UNCLASSIFIED"
    source_observations = (
        candidate.get("source_observations")
        if isinstance(candidate.get("source_observations"), Mapping)
        else canonical_candidate.get("source_observations")
    )
    source_observations = (
        dict(source_observations) if isinstance(source_observations, Mapping) else {}
    )
    top_change_observation = source_observations.get("top_change_rate")
    top_change_observation = (
        dict(top_change_observation)
        if isinstance(top_change_observation, Mapping)
        else {}
    )
    return {
        "rank": int(candidate.get("rank") or row.get("rank") or 1),
        "score_total": score,
        "score_band": _band(score, (0.75, 1.0, 1.25), ("LOW", "MID", "HIGH", "VERY_HIGH")),
        "risk_score": risk,
        "risk_band": _band(risk, (0.4, 0.7), ("LOW", "MEDIUM", "HIGH")),
        "confidence": _number(candidate.get("confidence")) or _number(row.get("confidence")),
        "sources": sources,
        "source_top_volume": "top_volume" in sources,
        "source_top_value": "top_value" in sources,
        "source_top_change_rate": "top_change_rate" in sources,
        "source_observations": source_observations,
        "top_change_rate_observation": top_change_observation,
        "top_change_rate_observation_status": (
            "OBSERVED_POINT_IN_TIME"
            if top_change_observation
            else (
                "NOT_CAPTURED_LEGACY"
                if "top_change_rate" in sources
                else "NOT_APPLICABLE"
            )
        ),
        "score_breakdown": breakdown,
        "directional_component_count": directional_component_count,
        "directional_component_keys": list(directional_keys),
        "candidate_setup": candidate_setup,
        "theme_match": theme_match,
        "theme_evidence_status": (
            "CANONICAL_BOOLEAN_ONLY" if theme_match is not None else "MISSING"
        ),
        "matched_theme_names": [],
        "matched_theme_names_status": (
            "NOT_PERSISTED_BY_SOURCE" if theme_match is not None else "MISSING"
        ),
        "relative_volume": relative_volume,
        "relative_volume_band": _band(relative_volume, (0.5, 1.0, 4.0), ("LOW", "MODERATE_LOW", "MODERATE", "EXTREME")),
        "prior_rank1_observations_5m": int(observation.get("prior_rank1_observations_5m") or row.get("rank1_prev5m_observations") or 0),
    }


def _pipeline_snapshot(row: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
    strategist = window.get("strategist_selection") if isinstance(window.get("strategist_selection"), Mapping) else {}
    commander = window.get("commander_final") if isinstance(window.get("commander_final"), Mapping) else {}
    return {
        "strategist_selected_symbol": str(strategist.get("selected_symbol") or row.get("strategist_selected_symbol") or ""),
        "strategist_relation": str(row.get("strategist_relation") or "MISSING"),
        "monitor_candidate_symbol": str(row.get("monitor_candidate_symbol") or ""),
        "monitor_intent": str(row.get("monitor_intent") or "MISSING"),
        "commander_decision": str(commander.get("decision") or row.get("commander_decision") or "MISSING"),
        "commander_reason": str(commander.get("reason") or row.get("commander_reason") or ""),
        "dominant_block_reason": str(row.get("dominant_block_reason") or ""),
    }


def _strategy_snapshot(row: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
    strategist = window.get("strategist_selection") if isinstance(window.get("strategist_selection"), Mapping) else {}
    canonical = window.get("_canonical_strategist")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    policy = canonical.get("policy_selected")
    policy = policy if isinstance(policy, Mapping) else {}
    strategy_policy = policy.get("strategy_policy")
    strategy_policy = strategy_policy if isinstance(strategy_policy, Mapping) else {}
    market_policy = strategy_policy.get("market_policy")
    market_policy = market_policy if isinstance(market_policy, Mapping) else {}
    theme_policy = market_policy.get("theme_policy")
    theme_policy = theme_policy if isinstance(theme_policy, Mapping) else {}
    return {
        "scenario": str(row.get("strategist_scenario") or strategist.get("scenario") or canonical.get("market_regime") or "MISSING"),
        "playbook": str(row.get("playbook") or row.get("strategist_playbook") or strategist.get("playbook") or canonical.get("playbook") or "MISSING"),
        "market_playbook": str(canonical.get("final_playbook") or canonical.get("playbook") or strategist.get("playbook") or "MISSING"),
        "tactical_strategy": str(canonical.get("tactical_strategy") or row.get("tactic_id") or "MISSING"),
        "tactical_subtype": str(canonical.get("tactical_subtype") or "MISSING"),
        "tactic_id": str(row.get("tactic_id") or canonical.get("tactical_strategy") or "MISSING"),
        "entry_horizon": str(row.get("strategy_horizon") or canonical.get("strategy_horizon") or strategist.get("strategy_horizon") or strategist.get("horizon") or "MISSING"),
        "strategy_scores": dict(canonical.get("strategy_scores") or {}),
        "preferred_themes": [str(value) for value in theme_policy.get("preferred_themes") or []],
        "theme_strength": dict(theme_policy.get("theme_strength") or canonical.get("theme_strength") or {}),
        "canonical_evidence_status": "OBSERVED" if canonical else "MISSING",
    }


def _merge_opening_chart_observation(
    chart: dict[str, Any], row: Mapping[str, Any], *, prospective: bool
) -> dict[str, Any]:
    if not prospective:
        return chart
    observation = row.get("opening_observability")
    observation = observation if isinstance(observation, Mapping) else {}
    observed_count = int(observation.get("completed_bar_count_at_decision") or 0)
    computed_count = int(chart.get("completed_bar_count") or 0)
    chart["computed_completed_bar_count"] = computed_count
    chart["opening_observation_completed_bar_count"] = observed_count
    if computed_count >= observed_count or observed_count <= 0:
        chart["evidence_source"] = (
            "MINUTE_CACHE"
            if computed_count > 0
            else "NO_COMPLETED_BAR_AT_DECISION"
        )
        return chart
    decision_epoch = int(row.get("decision_epoch") or 0)
    chart.update(
        {
            "status": "PARTIAL_OPENING_OBSERVATION_FALLBACK",
            "completed_bar_count": observed_count,
            "feature_max_epoch": decision_epoch - (decision_epoch % 60),
            "completed_return_1m_pct": _number(
                observation.get("completed_return_1m_pct")
            ),
            "above_vwap": observation.get("above_vwap"),
            "evidence_source": "OPENING_SHADOW_POINT_IN_TIME_FALLBACK",
            "cache_coverage_gap": True,
        }
    )
    return chart


def build_episode(
    *,
    row: Mapping[str, Any],
    prospective: bool,
    window: Mapping[str, Any],
    minute_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    longitudinal: Mapping[str, Any],
) -> dict[str, Any]:
    day = str(row.get("day") or "")
    symbol = str(row.get("symbol") or "").zfill(6)
    decision_epoch, baseline_epoch, baseline_price = _prospective_identity(row) if prospective else _historical_identity(row)
    candidate = intrinsic_candidate(window, symbol)
    canonical_candidate = canonical_scanner_candidate(window, symbol)
    if not candidate and prospective:
        observation = row.get("opening_observability") if isinstance(row.get("opening_observability"), Mapping) else {}
        candidate = dict(observation.get("candidate_snapshot") or {})
        candidate.setdefault("sources", list(row.get("sources") or []))
        candidate.setdefault("score_total", row.get("score_total"))
        candidate.setdefault("risk_score", row.get("risk_score"))
        candidate.setdefault("rank", 1)
    chart = build_rank1_chart_snapshot(
        day=day,
        decision_epoch=decision_epoch,
        minute_rows=minute_rows,
        daily_rows=daily_rows,
    )
    chart = _merge_opening_chart_observation(chart, row, prospective=prospective)
    fallback = _prospective_fallback(row) if prospective else dict(row)
    outcomes = build_original_hold_path(
        day=day,
        baseline_epoch=baseline_epoch,
        baseline_price=baseline_price,
        minute_rows=minute_rows,
        daily_rows=daily_rows,
        fallback=fallback,
        longitudinal=longitudinal,
    )
    decision_from_open = None
    if prospective:
        observation = row.get("opening_observability") if isinstance(row.get("opening_observability"), Mapping) else {}
        decision_from_open = observation.get("decision_from_open_sec")
    else:
        decision_from_open = row.get("decision_from_open_sec")
    scanner_snapshot = _scanner_snapshot(
        row,
        candidate,
        prospective=prospective,
        canonical_candidate=canonical_candidate,
    )
    strategy_snapshot = _strategy_snapshot(row, window)
    strategy_choice_observation = build_strategy_choice_observation(
        canonical_strategist=(
            window.get("_canonical_strategist")
            if isinstance(window.get("_canonical_strategist"), Mapping)
            else {}
        ),
        strategy=strategy_snapshot,
        scanner=scanner_snapshot,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "identity": {
            "episode_id": str(row.get("episode_id") or f"rank1:{day}:{symbol}:{decision_epoch}"),
            "cohort_source": "PROSPECTIVE_OPENING_SHADOW" if prospective else "HISTORICAL_DEEP_DIVE",
            "day": day,
            "decision_id": str(row.get("decision_id") or ""),
            "decision_epoch": decision_epoch,
            "decision_time_kst": datetime.fromtimestamp(decision_epoch, tz=KST).isoformat() if decision_epoch else "",
            "decision_from_open_sec": int(decision_from_open) if decision_from_open not in (None, "") else None,
            "symbol": symbol,
            "symbol_name": str(row.get("symbol_name") or ((row.get("opening_observability") or {}).get("asset_observation") or {}).get("symbol_name") or ""),
        },
        "market": _market_snapshot(row, prospective=prospective),
        "scanner": scanner_snapshot,
        "strategy": strategy_snapshot,
        "strategy_choice_observation": strategy_choice_observation,
        "chart": chart,
        "pipeline": _pipeline_snapshot(row, window),
        "execution_evidence": {
            "baseline_epoch": baseline_epoch,
            "baseline_price": baseline_price,
            "quote_status": str((((row.get("opening_observability") or {}).get("quote_snapshot") or {}).get("status") or row.get("microstructure_status") or "MISSING")),
            "spread_bps": (
                row.get("quote_spread_bps")
                if row.get("quote_spread_bps") is not None
                else (
                    _number(
                        ((row.get("opening_observability") or {}).get("quote_snapshot") or {}).get("spread_pct")
                    )
                    * 100.0
                    if _number(
                        ((row.get("opening_observability") or {}).get("quote_snapshot") or {}).get("spread_pct")
                    )
                    is not None
                    else None
                )
            ),
            "tradability_status": str(
                ((row.get("opening_observability") or {}).get("execution_evidence") or {}).get("status")
                or "MISSING"
            ),
            "missing_fields": list(
                ((row.get("opening_observability") or {}).get("execution_evidence") or {}).get("missing_fields")
                or []
            ),
        },
        "outcomes": outcomes,
        "source_refs": {
            "q9_window_present": bool(window),
            "minute_row_count": len(minute_rows),
            "daily_row_count": len(daily_rows),
            "canonical_strategist_present": bool(window.get("_canonical_strategist")),
            "canonical_scanner_present": bool(window.get("_canonical_scanner")),
        },
    }
