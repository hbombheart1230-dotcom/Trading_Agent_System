from __future__ import annotations

from libs.reporting.trade_bundle_state import (
    build_ai_trade_report_generation_component,
    build_bundle_health,
    build_bundle_provenance,
    build_component_fingerprint,
    build_generation_state,
    build_live_trade_bundle_payloads,
    build_operator_brief_generation_component,
    build_trade_bundle_state,
    finalize_bundle_health,
)


def test_build_component_fingerprint_is_deterministic() -> None:
    kwargs = {
        "component": "ai_trade_report",
        "trade_id": "TRD_20260416_000660_01",
        "run_id": "run-1",
        "lifecycle_status": "closed",
        "story_type": "simulation",
        "model": "openrouter/free",
        "story_input": {"a": 1, "b": {"x": 2}},
        "compact_input": {"c": 3},
    }
    first = build_component_fingerprint(**kwargs)
    second = build_component_fingerprint(**kwargs)
    assert first["fingerprint"] == second["fingerprint"]
    assert first["source_inputs"]["story_input_sha256"] == second["source_inputs"]["story_input_sha256"]


def test_build_generation_state_keeps_required_component_keys() -> None:
    ai = build_ai_trade_report_generation_component(
        fingerprint="fp-ai",
        trade_id="TRD_20260416_000660_01",
        run_id="run-1",
        status="ok",
        report_status="available",
        report_generation_reason="",
        model="openrouter/free",
        report_json_path="r.json",
        report_md_path="r.md",
        llm_response_path="llm.json",
        source_inputs={"story_input_sha256": "a", "compact_input_sha256": "b"},
        updated_at="2026-04-16T01:00:00+00:00",
    )
    brief = build_operator_brief_generation_component(
        trade_id="TRD_20260416_000660_01",
        run_id="run-1",
        llm_brief_status="ok",
        report_json_path="brief.json",
        report_md_path="brief.md",
        llm_response_path="brief_llm.json",
        brief_json_exists=True,
        brief_md_exists=True,
        brief_llm_exists=True,
        updated_at="2026-04-16T01:00:00+00:00",
    )
    state = build_generation_state(
        current_state={"schema_version": "report_generation_state.v1", "components": {}},
        ai_trade_report_component=ai,
        operator_brief_component=brief,
    )
    assert state["schema_version"] == "report_generation_state.v1"
    assert "ai_trade_report" in state["components"]
    assert "operator_brief" in state["components"]
    assert state["components"]["ai_trade_report"]["component"] == "ai_trade_report"


def test_build_bundle_provenance_preserves_contract_keys() -> None:
    payload = build_bundle_provenance(
        trade_id="TRD_20260416_000660_01",
        run_id="run-1",
        day="2026-04-16",
        lifecycle_status="closed",
        recovery_metadata={"trade_origin": "normal_lifecycle", "lifecycle_completeness": "complete", "evidence_recovery_used": False},
        strategy_anchor_run_id="run-1",
        evidence_source="canonical",
        agent_sources={"scanner": "canonical"},
        section_provenance={"scanner": {"source": "canonical", "artifact_path": "scanner.json", "confidence": "high"}},
        artifacts={"canonical_scanner_json": "scanner.json"},
    )
    assert payload["schema_version"] == "trade_provenance.v1"
    assert payload["trade_id"] == "TRD_20260416_000660_01"
    assert "section_resolution" in payload
    assert payload["section_resolution"]["scanner"]["source_type"] == "canonical"
    assert payload["canonical_agent_artifact_paths"]["canonical_scanner_json"] == "scanner.json"


