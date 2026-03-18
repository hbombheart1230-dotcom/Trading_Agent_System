from __future__ import annotations

from graphs.nodes.decide_trade import (
    _build_strategy_policy_packet_summary,
    _policy_thresholds,
    _score_override_enabled,
    _score_override_scope,
    _score_override_scope_allows,
    _strategy_v1_enabled,
)


def test_strategy_policy_decision_policy_controls_strategy_v1() -> None:
    state = {
        "strategist_output": {
            "strategy_policy": {
                "decision_policy": {
                    "use_strategy_v1_engine": True,
                }
            }
        },
        "policy": {
            "use_strategy_v1": False,
        },
    }

    assert _strategy_v1_enabled(state) is True


def test_strategy_policy_decision_policy_controls_score_override() -> None:
    state = {
        "strategist_output": {
            "strategy_policy": {
                "decision_policy": {
                    "allow_score_override": False,
                }
            }
        }
    }

    assert _score_override_enabled(state) is False


def test_strategy_policy_decision_policy_controls_score_override_thresholds() -> None:
    state = {
        "strategist_output": {
            "strategy_policy": {
                "decision_policy": {
                    "buy_threshold": 0.07,
                    "sell_threshold": -0.04,
                    "high_vol_abs_threshold": 0.03,
                    "news_buy_threshold": 0.02,
                    "news_sell_threshold": -0.02,
                }
            }
        }
    }

    thresholds = _policy_thresholds(state)
    assert float(thresholds["buy_threshold"]) == 0.07
    assert float(thresholds["sell_threshold"]) == -0.04
    assert float(thresholds["high_vol_abs_threshold"]) == 0.03
    assert float(thresholds["news_buy_threshold"]) == 0.02
    assert float(thresholds["news_sell_threshold"]) == -0.02


def test_strategy_policy_decision_policy_controls_score_override_scope() -> None:
    state = {
        "strategist_output": {
            "strategy_policy": {
                "decision_policy": {
                    "score_override_scope": "llm_only",
                }
            }
        }
    }

    assert _score_override_scope(state) == "llm_only"
    assert _score_override_scope_allows("llm", "llm_only") is True
    assert _score_override_scope_allows("strategy_v1", "llm_only") is False


def test_strategy_policy_packet_summary_includes_monitor_exit_axes() -> None:
    state = {
        "strategist_output": {
            "strategy_policy": {
                "monitor_policy": {
                    "adaptive_exit": {
                        "peak_drawdown_exit_pct": 0.012,
                        "vwap_breakdown_pct": 0.006,
                        "intraday_low_break_pct": 0.002,
                        "trend_strength_floor": -0.08,
                    },
                    "hard_risk_rails": {
                        "hard_stop_pct": 0.01,
                    },
                }
            }
        }
    }

    summary = _build_strategy_policy_packet_summary(state)
    assert float(summary["peak_drawdown_exit_pct"]) == 0.012
    assert float(summary["vwap_breakdown_pct"]) == 0.006
    assert float(summary["intraday_low_break_pct"]) == 0.002
    assert float(summary["trend_strength_floor"]) == -0.08
    assert float(summary["hard_stop_pct"]) == 0.01
