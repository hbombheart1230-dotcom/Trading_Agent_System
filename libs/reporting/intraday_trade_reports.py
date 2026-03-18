from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _brief_cache_dir(root: Path) -> Path:
    return Path(
        os.getenv("OPERATOR_UI_CACHE_PATH", str(root / "data" / "operator_ui" / "brief_cache"))
    )


def _execution_action(state: Dict[str, Any]) -> str:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    return str(order.get("action") or execution.get("action") or "").strip().upper()


def _execution_ok(state: Dict[str, Any]) -> bool:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    return bool(execution.get("ok")) and bool(execution.get("allowed", True))


def _cache_run_ids(summary: Dict[str, Any], current_run_id: str) -> List[str]:
    run_bundles = summary.get("run_bundles") if isinstance(summary.get("run_bundles"), list) else []
    matched_trade_ids = {
        str(row.get("trade_id") or "").strip()
        for row in run_bundles
        if str(row.get("run_id") or "").strip() == current_run_id and str(row.get("trade_id") or "").strip()
    }
    run_ids = {current_run_id}
    for row in run_bundles:
        if not isinstance(row, dict):
            continue
        trade_id = str(row.get("trade_id") or "").strip()
        run_id = str(row.get("run_id") or "").strip()
        if trade_id and trade_id in matched_trade_ids and run_id:
            run_ids.add(run_id)
    return sorted(x for x in run_ids if x)


def _invalidate_brief_cache(root: Path, run_ids: Iterable[str]) -> List[str]:
    cache_dir = _brief_cache_dir(root)
    removed: List[str] = []
    for run_id in run_ids:
        path = cache_dir / f"{run_id}.json"
        if not path.exists():
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except Exception:
            continue
    return removed


def generate_intraday_trade_artifacts(state: Dict[str, Any], *, root: Path | None = None) -> Dict[str, Any]:
    if not _is_trueish(os.getenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")):
        return {"ok": False, "status": "disabled", "reason": "intraday_trade_reports_disabled"}

    if not _execution_ok(state):
        return {"ok": False, "status": "skipped", "reason": "execution_not_successful"}

    action = _execution_action(state)
    if action not in {"BUY", "SELL"}:
        return {"ok": False, "status": "skipped", "reason": "non_trade_action"}

    repo_root = Path(root) if root is not None else _root_dir()
    run_id = str(state.get("run_id") or "").strip()
    from scripts.run_live_execution_bundle_report import main as bundle_main

    argv = [
        "--env-path",
        str(Path(os.getenv("ENV_PATH", str(repo_root / ".env")))),
        "--event-log-path",
        str(Path(os.getenv("EVENT_LOG_PATH", str(repo_root / "data" / "logs" / "events.jsonl")))),
        "--evidence-log-path",
        str(Path(os.getenv("EVIDENCE_LOG_PATH", str(repo_root / "data" / "evidence_ledger" / "events.jsonl")))),
        "--report-dir",
        str(repo_root / "reports" / "dev" / "analysis" / "live_execution_bundles"),
        "--reports-root",
        str(repo_root / "reports"),
        "--intents-path",
        str(Path(os.getenv("INTENTS_PATH", str(repo_root / "data" / "logs" / "intents.jsonl")))),
        "--max-runs",
        str(int(float(os.getenv("INTRADAY_TRADE_REPORT_MAX_RUNS", "200")))),
        "--trade-report-ai",
        "--json",
    ]

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = bundle_main(argv)
    raw = stdout.getvalue().strip()
    try:
        summary = json.loads(raw) if raw else {}
    except Exception:
        summary = {}

    if rc != 0 or not isinstance(summary, dict):
        return {
            "ok": False,
            "status": "failed",
            "reason": "intraday_bundle_generation_failed",
            "return_code": int(rc),
            "stdout": raw[-1000:],
        }

    cache_run_ids = _cache_run_ids(summary, run_id)
    removed_cache = _invalidate_brief_cache(repo_root, cache_run_ids)
    run_bundles = summary.get("run_bundles") if isinstance(summary.get("run_bundles"), list) else []
    matched = next(
        (row for row in run_bundles if isinstance(row, dict) and str(row.get("run_id") or "").strip() == run_id),
        {},
    )
    brief_artifacts: Dict[str, str] = {}
    if run_id:
        try:
            from apps.operator_ui.data_access import OperatorUIConfig, load_run_detail

            detail = load_run_detail(OperatorUIConfig.from_env(repo_root=repo_root), run_id)
            trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
            brief_artifacts = {
                "operator_brief_json_path": str(trade_report.get("operator_brief_json_path") or ""),
                "operator_brief_md_path": str(trade_report.get("operator_brief_md_path") or ""),
            }
        except Exception:
            brief_artifacts = {}

    return {
        "ok": True,
        "status": "generated",
        "reason": "",
        "return_code": int(rc),
        "summary": summary,
        "trade_id": str((matched or {}).get("trade_id") or ""),
        "story_id": str((matched or {}).get("story_id") or ""),
        "report_status": str((matched or {}).get("report_status") or ""),
        "report_path": str((matched or {}).get("trade_report_json_path") or ""),
        "symbol": _normalize_symbol((matched or {}).get("symbol") or ""),
        "cache_invalidated": removed_cache,
        **brief_artifacts,
    }
