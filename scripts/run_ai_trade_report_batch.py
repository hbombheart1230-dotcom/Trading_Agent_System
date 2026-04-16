from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
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
from libs.reporting.trade_story_pipeline import build_trade_story_input_from_bundle


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


def _stable_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_fingerprint(payload: Any) -> str:
    return hashlib.sha256(_stable_json_text(payload).encode("utf-8")).hexdigest()


def _report_generation_state_path(trade_paths: Dict[str, Path]) -> Path:
    return trade_paths["reports_dir"] / "report_generation_state.json"


def _load_report_generation_state(path: Path) -> Dict[str, Any]:
    payload = _read_json(path)
    if payload:
        payload.setdefault("schema_version", "report_generation_state.v1")
        payload.setdefault("components", {})
        return payload
    return {"schema_version": "report_generation_state.v1", "components": {}}


def _sync_report_generation_state(
    trade_paths: Dict[str, Path],
    *,
    story_input: Dict[str, Any],
    compact_input: Dict[str, Any],
    report: Dict[str, Any],
    llm_artifact: Dict[str, Any],
    llm_response_path: str,
) -> Dict[str, Any]:
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    state_path = _report_generation_state_path(trade_paths)
    state_payload = _load_report_generation_state(state_path)
    components = state_payload.get("components") if isinstance(state_payload.get("components"), dict) else {}
    generation_status = str(
        generation.get("status")
        or report.get("ai_trade_report_status")
        or report.get("status")
        or llm_artifact.get("status")
        or ""
    ).strip()
    model = str(
        generation.get("model")
        or llm_artifact.get("model")
        or ((llm_artifact.get("model_info") or {}) if isinstance(llm_artifact.get("model_info"), dict) else {}).get("model")
        or ""
    )
    report_reason = str(generation.get("reason") or llm_artifact.get("error") or ((llm_artifact.get("meta") or {}) if isinstance(llm_artifact.get("meta"), dict) else {}).get("reason") or "").strip()
    source_inputs = {
        "story_input_sha256": _payload_fingerprint(story_input),
        "compact_input_sha256": _payload_fingerprint(compact_input),
    }
    components["ai_trade_report"] = {
        "fingerprint": _payload_fingerprint(
            {
                "component": "ai_trade_report",
                "trade_id": str(story_input.get("trade_id") or ""),
                "run_id": str(story_input.get("run_id") or ""),
                **source_inputs,
            }
        ),
        "component": "ai_trade_report",
        "status": generation_status,
        "report_status": "available" if trade_paths["ai_trade_report_json"].exists() else "missing",
        "skip_reason": "",
        "trade_id": str(story_input.get("trade_id") or ""),
        "run_id": str(story_input.get("run_id") or ""),
        "updated_at": _utc_now_iso(),
        "model": model,
        "report_json_path": str(trade_paths["ai_trade_report_json"]),
        "report_md_path": str(trade_paths["ai_trade_report_md"]),
        "llm_response_path": str(llm_response_path or ""),
        "source_inputs": source_inputs,
    }
    state_payload["components"] = components
    write_json(state_path, state_payload)
    return state_payload


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


def _normalize_trade_id_filters(values: Any) -> List[str]:
    raw_values: List[str] = []
    if isinstance(values, list):
        raw_values = [str(value or "") for value in values]
    elif values not in (None, ""):
        raw_values = [str(values or "")]
    out: List[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in str(raw or "").split(","):
            trade_id = str(part or "").strip()
            if not trade_id or trade_id in seen:
                continue
            out.append(trade_id)
            seen.add(trade_id)
    return out


def _load_story_input(trade_dir: Path) -> tuple[Dict[str, Any], str]:
    canonical = trade_dir / "ai_trade_report_input.json"
    normalized_legacy = trade_dir / "ai_trade_report" / "ai_trade_report_input.json"
    legacy = trade_dir / "trade_story_input.json"
    for path in (canonical, normalized_legacy, legacy):
        payload = _read_json(path)
        if payload:
            return payload, str(path)
    return {}, ""


def _story_input_quality_score(story_input: Dict[str, Any]) -> int:
    if not isinstance(story_input, dict) or not story_input:
        return 0
    score = 0
    if str(story_input.get("status") or "").strip().lower() in {"open", "closed"}:
        score += 2
    if str(story_input.get("symbol") or "").strip():
        score += 1
    if str(story_input.get("run_id") or "").strip():
        score += 1
    scanner_reason_human = (
        story_input.get("scanner_reason_human")
        if isinstance(story_input.get("scanner_reason_human"), dict)
        else {}
    )
    scanner_trace = (
        story_input.get("scanner_selection_trace")
        if isinstance(story_input.get("scanner_selection_trace"), dict)
        else {}
    )
    selected_symbol = str(
        story_input.get("selected_symbol")
        or scanner_reason_human.get("selected_symbol")
        or scanner_trace.get("selected_symbol")
        or ""
    ).strip()
    if selected_symbol:
        score += 2
    candidate_count = (
        story_input.get("candidate_count")
        if story_input.get("candidate_count") not in (None, "")
        else scanner_reason_human.get("candidate_count")
    )
    if isinstance(candidate_count, (int, float)) and float(candidate_count) > 0:
        score += 1
    if isinstance(scanner_trace.get("ranked_candidates"), list) and len(scanner_trace.get("ranked_candidates") or []) > 0:
        score += 1
    if isinstance(story_input.get("monitor_stop_policy_trace"), dict) and story_input.get("monitor_stop_policy_trace"):
        score += 1
    if str(story_input.get("entry_summary") or "").strip():
        score += 1
    return score


def _resolve_story_input_for_regeneration(
    trade_dir: Path,
    trade_paths: Dict[str, Path],
) -> tuple[Dict[str, Any], str, str, int, int]:
    existing_story_input, existing_path = _load_story_input(trade_dir)
    existing_score = _story_input_quality_score(existing_story_input)
    lifecycle_bundle = _read_json(trade_paths["lifecycle_bundle_json"])
    if not lifecycle_bundle:
        return existing_story_input, existing_path, "existing_story_input", existing_score, existing_score

    rebuilt_story_input = build_trade_story_input_from_bundle(
        lifecycle_bundle,
        existing_story_input=existing_story_input,
    )
    rebuilt_score = _story_input_quality_score(rebuilt_story_input)
    if rebuilt_score >= existing_score and rebuilt_story_input:
        canonical_path = trade_paths["ai_trade_report_input_json"]
        if _payload_fingerprint(rebuilt_story_input) != _payload_fingerprint(existing_story_input):
            write_json(canonical_path, rebuilt_story_input)
        return (
            rebuilt_story_input,
            str(canonical_path),
            "rebuilt_from_lifecycle_bundle",
            existing_score,
            rebuilt_score,
        )
    return existing_story_input, existing_path, "existing_story_input", existing_score, rebuilt_score


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
        trade_paths["lifecycle_bundle_json"],
        trade_paths["ai_trade_report_input_json"],
        trade_paths["trade_health_json"],
    ):
        payload = _read_json(path)
        if not payload:
            continue
        payload["ai_report_diagnostics"] = dict(diagnostics)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return diagnostics


def _finalize_report_diagnostics(
    trade_paths: Dict[str, Path],
    report_json_path: Path,
    diagnostics: Dict[str, Any],
) -> None:
    for path in (
        report_json_path,
        trade_paths["lifecycle_bundle_json"],
        trade_paths["ai_trade_report_input_json"],
        trade_paths["trade_health_json"],
    ):
        payload = _read_json(path)
        if not payload:
            continue
        payload["ai_report_diagnostics"] = dict(diagnostics)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
