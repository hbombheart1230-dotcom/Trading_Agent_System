from libs.reporting.policy_surface_summary import (
    build_policy_surface_quality_executive_line,
    build_policy_surface_quality_executive_summary,
    build_policy_surface_quality_summary,
)


def test_policy_surface_quality_summary_handles_empty_runs_safely() -> None:
    out = build_policy_surface_quality_summary([])

    assert out["schema_version"] == "policy_surface_quality_summary.v1"
    assert out["run_count"] == 0
    assert out["schema_available_rate"] == 0.0
    assert out["normalized_policy_rate"] == 0.0
    assert out["invalid_spec_rate"] == 0.0
    assert out["total_invalid_specs"] == 0
    assert out["notes"] == ["no_runs_available"]


def test_policy_surface_quality_summary_aggregates_invalid_specs_and_notes() -> None:
    out = build_policy_surface_quality_summary(
        [
            {
                "run_id": "run-1",
                "selected_source": "commander_applied_policy",
                "interpretation_basis": "mixed",
                "policy_schema_available": True,
                "normalized_policy_spec_count": 4,
                "invalid_policy_spec_count": 1,
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
            {
                "run_id": "run-2",
                "selected_source": "commander_applied_policy",
                "interpretation_basis": "explicit_policy",
                "policy_schema_available": True,
                "normalized_policy_spec_count": 3,
                "invalid_policy_spec_count": 1,
                "spec_validation_notes": ["blockers:momentum_decay=very_strong:invalid_state"],
                "invalid_policy_specs": [
                    {
                        "raw": "momentum_decay=very_strong",
                        "feature_name": "momentum_decay",
                        "expected_state": "very_strong",
                        "validation_notes": ["invalid_state"],
                    }
                ],
            },
            {
                "run_id": "run-3",
                "selected_source": "strategist_output.monitor_entry_policy",
                "interpretation_basis": "fallback_playbook",
                "policy_schema_available": False,
                "normalized_policy_spec_count": 0,
                "invalid_policy_spec_count": 0,
                "spec_validation_notes": [],
                "invalid_policy_specs": [],
            },
        ]
    )

    assert out["run_count"] == 3
    assert out["schema_available_rate"] == 0.6667
    assert out["normalized_policy_rate"] == 0.6667
    assert out["invalid_spec_rate"] == 0.2222
    assert out["total_invalid_specs"] == 2
    assert out["top_invalid_features"] == ["struture_hh_hl", "momentum_decay"]
    assert out["top_invalid_states"] == ["intact", "very_strong"]
    assert out["validation_notes_counts"]["invalid_feature"] == 1
    assert out["validation_notes_counts"]["invalid_state"] == 1
    assert out["invalid_specs_by_selected_source"]["commander_applied_policy"] == 2
    assert out["validation_notes_by_interpretation_basis"]["mixed"] == 1
    assert out["validation_notes_by_interpretation_basis"]["explicit_policy"] == 1


def test_policy_surface_quality_executive_summary_handles_empty_summary() -> None:
    out = build_policy_surface_quality_executive_summary(
        {
            "schema_version": "policy_surface_quality_summary.v1",
            "run_count": 0,
            "schema_available_rate": 0.0,
            "normalized_policy_rate": 0.0,
            "invalid_spec_rate": 0.0,
            "total_invalid_specs": 0,
            "top_invalid_features": [],
            "top_invalid_states": [],
            "validation_notes_counts": {},
            "invalid_specs_by_selected_source": {},
            "validation_notes_by_interpretation_basis": {},
            "notes": ["no_runs_available"],
        }
    )

    assert out["schema_version"] == "policy_surface_quality_executive_summary.v1"
    assert out["status"] == "unknown"
    assert "no runs available" in out["headline"].lower()


def test_policy_surface_quality_executive_summary_builds_compact_headline() -> None:
    summary = {
        "schema_version": "policy_surface_quality_summary.v1",
        "run_count": 12,
        "schema_available_rate": 0.83,
        "normalized_policy_rate": 0.75,
        "invalid_spec_rate": 0.01,
        "total_invalid_specs": 1,
        "top_invalid_features": ["momentum_decay"],
        "top_invalid_states": ["very_strong"],
        "validation_notes_counts": {"invalid_state": 1},
        "invalid_specs_by_selected_source": {"commander_applied_policy": 1},
        "validation_notes_by_interpretation_basis": {"explicit_policy": 1},
        "notes": [],
    }
    out = build_policy_surface_quality_executive_summary(summary)

    assert out["status"] == "good"
    assert out["top_invalid_features"] == ["momentum_decay"]
    assert "schema 0.83" in out["headline"]
    assert build_policy_surface_quality_executive_line(summary) == out["headline"]
