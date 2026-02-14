from __future__ import annotations

import libs.ai.providers.openai_provider as prov


def test_m20_1_from_env_reads_timeout_and_max_tokens(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "k")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "gpt-test")
    monkeypatch.setenv("AI_STRATEGIST_TIMEOUT_SEC", "7.5")
    monkeypatch.setenv("AI_STRATEGIST_MAX_TOKENS", "256")

    s = prov.OpenAIStrategist.from_env()
    assert s.api_key == "k"
    assert s.endpoint == "https://example.invalid/strategist"
    assert s.model == "gpt-test"
    assert abs(float(s.timeout_sec) - 7.5) < 1e-9
    assert s.max_tokens == 256


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
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    s = prov.OpenAIStrategist(
        api_key="k",
        endpoint="https://example.invalid/strategist",
        model="gpt-test",
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
    assert d.rationale == "llm-ok"
    assert d.meta["provider"] == "fake"

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
