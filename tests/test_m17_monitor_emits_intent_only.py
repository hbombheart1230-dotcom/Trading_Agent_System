from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node


def test_m17_monitor_emits_at_most_one_intent_from_selected():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "scan_results": [{"symbol": "AAA"}],
    }

    out = monitor_node(state)
    intents = out.get("intents")
    assert isinstance(intents, list)
    assert len(intents) == 1
    assert intents[0]["symbol"] == "AAA"
    assert "monitor" in out


def test_m17_monitor_emits_no_intent_when_no_selected():
    state = {"plan": {"thesis": "demo"}, "selected": None}
    out = monitor_node(state)
    assert out.get("intents") == []