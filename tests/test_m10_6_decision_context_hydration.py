from __future__ import annotations

from graphs.nodes.build_decision_context import build_decision_context


def test_m10_6_decision_context_hydrates_global_and_news_from_mocks(monkeypatch):
    monkeypatch.setattr("graphs.nodes.build_decision_context.time.time", lambda: 1000.0)

    state = {
        "symbol": "005930",
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "decision_context_refresh_sec": 300,
        },
        "mock_global_sentiment": 0.35,
        "mock_news_sentiment": {"005930": 0.25},
        "mock_news_items": {"005930": []},
    }

    out = build_decision_context(state)

    assert abs(float(out["global_sentiment"]["score"]) - 0.35) < 1e-12
    assert abs(float(out["news_sentiment"]["005930"]) - 0.25) < 1e-12
    assert out["decision_context_meta"]["cached"] is False
    assert int(out["decision_context_meta"]["last_refreshed_epoch"]) == 1000


def test_m10_6_decision_context_cache_skips_refresh_within_window(monkeypatch):
    monkeypatch.setattr("graphs.nodes.build_decision_context.time.time", lambda: 1000.0)
    state = {
        "symbol": "005930",
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "decision_context_refresh_sec": 300,
        },
        "mock_global_sentiment": 0.10,
        "mock_news_sentiment": {"005930": 0.20},
        "mock_news_items": {"005930": []},
    }
    out1 = build_decision_context(state)
    assert abs(float(out1["global_sentiment"]["score"]) - 0.10) < 1e-12
    assert abs(float(out1["news_sentiment"]["005930"]) - 0.20) < 1e-12

    # Change inputs, but keep same timestamp -> cache should hold previous values.
    state["mock_global_sentiment"] = 0.90
    state["mock_news_sentiment"] = {"005930": 0.80}
    out2 = build_decision_context(state)

    assert abs(float(out2["global_sentiment"]["score"]) - 0.10) < 1e-12
    assert abs(float(out2["news_sentiment"]["005930"]) - 0.20) < 1e-12
    assert out2["decision_context_meta"]["cached"] is True

    # After refresh window passes, new values should be applied.
    monkeypatch.setattr("graphs.nodes.build_decision_context.time.time", lambda: 1401.0)
    out3 = build_decision_context(state)
    assert abs(float(out3["global_sentiment"]["score"]) - 0.90) < 1e-12
    assert abs(float(out3["news_sentiment"]["005930"]) - 0.80) < 1e-12
    assert out3["decision_context_meta"]["cached"] is False

