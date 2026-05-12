from pathlib import Path

from libs.reporting.llm_artifacts import iter_trade_dirs, trade_artifact_paths
from libs.reporting.trade_story_pipeline import build_lifecycle_bundle


def _base_kwargs():
    return {
        "day": "2026-03-20",
        "trade_id": "TRD_20260320_005930_01",
        "run_id": "run-123",
        "symbol": "005930",
        "strategist_summary": {"playbook": "pullback"},
        "scanner_summary": {"selected_symbol": "005930"},
        "monitor_summary": {"posture": "HOLD"},
        "commander_summary": {"final_runtime_path": "trading"},
        "canonical_refs": {"canonical_strategist": "reports/canonical/2026-03-20/run-123/strategist.json"},
        "llm_refs": {"strategist_response_ref": "reports/llm/2026-03-20/run-123/strategist/response.json"},
        "artifact_links": {"lifecycle_bundle": "reports/trades/2026-03-20/TRD_20260320_005930_01/lifecycle_bundle.json"},
    }


def test_build_lifecycle_bundle_full_data() -> None:
    bundle = build_lifecycle_bundle(
        **_base_kwargs(),
        lifecycle={
            "entry": {"run_id": "run-entry", "action": "BUY"},
            "holding": {"holding_events": [{"run_id": "run-hold", "posture": "HOLD"}]},
            "exit": {"run_id": "run-exit", "action": "SELL"},
            "summary": {"holding_duration": "00:12:31", "exit_reason_human": "take_profit"},
        },
        story_input={
            "strategist_evidence": {"market_context_snapshots": [{}]},
            "scanner_evidence": {"candidate_selection_reasons": [{}]},
            "monitor_timeline": {"threshold_snapshots": [{}]},
            "entry_summary": {"reason_human": "reclaim"},
            "holding_summary": {"run_ids": ["run-hold"]},
            "exit_summary": {"reason_human": "take_profit"},
            "monitor_reason_human": {"pnl": 1000.0, "current_drawdown": 0.014},
        },
        diagnostics={
            "strategist_llm_status": "ok",
            "llm_brief_status": "ok",
            "ai_trade_report_status": "salvaged",
        },
    )

    assert bundle["schema_version"] == "lifecycle_bundle.v1"
    assert bundle["lifecycle"]["entry"]["run_id"] == "run-entry"
    assert bundle["lifecycle"]["hold"][0]["run_id"] == "run-hold"
    assert bundle["lifecycle"]["exit"]["run_id"] == "run-exit"
    assert bundle["missing"]["entry_missing"] is False
    assert bundle["missing"]["hold_missing"] is False
    assert bundle["missing"]["exit_missing"] is False
    assert bundle["llm_summary"]["strategist_llm_status"] == "ok"
    assert bundle["llm_summary"]["brief_llm_status"] == "ok"
    assert bundle["llm_summary"]["ai_report_status"] == "salvaged"


def test_build_lifecycle_bundle_defaults_llm_status_to_skipped() -> None:
    bundle = build_lifecycle_bundle(
        **_base_kwargs(),
        lifecycle={
            "entry": {"run_id": "run-entry", "action": "BUY"},
            "holding": {"holding_events": []},
            "exit": {},
            "summary": {},
        },
        story_input={},
        diagnostics={},
    )

    assert bundle["llm_summary"]["strategist_llm_status"] == "skipped"
    assert bundle["llm_summary"]["brief_llm_status"] == "skipped"
    assert bundle["llm_summary"]["ai_report_status"] == "skipped"


def test_build_lifecycle_bundle_marks_missing_hold_and_exit() -> None:
    bundle = build_lifecycle_bundle(
        **_base_kwargs(),
        lifecycle={
            "entry": {"run_id": "run-entry", "action": "BUY"},
            "holding": {},
            "exit": {},
            "summary": {},
        },
        story_input={"entry_summary": {"reason_human": "breakout"}},
        diagnostics={"strategist_llm_status": "ok"},
    )

    assert bundle["missing"]["entry_missing"] is False
    assert bundle["missing"]["hold_missing"] is True
    assert bundle["missing"]["exit_missing"] is True
    assert bundle["trade_outcome"]["exit_reason"] == ""
    assert 0.0 <= float(bundle["evidence_summary"]["completeness_score"]) <= 1.0


def test_trade_artifact_paths_use_phase3_trade_layout_and_keep_legacy_refs() -> None:
    paths = trade_artifact_paths(Path("reports"), "2026-03-20", "TRD_20260320_005930_01")

    assert paths["lifecycle_bundle_json"].as_posix().endswith("reports/trades/2026-03-20/TRD_20260320_005930_01/lifecycle_bundle.json")
    assert paths["ai_trade_report_json"].as_posix().endswith("reports/trades/2026-03-20/TRD_20260320_005930_01/reports/ai_trade_report.json")
    assert paths["brief_json"].as_posix().endswith("reports/trades/2026-03-20/TRD_20260320_005930_01/reports/operator_brief.json")
    assert paths["strategist_llm_response_json"].as_posix().endswith("reports/trades/2026-03-20/TRD_20260320_005930_01/reports/strategist_llm_response.json")
    assert paths["legacy_trade_lifecycle_json"].as_posix().endswith("reports/trades/2026/03/TRD_20260320_005930_01/trade_lifecycle.json")


def test_trade_artifact_paths_resolve_hour_bucketed_existing_trade(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_id = "TRD_20260320_005930_01"
    trade_root = reports_root / "trades" / "2026-03-20" / "0900" / trade_id
    trade_root.mkdir(parents=True)
    (trade_root / "lifecycle_bundle.json").write_text("{}", encoding="utf-8")

    paths = trade_artifact_paths(reports_root, "2026-03-20", trade_id)

    assert paths["trade_root"] == trade_root
    assert iter_trade_dirs(reports_root / "trades" / "2026-03-20") == [trade_root]
