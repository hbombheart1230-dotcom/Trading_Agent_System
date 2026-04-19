from pathlib import Path

from libs.reporting.llm_artifacts import trade_artifact_paths


def test_report_trades_path_contract_is_backward_compatible() -> None:
    reports_root = Path("reports")
    day = "2026-03-18"
    trade_id = "TRD_20260318_000660_01"
    paths = trade_artifact_paths(reports_root, day, trade_id)

    assert paths["trade_root"] == reports_root / "trades" / day / trade_id
    assert paths["legacy_trade_root"] == reports_root / "trades" / "2026" / "03" / trade_id

    # Legacy files remain unchanged for existing readers.
    assert paths["legacy_trade_story_input_json"].name == "trade_story_input.json"
    assert paths["legacy_trade_report_json"].name == "trade_report.json"
    assert paths["legacy_trade_report_md"].name == "trade_report.md"
    assert paths["legacy_trade_lifecycle_json"].name == "trade_lifecycle.json"
    assert paths["legacy_aggregated_execution_bundle_json"].name == "aggregated_execution_bundle.json"
    # New metadata files are additive under the same trade root.
    assert paths["trade_provenance_json"] == paths["trade_root"] / "_provenance.json"
    assert paths["trade_health_json"] == paths["trade_root"] / "_health.json"
    assert paths["trade_artifact_links_json"] == paths["trade_root"] / "_artifact_links.json"
    assert paths["ai_trade_report_compact_input_json"] == paths["trade_root"] / "ai_trade_report_compact_input.json"
    assert paths["brief_compact_input_json"] == paths["trade_root"] / "brief_compact_input.json"
    assert paths["brief_json"] == paths["trade_root"] / "reports" / "operator_brief.json"
    assert paths["brief_md"] == paths["trade_root"] / "reports" / "operator_brief.md"
    assert paths["brief_llm_response_json"] == paths["trade_root"] / "reports" / "brief_llm_response.json"
