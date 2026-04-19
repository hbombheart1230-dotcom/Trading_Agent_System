from __future__ import annotations

import json
from pathlib import Path

import scripts.run_phase5_validation_bundle as mod


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_phase5_validation_bundle_builds_index_with_existing_helpers(monkeypatch, tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    output_dir = reports_root / "dev" / "analysis" / "phase5_validation"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text('{"ts":"2026-04-03T05:00:00+00:00","stage":"monitor"}\n', encoding="utf-8")

    latest_run = reports_root / "canonical" / "2026-04-03" / "run-latest"
    latest_run.mkdir(parents=True, exist_ok=True)
    _write_json(latest_run / "commander.json", {"ok": True})
    _write_json(latest_run / "monitor.json", {"ok": True})

    daily_md = reports_root / "daily" / "2026-04-03" / "daily_report.md"
    daily_json = reports_root / "daily" / "2026-04-03" / "daily_report.json"
    operator_md = reports_root / "daily" / "2026-04-03" / "operator_summary.md"
    operator_json = reports_root / "daily" / "2026-04-03" / "operator_summary.json"
    decision_story_md = reports_root / "dev" / "manual" / "decision_story" / "decision_story_2026-04-03.md"
    run_cards_md = reports_root / "dev" / "manual" / "run_cards" / "run_cards_2026-04-03.md"
    trade_explain_md = reports_root / "dev" / "analysis" / "trade_explain" / "trade_explain_2026-04-03.md"
    trade_explain_json = reports_root / "dev" / "analysis" / "trade_explain" / "trade_explain_2026-04-03.json"
    trace_md = reports_root / "dev" / "analysis" / "agent_pipeline_trace" / "trace.md"
    trace_json = reports_root / "dev" / "analysis" / "agent_pipeline_trace" / "trace.json"
    for path in (
        daily_md,
        daily_json,
        operator_md,
        operator_json,
        decision_story_md,
        run_cards_md,
        trade_explain_md,
        trade_explain_json,
        trace_md,
        trace_json,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_text("# ok\n", encoding="utf-8")
    daily_json.write_text(
        json.dumps(
            {
                "policy_surface_quality_summary": {
                    "schema_version": "policy_surface_quality_summary.v1",
                    "run_count": 4,
                    "schema_available_rate": 0.75,
                    "normalized_policy_rate": 0.5,
                    "invalid_spec_rate": 0.1,
                    "total_invalid_specs": 1,
                    "top_invalid_features": ["momentum_decay"],
                    "top_invalid_states": ["very_strong"],
                    "validation_notes_counts": {"invalid_state": 1},
                    "invalid_specs_by_selected_source": {"commander_applied_policy": 1},
                    "validation_notes_by_interpretation_basis": {"mixed": 1},
                    "notes": [],
                },
                "policy_surface_quality_executive_summary": {
                    "schema_version": "policy_surface_quality_executive_summary.v1",
                    "status": "watch",
                    "run_count": 4,
                    "schema_available_rate": 0.75,
                    "normalized_policy_rate": 0.5,
                    "invalid_spec_rate": 0.1,
                    "top_invalid_features": ["momentum_decay"],
                    "headline": "Policy surface watch: schema 0.75, invalid spec 0.10",
                    "notes": ["invalid_specs_present"],
                },
                "policy_surface_quality_source": {
                    "run_count": 4,
                    "date": "2026-04-03",
                    "source": "daily_monitor_artifacts",
                },
                "chart_structure_decision_hint_summary": {
                    "schema_version": "chart_structure_decision_hint_summary.v1",
                    "run_count": 4,
                    "available_run_count": 3,
                    "applied_count": 1,
                    "applied_rate": 0.3333,
                    "mode_counts": {"block": 1, "none": 2},
                    "blocking_feature_counts": {"failed_breakout": 1},
                    "top_blocking_features": ["failed_breakout"],
                    "applied_run_ids": ["run-structure-guard"],
                    "reason_counts_when_applied": {"breakout_continuation_structure_guard_blocked": 1},
                    "entry_style_counts_when_applied": {"breakout": 1},
                    "decision_counts_when_applied": {"WAIT": 1},
                    "applied_examples": [
                        {
                            "run_id": "run-structure-guard",
                            "symbol": "005930",
                            "entry_style": "breakout",
                            "mode": "block",
                            "legacy_decision": "BUY",
                            "legacy_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                            "final_decision": "WAIT",
                            "final_reason": "breakout_continuation_structure_guard_blocked",
                            "reason_transition": "breakout_above_recent_high_with_vwap_structure_confirmation -> breakout_continuation_structure_guard_blocked",
                            "blocking_features": ["failed_breakout=confirmed"],
                            "matched_features": [],
                        }
                    ],
                    "notes": [],
                },
                "chart_structure_decision_hint_executive_summary": {
                    "schema_version": "chart_structure_decision_hint_executive_summary.v1",
                    "status": "active",
                    "run_count": 4,
                    "available_run_count": 3,
                    "applied_count": 1,
                    "applied_rate": 0.3333,
                    "top_blocking_features": ["failed_breakout"],
                    "headline": "Chart structure guard active: applied 1 times (rate 0.33), top blockers: failed_breakout",
                    "notes": [],
                },
                "chart_structure_decision_hint_source": {
                    "run_count": 4,
                    "date": "2026-04-03",
                    "source": "daily_monitor_artifacts",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_generate_daily_report(*args, **kwargs):
        return daily_md, daily_json

    def fake_generate_operator_daily_summary(*args, **kwargs):
        return operator_md, operator_json

    def fake_generate_decision_story_report(*args, **kwargs):
        return decision_story_md, {"story_total": 3}

    def fake_generate_run_card_report(*args, **kwargs):
        return run_cards_md, {"card_total": 4}

    def fake_generate_trade_explain_report(*args, **kwargs):
        return trade_explain_md, trade_explain_json, {"execution_summary": {"executions_total": 2, "sell_pairs_total": 1}}

    def fake_audit_reports_trades_health(*args, **kwargs):
        return {
            "ok": True,
            "trade_dir_count": 2,
            "severity_counts": {"warn": 1},
            "issue_counts": {"sidecar_missing": 1},
            "issues": [
                {
                    "severity": "warn",
                    "trade_id": "TRD_1",
                    "component": "trade_root",
                    "code": "sidecar_missing",
                    "message": "Missing additive sidecar _health.json.",
                    "path": str(reports_root / "trades" / "2026-04-03" / "TRD_1" / "_health.json"),
                }
            ],
        }

    def fake_collect_symbols_for_day(*args, **kwargs):
        return ["005930"]

    def fake_generate_symbol_trade_report(*args, **kwargs):
        symbol_root = reports_root / "symbols" / "005930"
        symbol_root.mkdir(parents=True, exist_ok=True)
        (symbol_root / "symbol_trade_report.json").write_text("{}", encoding="utf-8")
        (symbol_root / "symbol_trade_report.md").write_text("# symbol\n", encoding="utf-8")
        (symbol_root / "trade_history.json").write_text("[]", encoding="utf-8")
        (symbol_root / "latest_snapshot.json").write_text("{}", encoding="utf-8")
        return {
            "symbol": "005930",
            "path_json": str(symbol_root / "symbol_trade_report.json"),
        }

    def fake_generate_agent_pipeline_trace_report(*args, **kwargs):
        return trace_md, trace_json, {"summary": "ok"}

    monkeypatch.setattr(mod, "generate_daily_report", fake_generate_daily_report)
    monkeypatch.setattr(mod, "generate_operator_daily_summary", fake_generate_operator_daily_summary)
    monkeypatch.setattr(mod, "generate_decision_story_report", fake_generate_decision_story_report)
    monkeypatch.setattr(mod, "generate_run_card_report", fake_generate_run_card_report)
    monkeypatch.setattr(mod, "generate_trade_explain_report", fake_generate_trade_explain_report)
    monkeypatch.setattr(mod, "audit_reports_trades_health", fake_audit_reports_trades_health)
    monkeypatch.setattr(mod, "collect_symbols_for_day", fake_collect_symbols_for_day)
    monkeypatch.setattr(mod, "generate_symbol_trade_report", fake_generate_symbol_trade_report)
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", fake_generate_agent_pipeline_trace_report)

    md_path, json_path, out = mod.generate_phase5_validation_bundle(
        event_log_path=events_path,
        reports_root=reports_root,
        output_dir=output_dir,
        day="2026-04-03",
    )

    assert out["schema_version"] == "phase5_validation_bundle.v1"
    assert out["summary"]["trade_health_ok"] is True
    assert out["summary"]["symbol_report_count"] == 1
    assert out["summary"]["latest_canonical_run_id"] == "run-latest"
    assert out["artifacts"]["pipeline_trace"]["available"] is True
    assert out["artifacts"]["pipeline_trace"]["run_id"] == "run-latest"
    assert out["artifacts"]["policy_surface_quality"]["summary"]["schema_version"] == "policy_surface_quality_summary.v1"
    assert out["artifacts"]["policy_surface_quality"]["executive_summary"]["status"] == "watch"
    assert out["artifacts"]["policy_surface_quality"]["source"]["run_count"] == 4
    assert out["artifacts"]["chart_structure_decision_hint"]["summary"]["schema_version"] == "chart_structure_decision_hint_summary.v1"
    assert out["artifacts"]["chart_structure_decision_hint"]["executive_summary"]["status"] == "active"
    assert out["artifacts"]["chart_structure_decision_hint"]["source"]["run_count"] == 4
    assert out["artifacts"]["chart_structure_decision_hint"]["summary"]["applied_examples"][0]["run_id"] == "run-structure-guard"
    assert out["artifacts"]["decision_story"]["story_total"] == 3
    assert out["artifacts"]["run_cards"]["card_total"] == 4
    assert out["artifacts"]["trade_explain"]["executions_total"] == 2
    assert out["artifacts"]["symbol_reports"][0]["symbol"] == "005930"
    assert json_path.exists()
    assert md_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    assert "Phase 5 Validation Bundle (2026-04-03)" in markdown
    assert "## Policy Surface Executive Summary" in markdown
    assert "Policy surface watch: schema 0.75, invalid spec 0.10" in markdown
    assert "## Policy Surface Quality" in markdown
    assert "## Chart Structure Decision Hint Executive Summary" in markdown
    assert "Chart structure guard active: applied 1 times" in markdown
    assert "## Chart Structure Decision Hint" in markdown
    assert "## Chart Structure Decision Hint Applied Examples" in markdown
    assert "breakout_above_recent_high_with_vwap_structure_confirmation -> breakout_continuation_structure_guard_blocked" in markdown
    assert "schema_available_rate" in markdown
    assert "trade_health_ok" in markdown
    assert "005930" in markdown
