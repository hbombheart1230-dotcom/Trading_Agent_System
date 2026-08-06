from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import defaultdict
from statistics import median
from typing import Any, Mapping

from .contracts import LIVE_COST_PCT


KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference <= 0.0:
        return None
    return round((value / reference - 1.0) * 100.0, 4)


def _first_number(rows: list[Mapping[str, Any]], *keys: str) -> float | None:
    for row in rows:
        for key in keys:
            value = _number(row.get(key))
            if value is not None:
                return value
    return None


def _completed_return(rows: list[Mapping[str, Any]], minutes: int) -> float | None:
    if len(rows) <= minutes:
        return None
    return _pct(
        _number(rows[-1].get("close")),
        _number(rows[-1 - minutes].get("close")),
    )


def _opening_relative_volume(
    *,
    completed: list[Mapping[str, Any]],
    reference_rows: list[Mapping[str, Any]],
    day: str,
) -> float | None:
    if not completed or not reference_rows:
        return None
    by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in reference_rows:
        epoch = int(row.get("ts") or 0)
        if epoch <= 0:
            continue
        row_day = datetime.fromtimestamp(epoch, tz=KST).date().isoformat()
        if row_day < day:
            by_day[row_day].append(row)
    references = []
    count = len(completed)
    for row_day in sorted(by_day)[-10:]:
        opening = sorted(
            by_day[row_day],
            key=lambda row: int(row.get("ts") or 0),
        )[:count]
        if len(opening) == count:
            references.append(sum(float(row.get("volume") or 0.0) for row in opening))
    current_volume = sum(float(row.get("volume") or 0.0) for row in completed)
    reference = median(references) if references else 0.0
    return round(current_volume / reference, 4) if reference > 0.0 else None


def _asset_observation(candidate: Mapping[str, Any]) -> dict[str, Any]:
    compact = candidate.get("compact_feature_snapshot")
    compact = compact if isinstance(compact, Mapping) else {}
    asset_class = str(
        candidate.get("asset_class_detected")
        or candidate.get("asset_class")
        or compact.get("asset_class_detected")
        or ""
    ).strip().lower()
    name = str(
        candidate.get("name")
        or candidate.get("symbol_name")
        or compact.get("name")
        or ""
    ).strip()
    upper_name = name.upper()
    if not asset_class:
        if "인버스" in name or "INVERSE" in upper_name:
            asset_class = "inverse_etf"
        elif "레버리지" in name or "LEVERAGE" in upper_name:
            asset_class = "leveraged_etf"
        elif "ETF" in upper_name:
            asset_class = "etf"
        elif name:
            asset_class = "common_stock"
        else:
            asset_class = "unknown"
    if asset_class == "inverse_etf":
        exposure_direction = "INVERSE_HEDGE"
    elif asset_class == "leveraged_etf":
        exposure_direction = "LEVERAGED_LONG_RISK"
    elif asset_class in {"common_stock", "etf", "active_etf", "futures_etf"}:
        exposure_direction = "LONG_RISK_OR_OTHER"
    else:
        exposure_direction = "UNKNOWN"
    return {
        "asset_class": asset_class,
        "exposure_direction": exposure_direction,
        "symbol_name": name or None,
        "status": "OBSERVED" if exposure_direction != "UNKNOWN" else "MISSING_METADATA",
    }


def _execution_evidence(
    *,
    completed: list[Mapping[str, Any]],
    best_bid: float | None,
    best_ask: float | None,
    spread_pct: float | None,
) -> dict[str, Any]:
    missing = []
    if not completed:
        missing.append("completed_minute_bar")
    if not best_bid or not best_ask:
        missing.append("best_bid_ask")
    if len(missing) == 2:
        status = "INSUFFICIENT"
    elif missing:
        status = "PARTIAL"
    else:
        status = "COMPLETE"
    return {
        "status": status,
        "missing_fields": missing,
        "spread_pct": spread_pct,
        "spread_exceeds_live_cost": (
            spread_pct is not None and spread_pct > LIVE_COST_PCT
        ),
        "live_round_trip_cost_pct": LIVE_COST_PCT,
    }


