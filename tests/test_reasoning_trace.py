from libs.reporting.reasoning_trace import build_reasoning_trace_from_summaries


def test_build_reasoning_trace_prefers_section_seed_summaries_over_raw_human_fallbacks() -> None:
    trace = build_reasoning_trace_from_summaries(
        commander_summary={},
        strategist_summary={},
        scanner_summary={},
        monitor_summary={},
        report_section_seeds={
            "strategist_summary": {"summary": "Seed strategist summary."},
            "why_this_symbol_was_chosen": {"summary": "Seed scanner summary."},
            "holding_monitoring_story": {"summary": "Seed monitor summary."},
            "final_operator_conclusion": {"summary": "Seed commander summary."},
        },
        market_context_human={"summary": "raw market"},
        scanner_reason_human={"summary": "raw scanner"},
        monitor_reason_human={"summary": "raw monitor"},
        operator_conclusion_human={"summary": "raw conclusion"},
    )

    assert trace["commander_summary"]["summary"] == "Seed commander summary."
    assert trace["strategist_summary"]["summary"] == "Seed strategist summary."
    assert trace["scanner_summary"]["summary"] == "Seed scanner summary."
    assert trace["monitor_summary"]["summary"] == "Seed monitor summary."
