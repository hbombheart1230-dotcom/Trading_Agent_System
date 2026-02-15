from __future__ import annotations

import libs.ai.providers.openai_provider as prov


def test_m20_1_from_env_reads_timeout_and_max_tokens(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "k")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "gpt-test")
    monkeypatch.setenv("AI_STRATEGIST_TIMEOUT_SEC", "7.5")
    monkeypatch.setenv("AI_STRATEGIST_MAX_TOKENS", "256")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "3")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_BACKOFF_SEC", "0.25")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_VERSION", "pv-test")
    monkeypatch.setenv("AI_STRATEGIST_SCHEMA_VERSION", "intent.v1-test")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_COST_PER_1K_USD", "0.003")
    monkeypatch.setenv("AI_STRATEGIST_COMPLETION_COST_PER_1K_USD", "0.015")
    monkeypatch.setenv("AI_STRATEGIST_CB_FAIL_THRESHOLD", "4")
    monkeypatch.setenv("AI_STRATEGIST_CB_COOLDOWN_SEC", "90")

    s = prov.OpenAIStrategist.from_env()
    assert s.api_key == "k"
    assert s.endpoint == "https://example.invalid/strategist"
    assert s.model == "gpt-test"
    assert abs(float(s.timeout_sec) - 7.5) < 1e-9
    assert s.max_tokens == 256
    assert s.retry_max == 3
    assert abs(float(s.retry_backoff_sec) - 0.25) < 1e-9
    assert s.prompt_version == "pv-test"
    assert s.schema_version == "intent.v1-test"
    assert abs(float(s.prompt_cost_per_1k_usd) - 0.003) < 1e-12
    assert abs(float(s.completion_cost_per_1k_usd) - 0.015) < 1e-12
    assert s.cb_fail_threshold == 4
    assert abs(float(s.cb_cooldown_sec) - 90.0) < 1e-9


def test_m20_1_decide_posts_payload_and_parses_response(monkeypatch):
    captured = {}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["payload"] = dict(payload)
        captured["timeout"] = timeout
        return {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
            },
            "rationale": "llm-ok",
            "meta": {"provider": "fake"},
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist",
        model="gpt-test",
        timeout_sec=9.0,
        max_tokens=128,
        prompt_version="pv-unit",
        schema_version="intent.v1-unit",
        prompt_cost_per_1k_usd=0.003,
        completion_cost_per_1k_usd=0.015,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)

    assert d.intent["action"] == "BUY"
    assert d.rationale == "llm-ok"
    assert d.meta["provider"] == "fake"
    assert d.meta["prompt_version"] == "pv-unit"
    assert d.meta["schema_version"] == "intent.v1-unit"
    assert d.meta["prompt_tokens"] == 100
    assert d.meta["completion_tokens"] == 50
    assert d.meta["total_tokens"] == 150
    assert abs(float(d.meta["estimated_cost_usd"]) - 0.00105) < 1e-12

    assert captured["url"] == "https://example.invalid/strategist"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["payload"]["model"] == "gpt-test"
    assert captured["payload"]["input"]["symbol"] == "005930"
    assert captured["payload"]["max_tokens"] == 128
    assert abs(float(captured["timeout"]) - 9.0) < 1e-9


def test_m20_1_decide_timeout_returns_safe_noop(monkeypatch):
    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        raise TimeoutError("timed out")

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(api_key="k", endpoint="https://example.invalid/strategist")
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "NOOP"
    assert d.intent["reason"] == "strategist_error"
    assert "timed out" in d.rationale
    assert "error" in d.meta


def test_m20_1_decide_invalid_intent_shape_returns_safe_noop(monkeypatch):
    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {"intent": "BUY", "rationale": "bad-shape"}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(api_key="k", endpoint="https://example.invalid/strategist")
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "NOOP"
    assert d.intent["reason"] == "strategist_error"
    assert "intent" in d.rationale.lower()


def test_m20_1_decide_missing_config_returns_safe_noop():
    s = prov.OpenAIStrategist(api_key="", endpoint="")
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "NOOP"
    assert d.intent["reason"] == "missing_config"


def test_m20_1_retry_then_success(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("temporary")
        return {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
            }
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)
    monkeypatch.setattr(prov.time, "sleep", lambda s: sleeps.append(float(s)))

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist",
        retry_max=2,
        retry_backoff_sec=0.1,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "BUY"
    assert calls["n"] == 2
    assert sleeps == [0.1]
    assert d.meta["attempts"] == 2


