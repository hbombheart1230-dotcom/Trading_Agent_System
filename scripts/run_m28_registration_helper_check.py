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

from scripts.generate_m28_registration_helpers import main as helper_main


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


def _contains(path: Path, token: str) -> bool:
    if not path.exists():
        return False
    try:
        return token in path.read_text(encoding="utf-8")
    except Exception:
        return False


def _item(
    *,
    item_id: str,
    title: str,
    passed: bool,
    evidence: str,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "required": bool(required),
        "passed": bool(passed),
        "evidence": str(evidence),
    }


def _build_markdown(out: Dict[str, Any]) -> str:
    checklist = out.get("checklist") if isinstance(out.get("checklist"), list) else []
    lines = [
        f"# M28 Registration Helper Check ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- profile: **{out.get('profile')}**",
        f"- required_pass_total: **{int(out.get('required_pass_total') or 0)}**",
        f"- required_fail_total: **{int(out.get('required_fail_total') or 0)}**",
        "",
        "## Checklist",
        "",
    ]
    for item in checklist:
        mark = "x" if bool(item.get("passed")) else " "
        lines.append(f"- [{mark}] {item.get('title')} | evidence={item.get('evidence')}")
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
    p = argparse.ArgumentParser(description="M28-8 deployment registration helper check.")
    p.add_argument("--output-dir", default="deploy/m28_registration_helpers")
    p.add_argument("--template-dir", default="deploy/m28_launch_templates")
    p.add_argument("--report-dir", default="reports/m28_registration_helpers")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--service-prefix", default="trading-agent")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(str(args.output_dir).strip())
    template_dir = Path(str(args.template_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    profile = str(args.profile or "dev").strip().lower()
    service_prefix = str(args.service_prefix or "trading-agent").strip() or "trading-agent"
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    helper_argv = [
        "--output-dir",
        str(output_dir),
        "--template-dir",
        str(template_dir),
        "--profile",
        profile,
        "--service-prefix",
        service_prefix,
        "--json",
    ]
    if inject_fail:
        helper_argv.insert(-1, "--inject-fail")
    helper_rc, helper_obj = _run_json(helper_main, helper_argv)

    files = helper_obj.get("files") if isinstance(helper_obj.get("files"), dict) else {}
    ws = Path(str(files.get("windows_scheduler_register") or ""))
    ww = Path(str(files.get("windows_worker_register") or ""))
    ls = Path(str(files.get("linux_scheduler_install") or ""))
    lw = Path(str(files.get("linux_worker_install") or ""))

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="helper_generation_green",
            title="Registration helper generator runs successfully",
            passed=int(helper_rc) == 0 and bool(helper_obj),
            evidence=f"helper_rc={helper_rc}, obj_ok={bool(helper_obj)}",
        ),
        _item(
            item_id="windows_scheduler_register_ref",
            title="Windows scheduler helper references schtasks + scheduler template",
            passed=_contains(ws, "schtasks") and _contains(ws, "scheduler_task.xml"),
            evidence=f"path={ws}",
        ),
        _item(
            item_id="windows_worker_register_ref",
            title="Windows worker helper references schtasks + worker template",
            passed=_contains(ww, "schtasks") and _contains(ww, "worker_task.xml"),
            evidence=f"path={ww}",
        ),
        _item(
            item_id="linux_scheduler_register_ref",
            title="Linux scheduler helper references systemctl + scheduler service",
            passed=_contains(ls, "systemctl") and _contains(ls, "scheduler.service"),
            evidence=f"path={ls}",
        ),
        _item(
            item_id="linux_worker_register_ref",
            title="Linux worker helper references systemctl + worker service",
            passed=_contains(lw, "systemctl") and _contains(lw, "worker.service"),
            evidence=f"path={lw}",
        ),
    ]

    failures: List[str] = []
    for item in checklist:
        if bool(item.get("required")) and not bool(item.get("passed")):
            failures.append(f"check_failed:{item.get('id')}")
    if inject_fail and not failures:
        failures.append("inject_fail expected at least one failed required checklist item")

    required_total = int(sum(1 for x in checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)

    ok = required_fail_total == 0 and not inject_fail
    out: Dict[str, Any] = {
        "ok": bool(ok),
        "profile": profile,
        "inject_fail": inject_fail,
        "day": day,
        "output_dir": str(output_dir),
        "template_dir": str(template_dir),
        "report_dir": str(report_dir),
        "generator": {
            "rc": int(helper_rc),
            "ok": int(helper_rc) == 0 and bool(helper_obj),
            "files": files,
        },
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m28_registration_helpers_{day}.json"
    md_path = report_dir / f"m28_registration_helpers_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} profile={profile} "
            f"required_pass_total={required_pass_total} required_fail_total={required_fail_total} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if bool(ok) else 3


if __name__ == "__main__":
    raise SystemExit(main())
