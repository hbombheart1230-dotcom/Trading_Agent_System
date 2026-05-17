from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List


StepRunner = Callable[..., Dict[str, Any]]
CommonStep = Callable[[Dict[str, Any]], Dict[str, Any]]
OptionalReportStep = Callable[[str], Dict[str, Any]]


def phase_template(name: str) -> Dict[str, Any]:
    return {"phase": name, "ok": False, "failure_reason": "", "steps": []}


def optional_report_step(step_id: str, *, report_name: str, reason: str) -> Dict[str, Any]:
    return {
        "step_id": str(step_id),
        "mode": "optional_report_disabled",
        "report_name": str(report_name),
        "rc": 0,
        "ok": True,
        "skipped": True,
        "skip_reason": str(reason),
        "stdout_tail": "",
        "stderr_tail": "",
        "error": "",
        "duration_sec": 0.0,
    }


def run_closeout_phase(
    args: Any,
    common: Dict[str, Any],
    *,
    root: Path,
    phase_name: str,
    run_subprocess: StepRunner,
    stop_live_loop_processes: CommonStep,
    closeout_backup_liquidation: CommonStep,
) -> Dict[str, Any]:
    out = phase_template(phase_name)
    py = str(common["python_path"])
    day = str(common["day"])
    event_log_path = str(common["event_log_path"])
    evidence_log_path = str(common["evidence_log_path"])
    intents_path = str(Path(common["event_log_path"]).with_name("intents.jsonl"))
    canonical_reports_root = Path(common["canonical_reports_root"])
    timeout_sec = int(common["timeout_sec"])
    generate_decision_story = bool(getattr(args, "generate_decision_story", False))
    generate_run_cards = bool(getattr(args, "generate_run_cards", False))
    steps: List[Dict[str, Any]] = []

    stop_step = stop_live_loop_processes(common)
    steps.append(stop_step)
    if not bool(stop_step.get("ok")):
        out["steps"] = steps
        out["failure_reason"] = "stop_session_loop_failed"
        return out

    steps.append(closeout_backup_liquidation(common))

    steps.append(
        run_subprocess(
            step_id="closeout.m31_slo_incident",
            command=[
                py,
                str(root / "scripts" / "run_m31_slo_incident_review_check.py"),
                "--event-log-path",
                event_log_path,
                "--policy-report-dir",
                str(root / "reports" / "milestones" / "m30_post_golive"),
                "--signoff-report-dir",
                str(root / "reports" / "milestones" / "m30_golive"),
                "--report-dir",
                str(canonical_reports_root / "milestones" / "m31_slo_incident"),
                "--day",
                day,
                "--json",
            ],
            cwd=root,
            timeout_sec=timeout_sec,
        )
    )

    metrics_env = os.environ.copy()
    metrics_env["EVENT_LOG_PATH"] = event_log_path
    metrics_env["REPORT_DIR"] = str(canonical_reports_root)
    metrics_env["METRICS_DAY"] = day
    steps.append(
        run_subprocess(
            step_id="closeout.metrics",
            command=[py, str(root / "scripts" / "generate_metrics_report.py")],
            cwd=root,
            env=metrics_env,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        run_subprocess(
            step_id="closeout.operator_summary",
            command=[
                py,
                str(root / "scripts" / "run_operator_daily_summary.py"),
                "--event-log-path",
                event_log_path,
                "--metrics-report-dir",
                str(canonical_reports_root / "metrics"),
                "--m30-post-golive-dir",
                str(root / "reports" / "milestones" / "m30_post_golive"),
                "--m30-golive-dir",
                str(root / "reports" / "milestones" / "m30_golive"),
                "--m31-slo-incident-dir",
                str(canonical_reports_root / "milestones" / "m31_slo_incident"),
                "--report-dir",
                str(canonical_reports_root),
                "--day",
                day,
                "--json",
            ],
            cwd=root,
            timeout_sec=timeout_sec,
        )
    )

    if generate_decision_story:
        steps.append(
            run_subprocess(
                step_id="closeout.decision_story",
                command=[
                    py,
                    str(root / "scripts" / "run_decision_story_report.py"),
                    "--event-log-path",
                    event_log_path,
                    "--report-dir",
                    str(canonical_reports_root / "dev" / "manual" / "decision_story"),
                    "--day",
                    day,
                    "--json",
                ],
                cwd=root,
                timeout_sec=timeout_sec,
            )
        )
    else:
        steps.append(
            optional_report_step(
                "closeout.decision_story",
                report_name="decision_story",
                reason="disabled_by_default_generate_decision_story_flag_required",
            )
        )

    if generate_run_cards:
        steps.append(
            run_subprocess(
                step_id="closeout.run_cards",
                command=[
                    py,
                    str(root / "scripts" / "run_run_card_report.py"),
                    "--event-log-path",
                    event_log_path,
                    "--report-dir",
                    str(canonical_reports_root / "dev" / "manual" / "run_cards"),
                    "--day",
                    day,
                    "--json",
                ],
                cwd=root,
                timeout_sec=timeout_sec,
            )
        )
    else:
        steps.append(
            optional_report_step(
                "closeout.run_cards",
                report_name="run_cards",
                reason="disabled_by_default_generate_run_cards_flag_required",
            )
        )

    daily_env = os.environ.copy()
    daily_env["EVENT_LOG_PATH"] = event_log_path
    daily_env["REPORT_DIR"] = str(canonical_reports_root)
    daily_env["REPORT_DAY"] = day
    steps.append(
        run_subprocess(
            step_id="closeout.daily",
            command=[py, str(root / "scripts" / "generate_daily_report.py")],
            cwd=root,
            env=daily_env,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        run_subprocess(
            step_id="closeout.reporter_analysis",
            command=[
                py,
                str(root / "scripts" / "run_reporter_analysis_report.py"),
                "--env-path",
                str(common["env_path"]),
                "--event-log-path",
                event_log_path,
                "--intents-path",
                intents_path,
                "--reports-root",
                str(canonical_reports_root),
                "--report-dir",
                str(canonical_reports_root / "dev" / "analysis" / "reporter_analysis"),
                "--day",
                day,
                "--json",
            ],
            cwd=root,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        run_subprocess(
            step_id="closeout.live_execution_bundles",
            command=[
                py,
                str(root / "scripts" / "run_live_execution_bundle_report.py"),
                "--env-path",
                str(common["env_path"]),
                "--event-log-path",
                event_log_path,
                "--evidence-log-path",
                evidence_log_path,
                "--reports-root",
                str(canonical_reports_root),
                "--report-dir",
                str(canonical_reports_root / "dev" / "analysis" / "live_execution_bundles"),
                "--intents-path",
                intents_path,
                "--day",
                day,
                "--json",
            ],
            cwd=root,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        run_subprocess(
            step_id="closeout.report_inventory",
            command=[
                py,
                str(root / "scripts" / "run_report_maintenance.py"),
                "--report-root",
                str(canonical_reports_root),
                "--event-log-path",
                event_log_path,
                "--apply",
                "--include-legacy-root-daily",
                "--json",
            ],
            cwd=root,
            timeout_sec=timeout_sec,
        )
    )

    out["steps"] = steps
    failed = [s for s in steps if not bool(s.get("ok"))]
    out["ok"] = len(failed) == 0
    if failed:
        out["failure_reason"] = "closeout_failed:" + ",".join(str(s.get("step_id") or "") for s in failed)
    return out
