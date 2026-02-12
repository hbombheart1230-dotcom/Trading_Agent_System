from __future__ import annotations

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_request_builder import ApiRequestBuilder


def prepare_api_call(state: dict) -> dict:
    """Prepare request object from selected api_id + context (no execution).
    Expects:
      - state['catalog_path']
      - state['plan_result']['selected']['api_id']  (when action=='select')
      - state['context'] (dict) : known values (account_no, ticker, ...)
    Produces:
      - state['prepare_result'] : ready/ask + request + question
    """
    catalog = ApiCatalog.load(state["catalog_path"])
    plan = state["plan_result"]
    if plan["action"] != "select" or not plan.get("selected"):
        state["prepare_result"] = {
            "action": "ask",
            "reason": "No selected API (planner returned ask)",
            "question": "어떤 API를 사용할지 먼저 확정해야 해요.",
        }
        return state

    api_id = plan["selected"]["api_id"]
    spec = catalog.get(api_id)
    builder = ApiRequestBuilder()

    ctx = state.get("context", {})
    res = builder.prepare(spec, ctx)

    state["prepare_result"] = {
        "action": res.action,
        "reason": res.reason,
        "missing": res.missing,
        "question": res.question,
        "request": None if res.request is None else {
            "api_id": res.request.api_id,
            "method": res.request.method,
            "path": res.request.path,
            "headers": res.request.headers,
            "query": res.request.query,
            "body": res.request.body,
        },
    }
    return state
