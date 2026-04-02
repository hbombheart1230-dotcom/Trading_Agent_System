from libs.reporting.strategy_read_model import (
    build_news_symbol_linkage_view,
    build_recent_strategist_feedback_window,
    build_strategist_feedback_input_view,
)


def test_build_news_symbol_linkage_view_connects_targets_hints_and_selected_symbol() -> None:
    out = build_news_symbol_linkage_view(
        strategist_summary={
            "news_query_targets": ["반도체", "코스피", "AI"],
            "candidate_symbols_hint": ["005930", "000660"],
            "candidate_hypotheses": [
                {"symbol": "005930", "hypothesis": "semiconductor leader with strong memory demand"},
                {"symbol": "000660", "hypothesis": "AI server beta candidate"},
            ],
            "news_evidence_ranked": {
                "market_news_ranked": [{"title": "반도체 업종 강세"}],
                "candidate_news_ranked": [
                    {"symbol": "005930", "title": "삼성전자 HBM 기대감 확대"},
                    {"symbol": "000660", "title": "하이닉스 수급 개선"},
                ],
            },
        },
        selected_symbol="005930",
        top_ranked_symbols=["005930", "000660"],
    )

    assert out["selected_symbol"] == "005930"
    assert out["runner_up_symbol"] == "000660"
    assert out["selected_symbol_in_candidate_hints"] is True
    assert out["runner_up_symbol_in_candidate_hints"] is True
    assert out["linkage_strength"] == "strong"
    assert out["market_headlines"] == ["반도체 업종 강세"]
    assert out["selected_symbol_headlines"] == ["삼성전자 HBM 기대감 확대"]
    assert out["runner_up_symbol_headlines"] == ["하이닉스 수급 개선"]
    assert out["selected_vs_runner_up"]["runner_up_symbol"] == "000660"
    assert "Selected 005930 vs runner-up 000660" in out["selected_vs_runner_up"]["comparison_summary"]
    assert out["linked_candidates"][0]["symbol"] == "005930"
    assert "headline_link" in out["linked_candidates"][0]["linkage_flags"]
    assert "candidate_hint" in out["linked_candidates"][0]["linkage_flags"]


def test_build_strategist_feedback_input_view_summarizes_trade_story_for_reuse() -> None:
    out = build_strategist_feedback_input_view(
        {
            "symbol": "005930",
            "status": "closed",
            "action": "SELL",
            "strategist_candidate_hints": ["005930", "000660"],
            "improvement_points": ["late entry on second push", "volume persistence faded early"],
            "market_context_human": {
                "playbook": "pullback",
                "market_regime": "neutral",
                "market_sentiment": "bearish",
                "news_query_targets": ["KOSPI", "semiconductor"],
                "market_headlines": ["Chip leaders outperformed despite weak breadth."],
                "symbol_headlines": ["Samsung Electronics drew foreign inflows."],
                "strategist_evidence_trace": {"key_events": ["breadth weak but leaders held up"]},
            },
            "scanner_reason_human": {
                "selected_symbol": "005930",
                "selection_reason": "top value plus semiconductor theme alignment",
            },
            "monitor_reason_human": {"summary": "Holding posture stayed constructive until VWAP failure."},
            "operator_conclusion_human": {
                "summary": "Trade closed after structure weakened.",
                "watch_next": ["watch reclaim quality", "watch follow-through volume"],
                "thesis_invalidation": ["VWAP failure after breakout"],
            },
            "entry_summary": {"reason_human": "Breakout entry confirmed after monitor validation."},
            "exit_summary": {"reason_human": "VWAP breakdown confirmed the exit."},
            "news_symbol_linkage": {
                "selected_symbol": "005930",
                "news_query_targets": ["KOSPI", "semiconductor"],
                "candidate_symbols_hint": ["005930", "000660"],
                "market_headlines": ["Chip leaders outperformed despite weak breadth."],
                "selected_symbol_headlines": ["Samsung Electronics drew foreign inflows."],
                "linkage_strength": "strong",
                "selected_vs_runner_up": {
                    "comparison_summary": "Selected 005930 vs runner-up 000660: headlines 1 vs 0, hint_match true vs true.",
                },
            },
        }
    )

    assert out["schema_version"] == "strategist_feedback_input.v1"
    assert out["selected_symbol"] == "005930"
    assert out["playbook"] == "pullback"
    assert out["trade_status"] == "closed"
    assert out["final_action"] == "SELL"
    assert out["candidate_symbols_hint"] == ["005930", "000660"]
    assert out["linkage_strength"] == "strong"
    assert "runner-up 000660" in out["selected_vs_runner_up_summary"]
    assert out["entry_summary"] == "Breakout entry confirmed after monitor validation."
    assert out["entry_pattern_type"] == "breakout"
    assert out["entry_timing_quality"] == "late"
    assert out["entry_confirmation_quality"] == "moderate"
    assert out["exit_summary"] == "VWAP breakdown confirmed the exit."
    assert out["exit_pattern_type"] == "vwap_breakdown"
    assert out["exit_quality"] == "reactive"
    assert out["thesis_invalidation_code"] == "vwap_loss"
    assert "late_entry" in out["improvement_tags"]
    assert "vwap_loss" in out["improvement_tags"]
    assert out["watch_next"] == ["watch reclaim quality", "watch follow-through volume"]
    assert out["improvement_points"][0] == "late entry on second push"


