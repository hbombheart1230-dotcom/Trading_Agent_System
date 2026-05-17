from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from libs.runtime.mock_exam_day.closeout_phase import phase_template
from libs.runtime.mock_exam_day.common import latest_event_day, read_env_file
from libs.runtime.runtime_output_helpers import parse_stdout_json


StepRunner = Callable[..., Dict[str, Any]]
RuntimeModeChecker = Callable[[Dict[str, str]], Dict[str, Any]]


def run_preopen_phase(
    args: Any,
    common: Dict[str, Any],
    *,
    root: Path,
    phase_name: str,
    run_subprocess: StepRunner,
    runtime_mode_checks: RuntimeModeChecker,
) -> Dict[str, Any]:
    out = phase_template(phase_name)
    py = str(common["python_path"])
    day = str(common["day"])
    canonical_reports_root = Path(common["canonical_reports_root"])
    event_log_path = Path(common["event_log_path"])

    step1 = run_subprocess(
        step_id="preopen.m30_final_signoff",
        command=[
            py,
            str(root / "scripts" / "run_m30_final_golive_signoff.py"),
            "--event-log-dir",
            str(root / "data" / "logs" / "milestones" / "m30" / "golive"),
            "--quality-report-dir",
            str(root / "reports" / "milestones" / "m30_quality_gates"),
            "--signoff-report-dir",
            str(root / "reports" / "milestones" / "m30_signoff"),
            "--policy-report-dir",
            str(root / "reports" / "milestones" / "m30_post_golive"),
            "--report-dir",
            str(root / "reports" / "milestones" / "m30_golive"),
            "--day",
            day,
            "--no-clear",
            "--json",
        ],
        cwd=root,
        timeout_sec=int(common["timeout_sec"]),
    )
    out["steps"].append(step1)
    if not bool(step1.get("ok")):
        out["failure_reason"] = "m30_final_signoff_failed"
        return out

    step1_obj = parse_stdout_json(str(step1.get("stdout_tail") or ""))
    m30_2_signoff = step1_obj.get("m30_2_signoff") if isinstance(step1_obj.get("m30_2_signoff"), dict) else {}
    m30_2_signoff_json_path = str(m30_2_signoff.get("report_json_path") or "").strip()
    if not m30_2_signoff_json_path:
        m30_2_signoff_json_path = str(root / "reports" / "milestones" / "m30_signoff" / f"m30_release_signoff_{day}.json")

    step2 = run_subprocess(
        step_id="preopen.m30_post_golive_policy",
        command=[
            py,
            str(root / "scripts" / "run_m30_post_golive_monitoring_policy.py"),
            "--signoff-json-path",
            str(m30_2_signoff_json_path),
            "--event-log-dir",
            str(root / "data" / "logs" / "milestones" / "m30" / "golive"),
            "--quality-report-dir",
            str(root / "reports" / "milestones" / "m30_quality_gates"),
            "--signoff-report-dir",
            str(root / "reports" / "milestones" / "m30_signoff"),
            "--report-dir",
            str(root / "reports" / "milestones" / "m30_post_golive"),
            "--day",
            day,
            "--json",
        ],
        cwd=root,
        timeout_sec=int(common["timeout_sec"]),
    )
    out["steps"].append(step2)
    if not bool(step2.get("ok")):
        out["failure_reason"] = "m30_post_golive_policy_failed"
        return out

    requested_readiness_day = str(args.preopen_readiness_day or "").strip() or day
    obj3, readiness_ok, readiness_day_used = _run_readiness_check(
        common,
        root=root,
        py=py,
        day=day,
        requested_readiness_day=requested_readiness_day,
        canonical_reports_root=canonical_reports_root,
        event_log_path=event_log_path,
        run_subprocess=run_subprocess,
    )
    out["steps"].extend(obj3.pop("_steps", []))
    out["m31_mock_exam_readiness"] = obj3
    out["m31_mock_exam_readiness_day_used"] = readiness_day_used
    if not readiness_ok:
        out["failure_reason"] = "m31_mock_exam_readiness_failed"
        return out

    env_obj = read_env_file(Path(common["env_path"]))
    mode = runtime_mode_checks(env_obj)
    out["runtime_mode"] = mode
    if not bool(mode.get("ok")):
        out["failure_reason"] = "runtime_mode_policy_failed"
        return out

    out["ok"] = True
    return out


def _run_readiness_check(
    common: Dict[str, Any],
    *,
    root: Path,
    py: str,
    day: str,
    requested_readiness_day: str,
    canonical_reports_root: Path,
    event_log_path: Path,
    run_subprocess: StepRunner,
) -> tuple[Dict[str, Any], bool, str]:
    steps = []
    step3 = run_subprocess(
        step_id="preopen.m31_mock_exam_readiness_check",
        command=[
            py,
            str(root / "scripts" / "run_m31_mock_exam_readiness_check.py"),
            "--day",
            requested_readiness_day,
            "--env-path",
            str(common["env_path"]),
            "--event-log-path",
            str(event_log_path),
            "--report-dir",
            str(canonical_reports_root / "milestones" / "m31_mock_exam_readiness"),
            "--allow-offhours",
            "--json",
        ],
        cwd=root,
        timeout_sec=int(common["timeout_sec"]),
    )
    steps.append(step3)
    obj3 = parse_stdout_json(str(step3.get("stdout_tail") or ""))
    readiness_ok = bool(step3.get("ok")) and bool(obj3.get("ok"))
    readiness_day_used = requested_readiness_day

    if not readiness_ok and requested_readiness_day == day:
        missing = obj3.get("missing_prerequisites") if isinstance(obj3.get("missing_prerequisites"), list) else []
        only_slo_gap = bool(missing) and all("m31_slo_incident_ok" in str(x) for x in missing)
        fallback_day: Optional[str] = latest_event_day(event_log_path, before_day=day)
        if only_slo_gap and fallback_day:
            step3b = run_subprocess(
                step_id="preopen.m31_mock_exam_readiness_check_fallback",
                command=[
                    py,
                    str(root / "scripts" / "run_m31_mock_exam_readiness_check.py"),
                    "--day",
                    str(fallback_day),
                    "--env-path",
                    str(common["env_path"]),
                    "--event-log-path",
                    str(event_log_path),
                    "--report-dir",
                    str(canonical_reports_root / "milestones" / "m31_mock_exam_readiness"),
                    "--allow-offhours",
                    "--json",
                ],
                cwd=root,
                timeout_sec=int(common["timeout_sec"]),
            )
            steps.append(step3b)
            obj3b = parse_stdout_json(str(step3b.get("stdout_tail") or ""))
            if bool(step3b.get("ok")) and bool(obj3b.get("ok")):
                obj3 = obj3b
                readiness_ok = True
                readiness_day_used = str(fallback_day)

    obj3["_steps"] = steps
    return obj3, readiness_ok, readiness_day_used
