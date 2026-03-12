from __future__ import annotations

from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import _default_policy, strategist_node


def test_strategist_emits_signal_contract_for_global_and_news_when_disabled():
    state = {
        "universe": ["AAA", "BBB"],
        "policy": {
            "candidate_k": 2,
            "use_global_sentiment": False,
            "use_news_analysis": False,
        },
    }
    out = strategist_node(state)

    assert "global_sentiment" in out and "score" in out["global_sentiment"]
    assert out["global_sentiment_signal"]["status"] == "fallback"
    assert out["global_sentiment_signal"]["reason"] == "global_sentiment_disabled"

    assert "news_sentiment" in out
    assert "news_sentiment_signal" in out
    assert out["news_sentiment_signal"]["AAA"]["status"] == "fallback"
    assert out["news_sentiment_signal"]["AAA"]["reason"] == "news_analysis_disabled"
    assert float(out["news_sentiment"]["AAA"]) == 0.0


def test_scanner_prefers_signal_score_over_legacy_news_score():
    state = {
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
        },
        # opposite legacy scores (should be ignored when signal is present)
        "news_sentiment": {"AAA": 1.0, "BBB": 0.0},
        "news_sentiment_signal": {
            "AAA": {"score": 0.0, "status": "ok", "source": "test", "reason": "", "ts": 1772812800},
            "BBB": {"score": 1.0, "status": "ok", "source": "test", "reason": "", "ts": 1772812800},
        },
        "policy": {
            "weight_news": 0.20,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }
    out = scanner_node(state)
    assert out["selected"]["symbol"] == "BBB"


def test_scanner_components_include_signal_status_fields():
    state = {
        "candidates": [{"symbol": "AAA"}],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
        },
        "global_sentiment_signal": {
            "score": 0.25,
            "status": "fallback",
            "source": "dry_run_policy",
            "reason": "dry_run_neutral",
            "ts": 1772812800,
        },
        "news_sentiment_signal": {
            "AAA": {
                "score": 0.10,
                "status": "unavailable",
                "source": "scorer:simple",
                "reason": "fetch_failed",
                "ts": 1772812800,
            }
        },
        "policy": {
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }
    out = scanner_node(state)
    comp = (out["selected"] or {}).get("components") or {}
    assert comp["news_sentiment_status"] == "unavailable"
    assert comp["global_sentiment_status"] == "fallback"
    assert comp["global_sentiment_reason"] == "dry_run_neutral"


def test_strategist_default_policy_reads_news_sentiment_env(monkeypatch):
    monkeypatch.setenv("M10_USE_NEWS_SENTIMENT", "true")
    p_true = _default_policy({})
    assert bool(p_true.get("use_news_analysis")) is True

    monkeypatch.setenv("M10_USE_NEWS_SENTIMENT", "false")
    p_false = _default_policy({})
    assert bool(p_false.get("use_news_analysis")) is False
