from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from libs.reporting import trade_report_runtime_generation as runtime_generation_mod
from libs.reporting import trade_report_runtime_policy as runtime_policy_mod
from libs.reporting.intraday_trade_reports import (
    _run_bundle_sync,
    apply_live_bundle_backfill,
    apply_ai_trade_report_generation_result,
    apply_runtime_diagnostics_context,
    base_report_diagnostics,
    build_live_bundle_backfill_payload,
    build_live_execution_summary_payload,
    build_live_generation_state_payload,
    execute_ai_trade_report_generation,
    generate_intraday_trade_artifacts,
    plan_live_trade_report_generation,
    persist_live_story_input_artifacts,
    report_next_step,
    report_reason_human,
    resolve_trade_report_policy,
    seed_diagnostics_for_policy,
)


def test_intraday_trade_reports_reexports_runtime_policy_and_generation_modules() -> None:
    assert report_reason_human is runtime_policy_mod.report_reason_human
    assert report_next_step is runtime_policy_mod.report_next_step
    assert base_report_diagnostics is runtime_policy_mod.base_report_diagnostics
    assert resolve_trade_report_policy is runtime_policy_mod.resolve_trade_report_policy
    assert seed_diagnostics_for_policy is runtime_policy_mod.seed_diagnostics_for_policy
    assert apply_runtime_diagnostics_context is runtime_generation_mod.apply_runtime_diagnostics_context
    assert build_live_generation_state_payload is runtime_generation_mod.build_live_generation_state_payload
    assert plan_live_trade_report_generation is runtime_generation_mod.plan_live_trade_report_generation
    assert apply_ai_trade_report_generation_result is runtime_generation_mod.apply_ai_trade_report_generation_result
    assert execute_ai_trade_report_generation is runtime_generation_mod.execute_ai_trade_report_generation


def test_intraday_trade_reports_generates_and_invalidates_cache(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    cache_dir = root / "data" / "operator_ui" / "brief_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "run-1.json"
    cache_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("OPERATOR_UI_CACHE_PATH", str(cache_dir))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))

    def fake_runner(argv=None):  # type: ignore[no-untyped-def]
        out = {
            "run_bundles": [
                {
                    "run_id": "run-1",
                    "trade_id": "TRD_20260317_005930_01",
                    "story_id": "TRD_20260317_005930_01",
                    "report_status": "available",
                    "trade_report_json_path": str(root / "reports" / "trades" / "2026-03-17" / "TRD_20260317_005930_01" / "reports" / "ai_trade_report.json"),
                    "symbol": "005930",
                }
            ]
        }
        return 0, json.dumps(out, ensure_ascii=False)

    monkeypatch.setattr("libs.reporting.live_execution_bundle_runner.run_live_execution_bundle_inprocess", fake_runner)
    brief_json = root / "reports" / "trades" / "2026-03-17" / "TRD_20260317_005930_01" / "reports" / "operator_brief.json"
    brief_md = root / "reports" / "trades" / "2026-03-17" / "TRD_20260317_005930_01" / "reports" / "operator_brief.md"
    brief_json.parent.mkdir(parents=True, exist_ok=True)
    brief_json.write_text(json.dumps({"headline": "brief"}, ensure_ascii=False), encoding="utf-8")
    brief_md.write_text("# brief\n", encoding="utf-8")

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-1",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "BUY", "symbol": "005930"},
            },
        },
        root=root,
    )

    assert out["ok"] is True
    assert out["status"] == "generated"
    assert out["trade_id"] == "TRD_20260317_005930_01"
    assert out["report_status"] == "available"
    assert cache_path.exists() is False
    assert out["operator_brief_json_path"] == str(brief_json)
    assert out["operator_brief_md_path"] == str(brief_md)
    assert brief_json.exists() is True
    assert brief_md.exists() is True


