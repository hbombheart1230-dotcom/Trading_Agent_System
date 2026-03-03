from __future__ import annotations

import time

import libs.ai.providers.openai_provider as prov
from graphs.nodes.decide_trade import decide_trade


def test_m20_2_decide_trade_openai_success(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")

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
            "rationale": "llm-buy",
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "OpenAIStrategist"
    assert out["decision_packet"]["intent"]["action"] == "BUY"
    assert out["decision_packet"]["intent"]["symbol"] == "005930"


def test_m20_2_decide_trade_openai_timeout_is_safe_noop(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        raise TimeoutError("timeout")

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "OpenAIStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_trace"]["raw_intent"]["reason"] == "strategist_error"


def test_m20_2_decide_trade_non_openai_exception_falls_back_to_rule():
    class BrokenStrategist:
        def decide(self, x):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 10_000_000, "open_positions": 0},
        "strategist": BrokenStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "RuleStrategist"
    assert out["decision_packet"]["intent"]["action"] in ("BUY", "NOOP")


def test_m20_2_decide_trade_blocks_buy_when_position_already_open():
    class AlwaysBuyStrategist:
        def decide(self, x):  # type: ignore[no-untyped-def]
            class Decision:
                intent = {
                    "action": "BUY",
                    "symbol": "005930",
                    "qty": 1,
                    "price": 70000,
                    "order_type": "limit",
                    "order_api_id": "ORDER_SUBMIT",
                }
                rationale = "always-buy"
                meta = {}

            return Decision()

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 1, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "strategist": AlwaysBuyStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "position_already_open"


def test_m20_2_decide_trade_exit_policy_triggers_sell(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")

    class AlwaysBuyStrategist:
        def decide(self, x):  # type: ignore[no-untyped-def]
            class Decision:
                intent = {
                    "action": "BUY",
                    "symbol": "005930",
                    "qty": 1,
                    "price": 71000,
                    "order_type": "limit",
                    "order_api_id": "ORDER_SUBMIT",
                }
                rationale = "always-buy"
                meta = {}

            return Decision()

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 71000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "strategist": AlwaysBuyStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "ExitPolicyStrategist"
    assert out["decision_packet"]["intent"]["action"] == "SELL"
    assert out["decision_packet"]["intent"]["qty"] == 2


def test_m20_2_decide_trade_post_exit_cooldown_blocks_reentry(monkeypatch):
    monkeypatch.setenv("POST_EXIT_COOLDOWN_SEC", "300")
    monkeypatch.setattr(time, "time", lambda: 1500.0)

    class AlwaysBuyStrategist:
        def decide(self, x):  # type: ignore[no-untyped-def]
            class Decision:
                intent = {
                    "action": "BUY",
                    "symbol": "005930",
                    "qty": 1,
                    "price": 70000,
                    "order_type": "limit",
                    "order_api_id": "ORDER_SUBMIT",
                }
                rationale = "always-buy"
                meta = {}

            return Decision()

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "positions": [], "open_positions": 0},
        "risk_context": {"open_positions": 0, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "persisted_state": {"last_trade_side": "SELL", "last_trade_epoch": 1400},
        "strategist": AlwaysBuyStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "CooldownStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "post_exit_cooldown"
