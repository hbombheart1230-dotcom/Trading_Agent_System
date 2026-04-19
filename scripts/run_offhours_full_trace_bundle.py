from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.pipelines.offhours_validation import run_offhours_validation_once
from libs.core.settings import load_env_file
from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.reporter_analysis import generate_reporter_analysis_report
from libs.reporting.trade_explain import generate_trade_explain_report, official_trade_explain_report_dir


def _resolve_path(raw: str, default_rel: str) -> Path:
    s = str(raw or "").strip() or str(default_rel)
    p = Path(s)
    if not p.is_absolute():
        p = ROOT / p
    return p


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_day_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _normalize_symbol(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _print_json_safe(obj: Dict[str, Any]) -> None:
    try:
        print(json.dumps(obj, ensure_ascii=False))
    except UnicodeEncodeError:
        print(json.dumps(obj, ensure_ascii=True))


def _build_initial_state(symbol: str) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "offhours_validation": True,
        "runtime_mode": "offhours_full_trace",
        "exec_context": {"mode": "mock", "offhours_validation": True},
    }
    if symbol:
        state["symbol"] = symbol
    return state


def _enforce_safe_runtime(*, state_path: Path, event_log_path: Path, evidence_log_path: Path) -> None:
    os.environ["EXECUTION_MODE"] = "mock"
    os.environ["ALLOW_REAL_EXECUTION"] = "false"
    os.environ["STATE_STORE_PATH"] = str(state_path)
    os.environ["EVENT_LOG_PATH"] = str(event_log_path)
    os.environ["EVIDENCE_LEDGER_PATH"] = str(evidence_log_path)


