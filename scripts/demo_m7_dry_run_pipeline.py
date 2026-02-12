from __future__ import annotations

import json
from pathlib import Path

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_discovery import ApiDiscovery
from libs.catalog.api_planner import ApiPlanner
from libs.catalog.api_request_builder import ApiRequestBuilder
from libs.execution.order_client import OrderClient


def build_demo_catalog(tmp_path: Path) -> Path:
    """Create a tiny api_catalog.jsonl for demo purposes."""
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "api_id": "ORDER_SUBMIT",
            "title": "주문 제출",
            "description": "신규 매수/매도 주문을 제출한다 (demo).",
            "method": "POST",
            "path": "/uapi/domestic-stock/v1/trading/order",
            "tags": ["order"],
            "params": {},
            "_flags": {"callable": True},
        },
        {
            "api_id": "ACC_BAL",
            "title": "계좌 잔고 조회",
            "description": "계좌 잔고를 조회한다 (demo).",
            "method": "GET",
            "path": "/uapi/domestic-stock/v1/trading/inquire-balance",
            "tags": ["account"],
            "params": {},
            "_flags": {"callable": True},
        },
    ]
    with tmp_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return tmp_path


def main():
    catalog_path = Path("./data/specs/api_catalog.demo.jsonl")
    build_demo_catalog(catalog_path)

    catalog = ApiCatalog.load(str(catalog_path))
    discovery = ApiDiscovery(catalog)
    matches = discovery.search("주문", top_k=5)

    planner = ApiPlanner()
    plan = planner.plan(matches)

    if plan.action != "select" or plan.selected is None:
        print("[PLAN] need clarification:", plan.reason)
        for m in getattr(plan, "candidates", []) or []:
            print("-", m.spec.api_id, m.score, m.reasons)
        return

    selected_api_id = plan.selected.spec.api_id
    spec = catalog.get(selected_api_id)

    builder = ApiRequestBuilder()
    prep = builder.prepare(spec, context={})
    if prep.action != "ready" or prep.request is None:
        print("[PREP] missing:", prep.missing, prep.question)
        return

    client = OrderClient()
    dry = client.dry_run_order(
        prep.request,
        intent="buy",
        risk_context={
            "daily_pnl_ratio": -0.001,
            "open_positions": 0,
            "per_trade_risk_ratio": 0.001,
        },
        dry_run_token=True,
    )

    out = {
        "selected_api_id": selected_api_id,
        "dry_run": {
            "allowed": dry.allowed,
            "reason": dry.reason,
            "url": dry.url,
            "method": dry.method,
            "headers": dry.headers,
            "query": dry.query,
            "body": dry.body,
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
