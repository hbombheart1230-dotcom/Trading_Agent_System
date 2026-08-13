from libs.runtime.commander.strategist_refresh_decision import (
    assess_pre_buy_strategist_refresh_need,
    force_selected_symbol_tactical_refresh_decision,
    resolve_risk_max_positions,
)


def _base_state(*, selected_symbol: str = "005930", cache_age_sec: int = 400) -> dict:
    now_epoch = 10_000
    return {
        "now_epoch": now_epoch,
        "selected": {"symbol": selected_symbol, "rank": 1, "score_total": 0.91},
        "ranked_candidates": [
            {"symbol": selected_symbol, "rank": 1, "score_total": 0.91},
            {"symbol": "000660", "rank": 2, "score_total": 0.84},
        ],
        "portfolio_snapshot": {"positions": []},
        "persisted_state": {
            "strategist_output_cache": {
                "output": {
                    "playbook": "defensive",
                    "market_regime": "risk_off",
                    "candidate_symbols_hint": ["005930", "000660"],
                },
                "generated_epoch": now_epoch - cache_age_sec,
                "source": "strategist_node",
                "input_fingerprint": {
                    "schema_version": "strategist_input_fingerprint.v1",
                    "selected_symbol": "005930",
                    "top_symbols": ["005930", "000660"],
                    "top3_symbols": ["005930", "000660"],
                    "market_regime": "risk_off",
                    "open_position_count": 0,
                    "open_symbols": [],
                },
            }
        },
    }


def test_risk_max_positions_uses_same_environment_fallback_as_monitor(monkeypatch) -> None:
    monkeypatch.setenv("RISK_MAX_POSITIONS", "3")

    assert resolve_risk_max_positions({}) == 3
    assert resolve_risk_max_positions({"risk_context": {"max_positions": 2}}) == 2


def test_selected_symbol_refresh_is_suppressed_when_cached_frame_covers_symbol() -> None:
    out = force_selected_symbol_tactical_refresh_decision(
        _base_state(selected_symbol="005930", cache_age_sec=500),
        {"strategist_refresh_requested": False},
    )

    context = out.get("strategist_refresh_context") or {}
    assert out.get("strategist_refresh_requested") is not True
    assert context.get("post_scanner_refresh_suppressed") is True
    assert context.get("post_scanner_refresh_suppressed_reason") == "selected_symbol_covered_by_cached_frame"
    assert context.get("selected_symbol_in_cached_frame") is True


def test_selected_symbol_refresh_is_suppressed_for_fresh_cache_outside_frame_without_actionable_entry() -> None:
    state = _base_state(selected_symbol="078890", cache_age_sec=120)
    state["ranked_candidates"][0]["symbol"] = "078890"
    state["ranked_candidates"][0]["score_total"] = 0.84
    state["selected"]["symbol"] = "078890"
    state["selected"]["score_total"] = 0.84

    out = force_selected_symbol_tactical_refresh_decision(
        state,
        {"strategist_refresh_requested": False},
    )

    context = out.get("strategist_refresh_context") or {}
    assert out.get("strategist_refresh_requested") is not True
    assert context.get("post_scanner_refresh_suppressed") is True
    assert context.get("post_scanner_refresh_suppressed_reason") == "selected_symbol_tactical_refresh_cache_too_fresh"
    assert context.get("selected_symbol_in_cached_frame") is False


def test_selected_symbol_refresh_allows_strong_new_rank1_outside_cached_frame() -> None:
    state = _base_state(selected_symbol="078890", cache_age_sec=500)
    state["ranked_candidates"][0]["symbol"] = "078890"
    state["selected"]["symbol"] = "078890"

    out = force_selected_symbol_tactical_refresh_decision(
        state,
        {"strategist_refresh_requested": False},
    )

    context = out.get("strategist_refresh_context") or {}
    assert out.get("strategist_refresh_requested") is True
    assert out.get("strategist_refresh_reason") == "selected_symbol_tactical_refresh"
    assert context.get("strong_new_leader") is True
    assert context.get("selected_symbol_in_cached_frame") is False


def test_pre_buy_outside_cached_frame_no_longer_bypasses_fresh_cache_gate() -> None:
    state = _base_state(selected_symbol="078890", cache_age_sec=120)
    state["monitor_output"] = {
        "selected_symbol": "078890",
        "intent_side": "NOOP",
        "entry_exit_reason": "below_vwap_reclaim_not_ready",
    }

    out = assess_pre_buy_strategist_refresh_need(state, commander_market_regime="risk_off")

    assert out["requested"] is False
    assert out["refresh_signal"] == "selected_symbol_outside_cached_frame"
    assert out["fresh_cache_signal_override"] is False
    assert out["reason"] == "cache_too_fresh_for_refresh"