def test_build_bundle_health_and_finalize_keep_required_fields() -> None:
    health = build_bundle_health(
        trade_id="TRD_20260416_000660_01",
        run_id="run-1",
        day="2026-04-16",
        lifecycle_status="closed",
        recovery_metadata={"trade_origin": "normal_lifecycle", "lifecycle_completeness": "complete", "evidence_recovery_used": False},
        diagnostics={"report_status": "available", "llm_brief_status": "ok", "ai_trade_report_status": "ok"},
        report_generation={"status": "ok"},
        evidence_completeness_missing_sections=[],
        phase3_missing_sections=[],
        phase3_completeness_score=1.0,
        artifact_presence={"ai_trade_report_json": False, "ai_trade_report_md": False},
        ai_trade_report_llm_artifact={"status": "ok", "parse_mode": "strict"},
        strategist_event_count=1,
        scanner_event_count=1,
        monitor_event_count=1,
        operator_brief_json_exists=True,
    )
    finalized = finalize_bundle_health(
        health,
        artifact_presence={
            "ai_trade_report_json": True,
            "ai_trade_report_md": True,
            "operator_brief_json": True,
        },
        diagnostics={"report_status": "available", "llm_brief_status": "ok", "ai_trade_report_status": "ok"},
    )
    assert finalized["schema_version"] == "trade_health.v1"
    assert finalized["report_generation_status"] == "available"
    assert finalized["operator_brief_status"] == "ok"
    combined = build_trade_bundle_state(
        provenance_kwargs={
            "trade_id": "TRD_20260416_000660_01",
            "run_id": "run-1",
            "day": "2026-04-16",
            "lifecycle_status": "closed",
            "recovery_metadata": {"trade_origin": "normal_lifecycle", "lifecycle_completeness": "complete", "evidence_recovery_used": False},
            "strategy_anchor_run_id": "run-1",
            "evidence_source": "canonical",
            "agent_sources": {},
            "section_provenance": {},
            "artifacts": {},
        },
        health_kwargs={
            "trade_id": "TRD_20260416_000660_01",
            "run_id": "run-1",
            "day": "2026-04-16",
            "lifecycle_status": "closed",
            "recovery_metadata": {"trade_origin": "normal_lifecycle", "lifecycle_completeness": "complete", "evidence_recovery_used": False},
            "diagnostics": {"report_status": "available"},
            "report_generation": {},
            "evidence_completeness_missing_sections": [],
            "phase3_missing_sections": [],
            "phase3_completeness_score": 1.0,
            "artifact_presence": {},
            "ai_trade_report_llm_artifact": {},
            "strategist_event_count": 0,
            "scanner_event_count": 0,
            "monitor_event_count": 0,
            "operator_brief_json_exists": False,
        },
    )
    assert "provenance" in combined and "health" in combined


