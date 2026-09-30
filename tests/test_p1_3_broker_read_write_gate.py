"""Regression coverage for the 2026-09-30 P1.3 broker read/write gate fix.

Root cause: every existing production code path for a read-only Kiwoom
broker query (account balance, open orders) routed through
RealExecutor.preflight_check(), which required EXECUTION_ENABLED=true
unconditionally -- for reads exactly as for order mutations. A live P1.3
Paper acceptance run against the real Kiwoom Paper sandbox
(EXECUTION_MODE=real, KIWOOM_MODE=mock, EXECUTION_ENABLED=false,
ALLOW_REAL_EXECUTION=false) found PAPER_AUTH and PAPER_ACCOUNT_QUERY pass
(they use executor-independent read paths) but PAPER_OPEN_ORDER_QUERY
fail with ExecutionDisabledError, even though no order was ever placed or
attempted.

Fix: RealExecutor.preflight_check() now only enforces EXECUTION_ENABLED
for requests classified as a mutation by the existing, already-trusted
libs.execution.guards.broker_mutation.is_mutation_request() allowlist
(kt10000/kt10001/kt10002/kt10003 = BUY/SELL/MODIFY/CANCEL, plus the
unresolved "order_submit" alias). Everything else -- including every
account/order-history/open-order read API id -- is no longer blocked by
this flag. The ALLOW_REAL_EXECUTION / credential / base-URL checks for
KIWOOM_MODE=real are unchanged and still apply to both reads and writes.
"""

from __future__ import annotations

import pytest

from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings
from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.executors.real_executor import RealExecutor


class _DummyResp:
    def __init__(self, status_code: int = 200, text: str = "{}"):
        self.status_code = status_code
        self.text = text


class _DummyHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, path, headers=None, params=None, json_body=None, dry_run=False, **kwargs):
        self.calls.append(
            {"method": method, "path": path, "headers": headers or {}, "json": json_body, "dry_run": dry_run}
        )
        return "https://mockapi.kiwoom.com" + path, _DummyResp(200, "{\"ok\":true}")


def _executor(monkeypatch: pytest.MonkeyPatch, *, kiwoom_mode: str = "mock", execution_enabled: bool | None = None):
    monkeypatch.setenv("KIWOOM_MODE", kiwoom_mode)
    if execution_enabled is None:
        monkeypatch.delenv("EXECUTION_ENABLED", raising=False)
    else:
        monkeypatch.setenv("EXECUTION_ENABLED", "true" if execution_enabled else "false")
    monkeypatch.delenv("ALLOW_REAL_EXECUTION", raising=False)
    http = _DummyHttp()
    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"), http=http)  # type: ignore[arg-type]
    return ex, http


def _read_req(api_id: str, body: dict | None = None) -> PreparedRequest:
    return PreparedRequest(api_id=api_id, method="POST", path="/api/dostk/acnt", headers={}, query={}, body=body or {})


def _mutation_req(api_id: str) -> PreparedRequest:
    return PreparedRequest(
        api_id=api_id, method="POST", path="/api/dostk/ordr", headers={}, query={},
        body={"stk_cd": "005930", "ord_qty": "1", "ord_uv": "1000"},
    )


# --- B/C: reads succeed with EXECUTION_ENABLED=false -------------------------


@pytest.mark.parametrize("api_id", ["kt00018", "kt00009", "ka10075", "kt00007"])
def test_execution_disabled_allows_broker_reads(monkeypatch: pytest.MonkeyPatch, api_id: str):
    ex, http = _executor(monkeypatch, execution_enabled=False)
    out = ex.execute(_read_req(api_id), auth_token="dummy")
    assert out.meta.get("executor") == "real"
    assert http.calls and http.calls[0]["headers"].get("api-id") == api_id


def test_execution_disabled_preflight_ok_for_open_order_query(monkeypatch: pytest.MonkeyPatch):
    ex, _ = _executor(monkeypatch, execution_enabled=False)
    pf = ex.preflight_check(_read_req("kt00009"))
    assert pf["ok"] is True
    assert pf["code"] == "OK"


# --- D/E: mutations remain blocked with EXECUTION_ENABLED=false --------------


@pytest.mark.parametrize("api_id", ["kt10000", "kt10001", "kt10002", "kt10003", "ORDER_SUBMIT"])
def test_execution_disabled_blocks_mutations(monkeypatch: pytest.MonkeyPatch, api_id: str):
    ex, http = _executor(monkeypatch, execution_enabled=False)
    with pytest.raises(ExecutionDisabledError) as exc:
        ex.execute(_mutation_req(api_id), auth_token="dummy")
    assert "[EXECUTION_DISABLED]" in str(exc.value)
    assert not http.calls


def test_execution_disabled_buy_dispatch_blocked(monkeypatch: pytest.MonkeyPatch):
    ex, http = _executor(monkeypatch, execution_enabled=False)
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mutation_req("kt10000"), auth_token="dummy")  # BUY
    assert not http.calls


def test_execution_disabled_sell_dispatch_blocked(monkeypatch: pytest.MonkeyPatch):
    ex, http = _executor(monkeypatch, execution_enabled=False)
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mutation_req("kt10001"), auth_token="dummy")  # SELL
    assert not http.calls


# --- Ambiguous request (no req at all) fails closed, exactly as before ------


def test_preflight_with_no_request_still_requires_execution_enabled(monkeypatch: pytest.MonkeyPatch):
    ex, _ = _executor(monkeypatch, execution_enabled=False)
    pf = ex.preflight_check(None)
    assert pf["ok"] is False
    assert pf["code"] == "EXECUTION_DISABLED"


# --- Live-account guard (ALLOW_REAL_EXECUTION) is unchanged for reads too --


def test_live_mode_read_still_requires_allow_real_execution(monkeypatch: pytest.MonkeyPatch):
    # KIWOOM_MODE=real: the live-account-only guard must still apply
    # unconditionally, including to reads -- this fix narrows only the
    # EXECUTION_ENABLED check, not ALLOW_REAL_EXECUTION.
    ex, http = _executor(monkeypatch, kiwoom_mode="real", execution_enabled=True)
    monkeypatch.delenv("ALLOW_REAL_EXECUTION", raising=False)
    pf = ex.preflight_check(_read_req("kt00018"))
    assert pf["ok"] is False
    assert pf["code"] == "REAL_EXECUTION_NOT_ALLOWED"


# --- Enabled execution: behavior for mutations/reads is unaffected ---------


def test_execution_enabled_true_still_allows_mutation(monkeypatch: pytest.MonkeyPatch):
    ex, http = _executor(monkeypatch, execution_enabled=True)
    out = ex.execute(_mutation_req("kt10000"), auth_token="dummy")
    assert out.meta.get("executor") == "real"
    assert http.calls


# --- No production/broker mutation module reachable from a read path -------


def test_read_execution_never_reaches_mutation_transport_path(monkeypatch: pytest.MonkeyPatch):
    ex, http = _executor(monkeypatch, execution_enabled=False)
    out = ex.execute(_read_req("kt00018"), auth_token="dummy")
    assert "broker_outcome" not in out.meta  # only set by _execute_mutation
