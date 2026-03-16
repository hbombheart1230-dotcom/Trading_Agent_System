from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.symbols import normalize_symbol
from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.reporter_analysis import generate_reporter_analysis_report
from libs.reporting.trade_explain import generate_trade_explain_report


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
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
                out.append(obj)
    return out


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    raw = str(ts).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        pass
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> str:
    epoch = _to_epoch(ts)
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _normalize_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"action": "", "symbol": "", "qty": 0, "status": "", "ord_no": ""}
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    broker = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    response_payload = broker.get("response_payload") if isinstance(broker.get("response_payload"), dict) else {}
    return {
        "action": str(payload.get("action") or order.get("action") or "").upper(),
        "symbol": normalize_symbol(
            payload.get("symbol") or order.get("symbol") or order.get("stk_cd") or "",
            allow_test_symbols=True,
        ),
        "qty": _safe_int(payload.get("qty"), _safe_int(order.get("qty"), _safe_int(order.get("ord_qty"), 0))),
        "status": str(
            payload.get("fill_status_summary")
            or payload.get("status")
            or broker.get("broker_message")
            or response_payload.get("return_msg")
            or ""
        ),
        "ord_no": str(payload.get("ord_no") or broker.get("order_id") or response_payload.get("ord_no") or ""),
    }


def _latest_execution_day(event_log_path: Path) -> str:
    best_day = ""
    best_epoch = -1
    for row in _iter_jsonl(event_log_path):
        if str(row.get("stage") or "") != "execute_from_packet":
            continue
        if str(row.get("event") or "") != "execution":
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"}:
            continue
        if not str(execution.get("symbol") or "").strip():
            continue
        epoch = _to_epoch(row.get("ts"))
        if epoch is None or epoch < best_epoch:
            continue
        best_epoch = epoch
        best_day = _utc_day(row.get("ts"))
    return best_day


