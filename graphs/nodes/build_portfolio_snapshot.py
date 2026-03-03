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


def build_portfolio_snapshot(state: dict) -> dict:
    """M9 node: build portfolio_snapshot.
    Default: KiwoomPortfolioReader (real HTTP; host depends on KIWOOM_MODE).
    """
    if state.get("portfolio_reader") is not None:
        reader: PortfolioReader = state["portfolio_reader"]
    else:
        reader = KiwoomPortfolioReader.from_env()

    mock_mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"
    fallback_cash = float(os.getenv("MOCK_CASH_FALLBACK", "2000000") or 2000000)

    try:
        snap = reader.get_portfolio_snapshot()
    except Exception:
        if not mock_mode:
            raise
        snap = MockPortfolioReader(cash=fallback_cash, positions=[]).get_portfolio_snapshot()

    if mock_mode and float(getattr(snap, "cash", 0.0) or 0.0) <= 0.0:
        snap = MockPortfolioReader(cash=fallback_cash, positions=[]).get_portfolio_snapshot()

    snapshot = snap.to_dict()

    if mock_mode:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        persisted_positions = _normalize_positions((persisted or {}).get("mock_positions"))
        snapshot_positions = _normalize_positions(snapshot.get("positions"))

        # In mock mode, prefer persisted mock positions when API reader has no position data.
        if persisted_positions and not snapshot_positions:
            snapshot["positions"] = persisted_positions
        else:
            snapshot["positions"] = snapshot_positions

    positions = _normalize_positions(snapshot.get("positions"))
    snapshot["positions"] = positions
    snapshot["open_positions"] = len(positions)
    snapshot["cash"] = _safe_float(snapshot.get("cash"), fallback_cash)
    if snapshot["cash"] <= 0:
        snapshot["cash"] = float(fallback_cash)

    state["portfolio_snapshot"] = snapshot
    return state
