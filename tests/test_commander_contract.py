from __future__ import annotations

from typing import Any, Dict

from libs.agent.commander import Commander
from libs.agent.strategist import Strategist
from libs.agent.scanner import Scanner
from libs.agent.monitor import Monitor
from libs.agent.reporter import Reporter


class DummyExecutor:
    def submit(
        self,
        *,
        intent: Dict[str, Any],
        approval_mode: str = "manual",
        execution_enabled: bool = False,
    ) -> Dict[str, Any]:
        return {
            "decision": {
                "status": "approved" if approval_mode == "auto" else "needs_approval",
                "execution_enabled": bool(execution_enabled),
            }
        }


class _NoopLogger:
    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Dict[str, Any],
        ts: str | None = None,
    ) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "stage": stage,
            "event": event,
            "payload": payload,
            "ts": ts,
        }


def _make_commander() -> Commander:
    return Commander(
        strategist=Strategist(),
        scanner=Scanner(),
        monitor=Monitor(),
        reporter=Reporter(),
        executor=DummyExecutor(),  # type: ignore[arg-type]
    )


def test_commander_run_works_with_current_agent_interfaces_no_intent():
    c = _make_commander()

    out = c.run(context={"thesis": "t0"}, approval_mode="manual", execution_enabled=False)

    assert isinstance(out.plan, dict)
    assert out.intent is None
    assert out.execution is None
    assert isinstance(out.report, dict)
    assert out.report.get("intents_count") == 0


def test_commander_run_executes_first_intent_from_scanner_list():
    c = _make_commander()

    out = c.run(
        context={
            "thesis": "t1",
            "intents": [{"side": "BUY", "symbol": "005930", "qty": 1, "order_type": "market"}],
        },
        approval_mode="auto",
        execution_enabled=True,
    )

    assert out.intent is not None
    assert out.intent["symbol"] == "005930"
    assert isinstance(out.execution, dict)
    assert out.execution.get("decision", {}).get("status") == "approved"
    assert out.report.get("executions_count") == 1


def test_commander_run_canonical_bridge_uses_graph_mode():
    c = _make_commander()
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        state["path"] = "graph_spine"
        return state

    out = c.run_canonical(state={"event_logger": _NoopLogger()}, mode="graph_spine", graph_runner=graph_runner)
    assert out["path"] == "graph_spine"
    assert called["graph"] == 1


def test_commander_run_canonical_bridge_honors_pause_transition():
    c = _make_commander()
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    out = c.run_canonical(
        state={"runtime_control": "pause", "event_logger": _NoopLogger()},
        mode="graph_spine",
        graph_runner=graph_runner,
    )

    assert out["runtime_status"] == "paused"
    assert called["graph"] == 0
