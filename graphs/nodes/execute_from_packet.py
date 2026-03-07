from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple


def _import_api_catalog():
    from libs.catalog.api_catalog import ApiCatalog  # type: ignore
    return ApiCatalog


def _import_request_builder():
    from libs.catalog.api_request_builder import ApiRequestBuilder  # type: ignore
    return ApiRequestBuilder


def _import_settings():
    from libs.core.settings import Settings  # type: ignore
    return Settings


def _import_event_logger():
    """Try multiple locations for EventLogger/new_run_id."""
    for mod in (
        "libs.event_logger",
        "libs.logging.event_logger",
        "libs.core.event_logger",
    ):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    # final fallback: local minimal logger
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _import_supervisor():
    from libs.risk.supervisor import Supervisor  # type: ignore
    return Supervisor


def _import_get_executor():
    # returns get_executor() factory
    try:
        from libs.execution.executors import get_executor  # type: ignore
        return get_executor
    except Exception:
        from libs.execution.executors.factory import get_executor  # type: ignore
        return get_executor


def _catalog_path_from_env() -> str:
    # New canonical key
    p = os.getenv("KIWOOM_API_CATALOG_PATH")
    if p:
        return p
    # Legacy keys (kept for backwards compatibility)
    for k in ("KIWOOM_REGISTRY_APIS_JSONL", "KIWOOM_REGISTRY_TAGGED_JSONL"):
        v = os.getenv(k)
        if v:
            return v
    return "./data/specs/api_catalog.jsonl"


def _resolve_execution_mode() -> str:
    """Resolve effective execution mode consistently with executor factory."""
    mode = (os.getenv("EXECUTION_MODE", "") or "").strip().lower()
    if mode in ("mock", "real"):
        return mode

    try:
        Settings = _import_settings()
        s = Settings.from_env()
        base = str(getattr(s, "kiwoom_mode", "mock") or "mock").strip().lower()
        return "real" if base == "real" else "mock"
    except Exception:
        return "mock"


def _is_kiwoom_mock_mode() -> bool:
    return str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"


def _is_kiwoom_mock_broker_http_mode() -> bool:
    # Kiwoom mock REST path: KIWOOM_MODE=mock with EXECUTION_MODE=real.
    return _is_kiwoom_mock_mode() and _resolve_execution_mode() == "real"


def _is_trueish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_symbol_allowlist(raw: Optional[str]) -> set[str]:
    if raw is None:
        return set()
    v = raw.strip()
    if not v:
        return set()
    return {x.strip() for x in v.split(",") if x.strip()}


def _extract_order_symbol(order: Dict[str, Any]) -> str:
    sym = order.get("symbol") or order.get("stk_cd")
    if sym is None:
        return ""
    return str(sym).strip()


def _extract_open_symbols_from_state(state: Dict[str, Any]) -> set[str]:
    symbols: set[str] = set()

    port = state.get("portfolio_snapshot")
    if isinstance(port, dict):
        rows = port.get("positions")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or "").strip()
                qty = _coerce_int(row.get("qty"), 0)
                if sym and qty > 0:
                    symbols.add(sym)

    persisted = state.get("persisted_state")
    if isinstance(persisted, dict):
        rows = persisted.get("mock_positions")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or "").strip()
                qty = _coerce_int(row.get("qty"), 0)
                if sym and qty > 0:
                    symbols.add(sym)
    return symbols


def _should_block_duplicate_mock_buy(state: Dict[str, Any], order: Dict[str, Any]) -> bool:
    if _resolve_execution_mode() != "mock":
        return False
    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return False
    sym = _extract_order_symbol(order)
    if not sym:
        return False
    return sym in _extract_open_symbols_from_state(state)


def _resolve_mock_cash_available(state: Dict[str, Any]) -> float:
    persisted = state.get("persisted_state")
    if isinstance(persisted, dict):
        cash = _coerce_float(persisted.get("mock_cash"), 0.0)
        if cash > 0.0:
            return cash

    port = state.get("portfolio_snapshot")
    if isinstance(port, dict):
        cash = _coerce_float(port.get("cash"), 0.0)
        if cash > 0.0:
            return cash

    return _coerce_float(os.getenv("MOCK_CASH_FALLBACK"), 0.0)


