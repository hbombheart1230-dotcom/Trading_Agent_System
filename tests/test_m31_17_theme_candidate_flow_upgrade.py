from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import _neutralize_ambiguous_playbook_memory, strategist_node


def test_m31_17_strategist_outputs_themes_and_candidates_contract(monkeypatch):
    monkeypatch.setenv("TOP_N_CANDIDATES", "4")
    state = {
        "themes": ["semiconductor", "AI"],
        "candidate_symbols": ["005930", "000660", "042700", "058470", "091990"],
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output["themes"] == ["semiconductor", "AI"]
    assert strategist_output["candidates"] == ["005930", "000660", "042700", "058470"]
    assert int(strategist_output["candidate_count"]) == 4
    assert out.get("themes") == ["semiconductor", "AI"]
    for key in (
        "market_regime",
        "market_sentiment",
        "key_events",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_priority",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "report_focus",
        "strategic_answers",
    ):
        assert key in strategist_output

    assert strategist_output["market_regime"] in ("risk_on", "neutral", "risk_off")
    assert strategist_output["market_sentiment"] in ("bullish", "neutral", "bearish")
    assert strategist_output["playbook"] in ("breakout", "pullback", "reversal", "defensive")
    assert strategist_output["scanner_bias"] in ("large_cap", "leader", "momentum", "value")
    assert strategist_output["risk_tone"] in ("conservative", "normal", "aggressive")
    assert strategist_output["monitor_guidance"] in ("hold_through_noise", "defensive_exit", "quick_take_profit")
    assert strategist_output["trade_aggressiveness"] in ("low", "medium", "high")
    assert isinstance(strategist_output["scanner_priority"], list)
    assert isinstance(strategist_output.get("scanner_source_policy"), dict)
    assert strategist_output["scanner_source_policy"].get("preferred_sources")
    assert isinstance(strategist_output.get("monitor_policy"), dict)
    assert isinstance(strategist_output.get("exit_policy"), dict)
    assert float((strategist_output.get("exit_policy") or {}).get("stop_loss_pct") or 0.0) > 0.0
    assert float((strategist_output.get("exit_policy") or {}).get("take_profit_pct") or 0.0) > 0.0
    assert isinstance(strategist_output["report_focus"], list)
    assert isinstance(strategist_output["strategic_answers"], dict)
    assert strategist_output["runtime_theme_map_keys"] == ["ai", "semiconductor"]
    assert strategist_output["runtime_sector_map_keys"] == ["ai", "semiconductor"]
    assert out.get("theme_map", {}).get("semiconductor") == ["005930", "000660", "042700", "058470"]
    assert out.get("sector_map", {}).get("ai") == ["005930", "000660", "042700", "058470"]


def test_m31_17_ambiguous_best_worst_playbook_memory_is_not_directional():
    memory = _neutralize_ambiguous_playbook_memory(
        {
            "best_playbooks": ["defensive"],
            "worst_playbooks": ["defensive"],
            "advisory_only": True,
        }
    )

    assert memory["best_playbooks"] == []
    assert memory["worst_playbooks"] == []
    assert memory["directional_bias_usable"] is False
    assert "ambiguous_playbook_performance:best_worst_overlap" in memory["memory_quality_flags"]


def test_m31_17_scanner_accepts_strategist_output_and_emits_top_stock():
    state = {
        "strategist_output": {
            "themes": ["semiconductor"],
            "avoid_themes": ["high_gap_speculative"],
            "playbook": "breakout",
            "candidates": ["005930", "000660"],
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength", "liquidity"],
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
        },
        "mock_scan_results": {
            "005930": {"score": 0.91, "risk_score": 0.20, "confidence": 0.88},
            "000660": {"score": 0.75, "risk_score": 0.21, "confidence": 0.84},
        },
    }

    out = scanner_node(state)
    assert (out.get("selected") or {}).get("symbol") == "005930"
    assert out.get("top_stock") == "005930"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("top_stock") == "005930"
    assert float(scanner_output.get("score") or 0.0) == 0.91
    assert scanner_output.get("strategist_scanner_priority") == ["momentum", "trend_strength", "liquidity"]
    assert scanner_output.get("strategist_playbook") == "breakout"
    assert scanner_output.get("strategist_scanner_bias") == "momentum"
    assert scanner_output.get("strategist_trade_aggressiveness") == "high"
    assert scanner_output.get("strategist_risk_tone") == "aggressive"


def test_m31_17_scanner_source_policy_changes_kiwoom_source_mix():
    state = {
        "strategist_output": {
            "themes": ["semiconductor"],
            "playbook": "defensive",
            "scanner_bias": "leader",
            "scanner_priority": ["liquidity", "risk_penalty"],
            "scanner_source_policy": {
                "include_top_value": True,
                "include_top_volume": True,
                "include_change_rate": False,
                "include_condition_search": False,
                "include_sector_candidates": False,
                "include_watchlist": False,
                "preferred_sources": ["top_value", "top_volume"],
                "source_weights": {
                    "top_value": 2.2,
                    "top_volume": 1.9,
                    "top_change_rate": 0.0,
                    "condition_search": 0.0,
                },
            },
            "trade_aggressiveness": "low",
            "risk_tone": "conservative",
        },
        "mock_top_value_symbols": ["AAA"],
        "mock_top_volume_symbols": ["AAA"],
        "mock_top_change_symbols": ["BBB"],
        "mock_condition_symbols": ["CCC"],
        "mock_scan_results": {
            "AAA": {"score": 0.60, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.95, "risk_score": 0.20, "confidence": 0.90},
            "CCC": {"score": 0.94, "risk_score": 0.20, "confidence": 0.90},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}

    assert out.get("top_stock") == "AAA"
    assert scanner_output.get("source_mix") == {
        "top_value": 1,
        "top_volume": 1,
        "top_change_rate": 0,
        "condition_search": 0,
        "sector_theme": 0,
        "operator_watchlist": 0,
    }
    assert scanner_output.get("scanner_source_policy", {}).get("include_change_rate") is False
    assert scanner_output.get("scanner_source_policy", {}).get("include_condition_search") is False


def test_m31_17_runtime_theme_map_enables_sector_theme_candidates():
    base = strategist_node(
        {
            "themes": ["semiconductor"],
            "candidate_symbols": ["AAA", "BBB", "CCC"],
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )
    base["mock_scan_results"] = {
        "AAA": {"score": 0.91, "risk_score": 0.20, "confidence": 0.88},
        "BBB": {"score": 0.75, "risk_score": 0.21, "confidence": 0.84},
        "CCC": {"score": 0.72, "risk_score": 0.22, "confidence": 0.80},
    }
    base["mock_top_value_symbols"] = []
    base["mock_top_volume_symbols"] = []
    base["mock_top_change_symbols"] = []
    base["mock_condition_symbols"] = []
    base["scanner_features"] = {
        "AAA": {
            "return20": 0.12,
            "ma20_gap": 0.04,
            "ma60_gap": 0.05,
            "ma120_gap": 0.06,
            "trend_strength": 0.80,
            "adx14": 28.0,
            "volume_spike20": 2.0,
            "vwap_distance": 0.010,
            "cross_section_rank": 1.0,
            "volatility20": 0.02,
        },
        "BBB": {
            "return20": 0.02,
            "ma20_gap": 0.01,
            "ma60_gap": 0.01,
            "ma120_gap": 0.00,
            "trend_strength": 0.20,
            "adx14": 14.0,
            "volume_spike20": 1.0,
            "vwap_distance": 0.000,
            "cross_section_rank": 0.3,
            "volatility20": 0.03,
        },
        "CCC": {
            "return20": -0.01,
            "ma20_gap": -0.01,
            "ma60_gap": -0.01,
            "ma120_gap": -0.02,
            "trend_strength": -0.10,
            "adx14": 12.0,
            "volume_spike20": 1.0,
            "vwap_distance": -0.005,
            "cross_section_rank": 0.1,
            "volatility20": 0.03,
        },
    }

    out = scanner_node(base)
    scanner_output = out.get("scanner_output") or {}
    source_mix = scanner_output.get("source_mix") or {}

    assert int(source_mix.get("sector_theme") or 0) == 3
    assert out.get("top_stock") == "AAA"


def test_m31_17_llm_override_themes_enable_sector_theme_candidates(monkeypatch):
    class _Route:
        def __init__(self, model: str) -> None:
            self.model = model

    class _FakeRouterOk:
        def __init__(self) -> None:
            self.client = object()

        @staticmethod
        def from_env() -> "_FakeRouterOk":
            return _FakeRouterOk()

        def resolve(self, role, *, policy=None):
            return _Route(model=str((policy or {}).get("model") or "minimax/minimax-m2.5"))

        def chat(self, role, messages, *, policy=None):
            return (
                '{"market_regime":"risk_on","market_sentiment":"bullish","themes":["semiconductor","ai"],'
                '"avoid_themes":["high_gap_speculative"],"playbook":"breakout","scanner_bias":"momentum",'
                '"scanner_priority":["momentum","trend_strength","trading_value"],'
                '"trade_aggressiveness":"high","risk_tone":"aggressive","monitor_guidance":"hold_through_noise",'
                '"report_focus":["theme_accuracy","exit_quality"]}'
            )

    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    base = strategist_node(
        {
            "candidate_symbols": ["AAA", "BBB", "CCC"],
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )
    base["mock_scan_results"] = {
        "AAA": {"score": 0.91, "risk_score": 0.20, "confidence": 0.88},
        "BBB": {"score": 0.75, "risk_score": 0.21, "confidence": 0.84},
        "CCC": {"score": 0.72, "risk_score": 0.22, "confidence": 0.80},
    }
    base["mock_top_value_symbols"] = []
    base["mock_top_volume_symbols"] = []
    base["mock_top_change_symbols"] = []
    base["mock_condition_symbols"] = []
    base["scanner_features"] = {
        "AAA": {
            "return20": 0.12,
            "ma20_gap": 0.04,
            "ma60_gap": 0.05,
            "ma120_gap": 0.06,
            "trend_strength": 0.80,
            "adx14": 28.0,
            "volume_spike20": 2.0,
            "vwap_distance": 0.010,
            "cross_section_rank": 1.0,
            "volatility20": 0.02,
        },
        "BBB": {
            "return20": 0.02,
            "ma20_gap": 0.01,
            "ma60_gap": 0.01,
            "ma120_gap": 0.00,
            "trend_strength": 0.20,
            "adx14": 14.0,
            "volume_spike20": 1.0,
            "vwap_distance": 0.000,
            "cross_section_rank": 0.3,
            "volatility20": 0.03,
        },
        "CCC": {
            "return20": -0.01,
            "ma20_gap": -0.01,
            "ma60_gap": -0.01,
            "ma120_gap": -0.02,
            "trend_strength": -0.10,
            "adx14": 12.0,
            "volume_spike20": 1.0,
            "vwap_distance": -0.005,
            "cross_section_rank": 0.1,
            "volatility20": 0.03,
        },
    }

    out = scanner_node(base)
    scanner_output = out.get("scanner_output") or {}
    source_mix = scanner_output.get("source_mix") or {}

    assert int(source_mix.get("sector_theme") or 0) == 3
    assert out.get("top_stock") == "AAA"


def test_m31_17_kiwoom_theme_packet_drives_themes_and_sector_candidates(monkeypatch):
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)
    base = strategist_node(
        {
            "candidate_symbols": ["005930", "000660", "373220"],
            "mock_theme_groups": [
                {
                    "thema_grp_cd": "319",
                    "thema_nm": "semiconductor",
                    "stk_num": "4",
                    "flu_rt": "+4.0",
                    "rising_stk_num": "3",
                    "fall_stk_num": "0",
                    "dt_prft_rt": "+12.0",
                },
                {
                    "thema_grp_cd": "401",
                    "thema_nm": "battery",
                    "stk_num": "5",
                    "flu_rt": "+1.0",
                    "rising_stk_num": "1",
                    "fall_stk_num": "2",
                    "dt_prft_rt": "+2.0",
                },
            ],
            "mock_theme_component_map": {
                "semiconductor": ["005930", "000660"],
                "battery": ["373220"],
            },
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )

    strategist_output = base.get("strategist_output") or {}
    assert strategist_output["themes"][0] == "semiconductor"
    assert strategist_output["selected_themes"][0] == "semiconductor"
    assert strategist_output["theme_strategy"]["selection_mode"] == "kiwoom_api_constrained"
    assert strategist_output["theme_source"] == "state_mock"
    assert strategist_output["theme_source_status"] == "ok"
    assert base.get("theme_map", {}).get("semiconductor")[:2] == ["005930", "000660"]

    base["mock_scan_results"] = {
        "005930": {"score": 0.82, "risk_score": 0.20, "confidence": 0.86},
        "000660": {"score": 0.75, "risk_score": 0.20, "confidence": 0.84},
        "373220": {"score": 0.70, "risk_score": 0.20, "confidence": 0.82},
    }
    base["mock_top_value_symbols"] = []
    base["mock_top_volume_symbols"] = []
    base["mock_top_change_symbols"] = []
    base["mock_condition_symbols"] = []

    out = scanner_node(base)
    scanner_output = out.get("scanner_output") or {}
    source_mix = scanner_output.get("source_mix") or {}

    assert int(source_mix.get("sector_theme") or 0) >= 2
    assert scanner_output["selected_themes"][0] == "semiconductor"
    assert scanner_output["selected_theme_source"] in {
        "scanner_guidance.selected_themes",
        "strategist_output.selected_themes",
        "state.selected_themes",
    }
    assert scanner_output["theme_source_status"] == "ok"
    assert out.get("top_stock") in {"005930", "000660", "373220"}


def test_m31_17_kiwoom_theme_without_components_does_not_backfill_all_candidates(monkeypatch):
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)
    out = strategist_node(
        {
            "candidate_symbols": ["000660", "005930", "373220"],
            "mock_theme_groups": [
                {
                    "thema_grp_cd": "140",
                    "thema_nm": "battery",
                    "stk_num": "3",
                    "flu_rt": "+4.9",
                    "rising_stk_num": "3",
                    "fall_stk_num": "0",
                    "dt_prft_rt": "+27.5",
                },
                {
                    "thema_grp_cd": "319",
                    "thema_nm": "semiconductor",
                    "stk_num": "4",
                    "flu_rt": "+1.0",
                    "rising_stk_num": "2",
                    "fall_stk_num": "2",
                    "dt_prft_rt": "+10.0",
                },
            ],
            "mock_theme_component_map": {
                "semiconductor": ["005930"],
            },
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )

    theme_map = out.get("theme_map") or {}
    assert theme_map.get("semiconductor") == ["005930"]
    assert theme_map.get("battery") == []
    assert "000660" not in theme_map.get("battery", [])


def test_m31_17_commander_scanner_live_fetch_drives_strategist_theme_packet(monkeypatch):
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)
    monkeypatch.delenv("KIWOOM_THEME_FETCH_COMPONENTS", raising=False)
    monkeypatch.setenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", "true")
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")

    class _FakeThemeReader:
        @staticmethod
        def from_env():
            return _FakeThemeReader()

        def get_theme_groups(self, *, limit=20, date_tp="10", stex_tp="1"):
            return [
                {
                    "theme_code": "319",
                    "theme_name": "semiconductor",
                    "stock_count": 4,
                    "rising_count": 3,
                    "falling_count": 0,
                    "change_rate": 4.0,
                    "period_return": 12.0,
                }
            ]

        def get_theme_components(self, *, theme_code, limit=100, stex_tp="1"):
            assert theme_code == "319"
            return [
                {"symbol": "005930", "name": "Samsung", "change_rate": 2.5},
                {"symbol": "000660", "name": "SK Hynix", "change_rate": 3.0},
            ]

    monkeypatch.setattr("libs.read.kiwoom_theme_reader.KiwoomThemeReader", _FakeThemeReader)

    out = strategist_node(
        {
            "candidate_symbols": ["005930", "000660", "373220"],
            "applied_policy": {
                "scanner": {
                    "kiwoom": {
                        "live_fetch": True,
                    }
                }
            },
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output["theme_source"] == "kiwoom_live"
    assert strategist_output["theme_source_status"] == "ok"
    assert strategist_output["selected_themes"][0] == "semiconductor"
    assert out.get("theme_map", {}).get("semiconductor") == ["005930", "000660"]


def test_m31_17_unavailable_theme_packet_does_not_select_broad_market_fallback(monkeypatch):
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)
    monkeypatch.delenv("KIWOOM_THEME_FETCH_COMPONENTS", raising=False)
    monkeypatch.delenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", raising=False)
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")

    out = strategist_node(
        {
            "candidate_symbols": ["005930", "000660", "005380"],
            "policy": {
                "use_global_sentiment": False,
                "use_news_analysis": False,
                "use_universe_builder": False,
            },
        }
    )

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output["theme_source_status"] == "unavailable"
    assert strategist_output["selected_themes"] == []
    assert (strategist_output.get("theme_strategy") or {}).get("selection_mode") == "fallback"
    assert (strategist_output.get("theme_strategy") or {}).get("selected_theme_names") == []


def test_m31_17_monitor_sell_cooldown_env_alias_is_supported(monkeypatch):
    monkeypatch.delenv("SELL_COOLDOWN_SEC", raising=False)
    monkeypatch.setenv("SELL_COOLDOWN", "900")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "005930",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
        },
        "portfolio_snapshot": {
            "positions": [{"symbol": "005930", "qty": 3, "avg_price": 70000.0, "hold_sec": 120}]
        },
        "market_snapshot": {"symbol": "005930", "price": 68000.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.20,
        },
    }

    out1 = monitor_node(state)
    intents1 = out1.get("intents") or []
    assert len(intents1) == 1
    assert intents1[0]["side"] == "SELL"

    out2 = monitor_node(out1)
    assert out2.get("intents") == []
    exit_info = out2.get("monitor_exit") or {}
    assert bool(exit_info.get("sell_guard_blocked")) is True
    reason = str(exit_info.get("sell_guard_reason") or "")
    assert ("sell_guard_pending_exit_lock" in reason) or ("sell_guard_cooldown" in reason)
