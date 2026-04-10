from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
import libs.ai.providers.openai_provider as prov
from graphs.nodes.decide_trade import decide_trade


@pytest.fixture(autouse=True)
def _disable_strategy_v1(monkeypatch):
    monkeypatch.setenv("USE_STRATEGY_V1", "false")


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


def test_m20_2_decide_trade_injects_feature_news_context_to_llm_input(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")

    captured = {}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        captured["payload"] = dict(payload)
        return {"intent": {"action": "NOOP", "reason": "model_no_signal"}, "rationale": "hold"}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 61.2,
                    "ma20_gap": 0.015,
                    "atr14": 650.0,
                    "volume_spike20": 1.3,
                    "volatility20": 0.02,
                    "regime": "trend",
                    "signal_score": 0.7,
                }
            }
        },
        "news_sentiment": {"005930": 0.2},
        "global_sentiment": {"score": 0.1},
    }
    out = decide_trade(state)

    input_obj = captured["payload"]["input"]
    llm_ctx = input_obj["market_snapshot"]["llm_context"]
    assert llm_ctx["technical"]["regime"] == "trend"
    assert abs(float(llm_ctx["technical"]["signal_score"]) - 0.7) < 1e-12
    assert abs(float(llm_ctx["news"]["symbol_sentiment_score"]) - 0.2) < 1e-12
    assert abs(float(llm_ctx["news"]["global_sentiment_score"]) - 0.1) < 1e-12
    assert abs(float(input_obj["risk_context"]["llm_context"]["global_sentiment_score"]) - 0.1) < 1e-12
    assert out["decision_trace"]["llm_context"]["technical"]["regime"] == "trend"


def test_m20_2_decide_trade_llm_context_defaults_when_features_missing(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")

    captured = {}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        captured["payload"] = dict(payload)
        return {"intent": {"action": "NOOP", "reason": "model_no_signal"}, "rationale": "hold"}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    llm_ctx = captured["payload"]["input"]["market_snapshot"]["llm_context"]
    assert llm_ctx["technical"]["regime"] == "unknown"
    assert abs(float(llm_ctx["technical"]["rsi14"]) - 50.0) < 1e-12
    assert abs(float(llm_ctx["technical"]["signal_score"]) - 0.0) < 1e-12
    assert abs(float(llm_ctx["news"]["symbol_sentiment_score"]) - 0.0) < 1e-12
    assert abs(float(llm_ctx["news"]["global_sentiment_score"]) - 0.0) < 1e-12
    assert out["decision_trace"]["llm_context"]["technical"]["regime"] == "unknown"


def test_m20_2_decide_trade_propagates_signal_status_into_llm_context(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")

    captured = {}

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        captured["payload"] = dict(payload)
        return {"intent": {"action": "NOOP", "reason": "model_no_signal"}, "rationale": "hold"}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
        "feature_engine": {"by_symbol": {"005930": {"regime": "trend", "signal_score": 0.2}}},
        "news_sentiment_signal": {
            "005930": {
                "score": 0.0,
                "status": "unavailable",
                "source": "scorer:openrouter",
                "reason": "scorer_error:TimeoutError",
                "ts": 1000,
            }
        },
        "global_sentiment_signal": {
            "score": 0.0,
            "status": "fallback",
            "source": "dry_run_policy",
            "reason": "dry_run_neutral",
            "ts": 1000,
        },
    }
    out = decide_trade(state)

    llm_ctx = captured["payload"]["input"]["market_snapshot"]["llm_context"]
    risk_llm_ctx = captured["payload"]["input"]["risk_context"]["llm_context"]

    assert llm_ctx["news"]["symbol_sentiment_status"] == "unavailable"
    assert llm_ctx["news"]["global_sentiment_status"] == "fallback"
    assert risk_llm_ctx["symbol_sentiment_status"] == "unavailable"
    assert risk_llm_ctx["global_sentiment_status"] == "fallback"
    assert out["decision_trace"]["llm_context"]["news"]["symbol_sentiment_source"] == "scorer:openrouter"


def test_m20_2_decide_trade_openai_buy_without_rationale_is_forced_noop(monkeypatch):
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
            }
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "OpenAIStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "missing_rationale"


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


def test_m20_2_decide_trade_non_openai_exception_returns_safe_noop():
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

    assert out["decision_trace"]["strategy"] == "BrokenStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "strategist_error"


def test_m20_2_decide_trade_ignores_strategy_v1_runtime_when_ai_strategist_provider_openai(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("USE_STRATEGY_V1", "true")

    import libs.strategies.v1.registry as registry

    called = {"v1": 0}

    def fake_resolve_strategy_v1_name(policy, llm_context):  # type: ignore[no-untyped-def]
        called["v1"] += 1
        return "fake_v1"

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {"intent": {"action": "NOOP", "reason": "model_no_signal"}, "rationale": "llm-hold"}

    monkeypatch.setattr(registry, "resolve_strategy_v1_name", fake_resolve_strategy_v1_name)
    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
    }
    out = decide_trade(state)

    assert called["v1"] == 0
    assert out["decision_trace"]["strategy"] == "OpenAIStrategist"
    assert out["decision_trace"]["decision_source"] == "llm"


