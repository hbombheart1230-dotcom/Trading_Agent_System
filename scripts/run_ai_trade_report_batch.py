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
    persist_llm_artifact_refs,
    trade_artifact_paths,
    write_json,
)
from libs.reporting.trade_report_ai import (
    build_ai_trade_report,
    build_ai_trade_report_compact_input,
    render_trade_report_markdown,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate ai_trade_report artifacts for one trade day.")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--day", required=True)
    parser.add_argument("--trade-id", action="append", default=[], help="Optional trade_id filter. Repeat the flag to process multiple trades.")
    parser.add_argument("--model", default="", help="Optional model override.")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--retry-max", type=int, default=None, help="Override trade_report retry count for this run.")
    parser.add_argument("--timeout-sec", type=float, default=None, help="Override provider timeout_sec policy for this run.")
    parser.add_argument("--hard-timeout-sec", type=float, default=None, help="Apply a wall-clock timeout to each trade_report LLM call.")
    parser.add_argument("--local-debug", action="store_true", help="Skip LLM and render deterministic local-debug report from saved artifacts only.")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    load_env_file(str(args.env_path or ".env").strip() or ".env")

    reports_root = Path(str(args.reports_root or "reports")).resolve()
    day = str(args.day or "").strip()
    trade_day_root = reports_root / "trades" / day
    if not trade_day_root.exists():
        out = {"ok": False, "day": day, "error": "trade_day_root_not_found", "path": str(trade_day_root)}
        print(json.dumps(out, ensure_ascii=False) if bool(args.json) else f"ok=false error=trade_day_root_not_found path={trade_day_root}")
        return 3

    rows: List[Dict[str, Any]] = []
    trade_dirs = sorted(path for path in trade_day_root.iterdir() if path.is_dir())
    trade_id_filters = _normalize_trade_id_filters(args.trade_id)
    if trade_id_filters:
        allowed = set(trade_id_filters)
        trade_dirs = [path for path in trade_dirs if path.name in allowed]

    for trade_dir in trade_dirs:
        trade_id = trade_dir.name
        trade_paths = trade_artifact_paths(reports_root, day, trade_id)
        story_input, story_input_path, story_input_source, story_input_existing_score, story_input_rebuilt_score = (
            _resolve_story_input_for_regeneration(trade_dir, trade_paths)
        )
        if not story_input:
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

        compact_input_path = trade_paths["ai_trade_report_compact_input_json"]
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
        report = build_ai_trade_report(
            story_input,
            enabled=True,
            model=str(args.model or "").strip() or None,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            retry_max_override=args.retry_max,
            timeout_sec_override=args.timeout_sec,
            hard_timeout_sec_override=args.hard_timeout_sec,
            local_debug_no_llm=bool(args.local_debug),
        )
        llm_artifact = report.get("llm_response_artifact") if isinstance(report.get("llm_response_artifact"), dict) else {}
        generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
        diagnostics = _sync_report_diagnostics(trade_paths, report, llm_artifact)

        report_json_path = trade_paths["ai_trade_report_json"]
        report_md_path = trade_paths["ai_trade_report_md"]
        llm_path = trade_paths["ai_trade_report_llm_response_json"]
        llm_response_path = ""
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report_md_path.write_text(render_trade_report_markdown(report), encoding="utf-8")
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
                "ai_trade_report_llm_response_path": llm_response_path,
                "llm_status": str(llm_artifact.get("status") or ""),
                "llm_parse_mode": str(llm_artifact.get("parse_mode") or ""),
                "llm_completeness_score": float(llm_artifact.get("completeness_score") or 0.0),
                "llm_error": str(llm_artifact.get("error") or ((llm_artifact.get("meta") or {}).get("reason") or "")),
                "diagnostic_report_status": str(diagnostics.get("report_status") or ""),
                "local_debug": bool(args.local_debug),
            }
        )

    out = {
        "ok": True,
        "day": day,
        "trade_count": len(rows),
        "rows": rows,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok=true day={day} trade_count={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