def _resolve_order_price_for_notional(state: Dict[str, Any], order: Dict[str, Any]) -> float:
    px = _coerce_float(order.get("price"), 0.0)
    if px > 0.0:
        return px

    market = state.get("market_snapshot")
    if isinstance(market, dict):
        px = _coerce_float(market.get("price"), 0.0)
        if px > 0.0:
            return px
    return 0.0


def _evaluate_mock_cash_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    if _resolve_execution_mode() != "mock":
        return True, "", {}

    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return True, "", {}

    qty = _coerce_int(order.get("qty"), 0)
    if qty <= 0:
        return True, "", {"qty_evaluable": False}

    price = _resolve_order_price_for_notional(state, order)
    if price <= 0.0:
        # Cannot evaluate notional without price; keep existing behavior.
        return True, "", {"price_evaluable": False}

    cash = _resolve_mock_cash_available(state)
    if cash <= 0.0:
        return True, "", {"cash_evaluable": False}

    notional = float(qty) * float(price)
    details = {
        "cash": float(cash),
        "price": float(price),
        "qty": int(qty),
        "notional": float(notional),
    }
    if notional > cash:
        return False, "insufficient_mock_cash", details
    return True, "", details


def _extract_portfolio_snapshot_health(state: Dict[str, Any]) -> Dict[str, Any]:
    snap = state.get("portfolio_snapshot")
    if isinstance(snap, dict):
        h = snap.get("_health")
        if isinstance(h, dict):
            return dict(h)
    h2 = state.get("portfolio_snapshot_health")
    if isinstance(h2, dict):
        return dict(h2)
    return {}


def _evaluate_portfolio_snapshot_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    # Guard only in real execution path; mock/offline flow remains unchanged.
    if _resolve_execution_mode() != "real":
        return True, "", {"enabled": False, "reason": "execution_mode_not_real"}

    if not _is_trueish(os.getenv("PORTFOLIO_SNAPSHOT_HEALTH_GUARD_ENABLED", "true")):
        return True, "", {"enabled": False, "reason": "guard_disabled"}

    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return True, "", {"enabled": True, "action": action, "guard_applied": False}

    health = _extract_portfolio_snapshot_health(state)
    if not health:
        return True, "", {"enabled": True, "health_present": False, "guard_applied": True}

    reader_ok = _is_trueish(health.get("reader_ok"))
    details: Dict[str, Any] = {
        "enabled": True,
        "health_present": True,
        "reader_ok": bool(reader_ok),
        "source": str(health.get("source") or ""),
        "reader_error": str(health.get("reader_error") or ""),
        "guard_applied": True,
    }
    if reader_ok:
        return True, "", details
    return False, "portfolio_snapshot_reader_error", details


def _is_degrade_mode(state: Dict[str, Any]) -> bool:
    resilience = state.get("resilience")
    if not isinstance(resilience, dict):
        return False
    return _is_trueish(resilience.get("degrade_mode"))


def _is_manual_approved(state: Dict[str, Any], exec_context: Dict[str, Any]) -> bool:
    if _is_trueish(state.get("execution_manual_approved")):
        return True
    if _is_trueish(state.get("manual_approved")):
        return True
    if _is_trueish(exec_context.get("manual_approved")):
        return True
    approval_status = str(exec_context.get("approval_status") or "").strip().lower()
    return approval_status in ("approved", "manual_approved")


def _degrade_notional_ratio(state: Dict[str, Any]) -> float:
    policy = state.get("resilience_policy") if isinstance(state.get("resilience_policy"), dict) else {}
    ratio = _coerce_float(policy.get("degrade_notional_ratio"), _coerce_float(os.getenv("DEGRADE_NOTIONAL_RATIO"), 0.25))
    if ratio <= 0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


