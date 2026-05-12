from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.reporting.intraday_trade_reports import (
    finalize_ai_report_diagnostics as _finalize_report_diagnostics,
    normalize_trade_id_filters as _normalize_trade_id_filters,
    resolve_story_input_for_regeneration as _resolve_story_input_for_regeneration,
    sync_ai_report_diagnostics as _sync_report_diagnostics,
    sync_ai_trade_report_generation_state as _sync_report_generation_state,
)
from libs.reporting.llm_artifacts import (
    build_compact_input_artifact,
    build_llm_response_artifact,
    iter_trade_dirs,
    persist_llm_artifact_refs,
    resolve_trade_day_root,
    trade_artifact_paths,
    write_json,
)
from libs.reporting.operator_period_summary import generate_operator_daily_summary_artifact
from libs.reporting.symbol_trade_report import collect_symbols_for_day, generate_symbol_trade_report
from libs.reporting.trade_report_ai import (
    build_ai_trade_report,
    build_deterministic_trade_report,
    build_ai_trade_report_compact_input,
    build_trade_summary_input,
    build_trade_summary_report,
    render_trade_report_markdown,
    render_trade_summary_markdown_with_evaluation,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate ai_trade_report artifacts for one trade day.")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--day", required=True)
    parser.add_argument("--trade-id", action="append", default=[], help="Optional trade_id filter. Repeat the flag to process multiple trades.")
    llm = parser.add_mutually_exclusive_group()
    llm.add_argument("--with-llm", dest="with_llm", action="store_true", help="Opt in to LLM narrative generation during regeneration.")
    llm.add_argument("--no-llm", dest="with_llm", action="store_false", help="Regenerate deterministic artifacts without calling the report LLM. This is the default.")
    parser.set_defaults(with_llm=False)
    parser.add_argument("--model", default="", help="Optional model override.")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--retry-max", type=int, default=None, help="Override trade_report retry count for this run.")
    parser.add_argument("--timeout-sec", type=float, default=None, help="Override provider timeout_sec policy for this run.")
    parser.add_argument("--hard-timeout-sec", type=float, default=None, help="Apply a wall-clock timeout to each trade_report LLM call.")
    parser.add_argument("--local-debug", action="store_true", help="Skip LLM and render deterministic .local_debug artifacts without overwriting canonical report files.")
    parser.add_argument("--skip-operator-summary-refresh", action="store_true", help="Do not refresh reports/operator_summary/daily after canonical regeneration.")
    parser.add_argument("--refresh-all-symbols", action="store_true", help="Refresh every symbol report for the day even when --trade-id narrows regeneration.")
    parser.add_argument("--json", action="store_true")
    return parser


def _resolve_generation_mode(args: argparse.Namespace) -> str:
    if bool(getattr(args, "local_debug", False)):
        return "local_debug"
    if bool(getattr(args, "with_llm", False)):
        return "llm"
    return "deterministic"


def _local_debug_artifact_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.local_debug{path.suffix}")


def _resolve_output_paths(trade_paths: Dict[str, Path], local_debug: bool) -> Dict[str, Path]:
    compact_input_path = trade_paths["ai_trade_report_compact_input_json"]
    report_json_path = trade_paths["ai_trade_report_json"]
    report_md_path = trade_paths["ai_trade_report_md"]
    summary_input_json_path = trade_paths["ai_trade_summary_input_json"]
    summary_json_path = trade_paths["ai_trade_summary_json"]
    summary_md_path = trade_paths["ai_trade_summary_md"]
    summary_llm_path = trade_paths["ai_trade_summary_llm_response_json"]
    llm_path = trade_paths["ai_trade_report_llm_response_json"]
    if not local_debug:
        return {
            "compact_input_path": compact_input_path,
            "report_json_path": report_json_path,
            "report_md_path": report_md_path,
            "summary_input_json_path": summary_input_json_path,
            "summary_json_path": summary_json_path,
            "summary_md_path": summary_md_path,
            "summary_llm_path": summary_llm_path,
            "llm_path": llm_path,
        }
    return {
        "compact_input_path": _local_debug_artifact_path(compact_input_path),
        "report_json_path": _local_debug_artifact_path(report_json_path),
        "report_md_path": _local_debug_artifact_path(report_md_path),
        "summary_input_json_path": _local_debug_artifact_path(summary_input_json_path),
        "summary_json_path": _local_debug_artifact_path(summary_json_path),
        "summary_md_path": _local_debug_artifact_path(summary_md_path),
        "summary_llm_path": _local_debug_artifact_path(summary_llm_path),
        "llm_path": _local_debug_artifact_path(llm_path),
    }


