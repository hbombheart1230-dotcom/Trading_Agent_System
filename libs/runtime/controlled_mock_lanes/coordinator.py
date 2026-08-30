from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.core.symbols import normalize_symbol
from libs.runtime.same_symbol_loss_reentry import evaluate_same_symbol_loss_reentry

from .artifacts import q10_artifact_paths, q12_hypothesis_path, read_json
from .contracts import (
    DEFAULT_ORDER_QTY,
    INDEPENDENT_LANES,
    LANE_WINDOWS_KST,
    SCHEMA_VERSION,
)
from .ledger import lane_already_submitted, reserve_submission
from .signals import (
    build_q10_index_candidate,
    build_q10_semiconductor_candidate,
    build_q12_candidate,
)


KST = timezone(timedelta(hours=9))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _enabled() -> bool:
    return _text(os.getenv("CONTROLLED_MOCK_LANES_ENABLED", "true")).lower() not in {
        "0", "false", "no", "off", "disabled"
    }


def _now_epoch(state: Mapping[str, Any]) -> int:
    for key in ("now_epoch", "ts_epoch", "current_epoch"):
        value = _int(state.get(key))
        if value > 0:
            return value
    raw = state.get("ts")
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    return int(time.time())


def _inside_lane_window(lane_id: str, now: datetime) -> bool:
    start, end = LANE_WINDOWS_KST[lane_id]
    minute = now.hour * 60 + now.minute
    return start[0] * 60 + start[1] <= minute <= end[0] * 60 + end[1]


def _positions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    snapshot = _mapping(state.get("portfolio_snapshot"))
    rows = snapshot.get("positions")
    if not isinstance(rows, list):
        rows = _mapping(state.get("persisted_state")).get("mock_positions")
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def _held_symbols(state: Mapping[str, Any]) -> set[str]:
    return {
        normalize_symbol(row.get("symbol") or row.get("stk_cd") or row.get("code"))
        for row in _positions(state)
        if _int(row.get("qty") or row.get("quantity") or row.get("hold_qty")) > 0
    } - {""}


def _pending_buy_symbols(state: Mapping[str, Any]) -> set[str]:
    output: set[str] = set()
    containers = (
        state.get("account_orders"),
        _mapping(state.get("portfolio_snapshot")).get("orders"),
        _mapping(state.get("persisted_state")).get("pending_unfilled_orders"),
    )
    for container in containers:
        rows = container.values() if isinstance(container, Mapping) else container or []
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            side = _text(raw.get("side") or raw.get("action") or raw.get("ord_dvsn_name")).upper()
            remaining = _int(
                raw.get("remaining_qty")
                or raw.get("unfilled_qty")
                or raw.get("rmn_qty")
                or raw.get("qty")
            )
            if "BUY" not in side and "매수" not in side:
                continue
            if remaining <= 0:
                continue
            symbol = normalize_symbol(raw.get("symbol") or raw.get("stk_cd") or raw.get("code"))
            if symbol:
                output.add(symbol)
    return output


def _max_positions(state: Mapping[str, Any]) -> int:
    risk_context = _mapping(state.get("risk_context"))
    policy = _mapping(state.get("policy"))
    for value in (
        risk_context.get("max_positions"),
        _mapping(state.get("risk")).get("max_positions"),
        policy.get("max_positions"),
        os.getenv("RISK_MAX_POSITIONS"),
    ):
        number = _int(value)
        if number > 0:
            return number
    return 3


def _restricted_symbols(state: Mapping[str, Any]) -> set[str]:
    raw = _mapping(_mapping(state.get("persisted_state")).get("mock_broker_restricted_symbols"))
    return {normalize_symbol(key) for key in raw if normalize_symbol(key)}


def _load_candidates(*, reports_root: Path, day: str, now_epoch: int) -> list[dict[str, Any]]:
    output = []
    q12 = build_q12_candidate(
        read_json(q12_hypothesis_path(reports_root, day)), now_epoch=now_epoch
    )
    if q12:
        output.append(q12)
    q10_paths = q10_artifact_paths(reports_root, day)
    preopen = read_json(q10_paths["preopen"])
    reactions = read_json(q10_paths["reactions"])
    expected = read_json(q10_paths["expected_actual"])
    semiconductor = build_q10_semiconductor_candidate(
        preopen=preopen,
        reactions=reactions,
        expected_actual=expected,
        now_epoch=now_epoch,
    )
    if semiconductor:
        output.append(semiconductor)
    index = build_q10_index_candidate(
        preopen=preopen,
        reactions=reactions,
        expected_actual=expected,
        now_epoch=now_epoch,
    )
    if index:
        output.append(index)
    return output


def _strategy_snapshot(candidate: Mapping[str, Any]) -> dict[str, Any]:
    horizon = _text(candidate.get("horizon")) or "intraday"
    return {
        "strategy_horizon": horizon,
        "expected_hold_window": {
            "min_sec": 300,
            "target_sec": 1800,
            "max_sec": 14400,
        },
        "playbook": "controlled_signal_validation",
        "tactical_subtype": _text(candidate.get("lane_id")).lower(),
        "llm_used": False,
        "controlled_mock_lane": True,
        "horizon_revision_allowed": False,
    }


