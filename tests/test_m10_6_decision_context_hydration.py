from __future__ import annotations

from graphs.nodes.build_decision_context import build_decision_context


def _trend_up_candles(n: int = 50) -> list[dict]:
    out: list[dict] = []
    px = 100.0
    for i in range(n):
        px = px + 0.5
        out.append(
            {
                "ts": 1700000000 + i * 60,
                "open": px - 0.2,
                "high": px + 0.3,
                "low": px - 0.4,
                "close": px,
                "volume": 1000 + i * 10,
            }
        )
    return out


def test_m10_6_decision_context_hydrates_global_and_news_from_mocks(monkeypatch):
    monkeypatch.setattr("graphs.nodes.build_decision_context.time.time", lambda: 1000.0)
    monkeypatch.setenv("M10_FEATURE_SEED_WITH_YF", "false")

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
    monkeypatch.setenv("M10_FEATURE_SEED_WITH_YF", "false")
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


def test_m10_6_symbol_query_map_is_injected_from_env(monkeypatch):
    monkeypatch.setattr("graphs.nodes.build_decision_context.time.time", lambda: 2000.0)
    monkeypatch.setenv("M10_FEATURE_SEED_WITH_YF", "false")
    monkeypatch.setenv("M10_SYMBOL_QUERY_MAP", "005930=Samsung Electronics,000660=SK hynix")
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930,000660")

    captured = {}

    def _fake_collect(symbols, *, state, policy):
        captured["symbol_query_map"] = dict(policy.get("symbol_query_map") or {})
        return {str(symbols[0]): []}

    monkeypatch.setattr("graphs.nodes.build_decision_context.collect_news_items", _fake_collect)
    monkeypatch.setattr(
        "graphs.nodes.build_decision_context.score_news_sentiment",
        lambda items_by_symbol, *, state, policy: {"005930": 0.0},
    )

    state = {
        "symbol": "005930",
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": True,
            "decision_context_refresh_sec": 300,
        },
    }
    out = build_decision_context(state)

    sqm = captured.get("symbol_query_map") or {}
    assert sqm.get("005930") == "Samsung Electronics"
    assert sqm.get("000660") == "SK hynix"
    assert "news_sentiment" in out and "005930" in out["news_sentiment"]


def test_m10_6_feature_engine_context_is_built_from_ohlcv(monkeypatch):
    monkeypatch.setattr("graphs.nodes.build_decision_context.time.time", lambda: 2500.0)
    monkeypatch.setenv("M10_FEATURE_SEED_WITH_YF", "false")
    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 130.0},
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "decision_context_refresh_sec": 300,
        },
        "ohlcv_by_symbol": {"005930": _trend_up_candles(60)},
    }
    out = build_decision_context(state)

    fe = out.get("feature_engine") or {}
    by_symbol = fe.get("by_symbol") if isinstance(fe, dict) else {}
    row = by_symbol.get("005930") if isinstance(by_symbol, dict) else {}
    assert isinstance(row, dict)
    assert row.get("rsi14") is not None
    assert row.get("ma20_gap") is not None
    assert row.get("regime") in ("trend", "range", "high_volatility")
    assert "feature_regime" in out.get("decision_context_meta", {})