def _conditional_lanes(
    *,
    decision_from_open_sec: int,
    prior_rank1_observations_5m: int,
    completed_return_1m_pct: float | None,
    opening_relative_volume: float | None,
    above_vwap: bool | None,
    market_return_pct: float | None,
    entry_vs_prior_close_pct: float | None,
) -> dict[str, Any]:
    recurrent_missing = []
    if completed_return_1m_pct is None:
        recurrent_missing.append("completed_return_1m_pct")
    confirmed_recurrent = (
        prior_rank1_observations_5m >= 1
        and completed_return_1m_pct is not None
        and completed_return_1m_pct > 0.0
    )
    moderate_volume = (
        opening_relative_volume is not None
        and 0.5 <= opening_relative_volume <= 4.0
    )
    dislocation_known = (
        market_return_pct is not None
        or entry_vs_prior_close_pct is not None
    )
    dislocation = (
        (market_return_pct is not None and market_return_pct <= -3.0)
        or (
            entry_vs_prior_close_pct is not None
            and entry_vs_prior_close_pct <= -8.0
        )
    )
    return {
        "IMMEDIATE_OPENING_PROBE": {
            "eligible": decision_from_open_sec < 60,
            "status": "OBSERVED",
            "evidence": {"decision_from_open_sec": decision_from_open_sec},
        },
        "CONFIRMED_RECURRENT_RANK": {
            "eligible": confirmed_recurrent,
            "status": "OBSERVED" if not recurrent_missing else "INSUFFICIENT_EVIDENCE",
            "missing_fields": recurrent_missing,
            "evidence": {
                "prior_rank1_observations_5m": prior_rank1_observations_5m,
                "completed_return_1m_pct": completed_return_1m_pct,
                "opening_relative_volume": opening_relative_volume,
                "moderate_volume_0_5_to_4x": moderate_volume,
                "above_vwap": above_vwap,
            },
        },
        "DISLOCATION_REBOUND": {
            "eligible": (
                dislocation and moderate_volume
                if dislocation_known and opening_relative_volume is not None
                else None
            ),
            "status": (
                "OBSERVED"
                if dislocation_known and opening_relative_volume is not None
                else "INSUFFICIENT_EVIDENCE"
            ),
            "missing_fields": [
                field
                for field, missing in (
                    ("market_or_prior_close_dislocation", not dislocation_known),
                    ("opening_relative_volume", opening_relative_volume is None),
                )
                if missing
            ],
            "evidence": {
                "market_return_pct": market_return_pct,
                "entry_vs_prior_close_pct": entry_vs_prior_close_pct,
                "opening_relative_volume": opening_relative_volume,
                "moderate_volume_0_5_to_4x": moderate_volume,
            },
        },
    }


