from __future__ import annotations

import graphs.nodes.scanner_node as scanner_mod
from graphs.nodes.scanner_node import scanner_node


def test_scanner_auto_hydration_uses_runtime_candidate_pool_when_state_candidates_missing(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_resolve_scanner_candidates(state, policy):
        return ([{"symbol": "005930"}], {"candidate_source": "kiwoom_market_data"})

    def _fake_hydrate(state):
        captured["hydration_candidates"] = list(state.get("candidates") or [])
        state["skill_results"] = {
            "market.quote": {
                "005930": {
                    "symbol": "005930",
                    "price": 70000,
                    "volume": 123456,
                    "value": 987654321.0,
                    "change_pct": 1.5,
                }
            }
        }
        state["skill_fetch"] = {"used_runner": True}
        return state

    monkeypatch.setattr(scanner_mod, "_resolve_scanner_candidates", _fake_resolve_scanner_candidates)
    monkeypatch.setattr(
        "graphs.nodes.hydrate_skill_results_node.hydrate_skill_results_node",
        _fake_hydrate,
    )

    state = {
        "policy": {
            "enable_scanner_skill_hydration": True,
            "enable_practical_scoring": False,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "feature_score_weight": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
        "strategist_output": {
            "playbook": "pullback",
            "strategy_policy": {"scanner_policy": {}},
        },
        "mock_scan_results": {
            "005930": {"score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)

    assert captured["hydration_candidates"] == [{"symbol": "005930"}]
    selected_features = ((out.get("selected") or {}).get("features") or {})
    assert selected_features.get("skill_quote_price") == 70000.0
    assert selected_features.get("quote_volume") == 123456.0
    assert selected_features.get("quote_trading_value") == 987654321.0

