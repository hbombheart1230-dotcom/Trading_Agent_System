from __future__ import annotations

import json
from pathlib import Path

import scripts.check_trade_report_runtime_regression as mod
from libs.reporting.llm_artifacts import trade_artifact_paths


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_trade(
    reports_root: Path,
    *,
    day: str,
    trade_id: str,
    entry: dict,
    hold: dict,
    exit_payload: dict,
    lifecycle_bundle: dict,
    story_input: dict,
    report: dict,
) -> None:
    paths = trade_artifact_paths(reports_root, day, trade_id)
    _write_json(paths["entry_json"], entry)
    _write_json(paths["hold_json"], hold)
    _write_json(paths["exit_json"], exit_payload)
    _write_json(paths["lifecycle_bundle_json"], lifecycle_bundle)
    _write_json(paths["ai_trade_report_input_json"], story_input)
    _write_json(paths["ai_trade_report_json"], report)
    paths["ai_trade_report_md"].parent.mkdir(parents=True, exist_ok=True)
    paths["ai_trade_report_md"].write_text("# report\n", encoding="utf-8")
    _write_json(paths["trade_provenance_json"], {"trade_origin": lifecycle_bundle.get("trade_origin", ""), "lifecycle_completeness": lifecycle_bundle.get("lifecycle_completeness", "")})
    _write_json(paths["trade_health_json"], {"ok": True})


