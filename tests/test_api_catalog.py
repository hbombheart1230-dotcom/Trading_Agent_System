# tests/test_api_catalog.py
import pytest

from libs.catalog.api_catalog import ApiCatalog, ApiNotFoundError, ApiCatalogLoadError


def test_catalog_from_list_and_get():
    catalog = ApiCatalog.from_obj([
        {"api_id": "ACC001", "title": "Account Balance", "method": "GET", "path": "/v1/account/balance"},
        {"api_id": "ORD001", "title": "Order", "method": "POST", "path": "/v1/order"},
    ])

    spec = catalog.get("ACC001")
    assert spec.api_id == "ACC001"
    assert spec.method == "GET"
    assert catalog.has("ORD001") is True
    assert catalog.has("NOPE") is False


def test_catalog_missing_api_raises():
    catalog = ApiCatalog.from_obj([{"api_id": "X", "title": "X"}])
    with pytest.raises(ApiNotFoundError):
        catalog.get("Y")


def test_catalog_duplicate_id_raises():
    with pytest.raises(ApiCatalogLoadError):
        ApiCatalog.from_obj([
            {"api_id": "DUP", "title": "A"},
            {"api_id": "DUP", "title": "B"},
        ])


def test_catalog_mapping_style_supported():
    catalog = ApiCatalog.from_obj({
        "ACC001": {"title": "Account Balance", "method": "GET"},
        "ORD001": {"title": "Order", "method": "POST"},
    })
    assert catalog.get("ACC001").api_id == "ACC001"
    assert catalog.get("ORD001").method == "POST"