def test_build_live_trade_bundle_payloads_preserves_core_contract_fields(tmp_path) -> None:
    base = tmp_path / "reports" / "trades" / "2026-04-16" / "TRD_TEST"
    reports_dir = base / "reports"
    evidence_dir = base / "evidence"
    result = build_live_trade_bundle_payloads(
        day="2026-04-16",
        trade_id="TRD_TEST",
        run_id="run-1",
        symbol="000660",
        status="closed",
        lifecycle={
            "entry": {"run_id": "run-1"},
            "holding": {"holding_events": []},
            "exit": {"run_id": "run-2"},
            "timeline": [],
            "evidence": {"strategist_event_count": 1, "scanner_event_count": 2, "monitor_event_count": 3},
        },
        lifecycle_bundle={"strategist": {"playbook": "defensive"}, "scanner": {}, "monitor": {}, "commander": {}, "artifacts": {}, "evidence_provenance": {}, "market_context_human": {"summary": "market summary"}},
        story_input={
            "selected_symbol": "000660",
            "candidate_count": 2,
            "section_provenance": {},
            "market_context_human": {"summary": "market summary", "playbook": "defensive"},
            "strategist_evidence": {"decision_frames": [{"playbook": "defensive"}]},
        },
        summary_obj={"lifecycle_summary_human": "summary"},
        diagnostics={"report_status": "available", "llm_brief_status": "skipped", "ai_trade_report_status": "ok"},
        recovery_metadata={"trade_origin": "normal_lifecycle", "lifecycle_completeness": "complete", "evidence_recovery_used": False},
        story_contract={"schema_version": "story_contract.v1"},
        anchor_execution={"action": "SELL"},
        linked_run_ids=["run-1", "run-2"],
        same_day_reporter_linkage={"status": "linked_day_fallback"},
        failure_classification={"reporting_failure": False},
        execution_details={"order_status": "filled"},
        entry_execution_details={"order_status": "filled"},
        exit_execution_details={"order_status": "filled"},
        holding_phase_observability={"hold_duration": "1m", "hold_duration_sec": 60, "holding_phase_summary": "held", "hold_events_count": 0},
        strategist_llm_artifact={"status": "ok", "prompt_ref": "p1", "response_ref": "r1"},
        existing_brief_llm_artifact={"prompt_ref": "bp", "response_ref": "br"},
        ai_trade_report_llm_artifact={"status": "ok", "prompt_ref": "ap", "response_ref": "ar"},
        trade_report={"generation": {"status": "ok"}},
        evidence_completeness_missing_sections=[],
        phase3_missing_sections=[],
        phase3_completeness_score=1.0,
        strategist_event_count=1,
        scanner_event_count=2,
        monitor_event_count=3,
        operator_brief_json_exists=False,
        lifecycle_bundle_path=base / "lifecycle_bundle.json",
        entry_artifact_path=base / "entry.json",
        hold_artifact_path=base / "hold.json",
        exit_artifact_path=base / "exit.json",
        story_input_path=base / "ai_trade_report_input.json",
        story_compact_input_path=base / "ai_trade_report_compact_input.json",
        trade_report_json_path=reports_dir / "ai_trade_report.json",
        trade_report_md_path=reports_dir / "ai_trade_report.md",
        strategist_evidence_path=evidence_dir / "strategist_evidence.json",
        scanner_evidence_path=evidence_dir / "scanner_evidence.json",
        monitor_evidence_path=evidence_dir / "monitor_evidence.json",
        commander_evidence_path=evidence_dir / "commander_evidence.json",
        strategist_llm_response_path=reports_dir / "strategist_llm_response.json",
        ai_trade_report_llm_response_path=reports_dir / "ai_trade_report_llm_response.json",
        brief_llm_response_path=reports_dir / "brief_llm_response.json",
        operator_brief_json_path=reports_dir / "operator_brief.json",
        operator_brief_md_path=reports_dir / "operator_brief.md",
        trade_provenance_path=base / "_provenance.json",
        trade_health_path=base / "_health.json",
        trade_artifact_links_path=base / "_artifact_links.json",
        resolved_operator_brief_json=str(reports_dir / "operator_brief.json"),
        resolved_operator_brief_md=str(reports_dir / "operator_brief.md"),
        resolved_brief_llm_response_json=str(reports_dir / "brief_llm_response.json"),
        trade_report_json_written=str(reports_dir / "ai_trade_report.json"),
        trade_report_md_written=str(reports_dir / "ai_trade_report.md"),
        ai_trade_report_llm_response_written=str(reports_dir / "ai_trade_report_llm_response.json"),
    )

    lifecycle_bundle_payload = result["lifecycle_bundle_payload"]
    links_payload = result["trade_artifact_links_payload"]
    assert lifecycle_bundle_payload["trade_lifecycle_status"] == "closed"
    assert lifecycle_bundle_payload["selected_symbol"] == "000660"
    assert lifecycle_bundle_payload["candidate_count"] == 2
    assert lifecycle_bundle_payload["market_context_human"]["summary"] == "market summary"
    assert lifecycle_bundle_payload["strategist"]["playbook"] == "defensive"
    assert lifecycle_bundle_payload["strategist_evidence"]["decision_frames"][0]["playbook"] == "defensive"
    assert links_payload["trade_id"] == "TRD_TEST"
    assert links_payload["llm_prompt_refs"]["strategist"] == "p1"
    assert result["trade_health_payload"]["report_generation_status"] == "available"