def _intent(candidate: Mapping[str, Any], reservation: Mapping[str, Any]) -> dict[str, Any]:
    lane_id = _text(candidate.get("lane_id"))
    return {
        "symbol": normalize_symbol(candidate.get("symbol")),
        "side": "BUY",
        "qty": DEFAULT_ORDER_QTY,
        "price": candidate.get("price"),
        "risk_score": 0.0,
        "confidence": 1.0,
        "thesis": f"controlled mock validation lane: {lane_id}",
        "meta": {
            "entry_signal_source": "monitor_intraday_entry",
            "entry_lane": f"controlled_mock:{lane_id}",
            "entry_reason": "controlled_mock_lane_signal_confirmed",
            "controlled_mock_lane": {
                "schema_version": SCHEMA_VERSION,
                **dict(candidate),
                "daily_limit": 1,
                "reservation": dict(reservation),
            },
            "position_strategy_snapshot": _strategy_snapshot(candidate),
            "price": candidate.get("price"),
            "current_price": candidate.get("price"),
            "order_price_source": "controlled_mock_lane_artifact",
        },
    }


def inject_controlled_mock_lane_intent(
    state: dict[str, Any],
    *,
    reports_root: Path | str = Path("reports"),
    ledger_root: Path | str | None = None,
) -> dict[str, Any]:
    now_epoch = _now_epoch(state)
    now = datetime.fromtimestamp(now_epoch, tz=KST)
    day = now.date().isoformat()
    surface: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "enabled": _enabled(),
        "evaluated": False,
        "injected": False,
        "day": day,
        "now_epoch": now_epoch,
        "reason": "",
        "candidates": [],
    }

    def finish(reason: str) -> dict[str, Any]:
        surface["reason"] = reason
        state["controlled_mock_lanes"] = surface
        return state

    if not surface["enabled"]:
        return finish("disabled")
    if _text(os.getenv("KIWOOM_MODE")).lower() != "mock":
        return finish("kiwoom_mock_required")
    if _text(os.getenv("EXECUTION_MODE")).lower() != "real":
        return finish("mock_broker_http_execution_required")
    if _text(state.get("runtime_phase") or "session").lower() != "session":
        return finish("session_phase_required")
    intents = state.get("intents")
    if isinstance(intents, list) and intents:
        return finish("existing_monitor_intent_has_priority")
    held = _held_symbols(state)
    if len(held) >= _max_positions(state):
        return finish("max_positions_reached")

    candidates = _load_candidates(
        reports_root=Path(reports_root), day=day, now_epoch=now_epoch
    )
    surface["evaluated"] = True
    surface["candidates"] = [dict(row) for row in candidates]
    pending = _pending_buy_symbols(state)
    restricted = _restricted_symbols(state)
    eligible = []
    blocked = []
    for candidate in candidates:
        lane_id = _text(candidate.get("lane_id"))
        symbol = normalize_symbol(candidate.get("symbol"))
        reason = ""
        if lane_id not in INDEPENDENT_LANES:
            reason = "unknown_lane"
        elif not _inside_lane_window(lane_id, now):
            reason = "outside_lane_window"
        elif lane_already_submitted(day, lane_id, root=ledger_root):
            reason = "daily_lane_limit_reached"
        elif symbol in held:
            reason = "symbol_already_held"
        elif symbol in pending:
            reason = "symbol_pending_buy"
        elif symbol in restricted:
            reason = "mock_broker_restricted_symbol"
        else:
            reentry = evaluate_same_symbol_loss_reentry(
                state, symbol=symbol, now_epoch=now_epoch
            )
            if reentry.get("blocked"):
                reason = "same_symbol_loss_reentry_blocked"
        if reason:
            blocked.append({"lane_id": lane_id, "symbol": symbol, "reason": reason})
        else:
            eligible.append(candidate)
    surface["blocked"] = blocked
    if not eligible:
        return finish("no_eligible_independent_lane")

    candidate = max(eligible, key=lambda row: float(row.get("score") or 0.0))
    reservation = reserve_submission(
        day=day,
        candidate=candidate,
        run_id=_text(state.get("run_id")),
        recorded_at=datetime.fromtimestamp(now_epoch, tz=KST).isoformat(),
        root=ledger_root,
    )
    if not reservation.get("recorded"):
        surface["reservation"] = dict(reservation)
        return finish(_text(reservation.get("reason")) or "reservation_failed")
    intent = _intent(candidate, reservation)
    state["intents"] = [intent]
    surface["injected"] = True
    surface["selected_lane"] = _text(candidate.get("lane_id"))
    surface["selected_symbol"] = normalize_symbol(candidate.get("symbol"))
    surface["reservation"] = dict(reservation)
    surface["reason"] = "controlled_mock_lane_intent_injected"
    state["controlled_mock_lanes"] = surface
    return state


__all__ = ["inject_controlled_mock_lane_intent"]
