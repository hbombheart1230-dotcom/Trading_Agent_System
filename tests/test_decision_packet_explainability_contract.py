from __future__ import annotations

from graphs.nodes.assemble_decision_packet import assemble_decision_packet


def test_decision_packet_includes_explainability_fields():
    state = {
        "intent": {"intent": "buy"},
        "order_api_id": "ORDER_SUBMIT",
        "symbol": "005930",
        "risk_context": {},
        "exec_context": {"mode": "mock"},
        "decision_trace": {
            "llm_context": {
                "technical": {"regime": "trend", "rsi14": 57.0},
                "news": {"symbol_sentiment_score": 0.2, "global_sentiment_score": 0.1},
                "decision_policy": {"buy_threshold": 0.1},
            }
        },
    }

    out = assemble_decision_packet(state)
    pkt = out["decision_packet"]
    why = pkt["why"]
    invalidation = pkt["invalidation"]

    assert set(why.keys()) == {"regime", "technical", "news", "policy"}
    assert why["regime"] == "trend"
    assert set(invalidation.keys()) == {"triggered", "reason", "conditions"}
    assert invalidation["triggered"] is False
