from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.core.symbols import normalize_symbol
from libs.llm.model_names import normalize_openrouter_model_name
from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.reporter_analysis import generate_reporter_analysis_report
from libs.reporting.llm_artifacts import (
    build_compact_input_artifact,
    build_llm_response_artifact,
    canonical_llm_status,
    daily_artifact_paths,
    persist_llm_artifact_refs,
    split_prompt_text,
    trade_artifact_paths,
    write_json,
    write_text,
)
from libs.reporting.trade_explain import generate_trade_explain_report
from libs.reporting.trade_report_ai import (
    build_ai_trade_report,
    build_ai_trade_report_compact_input,
    build_deterministic_trade_report,
    render_trade_report_markdown,
)
from libs.reporting.trade_story_pipeline import (
    build_commander_evidence,
    build_execution_outcome_human,
    build_filters_human,
    build_lifecycle_bundle,
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
    compute_evidence_completeness,
    classify_story_type as _classify_story_type,
    collect_story_warnings,
    execution_mode_label,
    render_bundle_markdown,
    render_summary_markdown,
    safe_int,
    utc_now_iso,
)
from libs.runtime.canonical_artifacts import load_run_canonical_artifacts


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_model_name(model: Any) -> str:
    return normalize_openrouter_model_name(model)


def _sanitize_error_message(value: Any, *, max_len: int = 260) -> str:
    text = str(value or "").strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _is_placeholder_entry_reason(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {
        "",
        "no_position",
        "entry reasoning was not captured.",
        "entry reasoning was not captured",
        "-",
        "n/a",
    }


def _report_reason_human(code: str) -> str:
    mapping = {
        "no_executed_lifecycle": "No executed trade lifecycle was created for this run.",
        "decision_only_run": "This run was decision-only, so a full AI trade report was not generated.",
        "hold_only_run": "This run only updated hold/monitor state, so a full AI trade report was not generated.",
        "execution_failed": "Execution did not complete successfully, so a full AI trade report was skipped.",
        "missing_story_input": "Trade story input was not created, so report generation could not continue.",
        "llm_generation_failed": "Trade story input existed, but AI report generation failed.",
        "artifact_write_failed": "AI report generation ran, but writing report artifacts failed.",
        "missing_report_linkage": "A linked AI trade report could not be found for this run.",
        "report_not_requested": "AI trade report generation was not requested for this run.",
        "still_open_lifecycle": "This trade lifecycle is still open, so the full AI report is pending.",
        "awaiting_exit_for_full_report": "This trade is still open. The full AI report is generated after exit/closure.",
    }
    return mapping.get(str(code or "").strip().lower(), "AI report diagnostics are not fully classified.")


def _report_next_step(code: str) -> str:
    mapping = {
        "no_executed_lifecycle": "Continue with Operator Brief. Generate full AI report only for executed lifecycles.",
        "decision_only_run": "Continue with Operator Brief. Generate full AI report after executed lifecycle events.",
        "hold_only_run": "Continue monitoring. Generate full AI report after entry/exit execution is formed.",
        "execution_failed": "Review execution failure details and rerun report generation after stabilization.",
        "missing_story_input": "Fix trade story input generation first, then retry.",
        "llm_generation_failed": "Check OpenRouter/model connectivity and retry report generation.",
        "artifact_write_failed": "Check filesystem write path and permissions, then retry.",
        "missing_report_linkage": "Regenerate lifecycle/report linkage for this run and retry.",
        "report_not_requested": "Enable AI report generation policy and rerun.",
        "still_open_lifecycle": "Generate the full AI report after lifecycle exit/closure.",
        "awaiting_exit_for_full_report": "Generate the final AI report after exit/closure.",
    }
    return mapping.get(str(code or "").strip().lower(), "Review diagnostics and continue with Operator Brief.")


def _base_diagnostics(model_hint: str) -> Dict[str, Any]:
    return {
        "report_status": "pending",
        "report_reason_code": "",
        "report_reason_human": "",
        "report_generation_reason": "",
        "generation_attempted": False,
        "generation_ts": "",
        "story_input_available": False,
        "report_output_available": False,
        "report_artifact_available": False,
        "llm_provider": "OpenRouter",
        "llm_model_used": _normalize_model_name(model_hint) or "openrouter/free",
        "expected_generation_mode": "per-trade free model report",
        "last_error_message": "",
        "next_expected_step": "",
        "deterministic_report_status": "skipped",
        "llm_brief_status": "skipped",
        "ai_trade_report_status": "skipped",
    }


def _write_legacy_json(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _write_legacy_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return str(path)


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _latest_strategist_evidence_ledger_row(
    evidence_rows: List[Dict[str, Any]],
    strategist_run_ids: List[str],
) -> Dict[str, Any]:
    run_set = {str(item or "").strip() for item in list(strategist_run_ids or []) if str(item or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for row in list(evidence_rows or []):
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        if str(row.get("agent") or "").strip().lower() != "strategist":
            continue
        if str(row.get("stage") or "").strip() not in {"theme_selection", "theme_selection_repair"}:
            continue
        if not any(
            (
                bool(str(row.get("llm_prompt") or "").strip()),
                bool(str(row.get("llm_response") or "").strip()),
                isinstance(row.get("parsed_output"), dict) and bool(row.get("parsed_output")),
            )
        ):
            continue
        candidates.append(row)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: _to_epoch(item.get("timestamp") or item.get("ts")) or 0)
    return dict(candidates[-1])


def _latest_strategist_input_collection_row(
    evidence_rows: List[Dict[str, Any]],
    strategist_run_ids: List[str],
) -> Dict[str, Any]:
    run_set = {str(item or "").strip() for item in list(strategist_run_ids or []) if str(item or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for row in list(evidence_rows or []):
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        if str(row.get("agent") or "").strip().lower() != "strategist":
            continue
        raw_input = row.get("raw_input")
        if not isinstance(raw_input, dict) or not raw_input:
            continue
        if str(row.get("stage") or "").strip() != "theme_selection":
            continue
        decision_link = row.get("decision_link") if isinstance(row.get("decision_link"), dict) else {}
        if str(decision_link.get("stage") or "").strip() != "strategist_input_collection" and "llm_payload" not in raw_input:
            continue
        candidates.append(row)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: _to_epoch(item.get("timestamp") or item.get("ts")) or 0)
    return dict(candidates[-1])


def _latest_strategist_prompt_input_row(
    evidence_rows: List[Dict[str, Any]],
    strategist_run_ids: List[str],
) -> Dict[str, Any]:
    run_set = {str(item or "").strip() for item in list(strategist_run_ids or []) if str(item or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for row in list(evidence_rows or []):
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        if str(row.get("agent") or "").strip().lower() != "strategist":
            continue
        if str(row.get("stage") or "").strip() != "theme_selection":
            continue
        if not isinstance(row.get("raw_input"), dict) or not dict(row.get("raw_input") or {}):
            continue
        if not str(row.get("llm_prompt") or "").strip():
            continue
        candidates.append(row)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: _to_epoch(item.get("timestamp") or item.get("ts")) or 0)
    return dict(candidates[-1])


def _flatten_news_titles(sample: Any, *, max_groups: int = 3, max_titles_per_group: int = 2) -> List[str]:
    out: List[str] = []
    if not isinstance(sample, dict):
        return out

    def _extract_title(row: Any) -> str:
        if isinstance(row, dict):
            return html.unescape(str(row.get("title") or "").strip())
        text = str(row or "").strip()
        if not text:
            return ""
        for pattern in (r"title='([^']+)'", r'title="([^"]+)"'):
            match = re.search(pattern, text)
            if match:
                return html.unescape(str(match.group(1) or "").strip())
        return html.unescape(text[:160])

    for symbol, rows in list(sample.items())[:max_groups]:
        items = rows
        if isinstance(rows, dict):
            items = rows.get("sample")
        if not isinstance(items, list):
            continue
        for row in items[:max_titles_per_group]:
            title = _extract_title(row)
            if not title:
                continue
            out.append(f"{symbol}: {title}")
    return out


def _build_strategist_input_summary(
    source_input: Dict[str, Any],
    compact_input: Dict[str, Any],
) -> Dict[str, Any]:
    src = source_input if isinstance(source_input, dict) else {}
    compact = compact_input if isinstance(compact_input, dict) else {}
    global_signal = src.get("global_sentiment_signal") if isinstance(src.get("global_sentiment_signal"), dict) else {}
    if not global_signal and isinstance(compact.get("global_sentiment_signal"), dict):
        global_signal = dict(compact.get("global_sentiment_signal") or {})
    news_ctx = src.get("news_context") if isinstance(src.get("news_context"), dict) else {}
    if not news_ctx and isinstance(compact.get("news_context"), dict):
        news_ctx = dict(compact.get("news_context") or {})
    macro_moves = global_signal.get("macro_moves") if isinstance(global_signal.get("macro_moves"), dict) else {}
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    macro_stress = src.get("macro_stress_overlay_hint") if isinstance(src.get("macro_stress_overlay_hint"), dict) else {}
    if not macro_stress and isinstance(compact.get("macro_stress_overlay_hint"), dict):
        macro_stress = dict(compact.get("macro_stress_overlay_hint") or {})
    market_news_sample = src.get("market_news_sample") if isinstance(src.get("market_news_sample"), dict) else {}
    candidate_news_sample = src.get("candidate_news_sample") if isinstance(src.get("candidate_news_sample"), dict) else {}
    if not market_news_sample and isinstance(compact.get("market_news_sample"), dict):
        market_news_sample = dict(compact.get("market_news_sample") or {})
    if not candidate_news_sample and isinstance(compact.get("candidate_news_sample"), dict):
        candidate_news_sample = dict(compact.get("candidate_news_sample") or {})
    return {
        "global_sentiment_score": _safe_float(global_signal.get("score"), None),
        "vix_level": _safe_float(fear_index.get("level"), _safe_float(macro_moves.get("vix_level"), None)),
        "vix_change_pct": _safe_float(fear_index.get("change_pct"), _safe_float(macro_moves.get("vix_pct"), None)),
        "vix_level_pressure": _safe_float(fear_index.get("level_pressure"), _safe_float(macro_moves.get("vix_level_pressure"), None)),
        "headline_count": safe_int(news_ctx.get("headline_count"), 0),
        "candidate_signal_total": safe_int(news_ctx.get("candidate_signal_total"), 0),
        "market_signal_total": safe_int(news_ctx.get("market_signal_total"), 0),
        "news_query_targets": [str(x or "") for x in list(src.get("news_query_targets") or compact.get("news_query_targets") or []) if str(x or "").strip()][:8],
        "candidate_symbols_hint": [str(x or "") for x in list(src.get("candidate_symbols_hint") or compact.get("candidate_symbols_hint") or []) if str(x or "").strip()][:6],
        "themes_hint": [str(x or "") for x in list(src.get("themes_hint") or compact.get("themes_hint") or []) if str(x or "").strip()][:6],
        "key_events_hint": [str(x or "") for x in list(src.get("key_events_hint") or compact.get("key_events_hint") or []) if str(x or "").strip()][:6],
        "macro_stress_active": bool(macro_stress.get("active")),
        "macro_stress_flags": [str(x or "") for x in list(macro_stress.get("stress_flags") or []) if str(x or "").strip()][:6],
        "market_news_titles": _flatten_news_titles(market_news_sample),
        "candidate_news_titles": _flatten_news_titles(candidate_news_sample),
    }


def _enrich_strategist_from_input_summary(
    strategist_payload: Dict[str, Any],
    strategist_input_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(strategist_payload or {})
    summary = strategist_input_artifact.get("summary") if isinstance(strategist_input_artifact.get("summary"), dict) else {}
    if not summary:
        return out
    out["input_summary"] = dict(summary)
    if out.get("global_sentiment_score") in (None, ""):
        out["global_sentiment_score"] = summary.get("global_sentiment_score")

    fear_index = out.get("fear_index") if isinstance(out.get("fear_index"), dict) else {}
    if not fear_index and summary.get("vix_level") not in (None, ""):
        fear_index = {
            "level": summary.get("vix_level"),
            "change_pct": summary.get("vix_change_pct"),
            "level_pressure": summary.get("vix_level_pressure"),
        }
    out["fear_index"] = dict(fear_index or {})

    macro_moves = out.get("global_macro_moves") if isinstance(out.get("global_macro_moves"), dict) else {}
    if summary.get("vix_level") not in (None, "") and macro_moves.get("vix_level") in (None, ""):
        macro_moves["vix_level"] = summary.get("vix_level")
    if summary.get("vix_change_pct") not in (None, "") and macro_moves.get("vix_pct") in (None, ""):
        macro_moves["vix_pct"] = summary.get("vix_change_pct")
    if summary.get("vix_level_pressure") not in (None, "") and macro_moves.get("vix_level_pressure") in (None, ""):
        macro_moves["vix_level_pressure"] = summary.get("vix_level_pressure")
    out["global_macro_moves"] = dict(macro_moves or {})

    news_context = out.get("news_context") if isinstance(out.get("news_context"), dict) else {}
    if summary.get("headline_count") not in (None, "") and news_context.get("headline_count") in (None, ""):
        news_context["headline_count"] = summary.get("headline_count")
    if summary.get("candidate_signal_total") not in (None, "") and news_context.get("candidate_signal_total") in (None, ""):
        news_context["candidate_signal_total"] = summary.get("candidate_signal_total")
    if summary.get("market_signal_total") not in (None, "") and news_context.get("market_signal_total") in (None, ""):
        news_context["market_signal_total"] = summary.get("market_signal_total")
    out["news_context"] = dict(news_context or {})

    if safe_int(out.get("market_news_total_headlines"), 0) <= 0:
        out["market_news_total_headlines"] = safe_int(summary.get("headline_count"), 0)
    if safe_int(out.get("market_news_query_count"), 0) <= 0:
        out["market_news_query_count"] = len(list(summary.get("news_query_targets") or []))
    if not list(out.get("news_query_targets") or []):
        out["news_query_targets"] = [str(x or "") for x in list(summary.get("news_query_targets") or []) if str(x or "").strip()]
    return out


def _enrich_scanner_reason_from_evidence(
    scanner_reason_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(scanner_reason_human or {})
    selected_symbol = normalize_symbol(
        out.get("selected_symbol") or "",
        allow_test_symbols=True,
    )
    selection_rows = [
        dict(row)
        for row in list((scanner_evidence or {}).get("candidate_selection_reasons") or [])
        if isinstance(row, dict)
    ]
    payload = (
        selection_rows[0].get("payload")
        if selection_rows and isinstance(selection_rows[0].get("payload"), dict)
        else {}
    )
    if not isinstance(payload, dict):
        payload = {}

    why_selected = [str(x or "") for x in list(payload.get("why_selected") or []) if str(x or "").strip()][:4]
    selection_basis = str(payload.get("final_decision_basis") or "").strip()
    tie_break_rule = str(payload.get("tie_break_rule") or "").strip()
    runner_ups_lost: List[Dict[str, Any]] = []
    for row in list(payload.get("runner_ups_lost") or payload.get("runner_up_reasons") or []):
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol") or "", allow_test_symbols=True)
        why_lost = [
            str(x or "")
            for x in list(row.get("why_lost") or row.get("lost_because") or [])
            if str(x or "").strip()
        ][:4]
        if not symbol and not why_lost:
            continue
        runner_ups_lost.append(
            {
                "symbol": symbol,
                "why_lost": why_lost,
                "summary": "; ".join(why_lost),
            }
        )
        if len(runner_ups_lost) >= 3:
            break

    coverage = _normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    if coverage:
        out["feature_coverage"] = dict(coverage)
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        if present > 0 and total > 0:
            top_reasons = [str(x or "") for x in list(out.get("top_reasons") or []) if str(x or "").strip()]
            replaced_top_reason = False
            for idx, reason in enumerate(top_reasons):
                if reason.lower().startswith("chart feature coverage "):
                    top_reasons[idx] = f"chart feature coverage {present}/{total}"
                    replaced_top_reason = True
                    break
            if not replaced_top_reason:
                top_reasons.append(f"chart feature coverage {present}/{total}")
            out["top_reasons"] = top_reasons[:6]

            bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
            updated_bullets: List[str] = []
            replaced_chart_bullet = False
            for bullet in bullets:
                if bullet.lower().startswith("chart / feature coverage:"):
                    updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                    replaced_chart_bullet = True
                else:
                    updated_bullets.append(bullet)
            if not replaced_chart_bullet:
                updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
            out["bullets"] = updated_bullets[:12]

    if why_selected:
        out["why_selected"] = why_selected
    if selection_basis:
        out["selection_basis"] = selection_basis
    if tie_break_rule:
        out["tie_break_rule"] = tie_break_rule
    if runner_ups_lost:
        out["runner_ups_lost"] = runner_ups_lost

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    if why_selected:
        selection_text = "Selection decision: " + "; ".join(why_selected)
        if selection_text not in bullets:
            bullets.append(selection_text)
    if selection_basis:
        basis_text = f"Final decision basis: {selection_basis}"
        if basis_text not in bullets:
            bullets.append(basis_text)
    if tie_break_rule:
        tie_text = f"Tie-break rule: {tie_break_rule}"
        if tie_text not in bullets:
            bullets.append(tie_text)
    if runner_ups_lost:
        runner_text = "Runner-ups lost because: " + "; ".join(
            f"{row.get('symbol')}: {row.get('summary')}" for row in runner_ups_lost if row.get("symbol")
        )
        if runner_text not in bullets:
            bullets.append(runner_text)
    if bullets:
        out["bullets"] = bullets[:12]
    return out


def _normalized_feature_coverage_from_scanner_evidence(
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = normalize_symbol(selected_symbol or "", allow_test_symbols=True)
    if not symbol:
        return {}
    ranking_sources: List[Dict[str, Any]] = []
    for row in list((scanner_evidence or {}).get("candidate_ranking_tables") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("rows") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
    for row in list((scanner_evidence or {}).get("selection_outputs") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("ranking_top_n") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
        selected_candidate = payload.get("selected_candidate") if isinstance(payload.get("selected_candidate"), dict) else {}
        if selected_candidate:
            ranking_sources.append(selected_candidate)

    matched_row: Dict[str, Any] = {}
    for row in ranking_sources:
        row_symbol = normalize_symbol(row.get("symbol") or "", allow_test_symbols=True)
        if row_symbol == symbol:
            matched_row = row
            break
    if not matched_row:
        return {}

    snapshot = matched_row.get("compact_feature_snapshot") if isinstance(matched_row.get("compact_feature_snapshot"), dict) else {}
    if not snapshot:
        snapshot = matched_row.get("feature_snapshot") if isinstance(matched_row.get("feature_snapshot"), dict) else {}
    if not snapshot:
        return {}

    keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    present_keys = [key for key in keys if snapshot.get(key) is not None]
    missing_keys = [key for key in keys if snapshot.get(key) is None]
    total = len(keys)
    present = len(present_keys)
    coverage_ratio = float(present) / float(total) if total else 0.0
    if coverage_ratio >= 0.75:
        quality = "strong"
    elif coverage_ratio >= 0.5:
        quality = "partial"
    else:
        quality = "weak"
    return {
        "present": present,
        "total": total,
        "coverage_ratio": coverage_ratio,
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
    }


def _enrich_filters_from_evidence(
    filters_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    out = dict(filters_human or {})
    coverage = _normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    if not coverage:
        return out

    present = safe_int(coverage.get("present"), 0)
    total = safe_int(coverage.get("total"), 0)
    ratio = _safe_float(coverage.get("coverage_ratio"), 0.0) or 0.0
    if total <= 0:
        chart_status = "NOT_AVAILABLE"
        chart_note = "feature snapshot not available"
    elif ratio >= 0.75:
        chart_status = "PASS"
        chart_note = f"{present}/{total} captured chart features"
    elif ratio >= 0.5:
        chart_status = "PARTIAL"
        chart_note = f"{present}/{total} captured chart features"
    else:
        chart_status = "FAIL"
        chart_note = f"{present}/{total} captured chart features"

    summary = str(out.get("summary") or "").strip()
    if summary:
        summary = re.sub(
            r"Chart completeness was [^.]*(?:\.)?",
            f"Chart completeness was {str(coverage.get('quality') or chart_status.lower()).lower()} with {present}/{total} captured features.",
            summary,
            flags=re.IGNORECASE,
        )
    else:
        summary = f"Scanner and guard checks were captured. Chart completeness was {str(coverage.get('quality') or chart_status.lower()).lower()} with {present}/{total} captured features."
    out["summary"] = summary

    checks = [dict(x) for x in list(out.get("checks") or []) if isinstance(x, dict)]
    updated_checks: List[Dict[str, Any]] = []
    replaced_check = False
    for check in checks:
        if str(check.get("name") or "").strip().lower() == "chart completeness filter":
            check["status"] = chart_status
            check["detail"] = chart_note
            replaced_check = True
        updated_checks.append(check)
    if not replaced_check:
        updated_checks.append(
            {
                "name": "chart completeness filter",
                "status": chart_status,
                "detail": chart_note,
            }
        )
    if updated_checks:
        out["checks"] = updated_checks

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    updated_bullets: List[str] = []
    replaced = False
    for bullet in bullets:
        if bullet.lower().startswith("chart completeness filter:"):
            updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
            replaced = True
        else:
            updated_bullets.append(bullet)
    if not replaced:
        updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
    out["bullets"] = updated_bullets[:8]
    out["feature_coverage"] = dict(coverage)
    return out


def _attach_strategy_anchor(
    payload: Dict[str, Any] | None,
    *,
    strategy_anchor_run_id: str,
    strategist_input_path: Path,
    strategist_compact_input_path: Path,
    strategist_llm_response_path: Path,
) -> Dict[str, Any]:
    out = dict(payload or {})
    out["entry_strategist_run_id"] = str(strategy_anchor_run_id or "")
    out["strategy_anchor_run_id"] = str(strategy_anchor_run_id or "")
    out["strategy_anchor"] = {
        "run_id": str(strategy_anchor_run_id or ""),
        "artifacts": {
            # Linkage stores the normalized expected artifact path even when the
            # file is not present yet. Existence is tracked separately in health.
            "strategist_input_json": str(strategist_input_path),
            "strategist_compact_input_json": str(strategist_compact_input_path),
            "strategist_llm_response_json": str(strategist_llm_response_path),
        },
    }
    return out


def _build_strategist_input_artifacts(
    bundle_out: Dict[str, Any],
    *,
    day: str,
    trade_id: str,
    strategist_evidence: Dict[str, Any] | None = None,
    evidence_rows: List[Dict[str, Any]] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    strategist = bundle_out.get("strategist") if isinstance(bundle_out.get("strategist"), dict) else {}
    strategist_evidence = strategist_evidence if isinstance(strategist_evidence, dict) else {}
    strategist_run_ids = list(strategist_evidence.get("run_ids") or [])
    input_row = _latest_strategist_input_collection_row(list(evidence_rows or []), strategist_run_ids)
    prompt_row = _latest_strategist_prompt_input_row(list(evidence_rows or []), strategist_run_ids)

    source_input: Dict[str, Any] = {}
    raw_input = input_row.get("raw_input") if isinstance(input_row.get("raw_input"), dict) else {}
    if isinstance(raw_input.get("llm_payload"), dict) and dict(raw_input.get("llm_payload") or {}):
        source_input = dict(raw_input.get("llm_payload") or {})
    elif raw_input:
        source_input = dict(raw_input)

    compact_input = prompt_row.get("raw_input") if isinstance(prompt_row.get("raw_input"), dict) else {}
    if not compact_input and isinstance(strategist.get("llm_payload"), dict):
        compact_input = dict(strategist.get("llm_payload") or {})
    if not source_input and isinstance(strategist.get("llm_payload"), dict):
        source_input = dict(strategist.get("llm_payload") or {})
    if not source_input and compact_input:
        source_input = dict(compact_input)

    prompt_text = str(prompt_row.get("llm_prompt") or "")
    system_prompt, user_prompt = split_prompt_text(prompt_text)
    source_run_id = str(
        prompt_row.get("run_id")
        or input_row.get("run_id")
        or (strategist_run_ids[0] if strategist_run_ids else "")
        or bundle_out.get("run_id")
        or ""
    ).strip()

    source_stage = str(prompt_row.get("stage") or input_row.get("stage") or "").strip()
    reconstructed = bool(source_input or compact_input or system_prompt or user_prompt)
    input_artifact = {
        "schema_version": "strategist_input_artifact.v1",
        "component": "strategist",
        "role": "strategist",
        "run_id": str(bundle_out.get("run_id") or ""),
        "trade_id": str(trade_id or ""),
        "story_id": str(trade_id or ""),
        "day": str(day or ""),
        "saved_at": utc_now_iso(),
        "status": "ok" if bool(source_input or compact_input) else "placeholder",
        "summary": _build_strategist_input_summary(source_input, compact_input),
        "source_input": source_input if isinstance(source_input, dict) else {},
        "meta": {
            "source_run_id": source_run_id,
            "source_stage": source_stage,
            "reconstructed_from_evidence_ledger": reconstructed,
            "system_prompt_available": bool(system_prompt),
            "user_prompt_available": bool(user_prompt),
        },
    }
    if system_prompt:
        input_artifact["system_prompt"] = system_prompt
    if user_prompt:
        input_artifact["user_prompt"] = user_prompt

    compact_artifact = build_compact_input_artifact(
        component="strategist",
        run_id=str(bundle_out.get("run_id") or ""),
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        source_artifact_path="",
        source_input=source_input if isinstance(source_input, dict) else {},
        compact_input=compact_input if isinstance(compact_input, dict) else {},
    )
    compact_artifact["meta"] = {
        "source_run_id": source_run_id,
        "source_stage": source_stage,
        "reconstructed_from_evidence_ledger": reconstructed,
    }
    return input_artifact, compact_artifact


def _build_strategist_llm_response_artifact(
    bundle_out: Dict[str, Any],
    *,
    day: str,
    trade_id: str,
    strategist_evidence: Dict[str, Any] | None = None,
    evidence_rows: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    strategist = bundle_out.get("strategist") if isinstance(bundle_out.get("strategist"), dict) else {}
    strategist_evidence = strategist_evidence if isinstance(strategist_evidence, dict) else {}
    evidence_row = _latest_strategist_evidence_ledger_row(
        list(evidence_rows or []),
        list(strategist_evidence.get("run_ids") or []),
    )
    llm_saved = _latest_event_payload(list(strategist_evidence.get("llm_response_saved") or []))
    llm_prompt = strategist.get("llm_prompt") or evidence_row.get("llm_prompt") or ""
    system_prompt, user_prompt = split_prompt_text(llm_prompt)
    has_direct_strategist_llm_fields = any(
        (
            bool(str(strategist.get("llm_prompt") or "").strip()),
            bool(str(strategist.get("llm_response") or "").strip()),
            bool(str(strategist.get("llm_error") or "").strip()),
        )
    )
    parsed_output = strategist.get("llm_parsed_output") if isinstance(strategist.get("llm_parsed_output"), dict) else {}
    if (not has_direct_strategist_llm_fields or not parsed_output) and isinstance(evidence_row.get("parsed_output"), dict):
        parsed_output = dict(evidence_row.get("parsed_output") or {})
    if not parsed_output and isinstance(llm_saved.get("parsed_output"), dict):
        parsed_output = dict(llm_saved.get("parsed_output") or {})
    raw_response = str(strategist.get("llm_response") or evidence_row.get("llm_response") or "")
    llm_error = str(strategist.get("llm_error") or "")
    if not llm_error:
        llm_error = str(llm_saved.get("blocked_reason") or llm_saved.get("error") or "")
    llm_ok = strategist.get("llm_ok")
    saved_status = str(llm_saved.get("status") or "").strip().lower()
    if saved_status and (not has_direct_strategist_llm_fields or "llm_ok" not in strategist):
        llm_ok = saved_status == "ok"
    elif evidence_row and not has_direct_strategist_llm_fields:
        llm_ok = bool(raw_response or parsed_output) and not str(raw_response).startswith("ERROR:")
    elif llm_ok is None and evidence_row:
        llm_ok = bool(raw_response or parsed_output) and not str(raw_response).startswith("ERROR:")
    llm_model = str(strategist.get("llm_model") or llm_saved.get("model") or "")
    llm_provider = str(strategist.get("llm_provider") or llm_saved.get("provider") or "OpenRouter")
    llm_latency_ms = int(strategist.get("llm_latency_ms") or 0)
    llm_attempts = safe_int(llm_saved.get("attempts"), 1)
    has_linked_llm_evidence = any(
        (
            bool(system_prompt),
            bool(user_prompt),
            bool(raw_response),
            bool(parsed_output),
            bool(llm_model),
            bool(llm_provider),
            bool(llm_latency_ms),
            llm_ok is not None,
            bool(llm_error),
        )
    )
    source_run_id = str(evidence_row.get("run_id") or "")
    bundle_run_id = str(bundle_out.get("run_id") or "")
    reconstructed_from_evidence = bool(evidence_row and not has_direct_strategist_llm_fields)
    source_run_mismatch = bool(source_run_id and bundle_run_id and source_run_id != bundle_run_id)
    source_run_suspect = "strategist-llm-test" in source_run_id.lower()
    original_status = "ok" if bool(llm_ok) else "fallback"
    if raw_response.startswith("ERROR:"):
        original_status = "error"
    if reconstructed_from_evidence and source_run_suspect and original_status == "ok":
        original_status = "salvaged"
        if not llm_error:
            llm_error = "reconstructed_source_mismatch"
    attempts = []
    if has_linked_llm_evidence:
        attempts.append(
            {
                "step": "primary",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_response_text": raw_response,
                "parsed_output": parsed_output,
                "model_info": {
                    "provider": llm_provider,
                    "model": llm_model,
                },
                "latency_ms": llm_latency_ms,
                "status": original_status,
                "error": llm_error,
            }
        )
    meta: Dict[str, Any] = {}
    if not has_linked_llm_evidence:
        meta = {
            "synthetic_placeholder": True,
            "reason_code": "no_linked_strategist_llm_evidence",
            "reason": "No linked strategist LLM evidence was available for this trade bundle.",
            "evidence_available": False,
        }
    elif evidence_row:
        meta["reconstructed_from_evidence_ledger"] = reconstructed_from_evidence
        meta["source_run_id"] = source_run_id
        meta["source_stage"] = str(evidence_row.get("stage") or "")
        if source_run_mismatch:
            meta["source_run_mismatch"] = True
            meta["expected_run_id"] = bundle_run_id
        if source_run_suspect:
            meta["source_run_suspect"] = True
            meta["source_quality"] = "reconstructed_untrusted_source"
    return build_llm_response_artifact(
        component="strategist",
        run_id=str(bundle_out.get("run_id") or ""),
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        status=original_status if has_linked_llm_evidence else "fallback",
        attempts=attempts,
        parsed_output=parsed_output,
        model_info={
            "provider": llm_provider,
            "model": llm_model,
        },
        latency_ms=llm_latency_ms,
        meta=meta,
    )


def _seed_diagnostics_for_policy(
    *,
    lifecycle_status: str,
    story_type: str,
    report_requested: bool,
    story_input_available: bool,
    model_hint: str,
) -> Tuple[Dict[str, Any], bool]:
    diagnostics = _base_diagnostics(model_hint)
    diagnostics["story_input_available"] = bool(story_input_available)
    status = str(lifecycle_status or "").strip().lower()
    story = str(story_type or "").strip().lower()

    if not story_input_available:
        diagnostics["report_status"] = "failed"
        diagnostics["report_reason_code"] = "missing_story_input"
        diagnostics["report_reason_human"] = _report_reason_human("missing_story_input")
        diagnostics["next_expected_step"] = _report_next_step("missing_story_input")
        return diagnostics, False

    if not report_requested:
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "report_not_requested"
        diagnostics["report_reason_human"] = _report_reason_human("report_not_requested")
        diagnostics["next_expected_step"] = _report_next_step("report_not_requested")
        return diagnostics, False

    if story == "decision_only":
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "decision_only_run"
        diagnostics["report_reason_human"] = _report_reason_human("decision_only_run")
        diagnostics["next_expected_step"] = _report_next_step("decision_only_run")
        return diagnostics, False

    if story == "failed_execution":
        diagnostics["report_status"] = "skipped"
        diagnostics["report_reason_code"] = "execution_failed"
        diagnostics["report_reason_human"] = _report_reason_human("execution_failed")
        diagnostics["next_expected_step"] = _report_next_step("execution_failed")
        return diagnostics, False

    if status == "open":
        if not _env_bool("TRADE_REPORT_AI_GENERATE_ON_OPEN", True):
            diagnostics["report_status"] = "pending"
            diagnostics["report_reason_code"] = "awaiting_exit_for_full_report"
            diagnostics["report_reason_human"] = _report_reason_human("awaiting_exit_for_full_report")
            diagnostics["next_expected_step"] = _report_next_step("awaiting_exit_for_full_report")
            return diagnostics, False

    return diagnostics, True


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


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _runtime_position_for_symbol(state_obj: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    if not normalized or not isinstance(state_obj, dict):
        return {}

    portfolio_snapshot = state_obj.get("portfolio_snapshot") if isinstance(state_obj.get("portfolio_snapshot"), dict) else {}
    sources = [
        ("portfolio_snapshot.positions", portfolio_snapshot.get("positions")),
        ("mock_positions", state_obj.get("mock_positions")),
    ]
    for source_name, rows in sources:
        if not isinstance(rows, list):
            continue
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            row_symbol = normalize_symbol(raw_row.get("symbol") or raw_row.get("code") or "", allow_test_symbols=True)
            if row_symbol != normalized:
                continue
            row = dict(raw_row)
            row["_source"] = source_name
            return row
    return {}


def _derive_runtime_position_price(position: Dict[str, Any]) -> Tuple[Optional[float], str]:
    if not isinstance(position, dict):
        return None, ""
    direct_fields = (
        ("current_price", "runtime_state.position.current_price"),
        ("price", "runtime_state.position.price"),
        ("mark_price", "runtime_state.position.mark_price"),
        ("last_price", "runtime_state.position.last_price"),
    )
    for key, source in direct_fields:
        price = _safe_float(position.get(key), None)
        if price and price > 0:
            return price, source

    avg_price = _safe_float(position.get("avg_price"), None)
    qty = safe_int(position.get("qty"), 0)
    unrealized = _safe_float(position.get("unrealized_pnl"), None)
    if avg_price and avg_price > 0 and qty > 0 and unrealized is not None:
        derived = avg_price + (unrealized / float(qty))
        if derived > 0:
            return derived, "runtime_state.position.avg_plus_unrealized"
    return None, ""


def _append_unique_bullet(bullets: List[str], text: str) -> None:
    raw = str(text or "").strip()
    if not raw:
        return
    lowered = raw.lower()
    if any(str(existing or "").strip().lower() == lowered for existing in bullets):
        return
    bullets.append(raw)


def _backfill_open_lifecycle_monitor_reason(
    monitor_reason_human: Dict[str, Any],
    *,
    lifecycle_status: str,
    symbol: str,
    state_obj: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(monitor_reason_human or {})
    if str(lifecycle_status or "").strip().lower() != "open":
        return out
    normalized_symbol = normalize_symbol(symbol or "", allow_test_symbols=True)
    if not normalized_symbol or not isinstance(state_obj, dict) or not state_obj:
        return out

    position = _runtime_position_for_symbol(state_obj, normalized_symbol)
    peak_map = state_obj.get("position_peak_price") if isinstance(state_obj.get("position_peak_price"), dict) else {}
    bullets = [str(x or "").strip() for x in list(out.get("bullets") or []) if str(x or "").strip()]

    avg_price = out.get("average_price")
    if avg_price in (None, ""):
        avg_price = _safe_float(position.get("avg_price"), None)
        if avg_price not in (None, ""):
            out["average_price"] = avg_price
            _append_unique_bullet(bullets, f"Average price: {float(avg_price):.2f}")

    current_price = out.get("current_price")
    derived_price_source = ""
    current_price_backfilled = False
    if current_price in (None, ""):
        current_price, derived_price_source = _derive_runtime_position_price(position)
        if current_price not in (None, ""):
            out["current_price"] = current_price
            current_price_backfilled = True
            _append_unique_bullet(bullets, f"Current price: {float(current_price):.2f}")

    peak_price = out.get("peak_price")
    if peak_price in (None, ""):
        peak_price = _safe_float(peak_map.get(normalized_symbol), None)
        if peak_price in (None, ""):
            peak_price = _safe_float(position.get("peak_price"), None)
        if peak_price in (None, "") and avg_price not in (None, "") and current_price not in (None, ""):
            peak_price = max(float(avg_price), float(current_price))
        if peak_price not in (None, ""):
            out["peak_price"] = peak_price
            _append_unique_bullet(bullets, f"Peak price: {float(peak_price):.2f}")

    current_drawdown = out.get("current_drawdown")
    if current_drawdown in (None, "") and current_price not in (None, "") and avg_price not in (None, "") and float(avg_price) > 0:
        current_drawdown = (float(current_price) / float(avg_price)) - 1.0
        out["current_drawdown"] = current_drawdown
        _append_unique_bullet(bullets, f"Current drawdown: {current_drawdown * 100.0:.2f}%")

    peak_drawdown = out.get("peak_drawdown")
    if peak_drawdown in (None, "") and current_price not in (None, "") and peak_price not in (None, "") and float(peak_price) > 0:
        peak_drawdown = (float(current_price) / float(peak_price)) - 1.0
        out["peak_drawdown"] = peak_drawdown
        _append_unique_bullet(bullets, f"Peak drawdown: {peak_drawdown * 100.0:.2f}%")

    if derived_price_source and current_price_backfilled:
        out["price_source"] = derived_price_source
        _append_unique_bullet(bullets, f"Price source: {derived_price_source}")
    if derived_price_source and current_price_backfilled:
        policy = "runtime_state.position.current_price > runtime_state.position.avg_plus_unrealized > existing_monitor_fields"
        out["price_source_policy"] = policy
        _append_unique_bullet(bullets, f"Price source policy: {policy}")

    if bullets:
        out["bullets"] = bullets
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


def _latest_decision_trace_payload(rows: List[Dict[str, Any]], *, event: str, agent: str) -> Dict[str, Any]:
    agent_name = str(agent or "").strip().lower()
    event_name = str(event or "").strip()
    for row in reversed(rows):
        if str(row.get("stage") or "").strip() != "decision_trace":
            continue
        if str(row.get("event") or "").strip() != event_name:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        row_agent = str(payload.get("agent") or "").strip().lower()
        if row_agent != agent_name:
            continue
        agent_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        return dict(agent_payload or {})
    return {}


def _row_event_name(row: Dict[str, Any]) -> str:
    text = str(row.get("event_name") or "").strip()
    if text:
        return text
    stage = str(row.get("stage") or "").strip()
    event = str(row.get("event") or "").strip()
    return ".".join(part for part in (stage, event) if part)


def _filter_canonical_events(
    rows: List[Dict[str, Any]],
    *,
    run_ids: List[str],
    agent: str,
    event_names: List[str],
) -> List[Dict[str, Any]]:
    run_set = {str(item or "").strip() for item in list(run_ids or []) if str(item or "").strip()}
    names = {str(item or "").strip() for item in list(event_names or []) if str(item or "").strip()}
    out: List[Dict[str, Any]] = []
    for row in rows:
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        row_agent = str(row.get("agent") or row.get("stage") or "").strip().lower()
        if row_agent != str(agent or "").strip().lower():
            continue
        if names and _row_event_name(row) not in names:
            continue
        out.append(
            {
                "ts": str(row.get("ts") or ""),
                "event_name": _row_event_name(row),
                "level": str(row.get("level") or "info"),
                "run_id": str(row.get("run_id") or ""),
                "trade_id": str(row.get("trade_id") or ""),
                "session_id": str(row.get("session_id") or ""),
                "cycle_id": str(row.get("cycle_id") or ""),
                "agent": str(row.get("agent") or row.get("stage") or ""),
                "phase": str(row.get("phase") or ""),
                "symbol": str(row.get("symbol") or ""),
                "payload": dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {},
            }
        )
    out.sort(key=lambda item: _to_epoch(item.get("ts")) or 0)
    return out


def _resolve_strategist_source_run_ids(
    *,
    event_rows: List[Dict[str, Any]],
    lifecycle: Dict[str, Any],
) -> Tuple[List[str], Dict[str, str]]:
    lifecycle_run_ids = [str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
    if not lifecycle_run_ids:
        return [], {}

    strategist_event_names = {
        "strategist.market_context_snapshot",
        "strategist.global_sentiment_breakdown",
        "strategist.news_evidence_ranked",
        "strategist.decision_frame",
        "strategist.llm_response_saved",
    }
    strategist_run_ids = {
        str(row.get("run_id") or "").strip()
        for row in event_rows
        if str(row.get("run_id") or "").strip() in set(lifecycle_run_ids)
        and str(row.get("agent") or row.get("stage") or "").strip().lower() == "strategist"
        and _row_event_name(row) in strategist_event_names
    }

    strategist_frame_rows = [
        row
        for row in event_rows
        if str(row.get("agent") or row.get("stage") or "").strip().lower() == "strategist"
        and _row_event_name(row) == "strategist.decision_frame"
    ]
    strategist_frame_rows.sort(key=lambda row: _to_epoch(row.get("ts")) or 0)

    linked_cached_frames: Dict[str, str] = {}
    for run_id in lifecycle_run_ids:
        if run_id in strategist_run_ids:
            continue
        fast_path_rows = [
            row
            for row in event_rows
            if str(row.get("run_id") or "").strip() == run_id
            and _row_event_name(row) == "commander_router.fast_path"
        ]
        if not fast_path_rows:
            continue
        fast_path = fast_path_rows[-1]
        payload = fast_path.get("payload") if isinstance(fast_path.get("payload"), dict) else {}
        if str(payload.get("path") or "").strip() != "integrated_chain_cached_frame":
            continue
        target_ts = _to_epoch(fast_path.get("ts")) or 0
        reuse_sec = max(30, safe_int(payload.get("reuse_sec"), 180))
        candidate_rows = [
            row
            for row in strategist_frame_rows
            if str(row.get("run_id") or "").strip() != run_id
            and (_to_epoch(row.get("ts")) or 0) <= target_ts
            and target_ts - (_to_epoch(row.get("ts")) or 0) <= reuse_sec + 30
        ]
        if not candidate_rows:
            continue
        source_run_id = str(candidate_rows[-1].get("run_id") or "").strip()
        if not source_run_id:
            continue
        strategist_run_ids.add(source_run_id)
        linked_cached_frames[run_id] = source_run_id

    return sorted(strategist_run_ids), linked_cached_frames


def _latest_event_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    payload = rows[-1].get("payload") if isinstance(rows[-1], dict) else {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def _headline_count(news_rows: List[Dict[str, Any]]) -> int:
    total = 0
    for row in list(news_rows or []):
        if not isinstance(row, dict):
            continue
        total += safe_int(row.get("headline_count"), 0)
    return total


def _hydrate_strategist_payload_from_evidence(
    strategist_payload: Dict[str, Any],
    strategist_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(strategist_payload or {})
    snapshot = _latest_event_payload(list(strategist_evidence.get("market_context_snapshots") or []))
    decision_frame = _latest_event_payload(list(strategist_evidence.get("decision_frames") or []))
    news_ranked = _latest_event_payload(list(strategist_evidence.get("news_evidence_ranked") or []))
    llm_saved = _latest_event_payload(list(strategist_evidence.get("llm_response_saved") or []))

    global_signal = snapshot.get("global_signal") if isinstance(snapshot.get("global_signal"), dict) else {}
    if not isinstance(out.get("llm_parsed_output"), dict) or not out.get("llm_parsed_output"):
        out["llm_parsed_output"] = dict(decision_frame or {})
    if not str(out.get("market_regime") or "").strip():
        out["market_regime"] = str(decision_frame.get("market_regime") or "")
    if not str(out.get("market_sentiment") or "").strip():
        out["market_sentiment"] = str(decision_frame.get("market_sentiment") or "")
    if not str(out.get("playbook") or "").strip():
        out["playbook"] = str(decision_frame.get("playbook") or "")
    if not list(out.get("themes") or []):
        out["themes"] = [str(x or "") for x in list(decision_frame.get("themes") or []) if str(x or "").strip()]
    existing_global_score = out.get("global_sentiment_score")
    existing_global_status = str(out.get("global_sentiment_status") or "").strip()
    if existing_global_score in (None, "") or (
        _safe_float(existing_global_score, None) == 0.0
        and not existing_global_status
        and isinstance(global_signal, dict)
        and global_signal.get("score") not in (None, "")
    ):
        out["global_sentiment_score"] = global_signal.get("score")
    if not str(out.get("global_sentiment_status") or "").strip():
        out["global_sentiment_status"] = str(global_signal.get("status") or "")
    if not str(out.get("global_sentiment_source") or "").strip():
        out["global_sentiment_source"] = str(global_signal.get("source") or "")
    if not isinstance(out.get("fear_index"), dict) or not out.get("fear_index"):
        out["fear_index"] = dict(global_signal.get("fear_index") or {})
    if not isinstance(out.get("global_macro_moves"), dict) or not out.get("global_macro_moves"):
        out["global_macro_moves"] = dict(global_signal.get("macro_moves") or {})
    if not isinstance(out.get("macro_stress_overlay"), dict) or not out.get("macro_stress_overlay"):
        out["macro_stress_overlay"] = dict(snapshot.get("macro_stress_overlay") or {})
    if not str(out.get("news_query_reasoning") or "").strip():
        reasons = list(decision_frame.get("reason_chain") or [])
        out["news_query_reasoning"] = str(reasons[-1] or "") if reasons else ""
    if not list(out.get("news_query_targets") or []):
        out["news_query_targets"] = [str(x or "") for x in list(news_ranked.get("news_query_targets") or []) if str(x or "").strip()]
    if safe_int(out.get("market_news_query_count"), 0) <= 0:
        out["market_news_query_count"] = len(list(news_ranked.get("news_query_targets") or []))
    if safe_int(out.get("market_news_total_headlines"), 0) <= 0:
        ranked_rows = list(news_ranked.get("market_news_ranked") or []) + list(news_ranked.get("candidate_news_ranked") or [])
        out["market_news_total_headlines"] = _headline_count(ranked_rows)
    if not str(out.get("llm_provider") or "").strip():
        out["llm_provider"] = str(llm_saved.get("provider") or "OpenRouter")
    if not str(out.get("llm_model") or "").strip():
        out["llm_model"] = str(llm_saved.get("model") or "")
    return out


def _build_trade_evidence_from_events(
    *,
    event_rows: List[Dict[str, Any]],
    lifecycle: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    run_ids = [str(x or "") for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
    trade_id = str(lifecycle.get("trade_id") or "")
    symbol = str(lifecycle.get("symbol") or "")
    strategist_run_ids, linked_cached_frames = _resolve_strategist_source_run_ids(
        event_rows=event_rows,
        lifecycle=lifecycle,
    )

    strategist_events = _filter_canonical_events(
        event_rows,
        run_ids=strategist_run_ids,
        agent="strategist",
        event_names=[
            "strategist.market_context_snapshot",
            "strategist.global_sentiment_breakdown",
            "strategist.news_evidence_ranked",
            "strategist.decision_frame",
            "strategist.llm_response_saved",
        ],
    )
    scanner_events = _filter_canonical_events(
        event_rows,
        run_ids=run_ids,
        agent="scanner",
        event_names=[
            "scanner.candidate_pool_snapshot",
            "scanner.candidate_ranking_table",
            "scanner.candidate_selection_reason",
            "scanner.selection_output",
        ],
    )
    monitor_events = _filter_canonical_events(
        event_rows,
        run_ids=run_ids,
        agent="monitor",
        event_names=[
            "monitor.threshold_snapshot",
            "monitor.state_transition",
            "monitor.exit_decision_detail",
            "monitor.cycle_summary",
        ],
    )

    strategist_evidence = {
        "schema_version": "trade_strategist_evidence.v1",
        "trade_id": trade_id,
        "symbol": symbol,
        "run_ids": strategist_run_ids,
        "linked_cached_frame_sources": dict(linked_cached_frames),
        "market_context_snapshots": [row for row in strategist_events if row.get("event_name") == "strategist.market_context_snapshot"],
        "global_sentiment_breakdowns": [row for row in strategist_events if row.get("event_name") == "strategist.global_sentiment_breakdown"],
        "news_evidence_ranked": [row for row in strategist_events if row.get("event_name") == "strategist.news_evidence_ranked"],
        "decision_frames": [row for row in strategist_events if row.get("event_name") == "strategist.decision_frame"],
        "llm_response_saved": [row for row in strategist_events if row.get("event_name") == "strategist.llm_response_saved"],
    }
    scanner_evidence = {
        "schema_version": "trade_scanner_evidence.v1",
        "trade_id": trade_id,
        "symbol": symbol,
        "run_ids": run_ids,
        "candidate_pool_snapshots": [row for row in scanner_events if row.get("event_name") == "scanner.candidate_pool_snapshot"],
        "candidate_ranking_tables": [row for row in scanner_events if row.get("event_name") == "scanner.candidate_ranking_table"],
        "candidate_selection_reasons": [row for row in scanner_events if row.get("event_name") == "scanner.candidate_selection_reason"],
        "selection_outputs": [row for row in scanner_events if row.get("event_name") == "scanner.selection_output"],
    }
    monitor_timeline = {
        "schema_version": "trade_monitor_timeline.v1",
        "trade_id": trade_id,
        "symbol": symbol,
        "run_ids": run_ids,
        "threshold_snapshots": [row for row in monitor_events if row.get("event_name") == "monitor.threshold_snapshot"],
        "state_transitions": [row for row in monitor_events if row.get("event_name") == "monitor.state_transition"],
        "entry_decision_details": [row for row in monitor_events if row.get("event_name") == "monitor.entry_decision_detail"],
        "exit_decision_details": [row for row in monitor_events if row.get("event_name") == "monitor.exit_decision_detail"],
        "cycle_summaries": [row for row in monitor_events if row.get("event_name") == "monitor.cycle_summary"],
    }
    return strategist_evidence, scanner_evidence, monitor_timeline


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


def _has_meaningful_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    for value in payload.values():
        if isinstance(value, dict) and _has_meaningful_payload(value):
            return True
        if isinstance(value, list) and any(item not in ({}, [], None, "") for item in value):
            return True
        if value not in ({}, [], None, ""):
            return True
    return False


def _prefer_canonical_payload(
    canonical_sources: Dict[str, Any],
    agent: str,
    fallback: Dict[str, Any],
    *,
    fallback_source: str,
    normalized_payload: Dict[str, Any] | None = None,
    normalized_path: str = "",
) -> Tuple[Dict[str, Any], str, str]:
    canonical_payload = (
        (canonical_sources.get("artifacts") or {}).get(agent)
        if isinstance(canonical_sources.get("artifacts"), dict)
        else {}
    )
    canonical_path = (
        str(((canonical_sources.get("paths") or {}).get(agent) or "")).strip()
        if isinstance(canonical_sources.get("paths"), dict)
        else ""
    )
    merged = dict(fallback or {})
    if _has_meaningful_payload(normalized_payload):
        merged.update(dict(normalized_payload or {}))
        return merged, "normalized_trade_artifact", str(normalized_path or "")
    if _has_meaningful_payload(canonical_payload):
        merged.update(dict(canonical_payload or {}))
        return merged, "canonical", canonical_path
    return dict(fallback or {}), str(fallback_source or "fallback"), canonical_path


def _build_run_snapshots(event_log_path: Path, day: str, *, reports_root: Path) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in _iter_jsonl(event_log_path):
        if day and _utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        grouped.setdefault(run_id, []).append(row)

    out: List[Dict[str, Any]] = []
    for run_id, rows in grouped.items():
        rows = sorted(rows, key=lambda row: _to_epoch(row.get("ts")) or 0)
        canonical_sources = load_run_canonical_artifacts(
            reports_root=reports_root,
            run_id=run_id,
            day_hint=day,
        )
        route_row = next(
            (
                row
                for row in rows
                if str(row.get("stage") or "") == "commander_router"
                and str(row.get("event") or "") == "route"
            ),
            {},
        )
        scanner_summary = next(
            (
                row.get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "scanner"
                and str(row.get("event") or "") == "summary"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        monitor_trace = _latest_decision_trace_payload(rows, event="entry_exit_decision", agent="monitor")
        monitor_summary = next(
            (
                row.get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "monitor"
                and str(row.get("event") or "") == "summary"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        verdict_payload = next(
            (
                row.get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "execute_from_packet"
                and str(row.get("event") or "") == "verdict"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        commander_summary, commander_source, _commander_path = _prefer_canonical_payload(
            canonical_sources,
            "commander",
            {
                "mode": str((route_row.get("payload") or {}).get("mode") or ""),
                "phase": str((route_row.get("payload") or {}).get("phase") or ""),
                "status": str(((rows[-1].get("payload") or {}) if isinstance(rows[-1].get("payload"), dict) else {}).get("status") or ""),
                "path": str(((rows[-1].get("payload") or {}) if isinstance(rows[-1].get("payload"), dict) else {}).get("path") or ""),
            },
            fallback_source="event_log",
        )
        scanner_summary, scanner_source, _scanner_path = _prefer_canonical_payload(
            canonical_sources,
            "scanner",
            scanner_summary if isinstance(scanner_summary, dict) else {},
            fallback_source="direct_artifact",
        )
        monitor_summary, monitor_source, _monitor_path = _prefer_canonical_payload(
            canonical_sources,
            "monitor",
            monitor_summary if isinstance(monitor_summary, dict) else {},
            fallback_source="direct_artifact",
        )
        supervisor_summary, supervisor_source, _supervisor_path = _prefer_canonical_payload(
            canonical_sources,
            "supervisor",
            verdict_payload if isinstance(verdict_payload, dict) else {},
            fallback_source="event_log",
        )
        execution_row = next(
            (
                row
                for row in reversed(rows)
                if str(row.get("stage") or "") == "execute_from_packet"
                and str(row.get("event") or "") == "execution"
                and isinstance(row.get("payload"), dict)
            ),
            {},
        )
        executor_payload, executor_source, _executor_path = _prefer_canonical_payload(
            canonical_sources,
            "executor",
            _normalize_execution_payload(execution_row.get("payload") if isinstance(execution_row.get("payload"), dict) else {}),
            fallback_source="event_log",
        )
        execution = _normalize_execution_payload(executor_payload if isinstance(executor_payload, dict) else {})
        if isinstance(supervisor_summary, dict) and "supervisor_allow" in supervisor_summary:
            supervisor_summary = {
                **dict(supervisor_summary),
                "allowed": bool(supervisor_summary.get("supervisor_allow")),
                "reason": str(supervisor_summary.get("supervisor_reason") or supervisor_summary.get("guard_reason") or supervisor_summary.get("reason") or ""),
            }
        elif isinstance(supervisor_summary, dict) and "allowed" not in supervisor_summary:
            supervisor_summary = {
                **dict(supervisor_summary),
                "allowed": bool(supervisor_summary.get("supervisor_allow")),
                "reason": str(supervisor_summary.get("supervisor_reason") or supervisor_summary.get("guard_reason") or ""),
            }
        candidate_selection = next(
            (
                (row.get("payload") or {}).get("payload")
                for row in reversed(rows)
                if str(row.get("stage") or "") == "decision_trace"
                and str(row.get("event") or "") == "candidate_selection"
                and isinstance(row.get("payload"), dict)
                and str((row.get("payload") or {}).get("agent") or "") == "scanner"
            ),
            {},
        )
        selected_symbol = (
            (candidate_selection.get("selected_candidate") or {}).get("symbol")
            if isinstance(candidate_selection.get("selected_candidate"), dict)
            else candidate_selection.get("selected_symbol")
        )
        symbol = normalize_symbol(
            execution.get("symbol")
            or selected_symbol
            or scanner_summary.get("selected_symbol")
            or monitor_trace.get("selected_symbol")
            or monitor_summary.get("selected_symbol")
            or scanner_summary.get("top_stock")
            or monitor_summary.get("symbol")
            or "",
            allow_test_symbols=True,
        )
        execution_action = str(execution.get("action") or "").upper()
        monitor_reason = str(monitor_summary.get("monitor_reason") or "").strip()
        exit_reason = str(monitor_summary.get("exit_reason") or "").strip()
        merged_monitor = dict(monitor_summary or {})
        if monitor_trace:
            merged_monitor.update(dict(monitor_trace or {}))
        if not monitor_reason:
            monitor_reason = str(merged_monitor.get("monitor_reason") or "").strip()
        if not exit_reason:
            exit_reason = str(merged_monitor.get("exit_reason") or "").strip()
        if execution_action in {"BUY", "SELL"}:
            posture = execution_action
        elif "hold" in monitor_reason.lower() or "hold" in exit_reason.lower():
            posture = "HOLD"
        elif "exit" in exit_reason.lower():
            posture = "EXIT_SIGNAL"
        else:
            posture = "WAIT"
        ts_start = str(route_row.get("ts") or rows[0].get("ts") or "")
        ts_end = str(rows[-1].get("ts") or ts_start)
        out.append(
            {
                "run_id": run_id,
                "ts_start": ts_start,
                "ts_end": ts_end,
                "ts_epoch": _to_epoch(ts_start) or 0,
                "symbol": symbol,
                "execution_action": execution_action,
                "posture": posture,
                "execution": execution,
                "monitor_reason": monitor_reason,
                "exit_reason": exit_reason,
                "monitor": merged_monitor,
                "monitor_trace": dict(monitor_trace or {}),
                "phase": str(commander_summary.get("phase") or (route_row.get("payload") or {}).get("phase") or ""),
                "mode": str(commander_summary.get("mode") or (route_row.get("payload") or {}).get("mode") or ""),
                "verdict_allowed": bool(supervisor_summary.get("allowed")),
                "verdict_reason": str(supervisor_summary.get("reason") or ""),
                "canonical_agent_artifacts": dict((canonical_sources.get("artifacts") or {})) if isinstance(canonical_sources.get("artifacts"), dict) else {},
                "canonical_agent_artifact_paths": dict((canonical_sources.get("paths") or {})) if isinstance(canonical_sources.get("paths"), dict) else {},
                "evidence_provenance": {
                    "commander": commander_source,
                    "scanner": scanner_source,
                    "monitor": monitor_source,
                    "supervisor": supervisor_source,
                    "executor": executor_source,
                },
            }
        )
    out.sort(key=lambda row: int(row.get("ts_epoch") or 0))
    return out


def _format_duration_human(seconds: int) -> str:
    if seconds <= 0:
        return "0m"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds / 60.0:.1f}m"
    return f"{seconds / 3600.0:.1f}h"


def _build_trade_id(day: str, symbol: str, seq: int) -> str:
    compact_day = str(day or "").replace("-", "")
    clean_symbol = normalize_symbol(symbol or "", allow_test_symbols=True) or "UNKNOWN"
    return f"TRD_{compact_day}_{clean_symbol}_{int(seq):02d}"


def _build_lifecycle_from_seed(
    *,
    trade_id: str,
    symbol: str,
    day: str,
    execution_mode_label_text: str,
    story_type: str,
) -> Dict[str, Any]:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "day": day,
        "status": "open",
        "execution_mode_label": execution_mode_label_text,
        "story_type": story_type,
        "entry": {},
        "holding": {
            "run_ids": [],
            "holding_events": [],
            "posture_history": [],
            "monitor_updates": [],
            "noteworthy_changes": [],
        },
        "exit": {},
        "run_ids_all": [],
        "summary": {},
        "reporter": {},
        "timeline": [],
        "warnings": [],
    }


def _build_trade_lifecycles(
    *,
    day: str,
    run_snapshots: List[Dict[str, Any]],
    run_bundles: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    symbol_seq: Dict[str, int] = {}
    active_by_symbol: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []

    def _next_trade_id(symbol: str) -> str:
        key = normalize_symbol(symbol, allow_test_symbols=True) or "UNKNOWN"
        symbol_seq[key] = int(symbol_seq.get(key, 0) + 1)
        return _build_trade_id(day, key, symbol_seq[key])

    def _bundle_story_type(bundle: Dict[str, Any]) -> str:
        story_contract = bundle.get("story_contract") if isinstance(bundle.get("story_contract"), dict) else {}
        return str(story_contract.get("story_type") or "").strip().lower()

    def _bundle_mode_label(bundle: Dict[str, Any]) -> str:
        story_contract = bundle.get("story_contract") if isinstance(bundle.get("story_contract"), dict) else {}
        return str(story_contract.get("execution_mode_label") or "").strip()

    def _entry_context(snapshot: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        strategist_payload = bundle.get("strategist") if isinstance(bundle.get("strategist"), dict) else {}
        strategist_summary_payload = bundle.get("strategist_summary") if isinstance(bundle.get("strategist_summary"), dict) else {}
        strategist_policy = (
            strategist_payload.get("policy_selected")
            if isinstance(strategist_payload.get("policy_selected"), dict)
            else strategist_summary_payload.get("policy_selected")
            if isinstance(strategist_summary_payload.get("policy_selected"), dict)
            else {}
        )
        scanner_payload = bundle.get("scanner") if isinstance(bundle.get("scanner"), dict) else {}
        scanner_source_refs = scanner_payload.get("source_refs") if isinstance(scanner_payload.get("source_refs"), dict) else {}
        scanner_reason_human = bundle.get("scanner_reason_human") if isinstance(bundle.get("scanner_reason_human"), dict) else {}
        monitor_reason_human = bundle.get("monitor_reason_human") if isinstance(bundle.get("monitor_reason_human"), dict) else {}
        scanner_context = dict(scanner_reason_human)
        if not scanner_context and scanner_payload:
            scanner_context = {
                "selected_symbol": str(scanner_payload.get("selected_symbol") or scanner_payload.get("top_stock") or ""),
                "selected_rank": safe_int(scanner_payload.get("selected_rank"), 0),
                "selected_score": scanner_payload.get("top_score"),
                "summary": str(
                    scanner_payload.get("selection_reason")
                    or (scanner_payload.get("selected_candidate") or {}).get("why")
                    or ""
                ),
            }
        monitor_context = dict(monitor_reason_human)
        if not monitor_context and isinstance(bundle.get("monitor"), dict):
            monitor_payload = dict(bundle.get("monitor") or {})
            monitor_context = {
                "summary": str(monitor_payload.get("monitor_reason") or monitor_payload.get("entry_reason") or ""),
                "active_exit_axis": str(monitor_payload.get("active_exit_axis") or ""),
            }
        entry_price = execution.get("price")
        if entry_price is None or entry_price == "":
            entry_price = execution.get("order_price") or execution.get("avg_price")
        entry_reason = str(
            scanner_context.get("summary")
            or monitor_context.get("summary")
            or snapshot.get("monitor_reason")
            or ""
        ).strip()
        if _is_placeholder_entry_reason(entry_reason):
            entry_reason = str(
                (bundle.get("execution_outcome_human") or {}).get("summary")
                or scanner_context.get("summary")
                or monitor_context.get("summary")
                or snapshot.get("execution_reason")
                or snapshot.get("decision_reason")
                or snapshot.get("monitor_reason")
                or "Entry reasoning was not captured."
            ).strip()
        playbook = str(
            strategist_payload.get("playbook")
            or strategist_summary_payload.get("playbook")
            or strategist_policy.get("playbook")
            or scanner_source_refs.get("strategist_playbook")
            or ""
        )
        themes_raw = (
            strategist_payload.get("themes")
            or strategist_summary_payload.get("themes")
            or strategist_policy.get("themes")
            or []
        )
        themes = [str(item or "").strip() for item in list(themes_raw or []) if str(item or "").strip()]
        return {
            "run_id": str(snapshot.get("run_id") or ""),
            "ts": str(snapshot.get("ts_start") or ""),
            "action": str(execution.get("action") or "BUY"),
            "price": entry_price,
            "qty": safe_int(execution.get("qty"), 0),
            "reason_human": entry_reason,
            "strategist_context": {
                "playbook": playbook,
                "themes": themes[:6],
                "market_context_summary": str((bundle.get("market_context_human") or {}).get("summary") or ""),
            },
            "scanner_context": scanner_context,
            "monitor_context": monitor_context,
            "guard_context": dict(bundle.get("guard_reason_human") or {}),
            "execution_context": dict(bundle.get("execution_outcome_human") or {}),
        }

    def _exit_context(snapshot: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        has_exit_monitor_trace = bool(
            str(snapshot.get("exit_reason") or "").strip()
            or str(snapshot.get("monitor_reason") or "").strip()
        )
        monitor_context = dict(bundle.get("monitor_reason_human") or {}) if has_exit_monitor_trace else {}
        return {
            "run_id": str(snapshot.get("run_id") or ""),
            "ts": str(snapshot.get("ts_start") or ""),
            "action": str(execution.get("action") or "SELL"),
            "price": execution.get("price"),
            "qty": safe_int(execution.get("qty"), 0),
            "reason_human": str(
                (monitor_context or {}).get("summary")
                or (bundle.get("execution_outcome_human") or {}).get("summary")
                or snapshot.get("exit_reason")
                or snapshot.get("monitor_reason")
                or "Exit reasoning was not captured."
            ),
            "monitor_context": monitor_context,
            "guard_context": dict(bundle.get("guard_reason_human") or {}),
            "execution_context": dict(bundle.get("execution_outcome_human") or {}),
        }

    for snapshot in sorted(run_snapshots, key=lambda row: int(row.get("ts_epoch") or 0)):
        run_id = str(snapshot.get("run_id") or "").strip()
        symbol = normalize_symbol(snapshot.get("symbol") or "", allow_test_symbols=True)
        if not run_id or not symbol:
            continue
        bundle = run_bundles.get(run_id) if isinstance(run_bundles.get(run_id), dict) else {}
        action = str(snapshot.get("execution_action") or "").upper()
        if action == "BUY":
            if symbol in active_by_symbol and isinstance(active_by_symbol.get(symbol), dict):
                prev = active_by_symbol[symbol]
                if str(prev.get("status") or "") == "open":
                    prev["status"] = "partial"
                    prev.setdefault("warnings", []).append(
                        "A new BUY was detected while a previous lifecycle for the same symbol was still open."
                    )
                    prev.setdefault("timeline", []).append(
                        {
                            "event": "entry_overlap",
                            "ts": str(snapshot.get("ts_start") or ""),
                            "description": f"New BUY run {run_id} overlapped existing open lifecycle.",
                        }
                    )
            trade_id = _next_trade_id(symbol)
            story_type = _bundle_story_type(bundle) or "decision_only"
            mode_label = _bundle_mode_label(bundle) or "decision only"
            lifecycle = _build_lifecycle_from_seed(
                trade_id=trade_id,
                symbol=symbol,
                day=day,
                execution_mode_label_text=mode_label,
                story_type=story_type,
            )
            lifecycle["entry"] = _entry_context(snapshot, bundle)
            lifecycle["run_ids_all"] = [run_id]
            lifecycle["timeline"].append(
                {
                    "event": "entry",
                    "ts": str(snapshot.get("ts_start") or ""),
                    "description": f"Entry BUY was executed by run {run_id}.",
                }
            )
            active_by_symbol[symbol] = lifecycle
            out.append(lifecycle)
            continue

        if action == "SELL":
            lifecycle = active_by_symbol.get(symbol)
            if not lifecycle:
                trade_id = _next_trade_id(symbol)
                story_type = _bundle_story_type(bundle) or "decision_only"
                mode_label = _bundle_mode_label(bundle) or "decision only"
                lifecycle = _build_lifecycle_from_seed(
                    trade_id=trade_id,
                    symbol=symbol,
                    day=day,
                    execution_mode_label_text=mode_label,
                    story_type=story_type,
                )
                lifecycle["status"] = "partial"
                out.append(lifecycle)
            lifecycle["exit"] = _exit_context(snapshot, bundle)
            lifecycle.setdefault("run_ids_all", [])
            if run_id not in lifecycle["run_ids_all"]:
                lifecycle["run_ids_all"].append(run_id)
            lifecycle["timeline"].append(
                {
                    "event": "exit",
                    "ts": str(snapshot.get("ts_start") or ""),
                    "description": f"Exit SELL was executed by run {run_id}.",
                }
            )
            if lifecycle.get("entry"):
                lifecycle["status"] = "closed"
            else:
                lifecycle["status"] = "partial"
            active_by_symbol.pop(symbol, None)
            continue

        lifecycle = active_by_symbol.get(symbol)
        if not lifecycle:
            continue
        lifecycle.setdefault("run_ids_all", [])
        if run_id not in lifecycle["run_ids_all"]:
            lifecycle["run_ids_all"].append(run_id)
        monitor_reason = str(snapshot.get("monitor_reason") or "")
        exit_reason = str(snapshot.get("exit_reason") or "")
        holding_event = {
            "run_id": run_id,
            "ts": str(snapshot.get("ts_start") or ""),
            "posture": str(snapshot.get("posture") or "HOLD"),
            "monitor_reason": monitor_reason,
            "exit_reason": exit_reason,
            "monitor_context": dict(snapshot.get("monitor") or {}),
            "summary": f"Monitor posture={snapshot.get('posture') or 'HOLD'} reason={monitor_reason or '-'} exit={exit_reason or '-'}",
        }
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        holding.setdefault("run_ids", [])
        holding.setdefault("holding_events", [])
        holding.setdefault("posture_history", [])
        holding.setdefault("monitor_updates", [])
        if run_id not in holding["run_ids"]:
            holding["run_ids"].append(run_id)
        holding["holding_events"].append(holding_event)
        holding["posture_history"].append({"ts": str(snapshot.get("ts_start") or ""), "posture": str(snapshot.get("posture") or "HOLD")})
        holding["monitor_updates"].append(monitor_reason or exit_reason or "monitor update captured")
        lifecycle["holding"] = holding
        lifecycle["timeline"].append(
            {
                "event": "holding",
                "ts": str(snapshot.get("ts_start") or ""),
                "description": holding_event["summary"],
            }
        )

    for lifecycle in out:
        entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        entry_ts = _to_epoch(entry.get("ts"))
        end_ts = _to_epoch(exit_ctx.get("ts"))
        if end_ts is None:
            latest_hold_ts = max((_to_epoch((row or {}).get("ts")) or 0 for row in list(holding.get("holding_events") or [])), default=0)
            end_ts = latest_hold_ts or entry_ts or 0
        duration_sec = int(max(0, (end_ts or 0) - (entry_ts or end_ts or 0)))
        holding_duration = _format_duration_human(duration_sec)
        entry_reason_human = str(entry.get("reason_human") or "Entry reason was not captured.")
        if lifecycle.get("status") == "open":
            exit_reason_human = "Position is still open; monitor is watching for exit triggers."
        elif lifecycle.get("status") == "partial" and not exit_ctx:
            exit_reason_human = "Lifecycle is partial because exit evidence is missing."
        else:
            exit_reason_human = str(exit_ctx.get("reason_human") or "Exit reason was not captured.")
        lifecycle_summary = (
            f"Trade {lifecycle.get('trade_id')} for {lifecycle.get('symbol')} is {lifecycle.get('status')}. "
            f"Holding duration is {holding_duration}. "
            f"Entry: {entry_reason_human} "
            f"Exit: {exit_reason_human}"
        )
        operator_conclusion_human = (
            f"Current lifecycle status is {lifecycle.get('status')}. "
            f"{'Position remains open and requires monitoring.' if lifecycle.get('status') == 'open' else 'Entry and exit are connected in one lifecycle story.'}"
        )

        reporter_summary = ""
        reporter_grade = "N/A"
        reporter_status = "missing"
        improvement_points: List[str] = []
        entry_run_id = str(entry.get("run_id") or "")
        exit_run_id = str(exit_ctx.get("run_id") or "")
        entry_bundle = run_bundles.get(entry_run_id) if isinstance(run_bundles.get(entry_run_id), dict) else {}
        exit_bundle = run_bundles.get(exit_run_id) if isinstance(run_bundles.get(exit_run_id), dict) else {}
        reporter_human = (
            entry_bundle.get("reporter_status_human")
            if isinstance(entry_bundle.get("reporter_status_human"), dict)
            else exit_bundle.get("reporter_status_human")
            if isinstance(exit_bundle.get("reporter_status_human"), dict)
            else {}
        )
        if isinstance(reporter_human, dict):
            reporter_summary = str(reporter_human.get("summary") or "")
            reporter_grade = str(reporter_human.get("grade") or "N/A")
            reporter_status = str(reporter_human.get("status") or "missing")
        if reporter_status != "linked":
            improvement_points.append("Link same-day reporter analysis to this lifecycle for a complete quality review.")
        if lifecycle.get("status") == "open":
            improvement_points.append("Capture additional monitor runs so hold behavior quality can be evaluated.")
        if not holding.get("run_ids"):
            improvement_points.append("Holding-phase evidence is thin; preserve more monitor context between entry and exit.")

        lifecycle["summary"] = {
            "holding_duration": holding_duration,
            "entry_reason_human": entry_reason_human,
            "exit_reason_human": exit_reason_human,
            "lifecycle_summary_human": lifecycle_summary,
            "operator_conclusion_human": operator_conclusion_human,
        }
        lifecycle["reporter"] = {
            "status_human": reporter_status,
            "summary": reporter_summary or "Reporter linkage is pending or missing for this lifecycle.",
            "grade": reporter_grade,
            "improvement_points": improvement_points[:6],
        }
        if str(lifecycle.get("story_type") or "") == "failed_execution":
            lifecycle["status"] = "failed"
        lifecycle.setdefault("warnings", [])
        if lifecycle.get("status") == "partial":
            lifecycle["warnings"].append("Lifecycle is partial because entry or exit evidence is incomplete.")
        if lifecycle.get("status") == "open":
            lifecycle["warnings"].append("Lifecycle is open; no closing SELL execution has been recorded yet.")

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
    state_store_path = Path(str(os.getenv("STATE_STORE_PATH", "data/state.json")).strip() or "data/state.json")
    runtime_state = _read_json(state_store_path)
    report_requested = bool(args.trade_report_ai) if args.trade_report_ai is not None else _env_bool("TRADE_REPORT_AI_ENABLED", True)
    configured_report_model = _normalize_model_name(
        str(args.trade_report_ai_model).strip()
        if args.trade_report_ai_model
        else os.getenv("TRADE_REPORT_AI_MODEL", "")
        or os.getenv("OPENROUTER_MODEL_TRADE_REPORT", "")
        or os.getenv("OPENROUTER_DEFAULT_MODEL", "")
        or "openrouter/free"
    )

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

    day_event_rows = [row for row in _iter_jsonl(event_log_path) if not day or _utc_day(row.get("ts")) == day]
    day_evidence_rows = [
        row
        for row in _iter_jsonl(evidence_log_path)
        if not day or _utc_day(row.get("timestamp") or row.get("ts")) == day
    ]
    execution_runs = _resolve_execution_runs(event_log_path, day)[: max(1, int(args.max_runs))]
    trade_md, trade_js, trade_obj = _load_or_generate_trade_explain(event_log_path, analysis_root, day)
    reporter_md, reporter_js, reporter_obj = _load_or_generate_reporter_analysis(event_log_path, analysis_root, reports_root, intents_path, day)
    daily_paths = daily_artifact_paths(reports_root, day)
    operator_summary_json = daily_paths["operator_summary_json"]
    operator_summary_md = daily_paths["operator_summary_md"]
    if not operator_summary_json.exists():
        operator_summary_json = daily_paths["legacy_operator_summary_json"]
    if not operator_summary_md.exists():
        operator_summary_md = daily_paths["legacy_operator_summary_md"]
    canonical_trades_root = reports_root / "trades"
    year_part, month_part = (day.split("-") + ["01", "01"])[:2]

    run_bundles_by_run: Dict[str, Dict[str, Any]] = {}
    run_bundle_rows: List[Dict[str, Any]] = []
    run_story_type_counts: Dict[str, int] = {}
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
        canonical_sources = load_run_canonical_artifacts(
            reports_root=reports_root,
            run_id=run_id,
            day_hint=day,
        )
        commander_payload, commander_source, commander_path = _prefer_canonical_payload(
            canonical_sources,
            "commander",
            dict(trace_out.get("commander") or {}),
            fallback_source="direct_artifact",
        )
        strategist_payload, strategist_source, strategist_path = _prefer_canonical_payload(
            canonical_sources,
            "strategist",
            dict(trace_out.get("strategist") or {}),
            fallback_source="direct_artifact",
        )
        scanner_payload, scanner_source, scanner_path = _prefer_canonical_payload(
            canonical_sources,
            "scanner",
            dict(trace_out.get("scanner") or {}),
            fallback_source="direct_artifact",
        )
        monitor_payload, monitor_source, monitor_path = _prefer_canonical_payload(
            canonical_sources,
            "monitor",
            dict(trace_out.get("monitor") or {}),
            fallback_source="direct_artifact",
        )
        supervisor_payload, supervisor_source, supervisor_path = _prefer_canonical_payload(
            canonical_sources,
            "supervisor",
            dict(trace_out.get("supervisor") or {}),
            fallback_source="direct_artifact",
        )
        executor_payload, executor_source, executor_path = _prefer_canonical_payload(
            canonical_sources,
            "executor",
            dict(trace_out.get("executor") or {}),
            fallback_source="direct_artifact",
        )
        merged_execution = _normalize_execution_payload({**dict(execution or {}), **dict(executor_payload or {})})
        bundle_out: Dict[str, Any] = {
            "schema_version": "live_execution_bundle.v2",
            "artifact_type": "aggregated_execution_bundle",
            "ts": utc_now_iso(),
            "day": day,
            "run_id": run_id,
            "execution": merged_execution,
            "commander": commander_payload,
            "strategist": strategist_payload,
            "scanner": scanner_payload,
            "monitor": monitor_payload,
            "supervisor": supervisor_payload,
            "executor": executor_payload,
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
                "canonical_commander_json": commander_path,
                "canonical_strategist_json": strategist_path,
                "canonical_scanner_json": scanner_path,
                "canonical_monitor_json": monitor_path,
                "canonical_supervisor_json": supervisor_path,
                "canonical_executor_json": executor_path,
            },
            "canonical_agent_artifacts": dict((canonical_sources.get("artifacts") or {})) if isinstance(canonical_sources.get("artifacts"), dict) else {},
            "evidence_provenance": {
                "commander": commander_source,
                "strategist": strategist_source,
                "scanner": scanner_source,
                "monitor": monitor_source,
                "supervisor": supervisor_source,
                "executor": executor_source,
                "reporter": "direct_artifact",
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
        bundle_out.update(
            {
                "trade_id": "",
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

        bundle_json = report_dir / f"live_execution_bundle_{run_id}.json"
        bundle_md = report_dir / f"live_execution_bundle_{run_id}.md"
        bundle_out["report_json_path"] = str(bundle_json)
        bundle_out["report_md_path"] = str(bundle_md)
        bundle_json.write_text(json.dumps(bundle_out, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_md.write_text(render_bundle_markdown(bundle_out), encoding="utf-8")
        run_bundles_by_run[run_id] = bundle_out

        story_type = str(story_contract.get("story_type") or "unknown")
        run_story_type_counts[story_type] = int(run_story_type_counts.get(story_type, 0) + 1)
        run_bundle_rows.append(
            {
                "run_id": run_id,
                "trade_id": "",
                "story_id": story_id,
                "story_type": story_type,
                "action": execution.get("action"),
                "symbol": execution.get("symbol"),
                "qty": execution.get("qty"),
                "status": execution.get("status"),
                "report_json_path": str(bundle_json),
                "report_md_path": str(bundle_md),
                "trade_story_input_path": "",
                "trade_report_json_path": "",
                "trade_report_md_path": "",
                "trade_lifecycle_json_path": "",
                "trade_provenance_json_path": "",
                "trade_health_json_path": "",
                "trade_artifact_links_json_path": "",
                "trade_report_summary": "",
                "report_status": "failed",
                "report_reason_code": "missing_report_linkage",
                "report_reason_human": _report_reason_human("missing_report_linkage"),
                "report_next_expected_step": _report_next_step("missing_report_linkage"),
                "report_generation_model": configured_report_model,
                "report_generation_attempted": False,
            }
        )

    run_snapshots = _build_run_snapshots(event_log_path, day, reports_root=reports_root)
    trade_lifecycles = _build_trade_lifecycles(
        day=day,
        run_snapshots=run_snapshots,
        run_bundles=run_bundles_by_run,
    )
    lifecycle_rows: List[Dict[str, Any]] = []
    lifecycle_story_type_counts: Dict[str, int] = {}
    run_bundle_lookup = {str(row.get("run_id") or ""): row for row in run_bundle_rows}

    for lifecycle in trade_lifecycles:
        trade_id = str(lifecycle.get("trade_id") or "").strip()
        if not trade_id:
            continue
        symbol = normalize_symbol(lifecycle.get("symbol") or "", allow_test_symbols=True)
        status = str(lifecycle.get("status") or "open").strip().lower()
        story_type = str(lifecycle.get("story_type") or "decision_only").strip().lower()
        execution_mode_label_text = str(lifecycle.get("execution_mode_label") or "decision only").strip()

        entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        exit_action = str(exit_ctx.get("action") or "").strip().upper()
        entry_run_id = str(entry_ctx.get("run_id") or "")
        exit_run_id = str(exit_ctx.get("run_id") or "")
        linked_run_ids = [str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        hold_run_ids = [str(x or "").strip() for x in list(holding.get("run_ids") or []) if str(x or "").strip()]

        anchor_run_id = entry_run_id or exit_run_id or (linked_run_ids[0] if linked_run_ids else "")
        anchor_bundle = run_bundles_by_run.get(anchor_run_id) if isinstance(run_bundles_by_run.get(anchor_run_id), dict) else {}
        anchor_execution = anchor_bundle.get("execution") if isinstance(anchor_bundle.get("execution"), dict) else {}
        if not anchor_execution:
            anchor_execution = {
                "run_id": anchor_run_id,
                "action": str(entry_ctx.get("action") or exit_ctx.get("action") or ("BUY" if status == "open" else "WAIT")),
                "symbol": symbol,
                "qty": safe_int(entry_ctx.get("qty"), safe_int(exit_ctx.get("qty"), 0)),
                "status": str((exit_ctx.get("execution_context") or {}).get("outcome") or ""),
                "ord_no": "",
                "ts": str(entry_ctx.get("ts") or exit_ctx.get("ts") or ""),
            }

        summary_obj = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
        reporter_obj = lifecycle.get("reporter") if isinstance(lifecycle.get("reporter"), dict) else {}
        latest_holding_event = (
            list(holding.get("holding_events") or [])[-1]
            if isinstance(holding.get("holding_events"), list) and list(holding.get("holding_events") or [])
            else {}
        )
        latest_holding_monitor_context = (
            dict(latest_holding_event.get("monitor_context") or {})
            if isinstance(latest_holding_event, dict) and isinstance(latest_holding_event.get("monitor_context"), dict)
            else {}
        )
        exit_monitor_context = dict(exit_ctx.get("monitor_context") or {}) if isinstance(exit_ctx.get("monitor_context"), dict) else {}
        exit_guard_context = dict(exit_ctx.get("guard_context") or {}) if isinstance(exit_ctx.get("guard_context"), dict) else {}
        exit_execution_context = dict(exit_ctx.get("execution_context") or {}) if isinstance(exit_ctx.get("execution_context"), dict) else {}
        merged_exit_monitor_context = dict(latest_holding_monitor_context)
        if exit_monitor_context:
            merged_exit_monitor_context.update(exit_monitor_context)
        if status == "closed" and merged_exit_monitor_context:
            lifecycle_monitor_reason_human = build_monitor_reason_human(
                merged_exit_monitor_context,
                {"action": exit_action or "SELL"},
            )
        elif latest_holding_monitor_context:
            lifecycle_monitor_reason_human = build_monitor_reason_human(
                latest_holding_monitor_context,
                {"action": "HOLD"},
            )
        else:
            lifecycle_monitor_reason_human = dict(
                anchor_bundle.get("monitor_reason_human")
                or exit_ctx.get("monitor_context")
                or {}
            )
        lifecycle_monitor_reason_human = _backfill_open_lifecycle_monitor_reason(
            lifecycle_monitor_reason_human,
            lifecycle_status=status,
            symbol=symbol,
            state_obj=runtime_state,
        )
        story_contract = {
            "story_available": True,
            "story_type": story_type,
            "execution_mode_label": execution_mode_label_text,
            "story_anchor": f"{anchor_execution.get('action') or 'WAIT'} {symbol or '-'} x{safe_int(anchor_execution.get('qty'), 0)} | trade {trade_id}",
            "warnings": list(lifecycle.get("warnings") or []),
        }
        lifecycle_bundle: Dict[str, Any] = {
            "schema_version": "live_execution_bundle.v3",
            "artifact_type": "aggregated_execution_bundle",
            "ts": utc_now_iso(),
            "day": day,
            "run_id": anchor_run_id,
            "trade_id": trade_id,
            "story_id": trade_id,
            "linked_run_ids": linked_run_ids,
            "trade_lifecycle_status": status,
            "trade_lifecycle_summary": str(summary_obj.get("lifecycle_summary_human") or ""),
            "story_contract": story_contract,
            "execution": dict(anchor_execution),
            "commander": dict(anchor_bundle.get("commander") or {}),
            "strategist": dict(anchor_bundle.get("strategist") or {}),
            "scanner": dict(anchor_bundle.get("scanner") or {}),
            "monitor": dict(anchor_bundle.get("monitor") or {}),
            "supervisor": dict(anchor_bundle.get("supervisor") or {}),
            "executor": dict(anchor_bundle.get("executor") or {}),
            "reporter": dict(anchor_bundle.get("reporter") or {}),
            "canonical_agent_artifacts": dict(anchor_bundle.get("canonical_agent_artifacts") or {}),
            "evidence_provenance": dict(anchor_bundle.get("evidence_provenance") or {}),
            "market_context_human": dict(anchor_bundle.get("market_context_human") or entry_ctx.get("strategist_context") or {}),
            "scanner_reason_human": dict(anchor_bundle.get("scanner_reason_human") or entry_ctx.get("scanner_context") or {}),
            "filters_human": dict(anchor_bundle.get("filters_human") or {}),
            "monitor_reason_human": lifecycle_monitor_reason_human,
            "guard_reason_human": dict(exit_guard_context or anchor_bundle.get("guard_reason_human") or {}),
            "execution_outcome_human": dict(exit_execution_context or anchor_bundle.get("execution_outcome_human") or {}),
            "reporter_status_human": {
                "status": str(reporter_obj.get("status_human") or "missing"),
                "summary": str(reporter_obj.get("summary") or ""),
                "grade": str(reporter_obj.get("grade") or "N/A"),
                "bullets": [str(x or "") for x in list(reporter_obj.get("improvement_points") or [])[:6]],
            },
            "operator_conclusion_human": {
                "current_action": str(exit_action or ("HOLD" if status == "open" else anchor_execution.get("action") or "WAIT")),
                "summary": str(summary_obj.get("operator_conclusion_human") or ""),
                "watch_next": [f"Lifecycle status: {status}", "Monitor trigger changes", "Macro/news shifts"],
                "thesis_invalidation": ["stop-loss breach", "monitor and scanner divergence", "negative macro regime shift"],
            },
            "timeline": list(lifecycle.get("timeline") or []),
            "warnings": list(story_contract.get("warnings") or []),
            "trade_lifecycle": lifecycle,
            "artifacts": {
                "agent_pipeline_trace_json": str(anchor_bundle.get("artifacts", {}).get("agent_pipeline_trace_json") or ""),
                "agent_pipeline_trace_md": str(anchor_bundle.get("artifacts", {}).get("agent_pipeline_trace_md") or ""),
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

        trade_paths = trade_artifact_paths(reports_root, day, trade_id)
        trade_root = trade_paths["trade_root"]
        trade_root.mkdir(parents=True, exist_ok=True)
        for key in ("reports_dir", "evidence_dir"):
            trade_paths[key].mkdir(parents=True, exist_ok=True)
        lifecycle_bundle_path = trade_paths["lifecycle_bundle_json"]
        entry_artifact_path = trade_paths["entry_json"]
        hold_artifact_path = trade_paths["hold_json"]
        exit_artifact_path = trade_paths["exit_json"]
        story_input_path = trade_paths["ai_trade_report_input_json"]
        story_compact_input_path = trade_paths["ai_trade_report_compact_input_json"]
        trade_report_json_path = trade_paths["ai_trade_report_json"]
        trade_report_md_path = trade_paths["ai_trade_report_md"]
        operator_brief_json_path = trade_paths["brief_json"]
        operator_brief_md_path = trade_paths["brief_md"]
        brief_llm_response_path = trade_paths["brief_llm_response_json"]
        strategist_input_path = trade_paths["strategist_input_json"]
        strategist_compact_input_path = trade_paths["strategist_compact_input_json"]
        strategist_llm_response_path = trade_paths["strategist_llm_response_json"]
        ai_trade_report_llm_response_path = trade_paths["ai_trade_report_llm_response_json"]
        strategist_evidence_path = trade_paths["strategist_evidence_json"]
        scanner_evidence_path = trade_paths["scanner_evidence_json"]
        monitor_evidence_path = trade_paths["monitor_evidence_json"]
        commander_evidence_path = trade_paths["commander_evidence_json"]
        trade_provenance_path = trade_paths["trade_provenance_json"]
        trade_health_path = trade_paths["trade_health_json"]
        trade_artifact_links_path = trade_paths["trade_artifact_links_json"]
        existing_normalized_bundle = _read_json_if_exists(lifecycle_bundle_path)
        if not existing_normalized_bundle:
            existing_normalized_bundle = _read_json_if_exists(trade_paths["aggregated_execution_bundle_json"])
        if not existing_normalized_bundle:
            existing_normalized_bundle = _read_json_if_exists(trade_paths["legacy_normalized_aggregated_execution_bundle_json"])
        if isinstance(existing_normalized_bundle, dict) and existing_normalized_bundle:
            for agent_key in ("commander", "strategist", "scanner", "monitor", "supervisor", "executor", "reporter"):
                normalized_payload = (
                    existing_normalized_bundle.get(agent_key)
                    if isinstance(existing_normalized_bundle.get(agent_key), dict)
                    else {}
                )
                current_payload = (
                    lifecycle_bundle.get(agent_key)
                    if isinstance(lifecycle_bundle.get(agent_key), dict)
                    else {}
                )
                if _has_meaningful_payload(normalized_payload):
                    lifecycle_bundle[agent_key] = {**dict(current_payload or {}), **dict(normalized_payload or {})}
                    evidence_provenance = (
                        lifecycle_bundle.get("evidence_provenance")
                        if isinstance(lifecycle_bundle.get("evidence_provenance"), dict)
                        else {}
                    )
                    evidence_provenance = dict(evidence_provenance)
                    evidence_provenance[agent_key] = "normalized_trade_artifact"
                    lifecycle_bundle["evidence_provenance"] = evidence_provenance

        strategist_evidence, scanner_evidence, monitor_timeline = _build_trade_evidence_from_events(
            event_rows=day_event_rows,
            lifecycle=lifecycle,
        )
        lifecycle_bundle["strategist"] = _hydrate_strategist_payload_from_evidence(
            dict(lifecycle_bundle.get("strategist") or {}),
            strategist_evidence,
        )
        existing_market_context = (
            lifecycle_bundle.get("market_context_human")
            if isinstance(lifecycle_bundle.get("market_context_human"), dict)
            else {}
        )
        existing_regime = str(existing_market_context.get("regime") or "").strip().lower()
        existing_playbook = str(existing_market_context.get("playbook") or "").strip().lower()
        existing_vix = existing_market_context.get("vix_level")
        if (
            not existing_market_context
            or existing_regime in {"", "not_captured"}
            or existing_playbook in {"", "not_captured"}
            or existing_vix in (None, "", "not_captured")
        ):
            lifecycle_bundle["market_context_human"] = build_market_context_human(
                lifecycle_bundle.get("strategist") if isinstance(lifecycle_bundle.get("strategist"), dict) else {}
            )
        commander_evidence = build_commander_evidence(
            lifecycle_bundle.get("commander") if isinstance(lifecycle_bundle.get("commander"), dict) else {}
        )
        write_json(strategist_evidence_path, strategist_evidence)
        write_json(scanner_evidence_path, scanner_evidence)
        write_json(monitor_evidence_path, monitor_timeline)
        write_json(commander_evidence_path, commander_evidence)
        lifecycle["evidence"] = {
            "paths": {
                "strategist_evidence_json": str(strategist_evidence_path),
                "scanner_evidence_json": str(scanner_evidence_path),
                "monitor_evidence_json": str(monitor_evidence_path),
                "monitor_timeline_json": str(monitor_evidence_path),
                "commander_evidence_json": str(commander_evidence_path),
            },
            "strategist_event_count": sum(len(list(strategist_evidence.get(key) or [])) for key in ("market_context_snapshots", "global_sentiment_breakdowns", "news_evidence_ranked", "decision_frames", "llm_response_saved")),
            "scanner_event_count": sum(len(list(scanner_evidence.get(key) or [])) for key in ("candidate_pool_snapshots", "candidate_ranking_tables", "candidate_selection_reasons", "selection_outputs")),
            "monitor_event_count": sum(
                len(list(monitor_timeline.get(key) or []))
                for key in ("threshold_snapshots", "state_transitions", "entry_decision_details", "exit_decision_details", "cycle_summaries")
            ),
            "commander_event_count": 1 if commander_evidence else 0,
        }

        strategist_input_artifact, strategist_compact_input_artifact = _build_strategist_input_artifacts(
            lifecycle_bundle,
            day=day,
            trade_id=trade_id,
            strategist_evidence=strategist_evidence,
            evidence_rows=day_evidence_rows,
        )
        lifecycle_bundle["strategist"] = _enrich_strategist_from_input_summary(
            lifecycle_bundle.get("strategist") if isinstance(lifecycle_bundle.get("strategist"), dict) else {},
            strategist_input_artifact,
        )
        lifecycle_bundle["market_context_human"] = build_market_context_human(
            lifecycle_bundle.get("strategist") if isinstance(lifecycle_bundle.get("strategist"), dict) else {}
        )
        lifecycle_bundle["scanner_reason_human"] = build_scanner_reason_human(
            lifecycle_bundle.get("scanner") if isinstance(lifecycle_bundle.get("scanner"), dict) else {},
            lifecycle_bundle.get("strategist") if isinstance(lifecycle_bundle.get("strategist"), dict) else {},
        )
        lifecycle_bundle["scanner_reason_human"] = _enrich_scanner_reason_from_evidence(
            lifecycle_bundle.get("scanner_reason_human")
            if isinstance(lifecycle_bundle.get("scanner_reason_human"), dict)
            else {},
            scanner_evidence,
        )
        lifecycle_bundle["filters_human"] = build_filters_human(
            lifecycle_bundle.get("scanner") if isinstance(lifecycle_bundle.get("scanner"), dict) else {},
            lifecycle_bundle.get("strategist") if isinstance(lifecycle_bundle.get("strategist"), dict) else {},
            lifecycle_bundle.get("supervisor") if isinstance(lifecycle_bundle.get("supervisor"), dict) else {},
        )
        lifecycle_bundle["filters_human"] = _enrich_filters_from_evidence(
            lifecycle_bundle.get("filters_human") if isinstance(lifecycle_bundle.get("filters_human"), dict) else {},
            scanner_evidence,
            selected_symbol=str(
                (
                    lifecycle_bundle.get("scanner_reason_human")
                    if isinstance(lifecycle_bundle.get("scanner_reason_human"), dict)
                    else {}
                ).get("selected_symbol")
                or symbol
            ),
        )
        strategy_anchor_run_id = str(
            ((strategist_input_artifact.get("meta") or {}).get("source_run_id") or "")
            or entry_run_id
            or anchor_run_id
            or ""
        ).strip()
        lifecycle["entry_strategist_run_id"] = strategy_anchor_run_id
        lifecycle["strategy_anchor_run_id"] = strategy_anchor_run_id
        lifecycle["strategy_anchor"] = {
            "run_id": strategy_anchor_run_id,
            "source": "strategist_input_artifact" if strategy_anchor_run_id else "missing",
            "artifacts": {
                "strategist_input_json": str(strategist_input_path),
                "strategist_compact_input_json": str(strategist_compact_input_path),
                "strategist_llm_response_json": str(strategist_llm_response_path),
            },
        }
        lifecycle_bundle["entry_strategist_run_id"] = strategy_anchor_run_id
        lifecycle_bundle["strategy_anchor_run_id"] = strategy_anchor_run_id
        lifecycle_bundle["market_context_human"] = _attach_strategy_anchor(
            lifecycle_bundle.get("market_context_human") if isinstance(lifecycle_bundle.get("market_context_human"), dict) else {},
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        lifecycle_bundle["scanner_reason_human"] = _attach_strategy_anchor(
            lifecycle_bundle.get("scanner_reason_human") if isinstance(lifecycle_bundle.get("scanner_reason_human"), dict) else {},
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        lifecycle_bundle["monitor_reason_human"] = _attach_strategy_anchor(
            lifecycle_bundle.get("monitor_reason_human") if isinstance(lifecycle_bundle.get("monitor_reason_human"), dict) else {},
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        entry_ctx_live = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        if not entry_ctx_live:
            exit_seed = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
            exit_monitor_seed = exit_seed.get("monitor_context") if isinstance(exit_seed.get("monitor_context"), dict) else {}
            inferred_entry_price = (
                exit_monitor_seed.get("average_price")
                or exit_monitor_seed.get("avg_price")
                or exit_monitor_seed.get("current_price")
                or exit_seed.get("price")
            )
            entry_ctx_live = {
                "run_id": str(strategy_anchor_run_id or ""),
                "ts": "",
                "action": "BUY",
                "price": inferred_entry_price,
                "qty": safe_int(exit_seed.get("qty"), 0),
                "reason_human": "Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts.",
                "strategist_context": {},
                "scanner_context": {},
                "monitor_context": {},
                "guard_context": {},
                "execution_context": {},
                "inferred_entry": True,
            }
            lifecycle["entry"] = entry_ctx_live
            lifecycle.setdefault("warnings", []).append(
                "Entry evidence was missing; lifecycle entry context was inferred from available artifacts."
            )
        if entry_ctx_live:
            refreshed_strategist_context = dict(entry_ctx_live.get("strategist_context") or {}) if isinstance(entry_ctx_live.get("strategist_context"), dict) else {}
            refreshed_market_context = (
                lifecycle_bundle.get("market_context_human")
                if isinstance(lifecycle_bundle.get("market_context_human"), dict)
                else {}
            )
            strategist_summary_payload = (
                lifecycle_bundle.get("strategist_summary")
                if isinstance(lifecycle_bundle.get("strategist_summary"), dict)
                else {}
            )
            strategist_policy = (
                strategist_summary_payload.get("policy_selected")
                if isinstance(strategist_summary_payload.get("policy_selected"), dict)
                else {}
            )
            scanner_summary_payload = (
                lifecycle_bundle.get("scanner_summary")
                if isinstance(lifecycle_bundle.get("scanner_summary"), dict)
                else {}
            )
            scanner_source_refs = (
                scanner_summary_payload.get("source_refs")
                if isinstance(scanner_summary_payload.get("source_refs"), dict)
                else {}
            )
            if refreshed_market_context:
                refreshed_strategist_context["market_context_summary"] = str(
                    refreshed_market_context.get("summary")
                    or refreshed_strategist_context.get("market_context_summary")
                    or ""
                )
            if not str(refreshed_strategist_context.get("playbook") or "").strip():
                fallback_playbook = str(
                    strategist_summary_payload.get("playbook")
                    or strategist_policy.get("playbook")
                    or scanner_source_refs.get("strategist_playbook")
                    or ""
                ).strip()
                if fallback_playbook:
                    refreshed_strategist_context["playbook"] = fallback_playbook
            if not list(refreshed_strategist_context.get("themes") or []):
                fallback_themes = [
                    str(item or "").strip()
                    for item in list(
                        strategist_summary_payload.get("themes")
                        or strategist_policy.get("themes")
                        or []
                    )
                    if str(item or "").strip()
                ]
                if fallback_themes:
                    refreshed_strategist_context["themes"] = fallback_themes[:6]
            entry_ctx_live["strategist_context"] = _attach_strategy_anchor(
                refreshed_strategist_context,
                strategy_anchor_run_id=strategy_anchor_run_id,
                strategist_input_path=strategist_input_path,
                strategist_compact_input_path=strategist_compact_input_path,
                strategist_llm_response_path=strategist_llm_response_path,
            )
            refreshed_scanner_context = (
                dict(lifecycle_bundle.get("scanner_reason_human") or {})
                if isinstance(lifecycle_bundle.get("scanner_reason_human"), dict)
                else dict(entry_ctx_live.get("scanner_context") or {})
                if isinstance(entry_ctx_live.get("scanner_context"), dict)
                else {}
            )
            current_entry_reason = str(entry_ctx_live.get("reason_human") or "").strip()
            if _is_placeholder_entry_reason(current_entry_reason):
                fallback_entry_reason = str(
                    refreshed_scanner_context.get("summary")
                    or (
                        lifecycle_bundle.get("monitor_reason_human").get("summary")
                        if isinstance(lifecycle_bundle.get("monitor_reason_human"), dict)
                        else ""
                    )
                    or (
                        lifecycle_bundle.get("execution_outcome_human").get("summary")
                        if isinstance(lifecycle_bundle.get("execution_outcome_human"), dict)
                        else ""
                    )
                    or current_entry_reason
                ).strip()
                if fallback_entry_reason:
                    entry_ctx_live["reason_human"] = fallback_entry_reason
            if entry_ctx_live.get("price") is None or entry_ctx_live.get("price") == "":
                execution_payload = (
                    lifecycle_bundle.get("execution")
                    if isinstance(lifecycle_bundle.get("execution"), dict)
                    else {}
                )
                fallback_price = (
                    execution_payload.get("price")
                    or execution_payload.get("order_price")
                    or execution_payload.get("avg_price")
                )
                if (fallback_price is None or fallback_price == "") and isinstance(refreshed_scanner_context.get("selected_candidate"), dict):
                    selected_candidate = dict(refreshed_scanner_context.get("selected_candidate") or {})
                    feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
                    fallback_price = feature_snapshot.get("skill_quote_price")
                if fallback_price is None or fallback_price == "":
                    holding_for_price = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
                    first_monitor_ctx = {}
                    for row in list(holding_for_price.get("holding_events") or []):
                        if isinstance(row, dict) and isinstance(row.get("monitor_context"), dict):
                            first_monitor_ctx = dict(row.get("monitor_context") or {})
                            break
                    fallback_price = first_monitor_ctx.get("current_price") or first_monitor_ctx.get("price")
                if fallback_price is not None and fallback_price != "":
                    entry_ctx_live["price"] = fallback_price
            entry_ctx_live["scanner_context"] = _attach_strategy_anchor(
                refreshed_scanner_context,
                strategy_anchor_run_id=strategy_anchor_run_id,
                strategist_input_path=strategist_input_path,
                strategist_compact_input_path=strategist_compact_input_path,
                strategist_llm_response_path=strategist_llm_response_path,
            )
            entry_ctx_live["monitor_context"] = _attach_strategy_anchor(
                entry_ctx_live.get("monitor_context") if isinstance(entry_ctx_live.get("monitor_context"), dict) else {},
                strategy_anchor_run_id=strategy_anchor_run_id,
                strategist_input_path=strategist_input_path,
                strategist_compact_input_path=strategist_compact_input_path,
                strategist_llm_response_path=strategist_llm_response_path,
            )
            entry_reason_final = str(entry_ctx_live.get("reason_human") or "").strip()
            if entry_reason_final:
                if isinstance(summary_obj, dict):
                    summary_obj["entry_reason_human"] = entry_reason_final
                current_lifecycle_summary = str(lifecycle_bundle.get("trade_lifecycle_summary") or "")
                if "Entry reason was not captured" in current_lifecycle_summary:
                    exit_ctx_summary = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
                    exit_reason_final = str(exit_ctx_summary.get("reason_human") or "Exit reason was not captured.").strip()
                    refreshed_lifecycle_summary = (
                        f"Trade {trade_id} for {symbol} is {status}. "
                        f"Entry: {entry_reason_final} "
                        f"Exit: {exit_reason_final}"
                    )
                    lifecycle_bundle["trade_lifecycle_summary"] = refreshed_lifecycle_summary
                    if isinstance(summary_obj, dict):
                        summary_obj["lifecycle_summary_human"] = refreshed_lifecycle_summary
                        lifecycle["summary"] = summary_obj
            lifecycle["entry"] = entry_ctx_live
        exit_ctx_live = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        if exit_ctx_live:
            exit_ctx_live["monitor_context"] = _attach_strategy_anchor(
                exit_ctx_live.get("monitor_context") if isinstance(exit_ctx_live.get("monitor_context"), dict) else {},
                strategy_anchor_run_id=strategy_anchor_run_id,
                strategist_input_path=strategist_input_path,
                strategist_compact_input_path=strategist_compact_input_path,
                strategist_llm_response_path=strategist_llm_response_path,
            )
            lifecycle["exit"] = exit_ctx_live
        holding_live = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        if isinstance(holding_live.get("holding_events"), list):
            updated_events: List[Dict[str, Any]] = []
            for event in list(holding_live.get("holding_events") or []):
                event_obj = dict(event or {})
                event_obj["monitor_context"] = _attach_strategy_anchor(
                    event_obj.get("monitor_context") if isinstance(event_obj.get("monitor_context"), dict) else {},
                    strategy_anchor_run_id=strategy_anchor_run_id,
                    strategist_input_path=strategist_input_path,
                    strategist_compact_input_path=strategist_compact_input_path,
                    strategist_llm_response_path=strategist_llm_response_path,
                )
                updated_events.append(event_obj)
            holding_live["holding_events"] = updated_events
            lifecycle["holding"] = holding_live
        trade_story_input = build_trade_story_input(lifecycle_bundle, trade_lifecycle=lifecycle)
        trade_story_input["day"] = day
        trade_story_input["entry_strategist_run_id"] = strategy_anchor_run_id
        trade_story_input["strategy_anchor_run_id"] = strategy_anchor_run_id
        diagnostics, should_attempt_generation = _seed_diagnostics_for_policy(
            lifecycle_status=status,
            story_type=story_type,
            report_requested=report_requested,
            story_input_available=bool(trade_story_input),
            model_hint=configured_report_model,
        )

        strategist_llm_artifact_raw = _build_strategist_llm_response_artifact(
            lifecycle_bundle,
            day=day,
            trade_id=trade_id,
            strategist_evidence=strategist_evidence,
            evidence_rows=day_evidence_rows,
        )
        strategist_llm_artifact = persist_llm_artifact_refs(
            artifact=strategist_llm_artifact_raw,
            reports_root=reports_root,
            day=day,
            run_id=str(strategy_anchor_run_id or anchor_run_id or ""),
            component="strategist",
        )
        write_json(strategist_llm_response_path, strategist_llm_artifact)
        existing_brief_llm_artifact = _read_json_if_exists(trade_paths["brief_llm_response_json"])
        diagnostics["llm_brief_status"] = canonical_llm_status(
            existing_brief_llm_artifact.get("llm_status") or existing_brief_llm_artifact.get("status") or "skipped",
            default="skipped",
        )

        deterministic_report = build_deterministic_trade_report(trade_story_input)
        trade_report: Dict[str, Any] = dict(deterministic_report)
        diagnostics["deterministic_report_status"] = "ok"
        diagnostics["ai_trade_report_status"] = "skipped"
        ai_trade_report_llm_artifact: Dict[str, Any] = {}
        existing_trade_report_artifact = _read_json_if_exists(trade_report_json_path)
        existing_ai_trade_report_llm_artifact = _read_json_if_exists(ai_trade_report_llm_response_path)
        if should_attempt_generation:
            diagnostics["generation_attempted"] = True
            diagnostics["generation_ts"] = utc_now_iso()
            ai_trade_report = build_ai_trade_report(
                trade_story_input,
                enabled=True,
                model=str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else configured_report_model,
                temperature=args.trade_report_ai_temperature,
                max_tokens=args.trade_report_ai_max_tokens,
            )
            ai_trade_report_llm_artifact = (
                ai_trade_report.get("llm_response_artifact")
                if isinstance(ai_trade_report.get("llm_response_artifact"), dict)
                else {}
            )
            generation = ai_trade_report.get("generation") if isinstance(ai_trade_report.get("generation"), dict) else {}
            ai_status = canonical_llm_status(
                ai_trade_report.get("ai_trade_report_status")
                or generation.get("ai_trade_report_status")
                or generation.get("status")
                or ai_trade_report.get("status")
                or "error",
                default="error",
            )
            diagnostics["ai_trade_report_status"] = ai_status
            diagnostics["llm_model_used"] = _normalize_model_name(generation.get("model") or configured_report_model) or "openrouter/free"
            if ai_status in {"ok", "salvaged", "partial"}:
                trade_report = dict(ai_trade_report)
                diagnostics["report_status"] = "available"
                diagnostics["report_reason_code"] = ""
                diagnostics["report_reason_human"] = (
                    "AI trade report was generated successfully."
                    if ai_status == "ok"
                    else "AI trade report was generated with recovery. Deterministic evidence remains the factual source."
                )
                diagnostics["next_expected_step"] = "Open the full report for detailed lifecycle analysis."
            else:
                trade_report = dict(deterministic_report)
                diagnostics["report_status"] = "available"
                diagnostics["report_reason_code"] = "llm_generation_failed"
                diagnostics["report_reason_human"] = "AI trade report generation failed. Deterministic report was preserved."
                diagnostics["next_expected_step"] = _report_next_step("llm_generation_failed")
                diagnostics["last_error_message"] = _sanitize_error_message(generation.get("reason"))
            diagnostics["report_generation_reason"] = str(diagnostics.get("report_reason_human") or "")
        elif existing_trade_report_artifact:
            if not report_requested:
                trade_report = dict(existing_trade_report_artifact)
            else:
                merged_existing = dict(deterministic_report)
                merged_existing.update(dict(existing_trade_report_artifact))
                trade_report = merged_existing
            status_source = trade_report if isinstance(trade_report, dict) else {}
            generation_source = status_source.get("generation") if isinstance(status_source.get("generation"), dict) else {}
            diagnostics["ai_trade_report_status"] = canonical_llm_status(
                status_source.get("ai_trade_report_status")
                or generation_source.get("ai_trade_report_status")
                or existing_ai_trade_report_llm_artifact.get("llm_status")
                or existing_ai_trade_report_llm_artifact.get("status")
                or "skipped",
                default="skipped",
            )
            diagnostics["report_status"] = "available"
            diagnostics["report_reason_code"] = ""
            diagnostics["report_reason_human"] = (
                "Existing trade report artifact was preserved because AI generation was not requested."
                if not report_requested
                else "Existing trade report artifact was reused."
            )
            diagnostics["next_expected_step"] = "Open the full report for detailed lifecycle analysis."
            diagnostics["report_generation_reason"] = str(diagnostics.get("report_reason_human") or "")
        else:
            diagnostics["report_status"] = "available"
            diagnostics["report_reason_code"] = "deterministic_only"
            diagnostics["report_reason_human"] = "Deterministic report was generated without AI expansion."
            diagnostics["next_expected_step"] = "Review deterministic report sections and evidence linkage."
            diagnostics["report_generation_reason"] = str(diagnostics.get("report_reason_human") or "")

        diagnostics["report_output_available"] = False
        diagnostics["report_artifact_available"] = False
        trade_report_json_written = ""
        trade_report_md_written = ""
        ai_trade_report_llm_response_written = ""
        try:
            trade_report_payload = dict(trade_report)
            trade_report_payload.setdefault("deterministic_report_status", diagnostics.get("deterministic_report_status", "ok"))
            trade_report_payload.setdefault("llm_brief_status", diagnostics.get("llm_brief_status", "skipped"))
            trade_report_payload.setdefault("ai_trade_report_status", diagnostics.get("ai_trade_report_status", "skipped"))
            trade_report_json_path.write_text(json.dumps(trade_report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            trade_report_md_path.write_text(render_trade_report_markdown(trade_report_payload), encoding="utf-8")
            trade_report_json_written = str(trade_report_json_path)
            trade_report_md_written = str(trade_report_md_path)
            diagnostics["report_output_available"] = True
            diagnostics["report_artifact_available"] = True
        except Exception as exc:
            diagnostics["deterministic_report_status"] = "error"
            diagnostics["report_status"] = "failed"
            diagnostics["report_reason_code"] = "artifact_write_failed"
            diagnostics["report_reason_human"] = _report_reason_human("artifact_write_failed")
            diagnostics["report_generation_reason"] = str(diagnostics.get("report_reason_human") or "")
            diagnostics["next_expected_step"] = _report_next_step("artifact_write_failed")
            diagnostics["last_error_message"] = _sanitize_error_message(exc)
            diagnostics["report_output_available"] = False
            diagnostics["report_artifact_available"] = False

        if ai_trade_report_llm_artifact:
            ai_trade_report_llm_compact = persist_llm_artifact_refs(
                artifact=ai_trade_report_llm_artifact,
                reports_root=reports_root,
                day=day,
                run_id=str(anchor_run_id or ""),
                component="ai_trade_report",
            )
            ai_trade_report_llm_response_written = str(write_json(ai_trade_report_llm_response_path, ai_trade_report_llm_compact))
            ai_trade_report_llm_artifact = ai_trade_report_llm_compact
        elif ai_trade_report_llm_response_path.exists():
            ai_trade_report_llm_response_written = str(ai_trade_report_llm_response_path)

        lifecycle["ai_report_diagnostics"] = dict(diagnostics)
        lifecycle["evidence_artifacts"] = dict(lifecycle.get("evidence") or {})
        lifecycle["section_provenance"] = dict(trade_story_input.get("section_provenance") or {})
        lifecycle_bundle["ai_report_diagnostics"] = dict(diagnostics)
        lifecycle_bundle["section_provenance"] = dict(trade_story_input.get("section_provenance") or {})
        lifecycle_bundle["evidence"] = {
            "strategist": strategist_evidence,
            "scanner": scanner_evidence,
            "monitor": monitor_timeline,
            "commander": commander_evidence,
            "paths": {
                "strategist_evidence_json": str(strategist_evidence_path),
                "scanner_evidence_json": str(scanner_evidence_path),
                "monitor_evidence_json": str(monitor_evidence_path),
                "commander_evidence_json": str(commander_evidence_path),
            },
        }
        trade_story_input["ai_report_diagnostics"] = dict(diagnostics)
        trade_story_input["strategist_evidence"] = dict(strategist_evidence)
        trade_story_input["scanner_evidence"] = dict(scanner_evidence)
        trade_story_input["monitor_timeline"] = dict(monitor_timeline)
        if trade_report:
            trade_report["ai_report_diagnostics"] = dict(diagnostics)

        lifecycle["ai_report_diagnostics"] = dict(diagnostics)
        lifecycle_bundle["ai_report_diagnostics"] = dict(diagnostics)
        trade_story_input["ai_report_diagnostics"] = dict(diagnostics)
        if trade_report:
            trade_report["ai_report_diagnostics"] = dict(diagnostics)
            if trade_report_json_written:
                trade_report_json_path.write_text(json.dumps(trade_report, ensure_ascii=False, indent=2), encoding="utf-8")
                trade_report_md_path.write_text(render_trade_report_markdown(trade_report), encoding="utf-8")

        lifecycle_bundle["artifacts"].update(
            {
                "lifecycle_bundle_json": str(lifecycle_bundle_path),
                "entry_json": str(entry_artifact_path),
                "hold_json": str(hold_artifact_path),
                "exit_json": str(exit_artifact_path),
                "brief_json": str(operator_brief_json_path),
                "brief_md": str(operator_brief_md_path),
                "ai_trade_report_input_json": str(story_input_path),
                "trade_story_input_json": str(story_input_path),
                "ai_trade_report_compact_input_json": str(story_compact_input_path),
                "deprecated_ai_trade_report_compact_input_json": str(story_compact_input_path),
                "deprecated_trade_report_json": "",
                "deprecated_trade_report_md": "",
                "ai_trade_report_json": trade_report_json_written,
                "ai_trade_report_md": trade_report_md_written,
                "operator_brief_json": str(operator_brief_json_path),
                "strategist_llm_response_json": str(strategist_llm_response_path),
                "ai_trade_report_llm_response_json": ai_trade_report_llm_response_written,
                "brief_llm_response_json": str(brief_llm_response_path),
                "strategist_evidence_json": str(strategist_evidence_path),
                "scanner_evidence_json": str(scanner_evidence_path),
                "monitor_evidence_json": str(monitor_evidence_path),
                "commander_evidence_json": str(commander_evidence_path),
                "trade_provenance_json": str(trade_provenance_path),
                "trade_health_json": str(trade_health_path),
                "trade_artifact_links_json": str(trade_artifact_links_path),
            }
        )
        for key in (
            "canonical_commander_json",
            "canonical_strategist_json",
            "canonical_scanner_json",
            "canonical_monitor_json",
            "canonical_supervisor_json",
            "canonical_executor_json",
            "lifecycle_bundle_json",
            "entry_json",
            "hold_json",
            "exit_json",
            "brief_json",
            "brief_md",
            "operator_brief_json",
            "ai_trade_report_json",
            "ai_trade_report_md",
            "ai_trade_report_compact_input_json",
            "strategist_llm_response_json",
            "ai_trade_report_llm_response_json",
            "brief_llm_response_json",
        ):
            lifecycle_bundle["artifacts"].setdefault(key, "")

        if trade_report:
            trade_report["paths"] = {
                **(trade_report.get("paths") if isinstance(trade_report.get("paths"), dict) else {}),
                "ai_trade_report_json": trade_report_json_written,
                "ai_trade_report_md": trade_report_md_written,
                "ai_trade_report_input_json": str(story_input_path),
                "ai_trade_report_compact_input_json": str(story_compact_input_path),
                "ai_trade_report_llm_response_json": ai_trade_report_llm_response_written,
                "strategist_input_json": "",
                "strategist_compact_input_json": "",
                "strategist_llm_response_json": str(strategist_llm_response_path),
                "trade_lifecycle_json": "",
                "aggregated_execution_bundle_json": "",
                "lifecycle_bundle_json": str(lifecycle_bundle_path),
                "entry_json": str(entry_artifact_path),
                "hold_json": str(hold_artifact_path),
                "exit_json": str(exit_artifact_path),
                "operator_brief_json": str(operator_brief_json_path),
                "operator_brief_md": str(operator_brief_md_path),
                "brief_llm_response_json": str(brief_llm_response_path),
                "trade_provenance_json": str(trade_provenance_path),
                "trade_health_json": str(trade_health_path),
                "trade_artifact_links_json": str(trade_artifact_links_path),
            }

        section_provenance = (
            trade_story_input.get("section_provenance")
            if isinstance(trade_story_input.get("section_provenance"), dict)
            else {}
        )
        evidence_completeness = compute_evidence_completeness(trade_story_input)
        artifact_presence = {
            "lifecycle_bundle_json": lifecycle_bundle_path.exists(),
            "entry_json": entry_artifact_path.exists(),
            "hold_json": hold_artifact_path.exists(),
            "exit_json": exit_artifact_path.exists(),
            "ai_trade_report_input_json": story_input_path.exists(),
            "ai_trade_report_compact_input_json": story_compact_input_path.exists(),
            "ai_trade_report_json": bool(trade_report_json_written),
            "ai_trade_report_md": bool(trade_report_md_written),
            "strategist_evidence_json": strategist_evidence_path.exists(),
            "scanner_evidence_json": scanner_evidence_path.exists(),
            "monitor_evidence_json": monitor_evidence_path.exists(),
            "commander_evidence_json": commander_evidence_path.exists(),
            "strategist_llm_response_json": strategist_llm_response_path.exists(),
            "ai_trade_report_llm_response_json": bool(ai_trade_report_llm_response_written),
            "brief_llm_response_json": trade_paths["brief_llm_response_json"].exists(),
        }
        def _source_type(raw_source: Any, source_path: Any) -> str:
            src = str(raw_source or "").strip().lower()
            path_text = str(source_path or "").strip()
            if src == "canonical":
                return "canonical"
            if src in {"normalized_trade_artifact", "normalized_trade", "direct_artifact", "direct"}:
                return "trade"
            if src in {"event_log"}:
                return "events"
            if path_text:
                return "trade"
            return "missing"
        trade_provenance_payload = {
            "schema_version": "trade_provenance.v1",
            "trade_id": trade_id,
            "run_id": anchor_run_id,
            "day": day,
            "lifecycle_status": status,
            "entry_strategist_run_id": strategy_anchor_run_id,
            "strategy_anchor_run_id": strategy_anchor_run_id,
            "evidence_source": str(trade_story_input.get("evidence_source") or "fallback"),
            "agent_sources": dict(lifecycle_bundle.get("evidence_provenance") or {}),
            "section_provenance": dict(section_provenance),
            "read_precedence": [
                "normalized_trade_artifact",
                "canonical_artifact",
                "event_log",
                "missing",
            ],
            "section_resolution": {
                str(key): {
                    "source_type": _source_type((value or {}).get("source"), (value or {}).get("artifact_path")),
                    "source_path": str((value or {}).get("artifact_path") or ""),
                    "confidence": str((value or {}).get("confidence") or "low"),
                }
                for key, value in dict(section_provenance or {}).items()
            },
            "canonical_agent_artifact_paths": {
                key: str(value or "")
                for key, value in dict(lifecycle_bundle.get("artifacts") or {}).items()
                if str(key).startswith("canonical_") and str(key).endswith("_json")
            },
        }
        phase3_completeness_axes = {
            "strategist_evidence": strategist_evidence_path.exists(),
            "scanner_evidence": scanner_evidence_path.exists(),
            "monitor_evidence": monitor_evidence_path.exists(),
            "commander_evidence": commander_evidence_path.exists(),
            "entry": bool(lifecycle.get("entry")),
            "exit": bool(lifecycle.get("exit")),
        }
        phase3_missing_sections = [key for key, present in phase3_completeness_axes.items() if not bool(present)]
        phase3_completeness_score = (
            float(sum(1 for present in phase3_completeness_axes.values() if bool(present))) / float(len(phase3_completeness_axes))
            if phase3_completeness_axes
            else 0.0
        )
        trade_health_payload = {
            "schema_version": "trade_health.v1",
            "trade_id": trade_id,
            "run_id": anchor_run_id,
            "day": day,
            "lifecycle_status": status,
            "ai_report_diagnostics": dict(diagnostics),
            "report_generation": dict(trade_report.get("generation") or {}) if isinstance(trade_report, dict) else {},
            "deterministic_report_status": str(diagnostics.get("deterministic_report_status") or "skipped"),
            "llm_brief_status": str(diagnostics.get("llm_brief_status") or "skipped"),
            "ai_trade_report_status": str(diagnostics.get("ai_trade_report_status") or "skipped"),
            "report_generation_reason": str(diagnostics.get("report_generation_reason") or diagnostics.get("report_reason_human") or ""),
            "missing_sections": phase3_missing_sections
            + [str(x or "") for x in list(evidence_completeness.get("missing_sections") or []) if str(x or "").strip()],
            "completeness_score": phase3_completeness_score,
            "artifact_presence": artifact_presence,
            "llm_response_status": str(ai_trade_report_llm_artifact.get("status") or ""),
            "llm_parse_mode": str(ai_trade_report_llm_artifact.get("parse_mode") or ""),
            "llm_completeness_score": float(ai_trade_report_llm_artifact.get("completeness_score") or 0.0),
            "llm_required_keys_missing": [str(x or "") for x in list(ai_trade_report_llm_artifact.get("required_keys_missing") or []) if str(x or "").strip()],
            "evidence_counts": {
                "strategist_events": int((lifecycle.get("evidence") or {}).get("strategist_event_count") or 0),
                "scanner_events": int((lifecycle.get("evidence") or {}).get("scanner_event_count") or 0),
                "monitor_events": int((lifecycle.get("evidence") or {}).get("monitor_event_count") or 0),
            },
        }
        resolved_operator_brief_json = str(
            (lifecycle_bundle.get("artifacts") or {}).get("operator_brief_json")
            or operator_brief_json_path
        )
        resolved_operator_brief_md = str(
            (lifecycle_bundle.get("artifacts") or {}).get("brief_md")
            or operator_brief_md_path
        )
        resolved_brief_llm_response_json = str(
            (lifecycle_bundle.get("artifacts") or {}).get("brief_llm_response_json")
            or brief_llm_response_path
        )
        trade_artifact_links_payload = {
            "schema_version": "trade_artifact_links.v2",
            "trade_id": trade_id,
            "run_id": anchor_run_id,
            "day": day,
            "canonical_commander": str((lifecycle_bundle.get("artifacts") or {}).get("canonical_commander_json") or ""),
            "canonical_strategist": str((lifecycle_bundle.get("artifacts") or {}).get("canonical_strategist_json") or ""),
            "canonical_scanner": str((lifecycle_bundle.get("artifacts") or {}).get("canonical_scanner_json") or ""),
            "canonical_monitor": str((lifecycle_bundle.get("artifacts") or {}).get("canonical_monitor_json") or ""),
            "lifecycle_bundle": str(lifecycle_bundle_path),
            "entry": str(entry_artifact_path),
            "hold": str(hold_artifact_path),
            "exit": str(exit_artifact_path),
            "operator_brief": resolved_operator_brief_json,
            "ai_trade_report": str(trade_report_json_written or ""),
            "llm_prompt_refs": {
                "strategist": str(strategist_llm_artifact.get("prompt_ref") or ""),
                "brief": str((existing_brief_llm_artifact or {}).get("prompt_ref") if isinstance(existing_brief_llm_artifact, dict) else ""),
                "ai_trade_report": str(ai_trade_report_llm_artifact.get("prompt_ref") or ""),
            },
            "llm_response_refs": {
                "strategist": str(strategist_llm_artifact.get("response_ref") or ""),
                "brief": str((existing_brief_llm_artifact or {}).get("response_ref") if isinstance(existing_brief_llm_artifact, dict) else ""),
                "ai_trade_report": str(ai_trade_report_llm_artifact.get("response_ref") or ""),
            },
            "links": {
                key: str(value or "")
                for key, value in dict(lifecycle_bundle.get("artifacts") or {}).items()
            },
        }
        trade_artifact_links_payload["links"]["brief_json"] = resolved_operator_brief_json
        trade_artifact_links_payload["links"]["operator_brief_json"] = resolved_operator_brief_json
        trade_artifact_links_payload["links"]["brief_md"] = resolved_operator_brief_md
        trade_artifact_links_payload["links"]["brief_llm_response_json"] = resolved_brief_llm_response_json
        trade_artifact_links_payload["links"]["strategist_llm_prompt_ref"] = str(strategist_llm_artifact.get("prompt_ref") or "")
        trade_artifact_links_payload["links"]["strategist_llm_response_ref"] = str(strategist_llm_artifact.get("response_ref") or "")
        trade_artifact_links_payload["links"]["brief_llm_prompt_ref"] = str((existing_brief_llm_artifact or {}).get("prompt_ref") if isinstance(existing_brief_llm_artifact, dict) else "")
        trade_artifact_links_payload["links"]["brief_llm_response_ref"] = str((existing_brief_llm_artifact or {}).get("response_ref") if isinstance(existing_brief_llm_artifact, dict) else "")
        trade_artifact_links_payload["links"]["ai_trade_report_llm_prompt_ref"] = str(ai_trade_report_llm_artifact.get("prompt_ref") or "")
        trade_artifact_links_payload["links"]["ai_trade_report_llm_response_ref"] = str(ai_trade_report_llm_artifact.get("response_ref") or "")

        write_json(story_input_path, trade_story_input)
        trade_story_compact_input = build_ai_trade_report_compact_input(trade_story_input)
        trade_story_compact_artifact = build_compact_input_artifact(
            component="ai_trade_report",
            run_id=str(anchor_run_id or ""),
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            source_artifact_path=str(story_input_path),
            source_input=trade_story_input,
            compact_input=trade_story_compact_input,
        )
        write_json(story_compact_input_path, trade_story_compact_artifact)
        entry_payload = dict(lifecycle.get("entry") or {})
        holding_payload = dict(lifecycle.get("holding") or {})
        exit_payload = dict(lifecycle.get("exit") or {})
        lifecycle_bundle_v1 = build_lifecycle_bundle(
            day=day,
            trade_id=trade_id,
            run_id=str(anchor_run_id or ""),
            symbol=symbol,
            lifecycle=lifecycle,
            strategist_summary=dict(lifecycle_bundle.get("strategist") or {}),
            scanner_summary=dict(lifecycle_bundle.get("scanner") or {}),
            monitor_summary=dict(lifecycle_bundle.get("monitor") or {}),
            commander_summary=dict(lifecycle_bundle.get("commander") or {}),
            story_input=trade_story_input,
            diagnostics={
                **dict(diagnostics or {}),
                "strategist_llm_status": str(strategist_llm_artifact.get("llm_status") or strategist_llm_artifact.get("status") or "skipped"),
            },
            canonical_refs={
                key: value
                for key, value in dict(lifecycle_bundle.get("artifacts") or {}).items()
                if str(key).startswith("canonical_") and str(key).endswith("_json")
            },
            llm_refs={
                "strategist_prompt_ref": str(strategist_llm_artifact.get("prompt_ref") or ""),
                "strategist_response_ref": str(strategist_llm_artifact.get("response_ref") or ""),
                "brief_prompt_ref": str((existing_brief_llm_artifact or {}).get("prompt_ref") if isinstance(existing_brief_llm_artifact, dict) else ""),
                "brief_response_ref": str((existing_brief_llm_artifact or {}).get("response_ref") if isinstance(existing_brief_llm_artifact, dict) else ""),
                "ai_trade_report_prompt_ref": str(ai_trade_report_llm_artifact.get("prompt_ref") or ""),
                "ai_trade_report_response_ref": str(ai_trade_report_llm_artifact.get("response_ref") or ""),
            },
            artifact_links={
                "lifecycle_bundle": str(lifecycle_bundle_path),
                "entry": str(entry_artifact_path),
                "hold": str(hold_artifact_path),
                "exit": str(exit_artifact_path),
                "operator_brief": resolved_operator_brief_json,
                "ai_trade_report": str(trade_report_json_written or trade_report_json_path),
            },
        )
        # Compatibility bridge: nested lifecycle_bundle fields remain the source of truth.
        # These flat keys stay available for older readers that still expect top-level fields.
        lifecycle_bundle_v1.update(
            {
                "ts": str(lifecycle_bundle.get("ts") or utc_now_iso()),
                "story_id": trade_id,
                "linked_run_ids": linked_run_ids,
                "trade_lifecycle_status": status,
                "trade_lifecycle_summary": str(summary_obj.get("lifecycle_summary_human") or ""),
                "story_contract": dict(story_contract or {}),
                "execution": dict(anchor_execution or {}),
                "artifacts": dict(lifecycle_bundle.get("artifacts") or {}),
                "evidence_provenance": dict(lifecycle_bundle.get("evidence_provenance") or {}),
                "section_provenance": dict(trade_story_input.get("section_provenance") or {}),
                "ai_report_diagnostics": dict(diagnostics or {}),
                "timeline": list(lifecycle.get("timeline") or []),
                "strategist_llm_status": str(
                    ((lifecycle_bundle_v1.get("llm_summary") or {}) if isinstance(lifecycle_bundle_v1.get("llm_summary"), dict) else {}).get("strategist_llm_status")
                    or diagnostics.get("strategist_llm_status")
                    or "skipped"
                ),
                "brief_llm_status": str(
                    ((lifecycle_bundle_v1.get("llm_summary") or {}) if isinstance(lifecycle_bundle_v1.get("llm_summary"), dict) else {}).get("brief_llm_status")
                    or diagnostics.get("llm_brief_status")
                    or "skipped"
                ),
                "ai_trade_report_status": str(
                    ((lifecycle_bundle_v1.get("llm_summary") or {}) if isinstance(lifecycle_bundle_v1.get("llm_summary"), dict) else {}).get("ai_report_status")
                    or diagnostics.get("ai_trade_report_status")
                    or "skipped"
                ),
                "operator_brief": resolved_operator_brief_json,
                "ai_trade_report": str(trade_report_json_written or trade_report_json_path),
                "lifecycle_bundle": str(lifecycle_bundle_path),
            }
        )
        write_json(entry_artifact_path, entry_payload)
        write_json(hold_artifact_path, holding_payload)
        write_json(exit_artifact_path, exit_payload)
        write_json(lifecycle_bundle_path, lifecycle_bundle_v1)
        write_json(trade_provenance_path, trade_provenance_payload)
        # Recompute artifact presence after writes to avoid false negatives in _health.json.
        artifact_presence = {
            "lifecycle_bundle_json": lifecycle_bundle_path.exists(),
            "entry_json": entry_artifact_path.exists(),
            "hold_json": hold_artifact_path.exists(),
            "exit_json": exit_artifact_path.exists(),
            "ai_trade_report_input_json": story_input_path.exists(),
            "ai_trade_report_compact_input_json": story_compact_input_path.exists(),
            "ai_trade_report_json": bool(trade_report_json_written),
            "ai_trade_report_md": bool(trade_report_md_written),
            "strategist_evidence_json": strategist_evidence_path.exists(),
            "scanner_evidence_json": scanner_evidence_path.exists(),
            "monitor_evidence_json": monitor_evidence_path.exists(),
            "commander_evidence_json": commander_evidence_path.exists(),
            "strategist_llm_response_json": strategist_llm_response_path.exists(),
            "ai_trade_report_llm_response_json": bool(ai_trade_report_llm_response_written),
            "brief_llm_response_json": trade_paths["brief_llm_response_json"].exists(),
        }
        trade_health_payload["artifact_presence"] = artifact_presence
        write_json(trade_health_path, trade_health_payload)
        write_json(trade_artifact_links_path, trade_artifact_links_payload)

        lifecycle_story_type_counts[story_type] = int(lifecycle_story_type_counts.get(story_type, 0) + 1)
        lifecycle_rows.append(
            {
                "trade_id": trade_id,
                "story_id": trade_id,
                "status": status,
                "story_type": story_type,
                "execution_mode_label": execution_mode_label_text,
                "symbol": symbol,
                "entry_run_id": entry_run_id,
                "hold_run_ids": hold_run_ids,
                "exit_run_id": exit_run_id,
                "linked_run_ids": linked_run_ids,
                "lifecycle_summary": str(summary_obj.get("lifecycle_summary_human") or ""),
                "report_json_path": str(lifecycle_bundle_path),
                "lifecycle_bundle_json_path": str(lifecycle_bundle_path),
                "trade_lifecycle_json_path": "",
                "trade_story_input_path": str(story_input_path),
                "ai_trade_report_input_path": str(story_input_path),
                "ai_trade_report_compact_input_path": str(story_compact_input_path),
                "trade_report_json_path": trade_report_json_written,
                "trade_report_md_path": trade_report_md_written,
                "ai_trade_report_json_path": trade_report_json_written,
                "ai_trade_report_md_path": trade_report_md_written,
                "strategist_llm_response_path": str(strategist_llm_response_path),
                "ai_trade_report_llm_response_path": ai_trade_report_llm_response_written,
                "entry_json_path": str(entry_artifact_path),
                "hold_json_path": str(hold_artifact_path),
                "exit_json_path": str(exit_artifact_path),
                "strategist_evidence_json_path": str(strategist_evidence_path),
                "scanner_evidence_json_path": str(scanner_evidence_path),
                "monitor_evidence_json_path": str(monitor_evidence_path),
                "monitor_timeline_json_path": str(monitor_evidence_path),
                "commander_evidence_json_path": str(commander_evidence_path),
                "trade_provenance_json_path": str(trade_provenance_path),
                "trade_health_json_path": str(trade_health_path),
                "trade_artifact_links_json_path": str(trade_artifact_links_path),
                "trade_root_path": str(trade_root),
                "trade_report_summary": str((trade_report.get("executive_summary") or {}).get("summary") or ""),
                "report_status": str(diagnostics.get("report_status") or ""),
                "report_reason_code": str(diagnostics.get("report_reason_code") or ""),
                "report_reason_human": str(diagnostics.get("report_reason_human") or ""),
                "report_next_expected_step": str(diagnostics.get("next_expected_step") or ""),
                "report_generation_model": str(diagnostics.get("llm_model_used") or ""),
                "report_generation_attempted": bool(diagnostics.get("generation_attempted")),
                "deterministic_report_status": str(diagnostics.get("deterministic_report_status") or ""),
                "llm_brief_status": str(diagnostics.get("llm_brief_status") or ""),
                "ai_trade_report_status": str(diagnostics.get("ai_trade_report_status") or ""),
            }
        )

        for rid in linked_run_ids:
            row = run_bundle_lookup.get(rid)
            if isinstance(row, dict):
                row["trade_id"] = trade_id
                row["story_id"] = trade_id
                row["lifecycle_bundle_json_path"] = str(lifecycle_bundle_path)
                row["trade_lifecycle_json_path"] = ""
                row["trade_story_input_path"] = str(story_input_path)
                row["ai_trade_report_input_path"] = str(story_input_path)
                row["ai_trade_report_compact_input_path"] = str(story_compact_input_path)
                row["trade_report_json_path"] = trade_report_json_written
                row["trade_report_md_path"] = trade_report_md_written
                row["ai_trade_report_json_path"] = trade_report_json_written
                row["ai_trade_report_md_path"] = trade_report_md_written
                row["strategist_llm_response_path"] = str(strategist_llm_response_path)
                row["ai_trade_report_llm_response_path"] = ai_trade_report_llm_response_written
                row["entry_json_path"] = str(entry_artifact_path)
                row["hold_json_path"] = str(hold_artifact_path)
                row["exit_json_path"] = str(exit_artifact_path)
                row["strategist_evidence_json_path"] = str(strategist_evidence_path)
                row["scanner_evidence_json_path"] = str(scanner_evidence_path)
                row["monitor_evidence_json_path"] = str(monitor_evidence_path)
                row["monitor_timeline_json_path"] = str(monitor_evidence_path)
                row["commander_evidence_json_path"] = str(commander_evidence_path)
                row["trade_provenance_json_path"] = str(trade_provenance_path)
                row["trade_health_json_path"] = str(trade_health_path)
                row["trade_artifact_links_json_path"] = str(trade_artifact_links_path)
                row["trade_root_path"] = str(trade_root)
                row["trade_report_summary"] = str((trade_report.get("executive_summary") or {}).get("summary") or "")
                row["report_status"] = str(diagnostics.get("report_status") or "")
                row["report_reason_code"] = str(diagnostics.get("report_reason_code") or "")
                row["report_reason_human"] = str(diagnostics.get("report_reason_human") or "")
                row["report_next_expected_step"] = str(diagnostics.get("next_expected_step") or "")
                row["report_generation_model"] = str(diagnostics.get("llm_model_used") or "")
                row["report_generation_attempted"] = bool(diagnostics.get("generation_attempted"))
                row["deterministic_report_status"] = str(diagnostics.get("deterministic_report_status") or "")
                row["llm_brief_status"] = str(diagnostics.get("llm_brief_status") or "")
                row["ai_trade_report_status"] = str(diagnostics.get("ai_trade_report_status") or "")
            bundle = run_bundles_by_run.get(rid)
            if isinstance(bundle, dict):
                bundle["trade_id"] = trade_id
                bundle["story_id"] = trade_id
                bundle["ai_report_diagnostics"] = dict(diagnostics)
                bundle.setdefault("artifacts", {})
                bundle["artifacts"].update(
                    {
                        "lifecycle_bundle_json": str(lifecycle_bundle_path),
                        "entry_json": str(entry_artifact_path),
                        "hold_json": str(hold_artifact_path),
                        "exit_json": str(exit_artifact_path),
                        "trade_story_input_json": str(story_input_path),
                        "ai_trade_report_input_json": str(story_input_path),
                        "ai_trade_report_compact_input_json": str(story_compact_input_path),
                        "trade_report_json": trade_report_json_written,
                        "trade_report_md": trade_report_md_written,
                        "ai_trade_report_json": trade_report_json_written,
                        "ai_trade_report_md": trade_report_md_written,
                        "strategist_llm_response_json": str(strategist_llm_response_path),
                        "ai_trade_report_llm_response_json": ai_trade_report_llm_response_written,
                        "strategist_evidence_json": str(strategist_evidence_path),
                        "scanner_evidence_json": str(scanner_evidence_path),
                        "monitor_evidence_json": str(monitor_evidence_path),
                        "monitor_timeline_json": str(monitor_evidence_path),
                        "commander_evidence_json": str(commander_evidence_path),
                    }
                )
                report_json_path = Path(str(bundle.get("report_json_path") or ""))
                if report_json_path.exists():
                    report_json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
                report_md_path = Path(str(bundle.get("report_md_path") or ""))
                if report_md_path.exists():
                    report_md_path.write_text(render_bundle_markdown(bundle), encoding="utf-8")

    report_status_counts: Dict[str, int] = {}
    for row in lifecycle_rows:
        key = str(row.get("report_status") or "").strip().lower() or "unknown"
        report_status_counts[key] = int(report_status_counts.get(key, 0) + 1)

    summary_out: Dict[str, Any] = {
        "schema_version": "live_execution_bundles.v3",
        "ok": True,
        "ts": utc_now_iso(),
        "day": day,
        "event_log_path": str(event_log_path),
        "evidence_log_path": str(evidence_log_path),
        "bundle_count": len(lifecycle_rows),
        "trade_lifecycle_count": len(lifecycle_rows),
        "run_bundle_count": len(run_bundle_rows),
        "story_type_counts": lifecycle_story_type_counts,
        "report_status_counts": report_status_counts,
        "run_story_type_counts": run_story_type_counts,
        "canonical_trades_root": str(canonical_trades_root),
        "bundles": lifecycle_rows,
        "run_bundles": run_bundle_rows,
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
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_out["report_json_path"] = str(summary_json)
    summary_out["report_md_path"] = str(summary_md)
    summary_json.write_text(json.dumps(summary_out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md.write_text(render_summary_markdown(summary_out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(summary_out, ensure_ascii=False))
    else:
        print(f"day={day} bundle_count={len(lifecycle_rows)} report_json={summary_json} report_md={summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