def test_validate_trade_artifact_chain_flags_broken_closed_trade(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-16"
    trade_id = "TRD_20260416_000660_99"
    _seed_trade(
        reports_root,
        day=day,
        trade_id=trade_id,
        entry={
            "run_id": "",
            "ts": "",
            "action": "BUY",
            "symbol": "000660",
            "qty": 1,
            "reason_human": "recovered entry",
            "scanner_context": {"selected_symbol": "000660"},
        },
        hold={
            "hold_duration": "00:00:00",
            "hold_duration_sec": 0,
        },
        exit_payload={
            "run_id": "run-sell",
            "ts": "2026-04-16T00:08:48+00:00",
            "action": "SELL",
            "symbol": "000660",
            "reason_human": "peak_drawdown",
        },
        lifecycle_bundle={
            "trade_lifecycle_status": "closed",
            "linked_run_ids": [],
            "same_day_reporter_linkage": {"status": "missing", "reporter_analysis_json_path": "fake.json", "reporter_analysis_md_path": ""},
            "trade_origin": "normal_lifecycle",
            "lifecycle_completeness": "complete",
        },
        story_input={
            "symbol": "000660",
            "status": "closed",
            "selected_symbol": "000660",
            "selected_rank": 0,
            "candidate_count": 0,
        },
        report={
            "generation": {"status": "ok"},
            "section_provenance": {
                "market_context_at_entry": {"source": "fallback"},
                "why_this_symbol_was_chosen": {"source": "fallback"},
            },
        },
    )

    result = mod.validate_trade_artifact_chain(reports_root, day, trade_id)

    assert result["ok"] is False
    assert "closed_trade_missing_linked_run_ids" in result["failures"]
    assert "closed_trade_missing_entry_run_id" in result["failures"]
    assert "closed_trade_missing_entry_ts" in result["failures"]
    assert "closed_trade_fake_or_missing_hold_duration" in result["failures"]
    assert "closed_trade_zero_hold_duration_sec" in result["failures"]
    assert "closed_trade_selected_rank_zero" in result["failures"]
    assert "closed_trade_candidate_count_zero" in result["failures"]
    assert "ai_trade_report_all_section_provenance_fallback" in result["failures"]
    assert "reporter_linkage_missing_but_artifact_path_populated" in result["failures"]


def test_validate_trade_artifact_chain_passes_complete_trade(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-16"
    trade_id = "TRD_20260416_000660_01"
    _seed_trade(
        reports_root,
        day=day,
        trade_id=trade_id,
        entry={
            "run_id": "run-buy",
            "ts": "2026-04-16T00:07:45+00:00",
            "action": "BUY",
            "symbol": "000660",
            "qty": 1,
            "reason_human": "pullback_rebound_above_vwap_with_volume_confirmation",
            "scanner_context": {"selected_symbol": "000660"},
        },
        hold={
            "hold_duration": "1.0m",
            "hold_duration_sec": 62,
        },
        exit_payload={
            "run_id": "run-sell",
            "ts": "2026-04-16T00:08:47+00:00",
            "action": "SELL",
            "symbol": "000660",
            "reason_human": "peak_drawdown",
        },
        lifecycle_bundle={
            "trade_lifecycle_status": "closed",
            "linked_run_ids": ["run-buy", "run-sell"],
            "same_day_reporter_linkage": {"status": "missing", "reporter_analysis_json_path": "", "reporter_analysis_md_path": ""},
            "trade_origin": "normal_lifecycle",
            "lifecycle_completeness": "partial",
        },
        story_input={
            "symbol": "000660",
            "status": "closed",
            "selected_symbol": "000660",
            "selected_rank": 1,
            "candidate_count": 5,
            "hold_duration": "1.0m",
            "hold_duration_sec": 62,
        },
        report={
            "generation": {"status": "ok"},
            "section_provenance": {
                "market_context_at_entry": {"source": "canonical"},
                "why_this_symbol_was_chosen": {"source": "direct_artifact"},
            },
        },
    )

    result = mod.validate_trade_artifact_chain(reports_root, day, trade_id)

    assert result["ok"] is True
    assert result["failures"] == []
    assert result["entry_run_id"] == "run-buy"
    assert result["exit_run_id"] == "run-sell"
    assert result["selected_rank"] == 1
    assert result["candidate_count"] == 5
    assert result["hold_duration"] == "1.0m"


def test_validate_trade_artifact_chain_flags_open_trade_story_status_conflict(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-15"
    trade_id = "TRD_20260415_000660_01"
    _seed_trade(
        reports_root,
        day=day,
        trade_id=trade_id,
        entry={
            "run_id": "run-buy",
            "ts": "2026-04-15T04:38:19+00:00",
            "action": "BUY",
            "symbol": "000660",
            "qty": 1,
            "reason_human": "selected",
            "scanner_context": {"selected_symbol": "000660"},
        },
        hold={
            "hold_duration": "1.1m",
            "hold_duration_sec": 66,
        },
        exit_payload={
            "execution_details": {
                "order_status": None,
                "order_id": None,
                "execution_mode": None,
                "broker_env": None,
                "filled_qty": None,
                "avg_price": None,
            }
        },
        lifecycle_bundle={
            "trade_lifecycle_status": "open",
            "linked_run_ids": ["run-buy"],
            "same_day_reporter_linkage": {"status": "missing", "reporter_analysis_json_path": "", "reporter_analysis_md_path": ""},
            "trade_origin": "normal_lifecycle",
            "lifecycle_completeness": "complete",
        },
        story_input={
            "symbol": "000660",
            "action": "SELL",
            "status": "closed",
            "selected_symbol": "000660",
            "selected_rank": 1,
            "candidate_count": 4,
            "hold_duration": "1.1m",
            "hold_duration_sec": 66,
        },
        report={
            "generation": {"status": "ok"},
            "section_provenance": {
                "market_context_at_entry": {"source": "canonical"},
                "why_this_symbol_was_chosen": {"source": "direct_artifact"},
            },
        },
    )
    _write_json(
        trade_artifact_paths(reports_root, day, trade_id)["trade_provenance_json"],
        {"trade_origin": "normal_lifecycle", "lifecycle_completeness": "complete", "lifecycle_status": "open"},
    )
    _write_json(
        trade_artifact_paths(reports_root, day, trade_id)["trade_health_json"],
        {"lifecycle_status": "open"},
    )

    result = mod.validate_trade_artifact_chain(reports_root, day, trade_id)

    assert result["ok"] is False
    assert result["closed_trade"] is False
    assert result["authoritative_status"] == "open"
    assert "story_input_status_conflicts_with_authoritative_status" in result["failures"]
    assert "story_input_action_conflicts_with_open_trade" in result["failures"]


def test_build_commands_include_runtime_replay_flags() -> None:
    repair = mod._build_bundle_repair_command(  # type: ignore[attr-defined]
        day="2026-04-16",
        target_run_id="run-sell",
        role="manual_repair_bundle",
        max_runs=200,
        event_log_path="data/logs/events.jsonl",
        evidence_log_path="data/evidence_ledger/events.jsonl",
        report_dir="reports/dev/analysis/live_execution_bundles",
        reports_root="reports",
    )
    report_regen = mod._build_report_regen_command(  # type: ignore[attr-defined]
        day="2026-04-16",
        trade_id="TRD_20260416_000660_01",
        reports_root="reports",
        local_debug=True,
        hard_timeout_sec=5.0,
    )
    llm_regen = mod._build_report_regen_command(  # type: ignore[attr-defined]
        day="2026-04-16",
        trade_id="TRD_20260416_000660_01",
        reports_root="reports",
        local_debug=False,
        hard_timeout_sec=900.0,
        with_llm=True,
    )

    repair_text = " ".join(repair)
    report_text = " ".join(report_regen)
    llm_text = " ".join(llm_regen)

    assert "run_live_execution_bundle_report.py" in repair_text
    assert "--target-run-id run-sell" in repair_text
    assert "--role manual_repair_bundle" in repair_text
    assert "--no-trade-report-ai" in repair_text
    assert "run_ai_trade_report_batch.py" in report_text
    assert "--trade-id TRD_20260416_000660_01" in report_text
    assert "--local-debug" in report_text
    assert "--hard-timeout-sec 5.0" in report_text
    assert "--local-debug" not in llm_text
    assert "--with-llm" in llm_text
    assert "--hard-timeout-sec 900.0" in llm_text
