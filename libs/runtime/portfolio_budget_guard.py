from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from libs.runtime.intent_conflict_resolver import resolve_intent_conflicts


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _norm_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_strategy(value: Any) -> str:
    return str(value or "").strip()


def _priority_score(row: Dict[str, Any]) -> float:
    priority = _as_float(row.get("priority"), 0.0)
    confidence = _as_float(
        row.get("confidence"),
        _as_float((row.get("meta") or {}).get("confidence") if isinstance(row.get("meta"), dict) else 0.0, 0.0),
    )
    requested_notional = _as_float(row.get("requested_notional"), 0.0)
    return priority * 1000.0 + confidence * 100.0 + requested_notional * 0.000001


def _resolve_requested_notional(row: Dict[str, Any], *, market_prices: Dict[str, float]) -> float:
    direct = _as_float(row.get("requested_notional"), _as_float(row.get("notional"), 0.0))
    if direct > 0.0:
        return direct

    qty = max(0, _as_int(row.get("qty"), 0))
    if qty <= 0:
        return 1.0

    symbol = _norm_symbol(row.get("symbol"))
    price = _as_float(row.get("price"), _as_float(row.get("unit_price"), market_prices.get(symbol, 0.0)))
    if price > 0.0:
        return float(qty) * price
    return float(qty)


