from pathlib import Path

import apps.operator_ui.data_access as data_access


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
