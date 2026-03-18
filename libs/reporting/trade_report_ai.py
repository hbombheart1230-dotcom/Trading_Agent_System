from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from libs.llm.json_response import parse_llm_json_response, required_key_metadata
from libs.llm.model_names import normalize_openrouter_model_name
from libs.llm.llm_router import LLMRouter
from libs.reporting.llm_artifacts import build_llm_response_artifact, classify_llm_exception, make_attempt


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: Any, *, max_len: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _listify(values: Any, *, max_items: int = 6, max_len: int = 240) -> List[str]:
    out: List[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        text = _clip(value, max_len=max_len)
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _fmt_pct(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number * 100.0:.2f}%"


def _fmt_price(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number:.2f}"


AI_TRADE_REPORT_REQUIRED_KEYS = [
    "executive_summary",
    "market_context_at_entry",
    "why_this_symbol_was_chosen",
    "entry_decision",
    "holding_monitoring_story",
    "exit_decision",
    "execution_quality",
    "scanner_filters",
    "guard_approval_result",
    "reporter_evaluation",
    "errors_weaknesses_improvement_points",
    "final_operator_conclusion",
]


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_section(section: Any, *, default_summary: str = "", bullet_key: str = "bullets") -> Dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    out = {
        "summary": _clip(data.get("summary"), max_len=600) or _clip(default_summary, max_len=600),
        bullet_key: _listify(data.get(bullet_key), max_items=8, max_len=260),
    }
    for key in (
        "headline",
        "action",
        "confidence",
        "status",
        "grade",
        "current_action",
        "symbol",
        "story_type",
    ):
        value = _clip(data.get(key), max_len=120)
        if value:
            out[key] = value
    return out


def _actual_lifecycle_action(story_input: Dict[str, Any]) -> str:
    status_text = str(story_input.get("status") or "").strip().lower()
    exit_summary = story_input.get("exit_summary") if isinstance(story_input.get("exit_summary"), dict) else {}
    entry_summary = story_input.get("entry_summary") if isinstance(story_input.get("entry_summary"), dict) else {}
    operator_conclusion = story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}

    exit_action = _clip(exit_summary.get("action"), max_len=24).upper()
    entry_action = _clip(entry_summary.get("action"), max_len=24).upper()
    requested_action = _clip(story_input.get("action"), max_len=24).upper()
    conclusion_action = _clip(operator_conclusion.get("current_action"), max_len=24).upper()

    if exit_action in {"BUY", "SELL"}:
        return exit_action
    if status_text == "open":
        if conclusion_action in {"HOLD", "WAIT", "BUY"}:
            return conclusion_action
        return "HOLD"
    if requested_action in {"BUY", "SELL"}:
        return requested_action
    if conclusion_action in {"BUY", "SELL", "HOLD", "WAIT"}:
        return conclusion_action
    if entry_action in {"BUY", "SELL"}:
        return entry_action
    return "WAIT"


