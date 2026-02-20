from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


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


def _norm_side(row: Dict[str, Any]) -> str:
    side = str(row.get("side") or row.get("action") or "").strip().upper()
    if side in ("BUY", "SELL"):
        return side
    return ""


def _priority_score(row: Dict[str, Any]) -> float:
    priority = _as_float(row.get("priority"), 0.0)
    confidence = _as_float(
        row.get("confidence"),
        _as_float((row.get("meta") or {}).get("confidence") if isinstance(row.get("meta"), dict) else 0.0, 0.0),
    )
    requested_notional = _as_float(row.get("requested_notional"), 0.0)
    # Deterministic ordering: policy priority > confidence > requested size.
    return priority * 1000.0 + confidence * 100.0 + requested_notional * 0.000001


def _resolve_requested_notional(
    row: Dict[str, Any],
    *,
    symbol: str,
    market_prices: Dict[str, float],
) -> float:
    direct = _as_float(row.get("requested_notional"), _as_float(row.get("notional"), 0.0))
    if direct > 0.0:
        return direct

    qty = max(0, _as_int(row.get("qty"), 0))
    if qty <= 0:
        return 1.0

    price = _as_float(row.get("price"), _as_float(row.get("unit_price"), market_prices.get(symbol, 0.0)))
    if price > 0.0:
        return float(qty) * price
    return float(qty)


def _resolve_symbol_cap(
    symbol: str,
    *,
    default_symbol_max_notional: float,
    symbol_max_notional_map: Dict[str, float],
) -> float:
    if symbol in symbol_max_notional_map:
        return max(0.0, _as_float(symbol_max_notional_map.get(symbol), 0.0))
    return max(0.0, _as_float(default_symbol_max_notional, 0.0))