def test_m20_2_decide_trade_blocks_buy_when_position_already_open(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

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
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")

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


def test_m20_2_decide_trade_stop_take_env_are_fallback_only(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")

    class AlwaysBuyStrategist:
        def decide(self, x):  # type: ignore[no-untyped-def]
            class Decision:
                intent = {
                    "action": "BUY",
                    "symbol": "005930",
                    "qty": 1,
                    "price": 103.0,
                    "order_type": "limit",
                    "order_api_id": "ORDER_SUBMIT",
                }
                rationale = "always-buy"
                meta = {}

            return Decision()

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 103.0},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0}],
            "open_positions": 1,
        },
        "policy": {
            "use_exit_policy": True,
            "exit_policy": {
                "take_profit_pct": 0.05,
                "stop_loss_pct": 0.05,
            },
        },
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "strategist": AlwaysBuyStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "position_hold"


def test_m20_2_decide_trade_exit_policy_crosschecks_account_unrealized_pnl(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")

    class AlwaysBuyStrategist:
        def decide(self, x):  # type: ignore[no-untyped-def]
            class Decision:
                intent = {
                    "action": "BUY",
                    "symbol": "005930",
                    "qty": 1,
                    "price": 97.0,
                    "order_type": "limit",
                    "order_api_id": "ORDER_SUBMIT",
                }
                rationale = "always-buy"
                meta = {}

            return Decision()

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 97.0},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [
                {
                    "symbol": "005930",
                    "qty": 1,
                    "avg_price": 100.0,
                    "current_price": 97.0,
                    "unrealized_pnl": -4.5,
                }
            ],
            "open_positions": 1,
        },
        "policy": {
            "use_exit_policy": True,
            "exit_policy": {
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
        },
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "strategist": AlwaysBuyStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "ExitPolicyStrategist"
    assert out["decision_packet"]["intent"]["action"] == "SELL"
    exit_decision = dict(out["decision_trace"].get("exit_policy_decision") or {})
    assert float(exit_decision.get("raw_price") or 0.0) == 97.0
    assert float(exit_decision.get("effective_price") or 0.0) == 95.5
    assert round(float(exit_decision.get("pnl_ratio") or 0.0), 4) == -0.045
    assert exit_decision.get("pnl_crosscheck_applied") is True


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


def test_m20_2_decide_trade_exit_policy_max_hold_triggers_sell(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setattr(time, "time", lambda: 2000.0)

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
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "applied_policy": {
            "monitor": {
                "hold": {"min_hold_seconds": 0},
            },
            "execution": {
                "cooldowns": {"sell_sec": 0},
            },
        },
        "persisted_state": {"last_trade_side": "BUY", "last_trade_epoch": 1900},
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "strategist": AlwaysBuyStrategist(),
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "ExitPolicyStrategist"
    assert out["decision_packet"]["intent"]["action"] == "SELL"
    assert out["decision_packet"]["intent"]["qty"] == 2
    assert out["decision_packet"]["intent"]["rationale"] == "exit_policy:max_hold"


def test_m20_2_decide_trade_blocks_fast_sell_with_min_hold_guard(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "1")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setattr(time, "time", lambda: 2000.0)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "persisted_state": {"last_trade_side": "BUY", "last_trade_epoch": 1950},
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
    }
    out = decide_trade(state)

    intent = out["decision_packet"]["intent"]
    assert out["decision_trace"]["strategy"] == "ExitPolicyStrategist"
    assert intent["action"] == "NOOP"
    assert intent["reason"] == "sell_guard_min_hold"
    assert "sell_guard_min_hold" in str(intent.get("rationale") or "")
    assert intent["signal_source"] == "ExitPolicyStrategist"
    assert int(intent["position_age_sec"]) == 50
    assert intent["intent_id"] == out["run_id"]
    assert out["decision_trace"]["sell_timing_guard"]["blocked"] is True


def test_m20_2_decide_trade_hard_stop_bypasses_sell_timing_guard(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setattr(time, "time", lambda: 2000.0)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 68000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "persisted_state": {"last_trade_side": "BUY", "last_trade_epoch": 1950},
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "policy": {"use_exit_policy": True, "hard_stop_pct": 0.02, "stop_loss_pct": 0.08},
    }
    out = decide_trade(state)

    intent = out["decision_packet"]["intent"]
    assert intent["action"] == "SELL"
    assert intent["rationale"] == "exit_policy:hard_stop"
    assert out["decision_trace"]["sell_timing_guard"]["blocked"] is False


def test_m20_2_decide_trade_does_not_convert_noop_to_buy_via_env_thresholds(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {"intent": {"action": "NOOP", "reason": "model_no_signal"}, "rationale": "hold"}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 55.0,
                    "ma20_gap": 0.015,
                    "atr14": 650.0,
                    "volume_spike20": 1.3,
                    "volatility20": 0.05,
                    "regime": "high_volatility",
                    "signal_score": 0.2,
                }
            }
        },
        "news_sentiment": {"005930": 0.0},
        "global_sentiment": {"score": 0.0},
    }
    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_trace"]["score_override_applied"] is False


