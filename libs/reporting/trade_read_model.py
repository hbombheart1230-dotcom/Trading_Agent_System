from __future__ import annotations

"""Read-only reporting/trade artifact helpers for Phase 5-2.

This module is the stable non-UI surface for loading and normalizing
trade report / operator brief artifacts. UI modules may still wrap these
helpers, but the parsing and normalization ownership lives here.
"""

from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional

from libs.reporting.strategy_read_model import (
    build_recent_strategist_feedback_window,
    normalize_strategist_feedback_input,
)


def _pick_first_existing(*paths: Path) -> Path:
    for path in paths:
        if isinstance(path, Path) and path.exists():
            return path
    return Path()


def trade_report_artifact_payload(trade_report: Dict[str, Any], key: str) -> Dict[str, Any]:
    payload = trade_report.get(key) if isinstance(trade_report, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _section_value_quality(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, str):
        lower = value.strip().lower()
        if not lower or lower in {"not_captured", "-", "unknown", "none"} or "not_captured" in lower:
            return 0
        return 2
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        return 1
    if isinstance(value, list):
        return sum(_section_value_quality(item) for item in value[:12])
    if isinstance(value, dict):
        return sum(_section_value_quality(item) for item in list(value.values())[:20])
    return 0


def prefer_richer_trade_report_section(*sections: Any) -> Dict[str, Any]:
    best: Dict[str, Any] = {}
    best_score = -1
    for section in sections:
        if not isinstance(section, dict) or not section:
            continue
        score = 0
        for _, value in section.items():
            score += _section_value_quality(value)
        if score > best_score:
            best = section
            best_score = score
    return dict(best or {})


def trade_report_section_summary(section: Dict[str, Any], fallback: str = "") -> str:
    if not isinstance(section, dict):
        return str(fallback or "")
    return str(section.get("summary") or fallback or "")


def trade_report_section_bullets(section: Dict[str, Any], *, limit: int = 6) -> List[str]:
    if not isinstance(section, dict):
        return []
    return [str(x or "") for x in list(section.get("bullets") or [])[:limit] if str(x or "").strip()]


def normalize_trade_report_section(
    report: Dict[str, Any],
    key: str,
    fallback_summary: str = "",
    *,
    trim_text: Callable[..., str],
    clean_str_list: Callable[..., List[str]],
) -> Dict[str, Any]:
    section = report.get(key) if isinstance(report.get(key), dict) else {}
    return {
        "summary": trim_text(section.get("summary"), max_len=1000) or trim_text(fallback_summary, max_len=1000),
        "bullets": clean_str_list(section.get("bullets"), limit=12, max_len=280),
        "status": trim_text(section.get("status"), max_len=64),
        "grade": trim_text(section.get("grade"), max_len=32),
    }


def normalize_trade_report_detail_sections(
    report: Dict[str, Any],
    *,
    fallback_summaries: Dict[str, str],
    trim_text: Callable[..., str],
    clean_str_list: Callable[..., List[str]],
) -> Dict[str, Any]:
    executive = normalize_trade_report_section(
        report,
        "executive_summary",
        fallback_summaries.get("executive_summary", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    market_context = normalize_trade_report_section(
        report,
        "market_context_at_entry",
        fallback_summaries.get("market_context_at_entry", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    why_symbol = normalize_trade_report_section(
        report,
        "why_this_symbol_was_chosen",
        fallback_summaries.get("why_this_symbol_was_chosen", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    scanner_filters = normalize_trade_report_section(
        report,
        "scanner_filters",
        fallback_summaries.get("scanner_filters", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    entry_decision = normalize_trade_report_section(
        report,
        "entry_decision",
        fallback_summaries.get("entry_decision", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    holding_story = normalize_trade_report_section(
        report,
        "holding_monitoring_story",
        fallback_summaries.get("holding_monitoring_story", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    exit_decision = normalize_trade_report_section(
        report,
        "exit_decision",
        fallback_summaries.get("exit_decision", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    execution_quality = normalize_trade_report_section(
        report,
        "execution_quality",
        fallback_summaries.get("execution_quality", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    guard_result = normalize_trade_report_section(
        report,
        "guard_approval_result",
        fallback_summaries.get("guard_approval_result", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    reporter_eval = normalize_trade_report_section(
        report,
        "reporter_evaluation",
        fallback_summaries.get("reporter_evaluation", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    weak_points = normalize_trade_report_section(
        report,
        "errors_weaknesses_improvement_points",
        fallback_summaries.get("errors_weaknesses_improvement_points", ""),
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    return {
        "executive_summary": executive,
        "market_context": market_context,
        "why_this_symbol": why_symbol,
        "scanner_filters": scanner_filters,
        "entry_decision": entry_decision,
        "holding_monitoring_story": holding_story,
        "exit_decision": exit_decision,
        "execution_quality": execution_quality,
        "guard_approval_result": guard_result,
        "reporter_evaluation": reporter_eval,
        "errors_weaknesses_improvement_points": weak_points,
        "review_focus": {
            "why_entered": trim_text(entry_decision.get("summary"), max_len=320),
            "why_held": trim_text(holding_story.get("summary"), max_len=320),
            "why_exited": trim_text(exit_decision.get("summary"), max_len=320),
            "execution_quality": trim_text(execution_quality.get("summary"), max_len=320),
            "improvement_focus": trim_text(weak_points.get("summary"), max_len=320),
        },
    }


def normalize_trade_report_detail_meta(
    report: Dict[str, Any],
    *,
    operator_conclusion_human: Dict[str, Any],
    action: str,
    trim_text: Callable[..., str],
    clean_str_list: Callable[..., List[str]],
) -> Dict[str, Any]:
    final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    return {
        "final_operator_conclusion": {
            "summary": trim_text(final_conclusion.get("summary"), max_len=1000) or trim_text(operator_conclusion_human.get("summary"), max_len=1000),
            "current_action": trim_text(final_conclusion.get("current_action"), max_len=32) or trim_text(action, max_len=32),
            "watch_next": clean_str_list(final_conclusion.get("watch_next"), limit=8, max_len=220)
            or clean_str_list(operator_conclusion_human.get("watch_next"), limit=8, max_len=220),
            "thesis_invalidation": clean_str_list(final_conclusion.get("thesis_invalidation"), limit=8, max_len=220)
            or clean_str_list(operator_conclusion_human.get("thesis_invalidation"), limit=8, max_len=220),
        },
        "generation": {
            "status": trim_text(generation.get("status"), max_len=48) or "not_captured",
            "mode": trim_text(generation.get("mode"), max_len=48) or "not_captured",
            "model": trim_text(generation.get("model"), max_len=120) or "not_captured",
            "reason": trim_text(generation.get("reason"), max_len=320),
        },
    }


def build_trade_report_detail_view(
    meta: Dict[str, Any],
    payloads: Dict[str, Any],
    *,
    trim_text: Callable[..., str],
    clean_str_list: Callable[..., List[str]],
    normalize_symbol: Callable[..., str],
    story_type_label: Callable[[Any], str],
    story_type_badge_class: Callable[[Any], str],
    normalize_ai_report_diagnostics: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    report = payloads.get("report_data") if isinstance(payloads.get("report_data"), dict) else {}
    bundle = payloads.get("bundle_data") if isinstance(payloads.get("bundle_data"), dict) else {}
    lifecycle = payloads.get("lifecycle_data") if isinstance(payloads.get("lifecycle_data"), dict) else {}
    market_context_human = bundle.get("market_context_human") if isinstance(bundle.get("market_context_human"), dict) else {}
    scanner_reason_human = bundle.get("scanner_reason_human") if isinstance(bundle.get("scanner_reason_human"), dict) else {}
    filters_human = bundle.get("filters_human") if isinstance(bundle.get("filters_human"), dict) else {}
    monitor_reason_human = bundle.get("monitor_reason_human") if isinstance(bundle.get("monitor_reason_human"), dict) else {}
    guard_reason_human = bundle.get("guard_reason_human") if isinstance(bundle.get("guard_reason_human"), dict) else {}
    execution_outcome_human = bundle.get("execution_outcome_human") if isinstance(bundle.get("execution_outcome_human"), dict) else {}
    reporter_status_human = bundle.get("reporter_status_human") if isinstance(bundle.get("reporter_status_human"), dict) else {}
    operator_conclusion_human = bundle.get("operator_conclusion_human") if isinstance(bundle.get("operator_conclusion_human"), dict) else {}

    lifecycle_entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    lifecycle_holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    lifecycle_exit = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    lifecycle_summary_obj = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    lifecycle_reporter = lifecycle.get("reporter") if isinstance(lifecycle.get("reporter"), dict) else {}

    sections = normalize_trade_report_detail_sections(
        report,
        fallback_summaries={
            "executive_summary": lifecycle_summary_obj.get("lifecycle_summary_human") or operator_conclusion_human.get("summary") or execution_outcome_human.get("summary") or "",
            "market_context_at_entry": (lifecycle_entry.get("strategist_context") or {}).get("market_context_summary") if isinstance(lifecycle_entry.get("strategist_context"), dict) else market_context_human.get("summary") or "",
            "why_this_symbol_was_chosen": lifecycle_entry.get("reason_human") or scanner_reason_human.get("summary") or "",
            "scanner_filters": filters_human.get("summary") or "",
            "entry_decision": lifecycle_entry.get("reason_human") or scanner_reason_human.get("summary") or "",
            "holding_monitoring_story": monitor_reason_human.get("summary")
            or (
                f"Holding phase captured {len(list(lifecycle_holding.get('run_ids') or []))} runs."
                if list(lifecycle_holding.get("run_ids") or [])
                else ""
            ),
            "exit_decision": lifecycle_exit.get("reason_human")
            or (
                "Position is still open; no closing SELL execution has been captured yet."
                if str(lifecycle.get("status") or "").lower() == "open"
                else ""
            ),
            "execution_quality": execution_outcome_human.get("summary") or "",
            "guard_approval_result": guard_reason_human.get("summary") or "",
            "reporter_evaluation": reporter_status_human.get("summary") or "",
            "errors_weaknesses_improvement_points": "No explicit weaknesses were captured beyond standard warnings.",
        },
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    executive = sections.get("executive_summary") if isinstance(sections.get("executive_summary"), dict) else {}
    market_context = sections.get("market_context") if isinstance(sections.get("market_context"), dict) else {}
    why_symbol = sections.get("why_this_symbol") if isinstance(sections.get("why_this_symbol"), dict) else {}
    scanner_filters = sections.get("scanner_filters") if isinstance(sections.get("scanner_filters"), dict) else {}
    entry_decision = sections.get("entry_decision") if isinstance(sections.get("entry_decision"), dict) else {}
    holding_story = sections.get("holding_monitoring_story") if isinstance(sections.get("holding_monitoring_story"), dict) else {}
    exit_decision = sections.get("exit_decision") if isinstance(sections.get("exit_decision"), dict) else {}
    execution_quality = sections.get("execution_quality") if isinstance(sections.get("execution_quality"), dict) else {}
    guard_result = sections.get("guard_approval_result") if isinstance(sections.get("guard_approval_result"), dict) else {}
    reporter_eval = sections.get("reporter_evaluation") if isinstance(sections.get("reporter_evaluation"), dict) else {}
    weak_points = sections.get("errors_weaknesses_improvement_points") if isinstance(sections.get("errors_weaknesses_improvement_points"), dict) else {}
    timeline = [
        row
        for row in list(report.get("full_timeline") or report.get("timeline") or lifecycle.get("timeline") or bundle.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]
    report_exists = bool(payloads.get("report_exists"))
    action = trim_text(report.get("action"), max_len=32) or trim_text(meta.get("action"), max_len=32) or "WAIT"
    detail_meta = normalize_trade_report_detail_meta(
        report,
        operator_conclusion_human=operator_conclusion_human,
        action=action,
        trim_text=trim_text,
        clean_str_list=clean_str_list,
    )
    generation = detail_meta.get("generation") if isinstance(detail_meta.get("generation"), dict) else {}
    diagnostics = normalize_ai_report_diagnostics(
        report.get("ai_report_diagnostics")
        if isinstance(report.get("ai_report_diagnostics"), dict)
        else bundle.get("ai_report_diagnostics")
        if isinstance(bundle.get("ai_report_diagnostics"), dict)
        else lifecycle.get("ai_report_diagnostics")
        if isinstance(lifecycle.get("ai_report_diagnostics"), dict)
        else {},
        report_exists=report_exists,
        lifecycle_status=meta.get("lifecycle_status") or lifecycle.get("status"),
        story_type=meta.get("story_type") or report.get("story_type"),
        model_hint=generation.get("model"),
        generation=generation,
    )
    symbol = normalize_symbol(
        report.get("symbol") or meta.get("symbol") or "",
        allow_test_symbols=True,
    )
    reporter_status = trim_text(reporter_eval.get("status"), max_len=48) or trim_text(reporter_status_human.get("status"), max_len=48) or "-"
    reporter_grade = trim_text(reporter_eval.get("grade"), max_len=24) or trim_text(reporter_status_human.get("grade"), max_len=24) or "-"
    review_focus = sections.get("review_focus") if isinstance(sections.get("review_focus"), dict) else {}
    strategist_feedback_input = normalize_strategist_feedback_input(
        bundle.get("strategist_feedback_input")
        if isinstance(bundle.get("strategist_feedback_input"), dict)
        else lifecycle.get("strategist_feedback_input")
        if isinstance(lifecycle.get("strategist_feedback_input"), dict)
        else report.get("strategist_feedback_input")
        if isinstance(report.get("strategist_feedback_input"), dict)
        else {}
    )
    recent_feedback_items = (
        payloads.get("recent_feedback_items")
        if payloads.get("recent_feedback_items") is not None
        else meta.get("recent_feedback_items")
    )
    recent_feedback_window_size = (
        payloads.get("recent_feedback_window_size")
        if payloads.get("recent_feedback_window_size") not in (None, "")
        else meta.get("recent_feedback_window_size")
    )
    strategist_feedback_recent_window = build_trade_report_recent_feedback_view(
        recent_feedback_items,
        window_size=int(recent_feedback_window_size or 10),
    )

    return {
        "found": True,
        "trade_id": str(meta.get("trade_id") or meta.get("story_id") or ""),
        "story_id": str(meta.get("story_id") or ""),
        "run_id": str(meta.get("run_id") or ""),
        "run_link": f"/runs/{meta.get('run_id')}" if str(meta.get("run_id") or "").strip() else "",
        "symbol": symbol,
        "action": action,
        "status": str(meta.get("lifecycle_status") or report.get("status") or lifecycle.get("status") or ""),
        "lifecycle_summary": str(meta.get("lifecycle_summary") or lifecycle_summary_obj.get("lifecycle_summary_human") or ""),
        "story_type": str(meta.get("story_type") or report.get("story_type") or ""),
        "story_type_label": str(meta.get("story_type_label") or story_type_label(report.get("story_type"))),
        "story_type_badge_class": str(meta.get("story_type_badge_class") or story_type_badge_class(report.get("story_type"))),
        "execution_mode_label": str(meta.get("execution_mode_label") or report.get("execution_mode_label") or "not captured"),
        "report_available": bool(diagnostics.get("report_status") == "available" and report_exists),
        "report_summary": str(meta.get("report_summary") or executive.get("summary") or ""),
        "reporter_status_human": str(meta.get("reporter_status_human") or reporter_eval.get("summary") or ""),
        "ai_report_diagnostics": diagnostics,
        "executive_summary": executive,
        "market_context": market_context,
        "why_this_symbol": why_symbol,
        "entry_decision": entry_decision,
        "holding_monitoring_story": holding_story,
        "exit_decision": exit_decision,
        "scanner_logic_and_filters": scanner_filters,
        "monitor_trigger_reasoning": holding_story,
        "guard_approval_result": guard_result,
        "execution_result": execution_quality,
        "execution_quality": execution_quality,
        "review_focus": review_focus,
        "strategist_feedback_input": strategist_feedback_input,
        "strategist_feedback_recent_window": strategist_feedback_recent_window,
        "reporter_evaluation": {
            **reporter_eval,
            "status": reporter_status,
            "grade": reporter_grade or trim_text(lifecycle_reporter.get("grade"), max_len=24) or "-",
        },
        "errors_weaknesses_improvement_points": weak_points,
        "timeline": timeline,
        "full_timeline": timeline,
        "trade_lifecycle": lifecycle if isinstance(lifecycle, dict) else {},
        "final_operator_conclusion": detail_meta.get("final_operator_conclusion") if isinstance(detail_meta.get("final_operator_conclusion"), dict) else {},
        "generation": generation,
        "paths": {
            "trade_report_json": str(meta.get("trade_report_json_path") or ""),
            "trade_report_md": str(meta.get("trade_report_md_path") or ""),
            "trade_story_input": str(meta.get("trade_story_input_path") or ""),
            "ai_trade_report_json": str(meta.get("ai_trade_report_json_path") or meta.get("trade_report_json_path") or ""),
            "ai_trade_report_md": str(meta.get("ai_trade_report_md_path") or meta.get("trade_report_md_path") or ""),
            "ai_trade_report_input": str(meta.get("ai_trade_report_input_path") or meta.get("trade_story_input_path") or ""),
            "trade_lifecycle": str(meta.get("trade_lifecycle_json_path") or ""),
            "aggregated_execution_bundle": str(meta.get("aggregated_bundle_path") or ""),
            "strategist_llm_response": str(meta.get("strategist_llm_response_path") or ""),
            "ai_trade_report_llm_response": str(meta.get("ai_trade_report_llm_response_path") or ""),
            "brief_llm_response": str(meta.get("brief_llm_response_path") or ""),
        },
        "raw_report": report if isinstance(report, dict) else {},
    }


def collect_strategist_feedback_inputs(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = (
            item.get("strategist_feedback_input")
            if isinstance(item.get("strategist_feedback_input"), dict)
            else ((item.get("bundle_data") or {}).get("strategist_feedback_input"))
            if isinstance(item.get("bundle_data"), dict) and isinstance((item.get("bundle_data") or {}).get("strategist_feedback_input"), dict)
            else ((item.get("lifecycle_data") or {}).get("strategist_feedback_input"))
            if isinstance(item.get("lifecycle_data"), dict) and isinstance((item.get("lifecycle_data") or {}).get("strategist_feedback_input"), dict)
            else ((item.get("story_input_data") or {}).get("strategist_feedback_input"))
            if isinstance(item.get("story_input_data"), dict) and isinstance((item.get("story_input_data") or {}).get("strategist_feedback_input"), dict)
            else {}
        )
        if not isinstance(source, dict) or not source:
            continue
        normalized = normalize_strategist_feedback_input(source)
        normalized["trade_id"] = str(item.get("trade_id") or normalized.get("trade_id") or "")
        normalized["story_id"] = str(item.get("story_id") or normalized.get("story_id") or "")
        normalized["run_id"] = str(item.get("run_id") or normalized.get("run_id") or "")
        normalized["symbol"] = str(item.get("symbol") or normalized.get("selected_symbol") or "")
        normalized["trade_status"] = str(
            item.get("trade_status")
            or item.get("status")
            or normalized.get("trade_status")
            or ""
        )
        normalized["final_action"] = str(
            item.get("final_action")
            or item.get("action")
            or normalized.get("final_action")
            or ""
        )
        result_pct = item.get("result_pct")
        if result_pct in (None, "") and isinstance(item.get("summary"), dict):
            result_pct = (item.get("summary") or {}).get("result_pct")
        normalized["result_pct"] = result_pct
        out.append(normalized)
    return out


def build_recent_trade_feedback_summary_input(
    items: Any,
    *,
    window_size: int = 10,
) -> Dict[str, Any]:
    return build_recent_strategist_feedback_window(
        collect_strategist_feedback_inputs(items),
        window_size=window_size,
    )


def build_trade_report_recent_feedback_view(
    items: Any,
    *,
    window_size: int = 10,
) -> Dict[str, Any]:
    return build_recent_trade_feedback_summary_input(items, window_size=window_size)


def build_trade_report_recent_feedback_pack(
    items: Any,
    *,
    window_size: int = 10,
) -> Dict[str, Any]:
    window = build_trade_report_recent_feedback_view(items, window_size=window_size)
    return {
        "schema_version": "strategist_feedback_recent_window_pack.v1",
        "payload_type": "recent_strategist_feedback_window",
        "available": bool(int(window.get("trades_considered") or 0) > 0),
        "window": window,
    }


def load_trade_report_recent_feedback_pack(
    meta: Dict[str, Any] | None = None,
    payloads: Dict[str, Any] | None = None,
    *,
    default_window_size: int = 10,
) -> Dict[str, Any]:
    meta_obj = meta if isinstance(meta, dict) else {}
    payload_obj = payloads if isinstance(payloads, dict) else {}
    items = (
        payload_obj.get("recent_feedback_items")
        if payload_obj.get("recent_feedback_items") is not None
        else meta_obj.get("recent_feedback_items")
    )
    window_size = (
        payload_obj.get("recent_feedback_window_size")
        if payload_obj.get("recent_feedback_window_size") not in (None, "")
        else meta_obj.get("recent_feedback_window_size")
    )
    return build_trade_report_recent_feedback_pack(
        items,
        window_size=int(window_size or default_window_size),
    )


def load_time_bucketed_trade_report_recent_feedback_pack(
    meta: Dict[str, Any] | None = None,
    payloads: Dict[str, Any] | None = None,
    *,
    default_window_size: int = 10,
) -> Dict[str, Any]:
    """Future-facing time-bucketed contract candidate for non-UI consumers.

    This helper does not replace the existing recent-window contract.
    It wraps the existing recent-window pack in a parallel bucketed surface so
    future runtime or reporting consumers can depend on a common bucket shape
    without changing current behavior.

    Current buckets intentionally stay minimal:
    - overall_recent: existing recent-window pack reuse path
    - daily_recent: optional shell fed by meta/payload inputs if available
    - symbol_recent: optional shell fed by meta/payload inputs if available
    """

    meta_obj = meta if isinstance(meta, dict) else {}
    payload_obj = payloads if isinstance(payloads, dict) else {}

    def _resolve_items(base_key: str) -> Any:
        bucket_items_key = f"{base_key}_feedback_items"
        if payload_obj.get(bucket_items_key) is not None:
            return payload_obj.get(bucket_items_key)
        if meta_obj.get(bucket_items_key) is not None:
            return meta_obj.get(bucket_items_key)
        if base_key == "recent":
            if payload_obj.get("recent_feedback_items") is not None:
                return payload_obj.get("recent_feedback_items")
            return meta_obj.get("recent_feedback_items")
        return None

    def _resolve_window_size(base_key: str) -> int:
        bucket_window_key = f"{base_key}_feedback_window_size"
        if payload_obj.get(bucket_window_key) not in (None, ""):
            return int(payload_obj.get(bucket_window_key) or default_window_size)
        if meta_obj.get(bucket_window_key) not in (None, ""):
            return int(meta_obj.get(bucket_window_key) or default_window_size)
        if base_key == "recent":
            if payload_obj.get("recent_feedback_window_size") not in (None, ""):
                return int(payload_obj.get("recent_feedback_window_size") or default_window_size)
            if meta_obj.get("recent_feedback_window_size") not in (None, ""):
                return int(meta_obj.get("recent_feedback_window_size") or default_window_size)
        return int(default_window_size)

    def _bucket(base_key: str) -> Dict[str, Any]:
        packed = build_trade_report_recent_feedback_pack(
            _resolve_items(base_key),
            window_size=_resolve_window_size(base_key),
        )
        return {
            "available": bool(packed.get("available")),
            "window": dict(packed.get("window") or {}),
        }

    buckets = {
        "overall_recent": _bucket("recent"),
        "daily_recent": _bucket("daily_recent"),
        "symbol_recent": _bucket("symbol_recent"),
    }
    return {
        "schema_version": "strategist_feedback_time_bucket_pack.v1",
        "payload_type": "time_bucketed_recent_strategist_feedback",
        "available": any(bool((bucket or {}).get("available")) for bucket in buckets.values()),
        "buckets": buckets,
    }


def load_reporter_snippet_for_run(
    reports_root: Path,
    run_id: str,
    run_day: str,
    *,
    read_json: Callable[[Path], Dict[str, Any]],
) -> Dict[str, Any]:
    path = reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{run_day}.json"
    report = read_json(path)
    if not report:
        return {
            "report_path": str(path),
            "found": False,
            "ai_summary": "",
            "ai_run_grade": "",
            "reason": "same_day_report_missing",
        }
    chains = ((report.get("decision_trace_chain_summary") or {}).get("chains") or []) if isinstance(report.get("decision_trace_chain_summary"), dict) else []
    chain = next((c for c in chains if isinstance(c, dict) and str(c.get("run_id") or "").strip() == str(run_id or "").strip()), {})
    if not chain:
        return {
            "report_path": str(path),
            "found": False,
            "ai_summary": "",
            "ai_run_grade": str(report.get("ai_run_grade") or ""),
            "reason": "run_not_linked_in_same_day_report",
        }
    return {
        "report_path": str(path),
        "found": True,
        "ai_summary": str(report.get("ai_summary") or ""),
        "ai_run_grade": str(report.get("ai_run_grade") or ""),
        "chain": chain,
    }


def build_linked_trade_report_card(
    trade_report_meta: Dict[str, Any],
    report_payloads: Dict[str, Any],
    *,
    primary_symbol: str,
    execution_action: str,
    normalize_ai_report_diagnostics: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    story_input_data = dict(report_payloads.get("story_input_data") or {})
    lifecycle_data = dict(report_payloads.get("lifecycle_data") or {})
    report_data = dict(report_payloads.get("report_data") or {})
    payload_sources = dict(report_payloads.get("payload_sources") or {})
    payload_paths = dict(report_payloads.get("paths") or {})
    ai_diag = (
        trade_report_meta.get("ai_report_diagnostics")
        if isinstance(trade_report_meta.get("ai_report_diagnostics"), dict)
        else {}
    )
    if not ai_diag:
        ai_diag = normalize_ai_report_diagnostics(
            {},
            report_exists=bool(trade_report_meta.get("trade_report_json_path") or trade_report_meta.get("trade_report_md_path")),
            lifecycle_status=trade_report_meta.get("lifecycle_status"),
            story_type=trade_report_meta.get("story_type"),
            model_hint=trade_report_meta.get("report_generation_model"),
        )
    return {
        "report_available": bool(trade_report_meta.get("report_available")),
        "trade_id": str(trade_report_meta.get("trade_id") or ""),
        "story_id": str(trade_report_meta.get("story_id") or ""),
        "story_type": str(trade_report_meta.get("story_type") or ""),
        "story_type_label": str(trade_report_meta.get("story_type_label") or ""),
        "story_type_badge_class": str(trade_report_meta.get("story_type_badge_class") or "status-badge"),
        "lifecycle_status": str(trade_report_meta.get("lifecycle_status") or ""),
        "lifecycle_summary": str(trade_report_meta.get("lifecycle_summary") or ""),
        "execution_mode_label": str(trade_report_meta.get("execution_mode_label") or "-"),
        "report_status": str(trade_report_meta.get("report_status") or ai_diag.get("report_status") or "skipped"),
        "report_status_label": str(trade_report_meta.get("report_status_label") or ai_diag.get("report_status_label") or ""),
        "report_status_badge_class": str(trade_report_meta.get("report_status_badge_class") or ai_diag.get("report_status_badge_class") or "status-badge"),
        "report_reason_code": str(trade_report_meta.get("report_reason_code") or ai_diag.get("report_reason_code") or ""),
        "report_reason_human": str(trade_report_meta.get("report_reason_human") or ai_diag.get("report_reason_human") or ""),
        "report_next_expected_step": str(trade_report_meta.get("report_next_expected_step") or ai_diag.get("next_expected_step") or ""),
        "report_generation_model": str(trade_report_meta.get("report_generation_model") or ai_diag.get("llm_model_used") or ""),
        "report_generation_provider": str(trade_report_meta.get("report_generation_provider") or ai_diag.get("llm_provider") or "OpenRouter"),
        "report_summary": str(trade_report_meta.get("report_summary") or ""),
        "reporter_status_human": str(trade_report_meta.get("reporter_status_human") or ""),
        "report_link": str(trade_report_meta.get("report_link") or ""),
        "operator_brief_available": bool(trade_report_meta.get("operator_brief_available")),
        "operator_brief_link": str(trade_report_meta.get("operator_brief_link") or ""),
        "operator_brief_json_path": str(trade_report_meta.get("operator_brief_json_path") or ""),
        "operator_brief_md_path": str(trade_report_meta.get("operator_brief_md_path") or ""),
        "trade_report_json_path": str(trade_report_meta.get("trade_report_json_path") or ""),
        "trade_report_md_path": str(trade_report_meta.get("trade_report_md_path") or ""),
        "trade_story_input_path": str(trade_report_meta.get("trade_story_input_path") or ""),
        "ai_trade_report_json_path": str(trade_report_meta.get("ai_trade_report_json_path") or trade_report_meta.get("trade_report_json_path") or ""),
        "ai_trade_report_md_path": str(trade_report_meta.get("ai_trade_report_md_path") or trade_report_meta.get("trade_report_md_path") or ""),
        "ai_trade_report_input_path": str(trade_report_meta.get("ai_trade_report_input_path") or trade_report_meta.get("trade_story_input_path") or ""),
        "trade_lifecycle_json_path": str(trade_report_meta.get("trade_lifecycle_json_path") or ""),
        "aggregated_bundle_path": str(trade_report_meta.get("aggregated_bundle_path") or ""),
        "trade_root_path": str(trade_report_meta.get("trade_root_path") or ""),
        "strategist_llm_response_path": str(trade_report_meta.get("strategist_llm_response_path") or ""),
        "ai_trade_report_llm_response_path": str(trade_report_meta.get("ai_trade_report_llm_response_path") or ""),
        "brief_llm_response_path": str(trade_report_meta.get("brief_llm_response_path") or ""),
        "trade_provenance_json_path": str(trade_report_meta.get("trade_provenance_json_path") or ""),
        "trade_health_json_path": str(trade_report_meta.get("trade_health_json_path") or ""),
        "trade_artifact_links_json_path": str(trade_report_meta.get("trade_artifact_links_json_path") or ""),
        "section_provenance": dict(trade_report_meta.get("section_provenance") or {}) if isinstance(trade_report_meta.get("section_provenance"), dict) else {},
        "symbol": str(trade_report_meta.get("symbol") or primary_symbol or ""),
        "action": str(trade_report_meta.get("action") or execution_action or ""),
        "missing_reason": str(trade_report_meta.get("report_reason_human") or ai_diag.get("report_reason_human") or ""),
        "ai_report_diagnostics": ai_diag,
        "story_input_data": story_input_data if isinstance(story_input_data, dict) else {},
        "lifecycle_data": lifecycle_data if isinstance(lifecycle_data, dict) else {},
        "report_data": report_data if isinstance(report_data, dict) else {},
        "report_payload_sources": payload_sources,
        "report_payload_paths": payload_paths,
    }


def build_unlinked_trade_report_card(
    *,
    execution_action: str,
    monitor_reason_text: str,
    symbol: str,
    normalize_ai_report_diagnostics: Callable[..., Dict[str, Any]],
    report_reason_human: Callable[[str], str],
    report_next_step: Callable[[str], str],
) -> Dict[str, Any]:
    execution_action_upper = str(execution_action or "").upper()
    monitor_reason_lower = str(monitor_reason_text or "").strip().lower()
    if execution_action_upper in {"BUY", "SELL"}:
        reason_code = "missing_report_linkage"
        status = "failed"
    elif "hold" in monitor_reason_lower:
        reason_code = "hold_only_run"
        status = "skipped"
    else:
        reason_code = "decision_only_run"
        status = "skipped"
    ai_diag = normalize_ai_report_diagnostics(
        {
            "report_status": status,
            "report_reason_code": reason_code,
            "report_reason_human": report_reason_human(reason_code),
            "next_expected_step": report_next_step(reason_code),
            "generation_attempted": False,
            "story_input_available": False,
            "report_output_available": False,
        },
        report_exists=False,
        lifecycle_status="",
        story_type="decision_only" if status == "skipped" else "",
        model_hint="",
    )
    return {
        "report_available": False,
        "trade_id": "",
        "story_id": "",
        "story_type": "",
        "story_type_label": "No linked trade report",
        "story_type_badge_class": "status-badge",
        "lifecycle_status": "",
        "lifecycle_summary": "",
        "execution_mode_label": "-",
        "report_status": str(ai_diag.get("report_status") or "skipped"),
        "report_status_label": str(ai_diag.get("report_status_label") or ""),
        "report_status_badge_class": str(ai_diag.get("report_status_badge_class") or "status-badge"),
        "report_reason_code": str(ai_diag.get("report_reason_code") or ""),
        "report_reason_human": str(ai_diag.get("report_reason_human") or ""),
        "report_next_expected_step": str(ai_diag.get("next_expected_step") or ""),
        "report_generation_model": str(ai_diag.get("llm_model_used") or ""),
        "report_generation_provider": str(ai_diag.get("llm_provider") or "OpenRouter"),
        "report_summary": "",
        "reporter_status_human": "",
        "report_link": "",
        "operator_brief_available": False,
        "operator_brief_link": "",
        "operator_brief_json_path": "",
        "operator_brief_md_path": "",
        "trade_report_json_path": "",
        "trade_report_md_path": "",
        "trade_story_input_path": "",
        "ai_trade_report_json_path": "",
        "ai_trade_report_md_path": "",
        "ai_trade_report_input_path": "",
        "trade_lifecycle_json_path": "",
        "aggregated_bundle_path": "",
        "trade_root_path": "",
        "strategist_llm_response_path": "",
        "ai_trade_report_llm_response_path": "",
        "brief_llm_response_path": "",
        "trade_provenance_json_path": "",
        "trade_health_json_path": "",
        "trade_artifact_links_json_path": "",
        "section_provenance": {},
        "symbol": str(symbol or ""),
        "action": str(execution_action or ""),
        "missing_reason": str(ai_diag.get("report_reason_human") or "No linked trade report for this run."),
        "ai_report_diagnostics": ai_diag,
        "story_input_data": {},
        "lifecycle_data": {},
        "report_data": {},
    }


def load_trade_report_detail_payloads(
    trade_report_meta: Dict[str, Any],
    *,
    read_json: Callable[[Path], Dict[str, Any]],
) -> Dict[str, Any]:
    report_path = Path(str(trade_report_meta.get("trade_report_json_path") or ""))
    bundle_path = Path(str(trade_report_meta.get("aggregated_bundle_path") or ""))
    lifecycle_path = Path(str(trade_report_meta.get("trade_lifecycle_json_path") or ""))
    report_md_path = Path(str(trade_report_meta.get("trade_report_md_path") or ""))

    report_data = read_json(report_path) if report_path.exists() else {}
    bundle_data = read_json(bundle_path) if bundle_path.exists() else {}
    lifecycle_data = read_json(lifecycle_path) if lifecycle_path.exists() else {}

    return {
        "report_data": report_data if isinstance(report_data, dict) else {},
        "bundle_data": bundle_data if isinstance(bundle_data, dict) else {},
        "lifecycle_data": lifecycle_data if isinstance(lifecycle_data, dict) else {},
        "report_exists": bool(report_path.exists() or report_md_path.exists()),
        "paths": {
            "report_json_path": str(report_path) if report_path.exists() else "",
            "report_md_path": str(report_md_path) if report_md_path.exists() else "",
            "bundle_path": str(bundle_path) if bundle_path.exists() else "",
            "lifecycle_path": str(lifecycle_path) if lifecycle_path.exists() else "",
        },
    }


def load_operator_brief_detail_payloads(
    trade_report_meta: Dict[str, Any],
    *,
    read_json: Callable[[Path], Dict[str, Any]],
    allow_saved_brief: bool,
) -> Dict[str, Any]:
    json_path = Path(str(trade_report_meta.get("operator_brief_json_path") or ""))
    md_path = Path(str(trade_report_meta.get("operator_brief_md_path") or ""))
    brief_data: Dict[str, Any] = {}
    if allow_saved_brief and json_path.exists():
        brief_data = read_json(json_path)
        if not isinstance(brief_data, dict):
            brief_data = {}
    return {
        "brief_data": brief_data,
        "paths": {
            "operator_brief_json": str(json_path) if json_path.exists() else "",
            "operator_brief_md": str(md_path) if md_path.exists() else "",
        },
    }


def normalize_operator_brief_detail_payload(
    brief: Dict[str, Any],
    *,
    clean_str_list: Callable[..., List[str]],
) -> Dict[str, Any]:
    sections = brief.get("sections") if isinstance(brief.get("sections"), dict) else {}
    executive = sections.get("executive_decision") if isinstance(sections.get("executive_decision"), dict) else {}
    ai_trade = sections.get("ai_trade_report") if isinstance(sections.get("ai_trade_report"), dict) else {}
    conclusion = sections.get("operator_conclusion") if isinstance(sections.get("operator_conclusion"), dict) else {}
    return {
        "headline": str(brief.get("headline") or ""),
        "status": str(brief.get("status") or ""),
        "model": str(brief.get("model") or ""),
        "saved_at": str(brief.get("saved_at") or ""),
        "sections": sections,
        "operator_takeaways": clean_str_list(brief.get("operator_takeaways"), limit=8, max_len=220),
        "executive": executive,
        "ai_trade": ai_trade,
        "conclusion": conclusion,
        "watch_next": clean_str_list(conclusion.get("watch_next"), limit=8, max_len=220),
        "thesis_invalidation": clean_str_list(conclusion.get("thesis_invalidation"), limit=8, max_len=220),
    }


def build_operator_brief_detail_view(
    meta: Dict[str, Any],
    brief: Dict[str, Any],
    *,
    json_path: str,
    md_path: str,
    normalize_symbol: Callable[..., str],
    clean_str_list: Callable[..., List[str]],
) -> Dict[str, Any]:
    brief_view = normalize_operator_brief_detail_payload(
        brief,
        clean_str_list=clean_str_list,
    )
    sections = brief_view.get("sections") if isinstance(brief_view.get("sections"), dict) else {}
    executive = brief_view.get("executive") if isinstance(brief_view.get("executive"), dict) else {}
    ai_trade = brief_view.get("ai_trade") if isinstance(brief_view.get("ai_trade"), dict) else {}
    return {
        "found": True,
        "trade_id": str(meta.get("trade_id") or meta.get("story_id") or ""),
        "story_id": str(meta.get("story_id") or ""),
        "run_id": str(meta.get("run_id") or ""),
        "run_link": f"/runs/{meta.get('run_id')}" if str(meta.get("run_id") or "").strip() else "",
        "report_link": str(meta.get("report_link") or ""),
        "headline": str(brief_view.get("headline") or ""),
        "status": str(brief_view.get("status") or ""),
        "model": str(brief_view.get("model") or ""),
        "saved_at": str(brief_view.get("saved_at") or ""),
        "trade_summary": str(meta.get("report_summary") or ""),
        "lifecycle_status": str(meta.get("lifecycle_status") or ""),
        "story_type_label": str(meta.get("story_type_label") or ""),
        "story_type_badge_class": str(meta.get("story_type_badge_class") or "status-badge"),
        "execution_mode_label": str(meta.get("execution_mode_label") or "-"),
        "operator_takeaways": list(brief_view.get("operator_takeaways") or []),
        "sections": sections,
        "executive_action": str(executive.get("final_action") or executive.get("action") or meta.get("action") or "-"),
        "executive_symbol": normalize_symbol(executive.get("symbol") or meta.get("symbol") or "", allow_test_symbols=True),
        "ai_trade_status_label": str(ai_trade.get("status_label") or meta.get("report_status_label") or "-"),
        "ai_trade_status_badge_class": str(ai_trade.get("status_badge_class") or meta.get("report_status_badge_class") or "status-badge"),
        "watch_next": list(brief_view.get("watch_next") or []),
        "thesis_invalidation": list(brief_view.get("thesis_invalidation") or []),
        "paths": {
            "operator_brief_json": str(json_path or ""),
            "operator_brief_md": str(md_path or ""),
        },
        "raw_brief": brief,
    }


def extract_labeled_bullet(bullets: List[str], labels: List[str]) -> str:
    normalized_labels = [str(label or "").strip().lower() for label in labels if str(label or "").strip()]
    for bullet in bullets:
        text = str(bullet or "").strip()
        lower = text.lower()
        for label in normalized_labels:
            prefix = f"{label}:"
            if lower.startswith(prefix):
                return text.split(":", 1)[1].strip()
    return ""


def extract_labeled_int(bullets: List[str], labels: List[str]) -> Optional[int]:
    value = extract_labeled_bullet(bullets, labels)
    if not value:
        return None
    match = re.search(r"-?\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def parse_canonical_filter_bullets(bullets: List[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for bullet in bullets:
        text = str(bullet or "").strip()
        if not text or ":" not in text:
            continue
        name_raw, rest = text.split(":", 1)
        name = name_raw.strip().title()
        status = "INFO"
        note = rest.strip()
        match = re.match(r"\s*(PASS|FAIL|PARTIAL|SKIPPED|NOT_AVAILABLE)\s*[-:]?\s*(.*)$", note, flags=re.IGNORECASE)
        if match:
            status = match.group(1).upper()
            note = match.group(2).strip() or note.strip()
        rows.append({"name": name, "status": status, "note": note})
    return rows


def normalize_canonical_monitor_snapshot(
    snapshot: Dict[str, Any],
    story_monitor: Dict[str, Any] | None = None,
    *,
    format_duration: Callable[[Any], str],
    format_percent: Callable[[Any, int], str],
    format_float: Callable[[Any, int], str],
    friendly_exit_reason: Callable[[Any], str],
) -> Dict[str, Any]:
    if not isinstance(snapshot, dict):
        snapshot = {}
    if not isinstance(story_monitor, dict):
        story_monitor = {}

    posture = str(snapshot.get("posture") or story_monitor.get("posture") or "").strip()
    trigger_type = str(snapshot.get("trigger_type") or story_monitor.get("trigger_type") or "").strip()
    raw_effective_reason = str(
        snapshot.get("effective_stop_reason")
        or story_monitor.get("effective_stop_reason")
        or trigger_type
        or ""
    ).strip()
    effective_reason = friendly_exit_reason(raw_effective_reason) if raw_effective_reason else ""

    stop_loss_pct = snapshot.get("stop_loss_pct")
    if stop_loss_pct in (None, ""):
        stop_loss_pct = story_monitor.get("stop_loss_pct")
    effective_stop_loss_pct = snapshot.get("effective_stop_loss_pct")
    if effective_stop_loss_pct in (None, ""):
        effective_stop_loss_pct = story_monitor.get("effective_stop_loss_pct")
    take_profit_pct = snapshot.get("take_profit_pct")
    if take_profit_pct in (None, ""):
        take_profit_pct = story_monitor.get("take_profit_pct")
    position_age_seconds = snapshot.get("position_age_seconds")
    if position_age_seconds in (None, ""):
        position_age_seconds = story_monitor.get("position_age_seconds")

    active_exit_axis = str(snapshot.get("active_exit_axis") or "").strip()
    if not active_exit_axis:
        if trigger_type:
            active_exit_axis = friendly_exit_reason(trigger_type)
        elif raw_effective_reason:
            active_exit_axis = friendly_exit_reason(raw_effective_reason)
        elif posture.upper() == "HOLD":
            active_exit_axis = "No trigger yet"
    else:
        active_exit_axis = friendly_exit_reason(active_exit_axis)

    def _fmt_optional_price(value: Any) -> str:
        if value in (None, ""):
            return ""
        return format_float(value, 2)

    def _fmt_optional_pct(value: Any) -> str:
        if value in (None, ""):
            return ""
        return format_percent(value, 2)

    watch_axes = [str(x or "") for x in list(snapshot.get("watch_axes") or []) if str(x or "").strip()]
    hold_reasons = [str(x or "") for x in list(snapshot.get("hold_reasons") or []) if str(x or "").strip()]
    exit_triggers = [str(x or "") for x in list(snapshot.get("exit_triggers") or []) if str(x or "").strip()]
    if not hold_reasons:
        hold_reasons = [str(x or "") for x in list(story_monitor.get("bullets") or []) if str(x or "").strip()][:4]

    return {
        "posture": posture,
        "holding_time": (
            format_duration(position_age_seconds)
            if position_age_seconds not in (None, "")
            else str(snapshot.get("holding_time") or "").strip()
        ),
        "stop_loss": (
            format_percent(stop_loss_pct, 2)
            if stop_loss_pct not in (None, "")
            else str(snapshot.get("stop_loss") or "").strip()
        ),
        "effective_stop": (
            format_percent(effective_stop_loss_pct, 2)
            if effective_stop_loss_pct not in (None, "")
            else str(snapshot.get("effective_stop") or "").strip()
        ),
        "effective_stop_reason": effective_reason,
        "take_profit": (
            format_percent(take_profit_pct, 2)
            if take_profit_pct not in (None, "")
            else str(snapshot.get("take_profit") or "").strip()
        ),
        "current_price": _fmt_optional_price(snapshot.get("current_price")),
        "average_price": _fmt_optional_price(snapshot.get("average_price")),
        "peak_price": _fmt_optional_price(snapshot.get("peak_price")),
        "current_drawdown": _fmt_optional_pct(snapshot.get("current_drawdown")),
        "peak_drawdown": _fmt_optional_pct(snapshot.get("peak_drawdown")),
        "vwap_distance": _fmt_optional_pct(snapshot.get("vwap_distance")),
        "price_source": str(snapshot.get("price_source") or story_monitor.get("price_source") or "").strip(),
        "feature_source": str(snapshot.get("feature_source") or story_monitor.get("feature_source") or "").strip(),
        "price_source_policy": str(snapshot.get("price_source_policy") or story_monitor.get("price_source_policy") or "").strip(),
        "active_exit_axis": active_exit_axis,
        "watch_axes": watch_axes,
        "hold_reasons": hold_reasons[:6],
        "exit_triggers": exit_triggers[:6],
    }


def brief_headline_text(row: Any, *, trim_text: Callable[..., str]) -> str:
    item = row if isinstance(row, dict) else {}
    for key in ("title", "headline", "summary", "description", "text", "news_title"):
        text = trim_text(item.get(key), max_len=180)
        if text:
            return text
    return ""


def brief_norm_symbol_text(value: Any, *, normalize_symbol: Callable[..., str]) -> str:
    return normalize_symbol(value, allow_test_symbols=True).strip().upper()


def brief_headline_matches_symbol(
    row: Any,
    symbol: str,
    *,
    normalize_symbol: Callable[..., str],
) -> bool:
    item = row if isinstance(row, dict) else {}
    target = brief_norm_symbol_text(symbol, normalize_symbol=normalize_symbol)
    if not target:
        return False
    for candidate in (
        item.get("symbol"),
        item.get("code"),
        item.get("ticker"),
        item.get("query_target"),
        item.get("query"),
        item.get("news_query_target"),
    ):
        if brief_norm_symbol_text(candidate, normalize_symbol=normalize_symbol) == target:
            return True
    for key in ("symbols", "tickers", "related_symbols"):
        values = item.get(key)
        if not isinstance(values, list):
            continue
        for candidate in values:
            if brief_norm_symbol_text(candidate, normalize_symbol=normalize_symbol) == target:
                return True
    joined = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("headline") or ""),
            str(item.get("summary") or ""),
            str(item.get("description") or ""),
            str(item.get("query_target") or ""),
        ]
    ).upper()
    return bool(target and target in joined)


def brief_collect_top_headlines(
    rows: Any,
    *,
    limit: int = 3,
    symbol: str = "",
    trim_text: Callable[..., str],
    normalize_symbol: Callable[..., str],
) -> List[str]:
    if not isinstance(rows, list):
        return []
    filtered: List[str] = []
    fallback: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = brief_headline_text(row, trim_text=trim_text)
        if not text:
            continue
        if text not in fallback:
            fallback.append(text)
        if symbol and brief_headline_matches_symbol(row, symbol, normalize_symbol=normalize_symbol) and text not in filtered:
            filtered.append(text)
    picked = filtered or fallback
    return picked[: max(1, int(limit))]


def brief_top_numeric_drivers(values: Any, *, limit: int = 4) -> Dict[str, float]:
    if not isinstance(values, dict):
        return {}
    scored: List[tuple[float, str, float]] = []
    for key, value in values.items():
        try:
            numeric = float(value)
        except Exception:
            continue
        if numeric == 0.0:
            continue
        scored.append((abs(numeric), str(key), numeric))
    scored.sort(key=lambda row: (-row[0], row[1]))
    out: Dict[str, float] = {}
    for _, key, numeric in scored[: max(1, int(limit))]:
        out[key] = numeric
    return out


def load_trade_report_payloads(
    trade_report_meta: Dict[str, Any],
    *,
    read_json: Callable[[Path], Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    trade_root_path = Path(str(trade_report_meta.get("trade_root_path") or ""))
    normalized_story_input = trade_root_path / "ai_trade_report_input.json"
    normalized_lifecycle = trade_root_path / "lifecycle_bundle.json"
    normalized_report_json = trade_root_path / "reports" / "ai_trade_report.json"
    legacy_story_input = trade_root_path / "ai_trade_report" / "ai_trade_report_input.json"
    legacy_lifecycle = trade_root_path / "lifecycle" / "trade_lifecycle.json"
    legacy_report_json = trade_root_path / "ai_trade_report" / "ai_trade_report.json"

    story_input_meta_path = Path(str(trade_report_meta.get("trade_story_input_path") or ""))
    lifecycle_meta_path = Path(str(trade_report_meta.get("trade_lifecycle_json_path") or ""))
    report_meta_path = Path(str(trade_report_meta.get("trade_report_json_path") or ""))
    aggregated_bundle_path = Path(str(trade_report_meta.get("aggregated_bundle_path") or ""))

    story_input_path = _pick_first_existing(normalized_story_input, legacy_story_input, story_input_meta_path)
    lifecycle_path = _pick_first_existing(normalized_lifecycle, legacy_lifecycle, lifecycle_meta_path)
    report_json_path = _pick_first_existing(normalized_report_json, legacy_report_json, report_meta_path)

    story_input_data = read_json(story_input_path) if story_input_path.exists() else {}
    lifecycle_data = read_json(lifecycle_path) if lifecycle_path.exists() else {}
    report_data = read_json(report_json_path) if report_json_path.exists() else {}

    bundle_data = read_json(aggregated_bundle_path) if aggregated_bundle_path.exists() else {}
    if not bundle_data and normalized_lifecycle.exists():
        bundle_data = read_json(normalized_lifecycle)
    if not bundle_data and legacy_lifecycle.exists():
        bundle_data = read_json(legacy_lifecycle)
    canonical_fallback = (
        bundle_data.get("canonical_agent_artifacts")
        if isinstance(bundle_data.get("canonical_agent_artifacts"), dict)
        else {}
    )

    story_source = (
        "normalized_trade_artifact"
        if story_input_path == normalized_story_input and story_input_path.exists()
        else ("direct_artifact" if story_input_path.exists() else "missing")
    )
    lifecycle_source = (
        "normalized_trade_artifact"
        if lifecycle_path == normalized_lifecycle and lifecycle_path.exists()
        else ("direct_artifact" if lifecycle_path.exists() else "missing")
    )
    report_source = (
        "normalized_trade_artifact"
        if report_json_path == normalized_report_json and report_json_path.exists()
        else ("direct_artifact" if report_json_path.exists() else "missing")
    )

    return {
        "story_input_data": story_input_data if isinstance(story_input_data, dict) else {},
        "lifecycle_data": lifecycle_data if isinstance(lifecycle_data, dict) else {},
        "report_data": report_data if isinstance(report_data, dict) else {},
        "payload_sources": {
            "story_input": story_source,
            "lifecycle": lifecycle_source,
            "report": report_source,
            "canonical_fallback": "canonical_artifact" if canonical_fallback else "missing",
        },
        "paths": {
            "story_input_path": str(story_input_path) if story_input_path.exists() else "",
            "lifecycle_path": str(lifecycle_path) if lifecycle_path.exists() else "",
            "report_path": str(report_json_path) if report_json_path.exists() else "",
            "aggregated_bundle_path": str(aggregated_bundle_path) if aggregated_bundle_path.exists() else "",
        },
    }


__all__ = [
    "trade_report_artifact_payload",
    "prefer_richer_trade_report_section",
    "trade_report_section_summary",
    "trade_report_section_bullets",
    "normalize_trade_report_section",
    "normalize_trade_report_detail_sections",
    "normalize_trade_report_detail_meta",
    "build_trade_report_detail_view",
    "collect_strategist_feedback_inputs",
    "build_recent_trade_feedback_summary_input",
    "build_trade_report_recent_feedback_view",
    "build_trade_report_recent_feedback_pack",
    "load_trade_report_recent_feedback_pack",
    "load_time_bucketed_trade_report_recent_feedback_pack",
    "load_reporter_snippet_for_run",
    "build_linked_trade_report_card",
    "build_unlinked_trade_report_card",
    "load_trade_report_detail_payloads",
    "load_operator_brief_detail_payloads",
    "normalize_operator_brief_detail_payload",
    "build_operator_brief_detail_view",
    "extract_labeled_bullet",
    "extract_labeled_int",
    "parse_canonical_filter_bullets",
    "normalize_canonical_monitor_snapshot",
    "brief_headline_text",
    "brief_norm_symbol_text",
    "brief_headline_matches_symbol",
    "brief_collect_top_headlines",
    "brief_top_numeric_drivers",
    "load_trade_report_payloads",
]
