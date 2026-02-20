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

from libs.runtime.runtime_lifecycle import shutdown_hook
from libs.runtime.runtime_lifecycle import startup_hook
from scripts.check_runtime_profile import main as profile_check_main
from scripts.run_commander_runtime_once import main as runtime_once_main


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


def _seed_active_state(path: Path, *, now_epoch: int) -> None:
    obj = {
        "run_id": "runtime-inject-active",
        "status": "running",
        "pid": 99999,
        "started_epoch": int(now_epoch),
        "started_ts": "2026-02-21T00:00:00+00:00",
        "ended_epoch": 0,
        "ended_ts": "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


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
        f"# M28 Startup Preflight Check ({out.get('day')})",
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
    p = argparse.ArgumentParser(description="M28-4 startup preflight gate check.")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--state-path", default="data/state/m28_startup_preflight/runtime_state.json")
    p.add_argument("--report-dir", default="reports/m28_startup_preflight")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--run-id", default="m28-startup-preflight")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    profile = str(args.profile or "dev").strip().lower()
    env_path = Path(str(args.env_path).strip())
    state_path = Path(str(args.state_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    run_id = str(args.run_id or "m28-startup-preflight").strip() or "m28-startup-preflight"
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if state_path.exists():
            state_path.unlink(missing_ok=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    now_epoch = 1000
    if inject_fail:
        _seed_active_state(state_path, now_epoch=now_epoch)

    profile_rc, profile_obj = _run_json(
        profile_check_main,
        [
            "--profile",
            profile,
            "--env-path",
            str(env_path),
            "--strict",
            "--json",
        ],
    )
    profile_ok = int(profile_rc) == 0 and bool(profile_obj.get("ok"))

    startup = startup_hook(
        state_path=str(state_path),
        lock_stale_sec=600,
        now_epoch=now_epoch + 1,
    )
    startup_ok = bool(startup.get("ok"))

    runtime_rc = -1
    runtime_obj: Dict[str, Any] = {}
    runtime_ok = False
    if profile_ok and startup_ok:
        runtime_rc, runtime_obj = _run_json(
            runtime_once_main,
            [
                "--run-id",
                run_id,
                "--json",
            ],
        )
        runtime_ok = int(runtime_rc) == 0 and bool(runtime_obj)
    else:
        runtime_obj = {"reason": "startup_or_profile_failed"}

    shutdown: Dict[str, Any]
    if startup_ok:
        shutdown = shutdown_hook(
            state_path=str(state_path),
            run_id=str(startup.get("run_id") or ""),
            now_epoch=now_epoch + 2,
        )
    else:
        shutdown = {
            "ok": False,
            "reason": "startup_failed_skip",
            "state_path": str(state_path),
            "run_id": "",
            "status": "",
        }
    shutdown_ok = bool(shutdown.get("ok"))

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="runtime_profile_gate",
            title="Runtime profile strict validation passes",
            passed=profile_ok,
            evidence=f"profile_rc={profile_rc}, profile_ok={bool(profile_obj.get('ok'))}",
        ),
        _item(
            item_id="startup_lock_gate",
            title="Lifecycle startup hook acquires runtime lock",
            passed=startup_ok,
            evidence=f"startup_ok={startup_ok}, reason={startup.get('reason')}",
        ),
        _item(
            item_id="runtime_boot_smoke_gate",
            title="Commander runtime once smoke boot succeeds",
            passed=runtime_ok,
            evidence=f"runtime_rc={runtime_rc}, runtime_status={runtime_obj.get('runtime_status')}",
        ),
        _item(
            item_id="shutdown_gate",
            title="Lifecycle shutdown hook releases runtime lock",
            passed=shutdown_ok,
            evidence=f"shutdown_ok={shutdown_ok}, reason={shutdown.get('reason')}",
        ),
    ]

    required_total = int(sum(1 for x in checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)

    failures: List[str] = []
    for item in checklist:
        if bool(item.get("required")) and not bool(item.get("passed")):
            failures.append(f"check_failed:{item.get('id')}")
    if inject_fail and required_fail_total < 1:
        failures.append("inject_fail expected at least one failed required checklist item")

    ok = required_fail_total == 0 and not inject_fail
    out: Dict[str, Any] = {
        "ok": bool(ok),
        "profile": profile,
        "inject_fail": inject_fail,
        "day": day,
        "env_path": str(env_path),
        "state_path": str(state_path),
        "report_dir": str(report_dir),
        "profile_check": {
            "rc": int(profile_rc),
            "ok": bool(profile_obj.get("ok")) if isinstance(profile_obj, dict) else False,
            "required_missing": profile_obj.get("required_missing") if isinstance(profile_obj, dict) else [],
            "violation_total": len(profile_obj.get("violations") or []) if isinstance(profile_obj, dict) else 0,
        },
        "startup": startup,
        "runtime_smoke": {
            "rc": int(runtime_rc),
            "ok": bool(runtime_ok),
            "runtime_status": runtime_obj.get("runtime_status"),
            "path": runtime_obj.get("path"),
        },
        "shutdown": shutdown,
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m28_startup_preflight_{day}.json"
    md_path = report_dir / f"m28_startup_preflight_{day}.md"
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
