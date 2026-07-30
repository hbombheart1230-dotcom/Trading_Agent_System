from __future__ import annotations

from typing import Any, Mapping


TARGET_PROFILE = "vwap_reclaim:post_reclaim_pullback_candidate"
HORIZON_FIELDS = {
    "+5m": "avg_return_5m_pct",
    "+15m": "avg_return_15m_pct",
    "+30m": "avg_return_30m_pct",
    "+60m": "avg_return_60m_pct",
}


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_post_reclaim_shadow_review(
    historical_review: Mapping[str, Any],
    *,
    mock_drag_pct: float,
    live_drag_pct: float,
) -> dict[str, Any]:
    profiles = [
        dict(row)
        for row in historical_review.get("below_vwap_reclaim_subtype_forward") or []
        if isinstance(row, Mapping)
    ]
    target = next(
        (row for row in profiles if str(row.get("name") or "") == TARGET_PROFILE),
        {},
    )
    rows: list[dict[str, Any]] = []
    for horizon, field in HORIZON_FIELDS.items():
        gross = _number(target.get(field))
        rows.append(
            {
                "horizon": horizon,
                "gross_expectancy_pct": gross,
                "live_net_expectancy_pct": (
                    round(gross - float(live_drag_pct), 4) if gross is not None else None
                ),
                "mock_net_expectancy_pct": (
                    round(gross - float(mock_drag_pct), 4) if gross is not None else None
                ),
            }
        )

    live_30m = next(
        (row.get("live_net_expectancy_pct") for row in rows if row["horizon"] == "+30m"),
        None,
    )
    mock_30m = next(
        (row.get("mock_net_expectancy_pct") for row in rows if row["horizon"] == "+30m"),
        None,
    )
    observed_count = int(target.get("observed_count") or 0)
    observed_days = int(target.get("day_count") or 0)
    return {
        "schema_version": "post_reclaim_shadow_review.v1",
        "behavior_effect": "shadow_only",
        "profile_name": TARGET_PROFILE,
        "available": bool(target),
        "candidate_count": int(target.get("candidate_count") or 0),
        "observed_count": observed_count,
        "observed_day_count": observed_days,
        "coverage": target.get("coverage"),
        "rows": rows,
        "promotion_status": (
            "LIVE_COST_SHADOW_CANDIDATE"
            if observed_count >= 20
            and observed_days >= 10
            and live_30m is not None
            and live_30m > 0
            and mock_30m is not None
            and mock_30m <= 0
            else "RETAIN_UNDER_OBSERVATION"
        ),
        "runtime_directional_edge_used": False,
        "limitations": [
            "This subtype is not fed into Q17 runtime cost evidence.",
            "Aggregated subtype observations may remain serially correlated.",
            "Positive live-cost expectancy does not imply mock-cost profitability.",
        ],
    }


__all__ = ["build_post_reclaim_shadow_review"]
