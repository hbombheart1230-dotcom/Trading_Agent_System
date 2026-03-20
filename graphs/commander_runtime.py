from __future__ import annotations

"""M21-1: Canonical commander runtime entry.

This module provides one stable entry for orchestration while preserving
existing runtime behavior.

Implementation note:
  - This file is the primary commander/orchestrator implementation.
  - `graphs/nodes/commander_node.py` is a thin graph wrapper.
  - `libs/agent/commander.py` is legacy compatibility scaffolding.
  - Commander only routes runtime flow; it does not select symbols or execute orders.

Modes:
  - graph_spine: run M17 graph spine (`run_trading_graph`)
  - decision_packet: run strategist decision + execution packet path
    (`decide_trade` -> `execute_from_packet`)
  - integrated_chain: run visible chain
    (`strategist_node -> scanner_node -> monitor_node -> decision_node -> execute_from_packet`)

Default mode is graph_spine for backward compatibility.
"""

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional, Tuple

from graphs.trading_graph import run_trading_graph
from graphs.nodes.decide_trade import decide_trade
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.runtime.canonical_artifacts import write_commander_artifact
from libs.runtime.resilience_state import ensure_runtime_resilience_state


RuntimeMode = Literal["graph_spine", "decision_packet", "integrated_chain"]
RuntimePhase = Literal["preopen", "session", "closeout"]


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_mode(value: Any) -> RuntimeMode:
    v = str(value or "").strip().lower()
    if v == "decision_packet":
        return "decision_packet"
    if v in ("integrated_chain", "integrated", "chain"):
        return "integrated_chain"
    return "graph_spine"