def test_intraday_trade_reports_build_live_generation_state_payload_and_runtime_diagnostics(tmp_path: Path) -> None:
    trade_report_json = tmp_path / "ai_trade_report.json"
    trade_report_md = tmp_path / "ai_trade_report.md"
    ai_llm_response = tmp_path / "ai_trade_report_llm_response.json"
    operator_brief_json = tmp_path / "operator_brief.json"
    operator_brief_md = tmp_path / "operator_brief.md"
    brief_llm_response = tmp_path / "brief_llm_response.json"
    for path in (trade_report_json, trade_report_md, operator_brief_json):
        path.write_text("{}", encoding="utf-8")

    diagnostics = apply_runtime_diagnostics_context(
        {
            "report_status": "available",
            "ai_trade_report_status": "ok",
            "report_generation_reason": "generated",
            "llm_model_used": "openrouter/test",
            "llm_brief_status": "skipped",
        },
        holding_phase_observability={
            "hold_evidence_thin": False,
            "hold_events_count": 3,
            "hold_duration_sec": 120,
        },
        same_day_reporter_linkage={
            "status": "linked_day_fallback",
            "linkage_reason": "same-day file attached",
        },
        execution_details={
            "order_status": "filled",
            "order_id": "",
            "execution_mode": "mock",
            "broker_env": "paper",
            "filled_qty": 1,
            "avg_price": "",
        },
    )

    assert diagnostics["holding_evidence_thin"] is False
    assert diagnostics["hold_events_count"] == 3
    assert diagnostics["same_day_reporter_linkage_status"] == "linked_day_fallback"
    assert diagnostics["execution_fields_missing"] == ["order_id", "avg_price"]

    payload = build_live_generation_state_payload(
        current_state={"schema_version": "report_generation_state.v1", "components": {"legacy": {"status": "keep"}}},
        generation_components={"legacy": {"status": "keep"}},
        ai_trade_report_fingerprint="fp-1",
        trade_id="TRD_20260317_005930_01",
        run_id="run-1",
        diagnostics=diagnostics,
        configured_report_model="openrouter/test",
        trade_report_json_path=trade_report_json,
        trade_report_md_path=trade_report_md,
        ai_trade_report_llm_response_path=ai_llm_response,
        ai_trade_report_llm_response_written="",
        ai_trade_report_fingerprint_info={"source_inputs": {"story_input_sha256": "a", "compact_input_sha256": "b"}},
        operator_brief_json_path=operator_brief_json,
        operator_brief_md_path=operator_brief_md,
        brief_llm_response_path=brief_llm_response,
    )

    components = payload["generation_components"]
    assert components["legacy"]["status"] == "keep"
    assert components["ai_trade_report"]["status"] == "ok"
    assert components["ai_trade_report"]["report_status"] == "available"
    assert components["operator_brief"]["status"] == "skipped"


