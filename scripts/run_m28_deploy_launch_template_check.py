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

from scripts.generate_m28_launch_templates import main as template_main


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
        f"# M28 Deploy Launch Template Check ({out.get('day')})",
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
    p = argparse.ArgumentParser(description="M28-7 deploy-target launch template check.")
    p.add_argument("--output-dir", default="deploy/m28_launch_templates")
    p.add_argument("--report-dir", default="reports/m28_launch_templates")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--profile", choices=["dev", "staging", "prod"], default="dev")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(str(args.output_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    profile = str(args.profile or "dev").strip().lower()
    env_path = str(args.env_path or ".env").strip()
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    gen_argv = [
        "--output-dir",
        str(output_dir),
        "--profile",
        profile,
        "--env-path",
        env_path,
        "--json",
    ]
    if inject_fail:
        gen_argv.insert(-1, "--inject-fail")
    gen_rc, gen_obj = _run_json(template_main, gen_argv)

    files = gen_obj.get("files") if isinstance(gen_obj.get("files"), dict) else {}
    ws = Path(str(files.get("windows_scheduler_task") or ""))
    ww = Path(str(files.get("windows_worker_task") or ""))
    ls = Path(str(files.get("linux_scheduler_service") or ""))
    lw = Path(str(files.get("linux_worker_service") or ""))

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="template_generation_green",
            title="Template generator runs successfully",
            passed=int(gen_rc) == 0 and bool(gen_obj),
            evidence=f"gen_rc={gen_rc}, obj_ok={bool(gen_obj)}",
        ),
        _item(
            item_id="windows_scheduler_wrapper_ref",
            title="Windows scheduler template calls preflight wrapper",
            passed=_contains(ws, "launch_with_preflight.py"),
            evidence=f"path={ws}",
        ),
        _item(
            item_id="windows_worker_wrapper_ref",
            title="Windows worker template calls preflight wrapper",
            passed=_contains(ww, "launch_with_preflight.py"),
            evidence=f"path={ww}",
        ),
        _item(
            item_id="linux_scheduler_wrapper_ref",
            title="Linux scheduler template calls preflight wrapper",
            passed=_contains(ls, "launch_with_preflight.py"),
            evidence=f"path={ls}",
        ),
        _item(
            item_id="linux_worker_wrapper_ref",
            title="Linux worker template calls preflight wrapper",
            passed=_contains(lw, "launch_with_preflight.py"),
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
        "report_dir": str(report_dir),
        "generator": {
            "rc": int(gen_rc),
            "ok": int(gen_rc) == 0 and bool(gen_obj),
            "files": files,
        },
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m28_launch_templates_{day}.json"
    md_path = report_dir / f"m28_launch_templates_{day}.md"
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
