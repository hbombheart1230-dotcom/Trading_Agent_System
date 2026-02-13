from __future__ import annotations

from typing import Any, Dict, List

import pytest

from libs.news.news_pipeline import score_news_sentiment


def test_m19_4_openrouter_scorer_respects_mock_and_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRY_RUN", "1")
    items_by_symbol: Dict[str, List[Dict[str, Any]]] = {
        "AAA": [{"title": "AAA good"}],
        "BBB": [{"title": "BBB bad"}],
        "CCC": [],
    }
    state = {"mock_news_sentiment": {"AAA": 0.7, "BBB": -0.2}}
    policy = {"news_scorer": "openrouter"}  # should still use mock in DRY_RUN

    scores = score_news_sentiment(items_by_symbol, state=state, policy=policy)

    assert scores["AAA"] == 0.7
    assert scores["BBB"] == -0.2
    assert scores["CCC"] == 0.0


def test_m19_4_openrouter_scorer_dry_run_returns_zero(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRY_RUN", "1")
    items_by_symbol = {"AAA": [{"title": "x"}], "BBB": []}
    state = {}
    policy = {"news_scorer": "openrouter"}

    scores = score_news_sentiment(items_by_symbol, state=state, policy=policy)

    assert scores == {"AAA": 0.0, "BBB": 0.0}
