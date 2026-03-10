from __future__ import annotations

from graphs.nodes.execute_from_packet import execute_from_packet
from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import strategist_node


def test_decision_trace_ledger_collects_strategist_scanner_monitor(monkeypatch):
    monkeypatch.setenv("TOP_N_CANDIDATES", "3")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "run_id": "trace-r1",
        "themes": ["semiconductor", "AI"],
        "candidate_symbols": ["005930", "000660", "042700"],
        "mock_scan_results": {
            "005930": {"score": 0.91, "risk_score": 0.20, "confidence": 0.88},
            "000660": {"score": 0.83, "risk_score": 0.24, "confidence": 0.80},
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "use_universe_builder": False,
            "use_exit_policy": False,
        },
    }

    out = strategist_node(state)
    out = scanner_node(out)
    out = monitor_node(out)

    ledger = out.get("decision_trace_ledger") or {}
    assert ledger.get("run_id") == "trace-r1"
    entries = ledger.get("entries") or []
    agents = {str(x.get("agent") or "") for x in entries if isinstance(x, dict)}
    assert {"strategist", "scanner", "monitor"}.issubset(agents)
    latest = ledger.get("latest_by_agent") or {}
    strategist_payload = latest.get("strategist") if isinstance(latest.get("strategist"), dict) else {}
    assert "market_regime" in strategist_payload
    assert "themes" in strategist_payload
    assert "playbook" in strategist_payload
    assert "scanner_bias" in strategist_payload
    assert "risk_tone" in strategist_payload
    assert "monitor_guidance" in strategist_payload
    assert isinstance(strategist_payload.get("scanner_priority"), list)
    scanner_payload = latest.get("scanner") if isinstance(latest.get("scanner"), dict) else {}
    assert "candidate_pool_size" in scanner_payload
    assert isinstance(scanner_payload.get("top_candidates"), list)
    assert "selected_symbol" in scanner_payload
    assert isinstance(scanner_payload.get("score_breakdown_summary"), dict)
    monitor_payload = latest.get("monitor") if isinstance(latest.get("monitor"), dict) else {}
    assert "entry_reason" in monitor_payload
    assert "exit_reason" in monitor_payload
    assert "min_hold_blocked" in monitor_payload
    assert "sell_cooldown_blocked" in monitor_payload
    assert "monitor_reason" in monitor_payload


def test_decision_trace_ledger_collects_supervisor_and_executor(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.delenv("SYMBOL_ALLOWLIST", raising=False)

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "run_id": "trace-r2",
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    ledger = out.get("decision_trace_ledger") or {}
    latest = ledger.get("latest_by_agent") or {}
    assert "supervisor" in latest
    assert "executor" in latest
    assert latest["executor"]["execution_attempted"] is True
    assert str((latest["supervisor"] or {}).get("verdict") or "") in ("approve", "reject")
