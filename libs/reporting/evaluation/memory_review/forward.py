from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.research.opening_rank1_deep_dive.microstructure import load_minute_rows

from .contracts import COHORTS
from .loaders import mapping


HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")
ROLES = {"A_SCANNER_CONTROL", "B_STRATEGIST_RANKED", "C_COMMANDER_FINAL"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return mapping(payload)


def load_linked_q9_candidate_rows(
    project_root: Path,
    classified_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Load only shadow payloads directly named by a classified Stage-2 run."""
    shadow_root = project_root / "data" / "logs" / "quant_shadow_candidates"
    rows: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for classified in classified_rows:
        decision_id = str(classified.get("q9_decision_id") or "")
        run_id = str(classified.get("run_id") or "")
        day = str(classified.get("day") or "")
        if not decision_id or not run_id or not day:
            continue
        matches = sorted((shadow_root / day).glob(f"*_{run_id}.json"))
        for path in matches:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            payload = _read_json(path)
            generated_at = str(payload.get("generated_at") or "")
            for raw in payload.get("q9_decision_candidates") or []:
                candidate = mapping(raw)
                if (
                    str(candidate.get("q9_decision_id") or "") != decision_id
                    or str(candidate.get("q9_decision_role") or "") not in ROLES
                ):
                    continue
                candidate.setdefault("_payload_generated_at", generated_at)
                rows.append(candidate)
    return rows


def attach_historical_forward_outcomes(
    project_root: Path,
    candidate_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach outcomes one symbol at a time so historical caches do not fill memory."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in candidate_rows:
        row = dict(raw)
        symbol = str(row.get("symbol") or "")
        if symbol:
            grouped[symbol].append(row)
    primary = project_root / "data" / "research" / "post_reclaim_alpha" / "minute_cache"
    secondary = project_root / "data" / "research" / "opening_rank1_shadow" / "minute_cache"
    output: list[dict[str, Any]] = []
    for symbol, rows in sorted(grouped.items()):
        minute_rows = load_minute_rows(primary, {symbol}).get(symbol) or []
        if not minute_rows:
            minute_rows = load_minute_rows(secondary, {symbol}).get(symbol) or []
        output.extend(
            attach_forward_outcomes(
                rows,
                minute_rows_by_symbol={symbol: minute_rows} if minute_rows else {},
            )
        )
    return output


def _checkpoint_return(row: Mapping[str, Any], horizon: str) -> float | None:
    outcome = mapping(row.get("shadow_forward_outcome"))
    checkpoint = mapping(mapping(outcome.get("checkpoints")).get(horizon))
    if str(checkpoint.get("status") or "") != "observed":
        return None
    try:
        return float(checkpoint.get("return_pct"))
    except (TypeError, ValueError):
        return None


def _role_row(roles: Mapping[str, list[dict[str, Any]]], role: str) -> dict[str, Any]:
    candidates = roles.get(role) or []
    if role == "B_STRATEGIST_RANKED":
        selected = next((row for row in candidates if row.get("q9_selected")), None)
        if selected:
            return selected
    return min(
        candidates,
        key=lambda row: int(float(row.get("rank") or 999)),
        default={},
    )


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def build_forward_comparison(
    classified_rows: Iterable[Mapping[str, Any]],
    candidate_rows: Iterable[Mapping[str, Any]],
    *,
    cost_pct: float,
) -> dict[str, Any]:
    decision_cohorts: dict[str, set[str]] = defaultdict(set)
    decision_runtime: dict[str, dict[str, Any]] = {}
    for row in classified_rows:
        decision_id = str(row.get("q9_decision_id") or "")
        cohort = str(row.get("cohort") or "")
        if decision_id and cohort:
            decision_cohorts[decision_id].add(cohort)
            decision_runtime[decision_id] = dict(row)

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for raw in candidate_rows:
        row = dict(raw)
        decision_id = str(row.get("q9_decision_id") or "")
        role = str(row.get("q9_decision_role") or "")
        if decision_id in decision_cohorts and role in ROLES:
            grouped[decision_id][role].append(row)

    ambiguous = {key for key, values in decision_cohorts.items() if len(values) != 1}
    by_cohort: dict[str, Any] = {}
    for cohort in COHORTS:
        decisions = [
            decision_id
            for decision_id, values in decision_cohorts.items()
            if values == {cohort} and decision_id in grouped
        ]
        horizons: list[dict[str, Any]] = []
        for horizon in HORIZONS:
            a_values: list[float] = []
            b_values: list[float] = []
            b_net_values: list[float] = []
            strategist_deltas: list[float] = []
            commander_policy_values: list[float] = []
            commander_deltas: list[float] = []
            for decision_id in decisions:
                roles = grouped[decision_id]
                runtime = decision_runtime.get(decision_id) or {}
                a_row = _role_row(roles, "A_SCANNER_CONTROL")
                b_row = _role_row(roles, "B_STRATEGIST_RANKED")
                c_row = _role_row(roles, "C_COMMANDER_FINAL")
                a_value = _checkpoint_return(a_row, horizon) if a_row else None
                b_value = _checkpoint_return(b_row, horizon) if b_row else None
                if a_value is not None:
                    a_values.append(a_value)
                if b_value is not None:
                    b_values.append(b_value)
                    b_net_values.append(b_value - cost_pct)
                if a_value is not None and b_value is not None:
                    strategist_deltas.append(b_value - a_value)
                if b_value is None:
                    continue
                if bool(runtime.get("commander_no_trade")):
                    c_net = 0.0
                elif c_row:
                    c_value = _checkpoint_return(c_row, horizon)
                    if c_value is None:
                        continue
                    c_net = c_value - cost_pct
                else:
                    continue
                b_net = b_value - cost_pct
                commander_policy_values.append(c_net)
                commander_deltas.append(c_net - b_net)
            horizons.append(
                {
                    "horizon": horizon,
                    "scanner_observed_count": len(a_values),
                    "strategist_observed_count": len(b_values),
                    "paired_scanner_strategist_count": len(strategist_deltas),
                    "commander_comparison_count": len(commander_deltas),
                    "scanner_avg_gross_return_pct": _average(a_values),
                    "strategist_avg_gross_return_pct": _average(b_values),
                    "strategist_avg_net_return_pct": _average(b_net_values),
                    "strategist_minus_scanner_avg_pct": _average(strategist_deltas),
                    "strategist_positive_delta_rate": (
                        round(sum(value > 0 for value in strategist_deltas) / len(strategist_deltas), 4)
                        if strategist_deltas
                        else None
                    ),
                    "commander_policy_avg_net_return_pct": _average(commander_policy_values),
                    "commander_minus_strategist_avg_pct": _average(commander_deltas),
                    "commander_positive_delta_rate": (
                        round(sum(value > 0 for value in commander_deltas) / len(commander_deltas), 4)
                        if commander_deltas
                        else None
                    ),
                }
            )
        by_cohort[cohort] = {
            "linked_decision_count": len(decisions),
            "horizons": horizons,
        }
    return {
        "cost_pct": round(float(cost_pct), 6),
        "candidate_row_count": sum(len(rows) for roles in grouped.values() for rows in roles.values()),
        "linked_decision_count": len(grouped),
        "ambiguous_cohort_decision_count": len(ambiguous),
        "by_cohort": by_cohort,
    }
