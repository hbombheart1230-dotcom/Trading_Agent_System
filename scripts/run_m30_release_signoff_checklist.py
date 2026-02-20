from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m30_quality_gates_bundle import main as quality_bundle_main


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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _gitignore_has_env(root: Path) -> bool:
    p = root / ".gitignore"
    if not p.exists():
        return False
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip() == ".env":
                return True
    except Exception:
        return False
    return False


def _item(
    *,
    item_id: str,
    category: str,
    title: str,
    passed: bool,
    evidence: str,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "title": title,
        "required": bool(required),
        "passed": bool(passed),
        "evidence": str(evidence),
    }


def _count_by(items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for it in items:
        k = str(it.get(key) or "")
        if not k:
            continue
        out[k] = int(out.get(k) or 0) + 1
    return out


def _build_markdown(out: Dict[str, Any]) -> str:
    items = out.get("checklist") if isinstance(out.get("checklist"), list) else []
    lines = [
        f"# M30 Release Sign-off Checklist ({out.get('day')})",
        "",
        f"- release_ready: **{bool(out.get('release_ready'))}**",
        f"- quality_gates_ok: **{bool(out.get('quality_gates_ok'))}**",
        f"- required_pass_total: **{int(out.get('required_pass_total') or 0)}**",
        f"- required_fail_total: **{int(out.get('required_fail_total') or 0)}**",
        "",
        "## Checklist",
        "",
    ]
    for it in items:
        mark = "x" if bool(it.get("passed")) else " "
        lines.append(
            f"- [{mark}] ({it.get('category')}) {it.get('title')} | evidence={it.get('evidence')}"
        )
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
    p = argparse.ArgumentParser(description="M30-2 release sign-off checklist generator.")
    p.add_argument("--quality-gates-json-path", default="")
    p.add_argument("--event-log-dir", default="data/logs/m30_quality_gates")
    p.add_argument("--quality-report-dir", default="reports/m30_quality_gates")
    p.add_argument("--report-dir", default="reports/m30_signoff")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-run-quality-gates", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    quality_obj: Dict[str, Any] = {}
    quality_rc = -1

    raw_quality_path = str(args.quality_gates_json_path or "").strip()
    quality_path = Path(raw_quality_path) if raw_quality_path else None
    if quality_path is not None:
        quality_obj = _read_json(quality_path)
        quality_rc = 0 if quality_obj else 3

    if (not quality_obj) and (not bool(args.no_run_quality_gates)):
        quality_event_log_dir = Path(str(args.event_log_dir).strip())
        quality_report_dir = Path(str(args.quality_report_dir).strip())
        quality_argv = [
            "--event-log-dir",
            str(quality_event_log_dir),
            "--report-dir",
            str(quality_report_dir),
            "--day",
            day,
            "--json",
        ]
        if bool(args.inject_fail):
            quality_argv.insert(-1, "--inject-fail")
        quality_rc, quality_obj = _run_json(quality_bundle_main, quality_argv)

    gates = quality_obj.get("gates") if isinstance(quality_obj.get("gates"), dict) else {}
    functional_ok = bool(((gates.get("functional") or {}).get("ok")))
    resilience_ok = bool(((gates.get("resilience") or {}).get("ok")))
    safety_ok = bool(((gates.get("safety") or {}).get("ok")))
    ops_ok = bool(((gates.get("ops") or {}).get("ok")))
    quality_gates_ok = bool(quality_obj.get("ok")) and int(quality_rc) == 0

    quality_report_json = Path(str(quality_obj.get("report_json_path") or ""))
    quality_report_md = Path(str(quality_obj.get("report_md_path") or ""))

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="arch_gates_green",
            category="architecture",
            title="Functional and resilience gates are green",
            passed=bool(functional_ok and resilience_ok),
            evidence=f"functional={functional_ok}, resilience={resilience_ok}",
        ),
        _item(
            item_id="arch_runtime_bundle",
            category="architecture",
            title="Quality gates bundle artifact generated",
            passed=bool(quality_report_json.exists() and quality_report_md.exists()),
            evidence=f"json={quality_report_json.exists()}, md={quality_report_md.exists()}",
        ),
        _item(
            item_id="sec_env_gitignore",
            category="security",
            title=".env is excluded from git tracking",
            passed=_gitignore_has_env(ROOT),
            evidence=f".gitignore_has_.env={_gitignore_has_env(ROOT)}",
        ),
        _item(
            item_id="sec_safety_green",
            category="security",
            title="Safety gate is green (guardrails/idempotency)",
            passed=bool(safety_ok),
            evidence=f"safety={safety_ok}",
        ),
        _item(
            item_id="ops_observability_governance",
            category="operations",
            title="Ops gate is green (observability + governance)",
            passed=bool(ops_ok),
            evidence=f"ops={ops_ok}",
        ),
        _item(
            item_id="ops_bundle_green",
            category="operations",
            title="M30 quality bundle is green",
            passed=bool(quality_gates_ok),
            evidence=f"quality_rc={quality_rc}, quality_ok={bool(quality_obj.get('ok'))}",
        ),
    ]

    required_total = int(sum(1 for x in checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)

    failures: List[str] = []
    if required_fail_total > 0:
        for x in checklist:
            if bool(x.get("required")) and not bool(x.get("passed")):
                failures.append(f"check_failed:{x.get('id')}")

    # If caller explicitly asked to inject failure, force red-path expectation.
    if bool(args.inject_fail) and required_fail_total < 1:
        failures.append("inject_fail expected at least one failed required checklist item")

    release_ready = required_fail_total == 0 and not bool(args.inject_fail)
    by_category = _count_by(checklist, "category")
    pass_by_category: Dict[str, int] = {}
    for item in checklist:
        if bool(item.get("passed")):
            c = str(item.get("category") or "")
            pass_by_category[c] = int(pass_by_category.get(c) or 0) + 1

    out: Dict[str, Any] = {
        "ok": release_ready,
        "release_ready": release_ready,
        "day": day,
        "quality_gates_ok": bool(quality_gates_ok),
        "quality_gates_rc": int(quality_rc),
        "quality_gates_report_json_path": str(quality_report_json) if str(quality_report_json) else "",
        "quality_gates_report_md_path": str(quality_report_md) if str(quality_report_md) else "",
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "check_total_by_category": by_category,
        "check_pass_total_by_category": pass_by_category,
        "checklist": checklist,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m30_release_signoff_{day}.json"
    md_path = report_dir / f"m30_release_signoff_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"release_ready={out['release_ready']} day={day} "
            f"required_pass_total={required_pass_total} required_fail_total={required_fail_total} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if release_ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