def _evaluate_degrade_execution_policy(
    *,
    state: Dict[str, Any],
    order: Dict[str, Any],
    exec_context: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    if not _is_degrade_mode(state):
        return True, "", {"degrade_mode": False}

    details: Dict[str, Any] = {"degrade_mode": True}

    # M23-5 policy: degrade mode disables effective auto-approval.
    if not _is_manual_approved(state, exec_context):
        details["required"] = "manual_approval"
        return False, "degrade_manual_approval_required", details

    # M23-5 policy: degrade mode requires non-empty allowlist.
    allow = _parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST"))
    details["allowlist_size"] = len(allow)
    if not allow:
        return False, "degrade_allowlist_required", details

    sym = _extract_order_symbol(order)
    if sym and sym not in allow:
        details["symbol"] = sym
        return False, "degrade_symbol_not_allowlisted", details

    max_notional = _coerce_int(os.getenv("MAX_ORDER_NOTIONAL"), 0)
    ratio = _degrade_notional_ratio(state)
    details["degrade_notional_ratio"] = ratio
    details["max_order_notional"] = max_notional
    if max_notional <= 0 or ratio <= 0:
        return True, "", details

    effective_limit = max(1, int(max_notional * ratio))
    details["effective_max_notional"] = effective_limit

    qty = _coerce_int(order.get("qty"), 0)
    if qty <= 0:
        return True, "", details

    px_raw = order.get("price")
    if px_raw is None:
        return True, "", details
    try:
        px = int(px_raw)
    except Exception:
        details["invalid_price"] = str(px_raw)
        return False, "degrade_invalid_price_for_notional_guard", details

    notional = qty * px
    details["order_notional"] = notional
    if notional > effective_limit:
        return False, "degrade_notional_limit_exceeded", details

    return True, "", details


def _build_order_from_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort order dict. This is intentionally thin.

    Real request shaping should be done via ApiRequestBuilder + ApiSpec.
    """
    # Allow multiple intent schemas during transition
    action = intent.get("action") or intent.get("intent") or intent.get("type") or "NOOP"
    action = str(action).upper()
    api_id = intent.get("order_api_id") or intent.get("api_id") or "ORDER_SUBMIT"
    order_type = intent.get("order_type") or intent.get("type") or "limit"
    order_type = str(order_type or "limit").strip().lower()

    qty = intent.get("qty") or intent.get("quantity")
    price = intent.get("price")
    symbol = intent.get("symbol")

    qty_int = None
    if qty is not None:
        try:
            qty_int = int(float(qty))
        except Exception:
            qty_int = None

    price_int = None
    if price is not None:
        try:
            price_int = int(float(price))
        except Exception:
            price_int = None

    order: Dict[str, Any] = {
        "api_id": api_id,
        "action": action,
        "symbol": symbol,
        "qty": qty_int if qty_int is not None else qty,
        "price": price_int if price_int is not None else price,
        "order_type": order_type,
        "tif": intent.get("tif") or intent.get("time_in_force"),
        "rationale": intent.get("rationale") or intent.get("reason") or "",
    }

    # Add Kiwoom order-body aliases used by kt10000/kt10001 specs.
    if action in ("BUY", "SELL"):
        trde_tp = intent.get("trde_tp")
        if trde_tp is None or not str(trde_tp).strip():
            trde_tp = "3" if order_type == "market" else "0"
        ord_qty = "" if qty_int is None else str(max(0, int(qty_int)))
        ord_uv = ""
        if order_type != "market" and price_int is not None:
            ord_uv = str(max(0, int(price_int)))
        order["dmst_stex_tp"] = intent.get("dmst_stex_tp") or intent.get("market") or "KRX"
        order["stk_cd"] = symbol
        order["ord_qty"] = ord_qty
        order["ord_uv"] = ord_uv
        order["trde_tp"] = str(trde_tp)
        order["cond_uv"] = intent.get("cond_uv") or ""

    # Pass through any extra keys (so request builder can pick them up)
    for k, v in intent.items():
        if k not in order:
            order[k] = v
    return order


def _apply_mock_broker_order_safety(order: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize broker-facing order for Kiwoom mock REST compatibility.

    In mock broker HTTP mode, market orders are safer/reproducible than limit
    for LLM-generated intents. We coerce BUY/SELL orders to market semantics.
    """
    if not _is_kiwoom_mock_broker_http_mode():
        return order

    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL"):
        return order

    cur_type = str(order.get("order_type") or "limit").strip().lower()
    if cur_type == "market":
        return order

    order["order_type"] = "market"
    # Kiwoom body aliases
    order["trde_tp"] = "3"
    order["ord_uv"] = ""

    rationale = str(order.get("rationale") or "").strip()
    tag = "mock_broker_force_market"
    if not rationale:
        order["rationale"] = tag
    elif tag not in rationale:
        order["rationale"] = f"{rationale};{tag}"
    return order


def _broker_code_success(value: Any) -> Optional[bool]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s)) == 0
    except Exception:
        pass
    t = s.lower()
    if t in ("ok", "success", "accepted"):
        return True
    if t in ("error", "failed", "rejected"):
        return False
    return False


