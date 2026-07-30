from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from libs.core.symbols import normalize_symbol


SCHEMA_VERSION = "same_symbol_loss_reentry_control.v1"
_KST = timezone(timedelta(hours=9))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _trading_day(epoch: int) -> str:
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(int(epoch), tz=_KST).date().isoformat()


def _return_ratio(execution: Mapping[str, Any]) -> tuple[float | None, str]:
    order = _mapping(execution.get("order"))
    meta = _mapping(order.get("meta"))
    payload = _mapping(execution.get("payload"))
    payload_result = _mapping(payload.get("broker_result"))
    broker_result = _mapping(execution.get("broker_result"))
    execution_details = _mapping(execution.get("execution_details"))
    candidates = (
        ("order.meta.pnl_ratio", meta.get("pnl_ratio")),
        ("order.meta.account_pnl_ratio", meta.get("account_pnl_ratio")),
        ("execution.broker_realized_pnl_pct", execution.get("broker_realized_pnl_pct")),
        ("execution_details.broker_realized_pnl_pct", execution_details.get("broker_realized_pnl_pct")),
        ("broker_result.broker_realized_pnl_pct", broker_result.get("broker_realized_pnl_pct")),
        ("payload.broker_result.broker_realized_pnl_pct", payload_result.get("broker_realized_pnl_pct")),
    )
    for source, raw in candidates:
        value = _float(raw)
        if value is None:
            continue
        if abs(value) > 1.0:
            value /= 100.0
        return float(value), source
    return None, ""


def _is_full_exit(execution: Mapping[str, Any]) -> bool:
    order = _mapping(execution.get("order"))
    meta = _mapping(order.get("meta"))
    if not _bool(meta.get("partial_exit")):
        return True
    exit_qty = _int(meta.get("exit_qty") or order.get("qty"))
    position_qty = _int(meta.get("position_qty"))
    return bool(position_qty > 0 and exit_qty >= position_qty)


def _control_map(raw: Any, *, current_day: str = "") -> dict[str, dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        row = _mapping(value)
        symbol = normalize_symbol(row.get("symbol") or key)
        day = str(row.get("trading_day") or "")
        if not symbol or not day:
            continue
        if current_day and day != current_day:
            continue
        out[symbol] = {**row, "symbol": symbol, "trading_day": day}
    return out


def record_same_symbol_exit(
    persisted_state: dict[str, Any],
    execution: Mapping[str, Any],
    *,
    now_epoch: int,
) -> dict[str, Any]:
    """Record a completed SELL outcome without inferring unavailable PnL."""

    order = _mapping(execution.get("order"))
    if str(order.get("action") or "").strip().upper() != "SELL":
        return {"recorded": False, "reason": "not_sell"}
    symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))
    if not symbol:
        return {"recorded": False, "reason": "symbol_missing"}
    if not _is_full_exit(execution):
        return {"recorded": False, "reason": "partial_exit"}

    day = _trading_day(int(now_epoch))
    ratio, source = _return_ratio(execution)
    outcome = "UNKNOWN" if ratio is None else "LOSS" if ratio < 0.0 else "NON_LOSS"
    controls = _control_map(
        persisted_state.get("same_symbol_loss_reentry_control_by_symbol"),
        current_day=day,
    )
    meta = _mapping(order.get("meta"))
    row = {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "trading_day": day,
        "exit_epoch": int(now_epoch),
        "outcome": outcome,
        "realized_return_ratio": ratio,
        "realized_return_source": source,
        "exit_reason": str(meta.get("exit_reason") or meta.get("reason") or order.get("reason") or ""),
        "source": "execution_full_sell",
    }
    controls[symbol] = row
    persisted_state["same_symbol_loss_reentry_control_by_symbol"] = controls
    return {"recorded": True, **row}


def evaluate_same_symbol_loss_reentry(
    state: Mapping[str, Any],
    *,
    symbol: str,
    now_epoch: int,
) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    day = _trading_day(int(now_epoch))
    persisted = _mapping(state.get("persisted_state"))
    controls = _control_map(
        persisted.get("same_symbol_loss_reentry_control_by_symbol"),
        current_day=day,
    )
    row = _mapping(controls.get(normalized_symbol))
    blocked = bool(row and row.get("outcome") == "LOSS")
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluated": bool(normalized_symbol and day),
        "blocked": blocked,
        "reason": "same_symbol_loss_reentry_blocked" if blocked else "no_same_day_loss_exit",
        "symbol": normalized_symbol,
        "trading_day": day,
        "prior_exit": row,
        "scope": "same_symbol_same_trading_day_after_full_loss_exit",
    }


__all__ = [
    "evaluate_same_symbol_loss_reentry",
    "record_same_symbol_exit",
]
