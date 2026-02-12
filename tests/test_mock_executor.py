from libs.execution.executors.mock_executor import MockExecutor
from libs.catalog.api_request_builder import PreparedRequest


def test_mock_executor_returns_payload():
    ex = MockExecutor(base_url="https://example.com")
    req = PreparedRequest(api_id="X", method="POST", path="/orders", headers={}, query={"a": "1"}, body={"b": 2})
    res = ex.execute(req)
    assert res.response.ok is True
    assert res.response.payload["mode"] == "mock"
    assert res.response.payload["url"] == "https://example.com/orders"
