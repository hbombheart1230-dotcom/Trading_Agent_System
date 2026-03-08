from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m30_final_golive_signoff import main as m30_final_main
from scripts.run_m30_post_golive_monitoring_policy import main as m30_policy_main
from scripts.run_m31_mock_investor_exam_check import main as m31_mock_exam_main
from scripts.run_m31_slo_incident_review_check import main as m31_slo_main


def _run_json(main_fn, argv: List[str]) -> Tuple[int, Dict[str, Any]]:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main_fn(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _item(*, item_id: str, title: str, passed: bool, evidence: str, required: bool = True) -> Dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "required": bool(required),
        "passed": bool(passed),
        "evidence": str(evidence),
    }


def _build_markdown(out: Dict[str, Any]) -> str:
    stage = out.get("stage_checks") if isinstance(out.get("stage_checks"), dict) else {}
    runtime = out.get("runtime_profile") if isinstance(out.get("runtime_profile"), dict) else {}
    guard = out.get("guardrails") if isinstance(out.get("guardrails"), dict) else {}
    checklist = out.get("checklist") if isinstance(out.get("checklist"), list) else []
    missing = out.get("missing_prerequisites") if isinstance(out.get("missing_prerequisites"), list) else []
    lines = [
        f"# M31 Mock Exam Readiness Check ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- required_pass_total: **{int(out.get('required_pass_total') or 0)}**",
        f"- required_fail_total: **{int(out.get('required_fail_total') or 0)}**",
        "",
        "## Stage Checks",
        "",
        f"- m30_final_signoff: rc={int(stage.get('m30_final_signoff_rc') or 0)} ok={bool(stage.get('m30_final_signoff_ok'))}",
        f"- m30_post_golive_policy: rc={int(stage.get('m30_post_golive_policy_rc') or 0)} ok={bool(stage.get('m30_post_golive_policy_ok'))}",
        f"- m31_slo_incident: rc={int(stage.get('m31_slo_incident_rc') or 0)} ok={bool(stage.get('m31_slo_incident_ok'))}",
        f"- m31_mock_exam: rc={int(stage.get('m31_mock_exam_rc') or 0)} ok={bool(stage.get('m31_mock_exam_ok'))}",
        "",
        "## Runtime Profile",
        "",
        f"- RUNTIME_PROFILE: **{runtime.get('RUNTIME_PROFILE')}**",
        f"- KIWOOM_MODE: **{runtime.get('KIWOOM_MODE')}**",
        f"- APPROVAL_MODE: **{runtime.get('APPROVAL_MODE')}**",
        f"- EXECUTION_ENABLED: **{bool(runtime.get('EXECUTION_ENABLED'))}**",
        f"- ALLOW_REAL_EXECUTION: **{bool(runtime.get('ALLOW_REAL_EXECUTION'))}**",
        "",
        "## Guardrails",
        "",
        f"- allowlist_size: **{int(guard.get('allowlist_size') or 0)}**",
        f"- max_notional_key: **{guard.get('max_notional_key')}**",
        f"- max_notional: **{float(guard.get('max_notional') or 0.0):.2f}**",
        f"- daily_loss_limit: **{float(guard.get('daily_loss_limit') or 0.0):.6f}**",
        "",
        "## Checklist",
        "",
    ]
    for item in checklist:
        mark = "x" if bool(item.get("passed")) else " "
        lines.append(f"- [{mark}] {item.get('title')} | evidence={item.get('evidence')}")

    lines += ["", "## Missing Prerequisites", ""]
    if missing:
        for row in missing:
            lines.append(f"- {row}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aggregate M30/M31 artifacts into one mock exam readiness checklist.")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--m30-event-log-dir", default="data/logs/m30_golive")
    p.add_argument("--m30-quality-report-dir", default="reports/m30_quality_gates")
    p.add_argument("--m30-signoff-report-dir", default="reports/m30_signoff")
    p.add_argument("--m30-policy-report-dir", default="reports/m30_post_golive")
    p.add_argument("--m30-golive-report-dir", default="reports/m30_golive")
    p.add_argument("--m31-slo-report-dir", default="reports/m31_slo_incident")
    p.add_argument("--m31-mock-exam-report-dir", default="reports/m31_mock_exam")
    p.add_argument("--report-dir", default="reports/m31_mock_exam_readiness")
    p.add_argument("--strict-session", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    env_path = Path(str(args.env_path).strip())
    event_log_path = Path(str(args.event_log_path).strip())

    m30_event_log_dir = Path(str(args.m30_event_log_dir).strip())
    m30_quality_report_dir = Path(str(args.m30_quality_report_dir).strip())
    m30_signoff_report_dir = Path(str(args.m30_signoff_report_dir).strip())
    m30_policy_report_dir = Path(str(args.m30_policy_report_dir).strip())
    m30_golive_report_dir = Path(str(args.m30_golive_report_dir).strip())
    m31_slo_report_dir = Path(str(args.m31_slo_report_dir).strip())
    m31_mock_exam_report_dir = Path(str(args.m31_mock_exam_report_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    m30_final_rc, m30_final = _run_json(
        m30_final_main,
        [
            "--event-log-dir",
            str(m30_event_log_dir),
            "--quality-report-dir",
            str(m30_quality_report_dir),
            "--signoff-report-dir",
            str(m30_signoff_report_dir),
            "--policy-report-dir",
            str(m30_policy_report_dir),
            "--report-dir",
            str(m30_golive_report_dir),
            "--day",
            day,
            "--no-clear",
            "--json",
        ],
    )

    m30_2 = m30_final.get("m30_2_signoff") if isinstance(m30_final.get("m30_2_signoff"), dict) else {}
    signoff_json_path = str(m30_2.get("report_json_path") or "")
    m30_policy_rc, m30_policy = _run_json(
        m30_policy_main,
        [
            "--signoff-json-path",
            signoff_json_path,
            "--event-log-dir",
            str(m30_event_log_dir),
            "--quality-report-dir",
            str(m30_quality_report_dir),
            "--signoff-report-dir",
            str(m30_signoff_report_dir),
            "--report-dir",
            str(m30_policy_report_dir),
            "--day",
            day,
            "--json",
        ],
    )

    m31_slo_rc, m31_slo = _run_json(
        m31_slo_main,
        [
            "--event-log-path",
            str(event_log_path),
            "--policy-report-dir",
            str(m30_policy_report_dir),
            "--signoff-report-dir",
            str(m30_golive_report_dir),
            "--report-dir",
            str(m31_slo_report_dir),
            "--day",
            day,
            "--json",
        ],
    )

    m31_mock_argv = [
        "--env-path",
        str(env_path),
        "--event-log-path",
        str(event_log_path),
        "--report-dir",
        str(m31_mock_exam_report_dir),
        "--day",
        day,
        "--json",
    ]
    if bool(args.strict_session):
        m31_mock_argv.insert(-1, "--strict-session")
    m31_mock_rc, m31_mock = _run_json(m31_mock_exam_main, m31_mock_argv)

    runtime = m31_mock.get("runtime_mode") if isinstance(m31_mock.get("runtime_mode"), dict) else {}
    guards = m31_mock.get("guardrails") if isinstance(m31_mock.get("guardrails"), dict) else {}

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="m30_final_signoff_ok",
            title="M30 final signoff artifact is green",
            passed=(m30_final_rc == 0 and bool(m30_final.get("approved"))),
            evidence=f"rc={m30_final_rc}, approved={bool(m30_final.get('approved'))}",
        ),
        _item(
            item_id="m30_post_golive_policy_ok",
            title="M30 post-go-live monitoring policy is green and normal",
            passed=(m30_policy_rc == 0 and bool(m30_policy.get("ok")) and str(m30_policy.get("escalation_level") or "") == "normal"),
            evidence=f"rc={m30_policy_rc}, ok={bool(m30_policy.get('ok'))}, escalation_level={m30_policy.get('escalation_level')}",
        ),
        _item(
            item_id="m31_slo_incident_ok",
            title="M31-1 SLO/incident review check passes",
            passed=(m31_slo_rc == 0 and bool(m31_slo.get("ok"))),
            evidence=f"rc={m31_slo_rc}, ok={bool(m31_slo.get('ok'))}",
        ),
        _item(
            item_id="m31_mock_exam_gate_ok",
            title="M31-2 mock exam gate passes",
            passed=(m31_mock_rc == 0 and bool(m31_mock.get("ok"))),
            evidence=f"rc={m31_mock_rc}, ok={bool(m31_mock.get('ok'))}",
        ),
        _item(
            item_id="runtime_profile_staging",
            title="Runtime profile is staging",
            passed=(str(runtime.get("RUNTIME_PROFILE") or "").strip().lower() == "staging"),
            evidence=f"RUNTIME_PROFILE={runtime.get('RUNTIME_PROFILE')}",
        ),
        _item(
            item_id="kiwoom_mode_mock",
            title="Kiwoom mode is mock",
            passed=(str(runtime.get("KIWOOM_MODE") or "").strip().lower() == "mock"),
            evidence=f"KIWOOM_MODE={runtime.get('KIWOOM_MODE')}",
        ),
        _item(
            item_id="approval_mode_manual",
            title="Approval mode is manual for exam",
            passed=(str(runtime.get("APPROVAL_MODE") or "").strip().lower() == "manual"),
            evidence=f"APPROVAL_MODE={runtime.get('APPROVAL_MODE')}",
        ),
        _item(
            item_id="execution_guard_mode",
            title="Execution enabled and real execution disabled",
            passed=(bool(runtime.get("EXECUTION_ENABLED")) and not bool(runtime.get("ALLOW_REAL_EXECUTION"))),
            evidence=(
                f"EXECUTION_ENABLED={bool(runtime.get('EXECUTION_ENABLED'))}, "
                f"ALLOW_REAL_EXECUTION={bool(runtime.get('ALLOW_REAL_EXECUTION'))}"
            ),
        ),
        _item(
            item_id="guardrails_fixed",
            title="Allowlist/notional/daily-loss guardrails are configured",
            passed=(
                int(guards.get("allowlist_size") or 0) > 0
                and float(guards.get("max_notional") or 0.0) > 0.0
                and float(guards.get("daily_loss_limit") or 0.0) > 0.0
            ),
            evidence=(
                f"allowlist_size={int(guards.get('allowlist_size') or 0)}, "
                f"max_notional={float(guards.get('max_notional') or 0.0)}, "
                f"daily_loss_limit={float(guards.get('daily_loss_limit') or 0.0)}"
            ),
        ),
    ]

    missing_prerequisites: List[str] = []
    for item in checklist:
        if bool(item.get("required")) and not bool(item.get("passed")):
            missing_prerequisites.append(f"{item.get('id')}: {item.get('evidence')}")

    required_total = int(sum(1 for x in checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)
    ok = required_fail_total == 0

    out: Dict[str, Any] = {
        "ok": bool(ok),
        "day": day,
        "strict_session": bool(args.strict_session),
        "inputs": {
            "env_path": str(env_path),
            "event_log_path": str(event_log_path),
        },
        "stage_checks": {
            "m30_final_signoff_rc": int(m30_final_rc),
            "m30_final_signoff_ok": bool(m30_final.get("approved")),
            "m30_post_golive_policy_rc": int(m30_policy_rc),
            "m30_post_golive_policy_ok": bool(m30_policy.get("ok")),
            "m31_slo_incident_rc": int(m31_slo_rc),
            "m31_slo_incident_ok": bool(m31_slo.get("ok")),
            "m31_mock_exam_rc": int(m31_mock_rc),
            "m31_mock_exam_ok": bool(m31_mock.get("ok")),
        },
        "runtime_profile": {
            "RUNTIME_PROFILE": str(runtime.get("RUNTIME_PROFILE") or ""),
            "KIWOOM_MODE": str(runtime.get("KIWOOM_MODE") or ""),
            "APPROVAL_MODE": str(runtime.get("APPROVAL_MODE") or ""),
            "EXECUTION_ENABLED": bool(runtime.get("EXECUTION_ENABLED")),
            "ALLOW_REAL_EXECUTION": bool(runtime.get("ALLOW_REAL_EXECUTION")),
        },
        "guardrails": {
            "allowlist_size": int(guards.get("allowlist_size") or 0),
            "max_notional_key": str(guards.get("max_notional_key") or ""),
            "max_notional": float(guards.get("max_notional") or 0.0),
            "daily_loss_limit": float(guards.get("daily_loss_limit") or 0.0),
        },
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "missing_prerequisites": missing_prerequisites,
    }

    js_path = report_dir / f"m31_mock_exam_readiness_{day}.json"
    md_path = report_dir / f"m31_mock_exam_readiness_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={bool(ok)} day={day} required_fail_total={required_fail_total} "
            f"report_json={js_path} report_md={md_path}"
        )
        for row in missing_prerequisites:
            print(row)
    return 0 if bool(ok) else 3


if __name__ == "__main__":
    raise SystemExit(main())