def resolve_intent_conflicts(
    intents: List[Dict[str, Any]],
    *,
    default_symbol_max_notional: float = 0.0,
    symbol_max_notional_map: Optional[Dict[str, float]] = None,
    market_prices: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """M27-2: resolve simultaneous intent conflicts with deterministic policy.

    Policy:
    1. Same symbol opposite sides (BUY/SELL) cannot coexist:
       - keep intents from the side with stronger top priority score
       - block opposite side intents (`opposite_side_conflict`)
       - if tie, block all intents for the symbol (`side_conflict_tie`)
    2. Apply per-symbol notional cap:
       - keep higher-priority intents first
       - block overflow intents (`symbol_notional_cap_exceeded`)
    """

    cap_map: Dict[str, float] = {}
    if isinstance(symbol_max_notional_map, dict):
        for k, v in symbol_max_notional_map.items():
            cap_map[_norm_symbol(k)] = max(0.0, _as_float(v, 0.0))
    price_map: Dict[str, float] = {}
    if isinstance(market_prices, dict):
        for k, v in market_prices.items():
            price_map[_norm_symbol(k)] = max(0.0, _as_float(v, 0.0))

    failures: List[str] = []
    normalized: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    approved_stage1: List[Dict[str, Any]] = []

    if not isinstance(intents, list):
        failures.append("intents must be list")
        return {
            "ok": False,
            "intent_total": 0,
            "approved_total": 0,
            "blocked_total": 0,
            "invalid_total": 0,
            "blocked_reason_counts": {},
            "approved": [],
            "blocked": [],
            "failures": failures,
        }

    for idx, raw in enumerate(intents):
        if not isinstance(raw, dict):
            blocked.append({"index": idx, "status": "blocked", "reason": "invalid_intent_type", "intent": raw})
            continue

        symbol = _norm_symbol(raw.get("symbol"))
        side = _norm_side(raw)
        if not symbol:
            blocked.append({"index": idx, "status": "blocked", "reason": "missing_symbol", "intent": raw})
            continue
        if not side:
            blocked.append({"index": idx, "status": "blocked", "reason": "invalid_side", "intent": raw})
            continue

        requested_notional = _resolve_requested_notional(raw, symbol=symbol, market_prices=price_map)
        normalized.append(
            {
                "index": idx,
                "intent": raw,
                "strategy_id": str(raw.get("strategy_id") or ""),
                "symbol": symbol,
                "side": side,
                "requested_notional": requested_notional,
                "priority_score": _priority_score({**raw, "requested_notional": requested_notional}),
            }
        )

    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_symbol[row["symbol"]].append(row)

    for symbol in sorted(by_symbol.keys()):
        rows = sorted(by_symbol[symbol], key=lambda x: int(x["index"]))
        buys = [r for r in rows if r["side"] == "BUY"]
        sells = [r for r in rows if r["side"] == "SELL"]
        if buys and sells:
            best_buy = max(_as_float(x.get("priority_score"), 0.0) for x in buys)
            best_sell = max(_as_float(x.get("priority_score"), 0.0) for x in sells)
            eps = 1e-9
            if abs(best_buy - best_sell) <= eps:
                for r in rows:
                    blocked.append(
                        {
                            "index": int(r["index"]),
                            "strategy_id": r["strategy_id"],
                            "symbol": symbol,
                            "side": r["side"],
                            "requested_notional": float(r["requested_notional"]),
                            "priority_score": float(r["priority_score"]),
                            "status": "blocked",
                            "reason": "side_conflict_tie",
                            "intent": r["intent"],
                        }
                    )
                continue

            winning_side = "BUY" if best_buy > best_sell else "SELL"
            for r in rows:
                if r["side"] != winning_side:
                    blocked.append(
                        {
                            "index": int(r["index"]),
                            "strategy_id": r["strategy_id"],
                            "symbol": symbol,
                            "side": r["side"],
                            "requested_notional": float(r["requested_notional"]),
                            "priority_score": float(r["priority_score"]),
                            "status": "blocked",
                            "reason": "opposite_side_conflict",
                            "intent": r["intent"],
                        }
                    )
                    continue
                approved_stage1.append(r)
            continue

        approved_stage1.extend(rows)

    approved_final: List[Dict[str, Any]] = []
    by_symbol_stage1: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in approved_stage1:
        by_symbol_stage1[r["symbol"]].append(r)

    for symbol in sorted(by_symbol_stage1.keys()):
        rows = sorted(
            by_symbol_stage1[symbol],
            key=lambda x: (-_as_float(x.get("priority_score"), 0.0), int(x["index"])),
        )
        cap = _resolve_symbol_cap(
            symbol,
            default_symbol_max_notional=default_symbol_max_notional,
            symbol_max_notional_map=cap_map,
        )

        if cap <= 0.0:
            approved_final.extend(rows)
            continue

        used = 0.0
        for r in rows:
            requested = max(0.0, _as_float(r.get("requested_notional"), 0.0))
            if used + requested <= cap + 1e-9:
                used += requested
                approved_final.append(r)
                continue
            blocked.append(
                {
                    "index": int(r["index"]),
                    "strategy_id": r["strategy_id"],
                    "symbol": symbol,
                    "side": r["side"],
                    "requested_notional": float(requested),
                    "priority_score": float(r["priority_score"]),
                    "status": "blocked",
                    "reason": "symbol_notional_cap_exceeded",
                    "intent": r["intent"],
                    "symbol_cap_notional": float(cap),
                    "symbol_used_notional": float(used),
                }
            )

    approved: List[Dict[str, Any]] = []
    for r in sorted(approved_final, key=lambda x: int(x["index"])):
        approved.append(
            {
                "index": int(r["index"]),
                "strategy_id": r["strategy_id"],
                "symbol": r["symbol"],
                "side": r["side"],
                "requested_notional": float(r["requested_notional"]),
                "priority_score": float(r["priority_score"]),
                "status": "approved",
                "intent": r["intent"],
            }
        )

    reason_counts: Dict[str, int] = {}
    invalid_total = 0
    for r in blocked:
        reason = str(r.get("reason") or "")
        reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1
        if reason in ("invalid_intent_type", "missing_symbol", "invalid_side"):
            invalid_total += 1

    return {
        "ok": len(failures) == 0,
        "intent_total": len(intents),
        "approved_total": len(approved),
        "blocked_total": len(blocked),
        "invalid_total": int(invalid_total),
        "blocked_reason_counts": reason_counts,
        "approved": approved,
        "blocked": sorted(blocked, key=lambda x: int(_as_int(x.get("index"), 0))),
        "failures": failures,
    }
