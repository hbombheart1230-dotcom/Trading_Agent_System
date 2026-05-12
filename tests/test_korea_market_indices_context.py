from __future__ import annotations

from graphs.nodes.strategist_node import _build_compact_strategist_llm_payload, _extract_market_context_inputs
from libs.reporting.trade_report_markdown_clean import render_trade_summary_markdown_clean
from libs.reporting.trade_story_pipeline import build_market_context_human


def _korea_packet():
    return {
        "status": "ok",
        "source": "kiwoom.ka20009",
        "average_change_pct": 0.75,
        "breadth": 0.22,
        "indices": {
            "KOSPI": {"current": 3100.12, "previous_close": 3080.0, "change_pct": 0.65, "change": 20.12},
            "KOSDAQ": {"current": 850.55, "previous_close": 842.0, "change_pct": 1.02, "change": 8.55},
        },
    }


def test_strategist_market_context_uses_korea_indices_as_fallback_inputs():
    state = {"global_sentiment_signal": {"korea_indices": _korea_packet()}}

    inputs = _extract_market_context_inputs(state)

    assert abs(inputs["index_trend"] - 0.15) < 1e-9
    assert abs(inputs["market_breadth"] - 0.22) < 1e-9


def test_strategist_llm_payload_and_human_context_show_korea_indices():
    packet = _korea_packet()
    compact = _build_compact_strategist_llm_payload(
        {
            "global_sentiment_signal": {"score": 0.1, "status": "ok", "source": "kiwoom.ka20009", "korea_indices": packet},
            "market_context_inputs": {},
        }
    )
    assert compact["global_sentiment_signal"]["korea_indices"]["indices"]["KOSPI"]["previous_close"] == 3080.0

    human = build_market_context_human(
        {
            "market_regime": "trend",
            "market_sentiment": "bullish",
            "playbook": "momentum",
            "global_sentiment_signal": {"score": 0.1, "korea_indices": packet},
        }
    )
    assert "Korea indices" in human["summary"]
    assert human["korea_indices"]["indices"]["KOSDAQ"]["current"] == 850.55


def test_trade_summary_renders_korea_indices_in_market_state():
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "005930",
        "status": "closed",
        "story_type": "normal",
        "execution_mode_label": "live",
        "market_context_at_entry": {
            "summary": "Market regime was trend with a momentum playbook.",
            "market_sentiment": "bullish",
            "playbook": "momentum",
            "korea_indices": _korea_packet(),
        },
        "shared_facts": {"symbol": "005930", "status": "closed"},
        "reporter_evaluation": {"summary": "closed trade 1건 승패 0/1 평균 손익 -0.2%"},
    }

    markdown = render_trade_summary_markdown_clean(report)

    assert "국내 지수: KOSPI 현재 3,100.12 전일 3,080.00 등락률 +0.65%" in markdown
    assert "국내 지수: KOSDAQ 현재 850.55 전일 842.00 등락률 +1.02%" in markdown