def _normalize_trade_report_output(story_input: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(report or {})
    action = _actual_lifecycle_action(story_input)
    symbol = _clip(story_input.get("symbol"), max_len=32) or _clip(out.get("symbol"), max_len=32) or "unknown"
    status_text = _clip(story_input.get("status"), max_len=32) or _clip(out.get("status"), max_len=32) or "closed"
    story_type = _clip(story_input.get("story_type"), max_len=40) or _clip(out.get("story_type"), max_len=40)
    execution_mode = _clip(story_input.get("execution_mode_label"), max_len=80) or _clip(out.get("execution_mode_label"), max_len=80)

    out["symbol"] = symbol
    out["action"] = action
    out["status"] = status_text
    if story_type:
        out["story_type"] = story_type
    if execution_mode:
        out["execution_mode_label"] = execution_mode

    executive = out.get("executive_summary") if isinstance(out.get("executive_summary"), dict) else {}
    executive_summary = dict(executive)
    executive_summary["action"] = action
    executive_summary["symbol"] = symbol
    if not str(executive_summary.get("headline") or "").strip():
        executive_summary["headline"] = f"{action} {symbol}"
    out["executive_summary"] = executive_summary

    final_conclusion = out.get("final_operator_conclusion") if isinstance(out.get("final_operator_conclusion"), dict) else {}
    normalized_conclusion = dict(final_conclusion)
    normalized_conclusion["current_action"] = "HOLD" if status_text.lower() == "open" and action == "BUY" else action
    out["final_operator_conclusion"] = normalized_conclusion
    if "section_provenance" not in out:
        out["section_provenance"] = _report_section_provenance(story_input)
    if "evidence_source" not in out:
        out["evidence_source"] = str(story_input.get("evidence_source") or "fallback")
    section_provenance = out.get("section_provenance") if isinstance(out.get("section_provenance"), dict) else {}
    for section_key in (
        "executive_summary",
        "market_context_at_entry",
        "why_this_symbol_was_chosen",
        "entry_decision",
        "holding_monitoring_story",
        "exit_decision",
        "execution_quality",
        "scanner_filters",
        "guard_approval_result",
        "reporter_evaluation",
        "errors_weaknesses_improvement_points",
        "final_operator_conclusion",
    ):
        section = out.get(section_key) if isinstance(out.get(section_key), dict) else {}
        source_entry = (
            _normalize_provenance_entry(section_provenance.get(section_key))
            if isinstance(section_provenance.get(section_key), dict)
            else _normalize_provenance_entry({})
        )
        section["evidence_source"] = str(source_entry.get("evidence_source") or "fallback")
        section["confidence"] = str(source_entry.get("confidence") or "low")
        section["completeness"] = float(source_entry.get("completeness") or 0.0)
        out[section_key] = section
    return out


def _normalize_provenance_entry(entry: Any) -> Dict[str, Any]:
    row = entry if isinstance(entry, dict) else {}
    source = str(row.get("source") or "fallback").strip().lower()
    path = str(row.get("artifact_path") or "").strip()
    confidence = str(row.get("confidence") or "").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        if source == "canonical":
            confidence = "high"
        elif source in {"direct_artifact", "direct"}:
            confidence = "medium"
        else:
            confidence = "low"
    if confidence == "high":
        completeness = 1.0
    elif confidence == "medium":
        completeness = 0.75
    else:
        completeness = 0.5 if source != "fallback" else 0.35
    return {
        "source": source or "fallback",
        "evidence_source": source or "fallback",
        "artifact_path": path,
        "confidence": confidence,
        "completeness": completeness,
    }


def _report_section_provenance(story_input: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    source = story_input.get("section_provenance") if isinstance(story_input.get("section_provenance"), dict) else {}
    fallback = _normalize_provenance_entry({"source": "fallback", "artifact_path": "", "confidence": "low"})
    return {
        "executive_summary": _normalize_provenance_entry(source.get("operator_conclusion_human") or fallback),
        "market_context_at_entry": _normalize_provenance_entry(source.get("market_context_human") or fallback),
        "why_this_symbol_was_chosen": _normalize_provenance_entry(source.get("scanner_reason_human") or fallback),
        "entry_decision": _normalize_provenance_entry(source.get("scanner_reason_human") or fallback),
        "holding_monitoring_story": _normalize_provenance_entry(source.get("monitor_reason_human") or fallback),
        "exit_decision": _normalize_provenance_entry(source.get("monitor_reason_human") or fallback),
        "execution_quality": _normalize_provenance_entry(source.get("execution_outcome_human") or fallback),
        "scanner_filters": _normalize_provenance_entry(source.get("filters_human") or fallback),
        "guard_approval_result": _normalize_provenance_entry(source.get("guard_reason_human") or fallback),
        "reporter_evaluation": _normalize_provenance_entry(source.get("reporter_status_human") or fallback),
        "errors_weaknesses_improvement_points": _normalize_provenance_entry(source.get("reporter_status_human") or fallback),
        "full_timeline": _normalize_provenance_entry(source.get("timeline") or fallback),
        "final_operator_conclusion": _normalize_provenance_entry(source.get("operator_conclusion_human") or fallback),
    }


def _contains_hangul(value: Any) -> bool:
    return bool(re.search(r"[가-힣]", str(value or "")))


def _prefer_fallback_text(ai_text: Any, fallback_text: Any) -> str:
    ai_clean = _clip(ai_text, max_len=2000)
    fallback_clean = _clip(fallback_text, max_len=2000)
    if not ai_clean:
        return fallback_clean
    if fallback_clean and not _contains_hangul(ai_clean) and _contains_hangul(fallback_clean):
        return fallback_clean
    return ai_clean


def _merge_section_with_fallback(ai_section: Any, fallback_section: Dict[str, Any]) -> Dict[str, Any]:
    section = ai_section if isinstance(ai_section, dict) else {}
    fallback = fallback_section if isinstance(fallback_section, dict) else {}
    merged = dict(section)
    merged["summary"] = _prefer_fallback_text(section.get("summary"), fallback.get("summary"))
    ai_bullets = _listify(section.get("bullets"), max_items=12, max_len=260)
    fallback_bullets = _listify(fallback.get("bullets"), max_items=12, max_len=260)
    if not ai_bullets:
        merged["bullets"] = fallback_bullets
    elif fallback_bullets and not any(_contains_hangul(item) for item in ai_bullets) and any(_contains_hangul(item) for item in fallback_bullets):
        merged["bullets"] = fallback_bullets
    else:
        merged["bullets"] = ai_bullets
    for key in ("headline", "action", "confidence", "status", "grade", "current_action", "symbol"):
        if not str(merged.get(key) or "").strip() and str(fallback.get(key) or "").strip():
            merged[key] = fallback.get(key)
    return merged


def _trade_report_parse_meta(raw: Any, parsed: Dict[str, Any] | None) -> Dict[str, Any]:
    result = parse_llm_json_response(raw)
    candidate = parsed if isinstance(parsed, dict) else {}
    key_meta = required_key_metadata(candidate, AI_TRADE_REPORT_REQUIRED_KEYS)
    parse_mode = "none"
    if bool(result.get("is_full")):
        parse_mode = "full"
    elif bool(result.get("is_partial")):
        parse_mode = "partial"
    return {
        "parse_mode": parse_mode,
        **key_meta,
        "trailing_text": str(result.get("trailing_text") or ""),
        "raw_nonempty": bool(result.get("raw_nonempty")),
        "parse_error": str(result.get("error") or ""),
    }


def _merge_trade_report_candidate(
    story_input: Dict[str, Any],
    candidate: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
) -> Dict[str, Any]:
    out = _fallback_report(
        story_input,
        status=status,
        mode=mode,
        model=model,
        reason=reason,
    )
    out["generation"] = {
        "status": status,
        "mode": mode,
        "model": _clip(model, max_len=120),
        "reason": _clip(reason, max_len=320),
    }
    used_fallback_sections: List[str] = []

    def _merge_into(section_key: str, source_value: Any, fallback_key: str | None = None) -> None:
        normalized = _normalize_section(
            source_value,
            default_summary=(out.get(section_key) or {}).get("summary") or "",
        )
        merged = _merge_section_with_fallback(normalized, out.get(section_key) if isinstance(out.get(section_key), dict) else {})
        if not (isinstance(source_value, dict) and source_value):
            used_fallback_sections.append(section_key)
        out[section_key] = merged
        if fallback_key:
            out[fallback_key] = dict(merged)

    _merge_into("executive_summary", candidate.get("executive_summary"))
    _merge_into("market_context_at_entry", candidate.get("market_context_at_entry") or candidate.get("market_context"), "market_context")
    _merge_into("why_this_symbol_was_chosen", candidate.get("why_this_symbol_was_chosen") or candidate.get("why_this_symbol"), "why_this_symbol")
    _merge_into("entry_decision", candidate.get("entry_decision"))
    _merge_into("holding_monitoring_story", candidate.get("holding_monitoring_story") or candidate.get("monitor_trigger_reasoning"), "monitor_trigger_reasoning")
    _merge_into("exit_decision", candidate.get("exit_decision"))
    _merge_into("execution_quality", candidate.get("execution_quality") or candidate.get("execution_result"), "execution_result")
    _merge_into("scanner_filters", candidate.get("scanner_filters") or candidate.get("scanner_logic_and_filters"), "scanner_logic_and_filters")
    _merge_into("guard_approval_result", candidate.get("guard_approval_result"))
    out["reporter_evaluation"] = _merge_section_with_fallback(
        _normalize_section(candidate.get("reporter_evaluation"), default_summary=out["reporter_evaluation"]["summary"]),
        out["reporter_evaluation"],
    )
    if not isinstance(candidate.get("reporter_evaluation"), dict):
        used_fallback_sections.append("reporter_evaluation")
    out["errors_weaknesses_improvement_points"] = _merge_section_with_fallback(
        _normalize_section(
            candidate.get("errors_weaknesses_improvement_points"),
            default_summary=out["errors_weaknesses_improvement_points"]["summary"],
        ),
        out["errors_weaknesses_improvement_points"],
    )
    if not isinstance(candidate.get("errors_weaknesses_improvement_points"), dict):
        used_fallback_sections.append("errors_weaknesses_improvement_points")

    final_conclusion = candidate.get("final_operator_conclusion") if isinstance(candidate.get("final_operator_conclusion"), dict) else {}
    out["final_operator_conclusion"] = {
        "summary": _prefer_fallback_text(final_conclusion.get("summary"), out["final_operator_conclusion"]["summary"]),
        "current_action": _clip(final_conclusion.get("current_action"), max_len=24) or out["final_operator_conclusion"]["current_action"],
        "watch_next": _listify(final_conclusion.get("watch_next"), max_items=6, max_len=200) or out["final_operator_conclusion"]["watch_next"],
        "thesis_invalidation": _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=200)
        or out["final_operator_conclusion"]["thesis_invalidation"],
    }
    if not final_conclusion:
        used_fallback_sections.append("final_operator_conclusion")

    timeline_rows: List[Dict[str, Any]] = []
    parsed_timeline = candidate.get("full_timeline")
    if isinstance(parsed_timeline, list):
        timeline_rows = [row for row in parsed_timeline if isinstance(row, dict)][:24]
    if not timeline_rows:
        timeline_rows = [row for row in list(candidate.get("timeline") or []) if isinstance(row, dict)][:24]
    if timeline_rows:
        out["full_timeline"] = timeline_rows
        out["timeline"] = timeline_rows
    else:
        used_fallback_sections.append("timeline")

    out["used_fallback_sections"] = sorted(set(used_fallback_sections))
    return _normalize_trade_report_output(story_input, out)


def _fallback_report(
    story_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
) -> Dict[str, Any]:
    market_context = story_input.get("market_context_human") if isinstance(story_input.get("market_context_human"), dict) else {}
    scanner_reason = story_input.get("scanner_reason_human") if isinstance(story_input.get("scanner_reason_human"), dict) else {}
    filters_human = story_input.get("filters_human") if isinstance(story_input.get("filters_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    guard_reason = story_input.get("guard_reason_human") if isinstance(story_input.get("guard_reason_human"), dict) else {}
    execution_outcome = story_input.get("execution_outcome_human") if isinstance(story_input.get("execution_outcome_human"), dict) else {}
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    operator_conclusion = (
        story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}
    )
    action = _clip(story_input.get("action"), max_len=24) or "WAIT"
    monitor_snapshot = {
        "posture": _clip(monitor_reason.get("posture"), max_len=40) or action or "WAIT",
        "trigger_type": _clip(monitor_reason.get("trigger_type"), max_len=80) or "not_captured",
        "position_age_seconds": int(monitor_reason.get("position_age_seconds") or 0),
        "stop_loss_pct": monitor_reason.get("stop_loss_pct"),
        "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct"),
        "effective_stop_reason": _clip(monitor_reason.get("effective_stop_reason"), max_len=80) or "not_captured",
        "take_profit_pct": monitor_reason.get("take_profit_pct"),
        "exit_triggered": bool(monitor_reason.get("exit_triggered")),
        "current_price": monitor_reason.get("current_price"),
        "average_price": monitor_reason.get("average_price"),
        "peak_price": monitor_reason.get("peak_price"),
        "current_drawdown": monitor_reason.get("current_drawdown"),
        "peak_drawdown": monitor_reason.get("peak_drawdown"),
        "vwap_distance": monitor_reason.get("vwap_distance"),
        "active_exit_axis": _clip(monitor_reason.get("active_exit_axis"), max_len=80),
        "watch_axes": _listify(monitor_reason.get("watch_axes"), max_items=8, max_len=120),
        "price_source": _clip(monitor_reason.get("price_source"), max_len=120) or "not_captured",
        "feature_source": _clip(monitor_reason.get("feature_source"), max_len=120) or "not_captured",
        "price_source_policy": _clip(monitor_reason.get("price_source_policy"), max_len=260) or "",
    }
    entry_summary = story_input.get("entry_summary") if isinstance(story_input.get("entry_summary"), dict) else {}
    holding_summary = story_input.get("holding_summary") if isinstance(story_input.get("holding_summary"), dict) else {}
    exit_summary = story_input.get("exit_summary") if isinstance(story_input.get("exit_summary"), dict) else {}
    lifecycle_summary = story_input.get("lifecycle_summary") if isinstance(story_input.get("lifecycle_summary"), dict) else {}
    warnings = _listify(story_input.get("warnings"), max_items=10, max_len=260)
    improvement_points = _listify(story_input.get("improvement_points"), max_items=10, max_len=260)

    symbol = _clip(story_input.get("symbol"), max_len=32) or "unknown"
    trade_id = _clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120)
    status_text = _clip(story_input.get("status"), max_len=32) or "closed"
    executive_reason = (
        _clip(operator_conclusion.get("summary"), max_len=600)
        or _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=600)
        or _clip(execution_outcome.get("summary"), max_len=600)
        or _clip(scanner_reason.get("summary"), max_len=600)
        or "The decision path was recorded, but the operator-facing summary is limited."
    )
    confidence = _clip(scanner_reason.get("confidence_label"), max_len=24) or _clip(scanner_reason.get("confidence"), max_len=24)

    entry_decision = {
        "summary": (
            _clip(entry_summary.get("reason_human"), max_len=600)
            or _clip(scanner_reason.get("summary"), max_len=600)
            or "Entry decision rationale was not captured."
        ),
        "bullets": [
            f"Entry run: {_clip(entry_summary.get('run_id'), max_len=80) or 'not_captured'}",
            f"Entry time: {_clip(entry_summary.get('ts'), max_len=80) or 'not_captured'}",
            f"Entry action: {_clip(entry_summary.get('action'), max_len=40) or action}",
            f"Entry reason: {_clip(entry_summary.get('reason_human'), max_len=220) or 'not_captured'}",
        ],
    }
    hold_count = len(list(holding_summary.get("run_ids") or []))
    holding_story = {
        "summary": (
            f"Holding phase captured {hold_count} monitor runs."
            if hold_count > 0
            else "Holding phase evidence is limited for this lifecycle."
        ),
        "bullets": (
            _listify(holding_summary.get("monitor_updates"), max_items=10, max_len=260)
            or _listify(monitor_reason.get("bullets"), max_items=10, max_len=260)
        ),
    }
    exit_decision = {
        "summary": (
            _clip(exit_summary.get("reason_human"), max_len=600)
            or ("Position is still open; no closing SELL execution has been captured yet." if status_text == "open" else "Exit reasoning was not captured.")
        ),
        "bullets": [
            f"Exit run: {_clip(exit_summary.get('run_id'), max_len=80) or 'not_captured'}",
            f"Exit time: {_clip(exit_summary.get('ts'), max_len=80) or 'not_captured'}",
            f"Exit action: {_clip(exit_summary.get('action'), max_len=40) or ('HOLD' if status_text == 'open' else 'not_captured')}",
            f"Exit reason: {_clip(exit_summary.get('reason_human'), max_len=220) or ('position still open' if status_text == 'open' else 'not_captured')}",
        ],
    }
    execution_quality = {
        "summary": (
            _clip(execution_outcome.get("summary"), max_len=600)
            or _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=600)
            or "Execution quality details were not captured."
        ),
        "bullets": _listify(execution_outcome.get("bullets"), max_items=10, max_len=260),
    }
    reporter_eval = {
        "summary": _clip(reporter_status.get("summary"), max_len=600) or "Reporter linkage was not available yet.",
        "status": _clip(reporter_status.get("status"), max_len=40) or "missing",
        "grade": _clip(reporter_status.get("grade"), max_len=16) or "N/A",
        "bullets": _listify(reporter_status.get("bullets"), max_items=8, max_len=260),
    }
    weaknesses_bullets = warnings + [item for item in improvement_points if item not in warnings]
    full_timeline = [
        row
        for row in list(story_input.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]

    out = {
        "schema_version": "ai_trade_report.v2",
        "generated_at": _utc_now_iso(),
        "trade_id": trade_id,
        "story_id": _clip(story_input.get("story_id"), max_len=120) or trade_id,
        "run_id": _clip(story_input.get("run_id"), max_len=120),
        "symbol": symbol,
        "action": action,
        "status": status_text,
        "story_type": _clip(story_input.get("story_type"), max_len=40),
        "execution_mode_label": _clip(story_input.get("execution_mode_label"), max_len=80),
        "generation": {
            "status": status,
            "mode": mode,
            "model": _clip(model, max_len=120),
            "reason": _clip(reason, max_len=320),
        },
        "executive_summary": {
            "headline": f"{action} {symbol}",
            "action": action,
            "symbol": symbol,
            "confidence": confidence or "not_captured",
            "summary": executive_reason,
        },
        "market_context_at_entry": {
            "summary": _clip(market_context.get("summary"), max_len=600),
            "bullets": _listify(market_context.get("bullets"), max_items=8, max_len=260),
        },
        "why_this_symbol_was_chosen": {
            "summary": _clip(scanner_reason.get("summary"), max_len=600),
            "bullets": _listify(scanner_reason.get("bullets"), max_items=8, max_len=260),
        },
        "entry_decision": entry_decision,
        "holding_monitoring_story": holding_story,
        "exit_decision": exit_decision,
        "execution_quality": execution_quality,
        "monitor_snapshot": monitor_snapshot,
        "scanner_filters": {
            "summary": _clip(filters_human.get("summary"), max_len=600),
            "bullets": _listify(filters_human.get("bullets"), max_items=12, max_len=260),
        },
        "guard_approval_result": {
            "summary": _clip(guard_reason.get("summary"), max_len=600),
            "bullets": _listify(guard_reason.get("bullets"), max_items=8, max_len=260),
        },
        "reporter_evaluation": reporter_eval,
        "errors_weaknesses_improvement_points": {
            "summary": (
                "Warnings and missing links were recorded for operator follow-up."
                if weaknesses_bullets
                else "No explicit weaknesses were surfaced beyond the recorded trace."
            ),
            "bullets": weaknesses_bullets,
        },
        "full_timeline": full_timeline,
        "timeline": full_timeline,
        "final_operator_conclusion": {
            "summary": _clip(operator_conclusion.get("summary"), max_len=600) or executive_reason,
            "current_action": _clip(operator_conclusion.get("current_action"), max_len=24) or action,
            "watch_next": _listify(operator_conclusion.get("watch_next"), max_items=6, max_len=200),
            "thesis_invalidation": _listify(operator_conclusion.get("thesis_invalidation"), max_items=6, max_len=200),
        },
    }
    # Backward-compatible aliases used by earlier UI/report consumers.
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return out


def _failure_report(
    story_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
    error: str = "",
) -> Dict[str, Any]:
    trade_id = _clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120)
    action = _actual_lifecycle_action(story_input)
    symbol = _clip(story_input.get("symbol"), max_len=32) or "unknown"
    status_text = _clip(story_input.get("status"), max_len=32) or "unknown"
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    full_timeline = [
        row
        for row in list(story_input.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]
    out = {
        "schema_version": "ai_trade_report.v2",
        "generated_at": _utc_now_iso(),
        "trade_id": trade_id,
        "story_id": _clip(story_input.get("story_id"), max_len=120) or trade_id,
        "run_id": _clip(story_input.get("run_id"), max_len=120),
        "symbol": symbol,
        "action": action,
        "status": status_text,
        "story_type": _clip(story_input.get("story_type"), max_len=40),
        "execution_mode_label": _clip(story_input.get("execution_mode_label"), max_len=80),
        "generation": {
            "status": status,
            "mode": mode,
            "model": _clip(model, max_len=120),
            "reason": _clip(reason, max_len=320),
        },
        "failure": {
            "status": status,
            "reason": _clip(reason, max_len=320),
            "error": _clip(error, max_len=500),
        },
        "executive_summary": {
            "headline": f"AI trade report failed for {symbol}",
            "action": action,
            "symbol": symbol,
            "confidence": "not_available",
            "summary": "AI trade report generation failed after retry attempts. Review the saved LLM response artifact for details.",
        },
        "market_context_at_entry": {
            "summary": "AI generation failed before a rendered market-context section was produced.",
            "bullets": [],
        },
        "why_this_symbol_was_chosen": {
            "summary": "AI generation failed before a rendered symbol-selection section was produced.",
            "bullets": [],
        },
        "entry_decision": {
            "summary": "AI generation failed before a rendered entry-decision section was produced.",
            "bullets": [],
        },
        "holding_monitoring_story": {
            "summary": "AI generation failed before a rendered holding-monitoring section was produced.",
            "bullets": _listify(monitor_reason.get("bullets"), max_items=8, max_len=260),
        },
        "exit_decision": {
            "summary": "AI generation failed before a rendered exit-decision section was produced.",
            "bullets": [],
        },
        "execution_quality": {
            "summary": "AI generation failed before a rendered execution-quality section was produced.",
            "bullets": [],
        },
        "monitor_snapshot": {
            "posture": _clip(monitor_reason.get("posture"), max_len=40) or action or "WAIT",
            "trigger_type": _clip(monitor_reason.get("trigger_type"), max_len=80) or "not_captured",
            "position_age_seconds": int(monitor_reason.get("position_age_seconds") or 0),
            "stop_loss_pct": monitor_reason.get("stop_loss_pct"),
            "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct"),
            "effective_stop_reason": _clip(monitor_reason.get("effective_stop_reason"), max_len=80) or "not_captured",
            "take_profit_pct": monitor_reason.get("take_profit_pct"),
            "exit_triggered": bool(monitor_reason.get("exit_triggered")),
            "current_price": monitor_reason.get("current_price"),
            "average_price": monitor_reason.get("average_price"),
            "peak_price": monitor_reason.get("peak_price"),
            "current_drawdown": monitor_reason.get("current_drawdown"),
            "peak_drawdown": monitor_reason.get("peak_drawdown"),
            "vwap_distance": monitor_reason.get("vwap_distance"),
            "active_exit_axis": _clip(monitor_reason.get("active_exit_axis"), max_len=80),
            "watch_axes": _listify(monitor_reason.get("watch_axes"), max_items=8, max_len=120),
            "price_source": _clip(monitor_reason.get("price_source"), max_len=120) or "not_captured",
            "feature_source": _clip(monitor_reason.get("feature_source"), max_len=120) or "not_captured",
            "price_source_policy": _clip(monitor_reason.get("price_source_policy"), max_len=260) or "",
        },
        "scanner_filters": {
            "summary": "AI generation failed before a rendered scanner-filter section was produced.",
            "bullets": [],
        },
        "guard_approval_result": {
            "summary": "AI generation failed before a rendered guard-approval section was produced.",
            "bullets": [],
        },
        "reporter_evaluation": {
            "summary": _clip(reporter_status.get("summary"), max_len=600) or "Reporter linkage status was recorded separately.",
            "status": _clip(reporter_status.get("status"), max_len=40) or "missing",
            "grade": _clip(reporter_status.get("grade"), max_len=16) or "N/A",
            "bullets": _listify(reporter_status.get("bullets"), max_items=8, max_len=260),
        },
        "errors_weaknesses_improvement_points": {
            "summary": "AI generation failed and no rendered improvement section is available.",
            "bullets": [entry for entry in [_clip(reason, max_len=240), _clip(error, max_len=240)] if entry],
        },
        "full_timeline": full_timeline,
        "timeline": full_timeline,
        "final_operator_conclusion": {
            "summary": "AI generation failed. Review lifecycle artifacts and the saved LLM response artifact before taking action.",
            "current_action": "HOLD" if status_text.lower() == "open" and action == "BUY" else action,
            "watch_next": [],
            "thesis_invalidation": [],
        },
    }
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return _normalize_trade_report_output(story_input, out)


