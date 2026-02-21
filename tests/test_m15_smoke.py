from __future__ import annotations

import os
from pathlib import Path
import pytest

from libs.core.settings import Settings
from libs.supervisor.two_phase import TwoPhaseSupervisor
from libs.supervisor.intent_store import IntentStore
from libs.agent.executor.executor_agent import ExecutorAgent
from libs.skills.runner import CompositeSkillRunner


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure env does not leak between tests."""
    keys = [
        "APPROVAL_MODE",
        "AUTO_APPROVE",
        "KIWOOM_MODE",
        "EXECUTION_ENABLED",
        "SYMBOL_ALLOWLIST",
        "EXECUTION_MODE",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch
    for k in keys:
        monkeypatch.delenv(k, raising=False)


def _make_executor_agent(tmp_path: Path) -> ExecutorAgent:
    intent_store_path = tmp_path / "intents.jsonl"
    store = IntentStore(str(intent_store_path))
    runner = CompositeSkillRunner(
        settings=Settings.from_env(env_path="__missing__.env"),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    sup = TwoPhaseSupervisor(Settings.from_env(env_path="__missing__.env"))
    return ExecutorAgent(
        runner=runner,
        supervisor=sup,
        intent_store=store,
        intent_store_path=intent_store_path,
    )


def test_m15_two_phase_supervisor_manual_vs_auto(isolated_env: pytest.MonkeyPatch):
    isolated_env.setenv("KIWOOM_MODE", "mock")

    # manual -> needs_approval
    isolated_env.setenv("APPROVAL_MODE", "manual")
    sup = TwoPhaseSupervisor(Settings.from_env(env_path="__missing__.env"))
    d = sup.create_intent({"action": "BUY", "symbol": "005930", "qty": 1, "order_type": "market"})
    assert d.status == "needs_approval"

    # auto -> approved
    isolated_env.setenv("APPROVAL_MODE", "auto")
    sup = TwoPhaseSupervisor(Settings.from_env(env_path="__missing__.env"))
    d = sup.create_intent({"action": "BUY", "symbol": "005930", "qty": 1, "order_type": "market"})
    assert d.status == "approved"


def test_m15_auto_approve_legacy_env(isolated_env: pytest.MonkeyPatch):
    isolated_env.setenv("KIWOOM_MODE", "mock")

    # No APPROVAL_MODE -> falls back to AUTO_APPROVE legacy
    isolated_env.delenv("APPROVAL_MODE", raising=False)
    isolated_env.setenv("AUTO_APPROVE", "true")
    sup = TwoPhaseSupervisor(Settings.from_env(env_path="__missing__.env"))
    d = sup.create_intent({"action": "BUY", "symbol": "005930", "qty": 1, "order_type": "market"})
    assert d.status == "approved"


def test_m15_executor_agent_manual_flow_persists_and_rejects(isolated_env: pytest.MonkeyPatch, tmp_path: Path):
    isolated_env.setenv("KIWOOM_MODE", "mock")
    isolated_env.setenv("APPROVAL_MODE", "manual")

    agent = _make_executor_agent(tmp_path)

    res = agent.submit_order_intent(
        side="buy",
        symbol="005930",
        qty=1,
        order_type="market",
        approval_mode="manual",
        execution_enabled=False,
        rationale="m15 test",
    )
    assert "decision" in res
    assert res["decision"]["status"] in ("needs_approval", "approved", "rejected")

    # last/preview work
    last = agent.last_intent()
    assert last and last.get("symbol") == "005930"
    prev = agent.preview()
    assert prev["ok"] is True
    assert prev["intent"]["symbol"] == "005930"

    # list works
    lst = agent.list_intents(limit=5)
    assert lst["ok"] is True
    assert lst["count"] >= 1

    # reject marks a record
    rj = agent.reject(reason="unit test reject")
    assert rj["ok"] is True
    assert rj["status"] == "rejected"

    # list should include rejected status in recent records
    lst2 = agent.list_intents(limit=10)
    statuses = [x.get("status") for x in lst2.get("intents", [])]
    assert "rejected" in statuses


def test_m15_executor_agent_auto_but_execution_disabled_returns_note(isolated_env: pytest.MonkeyPatch, tmp_path: Path):
    isolated_env.setenv("KIWOOM_MODE", "mock")
    isolated_env.setenv("APPROVAL_MODE", "auto")

    agent = _make_executor_agent(tmp_path)

    res = agent.submit_order_intent(
        side="buy",
        symbol="005930",
        qty=1,
        order_type="market",
        approval_mode="auto",
        execution_enabled=False,  # should block "auto execute" path
        rationale="m15 test auto",
    )
    assert "note" in res
    assert "EXECUTION_ENABLED=false" in res["note"]
    assert "execution" not in res


def test_m15_real_mode_requires_execution_enabled(isolated_env: pytest.MonkeyPatch, tmp_path: Path):
    """
    If executor selection is real and KIWOOM_MODE=real, then EXECUTION_ENABLED must be true.
    We don't actually call the network: RealExecutor blocks before HTTP.
    """
    from libs.execution.executors.real_executor import RealExecutor
    from libs.execution.executors.base import ExecutionDisabledError
    from libs.catalog.api_request_builder import PreparedRequest

    isolated_env.setenv("KIWOOM_MODE", "real")
    isolated_env.setenv("EXECUTION_ENABLED", "false")

    ex = RealExecutor(Settings.from_env(env_path="__missing__.env"))
    req = PreparedRequest(
        api_id="DUMMY_API",
        method="GET",
        path="/dummy",
        headers={},
        query={},
        body={"stk_cd": "005930"},
    )

    # Real executor must block before any HTTP call when execution is disabled.
    with pytest.raises(ExecutionDisabledError) as e:
        ex.execute(req, auth_token="DUMMY")
    assert "Execution is disabled" in str(e.value)
