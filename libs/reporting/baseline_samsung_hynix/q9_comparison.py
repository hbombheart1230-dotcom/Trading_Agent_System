from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics
from libs.reporting.q9_forward_candles import (
    FORWARD_DATA_SOURCE,
    load_q9_forward_candles,
)
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes

from .contracts import HORIZONS
ROLES = (
    "P_SCANNER_PRE_STRATEGIST_UNIVERSE",
    "A_SCANNER_CONTROL",
    "B_STRATEGIST_RANKED",
    "C_COMMANDER_FINAL",
)


def _load_q9_rows(
    *,
    day: str,
    root: Path,
    state_path: Path = Path("data/state.json"),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day_root = root / day
    if not day_root.exists():
        return rows
    for path in sorted(day_root.glob("*.json")):
        if path.name == "latest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        generated_at = str(payload.get("generated_at") or "")
        for raw in payload.get("q9_decision_candidates") or []:
            if not isinstance(raw, Mapping) or raw.get("q9_decision_role") not in ROLES:
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", generated_at)
            rows.append(row)
    candles = load_q9_forward_candles(
        rows,
        state_path=state_path,
        allow_fresh_fetch=True,
        run_id_prefix="q9_comparison_forward_recovery",
    )
    return attach_forward_outcomes(rows, minute_rows_by_symbol=candles)


def build_q9_role_comparison(
    *,
    day: str,
    baseline_summary: Mapping[str, Any],
    cost_pct: float,
    slippage_pct: float,
    q9_root: Path = Path("data/logs/quant_shadow_candidates"),
    state_path: Path = Path("data/state.json"),
) -> dict[str, Any]:
    q9_rows = _load_q9_rows(day=day, root=q9_root, state_path=state_path)
    drag = float(cost_pct) + float(slippage_pct)
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in q9_rows:
        decision_id = str(row.get("q9_decision_id") or "")
        role = str(row.get("q9_decision_role") or "")
        if decision_id and role:
            grouped[decision_id][role].append(row)
    comparable_windows = {
        decision_id: roles
        for decision_id, roles in grouped.items()
        if all(role in roles for role in ROLES)
    }

    def representative(role: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if role == "B_STRATEGIST_RANKED":
            selected = next((row for row in rows if bool(row.get("q9_selected"))), None)
            if selected:
                return selected
        return min(
            rows,
            key=lambda row: int(float(row.get("rank") or 999)),
            default={},
        )

    role_rows: list[dict[str, Any]] = []
    for role in ROLES:
        role_candidates = [
            representative(role, roles.get(role) or [])
            for roles in comparable_windows.values()
            if roles.get(role)
        ]
        for horizon in HORIZONS:
            values: list[float] = []
            active_candidate_count = 0
            cash_no_trade_count = 0
            commander_decision_counts: dict[str, int] = defaultdict(int)
            for row in role_candidates:
                outcome = row.get("shadow_forward_outcome")
                outcome = outcome if isinstance(outcome, Mapping) else {}
                checkpoint = (outcome.get("checkpoints") or {}).get(horizon)
                checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
                if checkpoint.get("status") != "observed":
                    continue
                try:
                    candidate_return = float(checkpoint.get("return_pct"))
                except (TypeError, ValueError):
                    continue
                if role == "C_COMMANDER_FINAL":
                    decision = str(row.get("q9_commander_decision") or "").strip().lower()
                    no_trade = bool(row.get("q9_commander_no_trade"))
                    commander_decision_counts[decision or "unknown"] += 1
                    if no_trade or decision in {"reject", "noop", "no_trade", "blocked"}:
                        values.append(0.0)
                        cash_no_trade_count += 1
                    elif decision in {"approve", "approved", "allow", "buy"}:
                        values.append(candidate_return - drag)
                        active_candidate_count += 1
                    else:
                        continue
                else:
                    values.append(candidate_return - drag)
                    active_candidate_count += 1
            baseline_row = next(
                (
                    row
                    for row in baseline_summary.get("horizons") or []
                    if row.get("horizon") == horizon
                ),
                {},
            )
            baseline_expectancy = float(
                (baseline_row.get("top1_net") or {}).get("expectancy_pct") or 0.0
            )
            baseline_count = int((baseline_row.get("top1_net") or {}).get("count") or 0)
            metrics = performance_metrics(values)
            role_rows.append(
                {
                    "role": role,
                    "horizon": horizon,
                    "q9_net": metrics,
                    "metric_semantics": (
                        "commander_policy_return_approved_candidate_else_cash_zero"
                        if role == "C_COMMANDER_FINAL"
                        else "representative_candidate_forward_return"
                    ),
                    "active_candidate_count": active_candidate_count,
                    "cash_no_trade_count": cash_no_trade_count,
                    "commander_decision_counts": dict(commander_decision_counts),
                    "baseline_top1_count": baseline_count,
                    "baseline_top1_net_expectancy_pct": baseline_expectancy,
                    "baseline_minus_q9_expectancy_pct": (
                        round(
                            baseline_expectancy - float(metrics.get("expectancy_pct") or 0.0),
                            4,
                        )
                        if baseline_count > 0 and int(metrics.get("count") or 0) > 0
                        else None
                    ),
                }
            )
    return {
        "schema_version": "baseline_samsung_hynix_q9_comparison.v1",
        "behavior_effect": "evaluation_only",
        "day": day,
        "comparison_unit": "decision_window_representative_candidate",
        "cohort_scope": "complete_pabc_decision_windows_only",
        "forward_data_source": FORWARD_DATA_SOURCE,
        "decision_window_count": len(grouped),
        "comparable_complete_window_count": len(comparable_windows),
        "roles": role_rows,
    }
