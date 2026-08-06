from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def prospective_validation(
    *,
    stage_rows: Iterable[Mapping[str, Any]],
    opening_rows: Iterable[Mapping[str, Any]],
    trade_rows: Iterable[Mapping[str, Any]],
    start_day: str,
    required_days: int = 3,
    opening_day_statuses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    opening_day_statuses = opening_day_statuses or {}
    stages_by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    opening_by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    trades_by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in stage_rows:
        day = str(row.get("day") or "")
        if day >= start_day:
            stages_by_day[day].append(row)
    for row in opening_rows:
        day = str(row.get("day") or "")
        if day >= start_day:
            opening_by_day[day].append(row)
    for row in trade_rows:
        day = str(row.get("day") or "")
        if day >= start_day:
            trades_by_day[day].append(row)

    days = []
    for day in sorted(stages_by_day):
        stages = stages_by_day[day]
        policies = opening_by_day.get(day, [])
        trades = trades_by_day.get(day, [])
        expected_policy_rows = len(stages) * 4
        exact_lineage = sum(
            str((row.get("lineage") or {}).get("confidence") or "") == "EXACT"
            for row in trades
        )
        horizon_complete = sum(
            bool(row.get("strategy_horizon"))
            for row in trades
        )
        defects = []
        opening_day_status = str(opening_day_statuses.get(day) or "")
        if opening_day_status and opening_day_status != "VALID":
            defects.append(f"opening_shadow_status:{opening_day_status}")
        observed_forward = sum(
            row.get("forward_30m_status") == "observed"
            for row in stages
        )
        if len(policies) != expected_policy_rows:
            defects.append("opening_policy_row_count_mismatch")
        if exact_lineage != len(trades):
            defects.append("non_exact_trade_lineage")
        if horizon_complete != len(trades):
            defects.append("missing_horizon_contract")
        if observed_forward != len(stages):
            defects.append("missing_opening_30m_forward")
        days.append(
            {
                "day": day,
                "opening_decision_count": len(stages),
                "opening_policy_row_count": len(policies),
                "trade_count": len(trades),
                "exact_lineage_count": exact_lineage,
                "horizon_complete_count": horizon_complete,
                "opening_30m_forward_count": observed_forward,
                "opening_shadow_day_status": opening_day_status or "UNAVAILABLE",
                "status": "VALID" if not defects else "INVALID",
                "defects": defects,
            }
        )
    valid_count = sum(row["status"] == "VALID" for row in days)
    return {
        "schema_version": "integrated_trade_diagnosis_validation.v1",
        "start_day": start_day,
        "required_full_trading_days": required_days,
        "observed_day_count": len(days),
        "valid_day_count": valid_count,
        "status": "COMPLETE"
        if valid_count >= required_days
        else "PENDING",
        "remaining_valid_days": max(0, required_days - valid_count),
        "days": days,
        "reset_on_observability_fix": False,
    }
