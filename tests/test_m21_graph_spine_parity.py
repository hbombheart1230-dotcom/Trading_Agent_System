from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime
from graphs.trading_graph import run_trading_graph


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


def test_m21_graph_spine_parity_for_approve_path():
    def strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategy"] = "rule"
        return state

    def scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["candidate"] = "005930"
        state["scan_calls"] = int(state.get("scan_calls", 0)) + 1
        return state

    def monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["monitor_ok"] = True
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "approve"
        return state

    def executor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["execution_pending"] = True
        return state

    base = {"x": 1}
    legacy = run_trading_graph(
        deepcopy(base),
        strategist=strategist,
        scanner=scanner,
        monitor=monitor,
        decide=decide,
        executor=executor,
    )
    canonical = run_commander_runtime(
        {"x": 1, "event_logger": _NoopLogger()},
        mode="graph_spine",
        graph_runner=lambda s: run_trading_graph(
            s,
            strategist=strategist,
            scanner=scanner,
            monitor=monitor,
            decide=decide,
            executor=executor,
        ),
    )

    assert canonical["strategy"] == legacy["strategy"]
    assert canonical["candidate"] == legacy["candidate"]
    assert canonical["monitor_ok"] == legacy["monitor_ok"]
    assert canonical["decision"] == legacy["decision"]
    assert canonical["execution_pending"] == legacy["execution_pending"]
    assert canonical["scan_calls"] == legacy["scan_calls"]


def test_m21_graph_spine_parity_for_retry_scan_path():
    def strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategy"] = "rule"
        return state

    def scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["scan_calls"] = int(state.get("scan_calls", 0)) + 1
        return state

    def monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["monitor_calls"] = int(state.get("monitor_calls", 0)) + 1
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        if int(state.get("scan_calls", 0)) < 2:
            state["decision"] = "retry_scan"
        else:
            state["decision"] = "approve"
        return state

    def executor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["execution_pending"] = True
        return state

    base = {"x": 1}
    legacy = run_trading_graph(
        deepcopy(base),
        strategist=strategist,
        scanner=scanner,
        monitor=monitor,
        decide=decide,
        executor=executor,
    )
    canonical = run_commander_runtime(
        {"x": 1, "event_logger": _NoopLogger()},
        mode="graph_spine",
        graph_runner=lambda s: run_trading_graph(
            s,
            strategist=strategist,
            scanner=scanner,
            monitor=monitor,
            decide=decide,
            executor=executor,
        ),
    )

    assert canonical["strategy"] == legacy["strategy"]
    assert canonical["scan_calls"] == legacy["scan_calls"] == 2
    assert canonical["monitor_calls"] == legacy["monitor_calls"] == 2
    assert canonical["decision"] == legacy["decision"] == "approve"
    assert canonical["execution_pending"] == legacy["execution_pending"] is True