def test_build_strategist_feedback_input_view_keeps_unknown_safe_defaults_when_evidence_is_weak() -> None:
    out = build_strategist_feedback_input_view(
        {
            "symbol": "000660",
            "status": "open",
            "action": "HOLD",
            "market_context_human": {"playbook": "defensive"},
            "scanner_reason_human": {"selected_symbol": "000660"},
            "monitor_reason_human": {"summary": "Observation continues."},
            "operator_conclusion_human": {"summary": "Still monitoring."},
            "news_symbol_linkage": {"selected_symbol": "000660"},
        }
    )

    assert out["entry_pattern_type"] == "unknown"
    assert out["entry_timing_quality"] == "unknown"
    assert out["entry_confirmation_quality"] == "unknown"
    assert out["exit_pattern_type"] == "unknown"
    assert out["exit_quality"] == "unknown"
    assert out["thesis_invalidation_code"] == "unknown"
    assert out["improvement_tags"] == []
    assert out["review_flags"] == ["needs_human_review"]


def test_build_recent_strategist_feedback_window_counts_patterns_actions_and_tags() -> None:
    out = build_recent_strategist_feedback_window(
        [
            {
                "trade_id": "TRD_A",
                "selected_symbol": "005930",
                "playbook": "pullback",
                "trade_status": "closed",
                "final_action": "SELL",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "take_profit",
                "thesis_invalidation_code": "unknown",
                "improvement_tags": ["late_entry", "insufficient_confirmation"],
                "review_flags": ["high_quality_trade"],
                "result_pct": 1.25,
            },
            {
                "trade_id": "TRD_B",
                "selected_symbol": "000660",
                "playbook": "defensive",
                "trade_status": "closed",
                "final_action": "SELL",
                "entry_pattern_type": "pullback",
                "exit_pattern_type": "vwap_breakdown",
                "thesis_invalidation_code": "vwap_loss",
                "improvement_tags": ["late_entry"],
                "review_flags": ["needs_human_review"],
                "result_pct": -0.8,
            },
            {
                "trade_id": "TRD_C",
                "selected_symbol": "005930",
                "playbook": "pullback",
                "trade_status": "open",
                "final_action": "HOLD",
                "entry_pattern_type": "unknown",
                "exit_pattern_type": "unknown",
                "thesis_invalidation_code": "unknown",
                "improvement_tags": [],
                "review_flags": [],
            },
        ],
        window_size=10,
    )

    assert out["window_size"] == 10
    assert out["trades_considered"] == 3
    assert out["symbols"] == ["005930", "000660"]
    assert out["playbooks_seen"] == ["pullback", "defensive"]
    assert out["trade_status_counts"] == {"closed": 2, "open": 1}
    assert out["final_action_counts"] == {"SELL": 2, "HOLD": 1}
    assert out["entry_pattern_counts"] == {"breakout": 1, "pullback": 1, "unknown": 1}
    assert out["exit_pattern_counts"] == {"unknown": 1, "take_profit": 1, "vwap_breakdown": 1}
    assert out["thesis_invalidation_counts"] == {"unknown": 2, "vwap_loss": 1}
    assert out["improvement_tag_counts"] == {"late_entry": 2, "insufficient_confirmation": 1}
    assert out["review_flag_counts"] == {"high_quality_trade": 1, "needs_human_review": 1}
    assert out["known_result_trade_count"] == 2
    assert abs(float(out["average_result_pct"]) - 0.225) < 1e-9
    assert out["recent_trade_refs"][0]["trade_id"] == "TRD_A"
    assert out["recent_trade_refs"][1]["result_pct"] == -0.8


def test_build_recent_strategist_feedback_window_stays_unknown_safe_for_empty_or_partial_input() -> None:
    empty = build_recent_strategist_feedback_window([], window_size=5)
    assert empty["window_size"] == 5
    assert empty["trades_considered"] == 0
    assert empty["trade_status_counts"] == {}
    assert empty["recent_trade_refs"] == []
    assert empty["average_result_pct"] is None

    partial = build_recent_strategist_feedback_window(
        [
            {
                "trade_id": "TRD_X",
                "selected_symbol": "003280",
            }
        ],
        window_size=5,
    )
    assert partial["trades_considered"] == 1
    assert partial["entry_pattern_counts"] == {"unknown": 1}
    assert partial["exit_pattern_counts"] == {"unknown": 1}
    assert partial["review_flag_counts"] == {}
    assert partial["recent_trade_refs"][0]["symbol"] == "003280"
