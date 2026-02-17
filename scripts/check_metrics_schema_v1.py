from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.generate_metrics_report import generate_metrics_report


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_dict(v: Any) -> bool:
    return isinstance(v, dict)


def _is_list(v: Any) -> bool:
    return isinstance(v, list)


def _json_path_get(obj: Dict[str, Any], path: str) -> Tuple[bool, Any]:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate frozen metrics schema v1.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/metrics")
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    _, js_path = generate_metrics_report(events_path, report_dir, day=args.day)
    try:
        metrics = json.loads(js_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: failed to read metrics json: {e}")
        return 2

    required: List[Tuple[str, Callable[[Any], bool], str]] = [
        ("schema_version", lambda v: v == "metrics.v1", "must equal metrics.v1"),
        ("strategist_llm.success_rate", _is_number, "must be number"),
        ("strategist_llm.latency_ms.p95", _is_number, "must be number"),
        ("strategist_llm.circuit_open_rate", _is_number, "must be number"),
        ("execution.intents_created", _is_number, "must be number"),
        ("execution.intents_approved", _is_number, "must be number"),
        ("execution.intents_blocked", _is_number, "must be number"),
        ("execution.intents_executed", _is_number, "must be number"),
        ("execution.blocked_reason_topN", _is_list, "must be list"),
        ("broker_api.api_error_total_by_api_id", _is_dict, "must be object"),
        ("broker_api.api_429_rate", _is_number, "must be number"),
    ]

    failures: List[str] = []
    for path, validator, rule in required:
        found, value = _json_path_get(metrics, path)
        if not found:
            failures.append(f"missing:{path}")
            continue
        if not bool(validator(value)):
            failures.append(f"invalid:{path} ({rule})")

    out = {
        "ok": len(failures) == 0,
        "schema_version": str(metrics.get("schema_version") or ""),
        "metrics_json_path": str(js_path),
        "required_total": len(required),
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} schema_version={out['schema_version']} "
            f"required_total={out['required_total']} failure_total={out['failure_total']}"
        )
        if failures:
            for msg in failures:
                print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
