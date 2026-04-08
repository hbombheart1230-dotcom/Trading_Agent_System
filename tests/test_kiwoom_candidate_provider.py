from __future__ import annotations

from graphs.nodes.scanner_node import scanner_node
from libs.strategies.candidates.kiwoom_candidate_provider import (
    build_kiwoom_candidate_rows,
    get_condition_search_results_with_meta,
    get_top_volume_stocks,
)
from libs.strategies.candidates.fallback_pool import resolve_fallback_symbols
from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator


def test_get_top_volume_stocks_uses_env_injection(monkeypatch):
    monkeypatch.setenv("MOCK_TOP_VOLUME_SYMBOLS", "111111,222222,333333")
    rows = get_top_volume_stocks({}, topk=2)
    assert rows == ["111111", "222222"]


def test_build_kiwoom_candidate_rows_aggregates_multi_source_scores():
    state = {
        "mock_top_value_symbols": ["AAA", "BBB", "CCC"],
        "mock_top_volume_symbols": ["BBB", "AAA", "DDD"],
        "mock_top_change_symbols": ["DDD", "AAA"],
        "mock_condition_symbols": ["CCC", "AAA", "EEE"],
    }

    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=5,
        condition_limit=10,
        include_change_rate=True,
    )

    assert meta["candidate_source"] == "kiwoom_market_data"
    assert meta["pool_count"] == 5
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["source_count"] >= 3
    assert "top_value" in rows[0]["sources"]
    assert "condition_search" in rows[0]["sources"]
    assert rows[0]["rank_score"] <= 1.0


def test_build_kiwoom_candidate_rows_respects_source_flags_and_weights():
    state = {
        "mock_top_value_symbols": ["AAA", "BBB"],
        "mock_top_volume_symbols": ["AAA", "CCC"],
        "mock_top_change_symbols": ["DDD", "EEE"],
        "mock_condition_symbols": ["FFF", "GGG"],
    }

    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=5,
        condition_limit=10,
        include_change_rate=False,
        include_top_value=True,
        include_top_volume=True,
        include_condition_search=False,
        source_weights={
            "top_value": 2.5,
            "top_volume": 1.0,
            "top_change_rate": 0.0,
            "condition_search": 0.0,
        },
    )

    assert meta["pool_source_mix"]["top_value"] == 2
    assert meta["pool_source_mix"]["top_volume"] == 2
    assert meta["pool_source_mix"]["top_change_rate"] == 0
    assert meta["pool_source_mix"]["condition_search"] == 0
    assert meta["source_weights"]["top_value"] == 2.5
    assert meta["source_weights"]["top_change_rate"] == 0.0
    assert rows[0]["symbol"] == "AAA"
    assert "top_change_rate" not in rows[0]["sources"]
    assert "condition_search" not in rows[0]["sources"]


def test_build_kiwoom_candidate_rows_filters_malformed_live_like_symbols():
    state = {
        "mock_top_value_symbols": ["005930", "0082N0", "AAA"],
        "mock_top_volume_symbols": ["000660", "A0082N0", "005930"],
        "mock_condition_symbols": ["0082N0", "000660"],
    }

    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=10,
        condition_limit=10,
        include_condition_search=True,
    )

    symbols = [str(row.get("symbol") or "") for row in rows]
    assert "005930" in symbols
    assert "000660" in symbols
    assert "AAA" in symbols
    assert "0082N0" not in symbols
    assert "A0082N0" not in symbols
    assert meta["top_value_count"] == 2
    assert meta["top_volume_count"] == 2


def test_condition_search_reports_unavailable_status_when_live_not_integrated(monkeypatch):
    monkeypatch.delenv("MOCK_CONDITION_SYMBOLS", raising=False)
    monkeypatch.delenv("KIWOOM_CONDITION_LIVE_FETCH", raising=False)

    rows, meta = get_condition_search_results_with_meta({}, limit=10)

    assert rows == []
    assert meta["status"] == "unavailable"
    assert meta["reason"] == "kiwoom_condition_live_fetch_disabled"


def test_build_kiwoom_candidate_rows_exposes_condition_search_diagnostics(monkeypatch):
    monkeypatch.delenv("MOCK_CONDITION_SYMBOLS", raising=False)
    monkeypatch.setenv("KIWOOM_CONDITION_LIVE_FETCH", "true")

    rows, meta = build_kiwoom_candidate_rows(
        state={"mock_top_value_symbols": ["AAA"]},
        top_pool=5,
        condition_limit=10,
        include_condition_search=True,
    )

    assert rows[0]["symbol"] == "AAA"
    assert meta["condition_search_status"] == "unavailable"
    assert meta["condition_search_reason"] == "kiwoom_condition_websocket_not_integrated"