def test_m20_1_intent_is_schema_normalized(monkeypatch):
    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {
            "intent": {
                "action": "BUY",
                "qty": "2",
                "order_type": "market",
            },
            "rationale": "raw-intent",
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist",
        model="gpt-test",
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "BUY"
    assert d.intent["symbol"] == "005930"
    assert d.intent["qty"] == 2
    assert d.intent["order_type"] == "market"
    assert d.intent["order_api_id"] == "ORDER_SUBMIT"


def test_m20_1_usage_total_tokens_is_derived_when_missing(monkeypatch):
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
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist",
        prompt_cost_per_1k_usd=0.002,
        completion_cost_per_1k_usd=0.004,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.meta["prompt_tokens"] == 10
    assert d.meta["completion_tokens"] == 5
    assert d.meta["total_tokens"] == 15
    assert abs(float(d.meta["estimated_cost_usd"]) - 0.00004) < 1e-12


def test_m20_1_cost_not_emitted_when_usage_missing(monkeypatch):
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

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist",
        prompt_cost_per_1k_usd=0.003,
        completion_cost_per_1k_usd=0.015,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert "estimated_cost_usd" not in d.meta


def test_m20_1_openrouter_chat_content_json_is_adapted(monkeypatch):
    captured = {}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        captured["payload"] = dict(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "```json\n"
                            "{\"intent\":{\"action\":\"BUY\",\"symbol\":\"005930\",\"qty\":1,"
                            "\"price\":70000,\"order_type\":\"limit\",\"order_api_id\":\"ORDER_SUBMIT\"},"
                            "\"rationale\":\"adapter-ok\"}\n"
                            "```"
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)
    monkeypatch.setenv("OPENROUTER_MODEL_STRATEGIST", "anthropic/claude-3.5-sonnet")

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        model="gpt-4.1-mini",  # non openrouter-style; adapter should switch from env
        timeout_sec=9.0,
        max_tokens=128,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "BUY"
    assert d.intent["symbol"] == "005930"
    assert d.rationale == "adapter-ok"

    assert "messages" in captured["payload"]
    assert "input" not in captured["payload"]
    assert captured["payload"]["model"] == "anthropic/claude-3.5-sonnet"
    assert captured["payload"]["max_tokens"] == 128


def test_m20_1_openrouter_chat_content_without_json_is_safe_noop(monkeypatch):
    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {
            "choices": [
                {
                    "message": {
                        "content": "I cannot comply."
                    }
                }
            ]
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        model="anthropic/claude-3.5-sonnet",
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d = s.decide(x)
    assert d.intent["action"] == "NOOP"
    assert d.intent["reason"] == "strategist_error"
    assert "json" in d.rationale.lower()


def test_m20_1_circuit_breaker_opens_and_blocks_following_call(monkeypatch):
    calls = {"n": 0}
    now = {"t": 1000.0}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        raise TimeoutError("cb-timeout")

    monkeypatch.setattr(prov, "_post_json", fake_post_json)
    monkeypatch.setattr(prov.time, "time", lambda: now["t"])

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist-cb-open",
        retry_max=0,
        cb_fail_threshold=2,
        cb_cooldown_sec=60,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d1 = s.decide(x)
    d2 = s.decide(x)
    d3 = s.decide(x)

    assert d1.intent["reason"] == "strategist_error"
    assert d2.intent["reason"] == "strategist_error"
    assert d3.intent["reason"] == "circuit_open"
    assert d3.meta["error_type"] == "CircuitOpen"
    assert d3.meta["circuit_state"] == "open"
    assert int(d3.meta["circuit_fail_count"]) >= 2
    assert int(d3.meta["circuit_open_until_epoch"]) > int(now["t"])
    assert calls["n"] == 2


def test_m20_1_circuit_breaker_recovers_after_cooldown(monkeypatch):
    calls = {"n": 0}
    now = {"t": 2000.0}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("cb-timeout")
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
    monkeypatch.setattr(prov.time, "time", lambda: now["t"])

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist-cb-recover",
        retry_max=0,
        cb_fail_threshold=1,
        cb_cooldown_sec=10,
    )
    x = prov.StrategyInput(
        symbol="005930",
        market_snapshot={"symbol": "005930", "price": 70000},
        portfolio_snapshot={"cash": 2_000_000, "open_positions": 0},
        risk_context={"open_positions": 0},
    )

    d1 = s.decide(x)
    d2 = s.decide(x)
    assert d1.intent["reason"] == "strategist_error"
    assert d2.intent["reason"] == "circuit_open"
    assert calls["n"] == 1

    now["t"] = now["t"] + 11.0
    d3 = s.decide(x)
    assert d3.intent["action"] == "BUY"
    assert calls["n"] == 2
