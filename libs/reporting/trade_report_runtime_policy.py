from __future__ import annotations

from typing import Any, Dict, Mapping

from libs.llm.model_catalog import resolve_policy_llm_slot
from libs.llm.model_names import normalize_openrouter_model_name


def report_reason_human(code: str) -> str:
    mapping = {
        "no_executed_lifecycle": "No executed trade lifecycle was created for this run.",
        "decision_only_run": "This run was decision-only, so a full AI trade report was not generated.",
        "hold_only_run": "This run only updated hold/monitor state, so a full AI trade report was not generated.",
        "execution_failed": "Execution did not complete successfully, so a full AI trade report was skipped.",
        "missing_story_input": "Trade story input was not created, so report generation could not continue.",
        "llm_generation_failed": "Trade story input existed, but AI report generation failed.",
        "artifact_write_failed": "AI report generation ran, but writing report artifacts failed.",
        "missing_report_linkage": "A linked AI trade report could not be found for this run.",
        "report_not_requested": "AI trade report generation was not requested for this run.",
        "still_open_lifecycle": "This trade lifecycle is still open, so the full AI report is pending.",
        "awaiting_exit_for_full_report": "This trade is still open. The full AI report is generated after exit/closure.",
    }
    return mapping.get(str(code or "").strip().lower(), "AI report diagnostics are not fully classified.")



def report_next_step(code: str) -> str:
    mapping = {
        "no_executed_lifecycle": "Continue with Operator Brief. Generate full AI report only for executed lifecycles.",
        "decision_only_run": "Continue with Operator Brief. Generate full AI report after executed lifecycle events.",
        "hold_only_run": "Continue monitoring. Generate full AI report after entry/exit execution is formed.",
        "execution_failed": "Review execution failure details and rerun report generation after stabilization.",
        "missing_story_input": "Fix trade story input generation first, then retry.",
        "llm_generation_failed": "Check OpenRouter/model connectivity and retry report generation.",
        "artifact_write_failed": "Check filesystem write path and permissions, then retry.",
        "missing_report_linkage": "Regenerate lifecycle/report linkage for this run and retry.",
        "report_not_requested": "Enable AI report generation policy and rerun.",
        "still_open_lifecycle": "Generate the full AI report after lifecycle exit/closure.",
        "awaiting_exit_for_full_report": "Generate the final AI report after exit/closure.",
    }
    return mapping.get(str(code or "").strip().lower(), "Review diagnostics and continue with Operator Brief.")



def base_report_diagnostics(model_hint: str) -> Dict[str, Any]:
    return {
        "report_status": "pending",
        "report_reason_code": "",
        "report_reason_human": "",
        "report_generation_reason": "",
        "generation_attempted": False,
        "generation_ts": "",
        "story_input_available": False,
        "report_output_available": False,
        "report_artifact_available": False,
        "llm_provider": "OpenRouter",
        "llm_model_used": normalize_openrouter_model_name(model_hint) or "openrouter/free",
        "expected_generation_mode": "per-trade free model report",
        "last_error_message": "",
        "next_expected_step": "",
        "deterministic_report_status": "skipped",
        "llm_brief_status": "skipped",
        "ai_trade_report_status": "skipped",
    }



def resolve_trade_report_policy(
    *,
    runtime_state: Mapping[str, Any] | None = None,
    story_input: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    story_input_obj = dict(story_input or {})
    runtime_state_obj = dict(runtime_state or {})
    llm_slot = resolve_policy_llm_slot(
        {
            "applied_policy": (
                story_input_obj.get("applied_policy")
                if isinstance(story_input_obj.get("applied_policy"), dict)
                else runtime_state_obj.get("applied_policy")
                if isinstance(runtime_state_obj.get("applied_policy"), dict)
                else {}
            ),
            "commander": story_input_obj.get("commander") if isinstance(story_input_obj.get("commander"), dict) else {},
            "reporter_policy": story_input_obj.get("reporter_policy") if isinstance(story_input_obj.get("reporter_policy"), dict) else {},
        },
        "reporter",
        "intraday",
        default_profile="fast_free",
    )
    for container, source in (
        (
            (((story_input_obj.get("applied_policy") or {}).get("reporter") or {}).get("trade_report") or {}),
            "story_input.applied_policy",
        ),
        (
            ((((story_input_obj.get("commander") or {}).get("applied_policy") or {}).get("reporter") or {}).get("trade_report") or {}),
            "story_input.commander.applied_policy",
        ),
        (
            (((runtime_state_obj.get("applied_policy") or {}).get("reporter") or {}).get("trade_report") or {}),
            "runtime_state.applied_policy",
        ),
    ):
        if isinstance(container, dict) and container:
            return {
                "enabled": bool(container.get("enabled", True)),
                "generate_on_open": bool(container.get("generate_on_open", False)),
                "policy_source": str(container.get("policy_source") or source),
                "llm_profile": str(llm_slot.get("profile") or "fast_free"),
                "llm_primary": str(llm_slot.get("primary") or ""),
                "llm_fallback": str(llm_slot.get("fallback") or ""),
            }
    return {
        "enabled": True,
        "generate_on_open": False,
        "policy_source": "default",
        "llm_profile": str(llm_slot.get("profile") or "fast_free"),
        "llm_primary": str(llm_slot.get("primary") or ""),
        "llm_fallback": str(llm_slot.get("fallback") or ""),
    }



def seed_diagnostics_for_policy(
    *,
    lifecycle_status: str,
    story_type: str,
    report_requested: bool,
    story_input_available: bool,
    model_hint: str,
    generate_on_open: bool,
) -> Dict[str, Any]:
    diagnostics = base_report_diagnostics(model_hint)
    diagnostics["story_input_available"] = bool(story_input_available)
    status = str(lifecycle_status or "").strip().lower()
    story = str(story_type or "").strip().lower()

    if not story_input_available:
        diagnostics["report_status"] = "failed"
        diagnostics["report_reason_code"] = "missing_story_input"
        diagnostics["report_reason_human"] = report_reason_human("missing_story_input")
        diagnostics["next_expected_step"] = report_next_step("missing_story_input")
        return {"diagnostics": diagnostics, "should_attempt_generation": False}

    if not report_requested:
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "report_not_requested"
        diagnostics["report_reason_human"] = report_reason_human("report_not_requested")
        diagnostics["next_expected_step"] = report_next_step("report_not_requested")
        return {"diagnostics": diagnostics, "should_attempt_generation": False}

    if story == "decision_only":
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "decision_only_run"
        diagnostics["report_reason_human"] = report_reason_human("decision_only_run")
        diagnostics["next_expected_step"] = report_next_step("decision_only_run")
        return {"diagnostics": diagnostics, "should_attempt_generation": False}

    if story == "failed_execution":
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "execution_failed"
        diagnostics["report_reason_human"] = report_reason_human("execution_failed")
        diagnostics["next_expected_step"] = report_next_step("execution_failed")
        return {"diagnostics": diagnostics, "should_attempt_generation": False}

    if status == "open" and not bool(generate_on_open):
        diagnostics["report_status"] = "pending"
        diagnostics["report_reason_code"] = "awaiting_exit_for_full_report"
        diagnostics["report_reason_human"] = report_reason_human("awaiting_exit_for_full_report")
        diagnostics["next_expected_step"] = report_next_step("awaiting_exit_for_full_report")
        return {"diagnostics": diagnostics, "should_attempt_generation": False}

    return {"diagnostics": diagnostics, "should_attempt_generation": True}