def _build_strategy_budget_map(
    *,
    allocation_result: Optional[Dict[str, Any]],
    strategy_budget_map: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    out: Dict[str, float] = {}

    if isinstance(allocation_result, dict):
        rows = allocation_result.get("allocations")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                strategy_id = _norm_strategy(row.get("strategy_id"))
                if not strategy_id:
                    continue
                out[strategy_id] = max(0.0, _as_float(row.get("allocated_notional"), 0.0))

    if isinstance(strategy_budget_map, dict):
        for k, v in strategy_budget_map.items():
            strategy_id = _norm_strategy(k)
            if not strategy_id:
                continue
            out[strategy_id] = max(0.0, _as_float(v, 0.0))

    return out


def apply_portfolio_budget_guard(
    intents: List[Dict[str, Any]],
    *,
    allocation_result: Optional[Dict[str, Any]] = None,
    strategy_budget_map: Optional[Dict[str, Any]] = None,
    default_symbol_max_notional: float = 0.0,
    symbol_max_notional_map: Optional[Dict[str, float]] = None,
    market_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """M27-3: commander/supervisor boundary guard (budget -> conflict resolution)."""
    failures: List[str] = []
    cap_map: Dict[str, float] = {}
    if isinstance(symbol_max_notional_map, dict):
        for k, v in symbol_max_notional_map.items():
            cap_map[_norm_symbol(k)] = max(0.0, _as_float(v, 0.0))

    price_map: Dict[str, float] = {}
    if isinstance(market_prices, dict):
        for k, v in market_prices.items():
            price_map[_norm_symbol(k)] = max(0.0, _as_float(v, 0.0))

    budget_map = _build_strategy_budget_map(
        allocation_result=allocation_result,
        strategy_budget_map=strategy_budget_map,
    )
    budget_enabled = len(budget_map) > 0

    normalized: List[Dict[str, Any]] = []
    blocked_stage_budget: List[Dict[str, Any]] = []
    if not isinstance(intents, list):
        failures.append("intents must be list")
        intents = []

    for idx, raw in enumerate(intents):
        if not isinstance(raw, dict):
            blocked_stage_budget.append(
                {
                    "index": idx,
                    "status": "blocked",
                    "reason": "invalid_intent_type",
                    "intent": raw,
                }
            )
            continue

        strategy_id = _norm_strategy(raw.get("strategy_id"))
        symbol = _norm_symbol(raw.get("symbol"))
        if not symbol:
            blocked_stage_budget.append(
                {
                    "index": idx,
                    "strategy_id": strategy_id,
                    "status": "blocked",
                    "reason": "missing_symbol",
                    "intent": raw,
                }
            )
            continue

        requested_notional = _resolve_requested_notional(raw, market_prices=price_map)
        normalized.append(
            {
                "index": idx,
                "intent": raw,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "requested_notional": requested_notional,
                "priority_score": _priority_score({**raw, "requested_notional": requested_notional}),
            }
        )

    approved_after_budget: List[Dict[str, Any]] = []
    strategy_usage: Dict[str, Dict[str, float]] = {}

    if not budget_enabled:
        approved_after_budget = [x["intent"] for x in normalized]
    else:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in normalized:
            grouped[row["strategy_id"]].append(row)

        for strategy_id in budget_map:
            strategy_usage[strategy_id] = {
                "budget_notional": float(budget_map[strategy_id]),
                "used_notional": 0.0,
                "remaining_notional": float(budget_map[strategy_id]),
            }

        for strategy_id in sorted(grouped.keys()):
            rows = sorted(
                grouped[strategy_id],
                key=lambda x: (-_as_float(x.get("priority_score"), 0.0), int(_as_int(x.get("index"), 0))),
            )

            if not strategy_id:
                for row in rows:
                    blocked_stage_budget.append(
                        {
                            "index": int(_as_int(row.get("index"), 0)),
                            "strategy_id": strategy_id,
                            "symbol": row.get("symbol"),
                            "requested_notional": float(_as_float(row.get("requested_notional"), 0.0)),
                            "priority_score": float(_as_float(row.get("priority_score"), 0.0)),
                            "status": "blocked",
                            "reason": "missing_strategy_id",
                            "intent": row.get("intent"),
                        }
                    )
                continue

            if strategy_id not in budget_map:
                for row in rows:
                    blocked_stage_budget.append(
                        {
                            "index": int(_as_int(row.get("index"), 0)),
                            "strategy_id": strategy_id,
                            "symbol": row.get("symbol"),
                            "requested_notional": float(_as_float(row.get("requested_notional"), 0.0)),
                            "priority_score": float(_as_float(row.get("priority_score"), 0.0)),
                            "status": "blocked",
                            "reason": "missing_strategy_budget",
                            "intent": row.get("intent"),
                        }
                    )
                continue

            budget = float(max(0.0, _as_float(budget_map.get(strategy_id), 0.0)))
            used = 0.0
            for row in rows:
                requested = float(max(0.0, _as_float(row.get("requested_notional"), 0.0)))
                if requested <= 0.0:
                    requested = 1.0
                if used + requested <= budget + 1e-9:
                    used += requested
                    approved_after_budget.append(row["intent"])
                    continue
                blocked_stage_budget.append(
                    {
                        "index": int(_as_int(row.get("index"), 0)),
                        "strategy_id": strategy_id,
                        "symbol": row.get("symbol"),
                        "requested_notional": requested,
                        "priority_score": float(_as_float(row.get("priority_score"), 0.0)),
                        "status": "blocked",
                        "reason": "strategy_budget_exceeded",
                        "intent": row.get("intent"),
                        "strategy_budget_notional": float(budget),
                        "strategy_used_notional": float(used),
                    }
                )
            strategy_usage[strategy_id] = {
                "budget_notional": float(budget),
                "used_notional": float(used),
                "remaining_notional": float(max(0.0, budget - used)),
            }

    conflict = resolve_intent_conflicts(
        approved_after_budget,
        default_symbol_max_notional=float(max(0.0, _as_float(default_symbol_max_notional, 0.0))),
        symbol_max_notional_map=cap_map,
        market_prices=price_map,
    )

    blocked_all = list(blocked_stage_budget) + list(conflict.get("blocked") or [])
    reason_counts: Dict[str, int] = {}
    for row in blocked_all:
        reason = str(row.get("reason") or "")
        reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1

    return {
        "ok": len(failures) == 0,
        "budget_enabled": budget_enabled,
        "intent_total": len(intents),
        "budget_screened_total": len(approved_after_budget),
        "approved_total": int(_as_int(conflict.get("approved_total"), 0)),
        "blocked_total": len(blocked_all),
        "blocked_reason_counts": reason_counts,
        "strategy_budget": {
            "strategy_total": len(budget_map),
            "map": {k: float(v) for k, v in budget_map.items()},
            "usage": strategy_usage,
        },
        "approved": list(conflict.get("approved") or []),
        "blocked": blocked_all,
        "failures": failures,
    }