def _build_repair_messages(story_input: Dict[str, Any], raw_response: Any) -> List[Dict[str, str]]:
    compact_input = {
        "trade_id": story_input.get("trade_id") or story_input.get("story_id"),
        "story_id": story_input.get("story_id"),
        "run_id": story_input.get("run_id"),
        "symbol": story_input.get("symbol"),
        "action": story_input.get("action"),
        "status": story_input.get("status"),
        "story_type": story_input.get("story_type"),
        "execution_mode_label": story_input.get("execution_mode_label"),
        "market_context_human": story_input.get("market_context_human"),
        "scanner_reason_human": story_input.get("scanner_reason_human"),
        "filters_human": story_input.get("filters_human"),
        "monitor_reason_human": story_input.get("monitor_reason_human"),
        "guard_reason_human": story_input.get("guard_reason_human"),
        "execution_outcome_human": story_input.get("execution_outcome_human"),
        "reporter_status_human": story_input.get("reporter_status_human"),
        "operator_conclusion_human": story_input.get("operator_conclusion_human"),
        "timeline": story_input.get("timeline"),
        "warnings": story_input.get("warnings"),
    }
    contract = {
        "executive_summary": {"headline": "str", "action": "str", "symbol": "str", "confidence": "str", "summary": "str"},
        "market_context_at_entry": {"summary": "str", "bullets": ["str"]},
        "why_this_symbol_was_chosen": {"summary": "str", "bullets": ["str"]},
        "entry_decision": {"summary": "str", "bullets": ["str"]},
        "holding_monitoring_story": {"summary": "str", "bullets": ["str"]},
        "exit_decision": {"summary": "str", "bullets": ["str"]},
        "execution_quality": {"summary": "str", "bullets": ["str"]},
        "scanner_filters": {"summary": "str", "bullets": ["str"]},
        "guard_approval_result": {"summary": "str", "bullets": ["str"]},
        "reporter_evaluation": {"summary": "str", "status": "str", "grade": "str", "bullets": ["str"]},
        "errors_weaknesses_improvement_points": {"summary": "str", "bullets": ["str"]},
        "full_timeline": [{"event": "str", "ts": "str", "description": "str"}],
        "final_operator_conclusion": {"summary": "str", "current_action": "str", "watch_next": ["str"], "thesis_invalidation": ["str"]},
    }
    return [
        {
            "role": "system",
            "content": "You repair AI trade report outputs. Return one strict JSON object only. No markdown, no prose, no code fences.",
        },
        {
            "role": "user",
            "content": (
                "The previous response did not match the required JSON contract. "
                "Regenerate the report as valid JSON only.\n"
                f"JSON contract:\n{json.dumps(contract, ensure_ascii=False)}\n\n"
                f"Input:\n{json.dumps(compact_input, ensure_ascii=False)}\n\n"
                f"Previous response:\n{str(raw_response or '')[:1800]}"
            ),
        },
    ]


