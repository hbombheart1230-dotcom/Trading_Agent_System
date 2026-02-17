from __future__ import annotations

import json

import pytest

from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings
from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.executors.real_executor import RealExecutor
from scripts.check_real_execution_preflight import main as preflight_main


def _mk_req(symbol: str) -> PreparedRequest:
    return PreparedRequest(
        api_id="ORDER_SUBMIT",
        method="POST",
        path="/api/dostk/ordr",
        headers={},
        query={},
        body={"stk_cd": symbol, "ord_qty": "1"},
    )


def test_m24_5_preflight_mock_mode_ok_without_execution_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")

    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"))
    pf = ex.preflight_check(_mk_req("005930"))
    assert pf["ok"] is True
    assert pf["code"] == "OK"


def test_m24_5_preflight_real_mode_reports_explicit_denial_code(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("ALLOW_REAL_EXECUTION", "true")
    monkeypatch.delenv("KIWOOM_APP_KEY", raising=False)
    monkeypatch.delenv("KIWOOM_APP_SECRET", raising=False)
    monkeypatch.delenv("KIWOOM_ACCOUNT_NO", raising=False)

    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"))
    pf = ex.preflight_check(_mk_req("005930"))
    assert pf["ok"] is False
    assert pf["code"] == "MISSING_APP_KEY"


def test_m24_5_execute_denial_includes_reason_code(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "000660,035420")

    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"))
    with pytest.raises(ExecutionDisabledError) as e:
        ex.execute(_mk_req("005930"), auth_token="t")
    msg = str(e.value)
    assert "[ALLOWLIST_BLOCKED]" in msg
    assert "SYMBOL_ALLOWLIST" in msg


def test_m24_5_preflight_cli_json_fail_case(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")

    rc = preflight_main(["--symbol", "005930", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["code"] == "EXECUTION_DISABLED"
