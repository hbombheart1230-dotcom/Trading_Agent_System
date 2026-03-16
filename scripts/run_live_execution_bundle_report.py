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

from libs.core.settings import load_env_file
from libs.core.symbols import normalize_symbol
from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.reporter_analysis import generate_reporter_analysis_report
from libs.reporting.trade_explain import generate_trade_explain_report
from libs.reporting.trade_report_ai import build_ai_trade_report, render_trade_report_markdown
from libs.reporting.trade_story_pipeline import (
    build_execution_outcome_human,
    build_filters_human,
    build_guard_reason_human,
    build_market_context_human,
    build_monitor_reason_human,
    build_operator_conclusion_human,
    build_reporter_status_human,
    build_scanner_reason_human,
    build_story_contract,
    build_story_id,
    build_timeline,
    build_trade_story_input,
    classify_story_type as _classify_story_type,
    collect_story_warnings,
    execution_mode_label,
    render_bundle_markdown,
    render_summary_markdown,
    safe_int,
    utc_now_iso,
)


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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


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
    stamped = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(stamped)
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
        "qty": safe_int(payload.get("qty"), safe_int(order.get("qty"), safe_int(order.get("ord_qty"), 0))),
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
        if str(row.get("stage") or "") != "execute_from_packet" or str(row.get("event") or "") != "execution":
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
        if str(row.get("stage") or "") != "execute_from_packet" or str(row.get("event") or "") != "execution":
            continue
        if day and _utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id or run_id in seen:
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"} or not str(execution.get("symbol") or "").strip():
            continue
        seen.add(run_id)
        out.append(
            {
                "run_id": run_id,
                "ts": str(row.get("ts") or ""),
                "action": str(execution.get("action") or "").upper(),
                "symbol": str(execution.get("symbol") or ""),
                "qty": safe_int(execution.get("qty"), 0),
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
        return md_path, js_path, _read_json(js_path)
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
        return md_path, js_path, _read_json(js_path)
    return generate_reporter_analysis_report(
        event_log_path,
        report_dir,
        day=day,
        intents_path=intents_path if intents_path and intents_path.exists() else None,
        reports_root=reports_root,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate run-level aggregated execution bundles and per-trade reports.")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--evidence-log-path", default="data/evidence_ledger/events.jsonl")
    p.add_argument("--report-dir", default="reports/dev/analysis/live_execution_bundles")
    p.add_argument("--reports-root", default="reports")
    p.add_argument("--intents-path", default="data/logs/intents.jsonl")
    p.add_argument("--day", default=None)
    p.add_argument("--max-runs", type=int, default=50)
    ai = p.add_mutually_exclusive_group()
    ai.add_argument("--trade-report-ai", dest="trade_report_ai", action="store_true")
    ai.add_argument("--no-trade-report-ai", dest="trade_report_ai", action="store_false")
    p.set_defaults(trade_report_ai=None)
    p.add_argument("--trade-report-ai-model", default=None)
    p.add_argument("--trade-report-ai-temperature", type=float, default=None)
    p.add_argument("--trade-report-ai-max-tokens", type=int, default=None)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    load_env_file(str(args.env_path).strip() or ".env")
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
            "schema_version": "live_execution_bundles.v2",
            "ok": False,
            "error": "no_execution_day_detected",
            "event_log_path": str(event_log_path),
            "evidence_log_path": str(evidence_log_path),
            "bundle_count": 0,
            "bundles": [],
        }
        print(json.dumps(out, ensure_ascii=False) if bool(args.json) else "ok=false error=no_execution_day_detected")
        return 3

    execution_runs = _resolve_execution_runs(event_log_path, day)[: max(1, int(args.max_runs))]
    trade_md, trade_js, trade_obj = _load_or_generate_trade_explain(event_log_path, analysis_root, day)
    reporter_md, reporter_js, reporter_obj = _load_or_generate_reporter_analysis(event_log_path, analysis_root, reports_root, intents_path, day)
    operator_summary_json = reports_root / "operator_summary" / f"operator_summary_{day}.json"
    operator_summary_md = reports_root / "operator_summary" / f"operator_summary_{day}.md"
    canonical_trades_root = reports_root / "trades"
    year_part, month_part = (day.split("-") + ["01", "01"])[:2]

    bundles: List[Dict[str, Any]] = []
    story_type_counts: Dict[str, int] = {}
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
            "schema_version": "live_execution_bundle.v2",
            "artifact_type": "aggregated_execution_bundle",
            "ts": utc_now_iso(),
            "day": day,
            "run_id": run_id,
            "execution": dict(execution),
            "commander": dict(trace_out.get("commander") or {}),
            "strategist": dict(trace_out.get("strategist") or {}),
            "scanner": dict(trace_out.get("scanner") or {}),
            "monitor": dict(trace_out.get("monitor") or {}),
            "supervisor": dict(trace_out.get("supervisor") or {}),
            "executor": dict(trace_out.get("executor") or {}),
            "reporter": {
                **dict(trace_out.get("reporter") or {}),
                "reporter_analysis_summary": str(reporter_obj.get("ai_summary") or ""),
                "reporter_analysis_grade": str(reporter_obj.get("ai_run_grade") or "N/A"),
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
            "trade_explain_summary": {
                "executions_total": safe_int((trade_obj.get("execution_summary") or {}).get("executions_total"), 0)
                if isinstance(trade_obj.get("execution_summary"), dict)
                else 0
            },
        }

        story_contract = build_story_contract(bundle_out)
        market_context_human = build_market_context_human(bundle_out["strategist"])
        scanner_reason_human = build_scanner_reason_human(bundle_out["scanner"], bundle_out["strategist"])
        filters_human = build_filters_human(bundle_out["scanner"], bundle_out["strategist"], bundle_out["supervisor"])
        monitor_reason_human = build_monitor_reason_human(bundle_out["monitor"], bundle_out["execution"])
        guard_reason_human = build_guard_reason_human(bundle_out["supervisor"])
        execution_outcome_human = build_execution_outcome_human(
            bundle_out["execution"],
            bundle_out["executor"],
            story_type=str(story_contract.get("story_type") or ""),
            mode_label=execution_mode_label(bundle_out["executor"]),
        )
        reporter_status_human = build_reporter_status_human(bundle_out["reporter"], reporter_obj)
        operator_conclusion_human = build_operator_conclusion_human(
            execution=bundle_out["execution"],
            scanner_reason_human=scanner_reason_human,
            filters_human=filters_human,
            monitor_reason_human=monitor_reason_human,
            execution_outcome_human=execution_outcome_human,
            reporter_status_human=reporter_status_human,
        )
        timeline = build_timeline(
            commander=bundle_out["commander"],
            market_context_human=market_context_human,
            scanner_reason_human=scanner_reason_human,
            monitor_reason_human=monitor_reason_human,
            guard_reason_human=guard_reason_human,
            execution_outcome_human=execution_outcome_human,
            reporter_status_human=reporter_status_human,
            execution=bundle_out["execution"],
        )
        warnings = collect_story_warnings(
            story_contract=story_contract,
            market_context_human=market_context_human,
            filters_human=filters_human,
            reporter_status_human=reporter_status_human,
            execution_outcome_human=execution_outcome_human,
        )
        story_contract["warnings"] = warnings

        story_id = build_story_id(day, bundle_out["execution"])
        canonical_dir = canonical_trades_root / year_part / month_part / story_id
        canonical_dir.mkdir(parents=True, exist_ok=True)
        bundle_out.update(
            {
                "story_id": story_id,
                "story_contract": story_contract,
                "market_context_human": market_context_human,
                "scanner_reason_human": scanner_reason_human,
                "filters_human": filters_human,
                "monitor_reason_human": monitor_reason_human,
                "guard_reason_human": guard_reason_human,
                "execution_outcome_human": execution_outcome_human,
                "reporter_status_human": reporter_status_human,
                "operator_conclusion_human": operator_conclusion_human,
                "timeline": timeline,
                "warnings": warnings,
            }
        )

        trade_story_input = build_trade_story_input(bundle_out)
        trade_report = build_ai_trade_report(
            trade_story_input,
            enabled=args.trade_report_ai,
            model=str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else None,
            temperature=args.trade_report_ai_temperature,
            max_tokens=args.trade_report_ai_max_tokens,
        )

        aggregated_bundle_path = canonical_dir / "aggregated_execution_bundle.json"
        story_input_path = canonical_dir / "trade_story_input.json"
        trade_report_json_path = canonical_dir / "trade_report.json"
        trade_report_md_path = canonical_dir / "trade_report.md"
        aggregated_bundle_path.write_text(json.dumps(bundle_out, ensure_ascii=False, indent=2), encoding="utf-8")
        story_input_path.write_text(json.dumps(trade_story_input, ensure_ascii=False, indent=2), encoding="utf-8")
        trade_report_json_path.write_text(json.dumps(trade_report, ensure_ascii=False, indent=2), encoding="utf-8")
        trade_report_md_path.write_text(render_trade_report_markdown(trade_report), encoding="utf-8")

        bundle_out["artifacts"].update(
            {
                "aggregated_execution_bundle_json": str(aggregated_bundle_path),
                "trade_story_input_json": str(story_input_path),
                "trade_report_json": str(trade_report_json_path),
                "trade_report_md": str(trade_report_md_path),
            }
        )
        bundle_json = report_dir / f"live_execution_bundle_{run_id}.json"
        bundle_md = report_dir / f"live_execution_bundle_{run_id}.md"
        bundle_out["report_json_path"] = str(bundle_json)
        bundle_out["report_md_path"] = str(bundle_md)
        bundle_json.write_text(json.dumps(bundle_out, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_md.write_text(render_bundle_markdown(bundle_out), encoding="utf-8")

        story_type = str(story_contract.get("story_type") or "unknown")
        story_type_counts[story_type] = int(story_type_counts.get(story_type, 0) + 1)
        bundles.append(
            {
                "run_id": run_id,
                "story_id": story_id,
                "story_type": story_type,
                "action": execution.get("action"),
                "symbol": execution.get("symbol"),
                "qty": execution.get("qty"),
                "status": execution.get("status"),
                "report_json_path": str(bundle_json),
                "report_md_path": str(bundle_md),
                "trade_story_input_path": str(story_input_path),
                "trade_report_json_path": str(trade_report_json_path),
                "trade_report_md_path": str(trade_report_md_path),
                "trade_report_summary": str((trade_report.get("executive_summary") or {}).get("summary") or ""),
            }
        )

    summary_out: Dict[str, Any] = {
        "schema_version": "live_execution_bundles.v2",
        "ok": True,
        "ts": utc_now_iso(),
        "day": day,
        "event_log_path": str(event_log_path),
        "evidence_log_path": str(evidence_log_path),
        "bundle_count": len(bundles),
        "story_type_counts": story_type_counts,
        "canonical_trades_root": str(canonical_trades_root),
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
    summary_md.write_text(render_summary_markdown(summary_out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(summary_out, ensure_ascii=False))
    else:
        print(f"day={day} bundle_count={len(bundles)} report_json={summary_json} report_md={summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
