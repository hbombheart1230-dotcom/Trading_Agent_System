from __future__ import annotations

import os

from libs.core.symbols import normalize_symbol
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


def _safe_ratio(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if abs(out) > 1.0:
        out = out / 100.0
    return float(out)


def _normalize_positions(raw: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
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
        account_pnl_ratio = _safe_ratio(
            row.get("account_pnl_ratio")
            if row.get("account_pnl_ratio") not in (None, "")
            else row.get("unrealized_pnl_rate")
        )
        if account_pnl_ratio is not None:
            out[-1]["account_pnl_ratio"] = float(account_pnl_ratio)
            ratio_source = str(row.get("account_pnl_ratio_source") or "position.account_pnl_ratio").strip()
            out[-1]["account_pnl_ratio_source"] = ratio_source
        current_price = _safe_float(
            row.get("current_price")
            if row.get("current_price") not in (None, "")
            else row.get("cur_price"),
            0.0,
        )
        if current_price > 0.0:
            out[-1]["current_price"] = float(current_price)
    return out


def _positions_signature(rows: list[dict]) -> list[tuple[str, int, float]]:
    sig: list[tuple[str, int, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sig.append(
            (
                normalize_symbol(row.get("symbol")),
                _safe_int(row.get("qty"), 0),
                round(_safe_float(row.get("avg_price"), 0.0), 4),
            )
        )
    sig.sort()
    return sig


def _merge_position_current_prices(base_rows: list[dict], source_rows: list[dict]) -> list[dict]:
    if not isinstance(base_rows, list):
        return []
    current_price_by_symbol: dict[str, float] = {}
    account_pnl_ratio_by_symbol: dict[str, float] = {}
    account_pnl_ratio_source_by_symbol: dict[str, str] = {}
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol:
            continue
        current_price = _safe_float(
            row.get("current_price") if row.get("current_price") not in (None, "") else row.get("cur_price"),
            0.0,
        )
        if current_price > 0.0:
            current_price_by_symbol[symbol] = float(current_price)
        account_pnl_ratio = _safe_ratio(
            row.get("account_pnl_ratio")
            if row.get("account_pnl_ratio") not in (None, "")
            else row.get("unrealized_pnl_rate")
        )
        if account_pnl_ratio is not None:
            account_pnl_ratio_by_symbol[symbol] = float(account_pnl_ratio)
            account_pnl_ratio_source_by_symbol[symbol] = str(
                row.get("account_pnl_ratio_source") or "position.account_pnl_ratio"
            ).strip()

    merged: list[dict] = []
    for raw_row in base_rows:
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        symbol = normalize_symbol(row.get("symbol"))
        current_price = current_price_by_symbol.get(symbol, 0.0)
        if current_price > 0.0:
            row["current_price"] = float(current_price)
        if symbol in account_pnl_ratio_by_symbol:
            row["account_pnl_ratio"] = float(account_pnl_ratio_by_symbol[symbol])
            row["account_pnl_ratio_source"] = str(account_pnl_ratio_source_by_symbol.get(symbol) or "")
        merged.append(row)
    return merged


def _reader_positions_authoritative(*, mock_mode: bool, execution_mode: str, reader_ok: bool) -> bool:
    if not bool(reader_ok):
        return False
    if not mock_mode:
        return True
    # When runtime uses the real executor against Kiwoom mock host, account reader
    # is the best source of truth for manual sells / external mock-account changes.
    return str(execution_mode or "").strip().lower() == "real"


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
        if isinstance(persisted, dict):
            persisted["mock_positions"] = list(persisted_positions)
            persisted["open_positions"] = len(persisted_positions)
            normalized_last_trade_symbol = normalize_symbol((persisted or {}).get("last_trade_symbol"))
            if normalized_last_trade_symbol:
                persisted["last_trade_symbol"] = normalized_last_trade_symbol
            else:
                persisted.pop("last_trade_symbol", None)
        persisted_cash = _safe_float((persisted or {}).get("mock_cash"), 0.0)
        persisted_realized = _safe_float((persisted or {}).get("mock_realized_pnl"), 0.0)
        snapshot_positions = _normalize_positions(snapshot.get("positions"))
        positions_mismatch = _positions_signature(snapshot_positions) != _positions_signature(persisted_positions)
        reader_authoritative = _reader_positions_authoritative(
            mock_mode=mock_mode,
            execution_mode=execution_mode,
            reader_ok=bool(health.get("reader_ok")),
        )
        health["reader_positions_authoritative"] = bool(reader_authoritative)
        health["reader_positions_count"] = len(snapshot_positions)
        health["persisted_positions_count"] = len(persisted_positions)
        health["positions_mismatch_detected"] = bool(positions_mismatch)
        health["reconciliation_applied"] = False
        health["reconciliation_status"] = "aligned"

        # In mock mode with real executor -> Kiwoom mock host, reader positions are
        # authoritative even when empty. This keeps local state aligned when an
        # operator manually exits or when local mock ledger drifts.
        if reader_authoritative:
            snapshot["positions"] = snapshot_positions
            health["positions_source"] = (
                "reader_positions_authoritative"
                if snapshot_positions
                else "reader_positions_authoritative_empty"
            )
            if positions_mismatch:
                if isinstance(persisted, dict):
                    persisted["mock_positions"] = list(snapshot_positions)
                    persisted["open_positions"] = len(snapshot_positions)
                    persisted["mock_position_desync_reconciled"] = True
                    persisted["portfolio_reconcile_reason"] = "reader_positions_authoritative"
                health["reconciliation_applied"] = True
                health["reconciliation_status"] = "reconciled_to_reader"
            else:
                health["reconciliation_status"] = "reader_aligned"
            if isinstance(persisted, dict):
                persisted["mock_positions"] = list(snapshot_positions)
                persisted["open_positions"] = len(snapshot_positions)
        # In pure local mock execution, fall back to persisted mock ledger when
        # reader does not return positions.
        elif snapshot_positions:
            snapshot["positions"] = snapshot_positions
            health["positions_source"] = "reader_positions"
            if isinstance(persisted, dict) and persisted_positions:
                persisted["mock_positions"] = _merge_position_current_prices(persisted_positions, snapshot_positions)
                persisted["open_positions"] = len(_normalize_positions(persisted.get("mock_positions")))
        elif persisted_positions:
            snapshot["positions"] = persisted_positions
            health["positions_source"] = "persisted_mock_positions"
            health["reconciliation_status"] = "persisted_fallback"
        else:
            snapshot["positions"] = []
            health["positions_source"] = "reader_positions_empty"
            health["reconciliation_status"] = "empty"
        if reader_authoritative:
            health["cash_source"] = "reader_cash_authoritative"
        elif persisted_cash > 0.0:
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
