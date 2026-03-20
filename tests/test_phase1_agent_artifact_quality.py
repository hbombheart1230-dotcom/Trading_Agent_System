from __future__ import annotations

from libs.contracts.agent_outputs import (
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