def test_scanner_node_uses_kiwoom_candidates_and_theme_filter():
    state = {
        "themes": ["semiconductor"],
        "theme_map": {
            "semiconductor": ["005930"],
        },
        "mock_top_value_symbols": ["005930", "000660"],
        "mock_top_volume_symbols": ["000660", "005930"],
        "mock_top_change_symbols": ["000660"],
        "mock_condition_symbols": ["005930", "000660"],
        "mock_scan_results": {
            "005930": {"score": 0.8, "risk_score": 0.2, "confidence": 0.9},
            "000660": {"score": 0.9, "risk_score": 0.2, "confidence": 0.9},
        },
    }

    out = scanner_node(state)
    rows = out.get("scan_results") or []
    assert [r["symbol"] for r in rows] == ["005930"]
    assert out["top_stock"] == "005930"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom_market_data"
    assert bool(scanner_output.get("theme_filter_applied")) is True


def test_scanner_node_falls_back_to_strategist_candidates_when_kiwoom_pool_empty():
    state = {
        "candidate_source": "kiwoom",
        "strategist_output": {"candidates": ["123456"]},
        "mock_scan_results": {
            "123456": {"score": 0.5, "risk_score": 0.1, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    assert out.get("top_stock") == "123456"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "strategist_fallback"


def test_scanner_node_blocks_static_fallback_when_kiwoom_empty_by_default():
    state = {
        "candidate_source": "kiwoom",
        "candidates": [
            {"symbol": "005930", "why": "fallback_static", "fallback_source": "static_default"},
            {"symbol": "000660", "why": "fallback_static", "fallback_source": "static_default"},
        ],
    }

    out = scanner_node(state)
    assert out.get("top_stock") in ("", None)
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom"
    assert scanner_output.get("fallback_reason") == "kiwoom_candidate_pool_empty_static_fallback_blocked"
    assert bool(scanner_output.get("blocked_static_fallback")) is True


def test_scanner_node_can_allow_static_fallback_when_explicitly_enabled():
    state = {
        "candidate_source": "kiwoom",
        "applied_policy": {
            "scanner": {
                "source": {"type": "kiwoom"},
                "kiwoom": {"strict_only": False},
                "fallback": {"block_static_when_empty": False},
            }
        },
        "candidates": [
            {"symbol": "005930", "why": "fallback_static", "fallback_source": "static_default"},
            {"symbol": "000660", "why": "fallback_static", "fallback_source": "static_default"},
        ],
        "mock_scan_results": {
            "005930": {"score": 0.6, "risk_score": 0.2, "confidence": 0.8},
            "000660": {"score": 0.5, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    assert out.get("top_stock") == "005930"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "strategist_fallback"
    assert scanner_output.get("scanner_candidate_source") == "kiwoom"
    assert scanner_output.get("scanner_fallback_mode") == "allow_static_fallback"
    assert scanner_output.get("scanner_strict_mode") is False


def test_scanner_node_strict_kiwoom_only_blocks_strategist_fallback():
    state = {
        "candidate_source": "kiwoom",
        "applied_policy": {
            "scanner": {
                "source": {"type": "kiwoom"},
                "kiwoom": {"strict_only": True},
                "fallback": {"block_static_when_empty": False},
            }
        },
        "strategist_output": {"candidates": ["123456"]},
        "mock_scan_results": {
            "123456": {"score": 0.5, "risk_score": 0.1, "confidence": 0.8},
        },
    }
    out = scanner_node(state)
    assert out.get("top_stock") in ("", None)
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom"
    assert scanner_output.get("fallback_reason") == "kiwoom_candidate_pool_empty_strict_mode"
    assert bool(scanner_output.get("strict_kiwoom_only")) is True
    assert scanner_output.get("scanner_fallback_mode") == "strict_kiwoom_only"
    assert scanner_output.get("scanner_strict_mode") is True


def test_scanner_node_avoid_theme_overreach_keeps_empty_pool_under_strict_mode():
    state = {
        "candidate_source": "kiwoom",
        "applied_policy": {
            "scanner": {
                "source": {"type": "kiwoom"},
                "kiwoom": {"strict_only": True},
                "fallback": {"block_static_when_empty": True},
            }
        },
        "themes": ["semiconductor"],
        "theme_map": {
            "semiconductor": ["005930", "000660"],
            "defensive_large_cap": ["005930", "000660"],
        },
        "strategist_output": {"avoid_themes": ["defensive_large_cap"]},
        "mock_top_value_symbols": ["005930", "000660"],
        "mock_top_volume_symbols": ["005930", "000660"],
        "mock_scan_results": {
            "005930": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
            "000660": {"score": 0.59, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    assert out.get("top_stock") in ("", None)
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom"
    assert scanner_output.get("fallback_reason") == "kiwoom_candidate_pool_empty_strict_mode"
    assert bool(scanner_output.get("avoid_filter_applied")) is True
    assert scanner_output.get("avoid_filter_reason") == "empty_after_filter"


def test_scanner_candidate_limit_defaults_to_top_pool_when_top_n_unset(monkeypatch):
    monkeypatch.delenv("TOP_N_CANDIDATES", raising=False)

    state = {
        "candidate_source": "kiwoom",
        "applied_policy": {"scanner": {"candidate": {"top_pool": 8}}},
        "mock_top_value_symbols": [
            "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10"
        ],
        "mock_scan_results": {
            "A01": {"score": 0.60, "risk_score": 0.2, "confidence": 0.8},
            "A02": {"score": 0.59, "risk_score": 0.2, "confidence": 0.8},
            "A03": {"score": 0.58, "risk_score": 0.2, "confidence": 0.8},
            "A04": {"score": 0.57, "risk_score": 0.2, "confidence": 0.8},
            "A05": {"score": 0.56, "risk_score": 0.2, "confidence": 0.8},
            "A06": {"score": 0.55, "risk_score": 0.2, "confidence": 0.8},
            "A07": {"score": 0.54, "risk_score": 0.2, "confidence": 0.8},
            "A08": {"score": 0.53, "risk_score": 0.2, "confidence": 0.8},
            "A09": {"score": 0.52, "risk_score": 0.2, "confidence": 0.8},
            "A10": {"score": 0.51, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom_market_data"
    assert int(scanner_output.get("candidate_count") or 0) == 8
    assert int(scanner_output.get("candidate_pool_size") or 0) == 8


def test_fallback_symbols_use_watchlist_before_static_defaults():
    symbols, source = resolve_fallback_symbols(
        state={"watchlist_symbols": ["111111", "222222", "333333"]},
        policy={},
        limit=3,
    )
    assert symbols == ["111111", "222222", "333333"]
    assert source == "state_or_policy_watchlist"


def test_fallback_symbols_returns_empty_when_no_runtime_inputs(monkeypatch):
    monkeypatch.delenv("FALLBACK_CANDIDATE_SYMBOLS", raising=False)
    monkeypatch.delenv("OPERATOR_WATCHLIST", raising=False)
    symbols, source = resolve_fallback_symbols(state={}, policy={}, limit=5)
    assert symbols == []
    assert source == "none"


def test_scanner_kiwoom_pool_can_backfill_from_strategist_candidates(monkeypatch):
    monkeypatch.delenv("TOP_N_CANDIDATES", raising=False)

    state = {
        "candidate_source": "kiwoom",
        "applied_policy": {
            "scanner": {
                "candidate": {"top_pool": 6},
                "source": {"type": "kiwoom"},
                "kiwoom": {"strict_only": False},
                "fallback": {"block_static_when_empty": False},
            }
        },
        "mock_top_value_symbols": ["A01", "A02"],
        "strategist_output": {
            "candidates": ["A01", "A02", "A03", "A04", "A05", "A06"],
        },
        "mock_scan_results": {
            "A01": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
            "A02": {"score": 0.60, "risk_score": 0.2, "confidence": 0.8},
            "A03": {"score": 0.59, "risk_score": 0.2, "confidence": 0.8},
            "A04": {"score": 0.58, "risk_score": 0.2, "confidence": 0.8},
            "A05": {"score": 0.57, "risk_score": 0.2, "confidence": 0.8},
            "A06": {"score": 0.56, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom_market_data"
    assert int(scanner_output.get("candidate_count") or 0) == 6
    assert bool(scanner_output.get("backfill_used")) is True
    assert int(scanner_output.get("backfill_count") or 0) >= 4


def test_market_rank_candidate_generator_uses_reader_topk_signature(monkeypatch):
    calls = {}

    class _FakeReader:
        def get_top_symbols(self, *, mode, topk=5):  # noqa: ANN001
            calls["mode"] = getattr(mode, "value", str(mode))
            calls["topk"] = int(topk)
            return ["111111", "222222", "333333"]

    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", "true")
    monkeypatch.setattr(
        "libs.read.kiwoom_rank_reader.KiwoomRankReader.from_env",
        staticmethod(lambda: _FakeReader()),
    )

    out = MarketRankCandidateGenerator().generate(
        {
            "policy": {
                "candidate_rank_topn": 2,
                "candidate_rank_mode": "change_rate",
            }
        }
    )

    assert out == ["111111", "222222"]
    assert calls["topk"] == 2
    assert calls["mode"] == "change_rate"
