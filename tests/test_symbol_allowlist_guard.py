import os

import pytest

from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.executors.real_executor import RealExecutor


class _DummyHttp:
    """Minimal HttpClient stub used by RealExecutor in tests."""

    def __init__(self):
        self.calls = []

    def request(self, method, path, headers=None, params=None, json_body=None, dry_run=False):
        self.calls.append((method, path, headers or {}, params or {}, json_body, dry_run))

        class _Resp:
            status_code = 200
            text = '{"return_code":0,"return_msg":"ok"}'

        return "https://example.test" + path, _Resp()


def _mk_req(symbol: str) -> PreparedRequest:
    return PreparedRequest(
        api_id="TEST",
        method="POST",
        path="/api/dostk/ordr",
        headers={},
        query={},
        body={"stk_cd": symbol, "ord_qty": "1"},
    )


def test_allowlist_disabled_when_missing(monkeypatch):
    monkeypatch.delenv("SYMBOL_ALLOWLIST", raising=False)
    assert RealExecutor._parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST")) == set()


def test_allowlist_disabled_when_empty(monkeypatch):
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "   ")
    assert RealExecutor._parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST")) == set()


def test_allowlist_blocks_unknown_symbol(monkeypatch):
    # Enable execution so we reach the allowlist guard.
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "000660, 035420")

    ex = RealExecutor(http=_DummyHttp())
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mk_req("005930"), auth_token="t")


def test_allowlist_allows_listed_symbol(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930,000660")

    http = _DummyHttp()
    ex = RealExecutor(http=http)
    out = ex.execute(_mk_req("005930"), auth_token="t")
    assert out.response.status_code == 200
    assert http.calls, "Expected HTTP call to be made"
