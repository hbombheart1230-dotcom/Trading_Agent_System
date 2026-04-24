from __future__ import annotations

from typing import Any, Dict, Mapping


def _identity_score(details: Mapping[str, Any] | None) -> int:
    details_obj = dict(details or {})
    score = 0
    for key in ("order_id", "order_status", "filled_qty", "fill_status"):
        if details_obj.get(key) not in (None, "", [], {}):
            score += 1
    return score


def _detail_score(details: Mapping[str, Any] | None) -> int:
    details_obj = dict(details or {})
    score = 0
    for key in (
        "order_id",
        "order_status",
        "filled_qty",
        "filled_price",
        "broker_truth_source",
        "broker_day_truth_source",
        "broker_day_match_mode",
        "broker_realized_pnl",
        "broker_fee",
        "broker_tax",
    ):
        if details_obj.get(key) not in (None, "", [], {}):
            score += 1
    if bool(details_obj.get("broker_day_authoritative")):
        score += 1
    return score


def prefer_richer_execution_details(
    existing: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
) -> bool:
    existing_obj = dict(existing or {})
    candidate_obj = dict(candidate or {})
    if not candidate_obj:
        return False
    if _identity_score(candidate_obj) < _identity_score(existing_obj):
        return False
    if _detail_score(candidate_obj) >= _detail_score(existing_obj):
        return True
    return candidate_obj != existing_obj


def merge_preferred_execution_details(
    existing: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    existing_obj = dict(existing or {})
    candidate_obj = dict(candidate or {})
    if not prefer_richer_execution_details(existing_obj, candidate_obj):
        return existing_obj
    merged = dict(existing_obj)
    for key, value in candidate_obj.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


__all__ = [
    "merge_preferred_execution_details",
    "prefer_richer_execution_details",
]