def _render_markdown(out: Dict[str, Any]) -> str:
    strategist = out.get("strategist") if isinstance(out.get("strategist"), dict) else {}
    scanner = out.get("scanner") if isinstance(out.get("scanner"), dict) else {}
    monitor = out.get("monitor") if isinstance(out.get("monitor"), dict) else {}
    executor = out.get("executor") if isinstance(out.get("executor"), dict) else {}
    learning = out.get("future_learning") if isinstance(out.get("future_learning"), dict) else {}
    artifacts = out.get("artifacts") if isinstance(out.get("artifacts"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Off-Hours Full Trace Bundle ({out.get('run_id')})")
    lines.append("")
    lines.append(f"- ts: `{out.get('ts')}`")
    lines.append(f"- day: **{out.get('day')}**")
    lines.append(f"- symbol_hint: `{out.get('symbol_hint')}`")
    lines.append(f"- decision: **{out.get('decision')}** reason=`{out.get('decision_reason')}`")
    lines.append("")
    lines.append("## Strategist")
    lines.append(f"- news_source: **{strategist.get('news_source')}**")
    lines.append(f"- news_query_targets: `{json.dumps(strategist.get('news_query_targets') or [], ensure_ascii=False)}`")
    if strategist.get("news_query_reasoning"):
        lines.append(f"- news_query_reasoning: {strategist.get('news_query_reasoning')}")
    lines.append(f"- news_sample_titles: `{json.dumps(strategist.get('news_sample_titles') or [], ensure_ascii=False)}`")
    lines.append(
        f"- global_sentiment: score={strategist.get('global_sentiment_score')} "
        f"status={strategist.get('global_sentiment_status')} source={strategist.get('global_sentiment_source')}"
    )
    if strategist.get("global_index_moves"):
        lines.append(f"- global_index_moves: `{json.dumps(strategist.get('global_index_moves') or {}, ensure_ascii=False)}`")
    if strategist.get("fear_index"):
        lines.append(f"- fear_index: `{json.dumps(strategist.get('fear_index') or {}, ensure_ascii=False)}`")
    if strategist.get("macro_stress_overlay"):
        overlay = strategist.get("macro_stress_overlay") or {}
        lines.append(
            f"- macro_stress: active={bool(overlay.get('active'))} "
            f"flags=`{json.dumps(overlay.get('stress_flags') or [], ensure_ascii=False)}` "
            f"reason=`{overlay.get('reason')}`"
        )
    lines.append(f"- llm_model: `{strategist.get('llm_model')}` ok={strategist.get('llm_ok')}")
    lines.append(f"- themes: `{json.dumps(strategist.get('themes') or [], ensure_ascii=False)}`")
    lines.append(f"- playbook: **{strategist.get('playbook')}**")
    if strategist.get("scanner_source_policy"):
        lines.append(f"- scanner_source_policy: `{json.dumps(strategist.get('scanner_source_policy') or {}, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Scanner")
    lines.append(f"- candidate_source: **{scanner.get('candidate_source')}**")
    lines.append(f"- kiwoom_source_mix: `{json.dumps(scanner.get('kiwoom_source_mix') or {}, ensure_ascii=False)}`")
    if scanner.get("scanner_source_policy"):
        lines.append(f"- scanner_source_policy: `{json.dumps(scanner.get('scanner_source_policy') or {}, ensure_ascii=False)}`")
    lines.append(f"- top_stock: **{scanner.get('top_stock')}** top_score={scanner.get('top_score')}")
    lines.append(f"- selected_candidate: `{json.dumps(scanner.get('selected_candidate') or {}, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Monitor")
    lines.append(
        f"- entry_reason=`{monitor.get('entry_reason')}` exit_reason=`{monitor.get('exit_reason')}` "
        f"monitor_reason=`{monitor.get('monitor_reason')}`"
    )
    lines.append(
        f"- thresholds: `{json.dumps(monitor.get('thresholds') or {}, ensure_ascii=False)}` "
        f"min_hold={monitor.get('min_hold_sec')} cooldown={monitor.get('sell_cooldown_sec')} confirm={monitor.get('exit_confirm_ticks')}"
    )
    lines.append("")
    lines.append("## Execution")
    lines.append(
        f"- action={executor.get('order_action')} symbol={executor.get('order_symbol')} "
        f"qty={executor.get('order_qty')} mode={executor.get('mode')} ok={executor.get('execution_ok')}"
    )
    lines.append(
        f"- execution_mode={executor.get('execution_mode')} kiwoom_mode={executor.get('kiwoom_mode')} "
        f"broker_env={executor.get('broker_env')} effective_mode={executor.get('effective_mode')}"
    )
    lines.append("")
    lines.append("## Reporter")
    lines.append(f"- improvement_suggestions: `{json.dumps(learning.get('improvement_suggestions') or [], ensure_ascii=False)}`")
    lines.append(f"- next_learning_focus: `{json.dumps(learning.get('report_focus_targets') or [], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Artifacts")
    for key, value in artifacts.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one off-hours validation cycle and emit a full trace bundle.")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--state-path", default="data/state/offhours_full_trace.json")
    p.add_argument("--event-log-path", default="data/logs/dev/analysis/offhours/offhours_full_trace.jsonl")
    p.add_argument("--evidence-log-path", default="data/evidence_ledger/offhours_full_trace.jsonl")
    p.add_argument("--report-dir", default="reports/dev/analysis/offhours_full_trace")
    p.add_argument("--reports-root", default=None)
    p.add_argument("--intents-path", default="data/logs/intents.jsonl")
    p.add_argument("--symbol", default=os.getenv("SYMBOL", "").strip())
    p.add_argument("--ai-review", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    env_path = _resolve_path(str(args.env_path), ".env")
    state_path = _resolve_path(str(args.state_path), "data/state/offhours_full_trace.json")
    event_log_path = _resolve_path(str(args.event_log_path), "data/logs/dev/analysis/offhours/offhours_full_trace.jsonl")
    evidence_log_path = _resolve_path(str(args.evidence_log_path), "data/evidence_ledger/offhours_full_trace.jsonl")
    report_root = _resolve_path(str(args.report_dir), "reports/dev/analysis/offhours_full_trace")
    reports_root = _resolve_path(str(args.reports_root), str(report_root)) if args.reports_root else report_root
    intents_path = _resolve_path(str(args.intents_path), "data/logs/intents.jsonl")
    symbol = _normalize_symbol(args.symbol)

    report_root.mkdir(parents=True, exist_ok=True)
    load_env_file(str(env_path))
    _enforce_safe_runtime(
        state_path=state_path,
        event_log_path=event_log_path,
        evidence_log_path=evidence_log_path,
    )

    state = run_offhours_validation_once(_build_initial_state(symbol))
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        print(json.dumps({"ok": False, "error": "run_id_missing_after_offhours_validation"}, ensure_ascii=False))
        return 3

    day = _utc_day_now()

    trace_md, trace_js, trace_out = generate_agent_pipeline_trace_report(
        event_log_path=event_log_path,
        evidence_log_path=evidence_log_path,
        report_dir=reports_root / "agent_pipeline_trace",
        run_id=run_id,
        day=day,
        reports_root=reports_root,
    )
    trade_md, trade_js, trade_out = generate_trade_explain_report(
        event_log_path=event_log_path,
        report_dir=official_trade_explain_report_dir(reports_root),
        day=day,
    )
    reporter_md, reporter_js, reporter_out = generate_reporter_analysis_report(
        event_log_path=event_log_path,
        report_dir=reports_root / "reporter_analysis",
        day=day,
        intents_path=intents_path if intents_path.exists() else None,
        reports_root=reports_root,
        ai_review_enabled=True if bool(args.ai_review) else False,
    )

    learning = {
        "improvement_suggestions": list(reporter_out.get("improvement_suggestions") or []),
        "report_focus_targets": list(reporter_out.get("report_focus_targets") or []),
        "incident_total": (
            int(((reporter_out.get("incident_postmortem") or {}).get("incident_total")) or 0)
            if isinstance(reporter_out.get("incident_postmortem"), dict)
            else 0
        ),
    }

    out: Dict[str, Any] = {
        "schema_version": "offhours_full_trace_bundle.v1",
        "ok": True,
        "ts": _utc_now_iso(),
        "day": day,
        "run_id": run_id,
        "symbol_hint": symbol,
        "decision": str(state.get("decision") or ""),
        "decision_reason": str(state.get("decision_reason") or ""),
        "strategist": dict(trace_out.get("strategist") or {}),
        "scanner": dict(trace_out.get("scanner") or {}),
        "monitor": dict(trace_out.get("monitor") or {}),
        "supervisor": dict(trace_out.get("supervisor") or {}),
        "executor": dict(trace_out.get("executor") or {}),
        "reporter": {
            "reporter_analysis_found": bool((trace_out.get("reporter") or {}).get("reporter_analysis_found")),
            "reporter_analysis_day_file_found": bool((trace_out.get("reporter") or {}).get("reporter_analysis_day_file_found")),
        },
        "future_learning": learning,
        "artifacts": {
            "event_log_path": str(event_log_path),
            "evidence_log_path": str(evidence_log_path),
            "state_path": str(state_path),
            "agent_pipeline_trace_json": str(trace_js),
            "agent_pipeline_trace_md": str(trace_md),
            "trade_explain_json": str(trade_js),
            "trade_explain_md": str(trade_md),
            "reporter_analysis_json": str(reporter_js),
            "reporter_analysis_md": str(reporter_md),
        },
        "trade_explain_execution_summary": dict(trade_out.get("execution_summary") or {}),
    }

    safe_run = "".join(ch for ch in run_id if ch.isalnum() or ch in ("_", "-"))[:40] or "run"
    json_path = report_root / f"offhours_full_trace_{safe_run}.json"
    md_path = report_root / f"offhours_full_trace_{safe_run}.md"
    out["report_json_path"] = str(json_path)
    out["report_md_path"] = str(md_path)
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(out), encoding="utf-8")

    if bool(args.json):
        _print_json_safe(out)
    else:
        print(
            f"run_id={run_id} decision={out.get('decision')} "
            f"report_json={json_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
