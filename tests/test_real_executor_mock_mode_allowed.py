import pytest

from libs.execution.executors.base import ExecutionDisabledError
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


def test_real_executor_blocks_paper_mode_mutation_without_execution_enabled(monkeypatch: pytest.MonkeyPatch):
    # Paper Trading Execution Finalization (2026-09-17): EXECUTION_ENABLED
    # is a global physical-dispatch switch for MUTATIONS, independent of
    # KIWOOM_MODE. KIWOOM_MODE=mock (Paper Trading -- a real HTTP call to
    # Kiwoom's own sandbox) must NOT bypass it for an order-mutating call --
    # this test replaces test_real_executor_allows_mock_mode_without_execution_enabled,
    # which asserted the opposite (a live-reproduced bypass, fixed here).
    #
    # Uses a real mutation api_id (kt10000 = BUY) rather than the previous
    # generic/unrecognized "X" placeholder (P1.3 Paper acceptance,
    # 2026-09-30): EXECUTION_ENABLED now gates mutations only, not reads
    # (see RealExecutor.preflight_check()'s own docstring) -- "X" is not a
    # real Kiwoom api_id and does not represent either category
    # unambiguously, so it no longer exercises what this test is actually
    # meant to prove. A genuine BUY/SELL/MODIFY/CANCEL request must still be
    # blocked; that is what this test asserts now.
    monkeypatch.delenv("EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "mock")

    s = Settings.from_env(env_path="__missing__.env")
    http = _DummyHttp()
    ex = RealExecutor(settings=s, http=http)  # type: ignore[arg-type]

    req = PreparedRequest(
        api_id="kt10000", method="POST", path="/api/dostk/ordr", headers={}, query={},
        body={"stk_cd": "005930", "ord_qty": "1"},
    )
    with pytest.raises(ExecutionDisabledError):
        ex.execute(req, auth_token="dummy")
    assert not http.calls


def test_real_executor_allows_paper_mode_read_without_execution_enabled(monkeypatch: pytest.MonkeyPatch):
    # P1.3 Paper acceptance (2026-09-30): the read/write gate separation
    # fix. A pure broker READ (not one of the four mutation api_ids --
    # here a Kiwoom account-balance query, kt00018) must be allowed through
    # even with EXECUTION_ENABLED unset/false, in Paper mode
    # (KIWOOM_MODE=mock) -- this is the exact call shape
    # KiwoomAccountSnapshotCollector/KiwoomOrderFillReader use, and the
    # exact gap a live P1.3 acceptance run against the real Kiwoom Paper
    # sandbox found: every existing production read path was rejected the
    # same as an order dispatch would be.
    monkeypatch.delenv("EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "mock")

    s = Settings.from_env(env_path="__missing__.env")
    http = _DummyHttp()
    ex = RealExecutor(settings=s, http=http)  # type: ignore[arg-type]

    req = PreparedRequest(
        api_id="kt00018", method="POST", path="/api/dostk/acnt", headers={}, query={},
        body={"qry_tp": "1", "dmst_stex_tp": "KRX"},
    )
    out = ex.execute(req, auth_token="dummy")
    assert out.meta.get("executor") == "real"
    assert http.calls and http.calls[0]["headers"].get("api-id") == "kt00018"


def test_real_executor_allows_paper_mode_with_execution_enabled(monkeypatch: pytest.MonkeyPatch):
    # Paper Trading (EXECUTION_MODE=real, KIWOOM_MODE=mock) with
    # EXECUTION_ENABLED=true dispatches without needing ALLOW_REAL_EXECUTION
    # -- that flag is live-account-only.
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("ALLOW_REAL_EXECUTION", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "mock")

    s = Settings.from_env(env_path="__missing__.env")
    http = _DummyHttp()
    ex = RealExecutor(settings=s, http=http)  # type: ignore[arg-type]

    req = PreparedRequest(api_id="X", method="POST", path="/orders", headers={}, query={}, body={"b": 2})
    out = ex.execute(req, auth_token="dummy")
    assert out.meta.get("executor") == "real"
    assert http.calls and http.calls[0]["dry_run"] is False
    assert http.calls[0]["headers"].get("api-id") == "X"


def test_real_executor_sends_empty_json_object_for_post(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_MODE", "mock")

    http = _DummyHttp()
    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"), http=http)  # type: ignore[arg-type]
    req = PreparedRequest(api_id="X", method="POST", path="/account", headers={}, query={}, body={})

    ex.execute(req, auth_token="dummy")

    assert http.calls[0]["json"] == {}