def _normalize_transition(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("retry", "pause", "cancel", "resume"):
        return v
    return ""


def _normalize_phase(value: Any) -> RuntimePhase:
    v = str(value or "").strip().lower()
    if v == "preopen":
        return "preopen"
    if v == "closeout":
        return "closeout"
    return "session"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _runtime_now_epoch(state: Dict[str, Any]) -> int:
    return _coerce_int(state.get("now_epoch"), int(time.time()))


def _resolve_commander_cooldown_policy(state: Dict[str, Any]) -> Tuple[int, int]:
    policy = state.get("resilience_policy") if isinstance(state.get("resilience_policy"), dict) else {}
    threshold_default = _coerce_int(os.getenv("COMMANDER_INCIDENT_THRESHOLD", "0"), 0)
    cooldown_default = _coerce_int(os.getenv("COMMANDER_COOLDOWN_SEC", "0"), 0)
    threshold = _coerce_int(policy.get("incident_threshold"), threshold_default)
    cooldown_sec = _coerce_int(policy.get("cooldown_sec"), cooldown_default)
    return max(0, threshold), max(0, cooldown_sec)


def _set_degrade_mode(state: Dict[str, Any], *, reason: str) -> None:
    resilience = state.get("resilience")
    if not isinstance(resilience, dict):
        resilience = {}
        state["resilience"] = resilience
    resilience["degrade_mode"] = True
    if not str(resilience.get("degrade_reason") or "").strip():
        resilience["degrade_reason"] = str(reason or "")


def _apply_commander_cooldown_guard(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """M23-4: apply incident/cooldown policy before running node path."""
    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    threshold, cooldown_sec = _resolve_commander_cooldown_policy(state)
    now_epoch = _runtime_now_epoch(state)

    incident_count = max(0, _coerce_int(resilience.get("incident_count"), 0))
    cooldown_until = max(0, _coerce_int(resilience.get("cooldown_until_epoch"), 0))

    if cooldown_until > now_epoch:
        state["runtime_status"] = "cooldown_wait"
        state["runtime_transition"] = "cooldown"
        _set_degrade_mode(state, reason="commander_cooldown_active")
        return False, state, {
            "reason": "cooldown_active",
            "incident_count": incident_count,
            "incident_threshold": threshold,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": cooldown_until,
            "now_epoch": now_epoch,
        }

    if threshold > 0 and cooldown_sec > 0 and incident_count >= threshold:
        cooldown_until = now_epoch + cooldown_sec
        resilience["cooldown_until_epoch"] = cooldown_until
        state["resilience"] = resilience
        state["runtime_status"] = "cooldown_wait"
        state["runtime_transition"] = "cooldown"
        _set_degrade_mode(state, reason="incident_threshold_cooldown")
        return False, state, {
            "reason": "incident_threshold_cooldown",
            "incident_count": incident_count,
            "incident_threshold": threshold,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": cooldown_until,
            "now_epoch": now_epoch,
        }

    return True, state, {
        "reason": "cooldown_not_active",
        "incident_count": incident_count,
        "incident_threshold": threshold,
        "cooldown_sec": cooldown_sec,
        "cooldown_until_epoch": cooldown_until,
        "now_epoch": now_epoch,
    }


def _register_commander_incident(state: Dict[str, Any], *, error_type: str) -> Dict[str, Any]:
    """M23-4: increment incident counter and optionally open commander cooldown."""
    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    threshold, cooldown_sec = _resolve_commander_cooldown_policy(state)

    incident_count = max(0, _coerce_int(resilience.get("incident_count"), 0)) + 1
    resilience["incident_count"] = incident_count
    resilience["last_error_type"] = str(error_type or "")

    cooldown_until = max(0, _coerce_int(resilience.get("cooldown_until_epoch"), 0))
    if threshold > 0 and cooldown_sec > 0 and incident_count >= threshold:
        cooldown_until = max(cooldown_until, now_epoch + cooldown_sec)
        resilience["cooldown_until_epoch"] = cooldown_until
        _set_degrade_mode(state, reason="incident_threshold_cooldown")

    state["resilience"] = resilience
    return {
        "incident_count": incident_count,
        "incident_threshold": threshold,
        "cooldown_sec": cooldown_sec,
        "cooldown_until_epoch": cooldown_until,
        "last_error_type": str(error_type or ""),
    }


def _apply_operator_resume_intervention(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """M23-6: explicit operator intervention to resume runtime from cooldown/degrade."""
    transition = _normalize_transition(state.get("runtime_control"))
    if transition != "resume":
        return state, {}

    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    before = {
        "degrade_mode": bool(resilience.get("degrade_mode")),
        "degrade_reason": str(resilience.get("degrade_reason") or ""),
        "incident_count": _coerce_int(resilience.get("incident_count"), 0),
        "cooldown_until_epoch": _coerce_int(resilience.get("cooldown_until_epoch"), 0),
        "last_error_type": str(resilience.get("last_error_type") or ""),
    }
    now_epoch = _runtime_now_epoch(state)

    resilience["degrade_mode"] = False
    resilience["degrade_reason"] = ""
    resilience["incident_count"] = 0
    resilience["cooldown_until_epoch"] = 0
    resilience["last_error_type"] = ""
    state["resilience"] = resilience

    return state, {
        "type": "operator_resume",
        "at_epoch": now_epoch,
        "before": before,
        "after": {
            "degrade_mode": False,
            "degrade_reason": "",
            "incident_count": 0,
            "cooldown_until_epoch": 0,
            "last_error_type": "",
        },
    }


def _apply_runtime_transition(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Apply runtime control transition.

    Supported controls in `state["runtime_control"]`:
      - cancel: stop run immediately
      - pause: stop run immediately
      - retry: increment retry counter and continue run
    """
    transition = _normalize_transition(state.get("runtime_control"))
    if not transition:
        return True, state

    state["runtime_transition"] = transition

    if transition == "cancel":
        state["runtime_status"] = "cancelled"
        return False, state

    if transition == "pause":
        state["runtime_status"] = "paused"
        return False, state

    if transition == "resume":
        state["runtime_status"] = "resuming"
        return True, state

    # retry: mark status and continue the selected runtime path.
    state["runtime_status"] = "retrying"
    state["runtime_retry_count"] = _coerce_int(state.get("runtime_retry_count"), 0) + 1
    return True, state


def _runtime_agent_chain(mode: RuntimeMode, phase: RuntimePhase) -> Tuple[str, ...]:
    if phase == "preopen":
        return ("commander_router", "strategist")
    if phase == "closeout":
        return ("commander_router",)
    if mode == "decision_packet":
        return ("commander_router", "strategist", "supervisor", "executor", "reporter")
    if mode == "integrated_chain":
        return ("commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter")
    return ("commander_router", "strategist", "scanner", "monitor", "supervisor", "executor", "reporter")


def _annotate_runtime_plan(state: Dict[str, Any], selected: RuntimeMode, phase: RuntimePhase) -> Dict[str, Any]:
    state["runtime_plan"] = {
        "mode": selected,
        "phase": phase,
        "agents": list(_runtime_agent_chain(selected, phase)),
    }
    return state


def _import_event_logger():
    for mod in ("libs.event_logger", "libs.logging.event_logger", "libs.core.event_logger"):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _ensure_run_id(state: Dict[str, Any]) -> str:
    _EventLogger, new_run_id = _import_event_logger()
    rid = str(state.get("run_id") or new_run_id())
    state["run_id"] = rid
    return rid


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _log_commander_event(state: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="commander_router", event=event, payload=payload)
    except Exception:
        return


def _portfolio_guard_event_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    pg = state.get("portfolio_guard")
    if not isinstance(pg, dict):
        return {}
    return {
        "portfolio_guard": {
            "applied": bool(pg.get("applied")),
            "approved_total": _coerce_int(pg.get("approved_total"), 0),
            "blocked_total": _coerce_int(pg.get("blocked_total"), 0),
            "blocked_reason_counts": pg.get("blocked_reason_counts")
            if isinstance(pg.get("blocked_reason_counts"), dict)
            else {},
        }
    }


def _portfolio_preflight_event_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    pf = state.get("portfolio_preflight")
    if not isinstance(pf, dict):
        return {}
    return {
        "portfolio_preflight": {
            "applied": bool(pf.get("applied")),
            "blocked": bool(pf.get("blocked")),
            "reason": str(pf.get("reason") or ""),
            "phase": str(pf.get("phase") or ""),
        }
    }


def _extract_portfolio_snapshot_health(state: Dict[str, Any]) -> Dict[str, Any]:
    health = state.get("portfolio_snapshot_health")
    if isinstance(health, dict):
        return dict(health)
    snap = state.get("portfolio_snapshot")
    if isinstance(snap, dict) and isinstance(snap.get("_health"), dict):
        return dict(snap.get("_health") or {})
    return {}


def _portfolio_preflight_block_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    health = _extract_portfolio_snapshot_health(state)
    if not health:
        return {}

    reader_ok = bool(health.get("reader_ok"))
    mismatch = bool(health.get("positions_mismatch_detected"))
    reconciled = bool(health.get("reconciliation_applied"))

    reason = ""
    reason_human = ""
    if not reader_ok:
        reason = "portfolio_snapshot_reader_error"
        reason_human = "계좌 조회가 실패해서 전략 판단 전에 실행을 중단했습니다."
    elif mismatch and not reconciled:
        reason = "portfolio_snapshot_positions_mismatch_unresolved"
        reason_human = "계좌 보유 종목과 로컬 상태 불일치가 남아 있어서 전략 판단 전에 실행을 중단했습니다."
    if not reason:
        return {}

    return {
        "blocked": True,
        "reason": reason,
        "reason_human": reason_human,
        "reader_ok": reader_ok,
        "positions_source": str(health.get("positions_source") or ""),
        "reconciliation_status": str(health.get("reconciliation_status") or ""),
        "reader_positions_authoritative": bool(health.get("reader_positions_authoritative")),
        "positions_mismatch_detected": mismatch,
        "reconciliation_applied": reconciled,
        "reader_positions_count": _coerce_int(health.get("reader_positions_count"), 0),
        "persisted_positions_count": _coerce_int(health.get("persisted_positions_count"), 0),
    }


def _apply_portfolio_preflight_guard(state: Dict[str, Any], *, phase: RuntimePhase) -> Tuple[bool, Dict[str, Any]]:
    payload = _portfolio_preflight_block_payload(state)
    if not payload:
        state["portfolio_preflight"] = {
            "applied": True,
            "blocked": False,
            "phase": phase,
        }
        return True, state

    state["portfolio_preflight"] = {
        "applied": True,
        "blocked": True,
        "phase": phase,
        **payload,
    }
    state["runtime_status"] = "preflight_blocked"
    state["path"] = "portfolio_preflight_guard"
    state["decision"] = "reject"
    state["intents"] = []
    state["selected"] = None
    state["execution"] = {
        "allowed": False,
        "ok": False,
        "reason": payload.get("reason"),
        "order": {"action": "NOOP"},
        "payload": {
            "mode": "preflight_guard",
            "reason_human": payload.get("reason_human"),
        },
    }
    return False, state


def _graph_spine_portfolio_preflight_enabled(state: Dict[str, Any], *, phase: RuntimePhase) -> bool:
    if phase != "session":
        return False
    if _is_trueish(state.get("disable_graph_spine_portfolio_preflight")):
        return False
    if _is_trueish(state.get("enable_graph_spine_portfolio_preflight")):
        return True
    return _is_trueish(os.getenv("COMMANDER_GRAPH_SPINE_PORTFOLIO_PREFLIGHT_ENABLED", ""))


def _run_graph_spine_with_preflight(
    state: Dict[str, Any],
    *,
    graph_runner: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot

    state = build_portfolio_snapshot(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snaps or {}), "portfolio": state.get("portfolio_snapshot")}
    should_continue, state = _apply_portfolio_preflight_guard(state, phase="session")
    if not should_continue:
        return state
    return graph_runner(state)


def _intent_from_monitor_state(state: Dict[str, Any]) -> Dict[str, Any]:
    intents = state.get("intents")
    if not isinstance(intents, list) or not intents:
        return {"action": "NOOP", "reason": "no_monitor_intent"}

    it0 = intents[0] if isinstance(intents[0], dict) else {}
    side = str(it0.get("side") or "BUY").strip().upper()
    action = "BUY" if side == "BUY" else "SELL" if side == "SELL" else "NOOP"
    symbol = str(it0.get("symbol") or state.get("symbol") or state.get("selected_symbol") or "").strip().upper()
    qty = max(0, _coerce_int(it0.get("qty"), 0))

    market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    price = it0.get("price")
    if price is None:
        price = market.get("price")

    return {
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "order_type": "limit",
        "order_api_id": "ORDER_SUBMIT",
        "rationale": str(it0.get("thesis") or "monitor_intent"),
    }


def _build_packet_from_state(state: Dict[str, Any], *, intent: Dict[str, Any]) -> Dict[str, Any]:
    risk = state.get("risk_context") if isinstance(state.get("risk_context"), dict) else {}
    exec_context = state.get("exec_context") if isinstance(state.get("exec_context"), dict) else {}
    return {
        "intent": dict(intent),
        "risk": dict(risk),
        "exec_context": dict(exec_context),
    }


def _normalize_strategist_output_contract(output: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(output or {})
    strategy_policy = normalized.get("strategy_policy") if isinstance(normalized.get("strategy_policy"), dict) else {}
    if not strategy_policy:
        return normalized

    strategy_policy = dict(strategy_policy)
    decision_policy = strategy_policy.get("decision_policy") if isinstance(strategy_policy.get("decision_policy"), dict) else {}
    decision_policy = dict(decision_policy or {})
    decision_policy["use_strategy_v1_engine"] = False
    decision_policy["allow_score_override"] = False
    decision_policy["score_override_scope"] = "disabled"
    decision_policy["strategy_v1_name"] = ""
    decision_policy["strategy_variant_hint"] = "unified_ai_strategist"
    for key in (
        "buy_threshold",
        "sell_threshold",
        "high_vol_abs_threshold",
        "news_buy_threshold",
        "news_sell_threshold",
    ):
        decision_policy.pop(key, None)
    strategy_policy["decision_policy"] = decision_policy
    normalized["strategy_policy"] = strategy_policy
    return normalized


def _persist_strategist_output_cache(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    if not strategist_output:
        return state
    if bool(state.get("strategist_blocked")) or bool(strategist_output.get("llm_frame_blocked")):
        return state
    strategist_output = _normalize_strategist_output_contract(strategist_output)
    state["strategist_output"] = dict(strategist_output)
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    persisted_state["strategist_output_cache"] = {
        "output": dict(strategist_output),
        "generated_epoch": int(_runtime_now_epoch(state)),
        "source": "strategist_node",
    }
    state["persisted_state"] = persisted_state
    return state


def _strategist_frame_blocked(state: Dict[str, Any]) -> bool:
    if bool(state.get("strategist_blocked")):
        return True
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategist_llm = state.get("strategist_llm") if isinstance(state.get("strategist_llm"), dict) else {}
    return bool(strategist_output.get("llm_frame_blocked")) or bool(strategist_llm.get("blocked"))


def _apply_strategist_block(state: Dict[str, Any], *, phase: str) -> Dict[str, Any]:
    reason = str(
        state.get("strategist_blocked_reason")
        or ((state.get("strategist_output") or {}).get("llm_frame_blocked_reason") if isinstance(state.get("strategist_output"), dict) else "")
        or ((state.get("strategist_llm") or {}).get("blocked_reason") if isinstance(state.get("strategist_llm"), dict) else "")
        or "strategist_llm_failed"
    )
    payload = {"path": "strategist_llm_blocked", "phase": phase, "reason": reason}
    _log_commander_event(state, "fast_path", payload)
    state["runtime_status"] = "blocked"
    state["path"] = f"{phase}_strategist_blocked"
    state["decision"] = "noop"
    state["decision_reason"] = reason
    return state


def _hydrate_strategist_output_cache(state: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(state.get("strategist_output"), dict) and state.get("strategist_output"):
        return state
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = persisted_state.get("strategist_output_cache") if isinstance(persisted_state.get("strategist_output_cache"), dict) else {}
    cached = raw_cached.get("output") if isinstance(raw_cached.get("output"), dict) else raw_cached
    if isinstance(cached, dict) and cached:
        state["strategist_output"] = _normalize_strategist_output_contract(cached)
        if isinstance(raw_cached, dict) and raw_cached:
            state["strategist_output_cache_meta"] = dict(raw_cached)
        return state

    held_symbols = _portfolio_open_position_symbols(state)
    position_context = (
        persisted_state.get("position_strategy_context")
        if isinstance(persisted_state.get("position_strategy_context"), dict)
        else {}
    )
    for symbol in held_symbols:
        row = position_context.get(symbol) if isinstance(position_context.get(symbol), dict) else {}
        output = row.get("output") if isinstance(row.get("output"), dict) else {}
        if output:
            state["strategist_output"] = _normalize_strategist_output_contract(output)
            state["strategist_output_cache_meta"] = {
                "output": dict(state["strategist_output"]),
                "generated_epoch": _coerce_int(row.get("generated_epoch"), 0),
                "source": str(row.get("source") or "position_strategy_context"),
                "symbol": symbol,
            }
    return state


def _portfolio_open_position_count(state: Dict[str, Any]) -> int:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _coerce_int(row.get("qty"), 0) > 0:
            count += 1
    return int(count)


def _portfolio_open_position_symbols(state: Dict[str, Any]) -> list[str]:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []
    seen: set[str] = set()
    symbols: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _coerce_int(row.get("qty"), 0) <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _hydrate_monitor_symbol_features(state: Dict[str, Any]) -> Dict[str, Any]:
    held_symbols = _portfolio_open_position_symbols(state)
    if not held_symbols:
        state["monitor_feature_hydration"] = {
            "applied": False,
            "symbol_count": 0,
            "source": "none",
            "errors": [],
        }
        return state

    from graphs.nodes.skill_contracts import extract_market_quotes
    from libs.runtime.scanner_feature_hydration import hydrate_scanner_feature_map

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    skill_quotes, _quote_meta = extract_market_quotes(state)
    feature_map, feature_source, feature_errors = hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": symbol} for symbol in held_symbols],
        skill_quotes=skill_quotes,
        policy=policy,
        refresh_existing=True,
    )
    state["monitor_feature_hydration"] = {
        "applied": True,
        "symbol_count": int(len(held_symbols)),
        "source": str(feature_source or "none"),
        "feature_symbol_count": int(len(feature_map)),
        "errors": list(feature_errors),
        "symbols": list(held_symbols),
    }
    return state


def _should_use_monitor_only_fast_path(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    enabled = _is_trueish(
        state.get("enable_monitor_only_fast_path")
        if state.get("enable_monitor_only_fast_path") is not None
        else os.getenv("COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED", "true")
    )
    open_position_count = _portfolio_open_position_count(state)
    block_buy_when_open_position = _is_trueish(
        state.get("monitor_block_buy_when_open_position")
        if state.get("monitor_block_buy_when_open_position") is not None
        else os.getenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    )
    payload = {
        "enabled": bool(enabled),
        "open_position_count": int(open_position_count),
        "block_buy_when_open_position": bool(block_buy_when_open_position),
        "reason": "",
    }
    if not enabled:
        payload["reason"] = "disabled"
        return False, payload
    if open_position_count <= 0:
        payload["reason"] = "no_open_position"
        return False, payload
    if not block_buy_when_open_position:
        payload["reason"] = "buy_not_blocked_when_open_position"
        return False, payload
    payload["reason"] = "holding_position_monitor_only"
    return True, payload


def _strategist_cache_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = persisted_state.get("strategist_output_cache") if isinstance(persisted_state.get("strategist_output_cache"), dict) else {}
    if isinstance(raw_cached.get("output"), dict):
        return dict(raw_cached)
    if raw_cached:
        return {"output": dict(raw_cached), "generated_epoch": 0, "source": "legacy_cache"}
    return {}


def _should_use_cached_strategist_when_flat(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    enabled = _is_trueish(
        state.get("enable_cached_strategist_when_flat")
        if state.get("enable_cached_strategist_when_flat") is not None
        else os.getenv("COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED", "false")
    )
    open_position_count = _portfolio_open_position_count(state)
    cache_payload = _strategist_cache_payload(state)
    output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    generated_epoch = max(0, _coerce_int(cache_payload.get("generated_epoch"), 0))
    reuse_sec = max(0, _coerce_int(os.getenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "180"), 180))
    age_sec = max(0, now_epoch - generated_epoch) if generated_epoch > 0 else 10**9
    payload = {
        "enabled": bool(enabled),
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "reason": "",
    }
    if not enabled:
        payload["reason"] = "disabled"
        return False, payload
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return False, payload
    if _is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return False, payload
    if not output:
        payload["reason"] = "no_cached_strategist_output"
        return False, payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return False, payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return False, payload
    payload["reason"] = "flat_position_cached_strategist"
    return True, payload


def _run_integrated_chain(
    state: Dict[str, Any],
    *,
    execute_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a visible end-to-end chain inside canonical runtime."""
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
    from graphs.nodes.build_risk_context import build_risk_context
    from graphs.nodes.strategist_node import strategist_node
    from graphs.nodes.scanner_node import scanner_node
    from graphs.nodes.monitor_node import monitor_node
    from graphs.nodes.decision_node import decision_node
    from graphs.nodes.update_state_after_execution import update_state_after_execution
    from libs.reporting.intraday_trade_reports import generate_intraday_trade_artifacts

    # Keep integrated chain position/risk context aligned with live state.
    state = build_portfolio_snapshot(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snaps or {}), "portfolio": state.get("portfolio_snapshot")}
    should_continue, state = _apply_portfolio_preflight_guard(state, phase="session")
    if not should_continue:
        return state
    state = build_risk_context(state)

    use_monitor_only, fast_path_payload = _should_use_monitor_only_fast_path(state)
    if use_monitor_only:
        state = _hydrate_strategist_output_cache(state)
        held_symbols = _portfolio_open_position_symbols(state)
        if held_symbols:
            state["selected"] = {
                "symbol": held_symbols[0],
                "_monitor_synthetic_selected": True,
            }
        else:
            state.pop("selected", None)
        state.pop("scanner_output", None)
        state["runtime_fast_path"] = dict(fast_path_payload)
        _log_commander_event(state, "fast_path", {"path": "integrated_chain_monitor_only", **fast_path_payload})
        state = _hydrate_monitor_symbol_features(state)
        state = monitor_node(state)
        state = decision_node(state)
        decision = str(state.get("decision") or "").strip().lower()
        if decision == "approve":
            intent = _intent_from_monitor_state(state)
            state["decision_packet"] = _build_packet_from_state(state, intent=intent)
            state = execute_fn(state)
            state = update_state_after_execution(state)
            try:
                state["intraday_trade_report"] = generate_intraday_trade_artifacts(state)
            except Exception as exc:
                state["intraday_trade_report"] = {
                    "ok": False,
                    "status": "failed",
                    "reason": f"intraday_trade_artifact_exception:{type(exc).__name__}",
                }
        state["path"] = "integrated_chain_monitor_only"
        return state

    reused_strategist_cache, cache_payload = _should_use_cached_strategist_when_flat(state)
    if reused_strategist_cache:
        state = _hydrate_strategist_output_cache(state)
        state["runtime_fast_path"] = dict(cache_payload)
        _log_commander_event(state, "fast_path", {"path": "integrated_chain_cached_frame", **cache_payload})
    else:
        state = strategist_node(state)
        if _strategist_frame_blocked(state):
            return _apply_strategist_block(state, phase="integrated_chain")
        state = _persist_strategist_output_cache(state)
    state = scanner_node(state)
    state = _hydrate_monitor_symbol_features(state)
    state = monitor_node(state)
    state = decision_node(state)

    decision = str(state.get("decision") or "").strip().lower()
    if decision == "approve":
        intent = _intent_from_monitor_state(state)
        state["decision_packet"] = _build_packet_from_state(state, intent=intent)
        state = execute_fn(state)
        state = update_state_after_execution(state)
        try:
            state["intraday_trade_report"] = generate_intraday_trade_artifacts(state)
        except Exception as exc:
            state["intraday_trade_report"] = {
                "ok": False,
                "status": "failed",
                "reason": f"intraday_trade_artifact_exception:{type(exc).__name__}",
            }

    state["path"] = "integrated_chain_cached_frame" if reused_strategist_cache else "integrated_chain"
    return state


def _run_preopen_phase(state: Dict[str, Any]) -> Dict[str, Any]:
    """Warm strategist context before session without entering selection/execution paths."""
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
    from graphs.nodes.build_risk_context import build_risk_context
    from graphs.nodes.strategist_node import strategist_node

    state = build_portfolio_snapshot(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snaps or {}), "portfolio": state.get("portfolio_snapshot")}
    should_continue, state = _apply_portfolio_preflight_guard(state, phase="preopen")
    if not should_continue:
        return state
    state = build_risk_context(state)
    state = strategist_node(state)
    if _strategist_frame_blocked(state):
        return _apply_strategist_block(state, phase="preopen")
    state = _persist_strategist_output_cache(state)
    state["path"] = "preopen_strategist"
    state["runtime_status"] = str(state.get("runtime_status") or "preopen_ready")
    return state


def _run_closeout_phase(state: Dict[str, Any]) -> Dict[str, Any]:
    """Keep commander passive during closeout; reporting remains script-driven."""
    state["path"] = "closeout_idle"
    state["runtime_status"] = str(state.get("runtime_status") or "closeout_ready")
    return state


def resolve_runtime_mode(state: Dict[str, Any], *, mode: Optional[RuntimeMode] = None) -> RuntimeMode:
    """Resolve runtime mode with explicit precedence.

    Priority:
      1) explicit argument `mode`
      2) `state["runtime_mode"]`
      3) env `COMMANDER_RUNTIME_MODE`
      4) default `graph_spine`

    Safety guard:
      - decision_packet via state/env requires activation:
        state["allow_decision_packet_runtime"]=true OR
        env COMMANDER_RUNTIME_ALLOW_DECISION_PACKET=true
      - explicit `mode` bypasses this guard (caller-controlled override).
    """
    if mode is not None:
        return _normalize_mode(mode)

    allow_decision_packet = _is_trueish(state.get("allow_decision_packet_runtime")) or _is_trueish(
        os.getenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", "")
    )

    if "runtime_mode" in state:
        selected = _normalize_mode(state.get("runtime_mode"))
        if selected == "decision_packet" and not allow_decision_packet:
            return "graph_spine"
        return selected
    env_mode = os.getenv("COMMANDER_RUNTIME_MODE", "")
    selected = _normalize_mode(env_mode or "graph_spine")
    if selected == "decision_packet" and not allow_decision_packet:
        return "graph_spine"
    return selected


def resolve_runtime_phase(state: Dict[str, Any], *, phase: Optional[RuntimePhase] = None) -> RuntimePhase:
    """Resolve runtime phase with explicit precedence."""
    if phase is not None:
        return _normalize_phase(phase)
    if "runtime_phase" in state:
        return _normalize_phase(state.get("runtime_phase"))
    return _normalize_phase(os.getenv("COMMANDER_RUNTIME_PHASE", "session"))


def run_commander_runtime(
    state: Dict[str, Any],
    *,
    mode: Optional[RuntimeMode] = None,
    phase: Optional[RuntimePhase] = None,
    graph_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    integrated_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    preopen_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    closeout_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    decide: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    execute: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one canonical commander runtime step.

    Mode selection uses `resolve_runtime_mode(...)`.
    """
    state = ensure_runtime_resilience_state(state)

    def _build_commander_decision_frame(
        mode_value: str,
        phase_value: str,
        *,
        status_value: str,
        path_value: str,
        reason_text: str = "",
    ) -> Dict[str, Any]:
        runtime_plan = state.get("runtime_plan") if isinstance(state.get("runtime_plan"), dict) else {}
        portfolio_snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
        strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
        return {
            "session_type": str(phase_value or ""),
            "market_clock_phase": str(phase_value or ""),
            "portfolio_state_summary": {
                "position_count": len(list(portfolio_snapshot.get("positions") or [])),
                "cash": portfolio_snapshot.get("cash"),
                "positions_source": str((state.get("portfolio_preflight") or {}).get("positions_source") if isinstance(state.get("portfolio_preflight"), dict) else ""),
                "preflight_status": str((state.get("portfolio_preflight") or {}).get("status") if isinstance(state.get("portfolio_preflight"), dict) else ""),
            },
            "market_regime_summary": {
                "market_regime": str(strategist_output.get("market_regime") or ""),
                "market_sentiment": str(strategist_output.get("market_sentiment") or ""),
                "playbook": str(strategist_output.get("playbook") or ""),
            },
            "goal": (
                "Execute full trading session flow."
                if str(phase_value or "").strip() == "session"
                else f"Run {str(phase_value or '').strip() or 'runtime'} phase safely."
            ),
            "agent_invocation_plan": list(runtime_plan.get("agents") or []),
            "decision_checkpoints": {
                "runtime_transition": str(state.get("runtime_transition") or ""),
                "runtime_status": str(status_value or state.get("runtime_status") or ""),
                "portfolio_preflight_status": str((state.get("portfolio_preflight") or {}).get("status") if isinstance(state.get("portfolio_preflight"), dict) else ""),
                "runtime_fast_path": dict(state.get("runtime_fast_path") or {}) if isinstance(state.get("runtime_fast_path"), dict) else {},
            },
            "final_runtime_path": str(path_value or ""),
            "final_reason": str(reason_text or state.get("runtime_status") or ""),
            "handoff_instruction": (
                "Proceed to downstream agents according to runtime plan."
                if str(status_value or "").strip().lower() in {"ok", "ready", "preopen_ready", "closeout_ready"}
                else "Do not proceed. Inspect commander/runtime status first."
            ),
            "mode": str(mode_value or ""),
        }

    def _persist_commander(mode_value: str, phase_value: str, *, status_value: str, path_value: str, reason: str = "") -> None:
        try:
            state["commander_decision_frame"] = _build_commander_decision_frame(
                mode_value,
                phase_value,
                status_value=status_value,
                path_value=path_value,
                reason_text=reason,
            )
            write_commander_artifact(
                state,
                mode=str(mode_value or ""),
                phase=str(phase_value or ""),
                path=str(path_value or ""),
                status=str(status_value or "ok"),
                reason=str(reason or ""),
            )
        except Exception:
            pass
    selected = resolve_runtime_mode(state, mode=mode)
    selected_phase = resolve_runtime_phase(state, phase=phase)
    state["runtime_phase"] = selected_phase
    state = _annotate_runtime_plan(state, selected, selected_phase)
    _log_commander_event(
        state,
        "route",
        {
            "mode": selected,
            "phase": selected_phase,
            "agents": list(state.get("runtime_plan", {}).get("agents", [])),
        },
    )

    should_run, state = _apply_runtime_transition(state)
    if state.get("runtime_transition"):
        _log_commander_event(
            state,
            "transition",
            {
                "transition": state.get("runtime_transition"),
                "status": state.get("runtime_status"),
                "retry_count": state.get("runtime_retry_count"),
            },
        )
    if not should_run:
        _log_commander_event(
            state,
            "end",
            {"mode": selected, "status": state.get("runtime_status", "stopped"), "path": None},
        )
        _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "stopped") or "stopped"), path_value="")
        return state

    state, intervention_payload = _apply_operator_resume_intervention(state)
    if intervention_payload:
        _log_commander_event(state, "intervention", intervention_payload)

    should_run, state, cooldown_payload = _apply_commander_cooldown_guard(state)
    if not should_run:
        _log_commander_event(
            state,
            "transition",
            {
                "transition": state.get("runtime_transition"),
                "status": state.get("runtime_status"),
                "reason": cooldown_payload.get("reason"),
                "cooldown_until_epoch": cooldown_payload.get("cooldown_until_epoch"),
                "incident_count": cooldown_payload.get("incident_count"),
                "incident_threshold": cooldown_payload.get("incident_threshold"),
            },
        )
        _log_commander_event(state, "resilience", cooldown_payload)
        _log_commander_event(
            state,
            "end",
            {"mode": selected, "status": state.get("runtime_status", "stopped"), "path": None},
        )
        return state

    graph_runner = graph_runner or run_trading_graph
    decide = decide or decide_trade
    execute = execute or execute_from_packet
    integrated_runner = integrated_runner or (lambda s: _run_integrated_chain(s, execute_fn=execute))
    preopen_runner = preopen_runner or _run_preopen_phase
    closeout_runner = closeout_runner or _run_closeout_phase

    try:
        if selected_phase == "preopen":
            state = preopen_runner(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "preopen_ready"),
                    "path": state.get("path", "preopen_strategist"),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "preopen_ready") or "preopen_ready"), path_value=str(state.get("path", "preopen_strategist") or "preopen_strategist"))
            return state

        if selected_phase == "closeout":
            state = closeout_runner(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "closeout_ready"),
                    "path": state.get("path", "closeout_idle"),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "closeout_ready") or "closeout_ready"), path_value=str(state.get("path", "closeout_idle") or "closeout_idle"))
            return state

        if selected == "decision_packet":
            state = decide(state)
            state = execute(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "ok"),
                    "path": "decision_packet",
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "ok") or "ok"), path_value="decision_packet")
            return state

        if selected == "integrated_chain":
            state = integrated_runner(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "ok"),
                    "path": state.get("path", "integrated_chain"),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "ok") or "ok"), path_value=str(state.get("path", "integrated_chain") or "integrated_chain"))
            return state

        if _graph_spine_portfolio_preflight_enabled(state, phase=selected_phase):
            state = _run_graph_spine_with_preflight(state, graph_runner=graph_runner)
        else:
            state = graph_runner(state)
        _log_commander_event(
            state,
            "end",
            {
                "mode": selected,
                "phase": selected_phase,
                "status": state.get("runtime_status", "ok"),
                "path": state.get("path", "graph_spine"),
                **_portfolio_guard_event_summary(state),
                **_portfolio_preflight_event_summary(state),
            },
        )
        _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "ok") or "ok"), path_value=str(state.get("path", "graph_spine") or "graph_spine"))
        return state
    except Exception as e:
        incident_payload = _register_commander_incident(state, error_type=type(e).__name__)
        state["runtime_status"] = "error"
        _log_commander_event(
            state,
            "error",
            {
                "mode": selected,
                "phase": selected_phase,
                "error_type": type(e).__name__,
                "error": str(e),
                **incident_payload,
            },
        )
        _persist_commander(selected, selected_phase, status_value="error", path_value=str(state.get("path") or ""), reason=str(e))
        raise
