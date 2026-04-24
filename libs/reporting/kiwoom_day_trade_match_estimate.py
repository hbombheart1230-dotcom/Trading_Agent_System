from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def infer_buy_price_from_monitor_context(
    *,
    monitor_context: Mapping[str, Any] | None,
) -> float | None:
    row = dict(monitor_context or {})
    current_price = _safe_float(row.get("current_price"))
    pnl_ratio = (
        _safe_float(row.get("account_pnl_ratio"))
        if row.get("account_pnl_ratio") not in (None, "")
        else _safe_float(row.get("effective_pnl_ratio"))
    )
    if current_price is None or pnl_ratio is None:
        return None
    if current_price <= 0 or pnl_ratio <= -0.999:
        return None
    implied_basis = current_price / (1.0 + pnl_ratio)
    if implied_basis <= 0:
        return None
    return implied_basis


def extract_buy_price_anchor_candidates(
    *,
    monitor_context: Mapping[str, Any] | None,
) -> List[Dict[str, Any]]:
    row = dict(monitor_context or {})
    out: List[Dict[str, Any]] = []
    seen: set[float] = set()
    for source, key in (
        ("position_average_price", "average_price"),
        ("position_avg_price", "avg_price"),
    ):
        value = _safe_float(row.get(key))
        if value is None or value <= 0:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append({"source": source, "price": value})
    return out


def select_best_buy_price_match(
    rows: List[Mapping[str, Any]],
    *,
    implied_buy_price: float | None,
    max_match_diff: float = 1000.0,
    min_margin: float = 100.0,
) -> Dict[str, Any]:
    if implied_buy_price is None:
        return {}
    candidates = []
    for row in list(rows or []):
        buy_price = _safe_float((row or {}).get("buy_price"))
        if buy_price is None:
            continue
        candidates.append((abs(buy_price - implied_buy_price), dict(row)))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0])
    best_diff, best_row = candidates[0]
    second_diff = candidates[1][0] if len(candidates) > 1 else None
    if best_diff > max_match_diff:
        return {}
    if second_diff is not None and (second_diff - best_diff) < min_margin:
        return {}
    return {
        "row": best_row,
        "best_diff": best_diff,
        "second_diff": second_diff,
    }


def select_best_buy_price_match_from_anchors(
    rows: List[Mapping[str, Any]],
    *,
    anchors: List[Mapping[str, Any]] | None,
    max_match_diff: float = 1000.0,
    min_margin: float = 100.0,
) -> Dict[str, Any]:
    for anchor in list(anchors or []):
        anchor_price = _safe_float((anchor or {}).get("price"))
        if anchor_price is None:
            continue
        best = select_best_buy_price_match(
            rows,
            implied_buy_price=anchor_price,
            max_match_diff=max_match_diff,
            min_margin=min_margin,
        )
        if best:
            best["anchor_source"] = str((anchor or {}).get("source") or "")
            best["anchor_price"] = anchor_price
            return best
    return {}


__all__ = [
    "extract_buy_price_anchor_candidates",
    "infer_buy_price_from_monitor_context",
    "select_best_buy_price_match",
    "select_best_buy_price_match_from_anchors",
]
