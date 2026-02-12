import pytest

from libs.execution.executors.real_executor import RealExecutor
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings


class _DummyResp:
    def __init__(self, status_code: int = 200, text: str = "{}"):
        self.status_code = status_code
        self.text = text


class _DummyHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, path, headers=None, params=None, json_body=None, dry_run=False):
        self.calls.append({
            "method": method,
            "path": path,
            "headers": headers or {},
            "params": params or {},
            "json": json_body,
            "dry_run": dry_run,
        })
        return "https://mockapi.kiwoom.com" + path, _DummyResp(200, "{\"ok\":true}")


def test_real_executor_allows_mock_mode_without_execution_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "mock")

    s = Settings.from_env(env_path="__missing__.env")
    http = _DummyHttp()
    ex = RealExecutor(settings=s, http=http)  # type: ignore[arg-type]

    req = PreparedRequest(api_id="X", method="POST", path="/orders", headers={}, query={}, body={"b": 2})
    out = ex.execute(req, auth_token="dummy")
    assert out.meta.get("executor") == "real"
    assert http.calls and http.calls[0]["dry_run"] is False
