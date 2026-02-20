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

from scripts.run_m28_runtime_lifecycle_hooks_check import main as lifecycle_main
from scripts.run_m28_runtime_profile_scaffold_check import main as profile_main


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


def _build_md(out: Dict[str, Any]) -> str:
    checklist = out.get("rollout_checklist") if isinstance(out.get("rollout_checklist"), list) else []
    rollback_steps = out.get("rollback_procedure") if isinstance(out.get("rollback_procedure"), list) else []
    lines = [
        "# M28 Rollout and Rollback Check",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- go_no_go: **{out.get('go_no_go')}**",
        f"- required_pass_total: **{int(out.get('required_pass_total') or 0)}**",
        f"- required_fail_total: **{int(out.get('required_fail_total') or 0)}**",
        "",
        "## Rollout Checklist",
        "",
    ]
    for item in checklist:
        mark = "x" if bool(item.get("passed")) else " "
        lines.append(f"- [{mark}] {item.get('title')} | evidence={item.get('evidence')}")
    lines += ["", "## Rollback Procedure", ""]
    if rollback_steps:
        for idx, step in enumerate(rollback_steps, start=1):
            lines.append(f"{idx}. {step}")
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
    p = argparse.ArgumentParser(description="M28-3 rollout checklist + rollback procedure check.")
    p.add_argument("--work-dir", default="data/state/m28_rollout_check")
    p.add_argument("--report-dir", default="reports/m28_rollout")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    work_dir = Path(str(args.work_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    profile_work = work_dir / "profile"
    lifecycle_state = work_dir / "lifecycle" / "runtime_state.json"

    profile_argv = ["--work-dir", str(profile_work), "--json"]
    lifecycle_argv = ["--state-path", str(lifecycle_state), "--json"]
    if inject_fail:
        profile_argv.insert(-1, "--inject-fail")
        lifecycle_argv.insert(-1, "--inject-fail")

    profile_rc, profile_obj = _run_json(profile_main, profile_argv)
    lifecycle_rc, lifecycle_obj = _run_json(lifecycle_main, lifecycle_argv)

    profile_ok = int(profile_rc) == 0 and bool(profile_obj.get("ok"))
    lifecycle_ok = int(lifecycle_rc) == 0 and bool(lifecycle_obj.get("ok"))

    dev_ok = bool(((profile_obj.get("profiles") or {}).get("dev") or {}).get("ok"))
    staging_ok = bool(((profile_obj.get("profiles") or {}).get("staging") or {}).get("ok"))
    prod_ok = bool(((profile_obj.get("profiles") or {}).get("prod") or {}).get("ok"))
    shutdown_ok = bool(((lifecycle_obj.get("shutdown") or {}).get("ok")))

    rollout_checklist: List[Dict[str, Any]] = [
        _item(
            item_id="runtime_profile_green",
            title="Runtime profile validation gate is green",
            passed=profile_ok,
            evidence=f"profile_rc={profile_rc}, profile_ok={bool(profile_obj.get('ok'))}",
        ),
        _item(
            item_id="lifecycle_hooks_green",
            title="Startup/shutdown lifecycle gate is green",
            passed=lifecycle_ok,
            evidence=f"lifecycle_rc={lifecycle_rc}, lifecycle_ok={bool(lifecycle_obj.get('ok'))}",
        ),
        _item(
            item_id="nonprod_guards_ready",
            title="Dev/staging runtime guardrails are active",
            passed=bool(dev_ok and staging_ok),
            evidence=f"dev_ok={dev_ok}, staging_ok={staging_ok}",
        ),
        _item(
            item_id="prod_profile_ready",
            title="Prod runtime profile contract is validated",
            passed=bool(prod_ok),
            evidence=f"prod_ok={prod_ok}",
        ),
        _item(
            item_id="rollback_shutdown_ready",
            title="Rollback shutdown entrypoint is operable",
            passed=bool(shutdown_ok),
            evidence=f"shutdown_ok={shutdown_ok}",
        ),
    ]

    rollback_procedure: List[str] = [
        "Trigger shutdown hook for active runtime and verify state status becomes 'stopped'.",
        "Switch runtime profile to staging-safe mode (EXECUTION_ENABLED=false, ALLOW_REAL_EXECUTION=false).",
        "Restore last known-good runtime artifacts/config from previous deployment snapshot.",
        "Run runtime profile check and lifecycle hooks check before re-enabling scheduler.",
        "Resume scheduler in controlled dry-run path and observe first cycle metrics before normal mode.",
    ]

    required_total = int(sum(1 for x in rollout_checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in rollout_checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)

    failures: List[str] = []
    for item in rollout_checklist:
        if bool(item.get("required")) and not bool(item.get("passed")):
            failures.append(f"check_failed:{item.get('id')}")

    # red-path assertion in inject mode
    if inject_fail and required_fail_total < 1:
        failures.append("inject_fail expected at least one failed required checklist item")

    go_no_go = "go" if (required_fail_total == 0 and not inject_fail) else "hold"
    rollback_ready = bool(shutdown_ok and len(rollback_procedure) >= 3)
    ok = go_no_go == "go"

    out: Dict[str, Any] = {
        "ok": bool(ok),
        "go_no_go": go_no_go,
        "inject_fail": inject_fail,
        "day": day,
        "work_dir": str(work_dir),
        "report_dir": str(report_dir),
        "profile_check": {
            "rc": int(profile_rc),
            "ok": bool(profile_obj.get("ok")) if isinstance(profile_obj, dict) else False,
        },
        "lifecycle_check": {
            "rc": int(lifecycle_rc),
            "ok": bool(lifecycle_obj.get("ok")) if isinstance(lifecycle_obj, dict) else False,
        },
        "rollout_checklist": rollout_checklist,
        "rollback_ready": rollback_ready,
        "rollback_procedure": rollback_procedure,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m28_rollout_check_{day}.json"
    md_path = report_dir / f"m28_rollout_check_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_md(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} go_no_go={go_no_go} "
            f"required_pass_total={required_pass_total} required_fail_total={required_fail_total} "
            f"rollback_ready={rollback_ready}"
        )
        for msg in failures:
            print(msg)

    return 0 if bool(ok) else 3


if __name__ == "__main__":
    raise SystemExit(main())
