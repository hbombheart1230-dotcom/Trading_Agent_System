from __future__ import annotations

import json
from typing import Any, Dict

from graphs.trading_graph import run_trading_graph
from scripts.demo_m22_graph_with_hydration import main as graph_demo_main


def _noop(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def test_m22_6_graph_does_not_hydrate_by_default():
    called = {"hydrate": 0}

    def hydrate(state: Dict[str, Any]) -> Dict[str, Any]:
        called["hydrate"] += 1
        return state

    def scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["scanned"] = True
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "noop"
        return state

    out = run_trading_graph(
        {"candidates": [{"symbol": "AAA"}]},
        strategist=_noop,
        hydrate=hydrate,
        scanner=scanner,
        monitor=_noop,
        decide=decide,
    )
    assert called["hydrate"] == 0
    assert out["scanned"] is True


def test_m22_6_graph_hydrates_when_flag_enabled_and_on_retry():
    called = {"hydrate": 0, "scan": 0}

    def hydrate(state: Dict[str, Any]) -> Dict[str, Any]:
        called["hydrate"] += 1
        state["hydrated_count"] = called["hydrate"]
        return state

    def scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["scan"] += 1
        state["scan_count"] = called["scan"]
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        if int(state.get("scan_count") or 0) < 2:
            state["decision"] = "retry_scan"
        else:
            state["decision"] = "noop"
        return state

    out = run_trading_graph(
        {"use_skill_hydration": True, "candidates": [{"symbol": "AAA"}]},
        strategist=_noop,
        hydrate=hydrate,
        scanner=scanner,
        monitor=_noop,
        decide=decide,
    )
    assert called["scan"] == 2
    assert called["hydrate"] == 2
    assert out["hydrated_count"] == 2


def test_m22_6_graph_hydrates_when_skill_runner_exists():
    called = {"hydrate": 0}

    class _DummyRunner:
        def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> Dict[str, Any]:
            return {"result": {"action": "ready", "data": {}}}

    def hydrate(state: Dict[str, Any]) -> Dict[str, Any]:
        called["hydrate"] += 1
        state["skill_fetch"] = {"used_runner": True}
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "noop"
        return state

    out = run_trading_graph(
        {"skill_runner": _DummyRunner(), "candidates": [{"symbol": "AAA"}]},
        strategist=_noop,
        hydrate=hydrate,
        scanner=_noop,
        monitor=_noop,
        decide=decide,
    )
    assert called["hydrate"] == 1
    assert out["skill_fetch"]["used_runner"] is True


def test_m22_6_graph_hydration_demo_outputs_fetch_summary(capsys):
    rc = graph_demo_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["skill_fetch"]["used_runner"] is True
    assert obj["skill_fetch"]["errors_total"] == 0
    assert obj["scanner_skill"]["used"] is True


def test_m22_6_graph_hydration_demo_timeout_mode(capsys):
    rc = graph_demo_main(["--simulate-timeout", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["skill_fetch"]["errors_total"] >= 1
    assert obj["scanner_skill"]["fallback"] is True
    assert obj["monitor"]["order_status_fallback"] is True