def _build_messages(story_input: Dict[str, Any]) -> List[Dict[str, str]]:
    compact_input = {
        "trade_id": story_input.get("trade_id") or story_input.get("story_id"),
        "story_id": story_input.get("story_id"),
        "run_id": story_input.get("run_id"),
        "symbol": story_input.get("symbol"),
        "action": story_input.get("action"),
        "status": story_input.get("status"),
        "story_type": story_input.get("story_type"),
        "execution_mode_label": story_input.get("execution_mode_label"),
        "entry_summary": story_input.get("entry_summary"),
        "holding_summary": story_input.get("holding_summary"),
        "exit_summary": story_input.get("exit_summary"),
        "lifecycle_summary": story_input.get("lifecycle_summary"),
        "market_context_human": story_input.get("market_context_human"),
        "scanner_reason_human": story_input.get("scanner_reason_human"),
        "filters_human": story_input.get("filters_human"),
        "monitor_reason_human": story_input.get("monitor_reason_human"),
        "guard_reason_human": story_input.get("guard_reason_human"),
        "execution_outcome_human": story_input.get("execution_outcome_human"),
        "reporter_status_human": story_input.get("reporter_status_human"),
        "operator_conclusion_human": story_input.get("operator_conclusion_human"),
        "timeline": story_input.get("timeline"),
        "warnings": story_input.get("warnings"),
    }
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 거래별 운영 리포트를 작성하는 한국어 분석기입니다. "
                "입력으로 제공된 사실만 사용하고 숫자나 사건을 지어내지 마세요. "
                "모든 출력은 한국어 JSON 객체 하나만 반환하세요."
            ),
        },
        {
            "role": "user",
            "content": (
                "아래 trade story input을 운영자가 한눈에 이해할 수 있는 한국어 AI 거래 리포트로 정리하세요.\n"
                "파이프라인 순서를 반드시 유지하세요: 전략가 -> 스캐너 -> 모니터 -> 감독관 -> 수행자 -> 리포터.\n"
                "다음 원칙을 지키세요.\n"
                "- 글로벌 감성 점수, VIX, 수집한 뉴스 수와 질의 대상 수를 가능한 한 숫자로 적기\n"
                "- 스캐너는 후보 수, 1등 종목, runner-up, Kiwoom 소스(top_value/top_volume/sector_theme 등), 점수/feature coverage를 구체적으로 적기\n"
                "- 모니터는 전달받은 감시 기준(stop, effective stop, take profit, watch axis, 가격 source)을 구체적으로 적기\n"
                "- 감독관과 수행자는 승인/체결 결과를 분리해서 적기\n"
                "- 리포터 linkage가 없으면 원인을 한국어로 설명하기\n"
                "- 영어 문장 대신 한국어 문장으로 쓰되, 종목코드와 key 이름은 필요한 경우 유지 가능\n"
                "아래 JSON 스키마로만 반환하세요:\n"
                "{"
                "\"executive_summary\": {\"headline\": str, \"action\": str, \"symbol\": str, \"confidence\": str, \"summary\": str}, "
                "\"market_context_at_entry\": {\"summary\": str, \"bullets\": [str]}, "
                "\"why_this_symbol_was_chosen\": {\"summary\": str, \"bullets\": [str]}, "
                "\"entry_decision\": {\"summary\": str, \"bullets\": [str]}, "
                "\"holding_monitoring_story\": {\"summary\": str, \"bullets\": [str]}, "
                "\"exit_decision\": {\"summary\": str, \"bullets\": [str]}, "
                "\"execution_quality\": {\"summary\": str, \"bullets\": [str]}, "
                "\"scanner_filters\": {\"summary\": str, \"bullets\": [str]}, "
                "\"guard_approval_result\": {\"summary\": str, \"bullets\": [str]}, "
                "\"reporter_evaluation\": {\"summary\": str, \"status\": str, \"grade\": str, \"bullets\": [str]}, "
                "\"errors_weaknesses_improvement_points\": {\"summary\": str, \"bullets\": [str]}, "
                "\"full_timeline\": [{\"event\": str, \"ts\": str, \"description\": str}], "
                "\"final_operator_conclusion\": {\"summary\": str, \"current_action\": str, \"watch_next\": [str], \"thesis_invalidation\": [str]}"
                "}\n"
                "각 section의 bullets는 3~6개 정도로 충분히 자세하게 작성하세요.\n"
                "summary는 운영자가 바로 의사결정할 수 있도록 명확하게 쓰세요.\n"
                f"Input:\n{json.dumps(compact_input, ensure_ascii=False)}"
            ),
        },
    ]


