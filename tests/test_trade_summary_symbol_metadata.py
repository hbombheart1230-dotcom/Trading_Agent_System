from __future__ import annotations

from libs.reporting.trade_report_markdown_clean import (
    _same_day_summary_from_texts,
    render_trade_summary_markdown_with_evaluation_clean,
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


def test_trade_summary_uses_symbol_name_fallback_when_payload_name_missing() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "073490",
        "status": "closed",
        "shared_facts": {"symbol": "073490", "status": "closed"},
        "why_this_symbol_was_chosen": {
            "symbol": "073490",
            "theme_alignment_trace": {
                "component_symbols_by_theme": {
                    "통신장비": ["073490"],
                },
            },
        },
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert "* 종목: 073490 (이노와이어리스)" in markdown
    assert summary_input["trade"]["symbol_name"] == "이노와이어리스"
    assert summary_input["trade"]["themes"] == ["통신장비"]


def test_trade_summary_uses_symbol_metadata_fallback_when_report_has_no_symbol_specific_theme() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "012330",
        "status": "closed",
        "shared_facts": {"symbol": "012330", "status": "closed"},
        "strategist_summary": {
            "themes": ["\ud0dc\uc591\uad11_\uc789\uacf3/\uc6e8\uc774\ud37c/\uc140/\ubaa8\ub4c8", "\ubc18\ub3c4\uccb4_\uc124\uacc4(fabless)"],
        },
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert "* \uc885\ubaa9: 012330 (\ud604\ub300\ubaa8\ube44\uc2a4)" in markdown
    assert "* \ud14c\ub9c8: \uc790\ub3d9\ucc28\ubd80\ud488, \uc804\uae30\ucc28, \uc790\uc728\uc8fc\ud589\ucc28, \uc218\uc18c\ucc28" in markdown
    assert summary_input["trade"]["symbol_name"] == "\ud604\ub300\ubaa8\ube44\uc2a4"
    assert summary_input["trade"]["themes"] == ["\uc790\ub3d9\ucc28\ubd80\ud488", "\uc804\uae30\ucc28", "\uc790\uc728\uc8fc\ud589\ucc28", "\uc218\uc18c\ucc28"]


def test_trade_summary_does_not_use_runner_up_reason_as_symbol_name() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "034220",
        "status": "closed",
        "shared_facts": {"symbol": "034220", "status": "closed"},
        "why_this_symbol_was_chosen": {
            "symbol": "034220",
            "selected_candidate": {
                "symbol": "034220",
                "name": "runner_up \uc911 \ucd5c\uace0 \uc2a4\ucf54\uc5b4(1.00)",
            },
        },
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert "* \uc885\ubaa9: 034220 (LG\ub514\uc2a4\ud50c\ub808\uc774)" in markdown
    assert "runner_up" not in summary_input["trade"]["symbol_name"]
    assert summary_input["trade"]["symbol_name"] == "LG\ub514\uc2a4\ud50c\ub808\uc774"
    assert summary_input["trade"]["themes"] == ["OLED", "LCD", "\ub514\uc2a4\ud50c\ub808\uc774\ud328\ub110"]


def test_trade_summary_does_not_use_entry_reason_as_symbol_name() -> None:
    entry_reason = "pullback_structure_above_vwap_with_volume_confirmation"
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "011930",
        "status": "closed",
        "shared_facts": {"symbol": "011930", "status": "closed"},
        "why_this_symbol_was_chosen": {
            "symbol": "011930",
            "selected_candidate": {
                "symbol": "011930",
                "name": entry_reason,
            },
        },
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert "* \uc885\ubaa9: 011930 (\uc2e0\uc131\uc774\uc5d4\uc9c0)" in markdown
    assert summary_input["trade"]["symbol_name"] == "\uc2e0\uc131\uc774\uc5d4\uc9c0"
    assert entry_reason not in summary_input["trade"]["symbol_name"]


def test_trade_summary_prefers_symbol_prefix_over_news_headline_tail() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "999999",
        "status": "closed",
        "shared_facts": {"symbol": "999999", "status": "closed"},
        "why_this_symbol_was_chosen": {
            "symbol": "999999",
            "summary": (
                "999999: \ud14c\uc2a4\ud2b8\uc885\ubaa9, 1\ubd84\uae30 \uc218\uc8fc "
                "4246\uc5b5\u2026\uc791\ub144 \uc5f0\uac04 \uc218\uc8fc 60% \ub3cc\ud30c"
            ),
        },
    }

    summary_input = build_trade_summary_input_clean(report)

    assert summary_input["trade"]["symbol_name"] == "\ud14c\uc2a4\ud2b8\uc885\ubaa9"


def test_trade_summary_does_not_infer_score_text_as_symbol_name() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "024840",
        "status": "closed",
        "shared_facts": {"symbol": "024840", "status": "closed"},
        "why_this_symbol_was_chosen": {
            "summary": "024840 (\uc885\ud569 \uc810\uc218 1.401 (\ucd5c\uace0))",
        },
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert "* \uc885\ubaa9: 024840 (KBI\uba54\ud0c8)" in markdown
    assert "\uc885\ud569 \uc810\uc218" not in summary_input["trade"]["symbol_name"]
    assert summary_input["trade"]["symbol_name"] == "KBI\uba54\ud0c8"
    assert summary_input["trade"]["themes"] == ["\uc804\uc120", "\uad6c\ub9ac", "\uc804\ub825\uc124\ube44"]