def test_intraday_trade_reports_build_live_bundle_backfill_payload(tmp_path: Path) -> None:
    diagnostics = {
        "report_status": "available",
        "report_reason_code": "",
        "report_reason_human": "generated",
        "next_expected_step": "open",
        "llm_model_used": "openrouter/test",
        "generation_attempted": True,
        "deterministic_report_status": "ok",
        "llm_brief_status": "skipped",
        "ai_trade_report_status": "ok",
    }
    payload = build_live_bundle_backfill_payload(
        trade_id="TRD_20260317_005930_01",
        status="closed",
        story_type="simulation",
        execution_mode_label="simulation",
        symbol="005930",
        entry_run_id="run-1",
        hold_run_ids=["run-2"],
        exit_run_id="run-3",
        linked_run_ids=["run-1", "run-2", "run-3"],
        lifecycle_summary="summary",
        lifecycle_bundle_path=tmp_path / "lifecycle_bundle.json",
        story_input_path=tmp_path / "ai_trade_report_input.json",
        story_compact_input_path=tmp_path / "ai_trade_report_compact_input.json",
        trade_report_json_written=str(tmp_path / "reports" / "ai_trade_report.json"),
        trade_report_md_written=str(tmp_path / "reports" / "ai_trade_report.md"),
        strategist_llm_response_path=tmp_path / "reports" / "strategist_llm_response.json",
        ai_trade_report_llm_response_written=str(tmp_path / "reports" / "ai_trade_report_llm_response.json"),
        entry_artifact_path=tmp_path / "entry.json",
        hold_artifact_path=tmp_path / "hold.json",
        exit_artifact_path=tmp_path / "exit.json",
        strategist_evidence_path=tmp_path / "evidence" / "strategist_evidence.json",
        scanner_evidence_path=tmp_path / "evidence" / "scanner_evidence.json",
        monitor_evidence_path=tmp_path / "evidence" / "monitor_evidence.json",
        commander_evidence_path=tmp_path / "evidence" / "commander_evidence.json",
        trade_provenance_path=tmp_path / "_provenance.json",
        trade_health_path=tmp_path / "_health.json",
        trade_artifact_links_path=tmp_path / "_artifact_links.json",
        trade_root=tmp_path,
        trade_report_summary="AI report generated.",
        diagnostics=diagnostics,
    )

    row = payload["lifecycle_row"]
    row_patch = payload["run_bundle_row_patch"]
    bundle_patch = payload["bundle_artifacts_patch"]
    assert row["trade_id"] == "TRD_20260317_005930_01"
    assert row["entry_run_id"] == "run-1"
    assert row["hold_run_ids"] == ["run-2"]
    assert row["report_status"] == "available"
    assert row["ai_trade_report_status"] == "ok"
    assert row_patch["trade_root_path"] == str(tmp_path)
    assert row_patch["trade_report_summary"] == "AI report generated."
    assert bundle_patch["lifecycle_bundle_json"].endswith("lifecycle_bundle.json")
    assert bundle_patch["ai_trade_report_json"].endswith("ai_trade_report.json")


def test_intraday_trade_reports_persist_live_story_input_artifacts_preserves_closed_snapshot(tmp_path: Path) -> None:
    story_input_path = tmp_path / "ai_trade_report_input.json"
    compact_input_path = tmp_path / "ai_trade_report_compact_input.json"
    current_story_input = {
        "status": "open",
        "symbol": "005930",
        "shared_facts": {"status": "open"},
    }
    existing_story_input = {
        "status": "closed",
        "symbol": "005930",
        "shared_facts": {"status": "closed", "action": "SELL"},
    }
    out = persist_live_story_input_artifacts(
        day="2026-03-17",
        trade_id="TRD_20260317_005930_01",
        anchor_run_id="run-3",
        status="open",
        should_attempt_generation=False,
        trade_story_input=current_story_input,
        trade_story_compact_input={"status": "open"},
        existing_trade_report_artifact={"status": "closed", "action": "SELL", "run_id": "run-3"},
        existing_story_input_artifact=existing_story_input,
        story_input_path=story_input_path,
        story_compact_input_path=compact_input_path,
        diagnostics={},
    )

    persisted = out["story_input_to_persist"]
    compact_artifact = out["trade_story_compact_artifact"]
    assert persisted["status"] == "closed"
    assert persisted["shared_facts"]["status"] == "closed"
    assert out["preserved_closed_story_input"] is True
    assert out["diagnostics"]["story_input_persist_strategy"] == "preserve_existing_closed_snapshot"
    assert json.loads(story_input_path.read_text(encoding="utf-8"))["status"] == "closed"
    assert compact_artifact["trade_id"] == "TRD_20260317_005930_01"
    assert compact_artifact["source_artifact_path"] == str(story_input_path)
    assert compact_input_path.exists() is True


