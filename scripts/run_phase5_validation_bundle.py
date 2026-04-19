from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.llm_artifacts import symbol_artifact_paths
from libs.reporting.operator_visibility import generate_decision_story_report
from libs.reporting.operator_visibility import generate_operator_daily_summary
from libs.reporting.operator_visibility import generate_run_card_report
from libs.reporting.symbol_trade_report import collect_symbols_for_day
from libs.reporting.symbol_trade_report import generate_symbol_trade_report
from libs.reporting.trade_explain import (
    generate_trade_explain_report,
    official_trade_explain_report_dir,
)
from scripts.check_reports_trades_health import audit_reports_trades_health
from scripts.generate_daily_report import generate_daily_report


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_day_key(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    text = str(ts).strip()
    if not text:
        return None
    try:
        epoch = int(float(text))
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def _resolve_day(event_log_path: Path, requested_day: Optional[str]) -> str:
    if requested_day:
        return str(requested_day).strip()
    days = sorted({d for row in _iter_events(event_log_path) if (d := _to_day_key(row.get("ts") or row.get("ts_kst")))} )
    if days:
        return days[-1]
    return date.today().isoformat()


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _pick_latest_canonical_run_id(reports_root: Path, day: str) -> str:
    base = reports_root / "canonical" / day
    if not base.exists():
        return ""
    candidates = [path for path in base.iterdir() if path.is_dir()]
    if not candidates:
        return ""
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return latest.name


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_bundle_markdown(payload: Dict[str, Any], *, repo_root: Path) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    trade_health = artifacts.get("trade_health") if isinstance(artifacts.get("trade_health"), dict) else {}
    symbol_reports = artifacts.get("symbol_reports") if isinstance(artifacts.get("symbol_reports"), list) else []
    latest_runs = artifacts.get("latest_canonical_runs") if isinstance(artifacts.get("latest_canonical_runs"), list) else []
    policy_surface = (
        artifacts.get("policy_surface_quality")
        if isinstance(artifacts.get("policy_surface_quality"), dict)
        else {}
    )
    policy_surface_summary = (
        policy_surface.get("summary")
        if isinstance(policy_surface.get("summary"), dict)
        else {}
    )
    policy_surface_exec = (
        policy_surface.get("executive_summary")
        if isinstance(policy_surface.get("executive_summary"), dict)
        else {}
    )
    policy_surface_source = (
        policy_surface.get("source")
        if isinstance(policy_surface.get("source"), dict)
        else {}
    )
    chart_structure_guard = (
        artifacts.get("chart_structure_decision_hint")
        if isinstance(artifacts.get("chart_structure_decision_hint"), dict)
        else {}
    )
    chart_structure_guard_summary = (
        chart_structure_guard.get("summary")
        if isinstance(chart_structure_guard.get("summary"), dict)
        else {}
    )
    chart_structure_guard_exec = (
        chart_structure_guard.get("executive_summary")
        if isinstance(chart_structure_guard.get("executive_summary"), dict)
        else {}
    )
    chart_structure_guard_source = (
        chart_structure_guard.get("source")
        if isinstance(chart_structure_guard.get("source"), dict)
        else {}
    )
    chart_structure_guard_examples = (
        chart_structure_guard_summary.get("applied_examples")
        if isinstance(chart_structure_guard_summary.get("applied_examples"), list)
        else []
    )

    lines: List[str] = [
        f"# Phase 5 Validation Bundle ({payload.get('day')})",
        "",
        "## Summary",
        "",
        f"- daily_report_generated: **{bool(summary.get('daily_report_generated'))}**",
        f"- operator_daily_summary_generated: **{bool(summary.get('operator_daily_summary_generated'))}**",
        f"- trade_health_ok: **{bool(summary.get('trade_health_ok'))}**",
        f"- symbol_report_count: **{int(summary.get('symbol_report_count') or 0)}**",
        f"- latest_canonical_run_id: `{summary.get('latest_canonical_run_id') or ''}`",
        "",
        "## Daily Surfaces",
        "",
    ]

    daily = artifacts.get("daily_report") if isinstance(artifacts.get("daily_report"), dict) else {}
    operator = artifacts.get("operator_daily_summary") if isinstance(artifacts.get("operator_daily_summary"), dict) else {}
    lines += [
        f"- daily_report_json: `{daily.get('json_path') or ''}`",
        f"- daily_report_md: `{daily.get('md_path') or ''}`",
        f"- operator_daily_summary_json: `{operator.get('json_path') or ''}`",
        f"- operator_daily_summary_md: `{operator.get('md_path') or ''}`",
        "",
        "## Policy Surface Executive Summary",
        "",
        f"- status: **{str(policy_surface_exec.get('status') or 'unknown').upper()}**",
        f"- headline: {str(policy_surface_exec.get('headline') or 'Policy surface unknown')}",
        "",
        "## Policy Surface Quality",
        "",
        f"- schema_available_rate: **{float(policy_surface_summary.get('schema_available_rate') or 0.0):.4f}**",
        f"- normalized_policy_rate: **{float(policy_surface_summary.get('normalized_policy_rate') or 0.0):.4f}**",
        f"- invalid_spec_rate: **{float(policy_surface_summary.get('invalid_spec_rate') or 0.0):.4f}**",
        f"- total_invalid_specs: **{int(policy_surface_summary.get('total_invalid_specs') or 0)}**",
        f"- run_count: **{int(policy_surface_source.get('run_count') or 0)}**",
        f"- source: `{policy_surface_source.get('source') or ''}`",
        "",
        "## Chart Structure Decision Hint Executive Summary",
        "",
        f"- status: **{str(chart_structure_guard_exec.get('status') or 'unknown').upper()}**",
        f"- headline: {str(chart_structure_guard_exec.get('headline') or 'Chart structure guard unknown')}",
        "",
        "## Chart Structure Decision Hint",
        "",
        f"- available_run_count: **{int(chart_structure_guard_summary.get('available_run_count') or 0)}**",
        f"- applied_count: **{int(chart_structure_guard_summary.get('applied_count') or 0)}**",
        f"- applied_rate: **{float(chart_structure_guard_summary.get('applied_rate') or 0.0):.4f}**",
        f"- top_blocking_features: `{json.dumps(chart_structure_guard_summary.get('top_blocking_features') or [], ensure_ascii=False)}`",
        f"- source: `{chart_structure_guard_source.get('source') or ''}`",
        "",
        "## Trade / Report Health",
        "",
        f"- trade_dir_count: **{int(trade_health.get('trade_dir_count') or 0)}**",
        f"- severity_counts: `{json.dumps(trade_health.get('severity_counts') or {}, ensure_ascii=False)}`",
        f"- issue_counts: `{json.dumps(trade_health.get('issue_counts') or {}, ensure_ascii=False)}`",
        "",
        "## Symbol Reports",
        "",
    ]
    if chart_structure_guard_examples:
        lines += ["## Chart Structure Decision Hint Applied Examples", ""]
        for example in chart_structure_guard_examples[:3]:
            if not isinstance(example, dict):
                continue
            lines.append(
                f"- `{example.get('run_id') or '-'}` "
                f"[{str(example.get('entry_style') or '-').upper()}] "
                f"{example.get('reason_transition') or '-'} "
                f"blockers=`{json.dumps(example.get('blocking_features') or [], ensure_ascii=False)}`"
            )
        lines.append("")
    if symbol_reports:
        for row in symbol_reports:
            lines.append(
                f"- `{row.get('symbol')}`: json=`{row.get('json_path')}` md=`{row.get('md_path')}`"
            )
    else:
        lines.append("- (none)")

    decision_story = artifacts.get("decision_story") if isinstance(artifacts.get("decision_story"), dict) else {}
    run_cards = artifacts.get("run_cards") if isinstance(artifacts.get("run_cards"), dict) else {}
    trade_explain = artifacts.get("trade_explain") if isinstance(artifacts.get("trade_explain"), dict) else {}
    pipeline_trace = artifacts.get("pipeline_trace") if isinstance(artifacts.get("pipeline_trace"), dict) else {}
    lines += [
        "",
        "## Inspection Reports",
        "",
        f"- decision_story_md: `{decision_story.get('md_path') or ''}`",
        f"- run_cards_md: `{run_cards.get('md_path') or ''}`",
        f"- trade_explain_json: `{trade_explain.get('json_path') or ''}`",
        f"- trade_explain_md: `{trade_explain.get('md_path') or ''}`",
        f"- pipeline_trace_json: `{pipeline_trace.get('json_path') or ''}`",
        f"- pipeline_trace_md: `{pipeline_trace.get('md_path') or ''}`",
        "",
        "## Latest Canonical Runs",
        "",
    ]
    if latest_runs:
        for row in latest_runs:
            lines.append(
                f"- `{row.get('run_id')}`: commander=`{row.get('commander_json_path')}` monitor=`{row.get('monitor_json_path')}`"
            )
    else:
        lines.append("- (none)")

    issues = trade_health.get("issues") if isinstance(trade_health.get("issues"), list) else []
    lines += ["", "## Top Issues", ""]
    if issues:
        for issue in issues[:10]:
            lines.append(
                f"- [{issue.get('severity')}] `{issue.get('trade_id')}` `{issue.get('component')}` `{issue.get('code')}` - {issue.get('message')}"
            )
            lines.append(f"  path: `{issue.get('path')}`")
    else:
        lines.append("- (none)")

    lines += [
        "",
        "## Notes",
        "",
        "- This bundle is deterministic/read-only. It does not change runtime behavior.",
        "- It is intended to make report quality, schema linkage, and artifact paths easy to inspect by eye.",
        f"- repo_root: `{_safe_rel(repo_root, repo_root) or '.'}`",
        "",
    ]
    return "\n".join(lines)


def generate_phase5_validation_bundle(
    *,
    event_log_path: Path,
    reports_root: Path,
    output_dir: Path,
    day: Optional[str] = None,
    max_runs: int = 120,
    max_executions: int = 120,
    max_news_titles: int = 5,
) -> Tuple[Path, Path, Dict[str, Any]]:
    day = _resolve_day(event_log_path, day)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_md, daily_json = generate_daily_report(event_log_path, reports_root, day=day)
    daily_payload = _read_json(daily_json)
    operator_md, operator_json = generate_operator_daily_summary(event_log_path, reports_root, day=day)
    manual_dir = reports_root / "dev" / "manual"
    decision_story_md, decision_story = generate_decision_story_report(
        event_log_path, manual_dir / "decision_story", day=day, max_runs=max_runs, trade_only=True
    )
    run_cards_md, run_cards = generate_run_card_report(
        event_log_path, manual_dir / "run_cards", day=day, max_runs=max_runs, trade_only=True
    )
    trade_explain_md, trade_explain_json, trade_explain = generate_trade_explain_report(
        event_log_path,
        official_trade_explain_report_dir(reports_root),
        day=day,
        max_executions=max_executions,
        max_sell_pairs=max_executions,
    )
    health = audit_reports_trades_health(reports_root, day=day)

    symbols = collect_symbols_for_day(event_log_path, reports_root, day)
    symbol_rows: List[Dict[str, Any]] = []
    for symbol in symbols:
        generate_symbol_trade_report(event_log_path, reports_root, symbol)
        paths = symbol_artifact_paths(reports_root, symbol)
        symbol_rows.append(
            {
                "symbol": symbol,
                "json_path": str(paths["symbol_trade_report_json"]),
                "md_path": str(paths["symbol_trade_report_md"]),
                "history_json_path": str(paths["trade_history_json"]),
                "latest_snapshot_json_path": str(paths["latest_snapshot_json"]),
            }
        )

    latest_run_id = _pick_latest_canonical_run_id(reports_root, day)
    pipeline_trace_row: Dict[str, Any] = {
        "available": False,
        "run_id": latest_run_id,
        "json_path": "",
        "md_path": "",
    }
    if latest_run_id:
        trace_md, trace_json, trace_out = generate_agent_pipeline_trace_report(
            event_log_path=event_log_path,
            evidence_log_path=ROOT / "data" / "evidence_ledger" / "events.jsonl",
            report_dir=reports_root / "dev" / "analysis" / "agent_pipeline_trace",
            run_id=latest_run_id,
            day=day,
            reports_root=reports_root,
            max_news_titles=max_news_titles,
        )
        pipeline_trace_row = {
            "available": True,
            "run_id": latest_run_id,
            "json_path": str(trace_json),
            "md_path": str(trace_md),
            "summary": str((trace_out or {}).get("summary") or ""),
        }

    canonical_dir = reports_root / "canonical" / day
    latest_canonical_rows: List[Dict[str, Any]] = []
    if canonical_dir.exists():
        for path in sorted((p for p in canonical_dir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            latest_canonical_rows.append(
                {
                    "run_id": path.name,
                    "commander_json_path": str(path / "commander.json"),
                    "monitor_json_path": str(path / "monitor.json"),
                }
            )

    out: Dict[str, Any] = {
        "schema_version": "phase5_validation_bundle.v1",
        "day": day,
        "reports_root": str(reports_root),
        "summary": {
            "daily_report_generated": True,
            "operator_daily_summary_generated": True,
            "trade_health_ok": bool(health.get("ok")),
            "symbol_report_count": len(symbol_rows),
            "latest_canonical_run_id": latest_run_id,
        },
        "artifacts": {
            "daily_report": {
                "json_path": str(daily_json),
                "md_path": str(daily_md),
            },
            "policy_surface_quality": {
                "summary": (
                    dict(daily_payload.get("policy_surface_quality_summary") or {})
                    if isinstance(daily_payload.get("policy_surface_quality_summary"), dict)
                    else {}
                ),
                "executive_summary": (
                    dict(daily_payload.get("policy_surface_quality_executive_summary") or {})
                    if isinstance(daily_payload.get("policy_surface_quality_executive_summary"), dict)
                    else {}
                ),
                "source": (
                    dict(daily_payload.get("chart_structure_decision_hint_source") or {})
                    if isinstance(daily_payload.get("chart_structure_decision_hint_source"), dict)
                    else {"run_count": 0, "date": day, "source": "daily_monitor_artifacts"}
                ),
            },
            "chart_structure_decision_hint": {
                "summary": (
                    dict(daily_payload.get("chart_structure_decision_hint_summary") or {})
                    if isinstance(daily_payload.get("chart_structure_decision_hint_summary"), dict)
                    else {}
                ),
                "executive_summary": (
                    dict(daily_payload.get("chart_structure_decision_hint_executive_summary") or {})
                    if isinstance(daily_payload.get("chart_structure_decision_hint_executive_summary"), dict)
                    else {}
                ),
                "source": (
                    dict(daily_payload.get("policy_surface_quality_source") or {})
                    if isinstance(daily_payload.get("policy_surface_quality_source"), dict)
                    else {"run_count": 0, "date": day, "source": "daily_monitor_artifacts"}
                ),
            },
            "operator_daily_summary": {
                "json_path": str(operator_json),
                "md_path": str(operator_md),
            },
            "trade_health": health,
            "decision_story": {
                "md_path": str(decision_story_md),
                "story_total": int((decision_story or {}).get("story_total") or 0),
            },
            "run_cards": {
                "md_path": str(run_cards_md),
                "card_total": int((run_cards or {}).get("card_total") or 0),
            },
            "trade_explain": {
                "json_path": str(trade_explain_json),
                "md_path": str(trade_explain_md),
                "executions_total": int((((trade_explain or {}).get("execution_summary") or {}).get("executions_total")) or 0),
                "sell_pairs_total": int((((trade_explain or {}).get("execution_summary") or {}).get("sell_pairs_total")) or 0),
            },
            "pipeline_trace": pipeline_trace_row,
            "symbol_reports": symbol_rows,
            "latest_canonical_runs": latest_canonical_rows,
        },
    }

    json_path = output_dir / f"phase5_validation_bundle_{day}.json"
    md_path = output_dir / f"phase5_validation_bundle_{day}.md"
    _write_json(json_path, out)
    md_path.write_text(_render_bundle_markdown(out, repo_root=ROOT), encoding="utf-8")
    return md_path, json_path, out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a read-only validation bundle for phase 5 reporting/policy artifacts."
    )
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="reports/dev/analysis/phase5_validation")
    parser.add_argument("--day", default=None)
    parser.add_argument("--max-runs", type=int, default=120)
    parser.add_argument("--max-executions", type=int, default=120)
    parser.add_argument("--max-news-titles", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    md_path, json_path, out = generate_phase5_validation_bundle(
        event_log_path=Path(str(args.event_log_path).strip()),
        reports_root=Path(str(args.reports_root).strip()),
        output_dir=Path(str(args.output_dir).strip()),
        day=str(args.day).strip() if args.day else None,
        max_runs=max(1, int(args.max_runs)),
        max_executions=max(1, int(args.max_executions)),
        max_news_titles=max(1, int(args.max_news_titles)),
    )
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        summary = out.get("summary") if isinstance(out.get("summary"), dict) else {}
        print(
            f"day={out.get('day')} trade_health_ok={bool(summary.get('trade_health_ok'))} "
            f"symbol_report_count={int(summary.get('symbol_report_count') or 0)} "
            f"report_json={json_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