def test_trade_summary_input_contains_quant_tactic_surface() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "005930",
        "status": "closed",
        "shared_facts": {"symbol": "005930", "status": "closed"},
        "monitor_snapshot": {
            "entry_quant_decision": {
                "tactic_id": "vwap_reclaim_pullback",
                "decision": "block_recommended",
                "blockers": ["cost_edge_fail"],
            },
            "exit_quant_decision": {
                "tactic_id": "vwap_reclaim_pullback",
                "decision": "exit_aligned",
            },
        },
    }

    summary_input = build_trade_summary_input_clean(report)

    assert summary_input["quant_tactic"]["tactic_id"] == "vwap_reclaim_pullback"
    assert summary_input["quant_tactic"]["entry_quant_decision"]["decision"] == "block_recommended"


def test_trade_summary_input_and_diagnostics_surface_broker_alignment() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "005930",
        "status": "closed",
        "shared_facts": {"symbol": "005930", "status": "closed"},
        "broker_alignment": {
            "status": "mismatch",
            "generated_at": "2026-05-22T07:00:00+00:00",
            "report_json_path": "reports/reconciliation/broker_trade_reconciliation_2026-05-22.json",
            "summary": {
                "local_total": 4,
                "broker_total": 7,
                "matched_by_ord_no": 4,
                "missing_in_local_total": 3,
                "missing_in_broker_total": 0,
            },
        },
    }

    summary_input = build_trade_summary_input_clean(report)
    markdown = render_trade_summary_markdown_with_evaluation_clean(report, summary_input)

    assert summary_input["broker_alignment"]["status"] == "mismatch"
    assert summary_input["broker_alignment"]["local_total"] == 4
    assert summary_input["broker_alignment"]["broker_total"] == 7
    assert "* 브로커 주문 정합성: mismatch / local 4 / broker 7 / local누락 3 / broker누락 0" in markdown


def test_trade_summary_evaluation_diagnostics_replaces_stale_runner_up_symbol_name() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "034220",
        "status": "closed",
        "shared_facts": {"symbol": "034220", "status": "closed"},
    }
    evaluation = {
        "trade": {
            "symbol": "034220",
            "symbol_name": "runner_up \uc911 \ucd5c\uace0 \uc2a4\ucf54\uc5b4(1.00)",
            "theme": "OLED, LCD, \ub514\uc2a4\ud50c\ub808\uc774\ud328\ub110",
        },
        "truth_surface": {},
        "decision_flow": {},
        "deterministic_findings": {},
    }

    markdown = render_trade_summary_markdown_with_evaluation_clean(report, evaluation)

    assert "* \ub300\uc0c1 \uc885\ubaa9: 034220 (LG\ub514\uc2a4\ud50c\ub808\uc774)" in markdown
    assert "runner_up" not in markdown


def test_trade_summary_does_not_use_symbol_news_title_as_symbol_name() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "005930",
        "status": "closed",
        "shared_facts": {"symbol": "005930", "status": "closed"},
        "market_context_at_entry": {
            "symbol_news_titles": [
                "005930: \ucd5c\uc2b9\ud638 \uc0bc\uc131\uc804\uc790 \ub178\uc870\uc704\uc6d0\uc7a5 "
                "\u201c\uc870\ud569\uc6d0 \ucd5c\ub300\ud55c \ub9cc\uc871\ud560 \uc548 \ub9cc\ub4e4\uaca0\ub2e4\u201d"
            ],
        },
    }

    markdown = render_trade_summary_markdown_clean(report)
    summary_input = build_trade_summary_input_clean(report)

    assert summary_input["trade"]["symbol_name"] == "\uc0bc\uc131\uc804\uc790"
    assert "\uc0bc\uc131\uc804\uc790" in markdown
    assert "\ucd5c\uc2b9\ud638" not in summary_input["trade"]["symbol_name"]
    assert "* \uc885\ubaa9: 005930 (\uc0bc\uc131\uc804\uc790)" in markdown


def test_trade_summary_does_not_relabel_market_themes_as_symbol_themes() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "090710",
        "status": "closed",
        "shared_facts": {"symbol": "090710", "status": "closed"},
        "strategist_summary": {
            "themes": ["SI(시스템통합)", "AMOLED_소재", "셋톱박스"],
            "preferred_themes": ["SI(시스템통합)"],
        },
        "why_this_symbol_was_chosen": {
            "symbol": "090710",
            "theme_alignment_trace": {
                "strategist_themes": ["SI(시스템통합)", "AMOLED_소재"],
            },
        },
    }

    summary_input = build_trade_summary_input_clean(report)

    assert summary_input["trade"]["theme"] == ""
    assert summary_input["trade"]["themes"] == []


def test_trade_summary_same_day_single_trade_prefers_current_truth_pct() -> None:
    report = {
        "trade_id": "TRD_TEST",
        "symbol": "090710",
        "status": "closed",
        "shared_facts": {"symbol": "090710", "status": "closed"},
        "truth_surface": {
            "status": {"status": "closed"},
            "pnl": {"value": -51756, "pct": -0.017018841866364147},
        },
        "reporter_evaluation": {
            "summary": "closed trade 1 trades with 0 wins, 1 losses, avg pnl pct -0.059",
        },
    }

    summary_input = build_trade_summary_input_clean(report)
    summary = summary_input["same_day_context"]["summary"]

    assert "-1.70%" in summary
    assert "-0.059" not in summary


def test_same_day_summary_converts_reporter_ratio_average_and_clamps_unknown() -> None:
    summary = _same_day_summary_from_texts(
        [
            (
                "Same-day closed trade reports show 15 trades with 2 wins, "
                "11 losses, 2 flat, 2 unknown pnl, avg pnl pct -0.0107."
            )
        ]
    )

    assert summary == "15건 중 2승 / 11패 / 2건 보합 / 확인분 평균 -1.07%"
