from __future__ import annotations

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_request_builder import ApiRequestBuilder
from libs.execution.order_client import OrderClient
from libs.core.settings import Settings
from libs.core.event_logger import EventLogger


def prepare_order_dry_run(state: dict) -> dict:
    """M7-2 node: build an order request (prepared) and return dry-run payload.
    Expects:
      - state['catalog_path']
      - state['order_api_id']            (explicit; do not auto-select here)
      - state['context']                (dict of values for request builder)
      - state['intent']                 (e.g., 'buy')
      - state['risk_context']           (dict)
    Produces:
      - state['order_dry_run']
    """
    s: Settings = state.get("settings") or Settings.from_env()
    logger = EventLogger(node="prepare_order_dry_run")
    logger.start({"intent": state.get("intent")})

    catalog = ApiCatalog.load(state["catalog_path"])
    spec = catalog.get(state["order_api_id"])
    builder = ApiRequestBuilder()
    prep = builder.prepare(spec, state.get("context", {}))

    if prep.action != "ready" or prep.request is None:
        state["order_dry_run"] = {
            "allowed": False,
            "reason": "Missing required parameters",
            "missing": prep.missing,
            "question": prep.question,
        }
        logger.end({"allowed": False, "reason": "missing_params"})
        return state

    client = OrderClient(settings=s)
    dry = client.dry_run_order(
        prep.request,
        intent=state.get("intent", "buy"),
        risk_context=state.get("risk_context", {}),
        dry_run_token=True,
    )

    state["order_dry_run"] = {
        "allowed": dry.allowed,
        "reason": dry.reason,
        "url": dry.url,
        "method": dry.method,
        "headers": dry.headers,
        "query": dry.query,
        "body": dry.body,
    }
    logger.end({"allowed": dry.allowed})
    return state