def test_intraday_trade_reports_apply_live_bundle_backfill_updates_rows_and_bundle_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_json_path = tmp_path / "run-1.bundle.json"
    report_md_path = tmp_path / "run-1.bundle.md"
    report_json_path.write_text(json.dumps({"run_id": "run-1"}, ensure_ascii=False), encoding="utf-8")
    report_md_path.write_text("old", encoding="utf-8")
    monkeypatch.setattr("libs.reporting.intraday_trade_reports.render_bundle_markdown", lambda bundle: "bundle-md")

    run_bundle_lookup = {"run-1": {"run_id": "run-1"}}
    run_bundles_by_run = {
        "run-1": {
            "run_id": "run-1",
            "report_json_path": str(report_json_path),
            "report_md_path": str(report_md_path),
            "artifacts": {},
        }
    }
    payload = {
        "run_bundle_row_patch": {"trade_id": "TRD_20260317_005930_01", "report_status": "available"},
        "bundle_artifacts_patch": {"ai_trade_report_json": str(tmp_path / "ai_trade_report.json")},
    }

    out = apply_live_bundle_backfill(
        linked_run_ids=["run-1"],
        run_bundle_lookup=run_bundle_lookup,
        run_bundles_by_run=run_bundles_by_run,
        backfill_payload=payload,
        trade_id="TRD_20260317_005930_01",
        diagnostics={"report_status": "available"},
    )

    assert out["updated_run_ids"] == ["run-1"]
    assert run_bundle_lookup["run-1"]["trade_id"] == "TRD_20260317_005930_01"
    assert run_bundles_by_run["run-1"]["story_id"] == "TRD_20260317_005930_01"
    assert run_bundles_by_run["run-1"]["artifacts"]["ai_trade_report_json"].endswith("ai_trade_report.json")
    assert json.loads(report_json_path.read_text(encoding="utf-8"))["trade_id"] == "TRD_20260317_005930_01"
    assert report_md_path.read_text(encoding="utf-8") == "bundle-md"


def test_intraday_trade_reports_build_live_execution_summary_payload(tmp_path: Path) -> None:
    trade_js = tmp_path / "trade_explain.json"
    trade_md = tmp_path / "trade_explain.md"
    reporter_js = tmp_path / "reporter_analysis.json"
    reporter_md = tmp_path / "reporter_analysis.md"
    operator_summary_json = tmp_path / "operator_summary.json"
    operator_summary_md = tmp_path / "operator_summary.md"
    reporter_js.write_text("{}", encoding="utf-8")
    operator_summary_json.write_text("{}", encoding="utf-8")

    summary = build_live_execution_summary_payload(
        day="2026-03-17",
        role="intraday_trade_report_bundle",
        event_log_path=tmp_path / "events.jsonl",
        evidence_log_path=tmp_path / "evidence.jsonl",
        lifecycle_rows=[
            {"trade_id": "TRD1", "report_status": "available"},
            {"trade_id": "TRD2", "report_status": "skipped"},
            {"trade_id": "TRD3", "report_status": "available"},
        ],
        run_bundle_rows=[{"run_id": "run-1"}],
        lifecycle_story_type_counts={"simulation": 2, "decision_only": 1},
        run_story_type_counts={"simulation": 1},
        target_ctx={
            "targeted_mode": True,
            "target_run_id": "run-1",
            "target_symbol": "005930",
            "execution_run_count": 1,
            "lifecycle_context_run_count": 3,
        },
        canonical_trades_root=tmp_path / "trades",
        trade_js=trade_js,
        trade_md=trade_md,
        reporter_js=reporter_js,
        reporter_md=reporter_md,
        operator_summary_json=operator_summary_json,
        operator_summary_md=operator_summary_md,
    )

    assert summary["bundle_count"] == 3
    assert summary["trade_lifecycle_count"] == 3
    assert summary["run_bundle_count"] == 1
    assert summary["report_status_counts"] == {"available": 2, "skipped": 1}
    assert summary["targeted_mode"] is True
    assert summary["target_run_id"] == "run-1"
    assert summary["target_symbol"] == "005930"
    assert summary["day_artifacts"]["reporter_analysis_json"].endswith("reporter_analysis.json")
    assert summary["day_artifacts"]["operator_summary_json"].endswith("operator_summary.json")


