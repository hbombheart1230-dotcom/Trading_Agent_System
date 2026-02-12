from __future__ import annotations

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_request_builder import ApiRequestBuilder
from libs.core.event_logger_compat import get_event_logger
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

    executor = get_executor(s)
    result = executor.execute(prep.request)

    state["execution"] = {
        "allowed": True,
        "status_code": result.response.status_code,
        "ok": result.response.ok,
        "payload": result.response.payload,
        "error_code": result.response.error_code,
        "error_message": result.response.error_message,
        "meta": result.meta,
    }
    try:
        logger.end({"allowed": True, "ok": result.response.ok})
    except Exception:
        pass
    return state
