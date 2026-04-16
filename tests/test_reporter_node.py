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


def test_reporter_node_defaults_to_single_trade_mode(monkeypatch) -> None:
    monkeypatch.delenv("INTRADAY_REPORT_RUNTIME_MODE", raising=False)
    called = {"single": 0}

    def _fake_trade_id(state, *, root=None):  # type: ignore[no-untyped-def]
        assert state["run_id"] == "run-1"
        return "TRD_20260415_005930_01"

    def _fake_single(trade_id, *, state, root=None):  # type: ignore[no-untyped-def]
        called["single"] += 1
        assert trade_id == "TRD_20260415_005930_01"
        assert state["run_id"] == "run-1"
        return {"ok": True, "status": "ok", "trade_id": trade_id}

    monkeypatch.setattr(mod, "build_single_trade_report_id", _fake_trade_id)
    monkeypatch.setattr(mod, "generate_single_trade_report", _fake_single)

    out = mod.reporter_node(_state())
    assert called["single"] == 1
    assert out["report_runtime_mode"] == "single_trade"
    assert out["bundle_used"] is False
    assert out["status"] == "ok"


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


def test_commander_runtime_uses_reporter_node_and_keeps_intraday_bundle_reference() -> None:
    source = Path("graphs/commander_runtime.py").read_text(encoding="utf-8")
    assert "from graphs.nodes.reporter_node import reporter_node" in source
    assert "state = _emit_intraday_trade_report(state)" in source