def build_ai_trade_report(
    story_input: Dict[str, Any],
    *,
    enabled: Optional[bool] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    is_enabled = _env_bool("TRADE_REPORT_AI_ENABLED", True) if enabled is None else bool(enabled)
    chosen_model = normalize_openrouter_model_name(
        str(model or "").strip()
        or str(os.getenv("TRADE_REPORT_AI_MODEL", "")).strip()
        or str(os.getenv("OPENROUTER_MODEL_TRADE_REPORT", "")).strip()
    )
    trade_id = str(story_input.get("trade_id") or story_input.get("story_id") or "")
    run_id = str(story_input.get("run_id") or "")
    day = str(story_input.get("day") or "")
    retry_max = max(0, int(float(str(os.getenv("TRADE_REPORT_AI_RETRY_MAX", "2")).strip() or "2")))
    empty_required_meta = {
        "parse_mode": "none",
        "required_keys_expected": list(AI_TRADE_REPORT_REQUIRED_KEYS),
        "required_keys_present": [],
        "required_keys_missing": list(AI_TRADE_REPORT_REQUIRED_KEYS),
        "completeness_score": 0.0,
        "used_fallback_sections": [],
    }
    if not is_enabled:
        report = _failure_report(
            story_input,
            status="disabled",
            mode="fallback",
            model=chosen_model,
            reason="TRADE_REPORT_AI_ENABLED is false",
        )
        report["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status="fallback",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or "openrouter/free"},
            meta={"reason": "TRADE_REPORT_AI_ENABLED is false", **empty_required_meta},
        )
        return report

    router = LLMRouter.from_env()
    if router.client is None:
        report = _failure_report(
            story_input,
            status="error",
            mode="ai",
            model=chosen_model,
            reason="OPENROUTER_API_KEY is not configured",
        )
        report["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status="error",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or "openrouter/free"},
            meta={"reason": "OPENROUTER_API_KEY is not configured", "error": "llm_client_unavailable", **empty_required_meta},
        )
        return report

    temp = float(
        temperature
        if temperature is not None
        else str(os.getenv("TRADE_REPORT_AI_TEMPERATURE", "0.1")).strip() or "0.1"
    )
    token_budget = int(
        max_tokens
        if max_tokens is not None
        else str(os.getenv("TRADE_REPORT_AI_MAX_TOKENS", "1400")).strip() or "1400"
    )
    messages = _build_messages(story_input)
    attempts: List[Dict[str, Any]] = []
    resolved_model = str(
        router.resolve(
            "trade_report",
            policy={
                "temperature": temp,
                "max_tokens": max(600, token_budget),
                **({"model": chosen_model} if chosen_model else {}),
            },
        ).model
    )
    final_status = "error"
    final_reason = ""
    final_error = ""
    final_latency_ms = 0
    parsed: Optional[Dict[str, Any]] = None
    best_partial: Dict[str, Any] = {}
    best_partial_meta: Dict[str, Any] = {}
    raw = ""
    current_messages = list(messages)
    current_policy = {
        "temperature": temp,
        "max_tokens": max(600, token_budget),
        "response_format": {"type": "json_object"},
        **({"model": chosen_model} if chosen_model else {}),
    }
    for attempt_index in range(retry_max + 1):
        step = "primary" if attempt_index == 0 else f"retry_{attempt_index}"
        t0 = time.perf_counter()
        try:
            raw = router.chat("trade_report", current_messages, policy=current_policy)
        except Exception as exc:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            final_status = classify_llm_exception(exc)
            final_reason = f"trade_report_ai_exception:{type(exc).__name__}:{exc}"
            final_error = f"{type(exc).__name__}:{exc}"
            attempts.append(
                make_attempt(
                    step=step,
                    messages=current_messages,
                    raw_response_text=f"ERROR:{final_error}",
                    parsed_output={},
                    model=chosen_model or resolved_model,
                    latency_ms=final_latency_ms,
                    status=final_status,
                    meta={"role": "ai_trade_report", "error": final_error},
                )
            )
        else:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            parse_result = parse_llm_json_response(raw)
            candidate = parse_result.get("full_object") if isinstance(parse_result.get("full_object"), dict) else parse_result.get("partial_object")
            candidate = dict(candidate) if isinstance(candidate, dict) else {}
            parse_meta = _trade_report_parse_meta(raw, candidate)
            if not bool(parse_result.get("raw_nonempty")):
                final_status = "empty_response"
                final_reason = "trade_report_ai returned an empty response"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output={},
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta},
                    )
                )
            elif bool(parse_result.get("is_full")) and not parse_meta.get("required_keys_missing"):
                parsed = candidate
                final_status = "repaired" if step.startswith("repair") else "ok"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output=parsed,
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", **parse_meta},
                    )
                )
                break
            elif candidate:
                best_partial = dict(candidate)
                best_partial_meta = dict(parse_meta)
                final_status = "partial"
                missing = list(parse_meta.get("required_keys_missing") or [])
                if bool(parse_result.get("is_partial")):
                    final_reason = "trade_report_ai returned truncated or partial JSON"
                elif missing:
                    final_reason = f"trade_report_ai response is missing required keys: {', '.join(missing)}"
                else:
                    final_reason = "trade_report_ai response was incomplete"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output=candidate,
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta},
                    )
                )
            else:
                final_status = "parse_error"
                final_reason = "trade_report_ai returned non-JSON response"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output={},
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta},
                    )
                )
        if attempt_index < retry_max:
            if final_status in {"parse_error", "partial"}:
                current_messages = _build_repair_messages(story_input, raw)
            current_policy = {
                **current_policy,
                "temperature": 0.0,
                "max_tokens": min(max(800, token_budget), 1800),
            }

    if not parsed and best_partial:
        final_status = "salvaged"
        final_reason = final_reason or "trade_report_ai returned incomplete JSON; deterministic sections were salvaged from the partial response"
        out = _merge_trade_report_candidate(
            story_input,
            best_partial,
            status=final_status,
            mode="ai",
            model=chosen_model or resolved_model,
            reason=final_reason,
        )
        out["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status=final_status,
            attempts=attempts,
            parsed_output=best_partial,
            model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
            latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
            meta={
                "reason": final_reason,
                "error": final_error,
                **best_partial_meta,
                "used_fallback_sections": list(out.get("used_fallback_sections") or []),
            },
        )
        return out

    if not parsed:
        report = _failure_report(
            story_input,
            status=final_status,
            mode="ai",
            model=chosen_model or resolved_model,
            reason=final_reason or "AI trade report generation failed",
            error=final_error,
        )
        report["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status=final_status,
            attempts=attempts,
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
            latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
            meta={"reason": final_reason, "error": final_error, **empty_required_meta},
        )
        return report

    parse_meta = _trade_report_parse_meta(raw, parsed)
    out = _merge_trade_report_candidate(
        story_input,
        parsed,
        status=final_status,
        mode="ai",
        model=chosen_model or resolved_model,
        reason=final_reason,
    )
    out["llm_response_artifact"] = build_llm_response_artifact(
        component="ai_trade_report",
        run_id=run_id,
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        status=final_status,
        attempts=attempts,
        parsed_output=parsed,
        model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
        latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
        meta={
            **parse_meta,
            "reason": final_reason,
            "used_fallback_sections": list(out.get("used_fallback_sections") or []),
        },
    )
    return out


