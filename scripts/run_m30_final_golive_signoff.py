from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m30_post_golive_monitoring_policy import main as m30_3_main
from scripts.run_m30_quality_gates_bundle import main as m30_1_main
from scripts.run_m30_release_signoff_checklist import main as m30_2_main


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


def _build_markdown(out: Dict[str, Any]) -> str:
    m30_1 = out.get("m30_1_quality_gates") if isinstance(out.get("m30_1_quality_gates"), dict) else {}
    m30_2 = out.get("m30_2_signoff") if isinstance(out.get("m30_2_signoff"), dict) else {}
    m30_3 = out.get("m30_3_policy") if isinstance(out.get("m30_3_policy"), dict) else {}
    lines = [
        f"# M30 Final Go-live Signoff ({out.get('day')})",
        "",
        f"- approved: **{bool(out.get('approved'))}**",
        f"- go_live_decision: **{out.get('go_live_decision')}**",
        f"- failure_total: **{int(out.get('failure_total') or 0)}**",
        "",
        "## Stage Status",
        "",
        f"- m30_1_quality_gates: rc={int(m30_1.get('rc') or 0)} ok={bool(m30_1.get('ok'))}",
        f"- m30_2_release_signoff: rc={int(m30_2.get('rc') or 0)} release_ready={bool(m30_2.get('release_ready'))}",
        f"- m30_3_post_golive_policy: rc={int(m30_3.get('rc') or 0)} escalation_level={m30_3.get('escalation_level')}",
        "",
        "## Failures",
        "",
    ]
    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    if failures:
        for msg in failures:
            lines.append(f"- {msg}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M30-4 final go-live signoff aggregator.")
    p.add_argument("--event-log-dir", default="data/logs/m30_golive")
    p.add_argument("--quality-report-dir", default="reports/m30_quality_gates")
    p.add_argument("--signoff-report-dir", default="reports/m30_signoff")
    p.add_argument("--policy-report-dir", default="reports/m30_post_golive")
    p.add_argument("--report-dir", default="reports/m30_golive")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    inject_fail = bool(args.inject_fail)

    event_log_dir = Path(str(args.event_log_dir).strip())
    quality_report_dir = Path(str(args.quality_report_dir).strip())
    signoff_report_dir = Path(str(args.signoff_report_dir).strip())
    policy_report_dir = Path(str(args.policy_report_dir).strip())
    report_dir = Path(str(args.report_dir).strip())

    if not bool(args.no_clear):
        if event_log_dir.exists():
            shutil.rmtree(event_log_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    event_log_dir.mkdir(parents=True, exist_ok=True)
    quality_report_dir.mkdir(parents=True, exist_ok=True)
    signoff_report_dir.mkdir(parents=True, exist_ok=True)
    policy_report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    m30_1_argv = [
        "--event-log-dir",
        str(event_log_dir / "m30_1"),
        "--report-dir",
        str(quality_report_dir),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m30_1_argv.insert(-1, "--inject-fail")
    m30_1_rc, m30_1 = _run_json(m30_1_main, m30_1_argv)

    m30_1_json_path = str(m30_1.get("report_json_path") or "")
    m30_2_argv = [
        "--quality-gates-json-path",
        m30_1_json_path,
        "--event-log-dir",
        str(event_log_dir / "m30_2"),
        "--quality-report-dir",
        str(quality_report_dir),
        "--report-dir",
        str(signoff_report_dir),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m30_2_argv.insert(-1, "--inject-fail")
    m30_2_rc, m30_2 = _run_json(m30_2_main, m30_2_argv)

    m30_2_json_path = str(m30_2.get("report_json_path") or "")
    m30_3_argv = [
        "--signoff-json-path",
        m30_2_json_path,
        "--event-log-dir",
        str(event_log_dir / "m30_3"),
        "--quality-report-dir",
        str(quality_report_dir),
        "--signoff-report-dir",
        str(signoff_report_dir),
        "--report-dir",
        str(policy_report_dir),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m30_3_argv.insert(-1, "--inject-fail")
    m30_3_rc, m30_3 = _run_json(m30_3_main, m30_3_argv)

    failures: List[str] = []
    if not inject_fail:
        if m30_1_rc != 0 or not bool(m30_1.get("ok")):
            failures.append("m30_1_quality_gates not green")
        if m30_2_rc != 0 or not bool(m30_2.get("release_ready")):
            failures.append("m30_2_release_signoff not ready")
        if m30_3_rc != 0 or str(m30_3.get("escalation_level") or "") != "normal":
            failures.append("m30_3_policy escalation_level != normal")
        policy = m30_3.get("policy") if isinstance(m30_3.get("policy"), dict) else {}
        if bool(policy.get("manual_approval_only")):
            failures.append("m30_3_policy manual_approval_only != false")
    else:
        red_total = 0
        if m30_1_rc != 0 or not bool(m30_1.get("ok")):
            red_total += 1
        if m30_2_rc != 0 or not bool(m30_2.get("release_ready")):
            red_total += 1
        if m30_3_rc != 0 or str(m30_3.get("escalation_level") or "") != "normal":
            red_total += 1
        if red_total < 1:
            failures.append("inject_fail expected at least one non-green stage")

    approved = len(failures) == 0 and not inject_fail
    go_live_decision = "approve_go_live" if approved else "hold_go_live"
    out: Dict[str, Any] = {
        "ok": approved,
        "approved": approved,
        "go_live_decision": go_live_decision,
        "day": day,
        "inject_fail": inject_fail,
        "event_log_dir": str(event_log_dir),
        "quality_report_dir": str(quality_report_dir),
        "signoff_report_dir": str(signoff_report_dir),
        "policy_report_dir": str(policy_report_dir),
        "m30_1_quality_gates": {
            "rc": int(m30_1_rc),
            "ok": bool(m30_1.get("ok")) if isinstance(m30_1, dict) else False,
            "report_json_path": str(m30_1.get("report_json_path") or "") if isinstance(m30_1, dict) else "",
            "report_md_path": str(m30_1.get("report_md_path") or "") if isinstance(m30_1, dict) else "",
        },
        "m30_2_signoff": {
            "rc": int(m30_2_rc),
            "ok": bool(m30_2.get("ok")) if isinstance(m30_2, dict) else False,
            "release_ready": bool(m30_2.get("release_ready")) if isinstance(m30_2, dict) else False,
            "report_json_path": str(m30_2.get("report_json_path") or "") if isinstance(m30_2, dict) else "",
            "report_md_path": str(m30_2.get("report_md_path") or "") if isinstance(m30_2, dict) else "",
        },
        "m30_3_policy": {
            "rc": int(m30_3_rc),
            "ok": bool(m30_3.get("ok")) if isinstance(m30_3, dict) else False,
            "escalation_level": str(m30_3.get("escalation_level") or "") if isinstance(m30_3, dict) else "",
            "policy": m30_3.get("policy") if isinstance(m30_3.get("policy"), dict) else {},
            "report_json_path": str(m30_3.get("report_json_path") or "") if isinstance(m30_3, dict) else "",
            "report_md_path": str(m30_3.get("report_md_path") or "") if isinstance(m30_3, dict) else "",
        },
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m30_final_golive_signoff_{day}.json"
    md_path = report_dir / f"m30_final_golive_signoff_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"approved={approved} day={day} go_live_decision={go_live_decision} "
            f"m30_1_ok={out['m30_1_quality_gates']['ok']} "
            f"m30_2_ready={out['m30_2_signoff']['release_ready']} "
            f"m30_3_escalation={out['m30_3_policy']['escalation_level']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if approved else 3


if __name__ == "__main__":
    raise SystemExit(main())
