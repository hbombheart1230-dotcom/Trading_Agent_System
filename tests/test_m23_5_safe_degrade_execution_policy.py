from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from graphs.nodes.execute_from_packet import execute_from_packet


class _AllowSupervisor:
    def allow(self, intent: str, context: Dict[str, Any]):  # type: ignore[no-untyped-def]
        class _R:
            allow = True
            reason = "allowed"

        return _R()


class _SpyExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, req: Any):  # type: ignore[no-untyped-def]
        self.calls += 1

        class _Result:
            payload = {"ok": True}

        return _Result()


def _write_catalog(path: Path) -> Path:
    path.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    return path


def _base_state(catalog_path: Path, *, price: int, exec_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "catalog_path": str(catalog_path),
        "resilience": {"degrade_mode": True},
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": price,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": exec_context or {},
        },
    }


def test_m23_5_degrade_requires_manual_approval(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930")
    monkeypatch.delenv("MAX_ORDER_NOTIONAL", raising=False)

    ex = _SpyExecutor()
    state = _base_state(_write_catalog(tmp_path / "api_catalog.jsonl"), price=70000)
    state["supervisor"] = _AllowSupervisor()
    state["executor"] = ex

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "degrade_manual_approval_required"
    assert ex.calls == 0


def test_m23_5_degrade_requires_non_empty_allowlist(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.delenv("SYMBOL_ALLOWLIST", raising=False)
    monkeypatch.delenv("MAX_ORDER_NOTIONAL", raising=False)

    ex = _SpyExecutor()
    state = _base_state(
        _write_catalog(tmp_path / "api_catalog.jsonl"),
        price=70000,
        exec_context={"manual_approved": True},
    )
    state["supervisor"] = _AllowSupervisor()
    state["executor"] = ex

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "degrade_allowlist_required"
    assert ex.calls == 0


def test_m23_5_degrade_tightens_notional_guard(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "100000")
    monkeypatch.setenv("DEGRADE_NOTIONAL_RATIO", "0.25")

    ex = _SpyExecutor()
    state = _base_state(
        _write_catalog(tmp_path / "api_catalog.jsonl"),
        price=30000,  # qty=1 => 30000 > 25000
        exec_context={"manual_approved": True},
    )
    state["supervisor"] = _AllowSupervisor()
    state["executor"] = ex

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "degrade_notional_limit_exceeded"
    assert out["execution"]["degrade_policy"]["effective_max_notional"] == 25000
    assert ex.calls == 0


def test_m23_5_degrade_allows_execution_when_policy_passes(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "100000")
    monkeypatch.setenv("DEGRADE_NOTIONAL_RATIO", "0.25")

    ex = _SpyExecutor()
    state = _base_state(
        _write_catalog(tmp_path / "api_catalog.jsonl"),
        price=20000,  # qty=1 => 20000 <= 25000
        exec_context={"manual_approved": True},
    )
    state["supervisor"] = _AllowSupervisor()
    state["executor"] = ex

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is True
    assert ex.calls == 1
