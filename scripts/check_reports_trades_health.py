from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _iter_trade_dirs(reports_root: Path, day: str = "") -> List[Path]:
    trades_root = reports_root / "trades"
    if not trades_root.exists():
        return []
    if day:
        day_root = trades_root / day
        if not day_root.exists():
            return []
        return sorted(path for path in day_root.iterdir() if path.is_dir())
    out: List[Path] = []
    for path in sorted(trades_root.iterdir()):
        if not path.is_dir():
            continue
        if len(path.name) == 10 and path.name.count("-") == 2:
            out.extend(sorted(child for child in path.iterdir() if child.is_dir()))
    return out


def _artifact_path(trade_dir: Path, *candidates: str) -> Path:
    for raw in candidates:
        path = trade_dir / raw
        if path.exists():
            return path
    return trade_dir / candidates[0]


def _issue(
    *,
    severity: str,
    trade_id: str,
    component: str,
    code: str,
    message: str,
    path: Path,
) -> Dict[str, Any]:
    return {
        "severity": severity,
        "trade_id": trade_id,
        "component": component,
        "code": code,
        "message": message,
        "path": str(path),
    }


def audit_reports_trades_health(reports_root: Path, *, day: str = "") -> Dict[str, Any]:
    trade_dirs = _iter_trade_dirs(reports_root, day=day)
    issues: List[Dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    llm_status_counts: Counter[str] = Counter()
    lifecycle_status_counts: Counter[str] = Counter()
    duplicate_counts: Counter[str] = Counter()
    sidecar_counts: Counter[str] = Counter()

    for trade_dir in trade_dirs:
        trade_id = trade_dir.name
        lifecycle_path = _artifact_path(trade_dir, "lifecycle/trade_lifecycle.json", "trade_lifecycle.json")
        ai_trade_report_llm_path = _artifact_path(trade_dir, "ai_trade_report/ai_trade_report_llm_response.json")
        brief_llm_path = _artifact_path(trade_dir, "brief/brief_llm_response.json", "brief_llm_response.json")
        strategist_llm_path = _artifact_path(trade_dir, "strategist/strategist_llm_response.json")

        for sidecar_name in ("_provenance.json", "_health.json", "_artifact_links.json"):
            if (trade_dir / sidecar_name).exists():
                sidecar_counts[f"{sidecar_name}:present"] += 1
            else:
                sidecar_counts[f"{sidecar_name}:missing"] += 1
                issues.append(
                    _issue(
                        severity="warn",
                        trade_id=trade_id,
                        component="trade_root",
                        code="sidecar_missing",
                        message=f"Missing additive sidecar {sidecar_name}.",
                        path=trade_dir / sidecar_name,
                    )
                )
                issue_counts["sidecar_missing"] += 1

        legacy_brief_llm_path = trade_dir / "brief_llm_response.json"
        canonical_brief_llm_path = trade_dir / "brief" / "brief_llm_response.json"
        if legacy_brief_llm_path.exists() and canonical_brief_llm_path.exists():
            if legacy_brief_llm_path.read_bytes() == canonical_brief_llm_path.read_bytes():
                duplicate_counts["brief_llm_response:identical"] += 1
            else:
                duplicate_counts["brief_llm_response:different"] += 1
                issues.append(
                    _issue(
                        severity="warn",
                        trade_id=trade_id,
                        component="brief",
                        code="legacy_duplicate_mismatch",
                        message="Legacy and canonical brief LLM artifacts differ.",
                        path=canonical_brief_llm_path,
                    )
                )
                issue_counts["legacy_duplicate_mismatch"] += 1

        lifecycle = _read_json(lifecycle_path)
        lifecycle_diag = lifecycle.get("ai_report_diagnostics") if isinstance(lifecycle.get("ai_report_diagnostics"), dict) else {}
        lifecycle_status = str(lifecycle_diag.get("report_status") or "").strip().lower()
        if lifecycle_status:
            lifecycle_status_counts[lifecycle_status] += 1

        component_paths = {
            "ai_trade_report": ai_trade_report_llm_path,
            "brief": brief_llm_path,
            "strategist": strategist_llm_path,
        }
        component_rows: Dict[str, Dict[str, Any]] = {}
        for component, path in component_paths.items():
            payload = _read_json(path)
            component_rows[component] = payload
            if not payload:
                continue
            status = str(payload.get("status") or "").strip().lower()
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            if component == "strategist" and bool(meta.get("synthetic_placeholder")):
                llm_status_counts["strategist:synthetic_placeholder"] += 1
                continue
            if (
                component == "strategist"
                and status == "fallback"
                and not str(payload.get("model") or "").strip()
                and not str(payload.get("raw_response_text") or "").strip()
                and not str(payload.get("error") or "").strip()
                and int(payload.get("retry_count") or 0) == 0
            ):
                llm_status_counts["strategist:synthetic_placeholder"] += 1
                continue
            if status:
                llm_status_counts[f"{component}:{status}"] += 1
            if component == "ai_trade_report" and status in {"partial", "salvaged", "repaired"}:
                missing = payload.get("required_keys_missing") if isinstance(payload.get("required_keys_missing"), list) else []
                parse_error = str(meta.get("parse_error") or payload.get("error") or "").strip()
                issues.append(
                    _issue(
                        severity="warn",
                        trade_id=trade_id,
                        component=component,
                        code="llm_partial",
                        message=f"AI trade report LLM output is {status}; missing_keys={len(missing)} parse_error={parse_error[:120]}",
                        path=path,
                    )
                )
                issue_counts["llm_partial"] += 1
            elif component == "brief" and status == "error":
                reason = str(meta.get("reason") or payload.get("error") or "").strip()
                issues.append(
                    _issue(
                        severity="warn",
                        trade_id=trade_id,
                        component=component,
                        code="llm_error",
                        message=reason or "Brief generation failed without a saved reason.",
                        path=path,
                    )
                )
                issue_counts["llm_error"] += 1
            elif component == "strategist" and status == "fallback":
                parse_mode = str(payload.get("parse_mode") or "").strip().lower()
                raw_len = len(str(payload.get("raw_response_text") or ""))
                issues.append(
                    _issue(
                        severity="warn",
                        trade_id=trade_id,
                        component=component,
                        code="llm_fallback",
                        message=f"Strategist LLM fell back; parse_mode={parse_mode or 'none'} raw_response_len={raw_len}.",
                        path=path,
                    )
                )
                issue_counts["llm_fallback"] += 1

        ai_report_payload = component_rows.get("ai_trade_report") or {}
        ai_report_status = str(ai_report_payload.get("status") or "").strip().lower()
        if lifecycle_status == "failed" and ai_report_status in {"partial", "salvaged", "repaired"}:
            issues.append(
                _issue(
                    severity="warn",
                    trade_id=trade_id,
                    component="lifecycle",
                    code="diagnostic_status_mismatch",
                    message=(
                        "Lifecycle diagnostics say failed, but an AI trade report artifact exists in "
                        f"{ai_report_status} state."
                    ),
                    path=lifecycle_path,
                )
            )
            issue_counts["diagnostic_status_mismatch"] += 1

    severity_counts = Counter(str(item.get("severity") or "info").lower() for item in issues)
    return {
        "ok": len([item for item in issues if str(item.get("severity") or "").lower() == "error"]) == 0,
        "reports_root": str(reports_root),
        "day": day,
        "trade_dir_count": len(trade_dirs),
        "llm_status_counts": dict(sorted(llm_status_counts.items())),
        "lifecycle_report_status_counts": dict(sorted(lifecycle_status_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
        "duplicate_counts": dict(sorted(duplicate_counts.items())),
        "sidecar_counts": dict(sorted(sidecar_counts.items())),
        "issues": issues,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only health audit for reports/trades artifacts.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--day", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    reports_root = Path(str(args.reports_root).strip() or "reports")
    if not reports_root.is_absolute():
        reports_root = ROOT / reports_root
    out = audit_reports_trades_health(reports_root, day=str(args.day).strip())
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} trade_dir_count={out['trade_dir_count']} "
            f"issue_counts={json.dumps(out['issue_counts'], ensure_ascii=False)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