def opening_observability(
    *,
    candidate: Mapping[str, Any],
    day_rows: list[Mapping[str, Any]],
    decision_epoch: int,
    baseline_epoch: int,
    baseline_price: float,
    prior_rank1_observations_5m: int = 0,
    market_return_pct: float | None = None,
    volume_reference_rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    ordered = sorted(
        (
            row
            for row in day_rows
            if int(row.get("ts") or 0) > 0
        ),
        key=lambda row: int(row.get("ts") or 0),
    )
    opening = ordered[0] if ordered else {}
    opening_price = _number(opening.get("open") or opening.get("close"))
    completed = [
        row
        for row in ordered
        if int(row.get("ts") or 0) + 60 <= decision_epoch
    ]
    decision = datetime.fromtimestamp(decision_epoch, tz=KST)
    open_epoch = int(
        decision.replace(hour=9, minute=0, second=0, microsecond=0).timestamp()
    )
    compact = candidate.get("compact_feature_snapshot")
    compact = dict(compact) if isinstance(compact, Mapping) else {}
    source_scores = candidate.get("source_scores")
    source_scores = dict(source_scores) if isinstance(source_scores, Mapping) else {}
    score_breakdown = candidate.get("score_breakdown")
    score_breakdown = (
        dict(score_breakdown)
        if isinstance(score_breakdown, Mapping)
        else {}
    )
    best_bid = _number(compact.get("quote_best_bid"))
    best_ask = _number(compact.get("quote_best_ask"))
    spread_pct = (
        _pct(best_ask, best_bid)
        if best_bid and best_ask and best_ask >= best_bid
        else None
    )
    open_to_entry = _pct(baseline_price, opening_price)
    completed_return_1m_pct = _completed_return(completed, 1)
    opening_relative_volume = _first_number(
        [candidate, compact],
        "opening_relative_volume",
        "relative_volume",
        "volume_ratio",
    )
    if opening_relative_volume is None:
        opening_relative_volume = _opening_relative_volume(
            completed=completed,
            reference_rows=volume_reference_rows or [],
            day=decision.date().isoformat(),
        )
    prior_close = _first_number(
        [candidate, compact],
        "previous_close",
        "prior_close",
        "prev_close",
    )
    entry_vs_prior_close_pct = _pct(baseline_price, prior_close)
    if market_return_pct is None:
        market_return_pct = _first_number(
            [candidate, compact],
            "kospi_pct",
            "market_return_pct",
            "market_change_pct",
        )
    explicit_above_vwap = candidate.get("above_vwap", compact.get("above_vwap"))
    above_vwap = explicit_above_vwap if isinstance(explicit_above_vwap, bool) else None
    decision_from_open_sec = max(0, decision_epoch - open_epoch)
    lanes = _conditional_lanes(
        decision_from_open_sec=decision_from_open_sec,
        prior_rank1_observations_5m=prior_rank1_observations_5m,
        completed_return_1m_pct=completed_return_1m_pct,
        opening_relative_volume=opening_relative_volume,
        above_vwap=above_vwap,
        market_return_pct=market_return_pct,
        entry_vs_prior_close_pct=entry_vs_prior_close_pct,
    )
    decision_minute = decision.hour * 60 + decision.minute
    return {
        "decision_from_open_sec": decision_from_open_sec,
        "reference_entry_delay_sec": max(0, baseline_epoch - decision_epoch),
        "opening_price": opening_price,
        "reference_entry_vs_open_pct": open_to_entry,
        "completed_bar_count_at_decision": len(completed),
        "completed_cumulative_volume": (
            round(sum(float(row.get("volume") or 0.0) for row in completed), 4)
            if completed
            else None
        ),
        "completed_volume_status": (
            "OBSERVED" if completed else "UNAVAILABLE_FIRST_MINUTE"
        ),
        "prior_rank1_observations_5m": prior_rank1_observations_5m,
        "completed_return_1m_pct": completed_return_1m_pct,
        "opening_relative_volume": opening_relative_volume,
        "entry_vs_prior_close_pct": entry_vs_prior_close_pct,
        "market_return_pct": market_return_pct,
        "above_vwap": above_vwap,
        "exact_opening_09_00_04": 9 * 60 <= decision_minute < 9 * 60 + 5,
        "opening_chase_7pct": (
            open_to_entry is not None and open_to_entry >= 7.0
        ),
        "late_09_15_19_no_chase": (
            9 * 60 + 15 <= decision_minute < 9 * 60 + 20
            and open_to_entry is not None
            and open_to_entry < 7.0
        ),
        "candidate_snapshot": {
            "score_total": _number(candidate.get("score_total")),
            "pre_adjust_score_total": _number(
                candidate.get("pre_adjust_score_total")
            ),
            "confidence": _number(candidate.get("confidence")),
            "risk_score": _number(candidate.get("risk_score")),
            "sources": [
                str(value)
                for value in candidate.get("sources") or []
            ],
            "source_scores": source_scores,
            "score_breakdown": score_breakdown,
            "compact_feature_snapshot": compact,
        },
        "quote_snapshot": {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": spread_pct,
            "status": (
                "OBSERVED"
                if best_bid and best_ask
                else "MISSING_FROM_Q9_SNAPSHOT"
            ),
        },
        "asset_observation": _asset_observation(candidate),
        "execution_evidence": _execution_evidence(
            completed=completed,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_pct=spread_pct,
        ),
        "conditional_lanes": lanes,
        "missing_fields": [
            name
            for name, missing in (
                ("previous_close", prior_close is None),
                ("historical_same_clock_volume", opening_relative_volume is None),
                ("upper_limit_price", compact.get("upper_limit_price") in (None, 0, 0.0)),
                ("ask_depth", compact.get("ask_depth") in (None, 0, 0.0)),
                ("best_bid_ask", not (best_bid and best_ask)),
            )
            if missing
        ],
    }
