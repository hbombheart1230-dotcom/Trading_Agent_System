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

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            }
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
