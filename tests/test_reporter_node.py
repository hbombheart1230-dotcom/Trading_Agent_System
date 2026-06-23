from __future__ import annotations

from pathlib import Path

import graphs.nodes.reporter_node as mod


def _state() -> dict:
    return {
        "run_id": "run-1",
        "day": "2026-04-15",
        "symbol": "005930",
        "execution": {
            "ok": True,
            "order": {"action": "SELL", "symbol": "005930", "qty": 1},
        },
    }


def test_reporter_node_defaults_to_bundle_mode(monkeypatch) -> None:
    monkeypatch.delenv("INTRADAY_REPORT_RUNTIME_MODE", raising=False)
    called = {"bundle": 0}

    def _fake_bundle(state, *, root=None):  # type: ignore[no-untyped-def]
        called["bundle"] += 1
        assert state["run_id"] == "run-1"
        return {"ok": True, "status": "generated", "bundle_used": True}

    monkeypatch.setattr(mod, "generate_intraday_trade_artifacts", _fake_bundle)

    out = mod.reporter_node(_state())
    assert called["bundle"] == 1
    assert out["report_runtime_mode"] == "bundle"
    assert out["bundle_used"] is True
    assert out["status"] == "generated"
    assert out["runtime_mode_forced"] is False


def test_reporter_node_can_use_bundle_mode_when_explicit(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_REPORT_RUNTIME_MODE", "bundle")
    called = {"bundle": 0}

    def _fake_bundle(state, *, root=None):  # type: ignore[no-untyped-def]
        called["bundle"] += 1
        return {"ok": True, "status": "generated", "bundle_used": True}

    monkeypatch.setattr(mod, "generate_intraday_trade_artifacts", _fake_bundle)

    out = mod.reporter_node(_state())
    assert called["bundle"] == 1
    assert out["report_runtime_mode"] == "bundle"
    assert out["bundle_used"] is True
    assert out["status"] == "generated"
    assert out["runtime_mode_forced"] is False


def test_reporter_node_forces_bundle_even_when_single_trade_requested(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_REPORT_RUNTIME_MODE", "single_trade")
    called = {"bundle": 0}

    def _fake_bundle(state, *, root=None):  # type: ignore[no-untyped-def]
        called["bundle"] += 1
        return {"ok": True, "status": "generated", "bundle_used": True}

    monkeypatch.setattr(mod, "generate_intraday_trade_artifacts", _fake_bundle)

    out = mod.reporter_node(_state())
    assert called["bundle"] == 1
    assert out["report_runtime_mode"] == "bundle"
    assert out["requested_report_runtime_mode"] == "single_trade"
    assert out["runtime_mode_forced"] is True


def test_commander_runtime_uses_reporter_node_and_keeps_intraday_bundle_reference() -> None:
    source = Path("graphs/commander_runtime.py").read_text(encoding="utf-8")
    assert "emit_intraday_trade_report" in source
    assert "reporter_node=nodes.reporter_node" in source
    assert "emit_trade_report_fn=_emit_intraday_trade_report" in source
