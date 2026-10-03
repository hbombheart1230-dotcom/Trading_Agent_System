from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix.forward_returns import (
    attach_baseline_forward_returns,
    summarize_forward_returns,
)

from .contracts import TARGET_SYMBOL, TARGET_TICKER


def attach_forward_returns(
    decisions: list[dict[str, Any]],
    *,
    candles: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    compatible: list[dict[str, Any]] = []
    for row in decisions:
        features = row.get("local_features") or {}
        compatible.append(
            {
                "decision_id": row.get("decision_id"),
                "generated_at": row.get("generated_at"),
                "ranked_candidates": [
                    {
                        "symbol": TARGET_SYMBOL,
                        "ticker": TARGET_TICKER,
                        "rank": 1,
                        "eligible": row.get("eligible"),
                        "action": row.get("action"),
                        "features": features,
                    }
                ],
            }
        )
    return attach_baseline_forward_returns(
        compatible,
        minute_rows_by_symbol={TARGET_SYMBOL: list(candles)},
    )


def summarize(
    rows: list[dict[str, Any]],
    *,
    cost_pct: float,
    slippage_pct: float,
) -> dict[str, Any]:
    return summarize_forward_returns(rows, cost_pct=cost_pct, slippage_pct=slippage_pct)


def summarize_policy_variant(
    rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    policy_id: str,
    cost_pct: float,
    slippage_pct: float,
) -> dict[str, Any]:
    eligibility = {
        str(row.get("decision_id") or ""): bool(
            ((row.get("policy_variants") or {}).get(policy_id) or {}).get("eligible")
        )
        for row in decisions
    }
    variant_rows = deepcopy(rows)
    for row in variant_rows:
        decision_id = str(row.get("baseline_decision_id") or "")
        row["eligible"] = eligibility.get(decision_id, False)
        row["policy_variant_id"] = policy_id
    return summarize_forward_returns(
        variant_rows, cost_pct=cost_pct, slippage_pct=slippage_pct
    )
