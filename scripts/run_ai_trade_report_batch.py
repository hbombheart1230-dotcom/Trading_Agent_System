from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.reporting.llm_artifacts import build_compact_input_artifact, trade_artifact_paths, write_json
from libs.reporting.trade_report_ai import build_ai_trade_report, build_ai_trade_report_compact_input, render_trade_report_markdown


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate ai_trade_report artifacts for one trade day.")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--day", required=True)
    parser.add_argument("--trade-id", default="", help="Optional single trade_id filter.")
    parser.add_argument("--model", default="", help="Optional model override.")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _load_story_input(trade_dir: Path) -> tuple[Dict[str, Any], str]:
    canonical = trade_dir / "ai_trade_report" / "ai_trade_report_input.json"
    legacy = trade_dir / "trade_story_input.json"
    for path in (canonical, legacy):
        payload = _read_json(path)
        if payload:
            return payload, str(path)
    return {}, ""


def _report_diagnostics_from_report(report: Dict[str, Any], llm_artifact: Dict[str, Any]) -> Dict[str, Any]:
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    generation_status = str(generation.get("status") or llm_artifact.get("status") or "").strip().lower()
    model = str(generation.get("model") or llm_artifact.get("model") or ((llm_artifact.get("model_info") or {}).get("model")) or "")
    diagnostics = {
        "report_status": "failed",
        "report_reason_code": "llm_generation_failed",
        "report_reason_human": "AI trade report generation failed.",
        "generation_attempted": True,
        "generation_ts": _utc_now_iso(),
        "story_input_available": True,
        "report_output_available": True,
        "report_artifact_available": True,
        "llm_model_used": model,
        "last_error_message": str(llm_artifact.get("error") or ""),
        "next_expected_step": "Inspect the LLM response artifact and retry generation.",
    }
    if generation_status in {"ok", "repaired"}:
        diagnostics.update(
            {
                "report_status": "available",
                "report_reason_code": "",
                "report_reason_human": "AI trade report was generated successfully.",
                "next_expected_step": "Open the full report for detailed lifecycle analysis.",
                "last_error_message": "",
            }
        )
    elif generation_status in {"partial", "salvaged"}:
        diagnostics.update(
            {
                "report_status": "available",
                "report_reason_code": "llm_generation_salvaged",
                "report_reason_human": "AI trade report was generated with partial recovery.",
                "next_expected_step": "Open the report and review completeness metadata before relying on every section.",
            }
        )
    return diagnostics


def _sync_report_diagnostics(trade_paths: Dict[str, Path], report: Dict[str, Any], llm_artifact: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = _report_diagnostics_from_report(report, llm_artifact)
    report["ai_report_diagnostics"] = dict(diagnostics)

    for path in (
        trade_paths["trade_lifecycle_json"],
        trade_paths["aggregated_execution_bundle_json"],
        trade_paths["ai_trade_report_input_json"],
    ):
        payload = _read_json(path)
        if not payload:
            continue
        payload["ai_report_diagnostics"] = dict(diagnostics)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return diagnostics


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
    if str(args.trade_id or "").strip():
        trade_dirs = [path for path in trade_dirs if path.name == str(args.trade_id or "").strip()]

    for trade_dir in trade_dirs:
        trade_id = trade_dir.name
        story_input, story_input_path = _load_story_input(trade_dir)
        if not story_input:
            rows.append(
                {
                    "trade_id": trade_id,
                    "ok": False,
                    "status": "missing_input",
                    "story_input_path": "",
                    "error": "ai_trade_report_input_not_found",
                }
            )
            continue

        trade_paths = trade_artifact_paths(reports_root, day, trade_id)
        compact_input = build_ai_trade_report_compact_input(story_input)
        compact_input_path = trade_paths["ai_trade_report_compact_input_json"]
        write_json(
            compact_input_path,
            build_compact_input_artifact(
                component="ai_trade_report",
                run_id=str(story_input.get("run_id") or ""),
                trade_id=trade_id,
                story_id=str(story_input.get("story_id") or trade_id),
                day=day,
                source_artifact_path=story_input_path,
                source_input=story_input,
                compact_input=compact_input,
            ),
        )
        report = build_ai_trade_report(
            story_input,
            enabled=True,
            model=str(args.model or "").strip() or None,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        llm_artifact = report.get("llm_response_artifact") if isinstance(report.get("llm_response_artifact"), dict) else {}
        generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
        diagnostics = _sync_report_diagnostics(trade_paths, report, llm_artifact)

        report_json_path = trade_paths["ai_trade_report_json"]
        report_md_path = trade_paths["ai_trade_report_md"]
        llm_path = trade_paths["ai_trade_report_llm_response_json"]
        report_json_path.parent.mkdir(parents=True, exist_ok=True)
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report_md_path.write_text(render_trade_report_markdown(report), encoding="utf-8")
        if llm_artifact:
            write_json(llm_path, llm_artifact)

        rows.append(
            {
                "trade_id": trade_id,
                "ok": True,
                "status": str(generation.get("status") or report.get("status") or ""),
                "mode": str(generation.get("mode") or ""),
                "model": str(generation.get("model") or llm_artifact.get("model") or ""),
                "story_input_path": story_input_path,
                "ai_trade_report_compact_input_path": str(compact_input_path),
                "ai_trade_report_json_path": str(report_json_path),
                "ai_trade_report_md_path": str(report_md_path),
                "ai_trade_report_llm_response_path": str(llm_path) if llm_artifact else "",
                "llm_status": str(llm_artifact.get("status") or ""),
                "llm_parse_mode": str(llm_artifact.get("parse_mode") or ""),
                "llm_completeness_score": float(llm_artifact.get("completeness_score") or 0.0),
                "llm_error": str(llm_artifact.get("error") or ((llm_artifact.get("meta") or {}).get("reason") or "")),
                "diagnostic_report_status": str(diagnostics.get("report_status") or ""),
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