def _infer_execution_ok(payload: Dict[str, Any]) -> Tuple[bool, str]:
    broker = _broker_code_success(payload.get("broker_code"))
    if broker is not None:
        return bool(broker), "broker_code"

    if "api_ok" in payload:
        return bool(payload.get("api_ok")), "api_ok"

    status_code = payload.get("status_code")
    try:
        code = int(float(status_code))
        return (200 <= code < 300), "status_code"
    except Exception:
        pass

    if str(payload.get("mode") or "").strip().lower() == "mock":
        return True, "mode_mock_default"

    # Backward-compatible default when no execution signal exists.
    return True, "default_true"


def _supervisor_allow(supervisor: Any, order: Dict[str, Any], risk: Dict[str, Any]) -> Any:
    """Supervisor API changed during refactors.

    Current Supervisor.allow signature in libs/risk/supervisor.py:
      allow(intent: str, context: Dict[str,Any]) -> AllowResult
    """
    action = order.get("action") or order.get("intent") or "NOOP"
    action = str(action).lower().strip()
    ctx = dict(risk); ctx["order"] = order
    try:
        return supervisor.allow(action, ctx)
    except TypeError:
        # legacy keyword versions
        try:
            return supervisor.allow(intent=action, context=ctx)
        except TypeError:
            return supervisor.allow(action, ctx)


def _prepare_request(order: Dict[str, Any], catalog: Any) -> Any:
    """Build a PreparedRequest-like object for executors.

    - If api_id exists and catalog can load an ApiSpec, use ApiRequestBuilder.
    - Otherwise fall back to a SimpleNamespace with required attrs.
    """
    api_id_raw = str(order.get("api_id") or order.get("order_api_id") or "").strip()
    action = str(order.get("action") or "").strip().upper()
    api_candidates = []
    if api_id_raw:
        api_candidates.append(api_id_raw)

    # Resolve canonical order alias only when target API exists in current catalog.
    if api_id_raw.upper() == "ORDER_SUBMIT":
        alias = ""
        if action == "BUY":
            alias = "kt10000"
        elif action == "SELL":
            alias = "kt10001"
        if alias:
            try:
                spec_alias = None
                for meth in ("get", "get_api", "lookup"):
                    if hasattr(catalog, meth):
                        try:
                            spec_alias = getattr(catalog, meth)(alias)
                        except Exception:
                            spec_alias = None
                        break
                if spec_alias is not None and alias not in api_candidates:
                    api_candidates.append(alias)
            except Exception:
                pass

    for api_id in api_candidates:
        # Build from spec + context (preferred)
        try:
            spec = None
            for meth in ("get", "get_api", "lookup"):
                if hasattr(catalog, meth):
                    try:
                        spec = getattr(catalog, meth)(api_id)
                    except Exception:
                        spec = None
                    break

            if spec is not None:
                ApiRequestBuilder = _import_request_builder()
                Settings = _import_settings()
                s = Settings.from_env()
                ctx: Dict[str, Any] = dict(order)
                # provide common aliases expected by builder
                ctx.setdefault("account_no", s.kiwoom_account_no)
                ctx.setdefault("account", s.kiwoom_account_no)

                rb = ApiRequestBuilder()
                res = rb.prepare(spec, ctx)

                if str(getattr(res, "action", "")).strip().lower() == "ready" and getattr(res, "request", None) is not None:
                    req = res.request
                    # ensure attributes expected by executors exist
                    if getattr(req, "query", None) is None:
                        setattr(req, "query", getattr(req, "params", {}) or {})
                    if getattr(req, "headers", None) is None:
                        setattr(req, "headers", {})
                    if getattr(req, "body", None) is None:
                        setattr(req, "body", {})
                    return req

                # not ready -> fall back to a safe NOOP request with hint
                return SimpleNamespace(
                    method="POST",
                    path="/__missing_params__",
                    headers={},
                    query={},
                    body={"missing": res.missing, "api_id": api_id},
                )
        except Exception:
            continue

    # Fallback: minimal request
    return SimpleNamespace(
        method="POST",
        path="/orders",
        headers={},
        query={},
        body={k: v for k, v in order.items() if k not in ("headers", "query")},
    )