def test_intraday_trade_reports_policy_helpers_gate_open_trade_generation() -> None:
    policy = resolve_trade_report_policy(
        runtime_state={
            "applied_policy": {
                "reporter": {
                    "trade_report": {
                        "enabled": True,
                        "generate_on_open": False,
                        "policy_source": "runtime_state.applied_policy",
                    }
                }
            }
        }
    )
    assert policy["enabled"] is True
    assert policy["generate_on_open"] is False
    assert policy["policy_source"] == "runtime_state.applied_policy"

    diagnostics = base_report_diagnostics("openrouter/test")
    assert diagnostics["llm_model_used"] == "openrouter/test"
    assert report_reason_human("awaiting_exit_for_full_report").startswith("This trade is still open")
    assert report_next_step("awaiting_exit_for_full_report").startswith("Generate the final AI report")

    seeded = seed_diagnostics_for_policy(
        lifecycle_status="open",
        story_type="executed_trade",
        report_requested=True,
        story_input_available=True,
        model_hint="openrouter/test",
        generate_on_open=False,
    )
    assert seeded["should_attempt_generation"] is False
    assert seeded["diagnostics"]["report_reason_code"] == "awaiting_exit_for_full_report"
    assert seeded["diagnostics"]["report_status"] == "pending"


def test_intraday_trade_reports_run_bundle_sync_uses_inprocess_runner(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.reporting.live_execution_bundle_runner.run_live_execution_bundle_inprocess",
        lambda argv=None: (0, '{"ok":true,"status":"generated"}'),
    )

    rc, raw = _run_bundle_sync(["--day", "2026-04-17"])

    assert rc == 0
    assert raw == '{"ok":true,"status":"generated"}'


def test_intraday_trade_reports_plan_live_trade_report_generation_reuses_matching_artifact(tmp_path: Path) -> None:
    trade_report_json = tmp_path / "ai_trade_report.json"
    trade_report_md = tmp_path / "ai_trade_report.md"
    trade_report_json.write_text("{}", encoding="utf-8")
    trade_report_md.write_text("# report\n", encoding="utf-8")

    plan = plan_live_trade_report_generation(
        should_attempt_generation=True,
        report_requested=True,
        diagnostics={"llm_model_used": "openrouter/test"},
        deterministic_report={"headline": "deterministic"},
        existing_trade_report_artifact={
            "headline": "existing",
            "ai_trade_report_status": "ok",
            "generation": {"status": "ok", "model": "openrouter/existing"},
        },
        existing_ai_trade_report_llm_artifact={"llm_status": "ok", "status": "ok"},
        ai_trade_report_generation_state={"fingerprint": "fp-1", "model": "openrouter/state"},
        ai_trade_report_fingerprint="fp-1",
        trade_report_json_path=trade_report_json,
        trade_report_md_path=trade_report_md,
        configured_report_model="openrouter/test",
        existing_report_noisy=False,
    )

    diagnostics = plan["diagnostics"]
    assert plan["mode"] == "reuse_existing_success"
    assert plan["trade_report"]["headline"] == "existing"
    assert diagnostics["generation_attempted"] is False
    assert diagnostics["ai_trade_report_status"] == "ok"
    assert diagnostics["report_generation_reason"] == "fingerprint_match_existing_success"
    assert plan["log_events"][0]["event"] == "report_generation_skipped_fingerprint_match"


def test_intraday_trade_reports_plan_live_first_write_generates_ai(tmp_path: Path) -> None:
    plan = plan_live_trade_report_generation(
        should_attempt_generation=True,
        report_requested=True,
        diagnostics={"llm_model_used": "openrouter/test"},
        deterministic_report={"headline": "deterministic"},
        existing_trade_report_artifact={},
        existing_ai_trade_report_llm_artifact={},
        ai_trade_report_generation_state={},
        ai_trade_report_fingerprint="fp-live-1",
        trade_report_json_path=tmp_path / "ai_trade_report.json",
        trade_report_md_path=tmp_path / "ai_trade_report.md",
        configured_report_model="openrouter/test",
        existing_report_noisy=False,
    )

    assert plan["mode"] == "generate_ai"
    assert plan["diagnostics"]["generation_attempted"] is True
    assert plan["diagnostics"].get("ai_trade_report_status", "skipped") == "skipped"


