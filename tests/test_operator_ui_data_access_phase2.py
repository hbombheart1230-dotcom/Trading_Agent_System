import json
from pathlib import Path

import apps.operator_ui.data_access as data_access
from apps.operator_ui.data_access_reports import load_trade_report_payloads


def test_data_access_facade_uses_phase2_status_semantics() -> None:
    assert data_access._report_status_label("available") == "AI Report Available"
    assert data_access._report_status_label("pending") == "AI Report Pending"
    assert data_access._report_status_badge_class("failed").endswith("--critical")

    diag = data_access._normalize_ai_report_diagnostics(
        {
            "report_status": "pending",
            "report_reason_code": "awaiting_exit_for_full_report",
        },
        report_exists=False,
        lifecycle_status="open",
        story_type="simulation",
        model_hint="openrouter/free",
    )
    assert diag["report_status"] == "pending"
    assert "exit" in str(diag["next_expected_step"]).lower()


def test_data_access_facade_trade_paths_include_phase2_metadata(tmp_path: Path) -> None:
    bundle_path = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_TEST" / "lifecycle" / "aggregated_execution_bundle.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text("{}", encoding="utf-8")

    paths = data_access._trade_paths_from_bundle(
        bundle_path,
        day_hint="2026-03-18",
        trade_id_hint="TRD_TEST",
    )
    assert str(paths["trade_root"]).endswith("TRD_TEST")
    assert paths["trade_provenance_json"].name == "_provenance.json"
    assert paths["trade_health_json"].name == "_health.json"
    assert paths["trade_artifact_links_json"].name == "_artifact_links.json"


def test_load_trade_report_payloads_prefers_normalized_trade_paths(tmp_path: Path) -> None:
    trade_root = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_TEST"
    normalized_story = trade_root / "ai_trade_report_input.json"
    normalized_lifecycle = trade_root / "lifecycle_bundle.json"
    normalized_report = trade_root / "reports" / "ai_trade_report.json"
    for path, payload in (
        (normalized_story, {"source": "normalized_story"}),
        (normalized_lifecycle, {"source": "normalized_lifecycle"}),
        (normalized_report, {"source": "normalized_report"}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    meta_story = tmp_path / "meta_story.json"
    meta_story.write_text('{"source":"meta_story"}', encoding="utf-8")
    meta_lifecycle = tmp_path / "meta_lifecycle.json"
    meta_lifecycle.write_text('{"source":"meta_lifecycle"}', encoding="utf-8")
    meta_report = tmp_path / "meta_report.json"
    meta_report.write_text('{"source":"meta_report"}', encoding="utf-8")

    out = load_trade_report_payloads(
        {
            "trade_root_path": str(trade_root),
            "trade_story_input_path": str(meta_story),
            "trade_lifecycle_json_path": str(meta_lifecycle),
            "trade_report_json_path": str(meta_report),
        },
        read_json=lambda p: data_access._read_json(Path(p)),
    )
    assert out["story_input_data"]["source"] == "normalized_story"
    assert out["lifecycle_data"]["source"] == "normalized_lifecycle"
    assert out["report_data"]["source"] == "normalized_report"
    assert out["payload_sources"]["story_input"] == "normalized_trade_artifact"
