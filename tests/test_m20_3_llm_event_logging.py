from __future__ import annotations

import json
from pathlib import Path

import libs.ai.providers.openai_provider as prov
from graphs.nodes.decide_trade import decide_trade


def _load_events(path: Path):
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def test_m20_3_llm_event_logged_on_success(monkeypatch, tmp_path: Path):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "0")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_VERSION", "pv-log")
    monkeypatch.setenv("AI_STRATEGIST_SCHEMA_VERSION", "intent.v1-log")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_COST_PER_1K_USD", "0.003")
    monkeypatch.setenv("AI_STRATEGIST_COMPLETION_COST_PER_1K_USD", "0.015")

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "BUY"
    rows = _load_events(events)
    llm = [r for r in rows if r.get("stage") == "strategist_llm" and r.get("event") == "result"]
    assert llm
    p = llm[-1].get("payload") or {}
    assert p.get("strategy") == "OpenAIStrategist"
    assert p.get("ok") is True
    assert p.get("intent_action") == "BUY"
    assert isinstance(p.get("latency_ms"), int)
    assert p.get("attempts") == 1
    assert p.get("prompt_version") == "pv-log"
    assert p.get("schema_version") == "intent.v1-log"
    assert p.get("prompt_tokens") == 120
    assert p.get("completion_tokens") == 80
    assert p.get("total_tokens") == 200
    assert abs(float(p.get("estimated_cost_usd") or 0.0) - 0.00156) < 1e-12


def test_m20_3_llm_event_logged_on_error(monkeypatch, tmp_path: Path):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "0")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_BACKOFF_SEC", "0")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_VERSION", "pv-log")
    monkeypatch.setenv("AI_STRATEGIST_SCHEMA_VERSION", "intent.v1-log")

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        raise TimeoutError("timeout")

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    rows = _load_events(events)
    llm = [r for r in rows if r.get("stage") == "strategist_llm" and r.get("event") == "result"]
    assert llm
    p = llm[-1].get("payload") or {}
    assert p.get("strategy") == "OpenAIStrategist"
    assert p.get("ok") is False
    assert p.get("intent_action") == "NOOP"
    assert p.get("intent_reason") == "strategist_error"
    assert p.get("error_type") in ("TimeoutError", "Exception")
    assert p.get("prompt_version") == "pv-log"
    assert p.get("schema_version") == "intent.v1-log"


def test_m20_9_llm_event_logs_circuit_breaker_fields(monkeypatch, tmp_path: Path):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist-cb-event")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "0")
    monkeypatch.setenv("AI_STRATEGIST_CB_FAIL_THRESHOLD", "1")
    monkeypatch.setenv("AI_STRATEGIST_CB_COOLDOWN_SEC", "60")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_VERSION", "pv-log")
    monkeypatch.setenv("AI_STRATEGIST_SCHEMA_VERSION", "intent.v1-log")
    monkeypatch.setattr(prov.time, "time", lambda: 1000.0)

    # isolate breaker state for this test
    prov.OpenAIStrategist._CB_STATE.clear()

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        raise TimeoutError("timeout")

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }

    # 1st call: strategist_error + breaker open
    out1 = decide_trade(dict(state))
    assert out1["decision_packet"]["intent"]["action"] == "NOOP"

    # 2nd call: circuit_open short-circuit
    out2 = decide_trade(dict(state))
    assert out2["decision_packet"]["intent"]["action"] == "NOOP"

    rows = _load_events(events)
    llm = [r for r in rows if r.get("stage") == "strategist_llm" and r.get("event") == "result"]
    assert len(llm) >= 2
    p = llm[-1].get("payload") or {}

    assert p.get("error_type") == "CircuitOpen"
    assert p.get("intent_reason") == "circuit_open"
    assert p.get("circuit_state") == "open"
    assert int(p.get("circuit_fail_count") or 0) >= 1
    assert int(p.get("circuit_open_until_epoch") or 0) > 1000
