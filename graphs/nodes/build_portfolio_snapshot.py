from __future__ import annotations

import json
import os
import time
from pathlib import Path

from libs.core.symbols import normalize_symbol
from libs.read.portfolio_reader import PortfolioReader
from libs.read.portfolio_reader import MockPortfolioReader
from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader, _extract_cash, _extract_positions
from libs.read.snapshot_models import PortfolioSnapshot


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


def _snapshot_payload_has_auth_failure(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    text = json.dumps(payload, ensure_ascii=False).lower()
    return any(token in text for token in ("token", "8005", "805004", "인증에 실패"))


def _portfolio_snapshot_from_account_log_payload(payload: dict) -> PortfolioSnapshot | None:
    cash = _extract_cash(payload)
    positions = _extract_positions(payload)
    if cash > 0.0 or positions:
        return PortfolioSnapshot(cash=cash, positions=positions)
    return None


def _load_valid_account_snapshot_fallback() -> tuple[PortfolioSnapshot, dict] | None:
    root = Path(os.getenv("KIWOOM_ACCOUNT_SNAPSHOT_ROOT", "data/logs/kiwoom_account_snapshots"))
    if not root.exists():
        return None
    files = sorted(root.glob("**/*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        if path.name == "latest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        calls = payload.get("calls") if isinstance(payload.get("calls"), list) else []
        if not calls:
            continue
        if any(_snapshot_payload_has_auth_failure((call or {}).get("payload")) for call in calls if isinstance(call, dict)):
            continue
        best: PortfolioSnapshot | None = None
        for api_id in ("kt00018", "kt00004", "ka10085"):
            for call in calls:
                if not isinstance(call, dict) or str(call.get("api_id") or "") != api_id:
                    continue
                call_payload = call.get("payload") if isinstance(call.get("payload"), dict) else {}
                if str(call_payload.get("return_code")) not in ("0", ""):
                    continue
                snap = _portfolio_snapshot_from_account_log_payload(call_payload)
                if snap is not None:
                    best = snap
                    break
            if best is not None:
                meta = {
                    "source_path": str(path),
                    "generated_at": str(payload.get("generated_at") or ""),
                    "day": str(payload.get("day") or ""),
                    "trigger": str(payload.get("trigger") or ""),
                }
                return best, meta
    return None


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
        entry_epoch = _safe_int(
            row.get("position_entry_epoch")
            if row.get("position_entry_epoch") not in (None, "")
            else row.get("entry_epoch"),
            0,
        )
        if entry_epoch > 0:
            out[-1]["position_entry_epoch"] = int(entry_epoch)
        hold_sec = _safe_int(
            row.get("hold_sec")
            if row.get("hold_sec") not in (None, "")
            else row.get("position_age_seconds"),
            0,
        )
        if hold_sec > 0:
            out[-1]["hold_sec"] = int(hold_sec)
            out[-1]["position_age_seconds"] = int(hold_sec)
    return out


def _normalize_position_entry_epoch_map(raw: object, open_symbols: object = None) -> dict[str, int]:
    out: dict[str, int] = {}
    allowed = None
    if isinstance(open_symbols, (list, set, tuple)):
        allowed = {normalize_symbol(sym) for sym in open_symbols if normalize_symbol(sym)}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        symbol = normalize_symbol(key)
        if not symbol:
            continue
        if allowed is not None and symbol not in allowed:
            continue
        epoch = _safe_int(value, 0)
        if epoch > 0:
            out[symbol] = int(epoch)
    return out


def _apply_position_entry_epoch_map(rows: list[dict], epoch_map: dict[str, int]) -> list[dict]:
    out: list[dict] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        symbol = normalize_symbol(row.get("symbol"))
        epoch = _safe_int(epoch_map.get(symbol), 0)
        if epoch > 0:
            row["position_entry_epoch"] = int(epoch)
        out.append(row)
    return out


def _merge_position_metadata(base_rows: list[dict], source_rows: list[dict]) -> list[dict]:
    metadata: dict[str, dict] = {}
    for raw_row in source_rows:
        if not isinstance(raw_row, dict):
            continue
        symbol = normalize_symbol(raw_row.get("symbol"))
        if not symbol:
            continue
        meta = {}
        for key in ("position_entry_epoch", "hold_sec", "position_age_seconds"):
            if raw_row.get(key) not in (None, ""):
                meta[key] = raw_row.get(key)
        if meta:
            metadata[symbol] = meta

    out: list[dict] = []
    for raw_row in base_rows:
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        symbol = normalize_symbol(row.get("symbol"))
        for key, value in (metadata.get(symbol) or {}).items():
            if row.get(key) in (None, ""):
                row[key] = value
        out.append(row)
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


_RECENT_BUY_GUARD_CANONICAL_PATH = Path("data/state/execution_recent_buy_guard.json")


def _recent_buy_guard_path() -> Path:
    raw = os.getenv("EXECUTION_RECENT_BUY_GUARD_PATH", "") or str(_RECENT_BUY_GUARD_CANONICAL_PATH)
    # Phase 1 Step 5B Safety Fix: this module has its own independent
    # default-path resolution for the same recent-buy-guard file that
    # graphs/nodes/execute_from_packet.py writes -- isolate it the same way
    # (found during Step 5B Safety Fix's pytest production-path audit;
    # read-only here, but an unisolated default is still a latent risk if
    # this function is ever extended to write).
    from libs.core.path_isolation import isolate_canonical_path_for_pytest

    return isolate_canonical_path_for_pytest(
        raw, canonical_path=_RECENT_BUY_GUARD_CANONICAL_PATH, isolated_name="execution_recent_buy_guard.json"
    )


def _active_recent_buy_symbols(*, now_epoch: int | None = None) -> set[str]:
    path = _recent_buy_guard_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    orders = payload.get("orders") if isinstance(payload, dict) else {}
    if not isinstance(orders, dict):
        return set()
    now_value = int(now_epoch if now_epoch is not None else time.time())
    grace_sec = max(
        0,
        _safe_int(os.getenv("BROKER_POSITION_SETTLEMENT_GRACE_SEC", "180"), 180),
    )
    symbols: set[str] = set()
    for key, raw in orders.items():
        row = raw if isinstance(raw, dict) else {}
        symbol = normalize_symbol(row.get("symbol") or key)
        last_buy_epoch = _safe_int(row.get("last_buy_epoch"), 0)
        if (
            symbol
            and grace_sec > 0
            and last_buy_epoch > 0
            and 0 <= now_value - last_buy_epoch <= grace_sec
        ):
            symbols.add(symbol)
    return symbols


def _should_hold_recent_buy_settlement(
    *,
    snapshot_positions: list[dict],
    persisted_positions: list[dict],
) -> bool:
    if snapshot_positions or not persisted_positions:
        return False
    persisted_symbols = {
        normalize_symbol(row.get("symbol"))
        for row in persisted_positions
        if isinstance(row, dict) and normalize_symbol(row.get("symbol"))
    }
    return bool(persisted_symbols & _active_recent_buy_symbols())


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
        account_log_fallback = _load_valid_account_snapshot_fallback() if execution_mode == "real" else None
        if account_log_fallback is not None:
            snap, fallback_meta = account_log_fallback
            health["reader_ok"] = True
            health["source"] = "account_snapshot_fallback_after_reader_error"
            health["fallback_source_path"] = str(fallback_meta.get("source_path") or "")
            health["fallback_generated_at"] = str(fallback_meta.get("generated_at") or "")
            health["fallback_day"] = str(fallback_meta.get("day") or "")
            health["fallback_trigger"] = str(fallback_meta.get("trigger") or "")
        else:
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
        entry_epoch_map = _normalize_position_entry_epoch_map(
            (persisted or {}).get("position_entry_epoch_by_symbol"),
            [row.get("symbol") for row in persisted_positions],
        )
        if entry_epoch_map:
            persisted_positions = _apply_position_entry_epoch_map(persisted_positions, entry_epoch_map)
        if isinstance(persisted, dict):
            persisted["mock_positions"] = list(persisted_positions)
            persisted["open_positions"] = len(persisted_positions)
            if entry_epoch_map:
                persisted["position_entry_epoch_by_symbol"] = dict(entry_epoch_map)
            else:
                persisted.pop("position_entry_epoch_by_symbol", None)
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
            settlement_grace = _should_hold_recent_buy_settlement(
                snapshot_positions=snapshot_positions,
                persisted_positions=persisted_positions,
            )
            health["recent_buy_settlement_grace_applied"] = bool(settlement_grace)
            if settlement_grace:
                snapshot_positions = list(persisted_positions)
            snapshot_positions = _merge_position_metadata(snapshot_positions, persisted_positions)
            snapshot["positions"] = snapshot_positions
            health["positions_source"] = (
                "persisted_recent_buy_settlement_grace"
                if settlement_grace
                else "reader_positions_authoritative"
                if snapshot_positions
                else "reader_positions_authoritative_empty"
            )
            if positions_mismatch:
                if isinstance(persisted, dict):
                    persisted["mock_positions"] = list(snapshot_positions)
                    persisted["open_positions"] = len(snapshot_positions)
                    persisted["mock_position_desync_reconciled"] = True
                    persisted["portfolio_reconcile_reason"] = (
                        "recent_buy_settlement_grace"
                        if settlement_grace
                        else "reader_positions_authoritative"
                    )
                health["reconciliation_applied"] = True
                health["reconciliation_status"] = (
                    "recent_buy_settlement_grace"
                    if settlement_grace
                    else "reconciled_to_reader"
                )
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