def _classify_missing_story_input(trade_dir: Path, trade_paths: Dict[str, Path]) -> Dict[str, Any]:
    lifecycle_markers = (
        trade_paths["entry_json"],
        trade_paths["exit_json"],
        trade_paths["lifecycle_bundle_json"],
        trade_paths["ai_trade_report_input_json"],
        trade_paths["trade_artifact_links_json"],
    )
    if any(path.exists() for path in lifecycle_markers):
        return {
            "partial_trade_artifact": False,
            "skip_reason": "",
        }

    early_markers = (
        trade_paths["strategist_input_json"],
        trade_paths["strategist_compact_input_json"],
        trade_paths["strategist_evidence_json"],
        trade_paths["scanner_evidence_json"],
        trade_paths["monitor_evidence_json"],
        trade_paths["commander_evidence_json"],
    )
    if any(path.exists() for path in early_markers) or trade_paths["evidence_dir"].exists():
        return {
            "partial_trade_artifact": True,
            "skip_reason": "partial_trade_artifact",
        }

    return {
        "partial_trade_artifact": False,
        "skip_reason": "",
    }


def _mark_partial_trade_artifact(
    trade_paths: Dict[str, Path],
    *,
    day: str,
    trade_id: str,
    skip_reason: str,
) -> None:
    payload = {
        "schema_version": "trade_health.v1",
        "trade_id": str(trade_id or ""),
        "day": str(day or ""),
        "lifecycle_status": "partial",
        "report_generation_status": "skipped",
        "ai_trade_report_status": "skipped",
        "llm_trade_report_status": "skipped",
        "report_generation_reason": "partial trade artifact detected during ai_trade_report batch regeneration",
        "partial_trade_artifact": True,
        "skip_reason": str(skip_reason or "partial_trade_artifact"),
        "artifact_presence": {
            "entry_json": bool(trade_paths["entry_json"].exists()),
            "exit_json": bool(trade_paths["exit_json"].exists()),
            "lifecycle_bundle_json": bool(trade_paths["lifecycle_bundle_json"].exists()),
            "ai_trade_report_input_json": bool(trade_paths["ai_trade_report_input_json"].exists()),
            "strategist_input_json": bool(trade_paths["strategist_input_json"].exists()),
            "evidence_dir": bool(trade_paths["evidence_dir"].exists()),
        },
    }
    write_json(trade_paths["trade_health_json"], payload)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if bool(args.local_debug) and bool(args.with_llm):
        parser.error("--local-debug cannot be combined with --with-llm.")
    load_env_file(str(args.env_path or ".env").strip() or ".env")
    generation_mode = _resolve_generation_mode(args)

    reports_root = Path(str(args.reports_root or "reports")).resolve()
    day = str(args.day or "").strip()
    trade_day_root = resolve_trade_day_root(reports_root, day)
    if not trade_day_root.exists():
        out = {"ok": False, "day": day, "error": "trade_day_root_not_found", "path": str(trade_day_root)}
        print(json.dumps(out, ensure_ascii=False) if bool(args.json) else f"ok=false error=trade_day_root_not_found path={trade_day_root}")
        return 3

    rows: List[Dict[str, Any]] = []
    affected_symbols: set[str] = set()
    trade_dirs = iter_trade_dirs(trade_day_root)
    trade_id_filters = _normalize_trade_id_filters(args.trade_id)
    if trade_id_filters:
        allowed = set(trade_id_filters)
        trade_dirs = [path for path in trade_dirs if path.name in allowed]

    for trade_dir in trade_dirs:
        trade_id = trade_dir.name
        trade_paths = trade_artifact_paths(reports_root, day, trade_id, prefer_existing_day_root=True)
        output_paths = _resolve_output_paths(trade_paths, bool(args.local_debug))
        story_input, story_input_path, story_input_source, story_input_existing_score, story_input_rebuilt_score = (
            _resolve_story_input_for_regeneration(trade_dir, trade_paths)
        )
        if not story_input:
            missing_input_state = _classify_missing_story_input(trade_dir, trade_paths)
            if bool(missing_input_state.get("partial_trade_artifact")):
                _mark_partial_trade_artifact(
                    trade_paths,
                    day=day,
                    trade_id=trade_id,
                    skip_reason=str(missing_input_state.get("skip_reason") or ""),
                )
                rows.append(
                    {
                        "trade_id": trade_id,
                        "ok": True,
                        "status": "skipped_partial_trade_artifact",
                        "story_input_path": "",
                        "story_input_source": "missing",
                        "skip_reason": str(missing_input_state.get("skip_reason") or ""),
                        "error": "ai_trade_report_input_not_found",
                    }
                )
                continue
            rows.append(
                {
                    "trade_id": trade_id,
                    "ok": False,
                    "status": "missing_input",
                    "story_input_path": "",
                    "story_input_source": "missing",
                    "error": "ai_trade_report_input_not_found",
                }
            )
            continue
        symbol_hint = str(story_input.get("symbol") or "").strip().upper()
        if not symbol_hint and isinstance(story_input.get("shared_facts"), dict):
            symbol_hint = str((story_input.get("shared_facts") or {}).get("symbol") or "").strip().upper()
        if symbol_hint:
            affected_symbols.add(symbol_hint)

        compact_input_path = output_paths["compact_input_path"]
        compact_input = build_ai_trade_report_compact_input(story_input)
        compact_artifact = build_compact_input_artifact(
            component="ai_trade_report",
            run_id=str(story_input.get("run_id") or ""),
            trade_id=trade_id,
            story_id=str(story_input.get("story_id") or trade_id),
            day=day,
            source_artifact_path=story_input_path,
            source_input=story_input,
            compact_input=compact_input,
        )
        write_json(compact_input_path, compact_artifact)
        if generation_mode == "llm":
            report = build_ai_trade_report(
                story_input,
                enabled=True,
                model=str(args.model or "").strip() or None,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                retry_max_override=args.retry_max,
                timeout_sec_override=args.timeout_sec,
                hard_timeout_sec_override=args.hard_timeout_sec,
                local_debug_no_llm=False,
            )
        elif generation_mode == "local_debug":
            report = build_ai_trade_report(
                story_input,
                enabled=True,
                model=str(args.model or "").strip() or None,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                retry_max_override=args.retry_max,
                timeout_sec_override=args.timeout_sec,
                hard_timeout_sec_override=args.hard_timeout_sec,
                local_debug_no_llm=True,
            )
        else:
            report = build_deterministic_trade_report(story_input)
            report["llm_response_artifact"] = build_llm_response_artifact(
                component="ai_trade_report",
                run_id=str(story_input.get("run_id") or ""),
                trade_id=trade_id,
                story_id=str(story_input.get("story_id") or trade_id),
                day=day,
                status="fallback",
                attempts=[],
                parsed_output={},
                model_info={"provider": "OpenRouter", "model": ""},
                meta={"reason": "deterministic_no_llm"},
            )
        llm_artifact = report.get("llm_response_artifact") if isinstance(report.get("llm_response_artifact"), dict) else {}
        generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
        diagnostics = {} if bool(args.local_debug) else _sync_report_diagnostics(trade_paths, report, llm_artifact)

        report_json_path = output_paths["report_json_path"]
        report_md_path = output_paths["report_md_path"]
        summary_input_json_path = output_paths["summary_input_json_path"]
        summary_json_path = output_paths["summary_json_path"]
        summary_md_path = output_paths["summary_md_path"]
        summary_llm_path = output_paths["summary_llm_path"]
        llm_path = output_paths["llm_path"]
        llm_response_path = ""
        summary_llm_response_path = ""
        for path in (
            report_json_path,
            report_md_path,
            summary_input_json_path,
            summary_json_path,
            summary_md_path,
            summary_llm_path,
            llm_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report_md_path.write_text(render_trade_report_markdown(report), encoding="utf-8")
        summary_input = build_trade_summary_input(report)
        summary_report = build_trade_summary_report(
            summary_input,
            enabled=generation_mode == "llm",
            model=args.model or None,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            retry_max_override=args.retry_max,
            timeout_sec_override=args.timeout_sec,
            hard_timeout_sec_override=args.hard_timeout_sec,
            local_debug_no_llm=bool(args.local_debug),
        )
        summary_input_json_path.write_text(
            json.dumps(summary_input, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary_json_path.write_text(json.dumps(summary_report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary_md_path.write_text(
            render_trade_summary_markdown_with_evaluation(report, summary_report),
            encoding="utf-8",
        )
        summary_llm_artifact = (
            summary_report.get("llm_response_artifact")
            if isinstance(summary_report.get("llm_response_artifact"), dict)
            else {}
        )
        if summary_llm_artifact:
            summary_llm_compact = persist_llm_artifact_refs(
                artifact=summary_llm_artifact,
                reports_root=reports_root,
                day=day,
                run_id=str(story_input.get("run_id") or ""),
                component="ai_trade_summary",
            )
            write_json(summary_llm_path, summary_llm_compact)
            summary_llm_response_path = str(summary_llm_path)
        if llm_artifact:
            llm_compact = persist_llm_artifact_refs(
                artifact=llm_artifact,
                reports_root=reports_root,
                day=day,
                run_id=str(story_input.get("run_id") or ""),
                component="ai_trade_report",
            )
            write_json(llm_path, llm_compact)
            llm_response_path = str(llm_path)
        if not bool(args.local_debug):
            _sync_report_generation_state(
                trade_paths,
                story_input=story_input,
                compact_input=compact_input,
                report=report,
                llm_artifact=llm_artifact,
                llm_response_path=llm_response_path,
            )
            _finalize_report_diagnostics(trade_paths, report_json_path, diagnostics)

        rows.append(
            {
                "trade_id": trade_id,
                "ok": True,
                "status": str(generation.get("status") or report.get("status") or ""),
                "mode": str(generation.get("mode") or ""),
                "model": str(generation.get("model") or llm_artifact.get("model") or ""),
                "story_input_path": story_input_path,
                "story_input_source": story_input_source,
                "story_input_quality_existing": story_input_existing_score,
                "story_input_quality_rebuilt": story_input_rebuilt_score,
                "ai_trade_report_compact_input_path": str(compact_input_path),
                "ai_trade_report_json_path": str(report_json_path),
                "ai_trade_report_md_path": str(report_md_path),
                "ai_trade_summary_input_json_path": str(summary_input_json_path),
                "ai_trade_summary_json_path": str(summary_json_path),
                "ai_trade_summary_md_path": str(summary_md_path),
                "ai_trade_summary_llm_response_path": summary_llm_response_path,
                "ai_trade_report_llm_response_path": llm_response_path,
                "llm_status": str(llm_artifact.get("status") or ""),
                "llm_parse_mode": str(llm_artifact.get("parse_mode") or ""),
                "llm_completeness_score": float(llm_artifact.get("completeness_score") or 0.0),
                "llm_error": str(llm_artifact.get("error") or ((llm_artifact.get("meta") or {}).get("reason") or "")),
                "diagnostic_report_status": str(diagnostics.get("report_status") or ""),
                "generation_mode_requested": generation_mode,
                "llm_enabled": generation_mode == "llm",
                "local_debug": bool(args.local_debug),
                "preserved_live_outputs": bool(args.local_debug),
            }
        )

    operator_summary_refresh: Dict[str, Any] = {"status": "skipped", "reason": "not_requested"}
    if not bool(args.local_debug) and not bool(getattr(args, "skip_operator_summary_refresh", False)):
        try:
            event_log_path = Path(str(args.event_log_path or "data/logs/events.jsonl").strip())
            refreshed_symbols: List[str] = []
            if trade_id_filters and not bool(getattr(args, "refresh_all_symbols", False)):
                symbols_to_refresh = sorted(affected_symbols)
                refresh_scope = "affected_trade_symbols"
            else:
                symbols_to_refresh = list(collect_symbols_for_day(event_log_path, reports_root, day))
                refresh_scope = "all_day_symbols"
            for symbol in symbols_to_refresh:
                generate_symbol_trade_report(
                    events_path=event_log_path,
                    reports_root=reports_root,
                    symbol=symbol,
                )
                refreshed_symbols.append(symbol)
            daily_md, daily_json, _daily_payload = generate_operator_daily_summary_artifact(
                reports_root=reports_root,
                day=day,
            )
            operator_summary_refresh = {
                "status": "ok",
                "daily_summary_md": str(daily_md),
                "daily_summary_json": str(daily_json),
                "symbol_report_count": len(refreshed_symbols),
                "symbols": refreshed_symbols,
                "refresh_scope": refresh_scope,
            }
        except Exception as exc:
            operator_summary_refresh = {
                "status": "error",
                "error": str(exc),
            }

    out = {
        "ok": True,
        "day": day,
        "trade_count": len(rows),
        "operator_summary_refresh": operator_summary_refresh,
        "rows": rows,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok=true day={day} trade_count={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
