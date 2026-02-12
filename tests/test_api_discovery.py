# tests/test_api_discovery.py
from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_discovery import ApiDiscovery


def test_api_discovery_basic_search():
    catalog = ApiCatalog.from_obj([
        {
            "api_id": "ACC_BAL",
            "title": "계좌 잔고 조회",
            "method": "GET",
            "path": "/account/balance",
            "tags": ["account"],
        },
        {
            "api_id": "ACC_EVAL",
            "title": "계좌 평가 금액 조회",
            "method": "GET",
            "path": "/account/eval",
            "tags": ["account"],
        },
    ])

    disc = ApiDiscovery(catalog)
    hits = disc.search("계좌 잔고", top_k=2)

    assert len(hits) >= 1
    assert hits[0].spec.api_id == "ACC_BAL"
    assert hits[0].score > 0


def test_api_discovery_top_k_limit():
    catalog = ApiCatalog.from_obj([
        {"api_id": f"API_{i}", "title": "테스트"} for i in range(10)
    ])

    disc = ApiDiscovery(catalog)
    hits = disc.search("API", top_k=3)

    assert len(hits) == 3
