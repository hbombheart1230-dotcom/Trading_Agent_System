from __future__ import annotations

from pathlib import Path

from libs.reporting.trade_bundle_assembly import build_live_run_bundle, hydrate_live_run_bundle_context


def test_build_live_run_bundle_builds_story_contract_and_human_sections(tmp_path: Path) -> None:
    out = build_live_run_bundle(
        day="2026-04-17",
        run_id="run-1",
        merged_execution={"action": "BUY", "symbol": "005930", "qty": 1, "status": "filled"},
        commander_payload={"decision": "BUY"},
        strategist_payload={"playbook": "pullback", "themes": ["semiconductor"]},
        scanner_payload={"selected_symbol": "005930", "selected_rank": 1, "universe_size": 5},
        monitor_payload={"monitor_reason": "entry confirmed"},
        supervisor_payload={"risk_state": "normal"},
        executor_payload={"execution_mode": "mock"},
        reporter_trace_payload={"status_human": "linked"},
        reporter_obj={"ai_summary": "steady", "ai_run_grade": "B"},
        trade_obj={"execution_summary": {"executions_total": 2}},
        trace_json_path=tmp_path / "trace.json",
        trace_md_path=tmp_path / "trace.md",
        trade_json_path=tmp_path / "trade.json",
        trade_md_path=tmp_path / "trade.md",
        reporter_json_path=tmp_path / "reporter.json",
        reporter_md_path=tmp_path / "reporter.md",
        operator_summary_json_path=tmp_path / "operator_summary.json",
        operator_summary_md_path=tmp_path / "operator_summary.md",
        commander_path="commander.json",
        strategist_path="strategist.json",
        scanner_path="scanner.json",
        monitor_path="monitor.json",
        supervisor_path="supervisor.json",
        executor_path="executor.json",
        canonical_sources={"artifacts": {"strategist": {"playbook": "pullback"}}},
    )

    bundle = out["bundle_out"]
    assert out["story_type"]
    assert out["story_id"]
    assert bundle["run_id"] == "run-1"
    assert bundle["reporter"]["reporter_analysis_summary"] == "steady"
    assert bundle["artifacts"]["canonical_scanner_json"] == "scanner.json"
    assert bundle["market_context_human"]
    assert bundle["scanner_reason_human"]
    assert bundle["operator_conclusion_human"]
    assert bundle["story_contract"]["warnings"] == bundle["warnings"]


def test_hydrate_live_run_bundle_context_prefers_canonical_payloads(tmp_path: Path, monkeypatch) -> None:
    canonical_root = tmp_path / "reports"
    commander_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "commander.json"
    strategist_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "strategist.json"
    scanner_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "scanner.json"
    monitor_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "monitor.json"
    supervisor_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "supervisor.json"
    executor_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "executor.json"
    monkeypatch.setattr(
        "libs.reporting.trade_bundle_assembly.load_run_canonical_artifacts",
        lambda reports_root, run_id, day_hint: {
            "artifacts": {
                "commander": {"decision": "BUY"},
                "strategist": {"playbook": "pullback"},
                "scanner": {"selected_symbol": "005930", "selected_rank": 1, "universe_size": 4},
                "monitor": {"monitor_reason": "good"},
                "supervisor": {"allowed": True},
                "executor": {"execution_mode": "mock"},
            },
            "paths": {
                "commander": str(commander_path),
                "strategist": str(strategist_path),
                "scanner": str(scanner_path),
                "monitor": str(monitor_path),
                "supervisor": str(supervisor_path),
                "executor": str(executor_path),
            },
        },
    )
    out = hydrate_live_run_bundle_context(
        reports_root=canonical_root,
        day="2026-04-17",
        run_id="run-1",
        execution_row={"run_id": "run-1", "ts": "2026-04-17T00:00:00+00:00", "action": "BUY", "symbol": "005930"},
        trace_out={"reporter": {"status_human": "linked"}},
        reporter_obj={"ai_summary": "stable", "ai_run_grade": "A"},
        trade_obj={},
        trace_json_path=tmp_path / "trace.json",
        trace_md_path=tmp_path / "trace.md",
        trade_json_path=tmp_path / "trade.json",
        trade_md_path=tmp_path / "trade.md",
        reporter_json_path=tmp_path / "reporter.json",
        reporter_md_path=tmp_path / "reporter.md",
        operator_summary_json_path=tmp_path / "operator_summary.json",
        operator_summary_md_path=tmp_path / "operator_summary.md",
        bundle_ts="2026-04-17T00:00:01+00:00",
    )
    bundle = out["bundle_out"]
    assert bundle["ts"] == "2026-04-17T00:00:01+00:00"
    assert bundle["strategist"]["playbook"] == "pullback"
    assert bundle["artifacts"]["canonical_scanner_json"] == str(scanner_path)
    assert bundle["evidence_provenance"]["scanner"] == "canonical"
    assert out["story_type"]
