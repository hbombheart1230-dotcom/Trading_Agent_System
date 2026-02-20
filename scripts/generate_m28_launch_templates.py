from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate M28 deploy-target launch templates.")
    p.add_argument("--output-dir", default="deploy/m28_launch_templates")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--python-exec", default=sys.executable)
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _scheduler_wrapper_args(*, profile: str, env_path: str) -> str:
    return (
        "scripts/launch_with_preflight.py "
        f"--role scheduler --profile {profile} --env-path {env_path} "
        "-- python scripts/run_commander_runtime_once.py --live --json"
    )


def _worker_wrapper_args(*, profile: str, env_path: str, inject_fail: bool) -> str:
    if inject_fail:
        return "scripts/run_commander_runtime_once.py --mode decision_packet --live --json"
    return (
        "scripts/launch_with_preflight.py "
        f"--role worker --profile {profile} --env-path {env_path} "
        "-- python scripts/run_commander_runtime_once.py --mode decision_packet --live --json"
    )


def _windows_task_xml(
    *,
    description: str,
    command: str,
    arguments: str,
    working_dir: str,
) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        f"    <Description>{description}</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        "    <Principal id=\"Author\">\n"
        "      <RunLevel>HighestAvailable</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <Enabled>true</Enabled>\n"
        "  </Settings>\n"
        "  <Actions Context=\"Author\">\n"
        "    <Exec>\n"
        f"      <Command>{command}</Command>\n"
        f"      <Arguments>{arguments}</Arguments>\n"
        f"      <WorkingDirectory>{working_dir}</WorkingDirectory>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def _linux_service(
    *,
    description: str,
    command: str,
    arguments: str,
    working_dir: str,
) -> str:
    return (
        "[Unit]\n"
        f"Description={description}\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={working_dir}\n"
        f"ExecStart={command} {arguments}\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(str(args.output_dir).strip())
    profile = str(args.profile or "dev").strip().lower()
    env_path = str(args.env_path or ".env").strip()
    python_exec = str(args.python_exec or sys.executable).strip() or sys.executable
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear) and output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
    win_dir = output_dir / "windows"
    linux_dir = output_dir / "linux"
    win_dir.mkdir(parents=True, exist_ok=True)
    linux_dir.mkdir(parents=True, exist_ok=True)

    work_dir = str(ROOT)
    scheduler_args = _scheduler_wrapper_args(profile=profile, env_path=env_path)
    worker_args = _worker_wrapper_args(profile=profile, env_path=env_path, inject_fail=inject_fail)

    files: Dict[str, str] = {
        "windows_scheduler_task": str(win_dir / "scheduler_task.xml"),
        "windows_worker_task": str(win_dir / "worker_task.xml"),
        "linux_scheduler_service": str(linux_dir / "scheduler.service"),
        "linux_worker_service": str(linux_dir / "worker.service"),
    }

    Path(files["windows_scheduler_task"]).write_text(
        _windows_task_xml(
            description="M28 scheduler launch (preflight wrapped)",
            command=python_exec,
            arguments=scheduler_args,
            working_dir=work_dir,
        ),
        encoding="utf-8",
    )
    Path(files["windows_worker_task"]).write_text(
        _windows_task_xml(
            description="M28 worker launch (preflight wrapped)",
            command=python_exec,
            arguments=worker_args,
            working_dir=work_dir,
        ),
        encoding="utf-8",
    )
    Path(files["linux_scheduler_service"]).write_text(
        _linux_service(
            description="M28 scheduler launch (preflight wrapped)",
            command=python_exec,
            arguments=scheduler_args,
            working_dir=work_dir,
        ),
        encoding="utf-8",
    )
    Path(files["linux_worker_service"]).write_text(
        _linux_service(
            description="M28 worker launch (preflight wrapped)",
            command=python_exec,
            arguments=worker_args,
            working_dir=work_dir,
        ),
        encoding="utf-8",
    )

    out = {
        "ok": True,
        "inject_fail": inject_fail,
        "output_dir": str(output_dir),
        "profile": profile,
        "env_path": env_path,
        "python_exec": python_exec,
        "files": files,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} profile={profile} inject_fail={inject_fail} "
            f"template_total={len(files)} output_dir={output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
