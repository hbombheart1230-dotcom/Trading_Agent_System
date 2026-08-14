from __future__ import annotations

import json
from pathlib import Path

import scripts.check_phase_5_2_5_3_runtime_health as mod


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def test_runtime_health_aggregates_structure_presence_and_policy_counts(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    day = "2026-04-03"

    run1 = reports_root / "canonical" / day / "run-good"
    run2 = reports_root / "canonical" / day / "run-wait"
    run3 = reports_root / "canonical" / day / "run-buy-gating"
    run4 = reports_root / "canonical" / day / "run-structure-guard"

    _write_json(run1 / "monitor.json", {"day": day, "run_id": "run-good", "decision": "BUY", "entry_reason": "good_breakout"})
    _write_json(run2 / "monitor.json", {"day": day, "run_id": "run-wait", "decision": "WAIT", "entry_reason": "conditions_not_met"})
    _write_json(run3 / "monitor.json", {"day": day, "run_id": "run-buy-gating", "decision": "BUY", "entry_reason": "policy_relaxed"})
    _write_json(
        run4 / "monitor.json",
        {
            "day": day,
            "run_id": "run-structure-guard",
            "decision": "WAIT",
            "entry_reason": "breakout_continuation_structure_guard_blocked",
        },
    )
    _write_json(run1 / "commander.json", {"applied_policy": {"entry_style": "breakout", "required_checks": ["volume_ok"]}})
    _write_json(
        run1 / "strategist.json",
        {
            "monitor_entry_policy": {"entry_style": "breakout", "preferred_checks": ["breakout_ok"]},
            "strategy_policy": {"monitor_policy": {"entry_policy": {"entry_style": "breakout"}}},
        },
    )
    _write_json(
        run2 / "commander.json",
        {
            "applied_policy": {
                "enabled": True,
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.68,
                "policy_source": "strategist",
            }
        },
    )
    _write_json(
        run2 / "strategist.json",
        {
            "monitor_entry_policy": {
                "enabled": True,
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.68,
                "policy_source": "strategist",
            },
            "strategy_policy": {"monitor_policy": {"entry_policy": {"playbook": "defensive"}}},
        },
    )
    _write_json(run3 / "commander.json", {"applied_policy": {"entry_style": "breakout", "relaxable_checks": ["reclaim_gate_ok"]}})
    _write_json(
        run3 / "strategist.json",
        {
            "monitor_entry_policy": {"entry_style": "breakout", "relaxable_checks": ["reclaim_gate_ok"]},
            "strategy_policy": {"monitor_policy": {"entry_policy": {"entry_style": "breakout"}}},
        },
    )
    _write_json(run4 / "commander.json", {"applied_policy": {"entry_style": "breakout", "preferred_checks": ["structure_hh_hl=intact"]}})
    _write_json(
        run4 / "strategist.json",
        {
            "monitor_entry_policy": {"entry_style": "breakout", "preferred_checks": ["structure_hh_hl=intact"]},
            "strategy_policy": {"monitor_policy": {"entry_policy": {"entry_style": "breakout"}}},
        },
    )

    detail_good = {
        "policy_contract": {
            "selected_source": "commander_applied_policy",
            "selected_policy": {"entry_style": "breakout"},
            "selected_policy_schema": {
                "schema_version": "monitor_entry_policy_schema_candidate.v1",
                "available": True,
                "entry_style": "breakout",
                "required_checks": [],
                "preferred_checks": ["breakout_ok"],
                "relaxable_checks": [],
                "blockers": [],
                "explicit_fields_used": ["entry_style", "preferred_checks"],
                "raw_keys": ["entry_style", "preferred_checks"],
                "spec_validation_notes": [],
                "invalid_policy_specs": [],
            },
            "selected_policy_spec_health": {
                "schema_available": True,
                "normalized_policy_spec_count": 1,
                "invalid_policy_spec_count": 0,
                "spec_validation_notes": [],
                "explicit_fields_used": ["entry_style", "preferred_checks"],
                "raw_keys": ["entry_style", "preferred_checks"],
            },
            "source_priority": ["commander_applied_policy", "strategist_output"],
        },
        "policy_interpretation": {
            "interpretation_basis": "explicit_policy",
            "policy_schema_available": True,
            "policy_schema_version": "monitor_entry_policy_schema_candidate.v1",
        },
        "signal_evidence": {"checks": {"volume_ok": True}},
        "policy_interpreter_trace": {
            "check_status": {
                "required": [{"name": "volume_ok", "status": "pass", "source": "signal_evidence.checks.volume_ok"}],
                "preferred": [],
                "relaxable": [],
                "blockers": [],
            }
        },
        "policy_alignment_summary": {
            "alignment_state": "aligned",
            "primary_blocker": None,
            "secondary_blockers": [],
        },
        "policy_aware_gating": {
            "available": True,
            "applied": False,
            "applied_hints": [],
            "required_failures": [],
            "relaxations_applied": [],
            "blocked_by_required": [],
        },
        "chart_structure_decision_hint": {
            "available": True,
            "applied": False,
            "mode": "none",
            "entry_style": "breakout",
            "considered_features": ["structure_hh_hl", "momentum_follow_through", "failed_breakout"],
            "matched_features": ["structure_hh_hl=intact"],
            "blocking_features": [],
            "notes": ["continuation_quality_not_blocking"],
        },
    }
    _append_jsonl(
        events_path,
        {
            "run_id": "run-good",
            "event_name": "monitor.entry_decision_detail",
            "payload": detail_good,
        },
    )

    detail_wait = {
        "policy_contract": {
            "selected_source": "strategist_output",
            "selected_policy": {},
            "selected_policy_schema": {
                "schema_version": "monitor_entry_policy_schema_candidate.v1",
                "available": False,
                "required_checks": [],
                "preferred_checks": [],
                "relaxable_checks": [],
                "blockers": [],
                "explicit_fields_used": [],
                "raw_keys": [],
                "spec_validation_notes": [],
                "invalid_policy_specs": [],
            },
            "selected_policy_spec_health": {
                "schema_available": False,
                "normalized_policy_spec_count": 0,
                "invalid_policy_spec_count": 0,
                "spec_validation_notes": [],
                "explicit_fields_used": [],
                "raw_keys": [],
            },
            "source_priority": ["strategist_output"],
        },
        "policy_interpretation": {
            "interpretation_basis": "fallback_playbook",
            "policy_schema_available": False,
            "policy_schema_version": "",
        },
        "policy_interpreter_trace": {
            "check_status": {
                "required": [],
                "preferred": [],
                "relaxable": [],
                "blockers": [],
            }
        },
        "policy_alignment_summary": {
            "alignment_state": "partial",
            "primary_blocker": "",
            "secondary_blockers": [],
        },
        "policy_aware_gating": {
            "available": True,
            "applied": False,
            "applied_hints": [],
            "required_failures": [],
            "relaxations_applied": [],
            "blocked_by_required": [],
        },
        "chart_structure_decision_hint": {
            "available": False,
            "applied": False,
            "mode": "none",
            "entry_style": "pullback",
            "considered_features": [],
            "matched_features": [],
            "blocking_features": [],
            "notes": ["non_breakout_entry_style"],
        },
    }
    _append_jsonl(
        events_path,
        {
            "run_id": "run-wait",
            "event_name": "monitor.entry_decision_detail",
            "payload": detail_wait,
        },
    )

    detail_buy_gating = {
        "policy_contract": {
            "selected_source": "commander_applied_policy",
            "selected_policy": {"entry_style": "breakout"},
            "selected_policy_schema": {
                "schema_version": "monitor_entry_policy_schema_candidate.v1",
                "available": True,
                "entry_style": "breakout",
                "required_checks": ["volume_ok"],
                "preferred_checks": ["structure_hh_hl=intact"],
                "relaxable_checks": ["reclaim_gate_ok"],
                "blockers": [],
                "explicit_fields_used": ["entry_style", "required_checks", "preferred_checks", "relaxable_checks"],
                "raw_keys": ["entry_style", "preferred_checks", "relaxable_checks"],
                "spec_validation_notes": ["preferred_checks:struture_hh_hl=intact:invalid_feature"],
                "invalid_policy_specs": [
                    {
                        "raw": "struture_hh_hl=intact",
                        "feature_name": "struture_hh_hl",
                        "expected_state": "intact",
                        "validation_notes": ["invalid_feature"],
                    }
                ],
            },
            "selected_policy_spec_health": {
                "schema_available": True,
                "normalized_policy_spec_count": 2,
                "invalid_policy_spec_count": 1,
                "spec_validation_notes": ["preferred_checks:struture_hh_hl=intact:invalid_feature"],
                "explicit_fields_used": ["entry_style", "required_checks", "preferred_checks", "relaxable_checks"],
                "raw_keys": ["entry_style", "preferred_checks", "relaxable_checks"],
            },
            "source_priority": ["commander_applied_policy"],
        },
        "policy_interpretation": {
            "interpretation_basis": "mixed",
            "policy_schema_available": True,
            "policy_schema_version": "monitor_entry_policy_schema_candidate.v1",
            "entry_style": "breakout",
        },
        "signal_evidence": {
            "checks": {
                "reclaim_ok": False,
                "reclaim_gate_ok": False,
                "breakout_path_ok": True,
                "confidence_ok": True,
                "volume_ok": True,
            },
            "derived": {
                "too_extended": False,
                "reclaim_distance_to_ready": -0.001,
            },
        },
        "policy_interpreter_trace": {
            "check_status": {
                "required": [{"name": "volume_ok", "status": "pass", "source": "signal_evidence.checks.volume_ok"}],
                "preferred": [],
                "relaxable": [{"name": "reclaim_ok", "status": "fail", "source": "signal_evidence.checks.reclaim_ok"}],
                "blockers": [],
            }
        },
        "policy_alignment_summary": {
            "alignment_state": "aligned",
            "primary_blocker": None,
            "secondary_blockers": [],
        },
        "policy_aware_gating": {
            "available": True,
            "applied": True,
            "applied_hints": ["reclaim_relaxed_near_ready"],
            "required_failures": [],
            "relaxations_considered": ["reclaim_gate_ok"],
            "relaxations_applied": ["reclaim_gate_ok"],
            "blocked_by_required": [],
        },
        "chart_structure_decision_hint": {
            "available": True,
            "applied": False,
            "mode": "none",
            "entry_style": "breakout",
            "considered_features": ["structure_hh_hl", "momentum_follow_through", "failed_breakout"],
            "matched_features": ["structure_hh_hl=intact", "momentum_follow_through=strong"],
            "blocking_features": [],
            "notes": ["continuation_quality_not_blocking"],
        },
        "legacy_entry_decision": "WAIT",
        "legacy_entry_reason": "below_vwap_reclaim_not_ready",
    }
    _append_jsonl(
        events_path,
        {
            "run_id": "run-buy-gating",
            "event_name": "monitor.entry_decision_detail",
            "payload": detail_buy_gating,
        },
    )

    detail_structure_guard = {
        "policy_contract": {
            "selected_source": "commander_applied_policy",
            "selected_policy": {"entry_style": "breakout"},
            "selected_policy_schema": {
                "schema_version": "monitor_entry_policy_schema_candidate.v1",
                "available": True,
                "entry_style": "breakout",
                "required_checks": ["breakout_ok"],
                "preferred_checks": ["structure_hh_hl=intact", "momentum_follow_through=strong"],
                "relaxable_checks": [],
                "blockers": ["failed_breakout=confirmed"],
                "explicit_fields_used": ["entry_style", "required_checks", "preferred_checks", "blockers"],
                "raw_keys": ["entry_style", "required_checks", "preferred_checks", "blockers"],
                "spec_validation_notes": [],
                "invalid_policy_specs": [],
            },
            "selected_policy_spec_health": {
                "schema_available": True,
                "normalized_policy_spec_count": 4,
                "invalid_policy_spec_count": 0,
                "spec_validation_notes": [],
                "explicit_fields_used": ["entry_style", "required_checks", "preferred_checks", "blockers"],
                "raw_keys": ["entry_style", "required_checks", "preferred_checks", "blockers"],
            },
            "source_priority": ["commander_applied_policy"],
        },
        "policy_interpretation": {
            "interpretation_basis": "explicit_policy",
            "policy_schema_available": True,
            "policy_schema_version": "monitor_entry_policy_schema_candidate.v1",
            "entry_style": "breakout",
        },
        "signal_evidence": {
            "checks": {
                "breakout_ok": True,
                "breakout_path_ok": True,
                "confidence_ok": True,
                "volume_ok": True,
            }
        },
        "policy_interpreter_trace": {
            "check_status": {
                "required": [{"name": "breakout_ok", "status": "pass", "source": "signal_evidence.checks.breakout_ok"}],
                "preferred": [{"name": "structure_hh_hl", "status": "fail", "source": "chart_structure_features.structure.structure_hh_hl"}],
                "relaxable": [],
                "blockers": [{"name": "failed_breakout", "status": "inactive", "source": "chart_structure_features.support_resistance.failed_breakout"}],
            }
        },
        "policy_alignment_summary": {
            "alignment_state": "partial",
            "primary_blocker": "structure_hh_hl",
            "secondary_blockers": [],
        },
        "policy_aware_gating": {
            "available": True,
            "applied": False,
            "applied_hints": [],
            "required_failures": [],
            "relaxations_applied": [],
            "blocked_by_required": [],
        },
        "chart_structure_decision_hint": {
            "available": True,
            "applied": True,
            "mode": "block",
            "entry_style": "breakout",
            "considered_features": ["structure_hh_hl", "momentum_follow_through", "failed_breakout"],
            "matched_features": ["failed_breakout=none"],
            "blocking_features": ["structure_hh_hl=weakening", "momentum_follow_through=moderate"],
            "notes": ["breakout_continuation_structure_guard_applied"],
        },
        "legacy_entry_decision": "BUY",
        "legacy_entry_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
    }
    _append_jsonl(
        events_path,
        {
            "run_id": "run-structure-guard",
            "event_name": "monitor.entry_decision_detail",
            "payload": detail_structure_guard,
        },
    )

    out = mod.build_phase_5_2_5_3_runtime_health(
        reports_root=reports_root,
        event_log_path=events_path,
        day=day,
        limit=10,
    )

    assert out["schema_version"] == "phase_5_runtime_health_check.v1"
    assert out["run_count"] == 4
    assert out["structure_presence"]["entry_policy_contract"]["present_count"] == 4
    assert out["structure_presence"]["signal_evidence"]["missing_count"] == 1
    assert out["selected_source_counts"]["commander_applied_policy"] == 3
    assert out["selected_source_counts"]["strategist_output"] == 1
    assert out["interpretation_basis_counts"]["explicit_policy"] == 2
    assert out["interpretation_basis_counts"]["fallback_playbook"] == 1
    assert out["interpretation_basis_counts"]["mixed"] == 1
    assert out["policy_schema_available_counts"]["true"] == 3
    assert out["policy_schema_available_counts"]["false"] == 1
    assert out["policy_aware_gating_stats"]["applied_true_count"] == 1
    assert out["policy_spec_validation_stats"]["normalized_policy_schema_present_count"] == 3
    assert out["policy_spec_validation_stats"]["invalid_policy_spec_count"] == 1
    assert out["policy_spec_validation_stats"]["invalid_policy_spec_run_ids"] == ["run-buy-gating"]
    assert out["policy_spec_validation_stats"]["policy_validation_notes_counts"]["preferred_checks:struture_hh_hl=intact:invalid_feature"] == 1
    assert out["policy_spec_validation_stats"]["invalid_policy_specs_by_selected_source"]["commander_applied_policy"] == 1
    assert out["policy_surface_quality_summary"]["schema_version"] == "policy_surface_quality_summary.v1"
    assert out["policy_surface_quality_summary"]["run_count"] == 4
    assert out["policy_surface_quality_summary"]["total_invalid_specs"] == 1
    assert out["policy_surface_quality_summary"]["invalid_specs_by_selected_source"]["commander_applied_policy"] == 1
    assert out["chart_structure_decision_hint_summary"]["schema_version"] == "chart_structure_decision_hint_summary.v1"
    assert out["chart_structure_decision_hint_summary"]["available_run_count"] == 3
    assert out["chart_structure_decision_hint_summary"]["applied_count"] == 1
    assert out["chart_structure_decision_hint_summary"]["blocking_feature_counts"]["structure_hh_hl"] == 1
    assert out["chart_structure_decision_hint_summary"]["blocking_feature_counts"]["momentum_follow_through"] == 1
    assert out["chart_structure_decision_hint_summary"]["reason_counts_when_applied"]["breakout_continuation_structure_guard_blocked"] == 1
    assert out["chart_structure_decision_hint_summary"]["applied_run_ids"] == ["run-structure-guard"]
    assert out["chart_structure_decision_hint_summary"]["applied_examples"][0]["run_id"] == "run-structure-guard"
    assert out["chart_structure_decision_hint_summary"]["applied_examples"][0]["reason_transition"] == (
        "breakout_above_recent_high_with_vwap_structure_confirmation -> "
        "breakout_continuation_structure_guard_blocked"
    )
    assert len(out["buy_runs"]) == 2
    buy_runs_by_id = {row["run_id"]: row for row in out["buy_runs"]}
    assert buy_runs_by_id["run-buy-gating"]["invalid_policy_spec_count"] == 1
    assert "preferred_checks:struture_hh_hl=intact:invalid_feature" in buy_runs_by_id["run-buy-gating"]["policy_validation_notes"]
    assert buy_runs_by_id["run-good"]["chart_structure_hint_applied"] is False
    assert out["policy_aware_gating_deadness"]["policy_aware_gating_applied_count"] == 1
    assert out["policy_source_field_presence"]["commander_applied_policy"]["schema_available_true_count"] == 3
    assert out["policy_source_field_presence"]["commander_applied_policy"]["schema_available_false_count"] == 1


def test_runtime_health_flags_expected_suspicious_patterns(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    day = "2026-04-03"

    run_wait = reports_root / "canonical" / day / "run-wait"
    run_buy = reports_root / "canonical" / day / "run-buy"
    _write_json(run_wait / "monitor.json", {"day": day, "run_id": "run-wait", "decision": "WAIT", "entry_reason": "conditions_not_met"})
    _write_json(run_buy / "monitor.json", {"day": day, "run_id": "run-buy", "decision": "BUY", "entry_reason": "policy_relaxed"})

    _append_jsonl(
        events_path,
        {
            "run_id": "run-wait",
            "event_name": "monitor.entry_decision_detail",
            "payload": {
                "policy_contract": {"selected_source": "strategist_output", "selected_policy": {}, "source_priority": ["strategist_output"]},
                "policy_interpretation": {"interpretation_basis": "fallback_playbook", "policy_schema_available": False},
                "policy_interpreter_trace": {"check_status": {"required": [], "preferred": [], "relaxable": [], "blockers": []}},
                "policy_alignment_summary": {"alignment_state": "partial", "primary_blocker": "", "secondary_blockers": []},
                "policy_aware_gating": {"available": True, "applied": False, "applied_hints": [], "required_failures": [], "relaxations_applied": [], "blocked_by_required": []},
            },
        },
    )
    _append_jsonl(
        events_path,
        {
            "run_id": "run-buy",
            "event_name": "monitor.entry_decision_detail",
            "payload": {
                "policy_contract": {"selected_source": "commander_applied_policy", "selected_policy": {"entry_style": "breakout"}, "source_priority": ["commander_applied_policy"]},
                "policy_interpretation": {"interpretation_basis": "mixed", "policy_schema_available": True},
                "signal_evidence": {"checks": {"reclaim_ok": False}},
                "policy_interpreter_trace": {"check_status": {"required": [], "preferred": [], "relaxable": [], "blockers": []}},
                "policy_alignment_summary": {"alignment_state": "aligned", "primary_blocker": None, "secondary_blockers": []},
                "policy_aware_gating": {"available": True, "applied": True, "applied_hints": [], "required_failures": [], "relaxations_applied": [], "blocked_by_required": []},
            },
        },
    )

    out = mod.build_phase_5_2_5_3_runtime_health(
        reports_root=reports_root,
        event_log_path=events_path,
        day=day,
        limit=10,
    )

    suspicious_by_run = {row["run_id"]: set(row["suspicious_flags"]) for row in out["suspicious_runs"]}
    assert "wait_missing_primary_blocker" in suspicious_by_run["run-wait"]
    assert "wait_no_failed_required_checks" in suspicious_by_run["run-wait"]
    assert "buy_gating_applied_without_context" in suspicious_by_run["run-buy"]

    rendered = mod.render_phase_5_2_5_3_runtime_health_text(out)
    assert "Phase 5-2 ~ 5-3 Runtime Health (2026-04-03)" in rendered
    assert "run_id | selected_source | interpretation_basis" in rendered
    assert "## Policy Surface Quality Summary" in rendered
    assert "## Chart Structure Decision Hint Summary" in rendered
    assert "## Policy Spec Validation" in rendered
    assert "invalid_policy_specs_by_selected_source" in rendered
    assert "## Explicit Policy Source Presence" in rendered
    summary_text = mod.render_policy_surface_quality_summary_text("2026-04-03", out["policy_surface_quality_summary"])
    assert "=== Policy Surface Quality Summary (2026-04-03) ===" in summary_text
    assert "total_invalid_specs: 0" in summary_text
    chart_summary_text = mod.render_chart_structure_decision_hint_summary_text("2026-04-03", out["chart_structure_decision_hint_summary"])
    assert "=== Chart Structure Decision Hint Summary (2026-04-03) ===" in chart_summary_text


def test_runtime_health_restores_policy_surfaces_from_canonical_monitor(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    day = "2026-04-03"
    run_dir = reports_root / "canonical" / day / "run-persisted-only"
    _write_json(
        run_dir / "monitor.json",
        {
            "day": day,
            "run_id": "run-persisted-only",
            "symbol": "005930",
            "decision": "NOOP",
            "entry_reason": "volume_confirmation_missing",
            "received_policy_source": "commander_applied_policy",
            "effective_policy": {
                "entry_style": "pullback",
                "required_checks": ["reclaim_gate_ok"],
                "preferred_checks": ["volume_ok"],
            },
            "signal_snapshot": {
                "entry_evaluated": True,
                "entry_grouped_logic_trace": {
                    "reclaim_gate_ok": True,
                    "breakout_path_ok": False,
                    "confidence_gate_ok": True,
                    "extension_ok": True,
                    "volume_confirmation": {"volume_ok": False},
                    "policy_aware_gating_available": True,
                    "policy_aware_gating_applied": False,
                    "policy_aware_gating_hints": [],
                    "policy_aware_gating_blocked_by_required": ["volume_ok"],
                    "chart_structure_decision_hint_available": True,
                    "chart_structure_decision_hint_applied": False,
                    "chart_structure_decision_hint_mode": "none",
                    "chart_structure_decision_hint_blocking_features": [],
                },
            },
            "policy_interpreter_trace": {
                "available": True,
                "policy_available": True,
                "entry_style": "pullback",
                "check_status": {
                    "required": [{"name": "reclaim_gate_ok", "status": "pass"}],
                    "preferred": [{"name": "volume_ok", "status": "fail"}],
                    "relaxable": [],
                    "blockers": [],
                },
            },
            "policy_alignment_summary": {
                "alignment_state": "partial",
                "primary_blocker": "volume_ok",
                "secondary_blockers": [],
            },
        },
    )

    out = mod.build_phase_5_2_5_3_runtime_health(
        reports_root=reports_root,
        event_log_path=events_path,
        day=day,
        limit=10,
    )

    assert out["run_count"] == 1
    assert out["structure_presence"]["entry_policy_contract"]["present_count"] == 1
    assert out["structure_presence"]["signal_evidence"]["present_count"] == 1
    assert out["policy_schema_available_counts"]["true"] == 1
    assert out["policy_surface_quality_summary"]["run_count"] == 1
    assert out["policy_surface_quality_summary"]["schema_available_rate"] == 1.0
    assert out["policy_surface_quality_summary"]["normalized_policy_rate"] == 1.0
    assert out["chart_structure_decision_hint_summary"]["available_run_count"] == 1


def test_runtime_health_exposes_reclaim_wait_and_deadness_reasons(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    day = "2026-04-03"

    run_wait = reports_root / "canonical" / day / "run-reclaim-wait"
    _write_json(run_wait / "monitor.json", {"day": day, "run_id": "run-reclaim-wait", "decision": "WAIT", "entry_reason": "below_vwap_reclaim_not_ready"})
    _write_json(run_wait / "commander.json", {"applied_policy": {"entry_style": "breakout", "relaxable_checks": ["reclaim_gate_ok"]}})
    _write_json(run_wait / "strategist.json", {"monitor_entry_policy": {"entry_style": "breakout", "relaxable_checks": ["reclaim_gate_ok"]}})

    _append_jsonl(
        events_path,
        {
            "run_id": "run-reclaim-wait",
            "event_name": "monitor.entry_decision_detail",
            "payload": {
                "policy_contract": {
                    "selected_source": "commander_applied_policy",
                    "selected_policy": {"entry_style": "breakout", "relaxable_checks": ["reclaim_gate_ok"]},
                    "source_priority": ["commander_applied_policy"],
                },
                "policy_interpretation": {
                    "interpretation_basis": "explicit_policy",
                    "policy_schema_available": True,
                    "policy_schema_version": "monitor_entry_policy_schema_candidate.v1",
                    "entry_style": "breakout",
                },
                "signal_evidence": {
                    "checks": {
                        "reclaim_gate_ok": False,
                        "breakout_path_ok": True,
                        "confidence_ok": True,
                        "volume_ok": True,
                    },
                    "derived": {
                        "too_extended": False,
                        "reclaim_distance_to_ready": -0.01,
                    },
                },
                "policy_interpreter_trace": {
                    "check_status": {
                        "required": [],
                        "preferred": [],
                        "relaxable": [{"name": "reclaim_gate_ok", "status": "fail", "source": "signal_evidence.checks.reclaim_gate_ok"}],
                        "blockers": [],
                    }
                },
                "policy_alignment_summary": {
                    "alignment_state": "aligned",
                    "primary_blocker": "below_vwap_reclaim_not_ready",
                    "secondary_blockers": [],
                },
                "policy_aware_gating": {
                    "available": True,
                    "applied": False,
                    "applied_hints": [],
                    "required_failures": [],
                    "relaxations_considered": ["reclaim_gate_ok"],
                    "relaxations_applied": [],
                    "blocked_by_required": [],
                    "notes": ["reclaim_not_near_ready"],
                },
                "legacy_entry_decision": "WAIT",
                "legacy_entry_reason": "below_vwap_reclaim_not_ready",
            },
        },
    )

    out = mod.build_phase_5_2_5_3_runtime_health(
        reports_root=reports_root,
        event_log_path=events_path,
        day=day,
        limit=10,
    )

    assert len(out["reclaim_wait_runs"]) == 1
    reclaim_row = out["reclaim_wait_runs"][0]
    assert reclaim_row["breakout_path_ok"] is True
    assert reclaim_row["confidence_ok"] is True
    assert reclaim_row["policy_aware_gating_applied"] is False
    assert out["policy_aware_gating_deadness"]["policy_aware_gating_candidate_count"] == 1
    assert out["policy_aware_gating_deadness"]["policy_aware_gating_rejection_reasons"]["reclaim_not_near_ready"] == 1
