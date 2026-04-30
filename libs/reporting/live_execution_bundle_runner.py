from __future__ import annotations

import argparse
import atexit
import contextlib
import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.core.symbols import normalize_symbol
from libs.llm.model_names import normalize_openrouter_model_name
from libs.runtime.windows_subprocess import background_creationflags, popen_hidden, run_hidden
from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report
from libs.reporting.intraday_trade_reports import (
    apply_live_bundle_backfill,
    execute_ai_trade_report_generation,
    apply_ai_trade_report_generation_result,
    apply_runtime_diagnostics_context,
    base_report_diagnostics as _base_diagnostics,
    build_live_bundle_backfill_payload,
    build_live_execution_summary_payload,
    build_live_generation_state_payload,
    build_holding_phase_observability as _build_holding_phase_observability,
    build_same_day_reporter_linkage as _build_same_day_reporter_linkage,
    load_report_generation_state as _load_report_generation_state,
    plan_live_trade_report_generation,
    persist_live_story_input_artifacts,
    report_next_step as _report_next_step,
    report_reason_human as _report_reason_human,
    report_generation_state_path as _report_generation_state_path,
    resolve_trade_report_policy as _resolve_trade_report_policy,
    seed_diagnostics_for_policy as _seed_diagnostics_for_policy,
    write_report_generation_state as _write_report_generation_state,
)
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
from libs.reporting.operator_summary_refresh import refresh_operator_summaries_after_trade
from libs.reporting.trade_explain import (
    generate_trade_explain_report,
    official_trade_explain_report_dir,
)
from libs.reporting.trade_report_ai import (
    build_ai_trade_report,
    build_ai_trade_report_compact_input,
    build_deterministic_trade_report,
    build_trade_summary_input,
    build_trade_summary_report,
    render_trade_report_markdown,
    render_trade_summary_markdown_with_evaluation,
)
from libs.reporting.trade_story_pipeline import (
    build_commander_evidence,
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
    build_trade_story_input_from_bundle,
    classify_story_type as _classify_story_type,
    collect_story_warnings,
    execution_mode_label,
    render_bundle_markdown,
    render_summary_markdown,
    safe_int,
    utc_now_iso,
)
from libs.reporting.trade_lifecycle_builder import (
    build_trade_lifecycles as _build_trade_lifecycles_lib,
    has_substantive_entry_evidence as _has_substantive_entry_evidence_lib,
    load_existing_open_lifecycle_candidates as _load_existing_open_lifecycle_candidates_lib,
)
from libs.reporting.trade_execution_snapshot import (
    build_execution_snapshot as _build_execution_snapshot_lib,
    normalize_execution_row as _normalize_execution_row_lib,
)
from libs.reporting.trade_fallback_text import lifecycle_conclusion_summary_is_placeholder
from libs.reporting.trade_bundle_assembly import (
    hydrate_live_run_bundle_context,
    build_live_run_bundle,
    apply_final_trade_report_context,
    apply_entry_exit_holding_enrichment,
    apply_trace_summary_context,
    apply_live_trade_context,
    apply_strategy_anchor_metadata,
    attach_strategy_anchor as _attach_strategy_anchor,
    build_scanner_trace_summary_mirror as _build_scanner_trace_summary_mirror,
    build_execution_details_from_bundle as _build_execution_details_from_bundle,
    build_strategist_trace_summary_mirror as _build_strategist_trace_summary_mirror,
    preferred_run_ids_for_agent as _preferred_run_ids_for_agent,
    resolve_lifecycle_bundle_sources as _resolve_lifecycle_bundle_sources,
)
from libs.reporting.trade_bundle_state import (
    build_live_trade_bundle_payloads,
    build_component_fingerprint as _build_component_fingerprint_lib,
    payload_fingerprint as _payload_fingerprint_lib,
    stable_json_text as _stable_json_text_lib,
)
from libs.reporting.trade_bundle_persistence import (
    persist_trade_report_outputs,
    refresh_trade_report_outputs_if_written,
    persist_trade_bundle_outputs,
    persist_trade_llm_artifacts,
)
from libs.runtime.canonical_artifacts import load_run_canonical_artifacts


