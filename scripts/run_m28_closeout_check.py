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

from scripts.run_m28_deploy_launch_template_check import main as m28_7_main
from scripts.run_m28_launch_hook_integration_check import main as m28_6_main
from scripts.run_m28_registration_helper_check import main as m28_8_main
from scripts.run_m28_rollout_rollback_check import main as m28_3_main
from scripts.run_m28_runtime_lifecycle_hooks_check import main as m28_2_main
from scripts.run_m28_runtime_profile_scaffold_check import main as m28_1_main
from scripts.run_m28_scheduler_worker_launch_wrapper_check import main as m28_5_main
from scripts.run_m28_startup_preflight_check import main as m28_4_main


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


def _write_env(path: Path) -> None:
    rows = {
        "RUNTIME_PROFILE": "dev",
        "KIWOOM_MODE": "mock",
        "DRY_RUN": "1",
        "EXECUTION_ENABLED": "false",
        "ALLOW_REAL_EXECUTION": "false",
        "EVENT_LOG_PATH": "./data/logs/dev_events.jsonl",
        "REPORT_DIR": "./reports/dev",
        "M25_NOTIFY_PROVIDER": "none",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([f"{k}={v}" for k, v in rows.items()]) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M28 closeout check (runtime platformization readiness).")
    p.add_argument("--work-dir", default="data/state/m28_closeout")
    p.add_argument("--report-dir", default="reports/m28_closeout")
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

    env_path = work_dir / "m28_closeout_dev.env"
    _write_env(env_path)

    m28_1_rc, m28_1 = _run_json(
        m28_1_main,
        [
            "--work-dir",
            str(work_dir / "m28_1_profile"),
            "--json",
        ],
    )
    m28_2_rc, m28_2 = _run_json(
        m28_2_main,
        [
            "--state-path",
            str(work_dir / "m28_2_lifecycle" / "runtime_state.json"),
            "--json",
        ],
    )
    m28_3_rc, m28_3 = _run_json(
        m28_3_main,
        [
            "--work-dir",
            str(work_dir / "m28_3_rollout_state"),
            "--report-dir",
            str(report_dir / "m28_3_rollout"),
            "--day",
            day,
            "--json",
        ],
    )
    m28_4_rc, m28_4 = _run_json(
        m28_4_main,
        [
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--state-path",
            str(work_dir / "m28_4_preflight" / "runtime_state.json"),
            "--report-dir",
            str(report_dir / "m28_4_preflight"),
            "--day",
            day,
            "--json",
        ],
    )
    m28_5_rc, m28_5 = _run_json(
        m28_5_main,
        [
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--state-dir",
            str(work_dir / "m28_5_scheduler_worker"),
            "--report-dir",
            str(report_dir / "m28_5_scheduler_worker"),
            "--day",
            day,
            "--json",
        ],
    )
    m28_6_rc, m28_6 = _run_json(
        m28_6_main,
        [
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--state-dir",
            str(work_dir / "m28_6_launch_hook"),
            "--report-dir",
            str(report_dir / "m28_6_launch_hook"),
            "--day",
            day,
            "--json",
        ],
    )
    m28_7_templates_dir = work_dir / "m28_7_launch_templates"
    m28_7_rc, m28_7 = _run_json(
        m28_7_main,
        [
            "--output-dir",
            str(m28_7_templates_dir),
            "--report-dir",
            str(report_dir / "m28_7_launch_templates"),
            "--day",
            day,
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--json",
        ],
    )
    m28_8_argv: List[str] = [
        "--output-dir",
        str(work_dir / "m28_8_registration_helpers"),
        "--template-dir",
        str(m28_7_templates_dir),
        "--report-dir",
        str(report_dir / "m28_8_registration_helpers"),
        "--day",
        day,
        "--profile",
        "dev",
        "--json",
    ]
    if inject_fail:
        m28_8_argv.insert(-1, "--inject-fail")
    m28_8_rc, m28_8 = _run_json(m28_8_main, m28_8_argv)

    failures: List[str] = []
    checks = [
        ("m28_1", m28_1_rc, m28_1),
        ("m28_2", m28_2_rc, m28_2),
        ("m28_3", m28_3_rc, m28_3),
        ("m28_4", m28_4_rc, m28_4),
        ("m28_5", m28_5_rc, m28_5),
        ("m28_6", m28_6_rc, m28_6),
        ("m28_7", m28_7_rc, m28_7),
        ("m28_8", m28_8_rc, m28_8),
    ]

    if not inject_fail:
        for name, rc, obj in checks:
            if int(rc) != 0:
                failures.append(f"{name} rc != 0")
            if obj and not bool(obj.get("ok")):
                failures.append(f"{name} ok != true")

        if not bool(((m28_1.get("profiles") or {}).get("prod") or {}).get("ok")):
            failures.append("m28_1 profiles.prod.ok != true")
        if str(((m28_2.get("startup_2") or {}).get("reason")) or "") != "active_run":
            failures.append("m28_2 startup_2.reason != active_run")
        if str(m28_3.get("go_no_go") or "") != "go":
            failures.append("m28_3 go_no_go != go")
        if not bool(m28_3.get("rollback_ready")):
            failures.append("m28_3 rollback_ready != true")
        if not bool(((m28_4.get("runtime_smoke") or {}).get("ok"))):
            failures.append("m28_4 runtime_smoke.ok != true")
        if not bool(((m28_5.get("roles") or {}).get("scheduler") or {}).get("ok")):
            failures.append("m28_5 roles.scheduler.ok != true")
        if not bool(((m28_5.get("roles") or {}).get("worker") or {}).get("ok")):
            failures.append("m28_5 roles.worker.ok != true")
        if not bool(((m28_6.get("roles") or {}).get("scheduler") or {}).get("ok")):
            failures.append("m28_6 roles.scheduler.ok != true")
        if not bool(((m28_6.get("roles") or {}).get("worker") or {}).get("ok")):
            failures.append("m28_6 roles.worker.ok != true")
        if int(m28_7.get("required_fail_total") or 0) != 0:
            failures.append("m28_7 required_fail_total != 0")
        if int(m28_8.get("required_fail_total") or 0) != 0:
            failures.append("m28_8 required_fail_total != 0")
    else:
        failing_subchecks = 0
        for _name, rc, obj in checks:
            if int(rc) != 0 or not bool(obj.get("ok")):
                failing_subchecks += 1
        if failing_subchecks < 1:
            failures.append("inject_fail expected at least one failing subcheck")
        if int(m28_8_rc) == 0 and bool(m28_8.get("ok")):
            failures.append("inject_fail expected m28_8 failure path")

    overall_ok = len(failures) == 0 and not inject_fail
    out = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "work_dir": str(work_dir),
        "report_dir": str(report_dir),
        "env_path": str(env_path),
        "m28_1_profile": {
            "rc": int(m28_1_rc),
            "ok": bool(m28_1.get("ok")) if isinstance(m28_1, dict) else False,
            "prod_ok": bool(((m28_1.get("profiles") or {}).get("prod") or {}).get("ok")) if isinstance(m28_1, dict) else False,
        },
        "m28_2_lifecycle": {
            "rc": int(m28_2_rc),
            "ok": bool(m28_2.get("ok")) if isinstance(m28_2, dict) else False,
            "startup_2_reason": str(((m28_2.get("startup_2") or {}).get("reason")) or "") if isinstance(m28_2, dict) else "",
            "shutdown_ok": bool(((m28_2.get("shutdown") or {}).get("ok"))) if isinstance(m28_2, dict) else False,
        },
        "m28_3_rollout": {
            "rc": int(m28_3_rc),
            "ok": bool(m28_3.get("ok")) if isinstance(m28_3, dict) else False,
            "go_no_go": str(m28_3.get("go_no_go") or "") if isinstance(m28_3, dict) else "",
            "rollback_ready": bool(m28_3.get("rollback_ready")) if isinstance(m28_3, dict) else False,
        },
        "m28_4_preflight": {
            "rc": int(m28_4_rc),
            "ok": bool(m28_4.get("ok")) if isinstance(m28_4, dict) else False,
            "runtime_smoke_ok": bool(((m28_4.get("runtime_smoke") or {}).get("ok"))) if isinstance(m28_4, dict) else False,
        },
        "m28_5_scheduler_worker": {
            "rc": int(m28_5_rc),
            "ok": bool(m28_5.get("ok")) if isinstance(m28_5, dict) else False,
            "scheduler_ok": bool(((m28_5.get("roles") or {}).get("scheduler") or {}).get("ok")) if isinstance(m28_5, dict) else False,
            "worker_ok": bool(((m28_5.get("roles") or {}).get("worker") or {}).get("ok")) if isinstance(m28_5, dict) else False,
        },
        "m28_6_launch_hook": {
            "rc": int(m28_6_rc),
            "ok": bool(m28_6.get("ok")) if isinstance(m28_6, dict) else False,
            "scheduler_ok": bool(((m28_6.get("roles") or {}).get("scheduler") or {}).get("ok")) if isinstance(m28_6, dict) else False,
            "worker_ok": bool(((m28_6.get("roles") or {}).get("worker") or {}).get("ok")) if isinstance(m28_6, dict) else False,
        },
        "m28_7_templates": {
            "rc": int(m28_7_rc),
            "ok": bool(m28_7.get("ok")) if isinstance(m28_7, dict) else False,
            "required_fail_total": int(m28_7.get("required_fail_total") or 0) if isinstance(m28_7, dict) else 0,
        },
        "m28_8_registration_helpers": {
            "rc": int(m28_8_rc),
            "ok": bool(m28_8.get("ok")) if isinstance(m28_8, dict) else False,
            "required_fail_total": int(m28_8.get("required_fail_total") or 0) if isinstance(m28_8, dict) else 0,
        },
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} "
            f"profile_prod_ok={out['m28_1_profile']['prod_ok']} "
            f"rollout_go_no_go={out['m28_3_rollout']['go_no_go']} "
            f"preflight_smoke_ok={out['m28_4_preflight']['runtime_smoke_ok']} "
            f"hook_worker_ok={out['m28_6_launch_hook']['worker_ok']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
