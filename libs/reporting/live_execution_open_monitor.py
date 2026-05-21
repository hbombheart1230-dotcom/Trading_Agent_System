from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from libs.core.symbols import normalize_symbol
from libs.reporting.trade_story_pipeline import safe_int


def safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def runtime_position_for_symbol(state_obj: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    if not normalized or not isinstance(state_obj, dict):
        return {}

    portfolio_snapshot = state_obj.get("portfolio_snapshot") if isinstance(state_obj.get("portfolio_snapshot"), dict) else {}
    sources = [
        ("portfolio_snapshot.positions", portfolio_snapshot.get("positions")),
        ("mock_positions", state_obj.get("mock_positions")),
    ]
    for source_name, rows in sources:
        if not isinstance(rows, list):
            continue
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            row_symbol = normalize_symbol(raw_row.get("symbol") or raw_row.get("code") or "", allow_test_symbols=True)
            if row_symbol != normalized:
                continue
            row = dict(raw_row)
            row["_source"] = source_name
            return row
    return {}


def derive_runtime_position_price(position: Dict[str, Any]) -> Tuple[Optional[float], str]:
    if not isinstance(position, dict):
        return None, ""
    direct_fields = (
        ("current_price", "runtime_state.position.current_price"),
        ("price", "runtime_state.position.price"),
        ("mark_price", "runtime_state.position.mark_price"),
        ("last_price", "runtime_state.position.last_price"),
    )
    for key, source in direct_fields:
        price = safe_float(position.get(key), None)
        if price and price > 0:
            return price, source

    avg_price = safe_float(position.get("avg_price"), None)
    qty = safe_int(position.get("qty"), 0)
    unrealized = safe_float(position.get("unrealized_pnl"), None)
    if avg_price and avg_price > 0 and qty > 0 and unrealized is not None:
        derived = avg_price + (unrealized / float(qty))
        if derived > 0:
            return derived, "runtime_state.position.avg_plus_unrealized"
    return None, ""


def append_unique_bullet(bullets: List[str], text: str) -> None:
    raw = str(text or "").strip()
    if not raw:
        return
    lowered = raw.lower()
    if any(str(existing or "").strip().lower() == lowered for existing in bullets):
        return
    bullets.append(raw)


def backfill_open_lifecycle_monitor_reason(
    monitor_reason_human: Dict[str, Any],
    *,
    lifecycle_status: str,
    symbol: str,
    state_obj: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(monitor_reason_human or {})
    if str(lifecycle_status or "").strip().lower() != "open":
        return out
    normalized_symbol = normalize_symbol(symbol or "", allow_test_symbols=True)
    if not normalized_symbol or not isinstance(state_obj, dict) or not state_obj:
        return out

    position = runtime_position_for_symbol(state_obj, normalized_symbol)
    peak_map = state_obj.get("position_peak_price") if isinstance(state_obj.get("position_peak_price"), dict) else {}
    bullets = [str(x or "").strip() for x in list(out.get("bullets") or []) if str(x or "").strip()]

    avg_price = out.get("average_price")
    if avg_price in (None, ""):
        avg_price = safe_float(position.get("avg_price"), None)
        if avg_price not in (None, ""):
            out["average_price"] = avg_price
            append_unique_bullet(bullets, f"Average price: {float(avg_price):.2f}")

    current_price = out.get("current_price")
    derived_price_source = ""
    current_price_backfilled = False
    if current_price in (None, ""):
        current_price, derived_price_source = derive_runtime_position_price(position)
        if current_price not in (None, ""):
            out["current_price"] = current_price
            current_price_backfilled = True
            append_unique_bullet(bullets, f"Current price: {float(current_price):.2f}")

    peak_price = out.get("peak_price")
    if peak_price in (None, ""):
        peak_price = safe_float(peak_map.get(normalized_symbol), None)
        if peak_price in (None, ""):
            peak_price = safe_float(position.get("peak_price"), None)
        if peak_price in (None, "") and avg_price not in (None, "") and current_price not in (None, ""):
            peak_price = max(float(avg_price), float(current_price))
        if peak_price not in (None, ""):
            out["peak_price"] = peak_price
            append_unique_bullet(bullets, f"Peak price: {float(peak_price):.2f}")

    current_drawdown = out.get("current_drawdown")
    if current_drawdown in (None, "") and current_price not in (None, "") and avg_price not in (None, "") and float(avg_price) > 0:
        current_drawdown = (float(current_price) / float(avg_price)) - 1.0
        out["current_drawdown"] = current_drawdown
        append_unique_bullet(bullets, f"Current drawdown: {current_drawdown * 100.0:.2f}%")

    peak_drawdown = out.get("peak_drawdown")
    if peak_drawdown in (None, "") and current_price not in (None, "") and peak_price not in (None, "") and float(peak_price) > 0:
        peak_drawdown = (float(current_price) / float(peak_price)) - 1.0
        out["peak_drawdown"] = peak_drawdown
        append_unique_bullet(bullets, f"Peak drawdown: {peak_drawdown * 100.0:.2f}%")

    if derived_price_source and current_price_backfilled:
        out["price_source"] = derived_price_source
        append_unique_bullet(bullets, f"Price source: {derived_price_source}")
    if derived_price_source and current_price_backfilled:
        policy = "runtime_state.position.current_price > runtime_state.position.avg_plus_unrealized > existing_monitor_fields"
        out["price_source_policy"] = policy
        append_unique_bullet(bullets, f"Price source policy: {policy}")

    if bullets:
        out["bullets"] = bullets
    return out