def test_intraday_trade_reports_apply_ai_trade_report_generation_result_preserves_deterministic_on_failure() -> None:
    result = apply_ai_trade_report_generation_result(
        diagnostics={"generation_attempted": True},
        deterministic_report={"headline": "deterministic"},
        ai_trade_report={
            "headline": "ai",
            "generation": {"status": "error", "reason": "network timeout"},
            "llm_response_artifact": {"status": "error"},
        },
        configured_report_model="openrouter/test",
    )

    diagnostics = result["diagnostics"]
    assert result["trade_report"]["headline"] == "deterministic"
    assert diagnostics["ai_trade_report_status"] == "error"
    assert diagnostics["report_reason_code"] == "llm_generation_failed"
    assert diagnostics["last_error_message"] == "network timeout"
    assert result["ai_trade_report_llm_artifact"]["status"] == "error"


def test_intraday_trade_reports_execute_ai_trade_report_generation_passes_builder_args() -> None:
    captured: dict[str, object] = {}

    def fake_builder(story_input, **kwargs):  # type: ignore[no-untyped-def]
        captured["story_input"] = dict(story_input or {})
        captured["kwargs"] = dict(kwargs)
        return {
            "headline": "ai",
            "generation": {"status": "ok", "model": "openrouter/generated"},
            "llm_response_artifact": {"status": "ok"},
        }

    result = execute_ai_trade_report_generation(
        trade_story_input={"symbol": "000660"},
        diagnostics={"generation_attempted": True},
        deterministic_report={"headline": "deterministic"},
        configured_report_model="openrouter/test",
        ai_report_builder=fake_builder,
        model="openrouter/selected",
        temperature=0.2,
        max_tokens=1200,
    )

    assert captured["story_input"] == {"symbol": "000660"}
    assert captured["kwargs"] == {
        "enabled": True,
        "model": "openrouter/selected",
        "temperature": 0.2,
        "max_tokens": 1200,
    }
    assert result["trade_report"]["headline"] == "ai"
    assert result["diagnostics"]["ai_trade_report_status"] == "ok"


def test_intraday_trade_reports_skips_when_execution_failed(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-2",
            "execution": {
                "ok": False,
                "allowed": False,
                "order": {"action": "BUY", "symbol": "005930"},
            },
        }
    )
    assert out["ok"] is False
    assert out["reason"] == "execution_not_successful"


def test_intraday_trade_reports_respects_applied_policy_disable(monkeypatch) -> None:
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-disabled",
            "applied_policy": {"reporter": {"trade_report": {"enabled": False, "policy_source": "commander_applied_policy"}}},
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "BUY", "symbol": "005930"},
            },
        }
    )
    assert out["ok"] is False
    assert out["status"] == "disabled"
    assert out["reason"] == "reporter.trade_report.enabled is false"
    assert out["policy_source"] == "commander_applied_policy"


def test_intraday_trade_reports_skips_buy_when_generate_on_open_disabled(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)

    popen_called = False

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("BUY should not spawn report bundle when generate_on_open is disabled")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-buy-skip",
            "applied_policy": {"reporter": {"trade_report": {"enabled": True, "generate_on_open": False}}},
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "BUY", "symbol": "000660"},
            },
        },
    )

    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "trade_report_generate_on_open_disabled"
    assert out["report_status"] == "pending"
    assert out["symbol"] == "000660"
    assert out["target_run_id"] == "run-buy-skip"
    assert popen_called is False