def _runtime_minute_rows_for_symbol(runtime_state: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    candidates = [normalized]
    if normalized and not normalized.startswith("A"):
        candidates.append(f"A{normalized}")
    for root_key in ("recent_minute_ohlcv_by_symbol", "minute_ohlcv_by_symbol", "ohlcv_by_symbol"):
        root = runtime_state.get(root_key)
        if not isinstance(root, dict):
            continue
        for candidate in candidates:
            record = root.get(candidate)
            rows = record.get("rows") if isinstance(record, dict) else record
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _post_exit_shadow_from_lifecycle(lifecycle: Dict[str, Any], lifecycle_bundle: Dict[str, Any]) -> Dict[str, Any]:
    lifecycle_exit = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    for candidate in (
        lifecycle_bundle.get("post_exit_shadow"),
        lifecycle.get("post_exit_shadow"),
        lifecycle_exit.get("post_exit_shadow") if isinstance(lifecycle_exit, dict) else {},
    ):
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    return {}


def _attach_post_exit_shadow_to_trade_report(
    trade_report: Dict[str, Any],
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    shadow = _post_exit_shadow_from_lifecycle(lifecycle, lifecycle_bundle)
    if not shadow:
        return dict(trade_report or {})
    out = dict(trade_report or {})
    out["post_exit_shadow"] = dict(shadow)
    fact_payload = dict(out.get("fact_payload") or {}) if isinstance(out.get("fact_payload"), dict) else {}
    fact_trade = dict(fact_payload.get("trade") or {}) if isinstance(fact_payload.get("trade"), dict) else {}
    fact_trade["post_exit_shadow"] = dict(shadow)
    fact_payload["trade"] = fact_trade
    out["fact_payload"] = fact_payload
    return out


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


def _has_report_text_corruption(report: Any) -> bool:
    if not isinstance(report, dict):
        return False
    section_keys = (
        "market_context",
        "market_context_at_entry",
        "strategist_summary",
        "why_this_symbol_was_chosen",
        "scanner_filters",
    )
    for key in section_keys:
        section = report.get(key)
        if not isinstance(section, dict):
            continue
        texts: List[str] = [str(section.get("summary") or "")]
        texts.extend([str(item or "") for item in list(section.get("bullets") or [])])
        if any("??" in text for text in texts):
            return True
    return False


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


def _flatten_news_titles(sample: Any, *, max_groups: int = 10, max_titles_per_group: int = 2) -> List[str]:
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
    market_regime_hint = str(src.get("market_regime_hint") or compact.get("market_regime_hint") or "").strip()
    market_sentiment_hint = str(src.get("market_sentiment_hint") or compact.get("market_sentiment_hint") or "").strip()
    playbook_hint = str(src.get("playbook_hint") or compact.get("playbook_hint") or "").strip()
    return {
        "market_regime_hint": market_regime_hint,
        "market_sentiment_hint": market_sentiment_hint,
        "playbook_hint": playbook_hint,
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
    if not str(out.get("market_regime") or "").strip():
        out["market_regime"] = str(summary.get("market_regime_hint") or "").strip()
    if not str(out.get("market_sentiment") or "").strip():
        out["market_sentiment"] = str(summary.get("market_sentiment_hint") or "").strip()
    if not str(out.get("playbook") or "").strip():
        out["playbook"] = str(summary.get("playbook_hint") or "").strip()
    if not list(out.get("themes") or []):
        out["themes"] = [
            str(x or "")
            for x in list(summary.get("themes_hint") or [])
            if str(x or "").strip()
        ]
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

            selection_reason = str(out.get("selection_reason") or "").strip()
            if selection_reason:
                if "chart feature coverage " in selection_reason.lower():
                    selection_reason = re.sub(
                        r"chart feature coverage\s+\d+/\d+",
                        f"chart feature coverage {present}/{total}",
                        selection_reason,
                        flags=re.IGNORECASE,
                    )
                else:
                    selection_reason = f"{selection_reason}; chart feature coverage {present}/{total}"
            else:
                selection_reason = f"chart feature coverage {present}/{total}"
            out["selection_reason"] = selection_reason[:260]

            bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
            updated_bullets: List[str] = []
            replaced_chart_bullet = False
            coverage_detail_inserted = False
            present_keys = [str(x or "") for x in list(coverage.get("present_keys") or []) if str(x or "").strip()]
            missing_keys = [str(x or "") for x in list(coverage.get("missing_keys") or []) if str(x or "").strip()]
            coverage_source = str(coverage.get("source") or "").strip()

            def _append_coverage_details(target: List[str]) -> None:
                nonlocal coverage_detail_inserted
                if coverage_detail_inserted:
                    return
                if present_keys:
                    target.append(
                        "Chart features present: " + ", ".join(present_keys[:8]) + (", ..." if len(present_keys) > 8 else "")
                    )
                if missing_keys:
                    target.append(
                        "Chart features missing: " + ", ".join(missing_keys[:8]) + (", ..." if len(missing_keys) > 8 else "")
                    )
                if coverage_source:
                    target.append(f"Chart feature coverage source: {coverage_source}")
                coverage_detail_inserted = True

            for bullet in bullets:
                if bullet.lower().startswith("chart / feature coverage:"):
                    updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                    replaced_chart_bullet = True
                    _append_coverage_details(updated_bullets)
                else:
                    updated_bullets.append(bullet)
            if not replaced_chart_bullet:
                updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                _append_coverage_details(updated_bullets)
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
    trace = out.get("scanner_selection_trace") if isinstance(out.get("scanner_selection_trace"), dict) else {}
    if trace and coverage:
        trace["chart_feature_coverage"] = dict(coverage)
        out["scanner_selection_trace"] = trace
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

    reported = matched_row.get("feature_coverage") if isinstance(matched_row.get("feature_coverage"), dict) else {}
    snapshot = matched_row.get("compact_feature_snapshot") if isinstance(matched_row.get("compact_feature_snapshot"), dict) else {}
    if not snapshot:
        snapshot = matched_row.get("feature_snapshot") if isinstance(matched_row.get("feature_snapshot"), dict) else {}
    if not snapshot and not reported:
        return {}

    keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_atr14",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    computed_present_keys = [key for key in keys if snapshot.get(key) is not None]
    computed_missing_keys = [key for key in keys if snapshot.get(key) is None]
    computed_total = len(keys)
    computed_present = len(computed_present_keys)
    present = safe_int(reported.get("present"), computed_present)
    total = safe_int(reported.get("total"), computed_total)
    coverage_ratio = _safe_float(reported.get("coverage_ratio"), float(present) / float(total) if total else 0.0) or 0.0
    quality = str(reported.get("quality") or "").strip().lower()
    if not quality:
        if coverage_ratio >= 0.75:
            quality = "strong"
        elif coverage_ratio >= 0.5:
            quality = "partial"
        else:
            quality = "weak"
    reported_present_keys = [str(x or "") for x in list(reported.get("present_keys") or []) if str(x or "").strip()]
    reported_missing_keys = [str(x or "") for x in list(reported.get("missing_keys") or []) if str(x or "").strip()]
    reported_key_counts_match = bool(
        reported_present_keys
        and len(reported_present_keys) == present
        and len(reported_present_keys) + len(reported_missing_keys) == total
    )
    computed_key_counts_match = computed_present == present and computed_total == total
    present_keys = reported_present_keys if reported_key_counts_match else (computed_present_keys if computed_key_counts_match else [])
    missing_keys = reported_missing_keys if reported_key_counts_match else (computed_missing_keys if computed_key_counts_match else [])
    coverage_source = "feature_coverage_reported" if reported else "snapshot_derived"
    return {
        "present": present,
        "total": total,
        "coverage_ratio": coverage_ratio,
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
        "source": coverage_source,
    }


def _enrich_filters_from_evidence(
    filters_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
    monitor_evidence: Optional[Dict[str, Any]] = None,
    entry_execution_details: Optional[Dict[str, Any]] = None,
    exit_execution_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out = dict(filters_human or {})
    coverage = _normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    price_anomaly_check: Optional[Dict[str, str]] = None
    execution_spread_check: Optional[Dict[str, str]] = None

    def _visit_monitor_payload(node: Any) -> None:
        nonlocal price_anomaly_check
        if price_anomaly_check is not None:
            return
        if isinstance(node, dict):
            if "price_anomaly_flag" in node:
                flagged = bool(node.get("price_anomaly_flag"))
                reason = str(node.get("price_anomaly_reason") or "").strip()
                price_anomaly_check = {
                    "name": "price anomaly filter",
                    "status": "FAIL" if flagged else "PASS",
                    "detail": reason if flagged and reason else ("monitor price cross-check flagged an anomaly" if flagged else "monitor price cross-check found no anomaly"),
                }
                return
            for value in node.values():
                _visit_monitor_payload(value)
                if price_anomaly_check is not None:
                    return
        elif isinstance(node, list):
            for value in node:
                _visit_monitor_payload(value)
                if price_anomaly_check is not None:
                    return

    _visit_monitor_payload(monitor_evidence)
    def _resolve_execution_spread_check() -> Optional[Dict[str, str]]:
        spread_threshold_bps = 50.0
        for details in (entry_execution_details, exit_execution_details):
            if not isinstance(details, dict):
                continue
            quote_snapshot = details.get("quote_snapshot") if isinstance(details.get("quote_snapshot"), dict) else {}
            spread_bps = details.get("spread_bps")
            if spread_bps in (None, ""):
                spread_bps = quote_snapshot.get("spread_bps")
            if spread_bps in (None, ""):
                continue
            try:
                spread_value = float(spread_bps)
            except Exception:
                continue
            return {
                "name": "spread/slippage filter",
                "status": "PASS" if spread_value <= spread_threshold_bps else "FAIL",
                "detail": f"execution quote snapshot spread was {spread_value:.1f} bps",
            }
        return None

    execution_spread_check = _resolve_execution_spread_check()
    present = 0
    total = 0
    ratio = 0.0
    chart_status = "NOT_AVAILABLE"
    chart_note = "feature snapshot not available"
    coverage_quality = "missing"
    chart_available = bool(coverage)
    if coverage:
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        ratio = _safe_float(coverage.get("coverage_ratio"), 0.0) or 0.0
        coverage_quality = str(coverage.get("quality") or "").strip().lower() or chart_status.lower()
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
    if chart_available:
        if summary:
            summary = re.sub(
                r"Chart completeness was [^.]*(?:\.)?",
                f"Chart completeness was {coverage_quality} with {present}/{total} captured features.",
                summary,
                flags=re.IGNORECASE,
            )
        else:
            summary = f"Scanner and guard checks were captured. Chart completeness was {coverage_quality} with {present}/{total} captured features."
        out["summary"] = summary

    checks = [dict(x) for x in list(out.get("checks") or []) if isinstance(x, dict)]
    updated_checks: List[Dict[str, Any]] = []
    replaced_check = False
    replaced_price_anomaly = False
    replaced_spread_check = False
    for check in checks:
        check_name = str(check.get("name") or "").strip().lower()
        if check_name == "chart completeness filter" and chart_available:
            check["status"] = chart_status
            check["detail"] = chart_note
            replaced_check = True
        elif check_name == "price anomaly filter" and price_anomaly_check is not None:
            check["status"] = str(price_anomaly_check.get("status") or check.get("status") or "")
            check["detail"] = str(price_anomaly_check.get("detail") or check.get("detail") or "")
            replaced_price_anomaly = True
        elif check_name == "spread/slippage filter" and execution_spread_check is not None:
            current_status = str(check.get("status") or "").strip().upper()
            if current_status in {"", "NOT_AVAILABLE", "UNKNOWN"}:
                check["status"] = str(execution_spread_check.get("status") or check.get("status") or "")
                check["detail"] = str(execution_spread_check.get("detail") or check.get("detail") or "")
                replaced_spread_check = True
        updated_checks.append(check)
    if chart_available and not replaced_check:
        updated_checks.append(
            {
                "name": "chart completeness filter",
                "status": chart_status,
                "detail": chart_note,
            }
        )
    if price_anomaly_check is not None and not replaced_price_anomaly:
        updated_checks.append(dict(price_anomaly_check))
    if execution_spread_check is not None and not replaced_spread_check:
        updated_checks.append(dict(execution_spread_check))
    if updated_checks:
        out["checks"] = updated_checks

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    updated_bullets: List[str] = []
    replaced = False
    replaced_price_bullet = False
    replaced_spread_bullet = False
    for bullet in bullets:
        if bullet.lower().startswith("chart completeness filter:") and chart_available:
            updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
            replaced = True
        elif bullet.lower().startswith("price anomaly filter:") and price_anomaly_check is not None:
            updated_bullets.append(
                f"price anomaly filter: {price_anomaly_check['status']} - {price_anomaly_check['detail']}"
            )
            replaced_price_bullet = True
        elif bullet.lower().startswith("spread/slippage filter:") and execution_spread_check is not None:
            current_status = ""
            match = re.match(r"spread/slippage filter:\s*([A-Z_]+)\s*-", bullet, flags=re.IGNORECASE)
            if match:
                current_status = str(match.group(1) or "").strip().upper()
            if current_status in {"", "NOT_AVAILABLE", "UNKNOWN"}:
                updated_bullets.append(
                    f"spread/slippage filter: {execution_spread_check['status']} - {execution_spread_check['detail']}"
                )
                replaced_spread_bullet = True
            else:
                updated_bullets.append(bullet)
        else:
            updated_bullets.append(bullet)
    if chart_available and not replaced:
        updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
    if price_anomaly_check is not None and not replaced_price_bullet:
        updated_bullets.append(
            f"price anomaly filter: {price_anomaly_check['status']} - {price_anomaly_check['detail']}"
        )
    if execution_spread_check is not None and not replaced_spread_bullet:
        updated_bullets.append(
            f"spread/slippage filter: {execution_spread_check['status']} - {execution_spread_check['detail']}"
        )
    out["bullets"] = updated_bullets[:8]
    if coverage:
        out["feature_coverage"] = dict(coverage)
    return out


def _build_strategist_input_artifacts(
    bundle_out: Dict[str, Any],
    *,
    day: str,
    trade_id: str,
    reports_root: Path | None = None,
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
    if not source_input and not compact_input and reports_root is not None and source_run_id:
        prompt_artifact = _read_json_if_exists(
            Path(reports_root) / "llm" / str(day or "") / str(source_run_id) / "strategist" / "prompt.json"
        )
        prompt_payload = {}
        if isinstance(prompt_artifact, dict):
            prompt_payload = (
                prompt_artifact.get("payload")
                if isinstance(prompt_artifact.get("payload"), dict)
                else prompt_artifact.get("user_payload")
                if isinstance(prompt_artifact.get("user_payload"), dict)
                else {}
            )
            if prompt_payload:
                source_input = dict(prompt_payload)
                compact_input = dict(prompt_payload)
                source_stage = str(prompt_artifact.get("stage") or source_stage or "").strip()
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


def _background_job_lock_path() -> Path | None:
    raw = str(os.getenv("INTRADAY_TRADE_REPORT_JOB_LOCK_PATH") or "").strip()
    if raw:
        return Path(raw)
    return ROOT / "reports" / "runtime" / "intraday_trade_report_bundle.lock"


def _background_job_queue_path() -> Path:
    return ROOT / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"


def _bundle_role(value: Any = "") -> str:
    raw = str(value or "").strip()
    return raw or "intraday_trade_report_bundle"


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_background_job_queue(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        return [dict(row) for row in payload if isinstance(row, dict)]
    except Exception:
        return []


def _write_background_job_queue(path: Path, rows: List[Dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _pop_next_background_job_request(
    path: Path,
    *,
    current_run_id: str = "",
    current_symbol: str = "",
) -> Dict[str, Any]:
    rows = _load_background_job_queue(path)
    if not rows:
        return {}
    normalized_run_id = str(current_run_id or "").strip()
    normalized_symbol = str(current_symbol or "").strip().upper()
    next_row: Dict[str, Any] = {}
    remaining: List[Dict[str, Any]] = []
    for row in rows:
        row_run_id = str(row.get("target_run_id") or "").strip()
        row_symbol = str(row.get("target_symbol") or "").strip().upper()
        if not next_row and not (
            row_run_id == normalized_run_id and row_symbol == normalized_symbol
        ):
            next_row = dict(row)
            continue
        remaining.append(dict(row))
    _write_background_job_queue(path, remaining)
    return next_row


def _spawn_followup_background_job(
    next_request: Dict[str, Any],
    *,
    args: argparse.Namespace,
    role: str,
    event_log_path: Path | None,
) -> Dict[str, Any]:
    target_run_id = str(next_request.get("target_run_id") or "").strip()
    target_symbol = str(next_request.get("target_symbol") or "").strip()
    if not target_run_id:
        return {}
    cmd = [sys.executable, str(ROOT / "scripts" / "run_live_execution_bundle_report.py")]
    if args.env_path:
        cmd.extend(["--env-path", str(args.env_path)])
    cmd.extend(["--event-log-path", str(args.event_log_path)])
    cmd.extend(["--evidence-log-path", str(args.evidence_log_path)])
    cmd.extend(["--report-dir", str(args.report_dir)])
    cmd.extend(["--reports-root", str(args.reports_root)])
    if args.intents_path:
        cmd.extend(["--intents-path", str(args.intents_path)])
    if args.day:
        cmd.extend(["--day", str(args.day)])
    cmd.extend(["--role", str(role or _bundle_role())])
    cmd.extend(["--target-run-id", target_run_id])
    if target_symbol:
        cmd.extend(["--target-symbol", target_symbol])
    if bool(args.trade_report_ai):
        cmd.append("--trade-report-ai")
    if args.trade_report_ai_model:
        cmd.extend(["--trade-report-ai-model", str(args.trade_report_ai_model)])
    if args.trade_report_ai_temperature is not None:
        cmd.extend(["--trade-report-ai-temperature", str(args.trade_report_ai_temperature)])
    if args.trade_report_ai_max_tokens is not None:
        cmd.extend(["--trade-report-ai-max-tokens", str(args.trade_report_ai_max_tokens)])
    if bool(args.json):
        cmd.append("--json")
    env = dict(os.environ)
    env["INTRADAY_TRADE_REPORT_PARENT_SPAWN"] = "1"
    try:
        proc = popen_hidden(  # noqa: S603
            cmd,
            background=True,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except Exception as exc:
        _log_bundle_event(
            event_log_path,
            role=role,
            event="report_bundle_followup_spawn_failed",
            run_id=target_run_id or "report-bundle",
            symbol=target_symbol,
            payload={
                "reason": "followup_spawn_failed",
                "error": str(exc),
                "queued_run_id": target_run_id,
                "queued_symbol": target_symbol,
            },
        )
        return {}
    _log_bundle_event(
        event_log_path,
        role=role,
        event="report_bundle_spawned_followup_from_queue",
        run_id=target_run_id or "report-bundle",
        symbol=target_symbol,
        payload={
            "pid": int(getattr(proc, "pid", 0) or 0),
            "parent_pid": int(os.getpid()),
            "role": role,
            "queued_run_id": target_run_id,
            "queued_symbol": target_symbol,
            "spawn_command": list(cmd),
            "spawn_cwd": str(ROOT),
            "spawn_creationflags": int(_background_creationflags()),
        },
    )
    return {
        "pid": int(getattr(proc, "pid", 0) or 0),
        "target_run_id": target_run_id,
        "target_symbol": target_symbol,
    }


def _pid_active(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                process_query_limited_information,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _make_bundle_event_logger(event_log_path: Path | None):
    if event_log_path is None:
        return None
    try:
        from libs.core.event_logger import EventLogger
    except Exception:
        return None
    try:
        return EventLogger(log_path=event_log_path)
    except Exception:
        return None


def _log_bundle_event(
    event_log_path: Path | None,
    *,
    role: str,
    event: str,
    level: str = "info",
    run_id: str = "report-bundle",
    symbol: str = "",
    trade_id: str = "",
    payload: Dict[str, Any] | None = None,
) -> None:
    logger = _make_bundle_event_logger(event_log_path)
    if logger is None:
        return
    try:
        logger.log(
            run_id=str(run_id or "report-bundle"),
            stage="report_bundle",
            event=event,
            event_name=f"report_bundle.{event}",
            level=str(level or "info"),
            agent="report_bundle",
            phase="reporting",
            symbol=str(symbol or ""),
            trade_id=str(trade_id or ""),
            payload=dict(payload or {}),
        )
    except Exception:
        return


def _active_background_process(*, role: str) -> Dict[str, Any]:
    script_hint = "run_live_execution_bundle_report.py"
    role_hint = f"--role {str(role or '').strip()}".lower()
    current_pid = int(os.getpid())
    current_ppid = int(os.getppid())
    argv_lower = [str(arg or "").strip().lower() for arg in sys.argv]
    current_target_run_id = ""
    current_target_symbol = ""
    for idx, token in enumerate(argv_lower):
        if token == "--target-run-id" and idx + 1 < len(argv_lower):
            current_target_run_id = str(argv_lower[idx + 1] or "").strip().lower()
        if token == "--target-symbol" and idx + 1 < len(argv_lower):
            current_target_symbol = str(argv_lower[idx + 1] or "").strip().lower()
    try:
        if os.name == "nt":
            probe = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_live_execution_bundle_report.py*' } | "
                "Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Compress"
            )
            completed = run_hidden(
                ["powershell", "-NoProfile", "-Command", probe],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
                check=False,
            )
            raw = str(completed.stdout or "").strip()
            if not raw:
                return {}
            payload = json.loads(raw)
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                pid = int(row.get("ProcessId") or 0)
                parent_pid = int(row.get("ParentProcessId") or 0)
                cmd = str(row.get("CommandLine") or "")
                cmd_lower = cmd.lower()
                if pid <= 0 or pid == current_pid:
                    continue
                if (
                    parent_pid == current_ppid
                    and role_hint
                    and role_hint in cmd_lower
                    and current_target_run_id
                    and f"--target-run-id {current_target_run_id}" in cmd_lower
                    and (
                        not current_target_symbol
                        or f"--target-symbol {current_target_symbol}" in cmd_lower
                    )
                ):
                    continue
                if script_hint not in cmd_lower:
                    continue
                if role_hint and role_hint not in cmd_lower:
                    continue
                creation_epoch = _creation_epoch_from_wmi(row.get("CreationDate"))
                return {
                    "pid": pid,
                    "parent_pid": parent_pid,
                    "command_line": cmd,
                    "script": script_hint,
                    "role": _bundle_role(role),
                    "detection_source": "process_scan",
                    "creation_epoch": creation_epoch,
                    "age_sec": max(0.0, float(time.time()) - creation_epoch) if creation_epoch > 0 else None,
                }
        else:
            completed = run_hidden(
                ["ps", "-eo", "pid=,ppid=,args="],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
                check=False,
            )
            for raw in str(completed.stdout or "").splitlines():
                line = str(raw or "").strip()
                if not line:
                    continue
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue
                pid = int(parts[0] or 0)
                parent_pid = int(parts[1] or 0)
                cmd = str(parts[2] or "")
                cmd_lower = cmd.lower()
                if pid <= 0 or pid == current_pid:
                    continue
                if (
                    parent_pid == current_ppid
                    and role_hint
                    and role_hint in cmd_lower
                    and current_target_run_id
                    and f"--target-run-id {current_target_run_id}" in cmd_lower
                    and (
                        not current_target_symbol
                        or f"--target-symbol {current_target_symbol}" in cmd_lower
                    )
                ):
                    continue
                if script_hint not in cmd_lower:
                    continue
                if role_hint and role_hint not in cmd_lower:
                    continue
                return {
                    "pid": pid,
                    "parent_pid": parent_pid,
                    "command_line": cmd,
                    "script": script_hint,
                    "role": _bundle_role(role),
                    "detection_source": "process_scan",
                }
    except Exception:
        return {}
    return {}


def _creation_epoch_from_wmi(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    match = re.search(r"/Date\((\d+)", raw)
    if match:
        try:
            return float(match.group(1)) / 1000.0
        except Exception:
            return 0.0
    return 0.0


def _stale_process_after_sec() -> float:
    try:
        return max(30.0, float(os.getenv("INTRADAY_TRADE_REPORT_STALE_PROCESS_SEC", "180") or 180.0))
    except Exception:
        return 180.0


def _terminate_process_tree(pid: int) -> bool:
    pid = int(pid or 0)
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            completed = run_hidden(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
                check=False,
            )
            return int(completed.returncode or 1) == 0
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def _background_creationflags() -> int:
    return int(background_creationflags())


def _lock_timestamp_epoch(payload: Dict[str, Any], *, stale_after_sec: float) -> float:
    raw = (
        payload.get("touched_at_epoch")
        or payload.get("heartbeat_epoch")
        or payload.get("started_at_epoch")
    )
    try:
        epoch = float(raw or 0.0)
    except Exception:
        epoch = 0.0
    if epoch > 0:
        return epoch
    started_at = str(payload.get("started_at") or "").strip()
    return _to_epoch(started_at) or (time.time() - stale_after_sec - 1.0)


def _active_background_job(
    path: Path | None,
    *,
    stale_after_sec: float = 900.0,
    event_log_path: Path | None = None,
    role: str = "",
) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or not payload:
        return {}
    owner_pid = int(payload.get("pid") or 0)
    heartbeat_epoch = _lock_timestamp_epoch(payload, stale_after_sec=stale_after_sec)
    age_sec = max(0.0, time.time() - heartbeat_epoch)
    lock_role = _bundle_role(payload.get("role") or role)
    if owner_pid in (0, int(os.getpid())):
        out = dict(payload)
        out["lock_path"] = str(path)
        out["age_sec"] = age_sec
        out["detection_source"] = "lock"
        out["role"] = lock_role
        return out
    if _pid_active(owner_pid) and age_sec <= stale_after_sec:
        out = dict(payload)
        out["lock_path"] = str(path)
        out["age_sec"] = age_sec
        out["detection_source"] = "lock"
        out["role"] = lock_role
        return out
    with contextlib.suppress(Exception):
        path.unlink()
    _log_bundle_event(
        event_log_path,
        role=lock_role,
        event="report_bundle_stale_lock_removed",
        payload={
            "pid": owner_pid,
            "role": lock_role,
            "lock_path": str(path),
            "reason": "pid_missing_or_stale_lock",
            "age_sec": age_sec,
        },
    )
    return {}


def _write_background_job_lock(
    path: Path | None,
    *,
    status: str,
    role: str,
    extra: Dict[str, Any] | None = None,
) -> None:
    if path is None:
        return
    now_epoch = float(time.time())
    payload = {
        "pid": int(os.getpid()),
        "parent_pid": int(os.getppid()),
        "role": _bundle_role(role),
        "status": str(status or "running"),
        "created_at": utc_now_iso(),
        "created_at_epoch": now_epoch,
        "started_at": utc_now_iso(),
        "started_at_epoch": now_epoch,
        "touched_at": utc_now_iso(),
        "touched_at_epoch": now_epoch,
        "heartbeat": utc_now_iso(),
        "heartbeat_epoch": now_epoch,
        "script": "run_live_execution_bundle_report.py",
    }
    if isinstance(extra, dict) and extra:
        payload.update({str(k): v for k, v in extra.items()})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _touch_background_job_lock(path: Path | None, *, role: str, extra: Dict[str, Any] | None = None) -> None:
    if path is None:
        return
    payload = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    owner_pid = int(payload.get("pid") or 0)
    if owner_pid not in (0, int(os.getpid())):
        return
    now_epoch = float(time.time())
    payload.update(
        {
            "pid": int(os.getpid()),
            "parent_pid": int(os.getppid()),
            "role": _bundle_role(role),
            "status": str(payload.get("status") or "running"),
            "script": "run_live_execution_bundle_report.py",
            "touched_at": utc_now_iso(),
            "touched_at_epoch": now_epoch,
            "heartbeat": utc_now_iso(),
            "heartbeat_epoch": now_epoch,
        }
    )
    if not payload.get("created_at_epoch"):
        payload["created_at"] = utc_now_iso()
        payload["created_at_epoch"] = now_epoch
    if not payload.get("started_at_epoch"):
        payload["started_at"] = utc_now_iso()
        payload["started_at_epoch"] = now_epoch
    if isinstance(extra, dict) and extra:
        payload.update({str(k): v for k, v in extra.items()})
    with contextlib.suppress(Exception):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_background_job_lock(path: Path | None, *, role: str = "") -> None:
    if path is None or not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    owner_pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    if owner_pid not in (0, int(os.getpid())):
        return
    with contextlib.suppress(Exception):
        path.unlink()


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


def _null_if_empty(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _build_failure_classification(
    *,
    lifecycle: Dict[str, Any],
    diagnostics: Dict[str, Any],
    same_day_reporter_linkage: Dict[str, Any],
    holding_phase_observability: Dict[str, Any],
    execution_details: Dict[str, Any],
) -> Dict[str, bool]:
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    status = str(lifecycle.get("status") or "").strip().lower()
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    story_type = str(lifecycle.get("story_type") or "").strip().lower()
    ai_status = str(diagnostics.get("ai_trade_report_status") or "").strip().lower()
    reporter_status = str((same_day_reporter_linkage or {}).get("status") or "").strip().lower()
    return {
        "entry_failure": (not bool(entry)) or bool(entry.get("inferred_entry")),
        "hold_failure": bool((holding_phase_observability or {}).get("hold_evidence_thin")),
        "exit_failure": status in {"closed", "failed"} and not bool(exit_ctx),
        "execution_failure": story_type == "failed_execution" or (
            status in {"closed", "partial", "failed"}
            and not bool(execution_details.get("order_status"))
            and not bool(execution_details.get("order_id"))
        ),
        "reporting_failure": (
            reporter_status == "missing"
            or (status == "closed" and ai_status not in {"ok", "salvaged", "partial"})
        ),
    }


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
    return _normalize_execution_row_lib(payload if isinstance(payload, dict) else {})


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


def _expand_targeted_run_ids_with_cached_strategist_sources(
    *,
    event_rows: List[Dict[str, Any]],
    targeted_run_ids: Iterable[str],
) -> Set[str]:
    out: Set[str] = {
        str(run_id or "").strip()
        for run_id in list(targeted_run_ids or [])
        if str(run_id or "").strip()
    }
    if not out:
        return out

    strategist_frame_rows = [
        row
        for row in list(event_rows or [])
        if str(row.get("agent") or row.get("stage") or "").strip().lower() == "strategist"
        and _row_event_name(row) == "strategist.decision_frame"
    ]
    strategist_frame_rows.sort(key=lambda row: _to_epoch(row.get("ts")) or 0)
    if not strategist_frame_rows:
        return out

    fast_path_rows = [
        row
        for row in list(event_rows or [])
        if str(row.get("run_id") or "").strip() in out
        and _row_event_name(row) == "commander_router.fast_path"
    ]
    for fast_path in fast_path_rows:
        payload = fast_path.get("payload") if isinstance(fast_path.get("payload"), dict) else {}
        if str(payload.get("path") or "").strip() != "integrated_chain_cached_frame":
            continue
        target_run_id = str(fast_path.get("run_id") or "").strip()
        target_ts = _to_epoch(fast_path.get("ts")) or 0
        reuse_sec = max(30, safe_int(payload.get("reuse_sec"), 180))
        candidate_rows = [
            row
            for row in strategist_frame_rows
            if str(row.get("run_id") or "").strip() != target_run_id
            and (_to_epoch(row.get("ts")) or 0) <= target_ts
            and target_ts - (_to_epoch(row.get("ts")) or 0) <= reuse_sec + 30
        ]
        if not candidate_rows:
            continue
        source_run_id = str(candidate_rows[-1].get("run_id") or "").strip()
        if source_run_id:
            out.add(source_run_id)
    return out


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


_MONITOR_TIMELINE_CANONICAL_FIELDS = (
    "entry_minute_snapshot_age_minutes",
    "entry_minute_snapshot_was_stale",
    "entry_minute_refetch_attempted",
    "entry_minute_refetch_succeeded",
    "entry_minute_refetch_reason",
    "entry_minute_refetch_trigger_reason",
    "entry_minute_refetch_failure_reason",
    "entry_latest_candle_ts",
    "entry_inferred_spacing_minutes",
    "entry_series_class",
)


def _load_latest_canonical_monitor_artifact(
    *,
    reports_root: Path,
    day: str,
    run_ids: List[str],
) -> Dict[str, Any]:
    canonical_root = reports_root / "canonical" / str(day or "")
    for run_id in reversed([str(x or "").strip() for x in list(run_ids or []) if str(x or "").strip()]):
        monitor_path = canonical_root / run_id / "monitor.json"
        payload = _read_json_if_exists(monitor_path)
        if payload:
            return {
                "path": str(monitor_path),
                "payload": payload,
            }
    return {}


def _merge_monitor_timeline_with_canonical(
    *,
    monitor_timeline: Dict[str, Any],
    canonical_monitor_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(monitor_timeline or {})
    artifact_path = str(canonical_monitor_artifact.get("path") or "").strip()
    artifact_payload = (
        canonical_monitor_artifact.get("payload")
        if isinstance(canonical_monitor_artifact.get("payload"), dict)
        else {}
    )
    threshold_snapshot = (
        artifact_payload.get("threshold_snapshot")
        if isinstance(artifact_payload.get("threshold_snapshot"), dict)
        else {}
    )
    if not threshold_snapshot:
        return out

    out["canonical_monitor_artifact_path"] = artifact_path
    out["canonical_monitor_run_id"] = str(artifact_payload.get("run_id") or "")
    out["canonical_monitor_freshness_mirrored"] = True
    for field in _MONITOR_TIMELINE_CANONICAL_FIELDS:
        value = threshold_snapshot.get(field)
        if value not in (None, ""):
            out[field] = value

    threshold_rows = [dict(row) for row in list(out.get("threshold_snapshots") or []) if isinstance(row, dict)]
    if threshold_rows:
        latest_row = dict(threshold_rows[-1] or {})
        payload = dict(latest_row.get("payload") or {}) if isinstance(latest_row.get("payload"), dict) else {}
        for field in _MONITOR_TIMELINE_CANONICAL_FIELDS:
            if payload.get(field) in (None, "") and threshold_snapshot.get(field) not in (None, ""):
                payload[field] = threshold_snapshot.get(field)
        latest_row["payload"] = payload
        threshold_rows[-1] = latest_row
    else:
        threshold_rows.append(
            {
                "ts": str(artifact_payload.get("ts") or artifact_payload.get("generated_at") or ""),
                "event_name": "monitor.threshold_snapshot",
                "level": "info",
                "run_id": str(artifact_payload.get("run_id") or ""),
                "trade_id": str(artifact_payload.get("trade_id") or ""),
                "session_id": str(artifact_payload.get("session_id") or ""),
                "cycle_id": str(artifact_payload.get("cycle_id") or ""),
                "agent": "monitor",
                "phase": str(artifact_payload.get("phase") or ""),
                "symbol": str(artifact_payload.get("symbol") or out.get("symbol") or ""),
                "payload": dict(threshold_snapshot),
                "source": "canonical_monitor_artifact",
                "artifact_path": artifact_path,
            }
        )
    out["threshold_snapshots"] = threshold_rows
    return out


def _build_trade_evidence_from_events(
    *,
    event_rows: List[Dict[str, Any]],
    lifecycle: Dict[str, Any],
    reports_root: Optional[Path] = None,
    day: str = "",
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
            "monitor.entry_decision_detail",
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
    if isinstance(reports_root, Path) and str(day or "").strip():
        monitor_timeline = _merge_monitor_timeline_with_canonical(
            monitor_timeline=monitor_timeline,
            canonical_monitor_artifact=_load_latest_canonical_monitor_artifact(
                reports_root=reports_root,
                day=str(day or ""),
                run_ids=run_ids,
            ),
        )
    return strategist_evidence, scanner_evidence, monitor_timeline


def _resolve_execution_runs(
    event_log_path: Path,
    day: str,
    *,
    event_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    source_rows = list(event_rows) if isinstance(event_rows, list) else list(_iter_jsonl(event_log_path))
    rows = sorted(source_rows, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
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


def _targeted_execution_context(
    execution_runs: List[Dict[str, Any]],
    *,
    target_run_id: str = "",
    target_symbol: str = "",
    max_runs: int = 50,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = list(execution_runs or [])
    normalized_symbol = normalize_symbol(target_symbol, allow_test_symbols=True)
    targeted_mode = False
    target_row: Dict[str, Any] = {}
    if target_run_id:
        target_row = next(
            (row for row in rows if str(row.get("run_id") or "").strip() == str(target_run_id or "").strip()),
            {},
        )
        if isinstance(target_row, dict) and target_row:
            targeted_mode = True
            normalized_symbol = normalize_symbol(target_row.get("symbol") or normalized_symbol, allow_test_symbols=True)
            target_ts_epoch = _to_epoch(target_row.get("ts")) or 0.0
            lifecycle_context_rows = [
                row
                for row in rows
                if (
                    not normalized_symbol
                    or normalize_symbol(row.get("symbol") or "", allow_test_symbols=True) == normalized_symbol
                )
                and ((_to_epoch(row.get("ts")) or 0.0) <= target_ts_epoch)
            ]
            rows = [dict(target_row)]
        else:
            lifecycle_context_rows = []
    elif normalized_symbol:
        targeted_mode = True
        rows = [
            row
            for row in rows
            if normalize_symbol(row.get("symbol") or "", allow_test_symbols=True) == normalized_symbol
        ]
        lifecycle_context_rows = list(rows)
    else:
        rows = rows[: max(1, int(max_runs))]
        lifecycle_context_rows = list(rows)
    return rows, {
        "targeted_mode": bool(targeted_mode),
        "target_run_id": str(target_run_id or ""),
        "target_symbol": str(normalized_symbol or ""),
        "target_row": dict(target_row or {}),
        "execution_run_count": len(rows),
        "lifecycle_context_run_ids": [
            str(row.get("run_id") or "").strip()
            for row in lifecycle_context_rows
            if str(row.get("run_id") or "").strip()
        ],
        "lifecycle_context_run_count": len(lifecycle_context_rows),
    }


def _lifecycle_matches_target(lifecycle: Dict[str, Any], *, target_run_id: str = "", target_symbol: str = "") -> bool:
    run_id_target = str(target_run_id or "").strip()
    symbol_target = normalize_symbol(target_symbol, allow_test_symbols=True)
    if not run_id_target and not symbol_target:
        return True
    lifecycle_symbol = normalize_symbol(lifecycle.get("symbol") or "", allow_test_symbols=True)
    if symbol_target and lifecycle_symbol and lifecycle_symbol != symbol_target:
        return False
    run_ids = {str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()}
    entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    run_ids.add(str(entry_ctx.get("run_id") or "").strip())
    run_ids.add(str(exit_ctx.get("run_id") or "").strip())
    run_ids.update(str(x or "").strip() for x in list(holding.get("run_ids") or []) if str(x or "").strip())
    if run_id_target:
        return run_id_target in run_ids
    return True


def _stable_json_text(payload: Any) -> str:
    return _stable_json_text_lib(payload)


def _payload_fingerprint(payload: Any) -> str:
    return _payload_fingerprint_lib(payload)


def _build_component_fingerprint(
    *,
    component: str,
    trade_id: str,
    run_id: str,
    lifecycle_status: str,
    story_type: str,
    model: str,
    story_input: Dict[str, Any],
    compact_input: Dict[str, Any],
) -> Dict[str, Any]:
    return _build_component_fingerprint_lib(
        component=component,
        trade_id=trade_id,
        run_id=run_id,
        lifecycle_status=lifecycle_status,
        story_type=story_type,
        model=model,
        story_input=story_input,
        compact_input=compact_input,
    )


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


def _build_run_snapshots(
    event_log_path: Path,
    day: str,
    *,
    reports_root: Path,
    include_run_ids: Optional[set[str]] = None,
    event_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    source_rows = list(event_rows) if isinstance(event_rows, list) else list(_iter_jsonl(event_log_path))
    for row in source_rows:
        if day and _utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        if include_run_ids and run_id not in include_run_ids:
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
        execution_fallback_payload = _normalize_execution_payload(
            execution_row.get("payload") if isinstance(execution_row.get("payload"), dict) else {}
        )
        executor_payload, executor_source, _executor_path = _prefer_canonical_payload(
            canonical_sources,
            "executor",
            execution_fallback_payload,
            fallback_source="event_log",
        )
        execution_candidates = [
            execution_row.get("payload") if isinstance(execution_row.get("payload"), dict) else {},
            executor_payload if isinstance(executor_payload, dict) else {},
            execution_fallback_payload,
        ]
        if str(executor_source or "").strip().lower() == "canonical":
            execution_candidates = [
                executor_payload if isinstance(executor_payload, dict) else {},
                execution_row.get("payload") if isinstance(execution_row.get("payload"), dict) else {},
                execution_fallback_payload,
            ]
        execution = _build_execution_snapshot_lib(
            candidates=execution_candidates,
            run_id=run_id,
            ts=str(execution_row.get("ts") or rows[-1].get("ts") or ""),
        )
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
            (executor_payload.get("symbol") if str(executor_source or "").strip().lower() == "canonical" else "")
            or execution.get("symbol")
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


def _filter_rows_by_run_ids(
    rows: List[Dict[str, Any]] | None,
    run_ids: Iterable[str] | None,
) -> List[Dict[str, Any]]:
    source_rows = list(rows or [])
    allowed = {str(run_id or "").strip() for run_id in list(run_ids or []) if str(run_id or "").strip()}
    if not allowed:
        return source_rows
    return [
        row
        for row in source_rows
        if str((row or {}).get("run_id") or "").strip() in allowed
    ]


def _generate_agent_pipeline_trace_report_fast(
    *,
    event_log_path: Path,
    evidence_log_path: Path,
    report_dir: Path,
    run_id: str,
    day: str,
    reports_root: Path,
    event_rows: List[Dict[str, Any]] | None = None,
    evidence_rows_all: List[Dict[str, Any]] | None = None,
) -> Tuple[Path, Path, Dict[str, Any]]:
    try:
        return generate_agent_pipeline_trace_report(
            event_log_path=event_log_path,
            evidence_log_path=evidence_log_path,
            report_dir=report_dir,
            run_id=run_id,
            day=day,
            reports_root=reports_root,
            event_rows=event_rows,
            evidence_rows_all=evidence_rows_all,
        )
    except TypeError:
        return generate_agent_pipeline_trace_report(
            event_log_path=event_log_path,
            evidence_log_path=evidence_log_path,
            report_dir=report_dir,
            run_id=run_id,
            day=day,
            reports_root=reports_root,
        )


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


def _trade_id_sequence(trade_id: str) -> int:
    text = str(trade_id or "").strip()
    if not text:
        return 10**9
    tail = text.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except Exception:
        return 10**9


def _existing_trade_run_ids(trade_dir: Path) -> List[str]:
    lifecycle_path = trade_dir / "lifecycle_bundle.json"
    if not lifecycle_path.exists():
        return []
    payload = _read_json_if_exists(lifecycle_path)
    run_ids: List[str] = [str(x or "").strip() for x in list(payload.get("linked_run_ids") or []) if str(x or "").strip()]
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    exit_ctx = payload.get("exit") if isinstance(payload.get("exit"), dict) else {}
    lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    for item in (
        entry.get("run_id"),
        exit_ctx.get("run_id"),
    ):
        rid = str(item or "").strip()
        if rid and rid not in run_ids:
            run_ids.append(rid)
    for item in list(holding.get("run_ids") or []):
        rid = str(item or "").strip()
        if rid and rid not in run_ids:
            run_ids.append(rid)
    return run_ids


def _find_existing_trade_id_for_run_ids(
    *,
    reports_root: Path,
    day: str,
    symbol: str,
    run_ids: Iterable[str],
) -> str:
    day_root = Path(reports_root) / "trades" / str(day or "").strip()
    if not day_root.exists():
        return ""
    requested = {str(item or "").strip() for item in list(run_ids or []) if str(item or "").strip()}
    if not requested:
        return ""
    symbol_norm = normalize_symbol(symbol or "", allow_test_symbols=True) or ""
    matches: List[Tuple[int, str]] = []
    for trade_dir in day_root.iterdir():
        if not trade_dir.is_dir():
            continue
        trade_id = str(trade_dir.name or "").strip()
        if symbol_norm and f"_{symbol_norm}_" not in trade_id:
            continue
        existing_run_ids = set(_existing_trade_run_ids(trade_dir))
        if not existing_run_ids.intersection(requested):
            continue
        matches.append((_trade_id_sequence(trade_id), trade_id))
    if not matches:
        return ""
    matches.sort(key=lambda item: (item[0], item[1]))
    return str(matches[0][1] or "")


def _has_substantive_entry_evidence(entry: Dict[str, Any]) -> bool:
    return _has_substantive_entry_evidence_lib(entry)


def _load_existing_open_lifecycle_candidates(
    *,
    reports_root: Path,
    day: str,
) -> Dict[str, List[Dict[str, Any]]]:
    return _load_existing_open_lifecycle_candidates_lib(
        reports_root=reports_root,
        day=day,
    )


def _build_trade_lifecycles(
    *,
    day: str,
    run_snapshots: List[Dict[str, Any]],
    run_bundles: Dict[str, Dict[str, Any]],
    existing_open_lifecycles_by_symbol: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    return _build_trade_lifecycles_lib(
        day=day,
        run_snapshots=run_snapshots,
        run_bundles=run_bundles,
        existing_open_lifecycles_by_symbol=existing_open_lifecycles_by_symbol,
    )

def _resolve_existing_day_artifact(report_dir: Path, prefix: str, day: str) -> Tuple[Path, Path]:
    return report_dir / f"{prefix}_{day}.md", report_dir / f"{prefix}_{day}.json"


def _load_or_generate_trade_explain(event_log_path: Path, analysis_root: Path, day: str) -> Tuple[Path, Path, Dict[str, Any]]:
    reports_root = analysis_root.parent.parent if analysis_root.name == "analysis" else analysis_root
    report_dir = official_trade_explain_report_dir(reports_root)
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
    p.add_argument("--target-run-id", default=None)
    p.add_argument("--target-symbol", default=None)
    p.add_argument("--role", default="intraday_trade_report_bundle")
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
    role = _bundle_role(args.role)
    event_log_path = Path(str(args.event_log_path).strip())
    background_lock_path = _background_job_lock_path()
    inprocess_no_boundary = _is_trueish(os.getenv("INTRADAY_TRADE_REPORT_INPROCESS_NO_BOUNDARY", "0"))
    parent_spawn = _is_trueish(os.getenv("INTRADAY_TRADE_REPORT_PARENT_SPAWN", "0"))
    target_run_id = str(args.target_run_id or "").strip()
    target_symbol = normalize_symbol(args.target_symbol or "", allow_test_symbols=True)
    if not inprocess_no_boundary:
        active_job = _active_background_job(
            background_lock_path,
            event_log_path=event_log_path,
            role=role,
        )
        owner_pid = int(active_job.get("pid") or 0) if active_job else 0
        lock_matches_current_target = bool(
            active_job
            and parent_spawn
            and str(active_job.get("target_run_id") or "").strip() == target_run_id
            and normalize_symbol(active_job.get("target_symbol") or "", allow_test_symbols=True) == target_symbol
        )
        if active_job and owner_pid not in (0, int(os.getpid())) and not lock_matches_current_target:
            out = {
                "schema_version": "live_execution_bundles.v2",
                "ok": True,
                "status": "skipped",
                "reason": "bundle_job_already_running",
                "active_pid": owner_pid,
                "lock_path": str(active_job.get("lock_path") or background_lock_path or ""),
                "detection_source": str(active_job.get("detection_source") or "lock"),
                "role": role,
            }
            _log_bundle_event(
                event_log_path,
                role=role,
                event="report_bundle_spawn_skipped_existing_process",
                payload={
                    "pid": owner_pid,
                    "parent_pid": int(active_job.get("parent_pid") or 0),
                    "role": role,
                    "lock_path": str(active_job.get("lock_path") or background_lock_path or ""),
                    "reason": "bundle_job_already_running",
                    "detection_source": str(active_job.get("detection_source") or "lock"),
                },
            )
            print(json.dumps(out, ensure_ascii=False) if bool(args.json) else "ok=true status=skipped reason=bundle_job_already_running")
            return 0
        _write_background_job_lock(
            background_lock_path,
            status="running",
            role=role,
            extra={
                "role": role,
                "target_run_id": target_run_id,
                "target_symbol": target_symbol,
            },
        )
        _log_bundle_event(
            event_log_path,
            role=role,
            event="report_bundle_lock_acquired",
            payload={
                "pid": int(os.getpid()),
                "parent_pid": int(os.getppid()),
                "role": role,
                "lock_path": str(background_lock_path or ""),
                "target_run_id": target_run_id,
                "target_symbol": target_symbol,
            },
        )
        if background_lock_path is not None:
            atexit.register(_clear_background_job_lock, background_lock_path, role=role)
    load_env_file(str(args.env_path).strip() or ".env")
    evidence_log_path = Path(str(args.evidence_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    reports_root = Path(str(args.reports_root).strip())
    intents_path = Path(str(args.intents_path).strip()) if str(args.intents_path or "").strip() else None
    day = str(args.day).strip() if args.day else _latest_execution_day(event_log_path)
    analysis_root = report_dir.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    state_store_path = Path(str(os.getenv("STATE_STORE_PATH", "data/state.json")).strip() or "data/state.json")
    runtime_state = _read_json(state_store_path)
    trade_report_policy = _resolve_trade_report_policy(runtime_state=runtime_state)
    report_requested = bool(args.trade_report_ai) if args.trade_report_ai is not None else bool(trade_report_policy.get("enabled", True))
    configured_report_model = _normalize_model_name(
        str(args.trade_report_ai_model).strip()
        if args.trade_report_ai_model
        else str(trade_report_policy.get("llm_primary") or "")
        or "minimax/minimax-m2.5"
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
        if not inprocess_no_boundary:
            _log_bundle_event(
                event_log_path,
                role=role,
                event="report_bundle_lock_released",
                payload={
                    "pid": int(os.getpid()),
                    "parent_pid": int(os.getppid()),
                    "role": role,
                    "lock_path": str(background_lock_path or ""),
                    "reason": "no_execution_day_detected",
                },
            )
            _clear_background_job_lock(background_lock_path, role=role)
        print(json.dumps(out, ensure_ascii=False) if bool(args.json) else "ok=false error=no_execution_day_detected")
        return 3

    day_event_rows = [row for row in _iter_jsonl(event_log_path) if not day or _utc_day(row.get("ts")) == day]
    day_evidence_rows = [
        row
        for row in _iter_jsonl(evidence_log_path)
        if not day or _utc_day(row.get("timestamp") or row.get("ts")) == day
    ]
    all_execution_runs = _resolve_execution_runs(event_log_path, day, event_rows=day_event_rows)
    execution_runs, target_ctx = _targeted_execution_context(
        all_execution_runs,
        target_run_id=str(args.target_run_id or "").strip(),
        target_symbol=str(args.target_symbol or "").strip(),
        max_runs=max(1, int(args.max_runs)),
    )
    targeted_mode = bool(target_ctx.get("targeted_mode"))
    if targeted_mode:
        targeted_run_ids = {
            str(run_id or "").strip()
            for run_id in list(target_ctx.get("lifecycle_context_run_ids") or [])
            if str(run_id or "").strip()
        }
        targeted_run_ids.update(
            str(row.get("run_id") or "").strip()
            for row in list(execution_runs or [])
            if str(row.get("run_id") or "").strip()
        )
        targeted_run_ids = _expand_targeted_run_ids_with_cached_strategist_sources(
            event_rows=day_event_rows,
            targeted_run_ids=targeted_run_ids,
        )
        day_event_rows = _filter_rows_by_run_ids(day_event_rows, targeted_run_ids)
        day_evidence_rows = _filter_rows_by_run_ids(day_evidence_rows, targeted_run_ids)
    if targeted_mode:
        trade_report_dir = official_trade_explain_report_dir(reports_root)
        trade_md, trade_js = _resolve_existing_day_artifact(trade_report_dir, "trade_explain", day)
        trade_obj = _read_json(trade_js) if trade_js.exists() else {}
        reporter_report_dir = analysis_root / "reporter_analysis"
        reporter_md, reporter_js = _resolve_existing_day_artifact(reporter_report_dir, "reporter_analysis", day)
        reporter_obj = _read_json(reporter_js) if reporter_js.exists() else {}
    else:
        trade_md, trade_js, trade_obj = _load_or_generate_trade_explain(event_log_path, analysis_root, day)
        reporter_md, reporter_js, reporter_obj = _load_or_generate_reporter_analysis(event_log_path, analysis_root, reports_root, intents_path, day)
    daily_paths = daily_artifact_paths(reports_root, day)
    operator_summary_json = daily_paths["operator_summary_json"]
    operator_summary_md = daily_paths["operator_summary_md"]
    canonical_trades_root = reports_root / "trades"
    year_part, month_part = (day.split("-") + ["01", "01"])[:2]

    run_bundles_by_run: Dict[str, Dict[str, Any]] = {}
    run_bundle_rows: List[Dict[str, Any]] = []
    run_story_type_counts: Dict[str, int] = {}
    for execution in execution_runs:
        run_id = str(execution.get("run_id") or "").strip()
        run_event_rows = _filter_rows_by_run_ids(day_event_rows, [run_id])
        run_evidence_rows = _filter_rows_by_run_ids(day_evidence_rows, [run_id])
        _touch_background_job_lock(
            background_lock_path,
            role=role,
            extra={
                "status": "running",
                "current_run_id": run_id,
                "current_symbol": str(execution.get("symbol") or ""),
            },
        )
        trace_md, trace_js, trace_out = _generate_agent_pipeline_trace_report_fast(
            event_log_path=event_log_path,
            evidence_log_path=evidence_log_path,
            report_dir=report_dir / "agent_pipeline_trace",
            run_id=run_id,
            day=day,
            reports_root=analysis_root,
            event_rows=run_event_rows,
            evidence_rows_all=run_evidence_rows,
        )
        hydrated_run_bundle = hydrate_live_run_bundle_context(
            reports_root=reports_root,
            day=day,
            run_id=run_id,
            execution_row=execution,
            trace_out=trace_out,
            reporter_obj=reporter_obj,
            trade_obj=trade_obj,
            trace_json_path=trace_js,
            trace_md_path=trace_md,
            trade_json_path=trade_js,
            trade_md_path=trade_md,
            reporter_json_path=reporter_js,
            reporter_md_path=reporter_md,
            operator_summary_json_path=operator_summary_json,
            operator_summary_md_path=operator_summary_md,
            bundle_ts=utc_now_iso(),
        )
        canonical_sources = dict(hydrated_run_bundle.get("canonical_sources") or {})
        bundle_out = dict(hydrated_run_bundle.get("bundle_out") or {})
        story_contract = dict(hydrated_run_bundle.get("story_contract") or {})
        story_id = str(hydrated_run_bundle.get("story_id") or "")

        bundle_json = report_dir / f"live_execution_bundle_{run_id}.json"
        bundle_md = report_dir / f"live_execution_bundle_{run_id}.md"
        bundle_out["report_json_path"] = str(bundle_json)
        bundle_out["report_md_path"] = str(bundle_md)
        bundle_json.write_text(json.dumps(bundle_out, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_md.write_text(render_bundle_markdown(bundle_out), encoding="utf-8")
        run_bundles_by_run[run_id] = bundle_out

        story_type = str(hydrated_run_bundle.get("story_type") or story_contract.get("story_type") or "unknown")
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

    run_id_set = {str(row.get("run_id") or "").strip() for row in execution_runs if str(row.get("run_id") or "").strip()}
    if targeted_mode:
        run_id_set.update(
            str(run_id or "").strip()
            for run_id in list(target_ctx.get("lifecycle_context_run_ids") or [])
            if str(run_id or "").strip()
        )
    run_snapshots = _build_run_snapshots(
        event_log_path,
        day,
        reports_root=reports_root,
        include_run_ids=run_id_set or None,
        event_rows=day_event_rows,
    )
    existing_open_lifecycles_by_symbol = _load_existing_open_lifecycle_candidates(
        reports_root=reports_root,
        day=day,
    )
    trade_lifecycles = _build_trade_lifecycles(
        day=day,
        run_snapshots=run_snapshots,
        run_bundles=run_bundles_by_run,
        existing_open_lifecycles_by_symbol=existing_open_lifecycles_by_symbol,
    )
    if bool(target_ctx.get("targeted_mode")):
        trade_lifecycles = [
            lifecycle
            for lifecycle in trade_lifecycles
            if _lifecycle_matches_target(
                lifecycle,
                target_run_id=str(target_ctx.get("target_run_id") or ""),
                target_symbol=str(target_ctx.get("target_symbol") or ""),
            )
        ]
        for lifecycle in trade_lifecycles:
            lifecycle_run_ids = [str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
            entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
            exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
            for item in (entry_ctx.get("run_id"), exit_ctx.get("run_id")):
                rid = str(item or "").strip()
                if rid and rid not in lifecycle_run_ids:
                    lifecycle_run_ids.append(rid)
            existing_trade_id = _find_existing_trade_id_for_run_ids(
                reports_root=reports_root,
                day=day,
                symbol=str(lifecycle.get("symbol") or ""),
                run_ids=lifecycle_run_ids,
            )
            if existing_trade_id:
                lifecycle["trade_id"] = existing_trade_id
    lifecycle_rows: List[Dict[str, Any]] = []
    lifecycle_story_type_counts: Dict[str, int] = {}
    run_bundle_lookup = {str(row.get("run_id") or ""): row for row in run_bundle_rows}

    for lifecycle in trade_lifecycles:
        trade_id = str(lifecycle.get("trade_id") or "").strip()
        if not trade_id:
            continue
        symbol = normalize_symbol(lifecycle.get("symbol") or "", allow_test_symbols=True)
        _touch_background_job_lock(
            background_lock_path,
            role=role,
            extra={
                "status": "running",
                "current_trade_id": trade_id,
                "current_symbol": symbol,
            },
        )
        status = str(lifecycle.get("status") or "open").strip().lower()
        story_type = str(lifecycle.get("story_type") or "decision_only").strip().lower()
        execution_mode_label_text = str(lifecycle.get("execution_mode_label") or "decision only").strip()

        entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        exit_action = str(exit_ctx.get("action") or "").strip().upper()
        entry_run_id = str(entry_ctx.get("run_id") or "")
        exit_run_id = str(exit_ctx.get("run_id") or "")
        linked_run_ids = [str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
        for rid in (entry_run_id, exit_run_id):
            if rid and rid not in linked_run_ids:
                linked_run_ids.append(rid)
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        hold_run_ids = [str(x or "").strip() for x in list(holding.get("run_ids") or []) if str(x or "").strip()]

        anchor_run_id = entry_run_id or exit_run_id or (linked_run_ids[0] if linked_run_ids else "")
        anchor_bundle = run_bundles_by_run.get(anchor_run_id) if isinstance(run_bundles_by_run.get(anchor_run_id), dict) else {}
        resolved_bundle_sources = _resolve_lifecycle_bundle_sources(
            reports_root=reports_root,
            day=day,
            anchor_bundle=anchor_bundle,
            anchor_run_id=anchor_run_id,
            entry_run_id=entry_run_id,
            exit_run_id=exit_run_id,
        )
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
        lifecycle_execution_outcome_human = dict(exit_execution_context or anchor_bundle.get("execution_outcome_human") or {})
        if not lifecycle_execution_outcome_human:
            lifecycle_execution_outcome_human = build_execution_outcome_human(
                anchor_execution,
                dict((resolved_bundle_sources.get("agents") or {}).get("executor") or anchor_bundle.get("executor") or {}),
                story_type=story_type,
                mode_label=execution_mode_label_text,
            )
        lifecycle_reporter_status_human = {
            "status": str(reporter_obj.get("status_human") or "missing"),
            "summary": str(reporter_obj.get("summary") or ""),
            "grade": str(reporter_obj.get("grade") or "N/A"),
            "bullets": [str(x or "") for x in list(reporter_obj.get("improvement_points") or [])[:6]],
        }
        lifecycle_operator_conclusion_human = dict(anchor_bundle.get("operator_conclusion_human") or {})
        if (
            not lifecycle_operator_conclusion_human
            or lifecycle_conclusion_summary_is_placeholder(lifecycle_operator_conclusion_human.get("summary"))
        ):
            lifecycle_operator_conclusion_human = build_operator_conclusion_human(
                execution=anchor_execution,
                scanner_reason_human=dict(anchor_bundle.get("scanner_reason_human") or entry_ctx.get("scanner_context") or {}),
                filters_human=dict(anchor_bundle.get("filters_human") or {}),
                monitor_reason_human=lifecycle_monitor_reason_human,
                execution_outcome_human=lifecycle_execution_outcome_human,
                reporter_status_human=lifecycle_reporter_status_human,
            )
        if not str(lifecycle_operator_conclusion_human.get("summary") or "").strip():
            lifecycle_operator_conclusion_human["summary"] = str(summary_obj.get("operator_conclusion_human") or "")
        if not str(lifecycle_operator_conclusion_human.get("current_action") or "").strip():
            lifecycle_operator_conclusion_human["current_action"] = str(
                exit_action or ("HOLD" if status == "open" else anchor_execution.get("action") or "WAIT")
            )
        if not list(lifecycle_operator_conclusion_human.get("watch_next") or []):
            lifecycle_operator_conclusion_human["watch_next"] = [
                f"생애주기 상태는 {status}입니다.",
                "모니터 트리거 변화가 있는지 확인해야 합니다.",
                "거시 환경과 뉴스 흐름 변화가 있는지 확인해야 합니다.",
            ]
        if not list(lifecycle_operator_conclusion_human.get("thesis_invalidation") or []):
            lifecycle_operator_conclusion_human["thesis_invalidation"] = [
                "손절 기준 이탈",
                "모니터와 스캐너 판단 발산",
                "거시 환경의 부정적 전환",
            ]

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
            "commander": dict((resolved_bundle_sources.get("agents") or {}).get("commander") or anchor_bundle.get("commander") or {}),
            "strategist": dict((resolved_bundle_sources.get("agents") or {}).get("strategist") or anchor_bundle.get("strategist") or {}),
            "scanner": dict((resolved_bundle_sources.get("agents") or {}).get("scanner") or anchor_bundle.get("scanner") or {}),
            "monitor": dict((resolved_bundle_sources.get("agents") or {}).get("monitor") or anchor_bundle.get("monitor") or {}),
            "supervisor": dict((resolved_bundle_sources.get("agents") or {}).get("supervisor") or anchor_bundle.get("supervisor") or {}),
            "executor": dict((resolved_bundle_sources.get("agents") or {}).get("executor") or anchor_bundle.get("executor") or {}),
            "reporter": dict(anchor_bundle.get("reporter") or {}),
            "canonical_agent_artifacts": dict(resolved_bundle_sources.get("canonical_agent_artifacts") or {}),
            "evidence_provenance": dict(resolved_bundle_sources.get("evidence_provenance") or {}),
            "market_context_human": dict(anchor_bundle.get("market_context_human") or entry_ctx.get("strategist_context") or {}),
            "scanner_reason_human": dict(anchor_bundle.get("scanner_reason_human") or entry_ctx.get("scanner_context") or {}),
            "filters_human": dict(anchor_bundle.get("filters_human") or {}),
            "monitor_reason_human": lifecycle_monitor_reason_human,
            "guard_reason_human": dict(exit_guard_context or anchor_bundle.get("guard_reason_human") or {}),
            "execution_outcome_human": lifecycle_execution_outcome_human,
            "reporter_status_human": lifecycle_reporter_status_human,
            "operator_conclusion_human": lifecycle_operator_conclusion_human,
            "timeline": list(lifecycle.get("timeline") or []),
            "warnings": list(story_contract.get("warnings") or []),
            "lifecycle_attach_debug": [dict(row) for row in list(lifecycle.get("lifecycle_attach_debug") or []) if isinstance(row, dict)],
            "trade_lifecycle": lifecycle,
            "artifacts": {
                "agent_pipeline_trace_json": str(anchor_bundle.get("artifacts", {}).get("agent_pipeline_trace_json") or ""),
                "agent_pipeline_trace_md": str(anchor_bundle.get("artifacts", {}).get("agent_pipeline_trace_md") or ""),
                "trade_explain_json": str(trade_js),
                "trade_explain_md": str(trade_md),
                "reporter_analysis_json": str(reporter_js) if reporter_js.exists() else "",
                "reporter_analysis_md": str(reporter_md) if reporter_md.exists() else "",
                "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
                "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
                "canonical_commander_json": str((resolved_bundle_sources.get("artifacts") or {}).get("canonical_commander_json") or ""),
                "canonical_strategist_json": str((resolved_bundle_sources.get("artifacts") or {}).get("canonical_strategist_json") or ""),
                "canonical_scanner_json": str((resolved_bundle_sources.get("artifacts") or {}).get("canonical_scanner_json") or ""),
                "canonical_monitor_json": str((resolved_bundle_sources.get("artifacts") or {}).get("canonical_monitor_json") or ""),
                "canonical_supervisor_json": str((resolved_bundle_sources.get("artifacts") or {}).get("canonical_supervisor_json") or ""),
                "canonical_executor_json": str((resolved_bundle_sources.get("artifacts") or {}).get("canonical_executor_json") or ""),
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
        trade_summary_input_json_path = trade_paths["ai_trade_summary_input_json"]
        trade_summary_json_path = trade_paths["ai_trade_summary_json"]
        trade_summary_md_path = trade_paths["ai_trade_summary_md"]
        trade_summary_llm_response_path = trade_paths["ai_trade_summary_llm_response_json"]
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
        operator_summary_refresh_path = trade_root / "operator_summary_refresh.json"
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
            reports_root=reports_root,
            day=day,
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
            reports_root=reports_root,
            strategist_evidence=strategist_evidence,
            evidence_rows=day_evidence_rows,
        )
        write_json(strategist_input_path, strategist_input_artifact)
        write_json(strategist_compact_input_path, strategist_compact_input_artifact)
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
        lifecycle_bundle["scanner_evidence"] = scanner_evidence if isinstance(scanner_evidence, dict) else {}
        lifecycle_bundle["monitor_evidence"] = monitor_timeline if isinstance(monitor_timeline, dict) else {}
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
            monitor_evidence=monitor_timeline,
        )
        strategy_anchor_run_id = str(
            ((strategist_input_artifact.get("meta") or {}).get("source_run_id") or "")
            or entry_run_id
            or anchor_run_id
            or ""
        ).strip()
        anchor_context = apply_strategy_anchor_metadata(
            lifecycle=lifecycle,
            lifecycle_bundle=lifecycle_bundle,
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        lifecycle = dict(anchor_context.get("lifecycle") or lifecycle)
        lifecycle_bundle = dict(anchor_context.get("lifecycle_bundle") or lifecycle_bundle)
        enriched_context = apply_entry_exit_holding_enrichment(
            lifecycle=lifecycle,
            lifecycle_bundle=lifecycle_bundle,
            summary_obj=summary_obj,
            trade_id=trade_id,
            symbol=symbol,
            status=status,
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
            entry_run_id=entry_run_id,
            exit_run_id=exit_run_id,
            hold_run_ids=hold_run_ids,
            linked_run_ids=linked_run_ids,
            monitor_timeline=monitor_timeline,
            day_event_rows=day_event_rows,
        )
        lifecycle = dict(enriched_context.get("lifecycle") or lifecycle)
        lifecycle_bundle = dict(enriched_context.get("lifecycle_bundle") or lifecycle_bundle)
        summary_obj = dict(enriched_context.get("summary_obj") or summary_obj)
        entry_ctx_live = dict(enriched_context.get("entry_ctx_live") or {})
        exit_ctx_live = dict(enriched_context.get("exit_ctx_live") or {})
        hold_run_ids = [str(x or "").strip() for x in list(enriched_context.get("hold_run_ids") or []) if str(x or "").strip()]
        linked_run_ids = [str(x or "").strip() for x in list(enriched_context.get("linked_run_ids") or []) if str(x or "").strip()]
        entry_bundle = run_bundles_by_run.get(entry_run_id) if isinstance(run_bundles_by_run.get(entry_run_id), dict) else {}
        exit_bundle = run_bundles_by_run.get(exit_run_id) if isinstance(run_bundles_by_run.get(exit_run_id), dict) else {}
        live_trade_context = apply_live_trade_context(
            lifecycle=lifecycle,
            lifecycle_bundle=lifecycle_bundle,
            summary_obj=summary_obj,
            status=status,
            monitor_timeline=monitor_timeline,
            reporter_obj=reporter_obj,
            reporter_js=reporter_js,
            reporter_md=reporter_md,
            entry_run_id=entry_run_id,
            exit_run_id=exit_run_id,
            entry_ctx_live=entry_ctx_live,
            exit_ctx_live=exit_ctx_live,
            entry_bundle=entry_bundle,
            exit_bundle=exit_bundle,
            post_exit_price_rows=_runtime_minute_rows_for_symbol(runtime_state, symbol),
        )
        lifecycle = dict(live_trade_context.get("lifecycle") or lifecycle)
        lifecycle_bundle = dict(live_trade_context.get("lifecycle_bundle") or lifecycle_bundle)
        summary_obj = dict(live_trade_context.get("summary_obj") or summary_obj)
        entry_execution_details = dict(live_trade_context.get("entry_execution_details") or {})
        exit_execution_details = dict(live_trade_context.get("exit_execution_details") or {})
        execution_details = dict(live_trade_context.get("execution_details") or {})
        holding_phase_observability = dict(live_trade_context.get("holding_phase_observability") or {})
        same_day_reporter_linkage = dict(live_trade_context.get("same_day_reporter_linkage") or {})
        trade_story_input = build_trade_story_input_from_bundle(lifecycle_bundle, trade_lifecycle=lifecycle)
        trade_story_input["day"] = day
        trade_story_input["report_runtime_mode"] = "intraday_bundle"
        trade_story_input["skip_separated_report_llm"] = True
        trade_story_input["entry_strategist_run_id"] = strategy_anchor_run_id
        trade_story_input["strategy_anchor_run_id"] = strategy_anchor_run_id
        trade_story_input["hold_duration"] = holding_phase_observability.get("hold_duration")
        trade_story_input["hold_duration_sec"] = holding_phase_observability.get("hold_duration_sec")
        trade_story_input["holding_phase_summary"] = holding_phase_observability.get("holding_phase_summary")
        trade_story_input["hold_events_count"] = holding_phase_observability.get("hold_events_count")
        trade_story_input["monitor_context_snapshots"] = list(holding_phase_observability.get("monitor_context_snapshots") or [])
        trade_story_input["hold_signal_transitions"] = list(holding_phase_observability.get("hold_signal_transitions") or [])
        trade_story_input["pre_exit_context_summary"] = dict(holding_phase_observability.get("pre_exit_context_summary") or {})
        trade_story_input["same_day_reporter_linkage"] = dict(same_day_reporter_linkage)
        trade_story_input["execution_details"] = dict(execution_details)
        trade_story_input["entry_execution_details"] = dict(entry_execution_details)
        trade_story_input["exit_execution_details"] = dict(exit_execution_details)
        trace_context = apply_trace_summary_context(
            trade_story_input=trade_story_input,
            lifecycle_bundle=lifecycle_bundle,
            scanner_evidence=scanner_evidence if isinstance(scanner_evidence, dict) else {},
        )
        trade_story_input = dict(trace_context.get("trade_story_input") or trade_story_input)
        lifecycle_bundle = dict(trace_context.get("lifecycle_bundle") or lifecycle_bundle)
        policy_gate = _seed_diagnostics_for_policy(
            lifecycle_status=status,
            story_type=story_type,
            report_requested=report_requested,
            story_input_available=bool(trade_story_input),
            model_hint=configured_report_model,
            generate_on_open=bool(_resolve_trade_report_policy(runtime_state=runtime_state, story_input=trade_story_input).get("generate_on_open", True)),
        )
        diagnostics = dict(policy_gate.get("diagnostics") or {})
        should_attempt_generation = bool(policy_gate.get("should_attempt_generation"))
        diagnostics = apply_runtime_diagnostics_context(
            diagnostics,
            holding_phase_observability=holding_phase_observability,
            same_day_reporter_linkage=same_day_reporter_linkage,
            execution_details=execution_details,
        )

        strategist_llm_artifact_raw = _build_strategist_llm_response_artifact(
            lifecycle_bundle,
            day=day,
            trade_id=trade_id,
            strategist_evidence=strategist_evidence,
            evidence_rows=day_evidence_rows,
        )
        strategist_llm_artifact = {}
        existing_brief_llm_artifact = _read_json_if_exists(trade_paths["brief_llm_response_json"])
        diagnostics["llm_brief_status"] = canonical_llm_status(
            existing_brief_llm_artifact.get("llm_status") or existing_brief_llm_artifact.get("status") or "skipped",
            default="skipped",
        )
        trade_story_compact_input = build_ai_trade_report_compact_input(trade_story_input)
        generation_state_path = _report_generation_state_path(trade_paths)
        generation_state = _load_report_generation_state(generation_state_path)
        generation_components = (
            generation_state.get("components") if isinstance(generation_state.get("components"), dict) else {}
        )
        ai_trade_report_generation_state = (
            generation_components.get("ai_trade_report")
            if isinstance(generation_components.get("ai_trade_report"), dict)
            else {}
        )
        ai_trade_report_fingerprint_info = _build_component_fingerprint(
            component="ai_trade_report",
            trade_id=trade_id,
            run_id=str(anchor_run_id or ""),
            lifecycle_status=status,
            story_type=story_type,
            model=str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else configured_report_model,
            story_input=trade_story_input,
            compact_input=trade_story_compact_input,
        )
        ai_trade_report_fingerprint = str(ai_trade_report_fingerprint_info.get("fingerprint") or "")

        deterministic_report = build_deterministic_trade_report(trade_story_input)
        trade_report: Dict[str, Any] = dict(deterministic_report)
        diagnostics["deterministic_report_status"] = "ok"
        diagnostics["ai_trade_report_status"] = "skipped"
        ai_trade_report_llm_artifact: Dict[str, Any] = {}
        existing_trade_report_artifact = _read_json_if_exists(trade_report_json_path)
        existing_ai_trade_report_llm_artifact = _read_json_if_exists(ai_trade_report_llm_response_path)
        existing_story_input_artifact = _read_json_if_exists(story_input_path)
        generation_plan = plan_live_trade_report_generation(
            should_attempt_generation=should_attempt_generation,
            report_requested=report_requested,
            diagnostics=dict(diagnostics),
            deterministic_report=dict(deterministic_report),
            existing_trade_report_artifact=dict(existing_trade_report_artifact or {}),
            existing_ai_trade_report_llm_artifact=dict(existing_ai_trade_report_llm_artifact or {}),
            ai_trade_report_generation_state=dict(ai_trade_report_generation_state or {}),
            ai_trade_report_fingerprint=ai_trade_report_fingerprint,
            trade_report_json_path=trade_report_json_path,
            trade_report_md_path=trade_report_md_path,
            configured_report_model=configured_report_model,
            existing_report_noisy=_has_report_text_corruption(existing_trade_report_artifact),
        )
        diagnostics = dict(generation_plan.get("diagnostics") or diagnostics)
        trade_report = dict(generation_plan.get("trade_report") or deterministic_report)
        ai_trade_report_llm_artifact = dict(
            generation_plan.get("ai_trade_report_llm_artifact") or {}
        )
        for event_spec in list(generation_plan.get("log_events") or []):
            if not isinstance(event_spec, dict):
                continue
            _log_bundle_event(
                event_log_path,
                role=role,
                event=str(event_spec.get("event") or "report_generation_event"),
                run_id=str(anchor_run_id or "report-bundle"),
                symbol=symbol,
                trade_id=trade_id,
                payload={
                    "pid": int(os.getpid()),
                    "parent_pid": int(os.getppid()),
                    "role": role,
                    "component": str(event_spec.get("component") or "ai_trade_report"),
                    "trade_id": trade_id,
                    "run_id": str(anchor_run_id or ""),
                    "fingerprint": str(event_spec.get("fingerprint") or ""),
                    "reason": str(event_spec.get("reason") or ""),
                },
            )
        if str(generation_plan.get("mode") or "") == "generate_ai":
            _log_bundle_event(
                event_log_path,
                role=role,
                event="ai_trade_report_generation_started",
                run_id=str(anchor_run_id or "report-bundle"),
                symbol=symbol,
                trade_id=trade_id,
                payload={
                    "pid": int(os.getpid()),
                    "parent_pid": int(os.getppid()),
                    "role": role,
                    "component": "ai_trade_report",
                    "trade_id": trade_id,
                    "run_id": str(anchor_run_id or ""),
                    "model": str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else configured_report_model,
                    "report_requested": bool(report_requested),
                    "should_attempt_generation": bool(should_attempt_generation),
                    "story_type": str(story_type or ""),
                    "lifecycle_status": str(status or ""),
                },
            )
            try:
                generation_result = execute_ai_trade_report_generation(
                    trade_story_input=dict(trade_story_input or {}),
                    diagnostics=dict(diagnostics),
                    deterministic_report=dict(deterministic_report),
                    configured_report_model=configured_report_model,
                    ai_report_builder=build_ai_trade_report,
                    model=str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else configured_report_model,
                    temperature=args.trade_report_ai_temperature,
                    max_tokens=args.trade_report_ai_max_tokens,
                )
                diagnostics = dict(generation_result.get("diagnostics") or diagnostics)
                trade_report = dict(generation_result.get("trade_report") or deterministic_report)
                ai_trade_report_llm_artifact = dict(
                    generation_result.get("ai_trade_report_llm_artifact") or {}
                )
            except Exception as exc:
                diagnostics = dict(diagnostics or {})
                diagnostics["ai_trade_report_status"] = "error"
                diagnostics["report_status"] = "available"
                diagnostics["report_reason_code"] = "llm_generation_failed"
                diagnostics["report_reason_human"] = _report_reason_human("llm_generation_failed")
                diagnostics["report_generation_reason"] = str(diagnostics.get("report_reason_human") or "")
                diagnostics["next_expected_step"] = _report_next_step("llm_generation_failed")
                diagnostics["last_error_message"] = _sanitize_error_message(exc)
                trade_report = dict(deterministic_report)
                ai_trade_report_llm_artifact = build_llm_response_artifact(
                    component="ai_trade_report",
                    run_id=str(anchor_run_id or ""),
                    trade_id=trade_id,
                    story_id=trade_id,
                    day=day,
                    status="error",
                    attempts=[],
                    parsed_output={},
                    model_info={
                        "provider": "OpenRouter",
                        "model": str(args.trade_report_ai_model).strip() if args.trade_report_ai_model else configured_report_model,
                    },
                    latency_ms=0,
                    meta={
                        "reason_code": "llm_generation_failed",
                        "reason": _sanitize_error_message(exc),
                        "exception_class": exc.__class__.__name__,
                    },
                )
            llm_meta = (
                ai_trade_report_llm_artifact.get("meta")
                if isinstance(ai_trade_report_llm_artifact.get("meta"), dict)
                else {}
            )
            _log_bundle_event(
                event_log_path,
                role=role,
                event="ai_trade_report_generation_finished",
                run_id=str(anchor_run_id or "report-bundle"),
                symbol=symbol,
                trade_id=trade_id,
                payload={
                    "pid": int(os.getpid()),
                    "parent_pid": int(os.getppid()),
                    "role": role,
                    "component": "ai_trade_report",
                    "trade_id": trade_id,
                    "run_id": str(anchor_run_id or ""),
                    "ai_trade_report_status": str(diagnostics.get("ai_trade_report_status") or ""),
                    "report_status": str(diagnostics.get("report_status") or ""),
                    "report_reason_code": str(diagnostics.get("report_reason_code") or ""),
                    "report_generation_reason": str(diagnostics.get("report_generation_reason") or ""),
                    "llm_status": str(ai_trade_report_llm_artifact.get("llm_status") or ai_trade_report_llm_artifact.get("status") or ""),
                    "llm_reason": str(llm_meta.get("reason") or ""),
                    "llm_error": str(ai_trade_report_llm_artifact.get("error") or ""),
                    "model": str(diagnostics.get("llm_model_used") or configured_report_model or ""),
                },
            )

        report_output_persistence = persist_trade_report_outputs(
            trade_report=dict(trade_report or {}),
            diagnostics=dict(diagnostics),
            trade_report_json_path=trade_report_json_path,
            trade_report_md_path=trade_report_md_path,
            markdown_renderer=render_trade_report_markdown,
            write_failure_reason_human=_report_reason_human("artifact_write_failed"),
            write_failure_next_step=_report_next_step("artifact_write_failed"),
            error_sanitizer=_sanitize_error_message,
            trade_summary_input_json_path=trade_summary_input_json_path,
            summary_input_builder=build_trade_summary_input,
            trade_summary_md_path=trade_summary_md_path,
            summary_markdown_renderer=lambda payload: render_trade_summary_markdown_with_evaluation(payload, {}),
        )
        diagnostics = dict(report_output_persistence.get("diagnostics") or diagnostics)
        trade_report_json_written = str(
            report_output_persistence.get("trade_report_json_written") or ""
        )
        trade_report_md_written = str(
            report_output_persistence.get("trade_report_md_written") or ""
        )
        trade_summary_md_written = str(
            report_output_persistence.get("trade_summary_md_written") or ""
        )
        trade_summary_input_json_written = str(
            report_output_persistence.get("trade_summary_input_json_written") or ""
        )
        trade_summary_json_written = ""
        trade_summary_llm_response_written = ""
        ai_trade_report_llm_response_written = ""

        llm_persistence = persist_trade_llm_artifacts(
            reports_root=reports_root,
            day=day,
            strategy_anchor_run_id=str(strategy_anchor_run_id or ""),
            anchor_run_id=str(anchor_run_id or ""),
            strategist_llm_artifact_raw=dict(strategist_llm_artifact_raw or {}),
            strategist_llm_response_path=strategist_llm_response_path,
            ai_trade_report_llm_artifact=dict(ai_trade_report_llm_artifact or {}),
            ai_trade_report_llm_response_path=ai_trade_report_llm_response_path,
        )
        strategist_llm_artifact = dict(llm_persistence.get("strategist_llm_artifact") or {})
        ai_trade_report_llm_artifact = dict(
            llm_persistence.get("ai_trade_report_llm_artifact") or ai_trade_report_llm_artifact
        )
        ai_trade_report_llm_response_written = str(
            llm_persistence.get("ai_trade_report_llm_response_written") or ""
        )

        generation_state_payload = build_live_generation_state_payload(
            current_state=dict(generation_state or {}),
            generation_components=dict(generation_components or {}),
            ai_trade_report_fingerprint=ai_trade_report_fingerprint,
            trade_id=trade_id,
            run_id=str(anchor_run_id or ""),
            diagnostics=dict(diagnostics),
            configured_report_model=configured_report_model,
            trade_report_json_path=trade_report_json_path,
            trade_report_md_path=trade_report_md_path,
            ai_trade_report_llm_response_path=ai_trade_report_llm_response_path,
            ai_trade_report_llm_response_written=ai_trade_report_llm_response_written,
            ai_trade_report_fingerprint_info=dict(ai_trade_report_fingerprint_info or {}),
            operator_brief_json_path=operator_brief_json_path,
            operator_brief_md_path=operator_brief_md_path,
            brief_llm_response_path=brief_llm_response_path,
        )
        generation_state = dict(generation_state_payload.get("generation_state") or {})
        generation_components = dict(generation_state_payload.get("generation_components") or {})
        _write_report_generation_state(generation_state_path, generation_state)
        failure_classification = _build_failure_classification(
            lifecycle=lifecycle,
            diagnostics=diagnostics,
            same_day_reporter_linkage=same_day_reporter_linkage,
            holding_phase_observability=holding_phase_observability,
            execution_details=execution_details,
        )
        final_context = apply_final_trade_report_context(
            lifecycle=lifecycle,
            lifecycle_bundle=lifecycle_bundle,
            trade_story_input=trade_story_input,
            trade_report=trade_report,
            diagnostics=diagnostics,
            failure_classification=failure_classification,
            same_day_reporter_linkage=same_day_reporter_linkage,
            execution_details=execution_details,
            strategist_evidence=strategist_evidence,
            scanner_evidence=scanner_evidence,
            monitor_timeline=monitor_timeline,
            commander_evidence=commander_evidence,
            lifecycle_bundle_path=lifecycle_bundle_path,
            entry_artifact_path=entry_artifact_path,
            hold_artifact_path=hold_artifact_path,
            exit_artifact_path=exit_artifact_path,
            operator_brief_json_path=operator_brief_json_path,
            operator_brief_md_path=operator_brief_md_path,
            story_input_path=story_input_path,
            story_compact_input_path=story_compact_input_path,
            trade_report_json_written=trade_report_json_written,
            trade_report_md_written=trade_report_md_written,
            strategist_llm_response_path=strategist_llm_response_path,
            ai_trade_report_llm_response_written=ai_trade_report_llm_response_written,
            brief_llm_response_path=brief_llm_response_path,
            strategist_evidence_path=strategist_evidence_path,
            scanner_evidence_path=scanner_evidence_path,
            monitor_evidence_path=monitor_evidence_path,
            commander_evidence_path=commander_evidence_path,
            trade_provenance_path=trade_provenance_path,
            trade_health_path=trade_health_path,
            trade_artifact_links_path=trade_artifact_links_path,
            has_substantive_entry_evidence_fn=_has_substantive_entry_evidence,
        )
        lifecycle = dict(final_context.get("lifecycle") or lifecycle)
        lifecycle_bundle = dict(final_context.get("lifecycle_bundle") or lifecycle_bundle)
        trade_story_input = dict(final_context.get("trade_story_input") or trade_story_input)
        trade_report = dict(final_context.get("trade_report") or trade_report)
        trade_report = _attach_post_exit_shadow_to_trade_report(
            trade_report,
            lifecycle=lifecycle,
            lifecycle_bundle=lifecycle_bundle,
        )
        section_provenance = dict(final_context.get("section_provenance") or {})
        evidence_completeness = dict(final_context.get("evidence_completeness") or {})
        recovery_metadata = dict(final_context.get("recovery_metadata") or {})
        resolved_operator_brief_json = str(
            final_context.get("resolved_operator_brief_json") or operator_brief_json_path
        )
        resolved_operator_brief_md = str(
            final_context.get("resolved_operator_brief_md") or operator_brief_md_path
        )
        resolved_brief_llm_response_json = str(
            final_context.get("resolved_brief_llm_response_json") or brief_llm_response_path
        )

        if trade_report:
            refresh_trade_report_outputs_if_written(
                trade_report=dict(trade_report),
                trade_report_json_written=trade_report_json_written,
                trade_report_json_path=trade_report_json_path,
                trade_report_md_path=trade_report_md_path,
                markdown_renderer=render_trade_report_markdown,
                trade_summary_input_json_path=trade_summary_input_json_path,
                summary_input_builder=build_trade_summary_input,
                trade_summary_md_path=trade_summary_md_path,
                summary_markdown_renderer=lambda payload: render_trade_summary_markdown_with_evaluation(payload, {}),
            )
            trade_summary_input_payload = build_trade_summary_input(dict(trade_report))
            trade_summary_report_payload = build_trade_summary_report(
                trade_summary_input_payload,
                enabled=bool(report_requested and should_attempt_generation),
                model=configured_report_model,
                temperature=0.1,
                max_tokens=1200,
            )
            write_json(trade_summary_input_json_path, trade_summary_input_payload)
            write_json(trade_summary_json_path, trade_summary_report_payload)
            trade_summary_json_written = str(trade_summary_json_path)
            trade_summary_md_path.write_text(
                render_trade_summary_markdown_with_evaluation(
                    dict(trade_report),
                    trade_summary_report_payload,
                ),
                encoding="utf-8",
            )
            trade_summary_md_written = str(trade_summary_md_path)
            trade_summary_llm_artifact = (
                trade_summary_report_payload.get("llm_response_artifact")
                if isinstance(trade_summary_report_payload.get("llm_response_artifact"), dict)
                else {}
            )
            if trade_summary_llm_artifact:
                trade_summary_llm_compact = persist_llm_artifact_refs(
                    artifact=trade_summary_llm_artifact,
                    reports_root=reports_root,
                    day=day,
                    run_id=str(anchor_run_id or ""),
                    component="ai_trade_summary",
                )
                write_json(trade_summary_llm_response_path, trade_summary_llm_compact)
                trade_summary_llm_response_written = str(trade_summary_llm_response_path)

        artifact_presence = {
            "lifecycle_bundle_json": lifecycle_bundle_path.exists(),
            "entry_json": entry_artifact_path.exists(),
            "hold_json": hold_artifact_path.exists(),
            "exit_json": exit_artifact_path.exists(),
            "ai_trade_report_input_json": story_input_path.exists(),
            "ai_trade_report_compact_input_json": story_compact_input_path.exists(),
            "ai_trade_report_json": bool(trade_report_json_written),
            "ai_trade_report_md": bool(trade_report_md_written),
            "ai_trade_summary_input_json": bool(trade_summary_input_json_written) or trade_summary_input_json_path.exists(),
            "ai_trade_summary_json": bool(trade_summary_json_written) or trade_summary_json_path.exists(),
            "ai_trade_summary_md": bool(trade_summary_md_written) or trade_summary_md_path.exists(),
            "strategist_evidence_json": strategist_evidence_path.exists(),
            "scanner_evidence_json": scanner_evidence_path.exists(),
            "monitor_evidence_json": monitor_evidence_path.exists(),
            "commander_evidence_json": commander_evidence_path.exists(),
            "strategist_llm_response_json": strategist_llm_response_path.exists(),
            "ai_trade_report_llm_response_json": bool(ai_trade_report_llm_response_written),
            "ai_trade_summary_llm_response_json": bool(trade_summary_llm_response_written) or trade_summary_llm_response_path.exists(),
            "brief_llm_response_json": trade_paths["brief_llm_response_json"].exists(),
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

        persisted_story_inputs = persist_live_story_input_artifacts(
            day=day,
            trade_id=trade_id,
            anchor_run_id=str(anchor_run_id or ""),
            status=status,
            should_attempt_generation=should_attempt_generation,
            trade_story_input=trade_story_input,
            trade_story_compact_input=trade_story_compact_input,
            existing_trade_report_artifact=existing_trade_report_artifact,
            existing_story_input_artifact=existing_story_input_artifact,
            story_input_path=story_input_path,
            story_compact_input_path=story_compact_input_path,
            diagnostics=dict(diagnostics),
        )
        story_input_to_persist = dict(persisted_story_inputs.get("story_input_to_persist") or {})
        trade_story_compact_artifact = dict(persisted_story_inputs.get("trade_story_compact_artifact") or {})
        diagnostics = dict(persisted_story_inputs.get("diagnostics") or diagnostics)
        bundle_payloads = build_live_trade_bundle_payloads(
            day=day,
            trade_id=trade_id,
            run_id=str(anchor_run_id or ""),
            symbol=symbol,
            status=status,
            lifecycle=lifecycle,
            lifecycle_bundle=lifecycle_bundle,
            story_input=story_input_to_persist,
            summary_obj=summary_obj,
            diagnostics=dict(diagnostics),
            recovery_metadata=recovery_metadata,
            story_contract=story_contract,
            anchor_execution=anchor_execution,
            linked_run_ids=linked_run_ids,
            same_day_reporter_linkage=same_day_reporter_linkage,
            failure_classification=failure_classification,
            execution_details=execution_details,
            entry_execution_details=entry_execution_details,
            exit_execution_details=exit_execution_details,
            holding_phase_observability=holding_phase_observability,
            strategist_llm_artifact=strategist_llm_artifact,
            existing_brief_llm_artifact=existing_brief_llm_artifact,
            ai_trade_report_llm_artifact=ai_trade_report_llm_artifact,
            trade_report=trade_report,
            evidence_completeness_missing_sections=list(evidence_completeness.get("missing_sections") or []),
            phase3_missing_sections=phase3_missing_sections,
            phase3_completeness_score=phase3_completeness_score,
            strategist_event_count=int((lifecycle.get("evidence") or {}).get("strategist_event_count") or 0),
            scanner_event_count=int((lifecycle.get("evidence") or {}).get("scanner_event_count") or 0),
            monitor_event_count=int((lifecycle.get("evidence") or {}).get("monitor_event_count") or 0),
            operator_brief_json_exists=bool(operator_brief_json_path.exists()),
            lifecycle_bundle_path=lifecycle_bundle_path,
            entry_artifact_path=entry_artifact_path,
            hold_artifact_path=hold_artifact_path,
            exit_artifact_path=exit_artifact_path,
            story_input_path=story_input_path,
            story_compact_input_path=story_compact_input_path,
            trade_report_json_path=trade_report_json_path,
            trade_report_md_path=trade_report_md_path,
            strategist_evidence_path=strategist_evidence_path,
            scanner_evidence_path=scanner_evidence_path,
            monitor_evidence_path=monitor_evidence_path,
            commander_evidence_path=commander_evidence_path,
            strategist_llm_response_path=strategist_llm_response_path,
            ai_trade_report_llm_response_path=ai_trade_report_llm_response_path,
            brief_llm_response_path=trade_paths["brief_llm_response_json"],
            operator_brief_json_path=operator_brief_json_path,
            operator_brief_md_path=operator_brief_md_path,
            trade_provenance_path=trade_provenance_path,
            trade_health_path=trade_health_path,
            trade_artifact_links_path=trade_artifact_links_path,
            resolved_operator_brief_json=resolved_operator_brief_json,
            resolved_operator_brief_md=resolved_operator_brief_md,
            resolved_brief_llm_response_json=resolved_brief_llm_response_json,
            trade_report_json_written=trade_report_json_written,
            trade_report_md_written=trade_report_md_written,
            ai_trade_report_llm_response_written=ai_trade_report_llm_response_written,
        )
        entry_payload = dict(bundle_payloads.get("entry_payload") or {})
        holding_payload = dict(bundle_payloads.get("holding_payload") or {})
        exit_payload = dict(bundle_payloads.get("exit_payload") or {})
        lifecycle_bundle_v1 = dict(bundle_payloads.get("lifecycle_bundle_payload") or {})
        trade_provenance_payload = dict(bundle_payloads.get("trade_provenance_payload") or {})
        trade_health_payload = dict(bundle_payloads.get("trade_health_payload") or {})
        trade_artifact_links_payload = dict(bundle_payloads.get("trade_artifact_links_payload") or {})
        artifact_presence = dict(bundle_payloads.get("artifact_presence") or artifact_presence)

        persisted_trade_outputs = persist_trade_bundle_outputs(
            entry_artifact_path=entry_artifact_path,
            hold_artifact_path=hold_artifact_path,
            exit_artifact_path=exit_artifact_path,
            lifecycle_bundle_path=lifecycle_bundle_path,
            trade_provenance_path=trade_provenance_path,
            trade_health_path=trade_health_path,
            trade_artifact_links_path=trade_artifact_links_path,
            story_input_path=story_input_path,
            story_compact_input_path=story_compact_input_path,
            trade_report_json_path=trade_report_json_path,
            trade_report_md_path=trade_report_md_path,
            strategist_evidence_path=strategist_evidence_path,
            scanner_evidence_path=scanner_evidence_path,
            monitor_evidence_path=monitor_evidence_path,
            commander_evidence_path=commander_evidence_path,
            strategist_llm_response_path=strategist_llm_response_path,
            ai_trade_report_llm_response_path=ai_trade_report_llm_response_path,
            brief_llm_response_path=trade_paths["brief_llm_response_json"],
            operator_brief_json_path=operator_brief_json_path,
            operator_brief_md_path=operator_brief_md_path,
            entry_payload=entry_payload,
            holding_payload=holding_payload,
            exit_payload=exit_payload,
            lifecycle_bundle_payload=lifecycle_bundle_v1,
            trade_provenance_payload=trade_provenance_payload,
            trade_health_payload=trade_health_payload,
            trade_artifact_links_payload=trade_artifact_links_payload,
            diagnostics=dict(diagnostics),
            trade_summary_input_json_path=trade_summary_input_json_path,
            trade_summary_json_path=trade_summary_json_path,
            trade_summary_md_path=trade_summary_md_path,
            trade_summary_llm_response_path=trade_summary_llm_response_path,
        )
        artifact_presence = dict(persisted_trade_outputs.get("artifact_presence") or {})
        trade_health_payload = dict(persisted_trade_outputs.get("trade_health_payload") or {})

        operator_summary_refresh: Dict[str, Any] = {}
        try:
            operator_summary_refresh = refresh_operator_summaries_after_trade(
                reports_root=reports_root,
                event_log_path=event_log_path,
                day=day,
                symbol=symbol,
            )
        except Exception as exc:
            operator_summary_refresh = {
                "schema_version": "operator_summary_refresh.v1",
                "day": day,
                "symbol": symbol,
                "status": "error",
                "artifacts": {},
                "errors": [{"layer": "refresh", "error": _sanitize_error_message(exc)}],
            }
        write_json(operator_summary_refresh_path, operator_summary_refresh)
        _log_bundle_event(
            event_log_path,
            role=role,
            event="operator_summary_refresh_finished",
            run_id=str(anchor_run_id or "report-bundle"),
            symbol=symbol,
            trade_id=trade_id,
            payload={
                "trade_id": trade_id,
                "symbol": symbol,
                "day": day,
                "status": str(operator_summary_refresh.get("status") or ""),
                "artifact_path": str(operator_summary_refresh_path),
                "layers": sorted(
                    str(key)
                    for key in dict(operator_summary_refresh.get("artifacts") or {}).keys()
                ),
                "error_count": len(list(operator_summary_refresh.get("errors") or [])),
            },
            level="warning" if str(operator_summary_refresh.get("status") or "") in {"partial", "error"} else "info",
        )

        backfill_payload = build_live_bundle_backfill_payload(
            trade_id=trade_id,
            status=status,
            story_type=story_type,
            execution_mode_label=execution_mode_label_text,
            symbol=symbol,
            entry_run_id=entry_run_id,
            hold_run_ids=hold_run_ids,
            exit_run_id=exit_run_id,
            linked_run_ids=linked_run_ids,
            lifecycle_summary=str(summary_obj.get("lifecycle_summary_human") or ""),
            lifecycle_bundle_path=lifecycle_bundle_path,
            story_input_path=story_input_path,
            story_compact_input_path=story_compact_input_path,
            trade_report_json_written=trade_report_json_written,
            trade_report_md_written=trade_report_md_written,
            strategist_llm_response_path=strategist_llm_response_path,
            ai_trade_report_llm_response_written=ai_trade_report_llm_response_written,
            entry_artifact_path=entry_artifact_path,
            hold_artifact_path=hold_artifact_path,
            exit_artifact_path=exit_artifact_path,
            strategist_evidence_path=strategist_evidence_path,
            scanner_evidence_path=scanner_evidence_path,
            monitor_evidence_path=monitor_evidence_path,
            commander_evidence_path=commander_evidence_path,
            trade_provenance_path=trade_provenance_path,
            trade_health_path=trade_health_path,
            trade_artifact_links_path=trade_artifact_links_path,
            trade_root=trade_root,
            trade_report_summary=str((trade_report.get("executive_summary") or {}).get("summary") or ""),
            diagnostics=dict(diagnostics),
        )
        lifecycle_story_type_counts[story_type] = int(lifecycle_story_type_counts.get(story_type, 0) + 1)
        lifecycle_rows.append(dict(backfill_payload.get("lifecycle_row") or {}))

        apply_live_bundle_backfill(
            linked_run_ids=linked_run_ids,
            run_bundle_lookup=run_bundle_lookup,
            run_bundles_by_run=run_bundles_by_run,
            backfill_payload=backfill_payload,
            trade_id=trade_id,
            diagnostics=dict(diagnostics),
        )

    summary_out: Dict[str, Any] = build_live_execution_summary_payload(
        day=day,
        role=role,
        event_log_path=event_log_path,
        evidence_log_path=evidence_log_path,
        lifecycle_rows=lifecycle_rows,
        run_bundle_rows=run_bundle_rows,
        lifecycle_story_type_counts=lifecycle_story_type_counts,
        run_story_type_counts=run_story_type_counts,
        target_ctx=target_ctx,
        canonical_trades_root=canonical_trades_root,
        trade_js=trade_js,
        trade_md=trade_md,
        reporter_js=reporter_js,
        reporter_md=reporter_md,
        operator_summary_json=operator_summary_json,
        operator_summary_md=operator_summary_md,
    )
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
    if inprocess_no_boundary:
        return 0
    queue_path = _background_job_queue_path()
    next_queued_request = _pop_next_background_job_request(
        queue_path,
        current_run_id=str(target_ctx.get("target_run_id") or ""),
        current_symbol=str(target_ctx.get("target_symbol") or ""),
    )
    _log_bundle_event(
        event_log_path,
        role=role,
        event="report_bundle_lock_released",
        payload={
            "pid": int(os.getpid()),
            "parent_pid": int(os.getppid()),
            "role": role,
            "lock_path": str(background_lock_path or ""),
            "reason": "completed",
            "bundle_count": len(lifecycle_rows),
            "target_run_id": str(target_ctx.get("target_run_id") or ""),
            "target_symbol": str(target_ctx.get("target_symbol") or ""),
        },
    )
    _clear_background_job_lock(background_lock_path, role=role)
    if next_queued_request:
        _spawn_followup_background_job(
            next_queued_request,
            args=args,
            role=role,
            event_log_path=event_log_path,
        )
    return 0


def run_live_execution_bundle_inprocess(argv: Optional[List[str]] = None) -> Tuple[int, str]:
    previous = os.environ.get("INTRADAY_TRADE_REPORT_INPROCESS_NO_BOUNDARY")
    stdout = io.StringIO()
    try:
        os.environ["INTRADAY_TRADE_REPORT_INPROCESS_NO_BOUNDARY"] = "1"
        with contextlib.redirect_stdout(stdout):
            rc = main(argv)
    finally:
        if previous is None:
            os.environ.pop("INTRADAY_TRADE_REPORT_INPROCESS_NO_BOUNDARY", None)
        else:
            os.environ["INTRADAY_TRADE_REPORT_INPROCESS_NO_BOUNDARY"] = previous
    return int(rc), stdout.getvalue().strip()


if __name__ == "__main__":
    raise SystemExit(main())

