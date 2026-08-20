from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from libs.reporting.q8_evaluation_contract import candidate_day
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes

from .metrics import performance_metrics


TOP_K_VALUES = (1, 3, 5, 10)
SCANNER_HORIZONS = ("+5m", "+15m", "+30m", "EOD")


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _checkpoint_return(row: Mapping[str, Any], horizon: str) -> float | None:
    outcome = row.get("shadow_forward_outcome")
    outcome = outcome if isinstance(outcome, Mapping) else {}
    checkpoints = outcome.get("checkpoints")
    checkpoints = checkpoints if isinstance(checkpoints, Mapping) else {}
    checkpoint = checkpoints.get(horizon)
    checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
    if str(checkpoint.get("status") or "") != "observed":
        return None
    return _number(checkpoint.get("return_pct"))


def extract_pre_strategist_candidate_rows(
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for payload in payloads:
        generated_at = str(payload.get("generated_at") or "")
        for raw in payload.get("q9_decision_candidates") or []:
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("q9_decision_role") or "") != "P_SCANNER_PRE_STRATEGIST_UNIVERSE":
                continue
            row = dict(raw)
            decision_id = str(row.get("q9_decision_id") or "")
            symbol = str(row.get("symbol") or "")
            rank = int(_number(row.get("rank")) or 0)
            key = (decision_id, symbol, rank)
            if not decision_id or not symbol or rank <= 0 or key in seen:
                continue
            seen.add(key)
            row.setdefault("_payload_generated_at", generated_at)
            rows.append(row)
    return rows


def pre_strategist_candidate_rows(
    payloads: list[dict[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    rows = extract_pre_strategist_candidate_rows(payloads)
    if minute_rows_by_symbol is None:
        return attach_forward_outcomes(rows)
    return attach_forward_outcomes(
        rows,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )


def build_scanner_topk_forward_performance(
    rows: list[dict[str, Any]],
    *,
    cost_pct: float,
    slippage_pct: float,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        decision_id = str(row.get("q9_decision_id") or "")
        if decision_id:
            grouped[decision_id].append(row)
    output: list[dict[str, Any]] = []
    total_drag = float(cost_pct) + float(slippage_pct)
    for horizon in SCANNER_HORIZONS:
        for top_k in TOP_K_VALUES:
            gross_values: list[float] = []
            net_values: list[float] = []
            days: set[str] = set()
            candidate_observations = 0
            for decision_rows in grouped.values():
                ranked = sorted(
                    decision_rows,
                    key=lambda row: int(_number(row.get("rank")) or 999),
                )
                observed = [
                    value
                    for row in ranked[:top_k]
                    for value in [_checkpoint_return(row, horizon)]
                    if value is not None
                ]
                if not observed:
                    continue
                window_return = sum(observed) / len(observed)
                gross_values.append(window_return)
                net_values.append(window_return - total_drag)
                candidate_observations += len(observed)
                day = next((candidate_day(row) for row in ranked[:top_k] if candidate_day(row)), "")
                if day:
                    days.add(day)
            output.append(
                {
                    "top_k": top_k,
                    "horizon": horizon,
                    "window_count": len(gross_values),
                    "candidate_observation_count": candidate_observations,
                    "observed_day_count": len(days),
                    "cost_pct": round(float(cost_pct), 6),
                    "slippage_pct": round(float(slippage_pct), 6),
                    "gross": performance_metrics(gross_values),
                    "net": performance_metrics(net_values),
                }
            )
    return {
        "schema_version": "q9_scanner_topk_forward_performance.v1",
        "behavior_effect": "evaluation_only",
        "decision_window_count": len(grouped),
        "candidate_row_count": len(rows),
        "top_k_values": list(TOP_K_VALUES),
        "horizons": list(SCANNER_HORIZONS),
        "rows": output,
    }


def build_scanner_source_performance(
    rows: list[dict[str, Any]],
    *,
    cost_pct: float,
    slippage_pct: float,
) -> dict[str, Any]:
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    days: dict[tuple[str, str], set[str]] = defaultdict(set)
    total_drag = float(cost_pct) + float(slippage_pct)
    for row in rows:
        sources = [
            str(value or "")
            for value in row.get("q9_candidate_sources") or row.get("sources") or []
            if str(value or "")
        ] or ["unknown"]
        for horizon in SCANNER_HORIZONS:
            value = _checkpoint_return(row, horizon)
            if value is None:
                continue
            for source in sources:
                key = (source, horizon)
                buckets[key].append(value - total_drag)
                day = candidate_day(row)
                if day:
                    days[key].add(day)
    return {
        "schema_version": "q9_scanner_source_performance.v1",
        "behavior_effect": "evaluation_only",
        "rows": [
            {
                "source": source,
                "horizon": horizon,
                "observed_day_count": len(days[(source, horizon)]),
                "cost_pct": round(float(cost_pct), 6),
                "slippage_pct": round(float(slippage_pct), 6),
                **performance_metrics(values),
            }
            for (source, horizon), values in sorted(buckets.items())
        ],
    }


def build_scanner_quality_review(
    payloads: list[dict[str, Any]],
    *,
    cost_pct: float,
    slippage_pct: float,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    rows = pre_strategist_candidate_rows(
        payloads,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    return {
        "schema_version": "q9_scanner_quality_review.v1",
        "behavior_effect": "evaluation_only",
        "pre_strategist_universe_available": bool(rows),
        "topk_forward_performance": build_scanner_topk_forward_performance(
            rows,
            cost_pct=cost_pct,
            slippage_pct=slippage_pct,
        ),
        "source_performance": build_scanner_source_performance(
            rows,
            cost_pct=cost_pct,
            slippage_pct=slippage_pct,
        ),
    }


__all__ = [
    "SCANNER_HORIZONS",
    "TOP_K_VALUES",
    "build_scanner_quality_review",
    "build_scanner_source_performance",
    "build_scanner_topk_forward_performance",
    "pre_strategist_candidate_rows",
]
