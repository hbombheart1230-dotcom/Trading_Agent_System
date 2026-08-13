from __future__ import annotations

from typing import Any, Mapping


KA10027_RAW_FIELDS = (
    "stk_cls",
    "stk_cd",
    "stk_nm",
    "cur_prc",
    "pred_pre_sig",
    "pred_pre",
    "flu_rt",
    "sel_req",
    "buy_req",
    "now_trde_qty",
    "cntr_str",
    "cnt",
)

KA10027_REQUEST_FILTERS = {
    "mrkt_tp": "000",
    "sort_tp": "1",
    "trde_qty_cnd": "0000",
    "stk_cnd": "1",
    "crd_cnd": "0",
    "updown_incls": "0",
    "pric_cnd": "0",
    "trde_prica_cnd": "0",
    "stex_tp": "1",
}


def _number(value: Any, *, absolute: bool = False) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return abs(parsed) if absolute else parsed


def _integer(value: Any, *, absolute: bool = False) -> int | None:
    parsed = _number(value, absolute=absolute)
    return int(parsed) if parsed is not None else None


def build_top_change_rate_observation(
    raw_row: Mapping[str, Any],
    *,
    source_rank: int,
    captured_epoch: int | None = None,
    captured_at: str = "",
) -> dict[str, Any]:
    """Preserve the point-in-time ka10027 row without affecting ranking."""
    raw_fields = {
        key: raw_row.get(key)
        for key in KA10027_RAW_FIELDS
        if raw_row.get(key) not in (None, "")
    }
    return {
        "schema_version": "kiwoom_top_change_rate_observation.v1",
        "behavior_effect": "observation_only",
        "source": "top_change_rate",
        "api_id": "ka10027",
        "source_rank": max(1, int(source_rank)),
        "captured_epoch": int(captured_epoch or 0) or None,
        "captured_at": str(captured_at or ""),
        "point_in_time": True,
        "request_filters": dict(KA10027_REQUEST_FILTERS),
        "raw_fields": raw_fields,
        "normalized": {
            "symbol": str(raw_row.get("symbol") or raw_row.get("stk_cd") or ""),
            "symbol_name": str(raw_row.get("stk_nm") or ""),
            "stock_class": str(raw_row.get("stk_cls") or ""),
            "current_price": _number(raw_row.get("cur_prc"), absolute=True),
            "previous_change_sign": str(raw_row.get("pred_pre_sig") or ""),
            "previous_change_amount": _number(raw_row.get("pred_pre")),
            "change_rate_pct": _number(raw_row.get("flu_rt")),
            "sell_order_quantity": _integer(raw_row.get("sel_req"), absolute=True),
            "buy_order_quantity": _integer(raw_row.get("buy_req"), absolute=True),
            "current_volume": _integer(raw_row.get("now_trde_qty"), absolute=True),
            "execution_strength": _number(raw_row.get("cntr_str"), absolute=True),
            "rank_entry_count": _integer(raw_row.get("cnt"), absolute=True),
        },
    }
