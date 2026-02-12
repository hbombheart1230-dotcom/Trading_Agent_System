from pathlib import Path
import json

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_discovery import ApiDiscovery
from libs.catalog.api_planner import ApiPlanner


def test_demo_catalog_plans_order(tmp_path):
    p = tmp_path / "api_catalog.demo.jsonl"
    records = [
        {"api_id": "ORDER_SUBMIT", "title": "주문 제출", "method": "POST", "path": "/orders", "tags": ["order"], "params": {}, "_flags": {"callable": True}},
        {"api_id": "ACC_BAL", "title": "계좌 잔고 조회", "method": "GET", "path": "/balance", "tags": ["account"], "params": {}, "_flags": {"callable": True}},
    ]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")

    catalog = ApiCatalog.load(str(p))
    disc = ApiDiscovery(catalog)
    matches = disc.search("주문", top_k=5)
    plan = ApiPlanner().plan(matches)

    assert plan.action == "select"
    assert plan.selected is not None
    assert plan.selected.spec.api_id == "ORDER_SUBMIT"
