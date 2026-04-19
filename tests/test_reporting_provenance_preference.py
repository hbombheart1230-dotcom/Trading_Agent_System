from libs.reporting.trade_story_pipeline import build_trade_story_input, compute_evidence_completeness
from scripts import run_live_execution_bundle_report as bundle_script


def test_prefer_canonical_payload_over_fallback() -> None:
    canonical_sources = {
        "artifacts": {
            "scanner": {
                "selected_symbol": "000660",
                "selection_reason": "canonical_rank_1",
            }
        },
        "paths": {"scanner": "/tmp/reports/canonical/2026-03-18/run-1/scanner.json"},
    }
    fallback = {"selected_symbol": "005930", "selection_reason": "event_log"}

    merged, source, path = bundle_script._prefer_canonical_payload(  # type: ignore[attr-defined]
        canonical_sources,
        "scanner",
        fallback,
        fallback_source="event_log",
    )
    assert source == "canonical"
    assert path.endswith("scanner.json")
    assert merged["selected_symbol"] == "000660"
    assert merged["selection_reason"] == "canonical_rank_1"


def test_prefer_normalized_trade_payload_over_canonical() -> None:
    canonical_sources = {
        "artifacts": {
            "scanner": {
                "selected_symbol": "000660",
                "selection_reason": "canonical_rank_1",
            }
        },
        "paths": {"scanner": "/tmp/reports/canonical/2026-03-18/run-1/scanner.json"},
    }
    fallback = {"selected_symbol": "005930", "selection_reason": "event_log"}
    normalized = {"selected_symbol": "035420", "selection_reason": "normalized_trade"}
    merged, source, path = bundle_script._prefer_canonical_payload(  # type: ignore[attr-defined]
        canonical_sources,
        "scanner",
        fallback,
        fallback_source="event_log",
        normalized_payload=normalized,
        normalized_path="/tmp/reports/trades/2026-03-18/TRD_1/lifecycle/aggregated_execution_bundle.json",
    )
    assert source == "normalized_trade_artifact"
    assert path.endswith("aggregated_execution_bundle.json")
    assert merged["selected_symbol"] == "035420"
    assert merged["selection_reason"] == "normalized_trade"


def test_trade_story_input_contains_section_provenance() -> None:
    bundle_out = {
        "day": "2026-03-18",
        "run_id": "run-1",
        "story_contract": {"story_type": "simulation", "execution_mode_label": "simulation (mock broker)"},
        "execution": {"symbol": "000660", "action": "BUY"},
        "market_context_human": {"summary": "context", "bullets": []},
        "scanner_reason_human": {"summary": "scanner", "bullets": []},
        "filters_human": {"summary": "filters", "bullets": []},
        "monitor_reason_human": {"summary": "monitor", "bullets": []},
        "guard_reason_human": {"summary": "guard", "bullets": []},
        "execution_outcome_human": {"summary": "execution", "bullets": []},
        "reporter_status_human": {"summary": "reporter", "bullets": []},
        "operator_conclusion_human": {"summary": "conclusion"},
        "timeline": [],
        "warnings": [],
        "artifacts": {
            "canonical_commander_json": "/tmp/commander.json",
            "canonical_strategist_json": "/tmp/strategist.json",
            "canonical_scanner_json": "/tmp/scanner.json",
            "canonical_monitor_json": "/tmp/monitor.json",
            "canonical_supervisor_json": "/tmp/supervisor.json",
            "canonical_executor_json": "/tmp/executor.json",
            "reporter_analysis_json": "/tmp/reporter.json",
            "agent_pipeline_trace_json": "/tmp/trace.json",
        },
        "evidence_provenance": {
            "commander": "canonical",
            "strategist": "canonical",
            "scanner": "canonical",
            "monitor": "direct_artifact",
            "supervisor": "event_log",
            "executor": "direct_artifact",
            "reporter": "direct_artifact",
        },
    }

    story_input = build_trade_story_input(bundle_out)
    section_provenance = story_input.get("section_provenance")
    assert isinstance(section_provenance, dict)
    assert section_provenance["market_context_human"]["source"] == "canonical"
    assert section_provenance["market_context_human"]["confidence"] == "high"
    assert section_provenance["monitor_reason_human"]["source"] == "direct_artifact"
    assert section_provenance["guard_reason_human"]["source"] == "event_log"
    assert section_provenance["report_section_provenance_seeds"]["market_context_at_entry"]["source"] == "canonical"
    assert section_provenance["report_section_provenance_seeds"]["why_this_symbol_was_chosen"]["artifact_path"].endswith("scanner.json")
    assert story_input["report_section_seeds"]["market_context_at_entry"]["summary"] == "context"
    assert story_input["report_section_seeds"]["strategist_summary"]["summary"] == "context"
    assert story_input["report_section_seeds"]["why_this_symbol_was_chosen"]["summary"] == "scanner"
    assert story_input["report_section_seeds"]["entry_decision"]["summary"] == "scanner"
    assert story_input["report_section_seeds"]["holding_monitoring_story"]["summary"] == "monitor"
    assert story_input["report_section_seeds"]["exit_decision"]["summary"] == "execution"
    assert story_input["report_section_seeds"]["scanner_filters"]["summary"] == "filters"
    assert story_input["report_section_seeds"]["execution_quality"]["summary"] == "execution"
    assert story_input["report_section_seeds"]["guard_approval_result"]["summary"] == "guard"
    assert story_input["report_section_seeds"]["reporter_evaluation"]["summary"] == "reporter"
    assert story_input["report_section_seeds"]["final_operator_conclusion"]["summary"] == "conclusion"


def test_compute_evidence_completeness_reports_missing_sections() -> None:
    completeness = compute_evidence_completeness(
        {
            "market_context_human": {"summary": "ok"},
            "scanner_reason_human": {"summary": "ok"},
            "filters_human": {"summary": "ok"},
            "monitor_reason_human": {},
            "guard_reason_human": {},
            "execution_outcome_human": {"summary": "ok"},
            "operator_conclusion_human": {"summary": "ok"},
        }
    )
    assert "monitor_reason_human" in completeness["missing_sections"]
    assert "guard_reason_human" in completeness["missing_sections"]
    assert completeness["completeness_score"] < 1.0