def _resolve_execution_runs(event_log_path: Path, day: str) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    rows = sorted(_iter_jsonl(event_log_path), key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    for row in rows:
        if str(row.get("stage") or "") != "execute_from_packet":
            continue
        if str(row.get("event") or "") != "execution":
            continue
        if day and _utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id or run_id in seen:
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"}:
            continue
        if not str(execution.get("symbol") or "").strip():
            continue
        seen.add(run_id)
        out.append(
            {
                "run_id": run_id,
                "ts": str(row.get("ts") or ""),
                "action": str(execution.get("action") or "").upper(),
                "symbol": str(execution.get("symbol") or ""),
                "qty": _safe_int(execution.get("qty"), 0),
                "status": str(execution.get("status") or ""),
                "ord_no": str(execution.get("ord_no") or ""),
            }
        )
    out.sort(key=lambda row: _to_epoch(row.get("ts")) or 0)
    return out


def _resolve_existing_day_artifact(report_dir: Path, prefix: str, day: str) -> Tuple[Path, Path]:
    return report_dir / f"{prefix}_{day}.md", report_dir / f"{prefix}_{day}.json"


def _load_or_generate_trade_explain(event_log_path: Path, analysis_root: Path, day: str) -> Tuple[Path, Path, Dict[str, Any]]:
    report_dir = analysis_root / "trade_explain"
    md_path, js_path = _resolve_existing_day_artifact(report_dir, "trade_explain", day)
    if js_path.exists() and md_path.exists():
        try:
            obj = json.loads(js_path.read_text(encoding="utf-8"))
        except Exception:
            obj = {}
        return md_path, js_path, obj if isinstance(obj, dict) else {}
    return generate_trade_explain_report(event_log_path, report_dir, day=day)


def _load_or_generate_reporter_analysis(
    event_log_path: Path,
    analysis_root: Path,
    reports_root: Path,
    intents_path: Optional[Path],
    day: str,
) -> Tuple[Path, Path, Dict[str, Any]]:
    report_dir = analysis_root / "reporter_analysis"
    md_path, js_path = _resolve_existing_day_artifact(report_dir, "reporter_analysis", day)
    if js_path.exists() and md_path.exists():
        try:
            obj = json.loads(js_path.read_text(encoding="utf-8"))
        except Exception:
            obj = {}
        return md_path, js_path, obj if isinstance(obj, dict) else {}
    return generate_reporter_analysis_report(
        event_log_path,
        report_dir,
        day=day,
        intents_path=intents_path if intents_path and intents_path.exists() else None,
        reports_root=reports_root,
    )


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _render_bundle_markdown(out: Dict[str, Any]) -> str:
    strategist = out.get("strategist") if isinstance(out.get("strategist"), dict) else {}
    scanner = out.get("scanner") if isinstance(out.get("scanner"), dict) else {}
    monitor = out.get("monitor") if isinstance(out.get("monitor"), dict) else {}
    reporter = out.get("reporter") if isinstance(out.get("reporter"), dict) else {}
    execution = out.get("execution") if isinstance(out.get("execution"), dict) else {}
    artifacts = out.get("artifacts") if isinstance(out.get("artifacts"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Live Execution Bundle ({out.get('run_id')})")
    lines.append("")
    lines.append(f"- day: **{out.get('day')}**")
    lines.append(
        f"- execution: **{execution.get('action')} {execution.get('symbol')} x{execution.get('qty')}** "
        f"status=`{execution.get('status') or '-'}` ord_no=`{execution.get('ord_no') or '-'}`"
    )
    lines.append(f"- execution_ts: `{execution.get('ts') or ''}`")
    lines.append("")
    lines.append("## Strategist")
    lines.append(
        f"- playbook: **{strategist.get('playbook')}** themes=`{json.dumps(strategist.get('themes') or [], ensure_ascii=False)}`"
    )
    lines.append(
        f"- market context: sentiment={strategist.get('global_sentiment_score')} "
        f"vix=`{json.dumps(strategist.get('fear_index') or {}, ensure_ascii=False)}`"
    )
    if strategist.get("news_query_reasoning"):
        lines.append(f"- news_query_reasoning: {strategist.get('news_query_reasoning')}")
    lines.append("")
    lines.append("## Scanner")
    lines.append(
        f"- top_stock: **{scanner.get('top_stock')}** top_score={scanner.get('top_score')} "
        f"pool_after={scanner.get('candidate_pool_after_filter')}"
    )
    lines.append(f"- selected_candidate: `{json.dumps(scanner.get('selected_candidate') or {}, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Monitor")
    lines.append(
        f"- selected_symbol={monitor.get('selected_symbol')} entry_reason={monitor.get('entry_reason')} "
        f"exit_reason={monitor.get('exit_reason')} monitor_reason={monitor.get('monitor_reason')}"
    )
    lines.append(f"- thresholds: `{json.dumps(monitor.get('thresholds') or {}, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Reporter")
    lines.append(
        f"- reporter_analysis_found={reporter.get('reporter_analysis_found')} "
        f"day_file_found={reporter.get('reporter_analysis_day_file_found')}"
    )
    lines.append(f"- reporter_analysis_path: `{reporter.get('reporter_analysis_path') or ''}`")
    lines.append("")
    lines.append("## Artifacts")
    for key, value in artifacts.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _render_summary_markdown(out: Dict[str, Any]) -> str:
    bundles = out.get("bundles") if isinstance(out.get("bundles"), list) else []
    lines: List[str] = []
    lines.append(f"# Live Execution Bundles ({out.get('day')})")
    lines.append("")
    lines.append(f"- bundle_count: **{out.get('bundle_count')}**")
    lines.append(f"- event_log_path: `{out.get('event_log_path')}`")
    lines.append(f"- evidence_log_path: `{out.get('evidence_log_path')}`")
    lines.append("")
    if not bundles:
        lines.append("No executed BUY/SELL runs were found for the selected day.")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Bundles")
    lines.append("")
    for row in bundles:
        lines.append(
            f"- `{row.get('run_id')}` {row.get('action')} {row.get('symbol')} x{row.get('qty')} "
            f"status=`{row.get('status')}` json=`{row.get('report_json_path')}`"
        )
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate run-level live execution bundles for executed BUY/SELL runs.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--evidence-log-path", default="data/evidence_ledger/events.jsonl")
    p.add_argument("--report-dir", default="reports/dev/analysis/live_execution_bundles")
    p.add_argument("--reports-root", default="reports")
    p.add_argument("--intents-path", default="data/logs/intents.jsonl")
    p.add_argument("--day", default=None)
    p.add_argument("--max-runs", type=int, default=50)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    event_log_path = Path(str(args.event_log_path).strip())
    evidence_log_path = Path(str(args.evidence_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    reports_root = Path(str(args.reports_root).strip())
    intents_path = Path(str(args.intents_path).strip()) if str(args.intents_path or "").strip() else None
    day = str(args.day).strip() if args.day else _latest_execution_day(event_log_path)
    analysis_root = report_dir.parent

    report_dir.mkdir(parents=True, exist_ok=True)

    if not day:
        out = {
            "schema_version": "live_execution_bundles.v1",
            "ok": False,
            "error": "no_execution_day_detected",
            "event_log_path": str(event_log_path),
            "evidence_log_path": str(evidence_log_path),
            "bundle_count": 0,
            "bundles": [],
        }
        if bool(args.json):
            print(json.dumps(out, ensure_ascii=False))
        else:
            print("ok=false error=no_execution_day_detected")
        return 3

    execution_runs = _resolve_execution_runs(event_log_path, day)[: max(1, int(args.max_runs))]
    trade_md, trade_js, _trade_out = _load_or_generate_trade_explain(event_log_path, analysis_root, day)
    reporter_md, reporter_js, _reporter_out = _load_or_generate_reporter_analysis(
        event_log_path,
        analysis_root,
        reports_root,
        intents_path,
        day,
    )
    operator_summary_json = reports_root / "operator_summary" / f"operator_summary_{day}.json"
    operator_summary_md = reports_root / "operator_summary" / f"operator_summary_{day}.md"

    bundles: List[Dict[str, Any]] = []
    for execution in execution_runs:
        run_id = str(execution.get("run_id") or "").strip()
        trace_md, trace_js, trace_out = generate_agent_pipeline_trace_report(
            event_log_path=event_log_path,
            evidence_log_path=evidence_log_path,
            report_dir=report_dir / "agent_pipeline_trace",
            run_id=run_id,
            day=day,
            reports_root=analysis_root,
        )
        bundle_out: Dict[str, Any] = {
            "schema_version": "live_execution_bundle.v1",
            "ts": _utc_now_iso(),
            "day": day,
            "run_id": run_id,
            "execution": dict(execution),
            "strategist": dict(trace_out.get("strategist") or {}),
            "scanner": dict(trace_out.get("scanner") or {}),
            "monitor": dict(trace_out.get("monitor") or {}),
            "supervisor": dict(trace_out.get("supervisor") or {}),
            "executor": dict(trace_out.get("executor") or {}),
            "reporter": {
                **dict(trace_out.get("reporter") or {}),
                "reporter_analysis_summary": str((_read_json(reporter_js).get("ai_summary") or "")),
            },
            "artifacts": {
                "agent_pipeline_trace_json": str(trace_js),
                "agent_pipeline_trace_md": str(trace_md),
                "trade_explain_json": str(trade_js),
                "trade_explain_md": str(trade_md),
                "reporter_analysis_json": str(reporter_js),
                "reporter_analysis_md": str(reporter_md),
                "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
                "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
            },
        }
        safe_run = "".join(ch for ch in run_id if ch.isalnum() or ch in ("_", "-"))[:40] or "run"
        bundle_json = report_dir / f"live_execution_bundle_{safe_run}.json"
        bundle_md = report_dir / f"live_execution_bundle_{safe_run}.md"
        bundle_out["report_json_path"] = str(bundle_json)
        bundle_out["report_md_path"] = str(bundle_md)
        bundle_json.write_text(json.dumps(bundle_out, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_md.write_text(_render_bundle_markdown(bundle_out), encoding="utf-8")
        bundles.append(
            {
                "run_id": run_id,
                "action": execution.get("action"),
                "symbol": execution.get("symbol"),
                "qty": execution.get("qty"),
                "status": execution.get("status"),
                "report_json_path": str(bundle_json),
                "report_md_path": str(bundle_md),
            }
        )

    summary_out: Dict[str, Any] = {
        "schema_version": "live_execution_bundles.v1",
        "ok": True,
        "ts": _utc_now_iso(),
        "day": day,
        "event_log_path": str(event_log_path),
        "evidence_log_path": str(evidence_log_path),
        "bundle_count": len(bundles),
        "bundles": bundles,
        "day_artifacts": {
            "trade_explain_json": str(trade_js),
            "trade_explain_md": str(trade_md),
            "reporter_analysis_json": str(reporter_js),
            "reporter_analysis_md": str(reporter_md),
            "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
            "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
        },
    }
    summary_json = report_dir / f"live_execution_bundles_{day}.json"
    summary_md = report_dir / f"live_execution_bundles_{day}.md"
    summary_out["report_json_path"] = str(summary_json)
    summary_out["report_md_path"] = str(summary_md)
    summary_json.write_text(json.dumps(summary_out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md.write_text(_render_summary_markdown(summary_out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(summary_out, ensure_ascii=False))
    else:
        print(
            f"day={day} bundle_count={len(bundles)} "
            f"report_json={summary_json} report_md={summary_md}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
