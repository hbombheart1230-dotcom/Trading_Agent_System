from __future__ import annotations

from pathlib import Path
import pytest

from libs.core.settings import Settings
from libs.supervisor.two_phase import TwoPhaseSupervisor
from libs.supervisor.intent_store import IntentStore
from libs.agent.executor.executor_agent import ExecutorAgent
from libs.skills.runner import CompositeSkillRunner


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "manual")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)
    return monkeypatch


def _make_agent(tmp_path: Path) -> ExecutorAgent:
    store_path = tmp_path / "intents.jsonl"
    store = IntentStore(str(store_path))
    settings = Settings.from_env()
    sup = TwoPhaseSupervisor(settings)
    runner = CompositeSkillRunner.from_env()
    return ExecutorAgent(runner=runner, supervisor=sup, intent_store=store, intent_store_path=store_path)


def test_m16_approve_marks_and_executes_idempotently(isolated_env: pytest.MonkeyPatch, tmp_path: Path):
    agent = _make_agent(tmp_path)

    # create intent (manual)
    res = agent.submit_order_intent(
        side="buy",
        symbol="005930",
        qty=1,
        order_type="market",
        approval_mode="manual",
        execution_enabled=False,
        rationale="m16 test",
    )
    assert res["decision"]["status"] in ("needs_approval", "approved", "rejected")

    prev = agent.preview()
    assert prev["ok"] is True
    iid = prev["intent_id"]

    # approve with execution disabled -> approved only
    a1 = agent.approve(intent_id=iid, execution_enabled=False)
    assert a1["ok"] is True
    assert a1["status"] == "approved"

    # approve with execution enabled -> executed
    a2 = agent.approve(intent_id=iid, execution_enabled=True)
    assert a2["ok"] is True
    assert a2["status"] == "executed"
    assert "execution" in a2

    # approve again -> cached
    a3 = agent.approve(intent_id=iid, execution_enabled=True)
    assert a3["ok"] is True
    assert a3["status"] == "executed"
    assert a3.get("note")
