from __future__ import annotations

from libs.core.evidence_identity import stable_evidence_id
from libs.reporting.evaluation.feedback_effectiveness import build_feedback_effectiveness
from libs.reporting.evaluation.strategist_effectiveness import build_strategist_effectiveness
from libs.runtime.scanner.control_eligibility import build_full_strategist_control_eligibility
from libs.runtime.strategist_feedback_trace import build_feedback_application_trace


def test_evidence_id_is_stable_across_artifact_timestamps() -> None:
    first = stable_evidence_id("memory", {"status": "ok", "generated_at": "one", "rows": [1, 2]})
    second = stable_evidence_id("memory", {"rows": [1, 2], "generated_at": "two", "status": "ok"})
    assert first == second


def test_full_strategist_control_eligibility_is_explicit() -> None:
    eligible = build_full_strategist_control_eligibility(
        {
            "candidate_source": "kiwoom_market_data",
            "scanner_candidate_source": "kiwoom",
            "scanner_source_policy": {},
            "selected_themes": [],
            "avoid_themes": [],
            "backfill_used": False,
            "scan_aggressiveness": 0.0,
        }
    )
    influenced = build_full_strategist_control_eligibility(
        {
            "candidate_source": "kiwoom_market_data",
            "scanner_candidate_source": "kiwoom",
            "scanner_source_policy": {"include_change_rate": True},
            "selected_themes": ["semiconductor"],
        }
    )
    assert eligible["eligible"] is True
    assert influenced["eligible"] is False
    assert "strategist_scanner_source_policy_present" in influenced["ineligibility_reasons"]
    assert "strategist_selected_themes_present" in influenced["ineligibility_reasons"]


def test_feedback_trace_marks_candidate_without_claiming_causality() -> None:
    trace = build_feedback_application_trace(
        feedback_packet={
            "feedback_id": "feedback-1",
            "source_day": "2026-08-25",
            "available": True,
            "consumed": True,
            "feedback_gate_reason": "auto_accepted",
        },
        strategist_output={
            "run_id": "run-1",
            "pre_llm_playbook": "pullback",
            "final_playbook": "breakout",
        },
    )
    assert trace["adoption_status"] == "CHANGE_OBSERVED_WITH_FEEDBACK_EXPOSURE"
    assert trace["changed_fields"] == ["playbook"]
    assert trace["causal_attribution"] is False


def test_effectiveness_reports_consume_q9_provenance() -> None:
    windows = [
        {
            "decision_id": "Q9-1",
            "scanner_control": {
                "top1_symbol": "005930",
                "full_strategist_control_eligibility": {"eligible": True},
            },
            "strategist_selection": {"selected_symbol": "000660"},
            "strategist_provenance": {
                "feedback": {
                    "feedback_id": "feedback-1",
                    "source_day": "2026-08-25",
                    "consumed": True,
                    "adoption_status": "CHANGE_OBSERVED_WITH_FEEDBACK_EXPOSURE",
                    "changed_fields": ["playbook"],
                }
            },
        }
    ]
    strategist = build_strategist_effectiveness([], [], windows)
    feedback = build_feedback_effectiveness([], windows)
    assert strategist["full_strategist_contribution"]["eligible_control_count"] == 1
    assert strategist["full_strategist_contribution"]["selection_change_count"] == 1
    assert feedback["exposure_count"] == 1
    assert feedback["adoption_count"] == 1
    assert feedback["records"][0]["later_decision_id"] == "Q9-1"
    assert feedback["causal_claim_allowed"] is False
