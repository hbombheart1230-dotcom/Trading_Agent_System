from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


CANONICAL_ARTIFACT_KEYS: Tuple[str, ...] = (
    "canonical_commander_json",
    "canonical_strategist_json",
    "canonical_scanner_json",
    "canonical_monitor_json",
    "canonical_supervisor_json",
    "canonical_executor_json",
)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _trade_dirs_for_day(reports_root: Path, day: str) -> List[Path]:
    base = reports_root / "trades" / str(day or "").strip()
    if not base.exists():
        return []
    out = [path for path in base.iterdir() if path.is_dir()]
    out.sort(key=lambda p: p.name)
    return out


def _is_closed_trade(bundle: Dict[str, Any]) -> bool:
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
    exit_payload = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    if exit_payload:
        return True
    status = str(
        bundle.get("trade_lifecycle_status")
        or lifecycle.get("status")
        or bundle.get("status")
        or ""
    ).strip().lower()
    if status in {"closed", "exited", "sell"}:
        return True
    top_exit = bundle.get("exit") if isinstance(bundle.get("exit"), dict) else {}
    return bool(top_exit.get("available"))


def _section_provenance_all_fallback(report: Dict[str, Any]) -> bool:
    provenance = report.get("section_provenance") if isinstance(report.get("section_provenance"), dict) else {}
    if not provenance:
        return False
    entries = [value for value in provenance.values() if isinstance(value, dict)]
    if not entries:
        return False
    fallback_tags = {"fallback", "unknown", "missing"}
    return all(str(entry.get("source") or "").strip().lower() in fallback_tags for entry in entries)


def _reporter_section_fallback(report: Dict[str, Any]) -> bool:
    provenance = report.get("section_provenance") if isinstance(report.get("section_provenance"), dict) else {}
    for key in ("reporter_evaluation", "errors_weaknesses_improvement_points"):
        item = provenance.get(key) if isinstance(provenance.get(key), dict) else {}
        source = str(item.get("source") or "").strip().lower()
        if source in {"fallback", "unknown", "missing"}:
            return True
    return False


def _missing_canonical_paths(bundle: Dict[str, Any]) -> bool:
    artifacts = bundle.get("artifacts") if isinstance(bundle.get("artifacts"), dict) else {}
    values = [str(artifacts.get(key) or bundle.get(key) or "").strip() for key in CANONICAL_ARTIFACT_KEYS]
    return any(not value for value in values)


def _thin_trace(bundle: Dict[str, Any]) -> bool:
    scanner_trace = bundle.get("scanner_selection_trace") if isinstance(bundle.get("scanner_selection_trace"), dict) else {}
    if not scanner_trace:
        scanner_reason = bundle.get("scanner_reason_human") if isinstance(bundle.get("scanner_reason_human"), dict) else {}
        scanner_trace = (
            scanner_reason.get("scanner_selection_trace")
            if isinstance(scanner_reason.get("scanner_selection_trace"), dict)
            else {}
        )
    ranked = scanner_trace.get("ranked_candidates") if isinstance(scanner_trace.get("ranked_candidates"), list) else []
    if not ranked:
        scanner_reason = bundle.get("scanner_reason_human") if isinstance(bundle.get("scanner_reason_human"), dict) else {}
        ranked = scanner_reason.get("ranked_candidates") if isinstance(scanner_reason.get("ranked_candidates"), list) else []

    monitor_trace = bundle.get("monitor_stop_policy_trace") if isinstance(bundle.get("monitor_stop_policy_trace"), dict) else {}
    if not monitor_trace:
        monitor_reason = bundle.get("monitor_reason_human") if isinstance(bundle.get("monitor_reason_human"), dict) else {}
        monitor_trace = (
            monitor_reason.get("monitor_stop_policy_trace")
            if isinstance(monitor_reason.get("monitor_stop_policy_trace"), dict)
            else {}
        )
    scanner_thin = len(ranked) == 0
    monitor_thin = len(monitor_trace) == 0
    return scanner_thin or monitor_thin


