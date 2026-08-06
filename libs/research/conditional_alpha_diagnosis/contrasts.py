from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any, Callable, Mapping

from .metrics import number, performance


NUMERIC_FIELDS = (
    "scanner_score",
    "confidence",
    "risk_score",
    "rank1_prev5m_observations",
    "precompleted_return_1m_pct",
    "opening_relative_volume",
    "entry_vs_prior_close_pct",
)


def _profile(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    numeric = {}
    for field in NUMERIC_FIELDS:
        values = [value for row in rows if (value := number(row.get(field))) is not None]
        numeric[field] = {
            "count": len(values),
            "average": round(mean(values), 4) if values else None,
        }
    return {
        "count": len(rows),
        "performance_30m": performance(row.get("intrinsic_30m_net_pct") for row in rows),
        "numeric": numeric,
        "monitor_intent": dict(Counter(str(row.get("monitor_intent") or "MISSING") for row in rows)),
        "dominant_block_reason": dict(
            Counter(str(row.get("dominant_block_reason") or "MISSING") for row in rows)
        ),
        "expected_monitor_block_reason": dict(
            Counter(str(row.get("expected_monitor_block_reason") or "MISSING") for row in rows)
        ),
    }


def _comparison(
    rows: list[dict[str, Any]],
    name: str,
    left: Callable[[Mapping[str, Any]], bool],
    right: Callable[[Mapping[str, Any]], bool],
) -> dict[str, Any]:
    left_rows = [row for row in rows if left(row)]
    right_rows = [row for row in rows if right(row)]
    left_profile = _profile(left_rows)
    right_profile = _profile(right_rows)
    deltas = {}
    for field in NUMERIC_FIELDS:
        left_value = left_profile["numeric"][field]["average"]
        right_value = right_profile["numeric"][field]["average"]
        deltas[field] = (
            round(left_value - right_value, 4)
            if left_value is not None and right_value is not None
            else None
        )
    return {
        "comparison": name,
        "left": left_profile,
        "right": right_profile,
        "left_minus_right_numeric": deltas,
    }


def conditional_contrast_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive = lambda row: (number(row.get("intrinsic_30m_net_pct")) or -999.0) > 0
    non_positive = lambda row: (number(row.get("intrinsic_30m_net_pct")) or 999.0) <= 0
    approved = lambda row: str(row.get("commander_decision") or "").lower() == "approve"
    rejected = lambda row: str(row.get("commander_decision") or "").lower() in {
        "reject",
        "retry_scan",
    }
    no_execution = lambda row: number(row.get("executed_30m_net_pct")) is None
    comparisons = [
        _comparison(rows, "POSITIVE_VS_NON_POSITIVE", positive, non_positive),
        _comparison(
            rows,
            "APPROVED_NO_EXECUTION_POSITIVE_VS_NON_POSITIVE",
            lambda row: approved(row) and no_execution(row) and positive(row),
            lambda row: approved(row) and no_execution(row) and non_positive(row),
        ),
        _comparison(
            rows,
            "REJECTED_POSITIVE_VS_NON_POSITIVE",
            lambda row: rejected(row) and positive(row),
            lambda row: rejected(row) and non_positive(row),
        ),
    ]
    approved_no_execution = [row for row in rows if approved(row) and no_execution(row)]
    missing_reason = [
        row
        for row in approved_no_execution
        if not row.get("dominant_block_reason")
        and not row.get("expected_monitor_block_reason")
    ]
    return {
        "schema_version": "conditional_contrast_report.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "comparisons": comparisons,
        "noop_observability": {
            "approved_no_execution_count": len(approved_no_execution),
            "missing_reason_count": len(missing_reason),
            "missing_reason_rate": (
                round(len(missing_reason) / len(approved_no_execution), 4)
                if approved_no_execution
                else None
            ),
            "interpretation": (
                "A missing NOOP reason is an observability gap, not proof that Monitor was wrong."
            ),
        },
    }
