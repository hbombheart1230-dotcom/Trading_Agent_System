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
    api_id = intent.get("order_api_id") or intent.get("api_id") or "ORDER_SUBMIT"

    # Allow multiple intent schemas during transition
    action = intent.get("action") or intent.get("intent") or intent.get("type") or "NOOP"
    action = str(action).upper()

    order: Dict[str, Any] = {
        "api_id": api_id,
        "action": action,
        "symbol": intent.get("symbol"),
        "qty": intent.get("qty") or intent.get("quantity"),
        "price": intent.get("price"),
        "order_type": intent.get("order_type") or intent.get("type") or "limit",
        "tif": intent.get("tif") or intent.get("time_in_force"),
        "rationale": intent.get("rationale") or intent.get("reason") or "",
    }
    # Pass through any extra keys (so request builder can pick them up)
    for k, v in intent.items():
        if k not in order:
            order[k] = v
    return order


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
    api_id = order.get("api_id") or order.get("order_api_id")
    if api_id:
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

                if res.is_ready():
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
            # fall back below
            pass

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
                payload["text"] = getattr(r, "text", None)
                payload["json"] = getattr(r, "json", None)
            if hasattr(execution_result, "meta") and getattr(execution_result, "meta") is not None:
                payload["meta"] = getattr(execution_result, "meta")
        payload.setdefault("mode", exec_mode)

    verdict = {
        "allowed": bool(allowed),
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
