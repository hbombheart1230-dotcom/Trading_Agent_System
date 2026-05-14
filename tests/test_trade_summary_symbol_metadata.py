from __future__ import annotations

from libs.reporting.trade_report_markdown_clean import (
    build_trade_summary_input_clean,
    render_trade_summary_markdown_clean,
)


def test_trade_summary_renders_symbol_name_and_theme_metadata() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "003060",
        "status": "closed",
        "story_type": "simulation",
        "execution_mode_label": "live",
        "shared_facts": {"symbol": "003060", "status": "closed"},
        "why_this_symbol_was_chosen": {
            "symbol": "003060",
            "stock_name": "에이프로젠바이오로직스",
            "theme_alignment_trace": {
                "theme_source_matched": True,
                "strategist_themes": ["바이오_바이오시밀러/베터", "SI(시스템통합)"],
                "component_symbols_by_theme": {
                    "바이오_바이오시밀러/베터": ["003060", "086900"],
                    "SI(시스템통합)": ["022100"],
                },
            },
        },
        "reporter_evaluation": {"summary": "closed trade 1 trades with 1 wins, 0 losses, avg pnl pct 0.3"},
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert "* 종목: 003060 (에이프로젠바이오로직스)" in markdown
    assert "* 테마: 바이오_바이오시밀러/베터" in markdown
    assert "SI(시스템통합)" not in markdown
    assert summary_input["trade"]["symbol_name"] == "에이프로젠바이오로직스"
    assert summary_input["trade"]["themes"] == ["바이오_바이오시밀러/베터"]