def test_intraday_trade_reports_queues_background_job_after_timeout(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setenv("INTRADAY_TRADE_REPORT_SYNC_TIMEOUT_SEC", "0.5")
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)

    popen_calls: list[list[str]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=0.5)

    class DummyProc:
        pid = 43210

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        popen_calls.append(list(cmd))
        return DummyProc()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-timeout",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "069500"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["report_status"] == "queued"
    assert out["queue_mode"] == "background_subprocess"
    assert out["background_pid"] == 43210
    assert out["symbol"] == "069500"
    assert popen_calls
    flat_cmd = " ".join(popen_calls[0])
    assert "-m libs.reporting.live_execution_bundle_runner" in flat_cmd
    assert "--trade-report-ai" in flat_cmd
    assert "--no-trade-report-ai" not in flat_cmd
    assert "--max-runs" not in flat_cmd
    assert "--target-run-id run-timeout" in flat_cmd
    assert "--target-symbol 069500" in flat_cmd
    assert "--role intraday_trade_report_bundle" in flat_cmd


def test_intraday_trade_reports_dedupes_when_background_job_is_already_running(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._active_bundle_process", lambda _root: {})

    lock_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at_epoch": 9999999999.0,
                "script": "run_live_execution_bundle_report.py",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    popen_called = False

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("duplicate background job should not spawn")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-dedupe",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "bundle_busy_no_queue"
    assert out["report_status"] == "skipped"
    assert out["background_pid"] == os.getpid()
    assert out["lock_path"] == str(lock_path)
    queue_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"
    assert queue_path.exists() is False
    assert popen_called is False


def test_intraday_trade_reports_dedupes_when_background_process_is_already_running(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)
    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports._active_bundle_process",
        lambda _root: {
            "pid": 65432,
            "script": "run_live_execution_bundle_report.py",
            "command_line": "python scripts/run_live_execution_bundle_report.py --json",
            "detection_source": "process_scan",
        },
    )

    popen_called = False

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal popen_called
        popen_called = True
        raise AssertionError("duplicate background job should not spawn")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-dedupe-process",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "bundle_busy_no_queue"
    assert out["report_status"] == "skipped"
    assert out["background_pid"] == 65432
    assert out["dedupe_source"] == "process_scan"
    queue_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"
    assert queue_path.exists() is False
    assert popen_called is False


def test_intraday_trade_reports_removes_stale_lock_then_queues_background_job(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._active_bundle_process", lambda _root: {})

    lock_path = root / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": 999999,
                "role": "intraday_trade_report_bundle",
                "started_at_epoch": 1.0,
                "touched_at_epoch": 1.0,
                "script": "run_live_execution_bundle_report.py",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    popen_calls: list[list[str]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=0.5)

    class DummyProc:
        pid = 54321

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        popen_calls.append(list(cmd))
        return DummyProc()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-stale-lock",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["background_pid"] == 54321
    assert popen_calls
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert int(lock_payload["pid"]) == 54321
    assert str(lock_payload["role"]) == "intraday_trade_report_bundle"


def test_intraday_trade_reports_terminates_stale_orphan_process_then_queues_background_job(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    monkeypatch.setenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")
    monkeypatch.setenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))
    monkeypatch.setenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))
    monkeypatch.setenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl"))
    monkeypatch.setenv("ENV_PATH", str(root / ".env"))
    monkeypatch.setattr("libs.reporting.intraday_trade_reports._root_dir", lambda: root)
    monkeypatch.setattr(
        "libs.reporting.intraday_trade_reports._active_bundle_process",
        lambda _root: {
            "pid": 76543,
            "parent_pid": 111,
            "script": "run_live_execution_bundle_report.py",
            "command_line": "python scripts/run_live_execution_bundle_report.py --role intraday_trade_report_bundle",
            "detection_source": "process_scan",
            "age_sec": 999.0,
        },
    )

    terminated = {"called": False}

    def fake_terminate(pid):  # type: ignore[no-untyped-def]
        terminated["called"] = True
        return True

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=0.5)

    class DummyProc:
        pid = 65432

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        return DummyProc()

    monkeypatch.setattr("libs.reporting.intraday_trade_reports._terminate_process_tree", fake_terminate)
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    out = generate_intraday_trade_artifacts(
        {
            "run_id": "run-stale-process",
            "execution": {
                "ok": True,
                "allowed": True,
                "order": {"action": "SELL", "symbol": "005930"},
            },
        }
    )

    assert terminated["called"] is True
    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["background_pid"] == 65432
