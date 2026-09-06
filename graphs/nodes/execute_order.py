from __future__ import annotations

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_request_builder import ApiRequestBuilder
from libs.core.event_logger_compat import get_event_logger
from libs.core.symbols import normalize_symbol
from libs.execution.executors.factory import get_executor
from libs.core.settings import Settings
from libs.risk.supervisor import Supervisor


def execute_order(state: dict) -> dict:
    """Execute order through Supervisor + Executor."""
    s: Settings = state.get("settings") or Settings.from_env()
    logger = get_event_logger("execute_order")
    try:
        logger.start({"intent": state.get("intent")})
    except Exception:
        pass

    sup = Supervisor(s)
    allow = sup.allow(state.get("intent", "buy"), state.get("risk_context", {}))
    if not allow.allow:
        state["execution"] = {"allowed": False, "reason": allow.reason, "details": allow.details}
        try:
            logger.end({"allowed": False, "reason": allow.reason})
        except Exception:
            pass
        return state

    catalog = ApiCatalog.load(state["catalog_path"])
    spec = catalog.get(state["order_api_id"])
    builder = ApiRequestBuilder()
    prep = builder.prepare(spec, state.get("context", {}))

    if prep.action != "ready" or prep.request is None:
        state["execution"] = {
            "allowed": False,
            "reason": "Missing required parameters",
            "missing": prep.missing,
            "question": prep.question,
        }
        try:
            logger.end({"allowed": False, "reason": "missing_params"})
        except Exception:
            pass
        return state

    # Phase 1 Step 5B Safety Fix 2: this function is a legacy, parallel
    # execution path (LEGACY_REACHABLE per Codex's review) that does not go
    # through graphs/nodes/execute_from_packet.py's guard chain at all.
    # Reuse its UNKNOWN quarantine guard/lock store directly -- same durable
    # per-symbol lock files, same global_mutation_halt fallback -- so a
    # symbol quarantined via this path is also blocked on the canonical
    # live path (and vice versa), rather than this path being a way to
    # silently bypass an active quarantine.
    from graphs.nodes.execute_from_packet import (
        _evaluate_unknown_quarantine_guard,
        _quarantine_symbol_for_unknown_outcome,
    )

    req_body = getattr(prep.request, "body", None) or {}
    guard_order = {
        "action": str(state.get("intent") or "").strip().upper(),
        "symbol": normalize_symbol(req_body.get("stk_cd") or req_body.get("symbol")),
    }
    quarantine_allowed, quarantine_reason, quarantine_details = _evaluate_unknown_quarantine_guard(state, guard_order)
    if not quarantine_allowed:
        state["execution"] = {"allowed": False, "reason": quarantine_reason, "quarantine": quarantine_details}
        try:
            logger.end({"allowed": False, "reason": quarantine_reason})
        except Exception:
            pass
        return state

    executor = get_executor(s)
    def normalize_legacy(result):
        if result is None:
            return {'allowed': False, 'ok': False, 'broker_outcome': 'NOT_SENT'}
        result_meta = dict(getattr(result, 'meta', None) or {})
        outcome = str(result_meta.get('broker_outcome') or '').strip().upper()
        if not outcome:
            outcome = 'ACCEPTED' if bool(result.response.ok) else 'REJECTED'
        return {'allowed': True, 'status_code': result.response.status_code,
                'ok': result.response.ok, 'payload': result.response.payload,
                'error_code': result.response.error_code, 'error_message': result.response.error_message,
                'meta': result.meta, 'broker_outcome': outcome, 'reconciliation_required': outcome == 'UNKNOWN'}

    from libs.execution.intent_execution_owner import execute_owned_order
    guard_order.update({key: req_body.get(key) for key in ('orig_ord_no', 'cncl_qty', 'mdfy_qty', 'mdfy_uv')})
    guard_order.update(qty=req_body.get('ord_qty'), price=req_body.get('ord_uv'), intent_id=state.get('intent_id'))
    state['execution'] = execute_owned_order(state=state, order=guard_order, request=prep.request,
                                            executor=executor, normalize=normalize_legacy)
    broker_outcome = state['execution']['broker_outcome']
    if broker_outcome == "UNKNOWN":
        _quarantine_symbol_for_unknown_outcome(state, guard_order, state["execution"])
    try:
        logger.end({"allowed": state['execution']['allowed'], "ok": state['execution']['ok']})
    except Exception:
        pass
    return state
