from __future__ import annotations

from libs.contracts.agent_outputs import (
    build_commander_output_artifact,
    build_monitor_output_artifact,
    build_scanner_output_artifact,
    build_strategist_output_artifact,
)


def test_strategist_artifact_contains_phase1_sections() -> None:
    state = {
        "run_id": "run-s1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "strategist_output": {
            "market_regime": "risk_on",
            "market_sentiment": "bullish",
            "playbook": "breakout",
            "themes": ["semiconductor"],
            "avoid_themes": ["high_gap_speculative"],
            "strategy_policy": {"market_policy": {"playbook": "breakout"}},
            "monitor_guidance": "hold_through_noise",
            "risk_tone": "normal",
            "trade_aggressiveness": "medium",
            "market_context_inputs": {"index_trend": 0.3},
            "news_query_reasoning": "macro and sector alignment",
            "news_query_targets": ["semiconductor"],
        },
        "strategist_llm": {
            "status": "ok",
            "model": "minimax/minimax-m2.5",
            "prompt_hash": "prompt-hash",
            "response_hash": "response-hash",
            "prompt_ref": "reports/llm/2026-03-18/run-s1/strategist/prompt.json",
            "response_ref": "reports/llm/2026-03-18/run-s1/strategist/response.json",
        },
    }
    artifact = build_strategist_output_artifact(state)
    assert artifact["day"] == "2026-03-18"
    assert isinstance(artifact.get("market_context"), dict)
    assert isinstance(artifact.get("news_context"), dict)
    assert isinstance(artifact.get("strategy_frame"), dict)
    assert isinstance(artifact.get("policy_selected"), dict)
    assert isinstance(artifact.get("llm_trace"), dict)
    assert isinstance(artifact.get("decision_summary"), dict)
    assert artifact["llm_trace"]["prompt_hash"] == "prompt-hash"
    assert artifact["llm_trace"]["response_hash"] == "response-hash"


def test_scanner_artifact_contains_filter_funnel_and_selection_reason_detail() -> None:
    state = {
        "run_id": "run-scan-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "scanner_output": {
            "candidate_pool_size": 2,
            "candidate_count": 2,
            "candidate_source": "kiwoom_market_data",
        },
        "scanner_candidate_pool": {
            "candidate_source": "kiwoom_market_data",
            "candidate_pool_before_filter": 5,
            "candidate_pool_after_filter": 2,
            "theme_filter_applied": True,
            "avoid_filter_applied": True,
        },
        "ranked_candidates": [
            {
                "symbol": "005930",
                "score_total": 1.32,
                "risk_score": 0.21,
                "confidence": 0.82,
                "why": "top ranked",
                "score_breakdown": {"top_value": 0.8, "risk_penalty": -0.1},
            },
            {
                "symbol": "000660",
                "score_total": 1.01,
                "risk_score": 0.34,
                "confidence": 0.74,
                "why": "runner up",
                "score_breakdown": {"top_value": 0.5, "risk_penalty": -0.2},
            },
        ],
        "selected": {
            "symbol": "005930",
            "score_total": 1.32,
            "risk_score": 0.21,
            "confidence": 0.82,
            "why": "value and theme alignment",
            "score_breakdown": {"top_value": 0.8, "risk_penalty": -0.1},
            "candidate": {"source_scores": {"top_value": 2.1, "sector_theme": 1.7}},
        },
        "scanner_runner_up_reasons": [{"symbol": "000660", "why_lost": ["lower total score"]}],
    }
    artifact = build_scanner_output_artifact(state)
    assert isinstance(artifact.get("candidate_pool_snapshot"), dict)
    assert isinstance(artifact.get("filter_funnel"), dict)
    assert isinstance(artifact.get("selection_reason_detail"), dict)
    detail = artifact["selection_reason_detail"]
    assert detail["selected_symbol"] == "005930"
    assert "selected_score_total" in detail
    assert "margin_vs_second" in detail
    assert isinstance(detail.get("critical_positive_factors"), list)
    assert isinstance(detail.get("critical_negative_factors"), list)
    assert isinstance(artifact.get("rejection_summary"), list)


def test_monitor_artifact_contains_evaluation_and_action_sections() -> None:
    state = {
        "run_id": "run-mon-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 1},
        "monitor_posture": "holding",
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "hold"},
        "monitor_entry": {
            "triggered": False,
            "pattern": "",
            "reason": "no_breakout_signal",
            "failed_checks": ["breakout_ok"],
            "passed_checks": ["vwap_hold_ok"],
            "threshold_margins": {"volume_ratio": {"actual": 0.7, "limit": 0.8}},
            "guard_blocked": False,
            "confidence": 0.65,
        },
        "monitor_exit": {
            "symbol": "005930",
            "price": 70500,
            "avg_price": 70000,
            "peak_price": 71200,
            "monitor_reason": "hold",
            "reason": "",
            "active_exit_axis": "vwap_hold",
            "watch_axes": ["vwap", "prior_low"],
            "triggered": False,
            "sell_guard_blocked": False,
            "thresholds": {"stop_loss_pct": 0.02, "take_profit_pct": 0.03},
        },
    }
    artifact = build_monitor_output_artifact(state)
    assert isinstance(artifact.get("position_snapshot"), dict)
    assert isinstance(artifact.get("monitor_evaluation"), dict)
    assert isinstance(artifact.get("monitor_action_decision"), dict)
    assert "triggered_rules" in artifact["monitor_evaluation"]
    assert "blocked_rules" in artifact["monitor_evaluation"]
    assert "action_reason_human" in artifact["monitor_action_decision"]
    assert artifact.get("decision_phase") == "hold"
    assert artifact.get("decision_action") == "hold"
    assert artifact.get("decision_status") in {"skipped", "blocked", "unavailable"}
    assert isinstance(artifact.get("secondary_reason_codes"), list)
    assert isinstance(artifact.get("threshold_snapshot"), dict)
    assert isinstance(artifact.get("signal_snapshot"), dict)
    assert isinstance(artifact.get("market_snapshot_refs"), dict)
    assert artifact.get("intent_emitted") is False
    decision_summary = str(artifact.get("decision_summary") or "")
    assert decision_summary.startswith("Hold:")
    assert len(decision_summary) <= 120


