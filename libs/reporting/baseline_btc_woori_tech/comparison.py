from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix.q9_comparison import build_q9_role_comparison
from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import HORIZONS


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _metric(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trade_count": int(row.get("count") or 0),
        "win_rate": float(row.get("win_rate") or 0.0),
        "avg_return_pct": float(row.get("average_return_pct") or 0.0),
        "profit_factor": float(row.get("profit_factor") or 0.0),
        "max_drawdown_pct": float(row.get("maximum_drawdown_pct") or 0.0),
    }


def _gross_returns(rows: list[dict[str, Any]], horizon: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        checkpoint = (row.get("returns") or {}).get(horizon) or {}
        if checkpoint.get("status") == "observed":
            values.append(float(checkpoint.get("return_pct") or 0.0))
    return values


def build_comparison(
    *,
    day: str,
    summary: Mapping[str, Any],
    forward_rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    cost_pct: float,
    slippage_pct: float,
    reports_root: Path,
    q9_root: Path,
    state_path: Path,
) -> dict[str, Any]:
    q9 = build_q9_role_comparison(
        day=day,
        baseline_summary=summary,
        cost_pct=cost_pct,
        slippage_pct=slippage_pct,
        q9_root=q9_root,
        state_path=state_path,
    )
    q10 = _read(
        reports_root
        / "evaluation"
        / "baseline_samsung_hynix"
        / day
        / "baseline_samsung_hynix_forward_returns.json"
    )
    q10_by_horizon = {
        str(row.get("horizon") or ""): _metric(row.get("top1_net") or {})
        for row in (q10.get("summary") or {}).get("horizons") or []
    }
    q12_by_horizon = {
        str(row.get("horizon") or ""): _metric(row.get("eligible_entries_net") or {})
        for row in summary.get("horizons") or []
    }
    drag = float(cost_pct) + float(slippage_pct)
    horizons: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        buy_hold = performance_metrics(value - drag for value in _gross_returns(forward_rows, horizon))
        momentum_only_rows = [
            row
            for row, decision in zip(forward_rows, decisions)
            if bool((decision.get("btc_signal") or {}).get("positive"))
        ]
        momentum_only = performance_metrics(
            value - drag for value in _gross_returns(momentum_only_rows, horizon)
        )
        q9_roles = [
            row
            for row in q9.get("roles") or []
            if row.get("horizon") == horizon
        ]
        horizons.append(
            {
                "horizon": horizon,
                "q12_confirmed_entry": q12_by_horizon.get(horizon, _metric({})),
                "woori_buy_and_hold": _metric(buy_hold),
                "btc_momentum_only": _metric(momentum_only),
                "samsung_hynix_top1": q10_by_horizon.get(horizon, _metric({})),
                "q9_roles": q9_roles,
            }
        )
    comparable = any(
        row["q12_confirmed_entry"]["trade_count"] > 0
        and row["samsung_hynix_top1"]["trade_count"] > 0
        for row in horizons
    )
    return {
        "schema_version": "baseline_btc_woori_comparison.v1",
        "evaluation_program_id": "Q12_BTC_WOORI_TECH_BASELINE",
        "behavior_effect": "evaluation_only",
        "day": day,
        "evidence_status": "COMPARABLE" if comparable else "INSUFFICIENT_EVIDENCE",
        "horizons": horizons,
    }

