from __future__ import annotations

import libs.ai.providers.openai_provider as prov
from graphs.nodes.decide_trade import decide_trade


def test_m23_3_runtime_circuit_blocks_second_call_and_skips_provider(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/m23-runtime-cb")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "0")
    monkeypatch.delenv("AI_STRATEGIST_CB_FAIL_THRESHOLD", raising=False)
    monkeypatch.delenv("AI_STRATEGIST_CB_COOLDOWN_SEC", raising=False)
    monkeypatch.setenv("RUNTIME_CB_FAIL_THRESHOLD", "1")
    monkeypatch.setenv("RUNTIME_CB_COOLDOWN_SEC", "60")

    # isolate provider-level breaker; M23-3 test focuses on runtime-level circuit.
    prov.OpenAIStrategist._CB_STATE.clear()

    calls = {"n": 0}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        raise TimeoutError("timeout")

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }

    out1 = decide_trade(state)
    reason1 = str((out1.get("decision_trace") or {}).get("raw_intent", {}).get("reason") or "")
    strategy1 = str((out1.get("decision_trace") or {}).get("strategy") or "")
    out2 = decide_trade(state)
    reason2 = str((out2.get("decision_trace") or {}).get("raw_intent", {}).get("reason") or "")

    assert strategy1 == "OpenAIStrategist"
    assert reason1 == "strategist_error"
    assert reason2 == "circuit_open"
    assert calls["n"] == 1
    assert state["circuit"]["strategist"]["state"] == "open"
    assert int(state["circuit"]["strategist"]["fail_count"]) >= 1


def test_m23_3_runtime_circuit_half_open_success_closes_state(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/m23-runtime-half-open")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "0")
    monkeypatch.delenv("AI_STRATEGIST_CB_FAIL_THRESHOLD", raising=False)
    monkeypatch.delenv("AI_STRATEGIST_CB_COOLDOWN_SEC", raising=False)
    monkeypatch.setenv("RUNTIME_CB_FAIL_THRESHOLD", "1")
    monkeypatch.setenv("RUNTIME_CB_COOLDOWN_SEC", "60")

    prov.OpenAIStrategist._CB_STATE.clear()

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
            "rationale": "recovered",
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
        "circuit": {
            "strategist": {
                "state": "open",
                "fail_count": 3,
                "open_until_epoch": 1,
                "last_error_type": "TimeoutError",
            }
        },
    }

    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "OpenAIStrategist"
    assert out["decision_packet"]["intent"]["action"] == "BUY"
    assert state["circuit"]["strategist"]["state"] == "closed"
    assert int(state["circuit"]["strategist"]["fail_count"]) == 0
    assert int(state["circuit"]["strategist"]["open_until_epoch"]) == 0
