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

from scripts.run_m28_startup_preflight_check import main as preflight_main


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
        f"# M28 Scheduler/Worker Launch Wrapper Check ({out.get('day')})",
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

    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    lines += ["", "## Failures", ""]
    if failures:
        for msg in failures:
            lines.append(f"- {msg}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M28-5 scheduler/worker launch wrapper preflight check.")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--state-dir", default="data/state/m28_scheduler_worker")
    p.add_argument("--report-dir", default="reports/m28_scheduler_worker")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    profile = str(args.profile or "dev").strip().lower()
    env_path = Path(str(args.env_path).strip())
    state_dir = Path(str(args.state_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if state_dir.exists():
            shutil.rmtree(state_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    roles = ("scheduler", "worker")
    role_results: Dict[str, Dict[str, Any]] = {}
    checklist: List[Dict[str, Any]] = []
    failures: List[str] = []

    for role in roles:
        role_state_path = state_dir / f"{role}_runtime_state.json"
        role_report_dir = report_dir / role
        run_argv = [
            "--profile",
            profile,
            "--env-path",
            str(env_path),
            "--state-path",
            str(role_state_path),
            "--report-dir",
            str(role_report_dir),
            "--day",
            day,
            "--run-id",
            f"m28-5-{role}",
            "--json",
        ]
        if inject_fail and role == "worker":
            run_argv.insert(-1, "--inject-fail")

        rc, obj = _run_json(preflight_main, run_argv)
        role_ok = int(rc) == 0 and bool(obj.get("ok"))
        runtime_smoke = obj.get("runtime_smoke") if isinstance(obj.get("runtime_smoke"), dict) else {}
        smoke_path = str(runtime_smoke.get("path") or "")
        smoke_ok = bool(runtime_smoke.get("ok")) and smoke_path in {"graph_spine", "decision_packet"}

        role_results[role] = {
            "rc": int(rc),
            "ok": bool(role_ok),
            "state_path": str(role_state_path),
            "report_dir": str(role_report_dir),
            "required_fail_total": int(obj.get("required_fail_total") or 0),
            "runtime_smoke_ok": bool(runtime_smoke.get("ok")),
            "runtime_path": smoke_path,
            "failures": obj.get("failures") if isinstance(obj.get("failures"), list) else [],
        }

        checklist.append(
            _item(
                item_id=f"{role}_preflight_green",
                title=f"{role} preflight gate passes",
                passed=bool(role_ok),
                evidence=f"rc={int(rc)}, ok={bool(obj.get('ok'))}",
            )
        )
        checklist.append(
            _item(
                item_id=f"{role}_runtime_smoke_green",
                title=f"{role} runtime smoke boot path is valid",
                passed=bool(smoke_ok),
                evidence=f"runtime_smoke_ok={bool(runtime_smoke.get('ok'))}, path={smoke_path or '(none)'}",
            )
        )

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
        "env_path": str(env_path),
        "state_dir": str(state_dir),
        "report_dir": str(report_dir),
        "roles": role_results,
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m28_scheduler_worker_launch_{day}.json"
    md_path = report_dir / f"m28_scheduler_worker_launch_{day}.md"
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
