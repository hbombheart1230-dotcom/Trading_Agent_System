from __future__ import annotations

import argparse
import io
import json
import subprocess
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


def _tail(value: str, limit: int = 300) -> str:
    s = str(value or "")
    if len(s) <= limit:
        return s
    return s[-limit:]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Launch wrapper that enforces M28 startup preflight before running a command."
    )
    p.add_argument("--role", choices=["scheduler", "worker"], default="scheduler")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--state-path", default="")
    p.add_argument("--report-dir", default="")
    p.add_argument("--run-id", default="")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("command", nargs=argparse.REMAINDER)
    return p


def _normalize_command(command: List[str]) -> List[str]:
    parts = list(command)
    if parts and parts[0] == "--":
        parts = parts[1:]
    return [str(x) for x in parts if str(x).strip()]


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    role = str(args.role or "scheduler").strip().lower()
    profile = str(args.profile or "dev").strip().lower()
    env_path = Path(str(args.env_path).strip())
    state_path = str(args.state_path or "").strip() or f"data/state/m28_launch_wrapper/{role}_runtime_state.json"
    report_dir = str(args.report_dir or "").strip() or f"reports/m28_launch_wrapper/{role}"
    run_id = str(args.run_id or "").strip() or f"m28-launch-{role}"
    command = _normalize_command(args.command or [])

    preflight_argv = [
        "--profile",
        profile,
        "--env-path",
        str(env_path),
        "--state-path",
        str(state_path),
        "--report-dir",
        str(report_dir),
        "--run-id",
        run_id,
        "--json",
    ]
    if bool(args.inject_fail):
        preflight_argv.insert(-1, "--inject-fail")

    preflight_rc, preflight_obj = _run_json(preflight_main, preflight_argv)
    preflight_ok = int(preflight_rc) == 0 and bool(preflight_obj.get("ok"))

    out: Dict[str, Any] = {
        "ok": False,
        "role": role,
        "profile": profile,
        "env_path": str(env_path),
        "state_path": str(state_path),
        "report_dir": str(report_dir),
        "run_id": run_id,
        "inject_fail": bool(args.inject_fail),
        "preflight": {
            "rc": int(preflight_rc),
            "ok": bool(preflight_obj.get("ok")) if isinstance(preflight_obj, dict) else False,
            "required_fail_total": int(preflight_obj.get("required_fail_total") or 0)
            if isinstance(preflight_obj, dict)
            else 0,
        },
        "launch": {
            "attempted": False,
            "command": command,
            "rc": None,
            "stdout_tail": "",
            "stderr_tail": "",
        },
    }

    if not preflight_ok:
        out["reason"] = "preflight_failed"
        if bool(args.json):
            print(json.dumps(out, ensure_ascii=False))
        else:
            print(
                f"ok={out['ok']} role={role} reason={out['reason']} "
                f"preflight_rc={out['preflight']['rc']}"
            )
        return 3

    if not command:
        out["ok"] = True
        out["reason"] = "preflight_only"
        if bool(args.json):
            print(json.dumps(out, ensure_ascii=False))
        else:
            print(f"ok={out['ok']} role={role} reason={out['reason']}")
        return 0

    cp = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out["launch"] = {
        "attempted": True,
        "command": command,
        "rc": int(cp.returncode),
        "stdout_tail": _tail(cp.stdout),
        "stderr_tail": _tail(cp.stderr),
    }
    out["ok"] = int(cp.returncode) == 0
    out["reason"] = "launched" if out["ok"] else "command_failed"

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} role={role} reason={out['reason']} "
            f"command_rc={out['launch']['rc']}"
        )
    return 0 if bool(out["ok"]) else int(cp.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
