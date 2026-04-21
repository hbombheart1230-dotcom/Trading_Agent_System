from __future__ import annotations

from typing import Any, Dict

from libs.read.kiwoom_orderable_cash_reader import KiwoomOrderableCashReader


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_cash_truth(raw: Dict[str, Any], *, default_source: str) -> Dict[str, Any]:
    deposit = _to_float(raw.get("deposit"), 0.0)
    withdrawable_cash = _to_float(raw.get("withdrawable_cash"), 0.0)
    orderable_amount = _to_float(
        raw.get("orderable_amount")
        if raw.get("orderable_amount") not in (None, "")
        else raw.get("orderable_cash"),
        0.0,
    )
    source = str(raw.get("source") or default_source).strip()
    return {
        "broker_deposit": deposit,
        "broker_withdrawable_cash": withdrawable_cash,
        "broker_orderable_amount": orderable_amount,
        "cash_truth_source": source,
        "cash_truth_available": bool(deposit > 0.0 or withdrawable_cash > 0.0 or orderable_amount > 0.0),
    }


def _resolve_injected_cash_truth(state: Dict[str, Any]) -> Dict[str, Any]:
    direct = state.get("broker_orderable_cash_snapshot")
    if isinstance(direct, dict):
        return _normalize_cash_truth(direct, default_source="state.broker_orderable_cash_snapshot")

    snapshots = state.get("snapshots")
    if isinstance(snapshots, dict) and isinstance(snapshots.get("broker_orderable_cash"), dict):
        return _normalize_cash_truth(
            snapshots.get("broker_orderable_cash") or {},
            default_source="state.snapshots.broker_orderable_cash",
        )
    return {}


def resolve_risk_cash_truth(state: Dict[str, Any], *, portfolio_cash: float) -> Dict[str, Any]:
    resolved = _resolve_injected_cash_truth(state)
    if not resolved:
        reader = state.get("kiwoom_orderable_cash_reader")
        if reader is None:
            reader = KiwoomOrderableCashReader.from_env()
        try:
            resolved = _normalize_cash_truth(reader.get_deposit_snapshot(), default_source="kiwoom.kt00001")
        except Exception:
            resolved = {}

    if not resolved:
        return {
            "broker_deposit": 0.0,
            "broker_withdrawable_cash": 0.0,
            "broker_orderable_amount": 0.0,
            "capital_available_for_sizing": float(max(0.0, portfolio_cash)),
            "cash_truth_source": "portfolio.cash",
            "cash_truth_available": False,
        }

    capital_available = 0.0
    for key in ("broker_orderable_amount", "broker_withdrawable_cash", "broker_deposit"):
        value = _to_float(resolved.get(key), 0.0)
        if value > 0.0:
            capital_available = value
            break
    if capital_available <= 0.0:
        capital_available = float(max(0.0, portfolio_cash))

    resolved["capital_available_for_sizing"] = float(capital_available)
    return resolved