def analyze_day(reports_root: Path, day: str) -> Dict[str, Any]:
    trade_dirs = _trade_dirs_for_day(reports_root, day)
    metrics = {
        "day": day,
        "total_trades": 0,
        "closed_trades": 0,
        "closed_trade_ai_report_exists": 0,
        "closed_trade_ai_report_missing": 0,
        "all_fallback_section_count": 0,
        "reporter_fallback_count": 0,
        "missing_canonical_path_count": 0,
        "thin_trace_count": 0,
    }

    for trade_dir in trade_dirs:
        metrics["total_trades"] += 1
        bundle = _read_json(trade_dir / "lifecycle_bundle.json")
        report = _read_json(trade_dir / "reports" / "ai_trade_report.json")

        if _missing_canonical_paths(bundle):
            metrics["missing_canonical_path_count"] += 1
        if _thin_trace(bundle):
            metrics["thin_trace_count"] += 1

        if not _is_closed_trade(bundle):
            continue
        metrics["closed_trades"] += 1

        if report:
            metrics["closed_trade_ai_report_exists"] += 1
            if _section_provenance_all_fallback(report):
                metrics["all_fallback_section_count"] += 1
            if _reporter_section_fallback(report):
                metrics["reporter_fallback_count"] += 1
        else:
            metrics["closed_trade_ai_report_missing"] += 1

    closed = max(1, int(metrics["closed_trades"]))
    metrics["ratios"] = {
        "closed_trade_ai_report_exists_ratio": float(metrics["closed_trade_ai_report_exists"]) / float(closed),
        "all_fallback_section_ratio": float(metrics["all_fallback_section_count"]) / float(closed),
        "reporter_fallback_ratio": float(metrics["reporter_fallback_count"]) / float(closed),
    }
    return metrics


def compare_days(base: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "closed_trades",
        "closed_trade_ai_report_exists",
        "closed_trade_ai_report_missing",
        "all_fallback_section_count",
        "reporter_fallback_count",
        "missing_canonical_path_count",
        "thin_trace_count",
    )
    return {
        "base_day": str(base.get("day") or ""),
        "target_day": str(target.get("day") or ""),
        "deltas": {key: int(target.get(key) or 0) - int(base.get(key) or 0) for key in keys},
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check reporter upgrade regression metrics for trade artifacts.")
    parser.add_argument("--reports-root", default="reports", help="reports root directory (default: reports)")
    parser.add_argument("--day", action="append", required=True, help="target day (YYYY-MM-DD). can be repeated.")
    parser.add_argument("--json", action="store_true", help="print raw JSON output only")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    reports_root = Path(str(args.reports_root))
    days = [str(day).strip() for day in args.day if str(day).strip()]
    outputs = [analyze_day(reports_root, day) for day in days]
    payload: Dict[str, Any] = {"days": outputs}
    if len(outputs) >= 2:
        payload["comparison"] = compare_days(outputs[0], outputs[-1])

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for item in outputs:
        print(f"[day={item['day']}] total={item['total_trades']} closed={item['closed_trades']}")
        print(
            "  closed_reports: "
            f"exists={item['closed_trade_ai_report_exists']} missing={item['closed_trade_ai_report_missing']}"
        )
        print(
            "  fallback: "
            f"all_sections={item['all_fallback_section_count']} reporter={item['reporter_fallback_count']}"
        )
        print(
            "  quality: "
            f"missing_canonical={item['missing_canonical_path_count']} thin_trace={item['thin_trace_count']}"
        )

    if "comparison" in payload:
        cmp = payload["comparison"]
        print(f"[comparison] base={cmp['base_day']} target={cmp['target_day']}")
        for key, delta in (cmp.get("deltas") or {}).items():
            sign = "+" if int(delta) > 0 else ""
            print(f"  {key}: {sign}{delta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