def test_m20_2_decide_trade_strategy_policy_thresholds_do_not_override_llm_noop(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {"intent": {"action": "NOOP", "reason": "model_no_signal"}, "rationale": "hold"}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 55.0,
                    "ma20_gap": 0.015,
                    "atr14": 650.0,
                    "volume_spike20": 1.3,
                    "volatility20": 0.05,
                    "regime": "high_volatility",
                    "signal_score": 0.2,
                }
            }
        },
        "news_sentiment": {"005930": 0.0},
        "global_sentiment": {"score": 0.0},
        "strategist_output": {
            "strategy_policy": {
                "decision_policy": {
                    "use_strategy_v1_engine": False,
                    "allow_score_override": True,
                    "buy_threshold": 0.05,
                    "high_vol_abs_threshold": 0.06,
                }
            }
        },
    }
    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_trace"]["score_override_applied"] is False
    why = out["decision_packet"]["why"]
    assert float((why.get("policy") or {}).get("buy_threshold") or 0.0) == 0.05


def test_m20_2_decide_trade_score_override_does_not_override_strategy_v1_noop(monkeypatch):
    from libs.strategies.contracts import StrategyDecision
    import libs.strategies.v1.registry as registry

    class FakeV1:
        def decide(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return StrategyDecision(
                action="NOOP",
                symbol="005930",
                rationale="v1-noop",
            )

    monkeypatch.setattr(registry, "resolve_strategy_v1_name", lambda policy, llm_context: "fake_v1")
    monkeypatch.setattr(registry, "build_strategy_v1", lambda name, policy: (FakeV1(), "fake_v1"))

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2_000_000, "open_positions": 0},
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 55.0,
                    "ma20_gap": 0.015,
                    "atr14": 650.0,
                    "volume_spike20": 1.3,
                    "volatility20": 0.05,
                    "regime": "high_volatility",
                    "signal_score": 0.2,
                }
            }
        },
        "news_sentiment": {"005930": 0.0},
        "global_sentiment": {"score": 0.0},
        "strategist_output": {
            "strategy_policy": {
                "decision_policy": {
                    "use_strategy_v1_engine": True,
                    "allow_score_override": True,
                    "score_override_scope": "llm_only",
                    "buy_threshold": 0.05,
                    "high_vol_abs_threshold": 0.06,
                    "strategy_v1_name": "fake_v1",
                }
            }
        },
    }

    out = decide_trade(state)

    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_trace"]["score_override_applied"] is False
    assert out["decision_trace"]["decision_source"] == "strategy_v1"


def test_m20_2_decide_trade_eod_force_liquidation_emits_sell(monkeypatch):
    monkeypatch.setenv("USE_EOD_FORCE_LIQUIDATION", "true")
    monkeypatch.setenv("EOD_FORCE_LIQUIDATION_START_HHMM", "1520")
    monkeypatch.setenv("EOD_FORCE_LIQUIDATION_END_HHMM", "1530")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

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

    kst = timezone(timedelta(hours=9))
    tick_ts = int(datetime(2026, 2, 13, 15, 25, tzinfo=kst).timestamp())
    state = {
        "symbol": "005930",
        "tick_ts": tick_ts,
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 16, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "strategist": AlwaysBuyStrategist(),
    }

    out = decide_trade(state)
    assert out["decision_trace"]["strategy"] == "EODLiquidationStrategist"
    assert out["decision_packet"]["intent"]["action"] == "SELL"
    assert out["decision_packet"]["intent"]["symbol"] == "005930"
    assert out["decision_packet"]["intent"]["qty"] == 16
    assert str(out["decision_packet"]["intent"]["rationale"]).startswith("eod_force_liquidation:")


def test_m20_2_decide_trade_exit_policy_news_shock_triggers_sell(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "0.25")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 3, "avg_price": 69000.0}],
            "open_positions": 1,
        },
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
        "news_sentiment_signal": {
            "005930": {
                "score": -0.50,
                "status": "ok",
                "source": "test",
                "reason": "fixture",
                "ts": 1772812800,
            }
        },
        "global_sentiment_signal": {
            "score": -0.10,
            "status": "ok",
            "source": "test",
            "reason": "fixture",
            "ts": 1772812800,
        },
    }
    out = decide_trade(state)
    assert out["decision_trace"]["strategy"] == "ExitPolicyStrategist"
    assert out["decision_packet"]["intent"]["action"] == "SELL"
    assert out["decision_packet"]["intent"]["qty"] == 3
    assert out["decision_packet"]["intent"]["rationale"] == "exit_policy:news_shock"
