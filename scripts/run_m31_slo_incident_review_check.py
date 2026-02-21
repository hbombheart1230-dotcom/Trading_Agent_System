from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)

    s = str(ts).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> Optional[str]:
    e = _to_epoch(ts)
    if e is None:
        return None
    return datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%d")


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj

    return _gen()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


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


def _severity_from_level(level: str) -> str:
    lv = str(level or "").strip().lower()
    if lv == "incident":
        return "SEV-1"
    if lv == "watch":
        return "SEV-2"
    return "SEV-3"


def _ownership_from_level(level: str) -> str:
    lv = str(level or "").strip().lower()
    if lv == "incident":
        return "primary_and_secondary_oncall"
    if lv == "watch":
        return "primary_oncall"
    return "none"


def _build_markdown(out: Dict[str, Any]) -> str:
    slo = out.get("slo") if isinstance(out.get("slo"), dict) else {}
    inc = out.get("incident") if isinstance(out.get("incident"), dict) else {}
    policy = out.get("policy") if isinstance(out.get("policy"), dict) else {}
    checklist = out.get("checklist") if isinstance(out.get("checklist"), list) else []

    lines = [
        f"# M31-1 SLO and Incident Review Check ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- required_pass_total: **{int(out.get('required_pass_total') or 0)}**",
        f"- required_fail_total: **{int(out.get('required_fail_total') or 0)}**",
        "",
        "## SLO Snapshot",
        "",
        f"- run_total: **{int(slo.get('run_total') or 0)}**",
        f"- success_run_total: **{int(slo.get('success_run_total') or 0)}**",
        f"- availability_rate: **{float(slo.get('availability_rate') or 0.0):.2%}**",
        f"- event_total: **{int(slo.get('event_total') or 0)}**",
        f"- error_total: **{int(slo.get('error_total') or 0)}**",
        f"- error_rate: **{float(slo.get('error_rate') or 0.0):.2%}**",
        "",
        "## Incident and Ownership",
        "",
        f"- escalation_level: **{policy.get('escalation_level')}**",
        f"- severity: **{policy.get('severity')}**",
        f"- ownership: **{policy.get('ownership')}**",
        f"- cooldown_transition_total: **{int(inc.get('cooldown_transition_total') or 0)}**",
        f"- intervention_total: **{int(inc.get('intervention_total') or 0)}**",
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
    p = argparse.ArgumentParser(description="M31-1 daily SLO baseline + incident ownership check.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--policy-report-dir", default="reports/m30_post_golive")
    p.add_argument("--signoff-report-dir", default="reports/m30_golive")
    p.add_argument("--report-dir", default="reports/m31_slo_incident")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--min-availability-rate", type=float, default=0.99)
    p.add_argument("--max-error-rate", type=float, default=0.20)
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    event_log_path = Path(str(args.event_log_path).strip())
    policy_report_dir = Path(str(args.policy_report_dir).strip())
    signoff_report_dir = Path(str(args.signoff_report_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    min_availability_rate = max(0.0, min(1.0, float(args.min_availability_rate)))
    max_error_rate = max(0.0, min(1.0, float(args.max_error_rate)))
    inject_fail = bool(args.inject_fail)

    report_dir.mkdir(parents=True, exist_ok=True)

    event_total = 0
    error_total = 0
    run_total_set: set[str] = set()
    error_run_set: set[str] = set()
    cooldown_transition_total = 0
    intervention_total = 0
    stage_error_total: Counter[str] = Counter()

    for row in _iter_jsonl(event_log_path):
        row_day = _utc_day(row.get("ts"))
        if row_day != day:
            continue

        event_total += 1
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            run_total_set.add(run_id)

        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}

        if event == "error":
            error_total += 1
            if run_id:
                error_run_set.add(run_id)
            stage_error_total[stage or "unknown"] += 1

        if stage == "commander_router" and event == "transition":
            transition = str(payload.get("transition") or "").strip().lower()
            if transition == "cooldown":
                cooldown_transition_total += 1

        if stage == "commander_router" and event == "intervention":
            intervention_total += 1

    run_total = int(len(run_total_set))
    success_run_total = int(max(0, run_total - len(error_run_set)))
    availability_rate = float(success_run_total) / float(run_total) if run_total > 0 else 0.0
    error_rate = float(error_total) / float(event_total) if event_total > 0 else 0.0

    policy_path = policy_report_dir / f"m30_post_golive_policy_{day}.json"
    signoff_path = signoff_report_dir / f"m30_final_golive_signoff_{day}.json"
    policy_obj = _read_json(policy_path)
    signoff_obj = _read_json(signoff_path)

    escalation_level = str(policy_obj.get("escalation_level") or "").strip().lower()
    policy = policy_obj.get("policy") if isinstance(policy_obj.get("policy"), dict) else {}
    manual_approval_only = bool(policy.get("manual_approval_only"))
    oncall_escalation = str(policy.get("oncall_escalation") or "").strip().lower()
    severity = _severity_from_level(escalation_level)
    expected_ownership = _ownership_from_level(escalation_level)
    ownership_ok = (oncall_escalation == expected_ownership) or (not escalation_level)

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="policy_artifact_presence",
            title="M30 post-go-live policy artifact exists",
            passed=bool(policy_obj),
            evidence=f"path={policy_path}, exists={bool(policy_obj)}",
        ),
        _item(
            item_id="signoff_artifact_presence",
            title="M30 final signoff artifact exists",
            passed=bool(signoff_obj),
            evidence=f"path={signoff_path}, exists={bool(signoff_obj)}",
        ),
        _item(
            item_id="slo_probe_measurable",
            title="Daily SLO probes are measurable from artifacts",
            passed=(event_total > 0 and run_total > 0),
            evidence=f"event_total={event_total}, run_total={run_total}",
        ),
        _item(
            item_id="slo_availability_guard",
            title="Availability rate meets threshold",
            passed=availability_rate >= min_availability_rate,
            evidence=f"availability_rate={availability_rate:.4f}, threshold={min_availability_rate:.4f}",
        ),
        _item(
            item_id="slo_error_budget_guard",
            title="Error rate stays within threshold",
            passed=error_rate <= max_error_rate,
            evidence=f"error_rate={error_rate:.4f}, threshold={max_error_rate:.4f}",
        ),
        _item(
            item_id="severity_ownership_deterministic",
            title="Severity ladder and on-call ownership are deterministic from policy level",
            passed=ownership_ok,
            evidence=(
                f"escalation_level={escalation_level or '(none)'}, severity={severity}, "
                f"oncall_escalation={oncall_escalation or '(none)'}, expected={expected_ownership or '(none)'}"
            ),
        ),
        _item(
            item_id="incident_manual_approval_guard",
            title="Incident level enforces manual approval",
            passed=(escalation_level != "incident") or manual_approval_only,
            evidence=f"escalation_level={escalation_level or '(none)'}, manual_approval_only={manual_approval_only}",
        ),
    ]

    failures: List[str] = []
    for item in checklist:
        if bool(item.get("required")) and not bool(item.get("passed")):
            failures.append(f"check_failed:{item.get('id')}")
    if inject_fail:
        failures.append("inject_fail forced red-path for operator drill")

    required_total = int(sum(1 for x in checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)
    ok = (len(failures) == 0) and (not inject_fail)

    out: Dict[str, Any] = {
        "ok": bool(ok),
        "inject_fail": inject_fail,
        "day": day,
        "event_log_path": str(event_log_path),
        "policy_report_dir": str(policy_report_dir),
        "signoff_report_dir": str(signoff_report_dir),
        "report_dir": str(report_dir),
        "thresholds": {
            "min_availability_rate": min_availability_rate,
            "max_error_rate": max_error_rate,
        },
        "slo": {
            "event_total": int(event_total),
            "error_total": int(error_total),
            "error_rate": float(error_rate),
            "run_total": int(run_total),
            "success_run_total": int(success_run_total),
            "availability_rate": float(availability_rate),
            "stage_error_top": dict(stage_error_total.most_common(5)),
        },
        "incident": {
            "cooldown_transition_total": int(cooldown_transition_total),
            "intervention_total": int(intervention_total),
        },
        "policy": {
            "path": str(policy_path),
            "exists": bool(policy_obj),
            "escalation_level": escalation_level,
            "severity": severity,
            "ownership": expected_ownership,
            "manual_approval_only": manual_approval_only,
            "oncall_escalation": oncall_escalation,
        },
        "signoff": {
            "path": str(signoff_path),
            "exists": bool(signoff_obj),
            "approved": bool(signoff_obj.get("approved")),
            "go_live_decision": str(signoff_obj.get("go_live_decision") or ""),
        },
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m31_slo_incident_{day}.json"
    md_path = report_dir / f"m31_slo_incident_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} availability_rate={out['slo']['availability_rate']:.2%} "
            f"error_rate={out['slo']['error_rate']:.2%} severity={out['policy']['severity']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if bool(ok) else 3


if __name__ == "__main__":
    raise SystemExit(main())
