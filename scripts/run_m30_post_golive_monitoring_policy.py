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

from scripts.run_m30_release_signoff_checklist import main as signoff_main


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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _build_policy(*, release_ready: bool, required_fail_total: int, quality_gates_ok: bool) -> Tuple[str, Dict[str, Any]]:
    if release_ready and quality_gates_ok and required_fail_total == 0:
        return "normal", {
            "heartbeat_sec": 300,
            "alert_fail_on": "critical",
            "oncall_escalation": "none",
            "execution_mode": "normal",
            "manual_approval_only": False,
            "route_provider": "slack_webhook",
        }
    if required_fail_total <= 1:
        return "watch", {
            "heartbeat_sec": 180,
            "alert_fail_on": "warning",
            "oncall_escalation": "primary_oncall",
            "execution_mode": "degrade",
            "manual_approval_only": True,
            "route_provider": "slack_webhook",
        }
    return "incident", {
        "heartbeat_sec": 60,
        "alert_fail_on": "warning",
        "oncall_escalation": "primary_and_secondary_oncall",
        "execution_mode": "degrade",
        "manual_approval_only": True,
        "route_provider": "slack_webhook",
    }


def _build_markdown(out: Dict[str, Any]) -> str:
    policy = out.get("policy") if isinstance(out.get("policy"), dict) else {}
    signoff = out.get("signoff") if isinstance(out.get("signoff"), dict) else {}
    targets = out.get("monitoring_targets") if isinstance(out.get("monitoring_targets"), list) else []
    lines = [
        f"# M30 Post-go-live Monitoring Policy ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- release_ready: **{bool(out.get('release_ready'))}**",
        f"- escalation_level: **{out.get('escalation_level')}**",
        "",
        "## Sign-off Snapshot",
        "",
        f"- signoff_rc: {int(signoff.get('rc') or 0)}",
        f"- signoff_ok: {bool(signoff.get('ok'))}",
        f"- required_fail_total: {int(signoff.get('required_fail_total') or 0)}",
        f"- quality_gates_ok: {bool(signoff.get('quality_gates_ok'))}",
        "",
        "## Active Policy",
        "",
        f"- heartbeat_sec: {int(policy.get('heartbeat_sec') or 0)}",
        f"- alert_fail_on: {policy.get('alert_fail_on')}",
        f"- oncall_escalation: {policy.get('oncall_escalation')}",
        f"- execution_mode: {policy.get('execution_mode')}",
        f"- manual_approval_only: {bool(policy.get('manual_approval_only'))}",
        f"- route_provider: {policy.get('route_provider')}",
        "",
        "## Monitoring Targets",
        "",
    ]
    if targets:
        for t in targets:
            lines.append(f"- {t}")
    else:
        lines.append("- (none)")

    lines += ["", "## Failures", ""]
    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    if failures:
        for msg in failures:
            lines.append(f"- {msg}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M30-3 post-go-live monitoring/escalation policy check.")
    p.add_argument("--signoff-json-path", default="")
    p.add_argument("--event-log-dir", default="data/logs/m30_quality_gates")
    p.add_argument("--quality-report-dir", default="reports/m30_quality_gates")
    p.add_argument("--signoff-report-dir", default="reports/m30_signoff")
    p.add_argument("--report-dir", default="reports/m30_post_golive")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-run-signoff", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    signoff_obj: Dict[str, Any] = {}
    signoff_rc = -1
    raw_signoff = str(args.signoff_json_path or "").strip()
    if raw_signoff:
        signoff_obj = _read_json(Path(raw_signoff))
        signoff_rc = 0 if signoff_obj else 3

    if (not signoff_obj) and (not bool(args.no_run_signoff)):
        signoff_argv = [
            "--event-log-dir",
            str(Path(str(args.event_log_dir).strip())),
            "--quality-report-dir",
            str(Path(str(args.quality_report_dir).strip())),
            "--report-dir",
            str(Path(str(args.signoff_report_dir).strip())),
            "--day",
            day,
            "--json",
        ]
        if bool(args.inject_fail):
            signoff_argv.insert(-1, "--inject-fail")
        signoff_rc, signoff_obj = _run_json(signoff_main, signoff_argv)

    release_ready = bool(signoff_obj.get("release_ready"))
    quality_gates_ok = bool(signoff_obj.get("quality_gates_ok"))
    required_fail_total = int(signoff_obj.get("required_fail_total") or 0)
    escalation_level, policy = _build_policy(
        release_ready=release_ready,
        required_fail_total=required_fail_total,
        quality_gates_ok=quality_gates_ok,
    )

    checklist = signoff_obj.get("checklist") if isinstance(signoff_obj.get("checklist"), list) else []
    failed_required_ids: List[str] = []
    for row in checklist:
        if not isinstance(row, dict):
            continue
        if bool(row.get("required")) and not bool(row.get("passed")):
            rid = str(row.get("id") or "").strip()
            if rid:
                failed_required_ids.append(rid)

    monitoring_targets = [
        "strategist_llm.success_rate >= 99%",
        "strategist_llm.circuit_open_rate <= 1%",
        "execution.intents_blocked ratio baseline drift <= 10%",
        "broker_api.api_429_rate <= 2%",
        "incident_time_to_recovery_sec p95 <= 900",
    ]

    failures: List[str] = []
    if signoff_rc != 0:
        failures.append("signoff rc != 0")
    if not signoff_obj:
        failures.append("signoff output missing")
    if not bool(args.inject_fail):
        if not release_ready:
            failures.append("release_ready != true")
        if not quality_gates_ok:
            failures.append("quality_gates_ok != true")
        if required_fail_total != 0:
            failures.append("required_fail_total != 0")
        if escalation_level != "normal":
            failures.append("escalation_level != normal")
        if bool(policy.get("manual_approval_only")):
            failures.append("manual_approval_only != false")
    else:
        if release_ready:
            failures.append("inject_fail expected release_ready == false")
        if escalation_level == "normal":
            failures.append("inject_fail expected escalation_level != normal")
        if not bool(policy.get("manual_approval_only")):
            failures.append("inject_fail expected manual_approval_only == true")

    overall_ok = len(failures) == 0 and not bool(args.inject_fail)
    out: Dict[str, Any] = {
        "ok": overall_ok,
        "release_ready": release_ready,
        "day": day,
        "inject_fail": bool(args.inject_fail),
        "escalation_level": escalation_level,
        "policy": policy,
        "signoff": {
            "rc": int(signoff_rc),
            "ok": bool(signoff_obj.get("ok")) if isinstance(signoff_obj, dict) else False,
            "release_ready": bool(signoff_obj.get("release_ready")) if isinstance(signoff_obj, dict) else False,
            "quality_gates_ok": bool(signoff_obj.get("quality_gates_ok")) if isinstance(signoff_obj, dict) else False,
            "required_fail_total": int(signoff_obj.get("required_fail_total") or 0) if isinstance(signoff_obj, dict) else 0,
            "report_json_path": str(signoff_obj.get("report_json_path") or "") if isinstance(signoff_obj, dict) else "",
            "report_md_path": str(signoff_obj.get("report_md_path") or "") if isinstance(signoff_obj, dict) else "",
        },
        "failed_required_ids": failed_required_ids,
        "monitoring_targets": monitoring_targets,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m30_post_golive_policy_{day}.json"
    md_path = report_dir / f"m30_post_golive_policy_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} release_ready={release_ready} escalation_level={escalation_level} "
            f"manual_approval_only={bool(policy.get('manual_approval_only'))} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
