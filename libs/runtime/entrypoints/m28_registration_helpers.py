from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate M28 deployment registration helper templates.")
    p.add_argument("--output-dir", default="deploy/m28_registration_helpers")
    p.add_argument("--template-dir", default="deploy/m28_launch_templates")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--service-prefix", default="trading-agent")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _windows_ps1(*, role: str, template_xml_path: str, profile: str) -> str:
    task_name_default = f"TradingAgent-{role.capitalize()}-{profile}"
    return (
        "param(\n"
        f"  [string]$TaskName = \"{task_name_default}\",\n"
        f"  [string]$TaskXmlPath = \"{template_xml_path}\"\n"
        ")\n\n"
        "if (!(Test-Path $TaskXmlPath)) {\n"
        "  Write-Error \"missing_task_xml path=$TaskXmlPath\"\n"
        "  exit 3\n"
        "}\n\n"
        "schtasks /Create /TN $TaskName /XML $TaskXmlPath /F\n"
        "if ($LASTEXITCODE -ne 0) {\n"
        "  exit $LASTEXITCODE\n"
        "}\n\n"
        f"Write-Output \"ok role={role} profile={profile} task=$TaskName\"\n"
    )


def _linux_sh(*, role: str, template_service_path: str, service_prefix: str, profile: str) -> str:
    default_name = f"{service_prefix}-{role}-{profile}"
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        f'SERVICE_NAME="${{1:-{default_name}}}"\n'
        f'SERVICE_SRC="{template_service_path}"\n'
        'SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"\n\n'
        'if [ ! -f "$SERVICE_SRC" ]; then\n'
        '  echo "missing_service_template path=$SERVICE_SRC" >&2\n'
        "  exit 3\n"
        "fi\n\n"
        'sudo cp "$SERVICE_SRC" "$SERVICE_DST"\n'
        "sudo systemctl daemon-reload\n"
        'sudo systemctl enable "${SERVICE_NAME}.service"\n'
        'sudo systemctl restart "${SERVICE_NAME}.service"\n\n'
        f'echo "ok role={role} profile={profile} service=${{SERVICE_NAME}}"\n'
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(str(args.output_dir).strip())
    template_dir = Path(str(args.template_dir).strip())
    profile = str(args.profile or "dev").strip().lower()
    service_prefix = str(args.service_prefix or "trading-agent").strip() or "trading-agent"
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear) and output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
    win_dir = output_dir / "windows"
    linux_dir = output_dir / "linux"
    win_dir.mkdir(parents=True, exist_ok=True)
    linux_dir.mkdir(parents=True, exist_ok=True)

    scheduler_xml = str(template_dir / "windows" / "scheduler_task.xml")
    worker_xml = (
        str(template_dir / "windows" / "worker_task_broken.xml")
        if inject_fail
        else str(template_dir / "windows" / "worker_task.xml")
    )
    scheduler_service = str(template_dir / "linux" / "scheduler.service")
    worker_service = (
        str(template_dir / "linux" / "worker_broken.service")
        if inject_fail
        else str(template_dir / "linux" / "worker.service")
    )

    files: Dict[str, str] = {
        "windows_scheduler_register": str(win_dir / "register_scheduler_task.ps1"),
        "windows_worker_register": str(win_dir / "register_worker_task.ps1"),
        "linux_scheduler_install": str(linux_dir / "install_scheduler_service.sh"),
        "linux_worker_install": str(linux_dir / "install_worker_service.sh"),
    }

    Path(files["windows_scheduler_register"]).write_text(
        _windows_ps1(role="scheduler", template_xml_path=scheduler_xml, profile=profile),
        encoding="utf-8",
    )
    Path(files["windows_worker_register"]).write_text(
        _windows_ps1(role="worker", template_xml_path=worker_xml, profile=profile),
        encoding="utf-8",
    )
    Path(files["linux_scheduler_install"]).write_text(
        _linux_sh(
            role="scheduler",
            template_service_path=scheduler_service,
            service_prefix=service_prefix,
            profile=profile,
        ),
        encoding="utf-8",
    )
    Path(files["linux_worker_install"]).write_text(
        _linux_sh(
            role="worker",
            template_service_path=worker_service,
            service_prefix=service_prefix,
            profile=profile,
        ),
        encoding="utf-8",
    )

    out = {
        "ok": True,
        "inject_fail": inject_fail,
        "output_dir": str(output_dir),
        "template_dir": str(template_dir),
        "profile": profile,
        "service_prefix": service_prefix,
        "files": files,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} profile={profile} inject_fail={inject_fail} "
            f"helper_total={len(files)} output_dir={output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
