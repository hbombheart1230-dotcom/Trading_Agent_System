from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from graphs.nodes.skill_contracts import norm_symbol
from libs.runtime.etf_deviation import extract_etf_deviation_signal


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def resolve_min_trading_value(policy: Dict[str, Any]) -> float:
    raw = policy.get("min_trading_value")
    if raw in (None, ""):
        raw = os.getenv("MIN_TRADING_VALUE", "0")
    return max(0.0, to_float(raw))


def resolve_min_volume(policy: Dict[str, Any]) -> float:
    raw = policy.get("min_volume")
    if raw in (None, ""):
        raw = os.getenv("MIN_VOLUME", "0")
    return max(0.0, to_float(raw))


def resolve_exclude_halted(policy: Dict[str, Any]) -> bool:
    if policy.get("exclude_halted") is not None:
        return is_trueish(policy.get("exclude_halted"))
    return is_trueish(os.getenv("EXCLUDE_HALTED_STOCKS", "true"))


def candidate_quote_metrics(
    symbol: str,
    *,
    skill_quotes: Dict[str, Dict[str, Any]],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    quote = skill_quotes.get(norm_symbol(symbol), {})
    if not isinstance(quote, dict):
        quote = {}
    skill_quote_available = bool(quote)
    fallback_used = False
    fallback = state.get("mock_candidate_metrics")
    if isinstance(fallback, dict) and isinstance(fallback.get(symbol), dict):
        merged = dict(fallback.get(symbol) or {})
        merged.update(quote)
        quote = merged
        fallback_used = True

    volume = to_float(quote.get("volume") or quote.get("vol") or quote.get("trading_volume"))
    trading_value = to_float(
        quote.get("value")
        or quote.get("trading_value")
        or quote.get("trade_value")
        or quote.get("amount")
    )
    change_pct = to_float(quote.get("change_pct") or quote.get("chg_rate") or quote.get("changeRate"))

    raw_quote = quote.get("raw") if isinstance(quote.get("raw"), dict) else {}
    raw_rows = raw_quote.get("cntr_infr") if isinstance(raw_quote.get("cntr_infr"), list) else []
    raw_row = raw_rows[0] if raw_rows and isinstance(raw_rows[0], dict) else {}
    best_ask = to_float(quote.get("best_ask") or quote.get("ask"))
    best_bid = to_float(quote.get("best_bid") or quote.get("bid"))
    if volume <= 0.0:
        volume = to_float(raw_row.get("acc_trde_qty"))
    if trading_value <= 0.0:
        trading_value = to_float(raw_row.get("acc_trde_prica"))
    if change_pct == 0.0:
        change_pct = to_float(raw_row.get("pre_rt"))
    if best_ask <= 0.0:
        best_ask = to_float(raw_row.get("pri_sel_bid_unit") or raw_row.get("sel_1bid"))
    if best_bid <= 0.0:
        best_bid = to_float(raw_row.get("pri_buy_bid_unit") or raw_row.get("buy_1bid"))
    deviation_signal = extract_etf_deviation_signal(
        symbol=symbol,
        quote=quote,
        state=state,
    )

    halted = False
    if quote.get("halted") is not None:
        halted = bool(quote.get("halted"))
    elif str(quote.get("status") or "").strip().lower() in ("halted", "suspended", "stop"):
        halted = True

    abnormal = False
    if quote.get("abnormal") is not None:
        abnormal = bool(quote.get("abnormal"))
    if str(quote.get("risk_flag") or "").strip().lower() in ("abnormal", "warning", "danger"):
        abnormal = True

    spread_bps = None
    if best_ask > 0.0 and best_bid > 0.0 and best_ask >= best_bid:
        mid = (best_ask + best_bid) / 2.0
        if mid > 0.0:
            spread_bps = ((best_ask - best_bid) / mid) * 10000.0

    return {
        "volume": float(max(0.0, volume)),
        "trading_value": float(max(0.0, trading_value)),
        "change_pct": float(change_pct),
        "best_ask": float(max(0.0, best_ask)),
        "best_bid": float(max(0.0, best_bid)),
        "spread_bps": (float(max(0.0, spread_bps)) if spread_bps is not None else None),
        "quote_payload_available": bool(quote),
        "quote_source": (
            "skill_quote+mock_fallback"
            if skill_quote_available and fallback_used
            else "skill_quote"
            if skill_quote_available
            else "mock_candidate_metrics"
            if fallback_used
            else "unavailable"
        ),
        "bid_ask_evidence_status": (
            "OBSERVED"
            if best_ask > 0.0 and best_bid > 0.0
            else "QUOTE_PAYLOAD_WITHOUT_BID_ASK"
            if quote
            else "QUOTE_PAYLOAD_UNAVAILABLE"
        ),
        "etf_deviation_pct": deviation_signal.get("etf_deviation_pct"),
        "etf_deviation_source": str(deviation_signal.get("etf_deviation_source") or ""),
        "etf_deviation_available": bool(deviation_signal.get("available")),
        "halted": bool(halted),
        "abnormal": bool(abnormal),
    }


def reduce_candidates_by_practical_filters(
    rows: List[Any],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    skill_quotes: Dict[str, Dict[str, Any]],
) -> Tuple[List[Any], Dict[str, Any]]:
    min_value = resolve_min_trading_value(policy)
    min_volume = resolve_min_volume(policy)
    exclude_halted = resolve_exclude_halted(policy)
    before = len(rows)

    if before <= 0:
        return rows, {
            "candidate_pool_before_filter": 0,
            "candidate_pool_after_filter": 0,
            "filtered_out_count": 0,
            "min_trading_value": float(min_value),
            "min_volume": float(min_volume),
            "exclude_halted": bool(exclude_halted),
            "excluded_halted": 0,
            "excluded_illiquid": 0,
            "excluded_abnormal": 0,
            "reduction_fallback_used": False,
            "reduction_filter_applied": False,
        }

    kept: List[Any] = []
    excluded_halted = 0
    excluded_illiquid = 0
    excluded_abnormal = 0
    for row in rows:
        symbol = norm_symbol(row.get("symbol") if isinstance(row, dict) else row)
        if not symbol:
            continue
        metrics = candidate_quote_metrics(symbol, skill_quotes=skill_quotes, state=state)
        halted = bool(metrics.get("halted"))
        abnormal = bool(metrics.get("abnormal"))
        trading_value = to_float(metrics.get("trading_value"))
        volume = to_float(metrics.get("volume"))

        drop = False
        if exclude_halted and halted:
            excluded_halted += 1
            drop = True
        elif abnormal:
            excluded_abnormal += 1
            drop = True
        else:
            low_value = min_value > 0.0 and trading_value > 0.0 and trading_value < min_value
            low_volume = min_volume > 0.0 and volume > 0.0 and volume < min_volume
            if low_value or low_volume:
                excluded_illiquid += 1
                drop = True
        if not drop:
            kept.append(row)

    reduction_fallback_used = False
    if not kept:
        # If strict filter empties the pool, keep original candidates to avoid scanner NOOP collapse.
        kept = list(rows)
        reduction_fallback_used = True

    return kept, {
        "candidate_pool_before_filter": int(before),
        "candidate_pool_after_filter": int(len(kept)),
        "filtered_out_count": int(max(0, before - len(kept))),
        "min_trading_value": float(min_value),
        "min_volume": float(min_volume),
        "exclude_halted": bool(exclude_halted),
        "excluded_halted": int(excluded_halted),
        "excluded_illiquid": int(excluded_illiquid),
        "excluded_abnormal": int(excluded_abnormal),
        "reduction_fallback_used": bool(reduction_fallback_used),
        "reduction_filter_applied": bool(min_value > 0.0 or min_volume > 0.0 or exclude_halted),
    }


def filter_mock_broker_restricted_candidates(
    rows: List[Any],
    *,
    state: Dict[str, Any],
) -> Tuple[List[Any], Dict[str, Any]]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    restricted = persisted.get("mock_broker_restricted_symbols") if isinstance(persisted.get("mock_broker_restricted_symbols"), dict) else {}
    if not restricted:
        return list(rows), {
            "mock_broker_restricted_filter_applied": False,
            "mock_broker_restricted_excluded_count": 0,
            "mock_broker_restricted_excluded_symbols": [],
            "mock_broker_restricted_exclusions": [],
            "candidate_pool_after_mock_broker_restricted_filter": int(len(rows)),
        }

    restricted_by_symbol: Dict[str, Dict[str, Any]] = {}
    for key, raw in restricted.items():
        record = raw if isinstance(raw, dict) else {}
        symbol = norm_symbol(record.get("symbol") or key)
        if symbol:
            restricted_by_symbol[symbol] = dict(record)

    kept: List[Any] = []
    exclusions: List[Dict[str, Any]] = []
    for row in rows:
        symbol = norm_symbol(row.get("symbol") if isinstance(row, dict) else row)
        record = restricted_by_symbol.get(symbol)
        if not record:
            kept.append(row)
            continue
        exclusions.append(
            {
                "symbol": symbol,
                "exclusion_reason": "mock_broker_restricted_symbol",
                "broker_code": str(record.get("broker_code") or ""),
                "broker_message": str(record.get("broker_message") or "")[:200],
                "detected_date": str(record.get("detected_date") or ""),
                "reason": str(record.get("reason") or ""),
            }
        )

    return kept, {
        "mock_broker_restricted_filter_applied": bool(exclusions),
        "mock_broker_restricted_excluded_count": int(len(exclusions)),
        "mock_broker_restricted_excluded_symbols": [row["symbol"] for row in exclusions],
        "mock_broker_restricted_exclusions": exclusions[:20],
        "candidate_pool_after_mock_broker_restricted_filter": int(len(kept)),
    }