def _normalize_execution(
    *,
    allowed: bool,
    execution_result: Any,
    allow_result: Any,
    order: Dict[str, Any],
    reason: str = "",
) -> Dict[str, Any]:
    """Normalize to dict shape used by tests and reports."""
    exec_mode = _resolve_execution_mode()
    resolved_reason = str(reason or "")
    if not resolved_reason and allow_result is not None:
        resolved_reason = str(getattr(allow_result, "reason", "") or "")

    payload: Dict[str, Any] = {}
    if execution_result is None:
        payload = {"mode": exec_mode}
    else:
        # ExecutionResult dataclass
        if hasattr(execution_result, "payload"):
            p = getattr(execution_result, "payload")
            if isinstance(p, dict):
                payload = dict(p)
        # If still empty, build from response/meta
        if not payload:
            if hasattr(execution_result, "response") and getattr(execution_result, "response") is not None:
                r = getattr(execution_result, "response")
                payload["status_code"] = getattr(r, "status_code", None)
                payload["api_ok"] = bool(getattr(r, "ok", False))
                raw_text = getattr(r, "raw_text", None)
                if raw_text is None:
                    raw_text = getattr(r, "text", None)
                payload["text"] = raw_text

                response_payload = getattr(r, "payload", None)
                if isinstance(response_payload, dict):
                    response_payload = dict(response_payload)
                    payload["response_payload"] = response_payload
                    payload["json"] = response_payload

                    for k in ("ord_no", "order_id", "orderId", "odno", "ODNO", "ordNo"):
                        v = response_payload.get(k)
                        if v is not None and str(v).strip():
                            payload["order_id"] = str(v).strip()
                            break

                    for k in ("msg_cd", "message_code", "code", "rt_cd", "error_code", "err_cd", "return_code"):
                        v = response_payload.get(k)
                        if v is not None and str(v).strip():
                            payload["broker_code"] = str(v).strip()
                            break

                    for k in ("msg1", "msg", "message", "return_msg", "error_message"):
                        v = response_payload.get(k)
                        if v is not None and str(v).strip():
                            payload["broker_message"] = str(v).strip()
                            break
                else:
                    payload["json"] = getattr(r, "json", None)

                err_code = getattr(r, "error_code", None)
                if err_code is not None and str(err_code).strip():
                    payload["error_code"] = str(err_code).strip()

                err_msg = getattr(r, "error_message", None)
                if err_msg is not None and str(err_msg).strip():
                    payload["error_message"] = str(err_msg).strip()
            if hasattr(execution_result, "meta") and getattr(execution_result, "meta") is not None:
                payload["meta"] = getattr(execution_result, "meta")
        payload.setdefault("mode", exec_mode)

    ok = bool(allowed)
    ok_source = "allowed_gate"
    if allowed and execution_result is not None:
        ok, ok_source = _infer_execution_ok(payload)
        if not ok:
            cur = resolved_reason.strip().lower()
            if cur in ("", "allowed"):
                bcode = str(payload.get("broker_code") or "").strip()
                resolved_reason = f"broker_rejected:{bcode}" if bcode else "broker_rejected"

    verdict = {
        "allowed": bool(allowed),
        "ok": bool(ok),
        "ok_source": str(ok_source),
        "reason": resolved_reason,
        "order": order,
        "payload": payload,
    }
    return verdict


