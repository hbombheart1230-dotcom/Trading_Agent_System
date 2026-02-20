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

from scripts.check_runtime_profile import main as check_main


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M28-1 runtime profile scaffold check.")
    p.add_argument("--work-dir", default="data/state/m28_profile_check")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _write_env(path: Path, rows: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in rows.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_check(*, profile: str, env_path: Path, strict: bool) -> Tuple[int, Dict[str, Any]]:
    argv: List[str] = ["--profile", profile, "--env-path", str(env_path), "--json"]
    if strict:
        argv.insert(-1, "--strict")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = check_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    work_dir = Path(str(args.work_dir).strip())
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear) and work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    dev_env = work_dir / "dev.env"
    staging_env = work_dir / "staging.env"
    prod_env = work_dir / "prod.env"

    _write_env(
        dev_env,
        {
            "RUNTIME_PROFILE": "dev",
            "KIWOOM_MODE": "mock",
            "DRY_RUN": "1",
            "EXECUTION_ENABLED": "false",
            "ALLOW_REAL_EXECUTION": "false",
            "EVENT_LOG_PATH": "./data/logs/dev_events.jsonl",
            "REPORT_DIR": "./reports/dev",
        },
    )
    _write_env(
        staging_env,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "DRY_RUN": "1",
            "EXECUTION_ENABLED": "false",
            "ALLOW_REAL_EXECUTION": "false",
            "EVENT_LOG_PATH": "./data/logs/staging_events.jsonl",
            "REPORT_DIR": "./reports/staging",
            "M25_NOTIFY_PROVIDER": "slack_webhook",
        },
    )
    prod_rows = {
        "RUNTIME_PROFILE": "prod",
        "KIWOOM_MODE": "real",
        "DRY_RUN": "0",
        "EXECUTION_ENABLED": "true",
        "ALLOW_REAL_EXECUTION": "true",
        "EVENT_LOG_PATH": "./data/logs/prod_events.jsonl",
        "REPORT_DIR": "./reports/prod",
        "KIWOOM_APP_KEY": "demo_key",
        "KIWOOM_APP_SECRET": "demo_secret",
        "KIWOOM_ACCOUNT_NO": "12345678",
        "M25_NOTIFY_PROVIDER": "slack_webhook",
    }
    if inject_fail:
        prod_rows.pop("KIWOOM_APP_SECRET", None)
    _write_env(prod_env, prod_rows)

    dev_rc, dev = _run_check(profile="dev", env_path=dev_env, strict=True)
    staging_rc, staging = _run_check(profile="staging", env_path=staging_env, strict=True)
    prod_rc, prod = _run_check(profile="prod", env_path=prod_env, strict=True)

    failures: List[str] = []
    checks = [("dev", dev_rc, dev), ("staging", staging_rc, staging), ("prod", prod_rc, prod)]
    for name, rc, obj in checks:
        if int(rc) != 0:
            failures.append(f"{name} rc != 0")
        if obj and not bool(obj.get("ok")):
            failures.append(f"{name} ok != true")

    out = {
        "ok": len(failures) == 0,
        "inject_fail": inject_fail,
        "work_dir": str(work_dir),
        "profiles": {
            "dev": {
                "rc": int(dev_rc),
                "ok": bool(dev.get("ok")) if isinstance(dev, dict) else False,
                "violation_total": len(dev.get("violations") or []) if isinstance(dev, dict) else 0,
            },
            "staging": {
                "rc": int(staging_rc),
                "ok": bool(staging.get("ok")) if isinstance(staging, dict) else False,
                "violation_total": len(staging.get("violations") or []) if isinstance(staging, dict) else 0,
            },
            "prod": {
                "rc": int(prod_rc),
                "ok": bool(prod.get("ok")) if isinstance(prod, dict) else False,
                "violation_total": len(prod.get("violations") or []) if isinstance(prod, dict) else 0,
                "required_missing": prod.get("required_missing") if isinstance(prod, dict) else [],
            },
        },
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} inject_fail={inject_fail} "
            f"dev_rc={out['profiles']['dev']['rc']} staging_rc={out['profiles']['staging']['rc']} "
            f"prod_rc={out['profiles']['prod']['rc']} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
