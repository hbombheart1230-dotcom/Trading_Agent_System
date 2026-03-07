from __future__ import annotations

import os

from libs.read.portfolio_reader import PortfolioReader
from libs.read.portfolio_reader import MockPortfolioReader
from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_positions(raw: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip()
        qty = _safe_int(row.get("qty"), 0)
        if not symbol or qty <= 0:
            continue
        out.append(
            {
                "symbol": symbol,
                "qty": qty,
                "avg_price": _safe_float(row.get("avg_price"), 0.0),
                "unrealized_pnl": _safe_float(row.get("unrealized_pnl"), 0.0),
            }
        )
    return out


def _resolve_execution_mode() -> str:
    mode = str(os.getenv("EXECUTION_MODE", "") or "").strip().lower()
    if mode in ("mock", "real"):
        return mode
    base = str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower()
    return "real" if base == "real" else "mock"


def build_portfolio_snapshot(state: dict) -> dict:
    """M9 node: build portfolio_snapshot.
    Default: KiwoomPortfolioReader (real HTTP; host depends on KIWOOM_MODE).
    """
    if state.get("portfolio_reader") is not None:
        reader: PortfolioReader = state["portfolio_reader"]
    else:
        reader = KiwoomPortfolioReader.from_env()

    mock_mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"
    execution_mode = _resolve_execution_mode()
    fallback_cash = float(os.getenv("MOCK_CASH_FALLBACK", "2000000") or 2000000)
    health = {
        "reader_ok": True,
        "reader_error": "",
        "fallback_applied": False,
        "source": "reader",
        "kiwoom_mode": "mock" if mock_mode else "real",
        "execution_mode": execution_mode,
    }

    try:
        snap = reader.get_portfolio_snapshot()
    except Exception as e:
        health["reader_ok"] = False
        health["reader_error"] = str(e)
        health["fallback_applied"] = True
        health["source"] = "mock_fallback_after_reader_error"
        if not mock_mode:
            raise
        snap = MockPortfolioReader(cash=fallback_cash, positions=[]).get_portfolio_snapshot()

    if mock_mode and float(getattr(snap, "cash", 0.0) or 0.0) <= 0.0:
        health["fallback_applied"] = True
        if health.get("source") == "reader":
            health["source"] = "mock_fallback_after_non_positive_cash"
        snap = MockPortfolioReader(cash=fallback_cash, positions=[]).get_portfolio_snapshot()

    snapshot = snap.to_dict()

    if mock_mode:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        persisted_positions = _normalize_positions((persisted or {}).get("mock_positions"))
        persisted_cash = _safe_float((persisted or {}).get("mock_cash"), 0.0)
        persisted_realized = _safe_float((persisted or {}).get("mock_realized_pnl"), 0.0)
        snapshot_positions = _normalize_positions(snapshot.get("positions"))

        # In mock mode, prefer persisted mock ledger when available.
        if persisted_positions:
            snapshot["positions"] = persisted_positions
            health["positions_source"] = "persisted_mock_positions"
        else:
            snapshot["positions"] = snapshot_positions
            health["positions_source"] = "reader_positions"
        if persisted_cash > 0.0:
            snapshot["cash"] = float(persisted_cash)
            health["cash_source"] = "persisted_mock_cash"
        else:
            health["cash_source"] = "reader_cash_or_fallback"
        snapshot["realized_pnl"] = float(persisted_realized)
    else:
        health["positions_source"] = "reader_positions"
        health["cash_source"] = "reader_cash"

    positions = _normalize_positions(snapshot.get("positions"))
    snapshot["positions"] = positions
    snapshot["open_positions"] = len(positions)
    snapshot["cash"] = _safe_float(snapshot.get("cash"), fallback_cash)
    if snapshot["cash"] <= 0:
        snapshot["cash"] = float(fallback_cash)

    health["open_positions"] = int(snapshot["open_positions"])
    health["cash"] = float(snapshot["cash"])
    snapshot["_health"] = dict(health)
    state["portfolio_snapshot_health"] = dict(health)
    state["portfolio_snapshot"] = snapshot
    return state