def execute_from_packet(state: dict) -> dict:
    """Execute directly from a TradeDecisionPacket.

    Expects:
      - state['decision_packet']  # dict form
      - state['catalog_path'] optional (fallback: env KIWOOM_API_CATALOG_PATH)
      - state['run_id'] optional (auto-generate if missing)
      - optional: state['executor'] injected for tests
      - optional: state['supervisor'] injected for tests

    Produces:
      - state['execution'] (dict)
    """
    EventLogger, new_run_id = _import_event_logger()
    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    logger = EventLogger(log_path=Path(log_path))

    run_id = state.get("run_id") or new_run_id()
    state["run_id"] = run_id
    logger.log(run_id=run_id, stage="execute_from_packet", event="start", payload={})

    ApiCatalog = _import_api_catalog()
    Supervisor = _import_supervisor()
    get_executor = _import_get_executor()

    try:
        packet: Dict[str, Any] = state["decision_packet"]

        catalog_path = state.get("catalog_path") or _catalog_path_from_env()
        catalog = ApiCatalog.load(catalog_path)

        supervisor = state.get("supervisor")
        if supervisor is None:
            if hasattr(Supervisor, "from_settings"):
                supervisor = Supervisor.from_settings()
            else:
                supervisor = Supervisor()
        executor = state.get("executor") or get_executor()

        intent = packet.get("intent") or {}
        risk = packet.get("risk") or {}
        exec_context = packet.get("exec_context") or {}

        # Build order dict
        if state.get("order_builder") is not None:
            order = state["order_builder"](intent, catalog)  # type: ignore[call-arg]
        else:
            order = _build_order_from_intent(intent)
        order = _apply_mock_broker_order_safety(order)

        action = str(order.get("action") or "").strip().upper()
        if action == "NOOP":
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason="noop_intent_skipped",
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="verdict",
                payload={"allowed": False, "reason": "noop_intent_skipped"},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        portfolio_allowed, portfolio_reason, portfolio_details = _evaluate_portfolio_snapshot_guard(state, order)
        if not portfolio_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=portfolio_reason,
            )
            state["execution"]["portfolio_guard"] = portfolio_details
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="portfolio_guard_block",
                payload={"allowed": False, "reason": portfolio_reason, **portfolio_details},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        if _should_block_duplicate_mock_buy(state, order):
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason="duplicate_buy_position_exists",
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="verdict",
                payload={"allowed": False, "reason": "duplicate_buy_position_exists"},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        cash_allowed, cash_reason, cash_details = _evaluate_mock_cash_guard(state, order)
        if not cash_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=cash_reason,
            )
            state["execution"]["cash_guard"] = cash_details
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="verdict",
                payload={"allowed": False, "reason": cash_reason, **cash_details},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        degrade_allowed, degrade_reason, degrade_details = _evaluate_degrade_execution_policy(
            state=state,
            order=order,
            exec_context=exec_context,
        )
        if not degrade_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=degrade_reason,
            )
            state["execution"]["degrade_policy"] = degrade_details
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="degrade_policy_block",
                payload={"reason": degrade_reason, **degrade_details},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        # Supervisor verdict
        allow_result = _supervisor_allow(supervisor, order, risk)
        allowed = bool(getattr(allow_result, "allowed", getattr(allow_result, "allow", False)))
        # Mock mode bypasses supervisor gating for offline-safe test flows.
        # Real mode must honor supervisor verdict.
        if _resolve_execution_mode() == "mock":
            allowed = True

        if not allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=allow_result,
                order=order,
                reason=getattr(allow_result, "reason", "blocked"),
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="verdict", payload=state["execution"])
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        # Prepare request and execute
        req = _prepare_request(order, catalog)
        execution_result = executor.execute(req)

        state["execution"] = _normalize_execution(
            allowed=True,
            execution_result=execution_result,
            allow_result=allow_result,
            order=order,
        )

        logger.log(run_id=run_id, stage="execute_from_packet", event="verdict", payload={"allowed": True})
        logger.log(run_id=run_id, stage="execute_from_packet", event="execution", payload=state["execution"])
        logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
        return state

    except Exception as e:
        state["execution"] = {"allowed": False, "reason": str(e)}
        logger.log(run_id=run_id, stage="execute_from_packet", event="error", payload={"error": str(e)})
        raise
