from libs.catalog.api_request_builder import ApiRequestBuilder
from libs.catalog.api_catalog import ApiSpec


def test_prepare_ask_when_required_missing():
    spec = ApiSpec(
        api_id="ACC_BAL",
        method="GET",
        path="/account/balance",
        params={
            "account_no": {"in": "query", "required": True},
        },
    )
    builder = ApiRequestBuilder()
    res = builder.prepare(spec, context={})
    assert res.action == "ask"
    assert "account_no" in res.missing


def test_prepare_ready_when_present():
    spec = ApiSpec(
        api_id="ACC_BAL",
        method="GET",
        path="/account/balance",
        params={
            "account_no": {"in": "query", "required": True},
        },
    )
    builder = ApiRequestBuilder()
    res = builder.prepare(spec, context={"account_no": "123"})
    assert res.action == "ready"
    assert res.request is not None
    assert res.request.query["account_no"] == "123"
