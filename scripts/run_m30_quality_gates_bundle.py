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

from scripts.run_m23_closeout_check import main as m23_main
from scripts.run_m24_closeout_check import main as m24_main
from scripts.run_m25_closeout_check import main as m25_main
from scripts.run_m26_closeout_check import main as m26_main
from scripts.run_m27_closeout_check import main as m27_main
from scripts.run_m29_closeout_check import main as m29_main


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


def _build_md(out: Dict[str, Any]) -> str:
    gates = out.get("gates") if isinstance(out.get("gates"), dict) else {}
    lines = [
        f"# M30 Quality Gates Bundle ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- failure_total: **{int(out.get('failure_total') or 0)}**",
        f"- report_json_path: `{out.get('report_json_path')}`",
        "",
        "## Gate Status",
        "",
    ]
    for name in ("functional", "resilience", "safety", "ops"):
        g = gates.get(name) if isinstance(gates.get(name), dict) else {}
        lines.append(
            f"- {name}: ok={bool(g.get('ok'))} pass_total={int(g.get('pass_total') or 0)} fail_total={int(g.get('fail_total') or 0)}"
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


def _component_summary(rc: int, obj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rc": int(rc),
        "ok": bool(obj.get("ok")) if isinstance(obj, dict) else False,
        "failure_total": int(len(obj.get("failures") or [])) if isinstance(obj, dict) else 0,
    }


def _gate_status(components: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    pass_total = 0
    fail_total = 0
    for c in components.values():
        if bool(c.get("ok")) and int(c.get("rc") or 0) == 0:
            pass_total += 1
        else:
            fail_total += 1
    return {
        "ok": fail_total == 0,
        "pass_total": int(pass_total),
        "fail_total": int(fail_total),
        "components": components,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M30-1 quality gates bundle (functional/resilience/safety/ops).")
    p.add_argument("--event-log-dir", default="data/logs/m30_quality_gates")
    p.add_argument("--report-dir", default="reports/m30_quality_gates")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--m23-day", default="", help="Optional explicit day for m23 closeout; default uses script latest-day behavior.")
    p.add_argument("--m26-day", default="2026-02-17", help="Replay evaluation day for m26 closeout (dataset-seeded default).")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    m23_day = str(args.m23_day or "").strip()
    m26_day = str(args.m26_day or "2026-02-17").strip()
    event_log_dir = Path(str(args.event_log_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if event_log_dir.exists():
            shutil.rmtree(event_log_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)
    event_log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    m23_argv = [
        "--event-log-path",
        str(event_log_dir / "m23_events.jsonl"),
        "--report-dir",
        str(report_dir / "m23"),
        "--json",
    ]
    if m23_day:
        m23_argv[4:4] = ["--day", m23_day]
    m24_argv = [
        "--intent-log-path",
        str(event_log_dir / "m24_intents.jsonl"),
        "--state-db-path",
        str(event_log_dir / "m24_state.db"),
        "--json",
    ]
    m25_argv = [
        "--event-log-path",
        str(event_log_dir / "m25_events.jsonl"),
        "--report-dir",
        str(report_dir / "m25"),
        "--day",
        day,
        "--json",
    ]
    m26_argv = [
        "--base-dataset-root",
        str(event_log_dir / "m26_base"),
        "--candidate-dataset-root",
        str(event_log_dir / "m26_candidate"),
        "--day",
        m26_day,
        "--json",
    ]
    m27_argv = [
        "--event-log-dir",
        str(event_log_dir / "m27"),
        "--report-dir",
        str(report_dir / "m27"),
        "--day",
        day,
        "--json",
    ]
    m29_argv = [
        "--event-log-dir",
        str(event_log_dir / "m29"),
        "--report-dir",
        str(report_dir / "m29"),
        "--day",
        day,
        "--json",
    ]

    if inject_fail:
        # Induce failures across multiple groups for red-path validation.
        m23_argv.insert(-1, "--skip-error-case")
        m24_argv.insert(-1, "--inject-stuck-case")
        m25_argv.insert(-1, "--inject-critical-case")
        m26_argv.insert(-1, "--inject-gate-fail")
        m27_argv.insert(-1, "--inject-fail")
        m29_argv.insert(-1, "--inject-fail")

    m23_rc, m23 = _run_json(m23_main, m23_argv)
    m24_rc, m24 = _run_json(m24_main, m24_argv)
    m25_rc, m25 = _run_json(m25_main, m25_argv)
    m26_rc, m26 = _run_json(m26_main, m26_argv)
    m27_rc, m27 = _run_json(m27_main, m27_argv)
    m29_rc, m29 = _run_json(m29_main, m29_argv)

    functional = _gate_status({"m26_closeout": _component_summary(m26_rc, m26)})
    resilience = _gate_status({"m23_closeout": _component_summary(m23_rc, m23)})
    safety = _gate_status(
        {
            "m24_closeout": _component_summary(m24_rc, m24),
            "m27_closeout": _component_summary(m27_rc, m27),
        }
    )
    ops = _gate_status(
        {
            "m25_closeout": _component_summary(m25_rc, m25),
            "m29_closeout": _component_summary(m29_rc, m29),
        }
    )

    gates = {
        "functional": functional,
        "resilience": resilience,
        "safety": safety,
        "ops": ops,
    }

    failures: List[str] = []
    if not inject_fail:
        for gate_name, gate in gates.items():
            if not bool(gate.get("ok")):
                failures.append(f"gate.{gate_name} != green")
        if int(((m29.get("m29_8_disaster_recovery") or {}).get("rc") or 0) != 0):
            failures.append("m29 DR drill rc != 0")
    else:
        red_total = sum(1 for g in gates.values() if not bool(g.get("ok")))
        if red_total < 1:
            failures.append("inject_fail expected at least one red gate")

    overall_ok = len(failures) == 0 and not inject_fail
    out: Dict[str, Any] = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "event_log_dir": str(event_log_dir),
        "report_dir": str(report_dir),
        "gates": gates,
        "inputs": {
            "m23_rc": int(m23_rc),
            "m24_rc": int(m24_rc),
            "m25_rc": int(m25_rc),
            "m26_rc": int(m26_rc),
            "m27_rc": int(m27_rc),
            "m29_rc": int(m29_rc),
        },
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m30_quality_gates_{day}.json"
    md_path = report_dir / f"m30_quality_gates_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_md(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} "
            f"functional={gates['functional']['ok']} resilience={gates['resilience']['ok']} "
            f"safety={gates['safety']['ok']} ops={gates['ops']['ok']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