def test_monitor_artifact_marks_buy_intent_with_entry_phase() -> None:
    state = {
        "run_id": "run-mon-buy",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "BUY", "entry_exit_reason": "pullback_reclaim_confirmed"},
        "monitor_entry": {
            "evaluated": True,
            "triggered": True,
            "pattern": "pullback_vwap_reclaim",
            "reason": "pullback_reclaim_confirmed",
            "signal_chain": ["reclaim", "volume_confirmation"],
            "thresholds": {"volume_ratio_min": 0.8},
            "metrics": {"volume_ratio": 1.1},
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "thresholds": {}, "watch_axes": []},
        "intents": [{"intent_id": "intent-buy-1", "side": "BUY", "symbol": "005930"}],
    }
    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "entry"
    assert artifact.get("decision_action") == "buy"
    assert artifact.get("decision_status") == "ok"
    assert artifact.get("intent_emitted") is True
    assert artifact.get("intent_id") == "intent-buy-1"
    assert artifact.get("evidence_quality") in {"strong", "partial"}
    decision_summary = str(artifact.get("decision_summary") or "")
    assert decision_summary.startswith("Entry:")
    assert "BUY" in decision_summary


def test_monitor_artifact_marks_sell_intent_with_exit_phase() -> None:
    state = {
        "run_id": "run-mon-sell",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 1},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "SELL", "entry_exit_reason": "confirmed_exit_signal"},
        "monitor_entry": {"evaluated": False, "triggered": False},
        "monitor_exit": {
            "symbol": "005930",
            "price": 70100,
            "reason": "vwap_breakdown",
            "monitor_reason": "confirmed_exit_signal",
            "triggered": True,
            "exit_signal_detected": True,
            "watch_axes": ["vwap"],
            "thresholds": {"vwap_breakdown_pct": 0.002},
        },
        "monitor_exit_decision_detail": {"triggered_rule": "vwap_breakdown"},
        "intents": [{"intent_id": "intent-sell-1", "side": "SELL", "symbol": "005930"}],
    }
    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "exit"
    assert artifact.get("decision_action") == "sell"
    assert artifact.get("decision_status") == "ok"
    assert artifact.get("primary_reason_code") in {"vwap_breakdown", "confirmed_exit_signal"}
    assert artifact.get("intent_emitted") is True
    decision_summary = str(artifact.get("decision_summary") or "")
    assert decision_summary.startswith("Exit:")


def test_monitor_artifact_no_intent_summary_is_human_readable() -> None:
    state = {
        "run_id": "run-mon-noop",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "too_extended_from_vwap"},
        "monitor_entry": {
            "evaluated": True,
            "triggered": False,
            "reason": "too_extended_from_vwap",
            "failed_checks": ["extension_ok"],
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "reason": "", "thresholds": {}, "watch_axes": []},
        "intents": [],
    }
    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "no_intent"
    summary = str(artifact.get("decision_summary") or "")
    assert summary.startswith("No action:")
    assert len(summary) <= 120


def test_commander_artifact_routes_monitor_only_and_tracks_flags() -> None:
    state = {
        "run_id": "run-cmd-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "runtime_fast_path": {"reason": "holding_position_monitor_only"},
        "portfolio_snapshot": {"positions": [{"symbol": "005930"}, {"symbol": "000660"}], "cash": 1000},
        "portfolio_preflight": {"status": "ok", "blocked": False},
    }
    artifact = build_commander_output_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain_monitor_only",
        status="ok",
        reason="holding_position_monitor_only",
    )
    assert artifact.get("selected_route") == "monitor_only"
    assert artifact.get("open_position_count") == 2
    assert artifact.get("open_position_symbols") == ["005930", "000660"]
    assert artifact.get("runtime_mode") == "integrated_chain"
    assert artifact.get("runtime_phase") == "session"
    assert isinstance(artifact.get("route_reason_codes"), list)
    assert artifact.get("cooldown_applied") is False


def test_commander_artifact_routes_blocked_with_cooldown() -> None:
    state = {
        "run_id": "run-cmd-2",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "cooldown_wait",
        "runtime_transition": "cooldown",
        "runtime_resilience_state": {"incident_count": 3, "cooldown_until_epoch": 1773000000},
        "portfolio_snapshot": {"positions": [], "cash": 1000},
        "portfolio_preflight": {"status": "ok", "blocked": False},
    }
    artifact = build_commander_output_artifact(
        state,
        mode="graph_spine",
        phase="session",
        path="session_strategist_blocked",
        status="blocked",
        reason="incident_threshold_cooldown",
    )
    assert artifact.get("selected_route") == "blocked"
    assert artifact.get("cooldown_applied") is True
    incident_state = artifact.get("incident_state") if isinstance(artifact.get("incident_state"), dict) else {}
    assert incident_state.get("incident_count") == 3
    assert artifact.get("strategist_blocked") is True