def render_trade_report_markdown(report: Dict[str, Any]) -> str:
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    generation_status = str(generation.get("status") or "").strip().lower()
    if generation_status not in {"", "ok", "repaired", "partial", "salvaged"}:
        failure = report.get("failure") if isinstance(report.get("failure"), dict) else {}
        lines = [
            f"# AI Trade Report ({report.get('trade_id') or report.get('story_id') or report.get('run_id') or 'story'})",
            "",
            f"- action: **{report.get('action') or '-'} {report.get('symbol') or '-'}**",
            f"- lifecycle_status: **{report.get('status') or '-'}**",
            f"- generation_status: `{generation.get('status') or '-'}`",
            f"- model: `{generation.get('model') or '-'}`",
            "",
            "## Failure",
            "",
            f"- reason: {failure.get('reason') or generation.get('reason') or '-'}",
        ]
        if str(failure.get("error") or "").strip():
            lines.append(f"- error: {failure.get('error')}")
        lines.append("")
        return "\n".join(lines)

    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    market_context = (
        report.get("market_context_at_entry")
        if isinstance(report.get("market_context_at_entry"), dict)
        else report.get("market_context")
        if isinstance(report.get("market_context"), dict)
        else {}
    )
    why_symbol = (
        report.get("why_this_symbol_was_chosen")
        if isinstance(report.get("why_this_symbol_was_chosen"), dict)
        else report.get("why_this_symbol")
        if isinstance(report.get("why_this_symbol"), dict)
        else {}
    )
    entry_decision = report.get("entry_decision") if isinstance(report.get("entry_decision"), dict) else {}
    holding_story = (
        report.get("holding_monitoring_story")
        if isinstance(report.get("holding_monitoring_story"), dict)
        else report.get("monitor_trigger_reasoning")
        if isinstance(report.get("monitor_trigger_reasoning"), dict)
        else {}
    )
    exit_decision = report.get("exit_decision") if isinstance(report.get("exit_decision"), dict) else {}
    scanner_filters = (
        report.get("scanner_filters")
        if isinstance(report.get("scanner_filters"), dict)
        else report.get("scanner_logic_and_filters")
        if isinstance(report.get("scanner_logic_and_filters"), dict)
        else {}
    )
    guard_result = report.get("guard_approval_result") if isinstance(report.get("guard_approval_result"), dict) else {}
    execution_result = (
        report.get("execution_quality")
        if isinstance(report.get("execution_quality"), dict)
        else report.get("execution_result")
        if isinstance(report.get("execution_result"), dict)
        else {}
    )
    reporter_eval = report.get("reporter_evaluation") if isinstance(report.get("reporter_evaluation"), dict) else {}
    weak_points = (
        report.get("errors_weaknesses_improvement_points")
        if isinstance(report.get("errors_weaknesses_improvement_points"), dict)
        else {}
    )
    final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
    monitor_snapshot = report.get("monitor_snapshot") if isinstance(report.get("monitor_snapshot"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Trade Report ({report.get('trade_id') or report.get('story_id') or report.get('run_id') or 'story'})")
    lines.append("")
    lines.append(f"- action: **{report.get('action') or '-'} {report.get('symbol') or '-'}**")
    lines.append(f"- lifecycle_status: **{report.get('status') or '-'}**")
    lines.append(f"- story_type: **{report.get('story_type') or '-'}**")
    lines.append(f"- execution_mode: **{report.get('execution_mode_label') or '-'}**")
    lines.append(
        f"- report_generation: status=`{generation.get('status') or '-'}` mode=`{generation.get('mode') or '-'}` "
        f"model=`{generation.get('model') or '-'}`"
    )
    lines.append("")
    if generation_status in {"repaired", "partial", "salvaged"}:
        lines.append("## Generation Note")
        lines.append("")
        lines.append(
            f"- status: `{generation_status}`"
        )
        lines.append(
            f"- reason: {generation.get('reason') or 'The report was reconstructed from a repaired or partial LLM response.'}"
        )
        lines.append("")
    section_provenance = report.get("section_provenance") if isinstance(report.get("section_provenance"), dict) else {}
    if section_provenance:
        lines.append("## Evidence Provenance")
        lines.append("")
        for section_key in (
            "market_context_at_entry",
            "why_this_symbol_was_chosen",
            "holding_monitoring_story",
            "execution_quality",
            "reporter_evaluation",
        ):
            entry = section_provenance.get(section_key) if isinstance(section_provenance.get(section_key), dict) else {}
            lines.append(
                f"- {section_key}: source={entry.get('source') or 'fallback'} "
                f"confidence={entry.get('confidence') or 'low'} "
                f"path={entry.get('artifact_path') or '-'}"
            )
        lines.append("")
    if monitor_snapshot:
        lines.append("## Monitor Snapshot")
        lines.append("")
        lines.append(f"- posture: **{monitor_snapshot.get('posture') or '-'}**")
        lines.append(f"- trigger_type: **{monitor_snapshot.get('trigger_type') or '-'}**")
        lines.append(f"- effective_stop: **{_fmt_pct(monitor_snapshot.get('effective_stop_loss_pct'))}**")
        lines.append(f"- effective_stop_reason: {monitor_snapshot.get('effective_stop_reason') or '-'}")
        lines.append(f"- take_profit: {_fmt_pct(monitor_snapshot.get('take_profit_pct'))}")
        if monitor_snapshot.get("current_price") not in (None, ""):
            lines.append(f"- current_price: {_fmt_price(monitor_snapshot.get('current_price'))}")
        if monitor_snapshot.get("average_price") not in (None, ""):
            lines.append(f"- average_price: {_fmt_price(monitor_snapshot.get('average_price'))}")
        if monitor_snapshot.get("peak_price") not in (None, ""):
            lines.append(f"- peak_price: {_fmt_price(monitor_snapshot.get('peak_price'))}")
        if monitor_snapshot.get("current_drawdown") not in (None, ""):
            lines.append(f"- current_drawdown: {_fmt_pct(monitor_snapshot.get('current_drawdown'))}")
        if monitor_snapshot.get("peak_drawdown") not in (None, ""):
            lines.append(f"- peak_drawdown: {_fmt_pct(monitor_snapshot.get('peak_drawdown'))}")
        if monitor_snapshot.get("vwap_distance") not in (None, ""):
            lines.append(f"- vwap_distance: {_fmt_pct(monitor_snapshot.get('vwap_distance'))}")
        if str(monitor_snapshot.get("active_exit_axis") or "").strip():
            lines.append(f"- active_exit_axis: {monitor_snapshot.get('active_exit_axis')}")
        for axis in list(monitor_snapshot.get("watch_axes") or [])[:6]:
            lines.append(f"- watch_axis: {axis}")
        lines.append(f"- price_source: {monitor_snapshot.get('price_source') or '-'}")
        lines.append(f"- feature_source: {monitor_snapshot.get('feature_source') or '-'}")
        if str(monitor_snapshot.get('price_source_policy') or '').strip():
            lines.append(f"- price_source_policy: {monitor_snapshot.get('price_source_policy')}")
        lines.append(f"- exit_triggered: {'yes' if monitor_snapshot.get('exit_triggered') else 'no'}")
        lines.append("")

    def _section(title: str, section: Dict[str, Any], *, bullet_key: str = "bullets") -> None:
        lines.append(f"## {title}")
        lines.append("")
        summary = _clip(section.get("summary"), max_len=2000)
        if summary:
            lines.append(summary)
            lines.append("")
        bullets = _listify(section.get(bullet_key), max_items=12, max_len=400)
        for bullet in bullets:
            lines.append(f"- {bullet}")
        if bullets:
            lines.append("")

    _section("Executive Summary", executive)
    _section("Market Context at Entry", market_context)
    _section("Why This Symbol Was Chosen", why_symbol)
    _section("Entry Decision", entry_decision)
    _section("Holding / Monitoring Story", holding_story)
    _section("Exit Decision", exit_decision)
    _section("Scanner Logic and Filters", scanner_filters)
    _section("Guard / Approval Result", guard_result)
    _section("Execution Quality", execution_result)
    _section("Reporter Evaluation", reporter_eval)
    _section("Errors / Weaknesses / Improvement Points", weak_points)

    lines.append("## Full Timeline")
    lines.append("")
    timeline = report.get("full_timeline") if isinstance(report.get("full_timeline"), list) else report.get("timeline") if isinstance(report.get("timeline"), list) else []
    if timeline:
        for row in timeline[:24]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row.get('event') or row.get('step') or row.get('label') or 'step'}: "
                f"{row.get('description') or row.get('summary') or row.get('detail') or '-'}"
            )
    else:
        lines.append("- No timeline entries were captured.")
    lines.append("")

    lines.append("## Final Operator Conclusion")
    lines.append("")
    final_summary = _clip(final_conclusion.get("summary"), max_len=2000)
    if final_summary:
        lines.append(final_summary)
        lines.append("")
    current_action = _clip(final_conclusion.get("current_action"), max_len=48)
    if current_action:
        lines.append(f"- current_action: **{current_action}**")
    for item in _listify(final_conclusion.get("watch_next"), max_items=6, max_len=220):
        lines.append(f"- watch_next: {item}")
    for item in _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=220):
        lines.append(f"- thesis_invalidation: {item}")
    lines.append("")
    return "\n".join(lines)
