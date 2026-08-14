from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..models.opportunities import (
    ForwardCheckpoint,
    OpportunityBlocker,
    OpportunityOutcome,
    OpportunitySignal,
)
from .trade_values import list_value, mapping, number, string_list, text_value, timestamp


def project_latest_signals(payload: dict[str, Any]) -> list[OpportunitySignal]:
    latest: dict[str, tuple[float, dict[str, Any]]] = {}
    for raw in list_value(payload.get("signals")):
        row = mapping(raw)
        symbol = text_value(row.get("symbol"))
        if not symbol:
            continue
        epoch = number(row.get("as_of_epoch")) or 0.0
        if symbol not in latest or epoch >= latest[symbol][0]:
            latest[symbol] = (epoch, row)
    return [_signal(row) for _, row in sorted(latest.values(), key=lambda item: item[0], reverse=True)]


def project_blockers(payload: dict[str, Any]) -> list[OpportunityBlocker]:
    projected = [_blocker(item) for item in list_value(payload.get("groups"))]
    return [item for item in projected if item is not None]


def project_outcomes(payload: dict[str, Any]) -> list[OpportunityOutcome]:
    projected = [_outcome(item) for item in list_value(payload.get("episodes"))]
    return [item for item in projected if item is not None]


def blocker_coverage(payload: dict[str, Any]) -> float | None:
    return number(mapping(payload.get("evaluation_trust_gate")).get("trusted_forward_coverage"))


def _signal(row: dict[str, Any]) -> OpportunitySignal:
    opportunity = mapping(row.get("opportunity"))
    features = mapping(row.get("symbol_features"))
    market = mapping(row.get("market"))
    epoch = number(row.get("as_of_epoch"))
    observed_at = datetime.fromtimestamp(epoch, UTC) if epoch is not None else None
    return OpportunitySignal(
        symbol=text_value(row.get("symbol")) or "UNKNOWN",
        observed_at=observed_at,
        price=number(features.get("price")),
        score=number(opportunity.get("score")),
        state=text_value(opportunity.get("state")),
        probe_candidate=bool(opportunity.get("probe_candidate")),
        probe_near_miss=bool(opportunity.get("probe_near_miss")),
        blocker_reasons=string_list(opportunity.get("probe_fail_reasons")),
        market_state=text_value(market.get("state")),
        market_relative_strength=number(features.get("market_relative_strength_proxy")),
        vwap_distance_pct=number(features.get("vwap_distance_pct")),
        volume_ratio=number(features.get("robust_volume_ratio")),
        breakout_5m=(bool(features.get("breakout_5m")) if features.get("breakout_5m") is not None else None),
    )


def _blocker(raw: Any) -> OpportunityBlocker | None:
    row = mapping(raw)
    reason = text_value(row.get("reason"))
    if not reason:
        return None
    return OpportunityBlocker(
        reason=reason,
        candidate_count=int(number(row.get("candidate_count")) or 0),
        observed_count=int(number(row.get("observed_count")) or 0),
        coverage=number(row.get("coverage")),
        positive_rate=number(row.get("positive_latest_rate")),
        missed_opportunity_rate=number(row.get("missed_opportunity_rate")),
        adverse_rate=number(row.get("adverse_rate")),
        average_latest_return_pct=number(row.get("avg_latest_return_pct")),
        decision=text_value(row.get("decision")),
    )


def _outcome(raw: Any) -> OpportunityOutcome | None:
    row = mapping(raw)
    opportunity_id = text_value(row.get("episode_id"))
    symbol = text_value(row.get("symbol"))
    if not opportunity_id or not symbol:
        return None
    asset = mapping(mapping(row.get("opening_observability")).get("asset_observation"))
    checkpoints = [
        _checkpoint(str(horizon), value)
        for horizon, value in mapping(row.get("checkpoints")).items()
    ]
    return OpportunityOutcome(
        opportunity_id=opportunity_id,
        symbol=symbol,
        symbol_name=text_value(asset.get("symbol_name")),
        observed_at=timestamp(row.get("decision_time_kst")),
        reference_entry_at=timestamp(row.get("entry_time_kst")),
        rank=int(number(row.get("rank"))) if number(row.get("rank")) is not None else None,
        score=number(row.get("score_total")),
        source_labels=string_list(row.get("sources")),
        prospective_eligible=bool(row.get("prospective_eligible")),
        checkpoints=checkpoints,
    )


def _checkpoint(horizon: str, raw: Any) -> ForwardCheckpoint:
    row = mapping(raw)
    return ForwardCheckpoint(
        horizon=horizon,
        status=text_value(row.get("status")) or "missing",
        gross_return_pct=number(row.get("gross_return_pct")),
        live_equivalent_net_return_pct=number(row.get("live_net_return_pct")),
        mock_broker_net_return_pct=number(row.get("mock_net_return_pct")),
        maximum_favorable_excursion_pct=number(row.get("mfe_pct")),
        maximum_adverse_excursion_pct=number(row.get("mae_pct")),
    )
