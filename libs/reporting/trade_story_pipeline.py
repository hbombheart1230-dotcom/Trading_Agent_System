from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from libs.reporting.reasoning_trace import (
    build_reasoning_provenance,
    build_reasoning_trace_from_summaries,
    normalize_reasoning_provenance_aliases,
    normalize_reasoning_trace_aliases,
)
from libs.reporting.strategy_read_model import (
    build_news_symbol_linkage_view,
    build_strategist_feedback_input_view,
)
from libs.reporting.trade_report_ai import resolve_shared_trade_facts
from libs.core.symbols import normalize_symbol


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def clip(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def format_pct(value: Any) -> str:
    if value in (None, ""):
        return "not_captured"
    return f"{safe_float(value, 0.0):.2f}"


def format_ratio_pct(value: Any) -> str:
    if value in (None, ""):
        return "not_captured"
    return f"{safe_float(value, 0.0) * 100.0:.2f}"


def format_exit_label(value: Any) -> str:
    text = str(value or "").strip().replace("_", " ")
    if not text:
        return "not_captured"
    return " ".join(part.capitalize() for part in text.split())


def _list_text(values: Any, *, limit: int = 6, max_len: int = 220) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = clip(value, max_len=max_len)
        if not text:
            continue
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _merge_missing_values(base: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in dict(fallback or {}).items():
        if key not in out or out.get(key) in (None, "", [], {}):
            out[key] = value
    return out


def _headline_text(row: Any) -> str:
    item = row if isinstance(row, dict) else {}
    for key in ("title", "headline", "summary", "description", "text", "news_title"):
        text = clip(item.get(key), max_len=180)
        if text:
            return text
    return ""


def _norm_symbol_text(value: Any) -> str:
    return normalize_symbol(value, allow_test_symbols=True).strip().upper()


def _headline_matches_symbol(row: Any, symbol: str) -> bool:
    item = row if isinstance(row, dict) else {}
    target = _norm_symbol_text(symbol)
    if not target:
        return False
    scalar_candidates = [
        item.get("symbol"),
        item.get("code"),
        item.get("ticker"),
        item.get("query_target"),
        item.get("query"),
        item.get("news_query_target"),
    ]
    for candidate in scalar_candidates:
        if _norm_symbol_text(candidate) == target:
            return True
    for key in ("symbols", "tickers", "related_symbols"):
        values = item.get(key)
        if not isinstance(values, list):
            continue
        for candidate in values:
            if _norm_symbol_text(candidate) == target:
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


def _collect_top_headlines(rows: Any, *, limit: int = 3, symbol: str = "") -> List[str]:
    if not isinstance(rows, list):
        return []
    filtered: List[str] = []
    fallback: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _headline_text(row)
        if not text:
            continue
        if text not in fallback:
            fallback.append(text)
        if symbol and _headline_matches_symbol(row, symbol) and text not in filtered:
            filtered.append(text)
    picked = filtered or fallback
    return picked[: max(1, int(limit))]


def _top_numeric_drivers(values: Any, *, limit: int = 4) -> Dict[str, float]:
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


def _build_strategist_evidence_trace(
    strategist: Dict[str, Any],
    *,
    selected_symbol: str = "",
    fallback_market_titles: Any = None,
    fallback_candidate_titles: Any = None,
) -> Dict[str, Any]:
    data = strategist if isinstance(strategist, dict) else {}
    news_ranked = data.get("news_evidence_ranked") if isinstance(data.get("news_evidence_ranked"), dict) else {}
    global_signal = data.get("global_sentiment_signal") if isinstance(data.get("global_sentiment_signal"), dict) else {}
    fear_index = data.get("fear_index") if isinstance(data.get("fear_index"), dict) else {}
    if not fear_index and isinstance(global_signal.get("fear_index"), dict):
        fear_index = dict(global_signal.get("fear_index") or {})
    market_rows = list(news_ranked.get("market_news_ranked") or [])
    candidate_rows = list(news_ranked.get("candidate_news_ranked") or [])
    market_headlines = _collect_top_headlines(market_rows, limit=3)
    symbol_headlines = _collect_top_headlines(candidate_rows, limit=3, symbol=selected_symbol)
    if not market_headlines:
        market_headlines = _list_text(fallback_market_titles, limit=3, max_len=180)
    if not symbol_headlines:
        symbol_headlines = _list_text(fallback_candidate_titles, limit=3, max_len=180)
    candidate_hints = _list_text(
        data.get("candidate_symbols_hint"),
        limit=8,
        max_len=24,
    )
    key_events = _list_text(
        data.get("key_events") if data.get("key_events") is not None else data.get("key_events_hint"),
        limit=6,
        max_len=180,
    )
    return {
        "candidate_hints": candidate_hints,
        "news_query_targets": _list_text(
            data.get("news_query_targets")
            if data.get("news_query_targets") is not None
            else news_ranked.get("news_query_targets"),
            limit=8,
            max_len=80,
        ),
        "market_headlines": market_headlines,
        "symbol_headlines": symbol_headlines,
        "global_sentiment_signal": dict(global_signal or {}),
        "fear_index": dict(fear_index or {}),
        "key_events": key_events,
    }


def _build_scanner_selection_trace(scanner_reason: Dict[str, Any], scanner_artifact: Dict[str, Any]) -> Dict[str, Any]:
    reason = scanner_reason if isinstance(scanner_reason, dict) else {}
    artifact = scanner_artifact if isinstance(scanner_artifact, dict) else {}
    selected_symbol = str(
        reason.get("selected_symbol")
        or artifact.get("selected_symbol")
        or ""
    ).strip()
    selected_rank = safe_int(reason.get("selected_rank"), safe_int(artifact.get("selected_rank"), 0))
    ranked_candidates = [dict(row) for row in list(reason.get("top_candidates") or []) if isinstance(row, dict)]
    if not ranked_candidates:
        ranked_candidates = [dict(row) for row in list(artifact.get("ranked_candidates") or []) if isinstance(row, dict)]
    if not ranked_candidates:
        ranking_table = artifact.get("candidate_ranking_table") if isinstance(artifact.get("candidate_ranking_table"), dict) else {}
        ranked_candidates = [dict(row) for row in list(ranking_table.get("rows") or []) if isinstance(row, dict)]
    score_drivers = {}
    if isinstance(reason.get("score_breakdown"), dict):
        score_drivers = _top_numeric_drivers(reason.get("score_breakdown"), limit=4)
    if not score_drivers:
        score_breakdown_by_symbol = artifact.get("score_breakdown_by_symbol") if isinstance(artifact.get("score_breakdown_by_symbol"), dict) else {}
        score_drivers = _top_numeric_drivers(score_breakdown_by_symbol.get(selected_symbol), limit=4)
    selection_reason = (
        clip(reason.get("selection_basis"), max_len=260)
        or clip(reason.get("selection_reason_with_bias"), max_len=260)
        or clip(artifact.get("selection_reason_with_bias"), max_len=260)
        or clip(artifact.get("selection_reason"), max_len=260)
        or clip((artifact.get("candidate_selection_reason") or {}).get("selection_summary"), max_len=260)
        or clip(reason.get("summary"), max_len=260)
    )
    return {
        "ranked_candidates": ranked_candidates[:5],
        "selected_symbol": selected_symbol,
        "selected_rank": selected_rank,
        "selection_reason": selection_reason,
        "selected_symbol_score_drivers": score_drivers,
    }


def _normalize_stop_thresholds(thresholds: Dict[str, Any]) -> Dict[str, Any]:
    data = thresholds if isinstance(thresholds, dict) else {}
    nested = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    return nested or data


def _resolve_strategist_adaptive_exit(monitor: Dict[str, Any]) -> Dict[str, Any]:
    data = monitor if isinstance(monitor, dict) else {}
    for candidate in (
        ((data.get("policy_ref") or {}).get("exit_plan") or {}).get("adaptive_exit"),
        (((data.get("decision_trace") or {}).get("policy_ref") or {}).get("exit_plan") or {}).get("adaptive_exit"),
        (((data.get("timing_assessment") or {}).get("entry_plan") or {}).get("adaptive_exit")),
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _resolve_adaptive_stop_loss_pct(monitor: Dict[str, Any], thresholds: Dict[str, Any]) -> Any:
    thresholds = _normalize_stop_thresholds(thresholds)
    adaptive_exit = monitor.get("adaptive_exit") if isinstance(monitor.get("adaptive_exit"), dict) else {}
    if adaptive_exit.get("stop_loss_pct") not in (None, ""):
        return adaptive_exit.get("stop_loss_pct")
    if thresholds.get("adaptive_stop_loss_pct") not in (None, ""):
        return thresholds.get("adaptive_stop_loss_pct")
    threshold_snapshot = monitor.get("threshold_snapshot") if isinstance(monitor.get("threshold_snapshot"), dict) else {}
    if threshold_snapshot.get("adaptive_stop_loss_pct") not in (None, ""):
        return threshold_snapshot.get("adaptive_stop_loss_pct")
    return None


def _build_monitor_stop_policy_trace(monitor: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = _normalize_stop_thresholds(thresholds)
    strategist_adaptive_exit = _resolve_strategist_adaptive_exit(monitor)
    adaptive_stop_loss_pct = _resolve_adaptive_stop_loss_pct(monitor, thresholds)
    hard_stop_pct = (
        thresholds.get("hard_stop_pct")
        if thresholds.get("hard_stop_pct") not in (None, "")
        else monitor.get("hard_stop_pct")
    )
    effective_stop_loss_pct = (
        thresholds.get("effective_stop_loss_pct")
        if thresholds.get("effective_stop_loss_pct") not in (None, "")
        else adaptive_stop_loss_pct
        if adaptive_stop_loss_pct not in (None, "")
        else hard_stop_pct
    )
    return {
        "hard_stop_pct": hard_stop_pct,
        "adaptive_stop_loss_pct": adaptive_stop_loss_pct,
        "effective_stop_loss_pct": effective_stop_loss_pct,
        "trailing_stop_pct": thresholds.get("trailing_stop_pct"),
        "take_profit_pct": thresholds.get("take_profit_pct"),
        "strategist_baseline_stop_loss_pct": strategist_adaptive_exit.get("stop_loss_pct"),
        "strategist_baseline_take_profit_pct": strategist_adaptive_exit.get("take_profit_pct"),
        "strategist_baseline_trailing_stop_pct": strategist_adaptive_exit.get("trailing_stop_pct"),
    }


def _build_monitor_blocker_trace(monitor: Dict[str, Any]) -> Dict[str, Any]:
    data = monitor if isinstance(monitor, dict) else {}
    entry_metrics = data.get("entry_metrics") if isinstance(data.get("entry_metrics"), dict) else {}
    entry_thresholds = data.get("entry_thresholds") if isinstance(data.get("entry_thresholds"), dict) else {}
    timing_assessment = data.get("timing_assessment") if isinstance(data.get("timing_assessment"), dict) else {}
    policy_ref = data.get("policy_ref") if isinstance(data.get("policy_ref"), dict) else {}
    threshold_shortfalls: List[str] = []
    if entry_metrics.get("volume_ratio") not in (None, "") and entry_thresholds.get("volume_ratio_min") not in (None, ""):
        volume_ratio = safe_float(entry_metrics.get("volume_ratio"), 0.0)
        volume_ratio_min = safe_float(entry_thresholds.get("volume_ratio_min"), 0.0)
        if volume_ratio < volume_ratio_min:
            threshold_shortfalls.append(f"volume ratio {volume_ratio:.2f} below min {volume_ratio_min:.2f}")
    if entry_metrics.get("extended_from_vwap_pct") not in (None, "") and entry_thresholds.get("max_extended_from_vwap_pct") not in (None, ""):
        extended = safe_float(entry_metrics.get("extended_from_vwap_pct"), 0.0)
        extended_max = safe_float(entry_thresholds.get("max_extended_from_vwap_pct"), 0.0)
        if extended > extended_max:
            threshold_shortfalls.append(
                f"VWAP extension {format_ratio_pct(extended)}% above max {format_ratio_pct(extended_max)}%"
            )
    if entry_metrics.get("pullback_depth_pct") not in (None, "") and entry_thresholds.get("pullback_min_pct") not in (None, ""):
        pullback_depth = safe_float(entry_metrics.get("pullback_depth_pct"), 0.0)
        pullback_min = safe_float(entry_thresholds.get("pullback_min_pct"), 0.0)
        if pullback_depth < pullback_min:
            threshold_shortfalls.append(
                f"pullback depth {format_ratio_pct(pullback_depth)}% below min {format_ratio_pct(pullback_min)}%"
            )
    return {
        "entry_check_summary": clip(data.get("entry_check_summary"), max_len=260),
        "entry_blockers": _list_text(data.get("entry_blockers"), limit=8, max_len=120),
        "threshold_shortfalls": threshold_shortfalls[:4],
        "timing_assessment": dict(timing_assessment or {}),
        "policy_ref": dict(policy_ref or {}),
        "entry_condition_path": clip(data.get("entry_condition_path"), max_len=80),
        "entry_condition_paths_passed": _list_text(data.get("entry_condition_paths_passed"), limit=4, max_len=80),
        "condition_scores": dict(data.get("condition_scores") or {}),
        "grouped_logic_trace": dict(data.get("grouped_logic_trace") or {}),
    }


def _source_confidence_label(source: Any) -> str:
    raw = str(source or "").strip().lower()
    if raw in {"canonical", "normalized_trade_artifact", "normalized_trade"}:
        return "high"
    if raw in {"direct_artifact", "direct"}:
        return "medium"
    if raw in {"event_log", "fallback", "inferred"}:
        return "low"
    return "low"


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def compute_evidence_completeness(story_input: Dict[str, Any]) -> Dict[str, Any]:
    obj = dict(story_input or {})
    required_sections = [
        "market_context_human",
        "scanner_reason_human",
        "filters_human",
        "monitor_reason_human",
        "guard_reason_human",
        "execution_outcome_human",
        "operator_conclusion_human",
    ]
    present_sections: List[str] = []
    missing_sections: List[str] = []
    for key in required_sections:
        value = obj.get(key)
        if isinstance(value, dict) and (_is_present(value.get("summary")) or _is_present(value.get("bullets"))):
            present_sections.append(key)
        elif _is_present(value):
            present_sections.append(key)
        else:
            missing_sections.append(key)
    score = float(len(present_sections)) / float(len(required_sections)) if required_sections else 1.0
    return {
        "required_sections": required_sections,
        "present_sections": present_sections,
        "missing_sections": missing_sections,
        "completeness_score": score,
    }


def _safe_path_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_ref_map(values: Any) -> Dict[str, str]:
    if not isinstance(values, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in values.items():
        out[str(key)] = _safe_path_text(value)
    return out


def _resolve_commander_source_ref(refs: Dict[str, Any], section_provenance: Dict[str, Any]) -> str:
    ref_map = _safe_ref_map(refs)
    section_map = dict(section_provenance or {})
    return str(
        ref_map.get("canonical_commander_json")
        or ref_map.get("canonical_commander")
        or (section_map.get("market_context_human") or {}).get("artifact_path")
        or (section_map.get("operator_conclusion_human") or {}).get("artifact_path")
        or ""
    )


def _commander_reasoning_flag(source: Dict[str, Any], commander_summary: Dict[str, Any], key: str) -> bool:
    summary_obj = dict(commander_summary or {})
    if key in summary_obj and isinstance(summary_obj.get(key), bool):
        return bool(summary_obj.get(key))
    latest_provenance = source.get("latest_reasoning_trace_provenance")
    if isinstance(latest_provenance, dict) and key in latest_provenance and isinstance(latest_provenance.get(key), bool):
        return bool(latest_provenance.get(key))
    commander_obj = source.get("commander")
    if isinstance(commander_obj, dict) and key in commander_obj and isinstance(commander_obj.get(key), bool):
        return bool(commander_obj.get(key))
    return False


def _commander_reasoning_source_priority(source: Dict[str, Any], commander_summary: Dict[str, Any]) -> List[str]:
    summary_obj = dict(commander_summary or {})
    latest_provenance = source.get("latest_reasoning_trace_provenance") if isinstance(source.get("latest_reasoning_trace_provenance"), dict) else {}
    commander_obj = source.get("commander") if isinstance(source.get("commander"), dict) else {}
    for candidate in (latest_provenance, commander_obj, summary_obj):
        values = [str(x or "").strip() for x in list(candidate.get("source_priority") or []) if str(x or "").strip()]
        if values:
            return values
    return []


def build_commander_evidence(commander_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(commander_payload or {})
    return {
        "schema_version": "commander_evidence.v1",
        "session_type": str(payload.get("session_type") or ""),
        "market_regime_summary": str(payload.get("market_regime_summary") or ""),
        "goal": str(payload.get("goal") or ""),
        "decision_path": str(payload.get("final_runtime_path") or payload.get("path") or ""),
        "invocation_plan": [str(x or "") for x in list(payload.get("agent_invocation_plan") or []) if str(x or "").strip()],
        "final_reason": str(payload.get("final_reason") or payload.get("reason") or ""),
    }


def build_lifecycle_bundle(
    *,
    day: str,
    trade_id: str,
    run_id: str,
    symbol: str,
    lifecycle: Dict[str, Any],
    strategist_summary: Dict[str, Any],
    scanner_summary: Dict[str, Any],
    monitor_summary: Dict[str, Any],
    commander_summary: Dict[str, Any],
    story_input: Dict[str, Any],
    diagnostics: Dict[str, Any],
    canonical_refs: Dict[str, Any],
    llm_refs: Dict[str, Any],
    artifact_links: Dict[str, Any],
) -> Dict[str, Any]:
    lifecycle_obj = dict(lifecycle or {})
    entry_obj = dict(lifecycle_obj.get("entry") or {})
    holding_obj = dict(lifecycle_obj.get("holding") or {})
    exit_obj = dict(lifecycle_obj.get("exit") or {})
    summary_obj = dict(lifecycle_obj.get("summary") or {})
    hold_events = [
        dict(row)
        for row in list(holding_obj.get("holding_events") or [])
        if isinstance(row, dict)
    ]
    if not hold_events and isinstance(holding_obj.get("posture_history"), list):
        hold_events = [
            dict(row)
            for row in list(holding_obj.get("posture_history") or [])
            if isinstance(row, dict)
        ]
    completeness = compute_evidence_completeness(story_input)
    shared_facts = resolve_shared_trade_facts(story_input)
    exit_reason = (
        str(summary_obj.get("exit_reason_human") or "")
        or str((exit_obj.get("monitor_context") or {}).get("exit_reason") or "")
        or str(exit_obj.get("reason_human") or "")
    )
    entry_reason = (
        str(summary_obj.get("entry_reason_human") or "")
        or str(entry_obj.get("reason_human") or "")
        or str((story_input.get("entry_reason_human") or {}).get("summary") or "")
    )
    monitor_snapshot = dict(story_input.get("monitor_reason_human") or {})
    same_day_reporter_linkage = dict(story_input.get("same_day_reporter_linkage") or lifecycle_obj.get("same_day_reporter_linkage") or {})
    execution_details = dict(story_input.get("execution_details") or lifecycle_obj.get("execution_details") or {})
    entry_execution_details = dict(
        story_input.get("entry_execution_details")
        or (entry_obj.get("execution_details") if isinstance(entry_obj.get("execution_details"), dict) else {})
        or {}
    )
    exit_execution_details = dict(
        story_input.get("exit_execution_details")
        or (exit_obj.get("execution_details") if isinstance(exit_obj.get("execution_details"), dict) else {})
        or {}
    )
    failure_classification = dict(story_input.get("failure_classification") or lifecycle_obj.get("failure_classification") or {})
    derived_reasoning_trace = build_reasoning_trace_from_summaries(
        commander_summary=dict(commander_summary or {}),
        strategist_summary=dict(strategist_summary or {}),
        scanner_summary=dict(scanner_summary or {}),
        monitor_summary=dict(monitor_summary or {}),
        market_context_human=dict(story_input.get("market_context_human") or {}),
        scanner_reason_human=dict(story_input.get("scanner_reason_human") or {}),
        monitor_reason_human=dict(story_input.get("monitor_reason_human") or {}),
        operator_conclusion_human=dict(story_input.get("operator_conclusion_human") or {}),
    )
    reasoning_trace = normalize_reasoning_trace_aliases(story_input, fallback=derived_reasoning_trace)
    section_provenance = dict(story_input.get("section_provenance") or {})
    evidence_provenance = dict(story_input.get("evidence_provenance") or {})
    refs = _safe_ref_map({**dict(canonical_refs or {}), **dict(artifact_links or {})})
    commander_source_priority = _commander_reasoning_source_priority(story_input, dict(commander_summary or {}))
    derived_reasoning_provenance = build_reasoning_provenance(
        commander_context_source="canonical" if refs.get("canonical_commander_json") or refs.get("canonical_commander") else str(evidence_provenance.get("commander") or ""),
        strategist_plan_source=str(
            (section_provenance.get("market_context_human") or {}).get("source")
            or evidence_provenance.get("strategist")
            or ("canonical" if refs.get("canonical_strategist_json") or refs.get("canonical_strategist") else "")
        ),
        scanner_reason_source=str(
            (section_provenance.get("scanner_reason_human") or {}).get("source")
            or evidence_provenance.get("scanner")
            or ("canonical" if refs.get("canonical_scanner_json") or refs.get("canonical_scanner") else "")
        ),
        monitor_reason_source=str(
            (section_provenance.get("monitor_reason_human") or {}).get("source")
            or evidence_provenance.get("monitor")
            or ("canonical" if refs.get("canonical_monitor_json") or refs.get("canonical_monitor") else "")
        ),
        commander_source_ref=_resolve_commander_source_ref(refs, section_provenance),
        strategist_source_ref=str(
            refs.get("canonical_strategist_json")
            or refs.get("canonical_strategist")
            or (section_provenance.get("market_context_human") or {}).get("artifact_path")
            or ""
        ),
        scanner_source_ref=str(
            refs.get("canonical_scanner_json")
            or refs.get("canonical_scanner")
            or (section_provenance.get("scanner_reason_human") or {}).get("artifact_path")
            or ""
        ),
        monitor_source_ref=str(
            refs.get("canonical_monitor_json")
            or refs.get("canonical_monitor")
            or (section_provenance.get("monitor_reason_human") or {}).get("artifact_path")
            or ""
        ),
        shadow_used=_commander_reasoning_flag(story_input, dict(commander_summary or {}), "shadow_used"),
        strategist_fallback_used=(
            _commander_reasoning_flag(story_input, dict(commander_summary or {}), "strategist_fallback_used")
            or bool((strategist_summary or {}).get("strategist_fallback_used"))
        ),
        source_priority=commander_source_priority,
    )
    reasoning_provenance = normalize_reasoning_provenance_aliases(
        story_input,
        fallback=derived_reasoning_provenance,
    )
    top_level_entry = dict(entry_obj)
    if not top_level_entry:
        top_level_entry = {"available": False}
    top_level_entry.setdefault("available", bool(entry_obj))
    if entry_reason:
        top_level_entry.setdefault("summary", str(entry_reason))
    if symbol:
        top_level_entry.setdefault("symbol", str(symbol))

    top_level_exit = dict(exit_obj)
    if not top_level_exit:
        top_level_exit = {"available": False}
    top_level_exit.setdefault("available", bool(exit_obj))
    if exit_reason:
        top_level_exit.setdefault("summary", str(exit_reason))
    if symbol:
        top_level_exit.setdefault("symbol", str(symbol))
    return {
        "schema_version": "lifecycle_bundle.v1",
        "day": str(day or ""),
        "trade_id": str(trade_id or ""),
        "symbol": str(symbol or ""),
        "run_id": str(run_id or ""),
        "entry": top_level_entry,
        "exit": top_level_exit,
        "shared_facts": dict(shared_facts or {}),
        "news_symbol_linkage": dict(story_input.get("news_symbol_linkage") or {}),
        "strategist_feedback_input": dict(story_input.get("strategist_feedback_input") or {}),
        "lifecycle": {
            "entry": entry_obj,
            "hold": hold_events,
            "exit": exit_obj,
        },
        "strategist_summary": dict(strategist_summary or {}),
        "scanner_summary": dict(scanner_summary or {}),
        "monitor_summary": dict(monitor_summary or {}),
        "commander_summary": dict(commander_summary or {}),
        "reasoning_trace": reasoning_trace,
        "reasoning_provenance": reasoning_provenance,
        "trade_outcome": {
            "pnl": monitor_snapshot.get("pnl"),
            "return_pct": monitor_snapshot.get("current_drawdown"),
            "holding_time": str(summary_obj.get("holding_duration") or ""),
            "exit_reason": str(exit_reason or ""),
        },
        "hold_duration": str(
            summary_obj.get("holding_duration")
            or holding_obj.get("hold_duration")
            or story_input.get("hold_duration")
            or ""
        ),
        "hold_duration_sec": (
            holding_obj.get("hold_duration_sec")
            if holding_obj.get("hold_duration_sec") is not None
            else story_input.get("hold_duration_sec")
        ),
        "holding_phase_summary": str(
            holding_obj.get("holding_phase_summary")
            or story_input.get("holding_phase_summary")
            or ""
        ),
        "hold_events_count": (
            holding_obj.get("hold_events_count")
            if holding_obj.get("hold_events_count") is not None
            else story_input.get("hold_events_count")
            if story_input.get("hold_events_count") is not None
            else len(hold_events)
        ),
        "monitor_context_snapshots": [
            dict(row)
            for row in list(
                holding_obj.get("monitor_context_snapshots")
                or story_input.get("monitor_context_snapshots")
                or []
            )
            if isinstance(row, dict)
        ][:20],
        "hold_signal_transitions": [
            dict(row)
            for row in list(
                holding_obj.get("hold_signal_transitions")
                or story_input.get("hold_signal_transitions")
                or []
            )
            if isinstance(row, dict)
        ][:20],
        "pre_exit_context_summary": dict(
            holding_obj.get("pre_exit_context_summary")
            or story_input.get("pre_exit_context_summary")
            or {}
        ),
        "same_day_reporter_linkage": same_day_reporter_linkage,
        "execution_details": execution_details,
        "entry_execution_details": entry_execution_details,
        "exit_execution_details": exit_execution_details,
        "failure_classification": failure_classification,
        "evidence_summary": {
            "completeness_score": float(completeness.get("completeness_score") or 0.0),
            "missing_sections": [str(x or "") for x in list(completeness.get("missing_sections") or []) if str(x or "").strip()],
        },
        "llm_summary": {
            "strategist_llm_status": str(diagnostics.get("strategist_llm_status") or "skipped"),
            "brief_llm_status": str(diagnostics.get("llm_brief_status") or "skipped"),
            "ai_report_status": str(diagnostics.get("ai_trade_report_status") or "skipped"),
        },
        "refs": {
            "canonical_refs": _safe_ref_map(canonical_refs),
            "llm_refs": _safe_ref_map(llm_refs),
            "artifact_links": _safe_ref_map(artifact_links),
        },
        "missing": {
            "entry_missing": not bool(entry_obj),
            "hold_missing": not bool(hold_events),
            "exit_missing": not bool(exit_obj),
        },
    }


def _section_source_entry(
    *,
    source: str,
    artifact_path: str = "",
) -> Dict[str, str]:
    return {
        "source": str(source or "fallback"),
        "artifact_path": str(artifact_path or ""),
        "confidence": _source_confidence_label(source),
    }


def build_section_provenance(bundle_out: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    artifacts = bundle_out.get("artifacts") if isinstance(bundle_out.get("artifacts"), dict) else {}
    evidence_provenance = (
        bundle_out.get("evidence_provenance") if isinstance(bundle_out.get("evidence_provenance"), dict) else {}
    )

    def _agent_source(agent: str) -> str:
        return str(evidence_provenance.get(agent) or "fallback").strip().lower()

    def _agent_path(agent: str) -> str:
        canonical_key = f"canonical_{agent}_json"
        canonical_path = str(artifacts.get(canonical_key) or "").strip()
        if canonical_path:
            return canonical_path
        if agent == "reporter":
            return str(artifacts.get("reporter_analysis_json") or "").strip()
        return str(artifacts.get("agent_pipeline_trace_json") or "").strip()

    strategist_entry = _section_source_entry(
        source=_agent_source("strategist"),
        artifact_path=_agent_path("strategist"),
    )
    scanner_entry = _section_source_entry(
        source=_agent_source("scanner"),
        artifact_path=_agent_path("scanner"),
    )
    monitor_entry = _section_source_entry(
        source=_agent_source("monitor"),
        artifact_path=_agent_path("monitor"),
    )
    supervisor_entry = _section_source_entry(
        source=_agent_source("supervisor"),
        artifact_path=_agent_path("supervisor"),
    )
    executor_entry = _section_source_entry(
        source=_agent_source("executor"),
        artifact_path=_agent_path("executor"),
    )
    reporter_entry = _section_source_entry(
        source=_agent_source("reporter"),
        artifact_path=_agent_path("reporter"),
    )
    commander_entry = _section_source_entry(
        source=_agent_source("commander"),
        artifact_path=_agent_path("commander"),
    )
    return {
        "market_context_human": strategist_entry,
        "scanner_reason_human": scanner_entry,
        "filters_human": scanner_entry,
        "monitor_reason_human": monitor_entry,
        "guard_reason_human": supervisor_entry,
        "execution_outcome_human": executor_entry,
        "reporter_status_human": reporter_entry,
        "operator_conclusion_human": commander_entry,
        "timeline": commander_entry,
    }


def slug(value: Any, *, max_len: int = 80) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_")
    if not text:
        return "item"
    return text[: max_len]


def feature_coverage(selected_candidate: Dict[str, Any]) -> Dict[str, Any]:
    feature_snapshot = (
        selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
    )
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
    present: List[str] = []
    missing: List[str] = []
    for key in keys:
        if feature_snapshot.get(key) is None:
            missing.append(key)
        else:
            present.append(key)
    return {
        "present": len(present),
        "total": len(keys),
        "present_keys": present,
        "missing_keys": missing,
    }


def normalized_feature_coverage(scanner: Dict[str, Any], selected_candidate: Dict[str, Any]) -> Dict[str, Any]:
    reported = scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {}
    computed = feature_coverage(selected_candidate)
    present = safe_int(reported.get("present"), computed.get("present"))
    total = safe_int(reported.get("total"), computed.get("total"))
    coverage_ratio = safe_float(
        reported.get("coverage_ratio"),
        (present / total) if total > 0 else 0.0,
    )
    quality = str(reported.get("quality") or "").strip().lower()
    if not quality:
        if total <= 0:
            quality = "missing"
        elif coverage_ratio >= 0.75:
            quality = "strong"
        elif coverage_ratio >= 0.5:
            quality = "partial"
        else:
            quality = "weak"
    present_keys = [str(x or "") for x in list(reported.get("present_keys") or computed.get("present_keys") or []) if str(x or "").strip()]
    missing_keys = [str(x or "") for x in list(reported.get("missing_keys") or computed.get("missing_keys") or []) if str(x or "").strip()]
    return {
        "present": present,
        "total": total,
        "coverage_ratio": coverage_ratio,
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
    }


def confidence_label(value: Any) -> str:
    score = safe_float(value, -1.0)
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    if score >= 0.0:
        return "low"
    return "not_captured"


def execution_mode_label(executor: Dict[str, Any]) -> str:
    effective_mode = str(executor.get("effective_mode") or "").strip().lower()
    broker_env = str(executor.get("broker_env") or "").strip().lower()
    execution_mode = str(executor.get("execution_mode") or executor.get("mode") or "").strip().lower()
    kiwoom_mode = str(executor.get("kiwoom_mode") or "").strip().lower()
    if "mock" in effective_mode or broker_env == "mock" or kiwoom_mode == "mock":
        return "simulation (mock broker)"
    if broker_env == "real" or effective_mode == "real_broker_http":
        return "live broker"
    if execution_mode:
        return execution_mode
    return "decision only"


def classify_story_type(execution: Dict[str, Any], executor: Dict[str, Any]) -> str:
    effective_mode = str(executor.get("effective_mode") or "").strip().lower()
    broker_env = str(executor.get("broker_env") or "").strip().lower()
    kiwoom_mode = str(executor.get("kiwoom_mode") or "").strip().lower()
    execution_attempted = bool(executor.get("execution_attempted")) or bool(execution.get("action"))
    execution_ok = bool(executor.get("execution_ok"))
    if "mock" in effective_mode or broker_env == "mock" or kiwoom_mode == "mock":
        return "simulation"
    if not execution_attempted:
        return "decision_only"
    if execution_attempted and not execution_ok:
        return "failed_execution"
    return "live_trade"


def build_story_id(day: str, execution: Dict[str, Any]) -> str:
    run_id = slug(execution.get("run_id"), max_len=48)
    symbol = slug(execution.get("symbol"), max_len=24)
    action = slug(str(execution.get("action") or "").lower(), max_len=12)
    compact_day = str(day or "").replace("-", "")
    return slug(f"{compact_day}_{symbol}_{action}_{run_id}", max_len=96)


def build_story_contract(bundle_out: Dict[str, Any]) -> Dict[str, Any]:
    execution = bundle_out.get("execution") if isinstance(bundle_out.get("execution"), dict) else {}
    executor = bundle_out.get("executor") if isinstance(bundle_out.get("executor"), dict) else {}
    story_type = classify_story_type(execution, executor)
    mode_label = execution_mode_label(executor)
    story_anchor = (
        f"{execution.get('action') or 'WAIT'} {execution.get('symbol') or (bundle_out.get('scanner') or {}).get('top_stock') or '-'} "
        f"x{execution.get('qty') or 0} | run {bundle_out.get('run_id') or '-'}"
    )
    warnings: List[str] = []
    if story_type == "failed_execution":
        warnings.append("Execution was attempted but did not complete successfully.")
    if story_type == "simulation":
        warnings.append("This story reflects simulation mode, not a live broker fill.")
    return {
        "story_available": bool(execution.get("action") or execution.get("symbol") or (bundle_out.get("scanner") or {}).get("top_stock")),
        "story_type": story_type,
        "execution_mode_label": mode_label,
        "story_anchor": story_anchor,
        "warnings": warnings,
    }


def build_market_context_human(strategist: Dict[str, Any]) -> Dict[str, Any]:
    llm_parsed = strategist.get("llm_parsed_output") if isinstance(strategist.get("llm_parsed_output"), dict) else {}
    input_summary = strategist.get("input_summary") if isinstance(strategist.get("input_summary"), dict) else {}
    fear_index = strategist.get("fear_index") if isinstance(strategist.get("fear_index"), dict) else {}
    macro_overlay = strategist.get("macro_stress_overlay") if isinstance(strategist.get("macro_stress_overlay"), dict) else {}
    macro_moves = strategist.get("global_macro_moves") if isinstance(strategist.get("global_macro_moves"), dict) else {}
    news_context = strategist.get("news_context") if isinstance(strategist.get("news_context"), dict) else {}
    regime = str(llm_parsed.get("market_regime") or strategist.get("market_regime") or "not_captured")
    sentiment_state = str(llm_parsed.get("market_sentiment") or strategist.get("market_sentiment") or strategist.get("global_sentiment_status") or "not_captured")
    playbook = str(strategist.get("playbook") or llm_parsed.get("playbook") or "not_captured")
    themes = [str(x or "") for x in list(strategist.get("themes") or []) if str(x or "").strip()][:4]
    global_sentiment_score = strategist.get("global_sentiment_score")
    if global_sentiment_score in (None, ""):
        global_sentiment_score = input_summary.get("global_sentiment_score")
    if not fear_index and input_summary:
        fear_index = {
            "level": input_summary.get("vix_level"),
            "change_pct": input_summary.get("vix_change_pct"),
            "level_pressure": input_summary.get("vix_level_pressure"),
        }
    if not macro_moves and input_summary:
        macro_moves = {
            "vix_level": input_summary.get("vix_level"),
            "vix_pct": input_summary.get("vix_change_pct"),
            "vix_level_pressure": input_summary.get("vix_level_pressure"),
        }
    vix_level = (
        fear_index.get("level")
        if fear_index
        else macro_moves.get("vix_level")
        if macro_moves
        else macro_overlay.get("vix_level")
        if macro_overlay
        else input_summary.get("vix_level")
    )
    dxy_pct = (
        macro_moves.get("dxy_pct")
        if macro_moves
        else macro_overlay.get("dxy_pct")
        if macro_overlay
        else None
    )
    news_total = safe_int(
        news_context.get("headline_count"),
        safe_int(
            strategist.get("market_news_total_headlines"),
            safe_int(strategist.get("news_total_headlines"), safe_int(input_summary.get("headline_count"), 0)),
        ),
    )
    query_targets = _list_text(
        strategist.get("news_query_targets") or input_summary.get("news_query_targets") or [],
        limit=8,
        max_len=80,
    )
    query_count = safe_int(
        strategist.get("market_news_query_count"),
        safe_int(strategist.get("news_symbol_count"), len(query_targets)),
    )
    market_signal_total = safe_int(news_context.get("market_signal_total"), safe_int(input_summary.get("market_signal_total"), 0))
    candidate_signal_total = safe_int(news_context.get("candidate_signal_total"), safe_int(input_summary.get("candidate_signal_total"), 0))
    stress_flags = [str(x or "") for x in list(macro_overlay.get("stress_flags") or []) if str(x or "").strip()]
    defensive_mode = bool(macro_overlay.get("active")) or bool(stress_flags) or (safe_float(vix_level, 0.0) >= 25.0)
    market_news_titles = _list_text(input_summary.get("market_news_titles"), limit=3, max_len=140)
    candidate_news_titles = _list_text(input_summary.get("candidate_news_titles"), limit=3, max_len=140)
    key_events_hint = _list_text(input_summary.get("key_events_hint"), limit=5, max_len=180)
    strategist_evidence_trace = _build_strategist_evidence_trace(
        strategist,
        fallback_market_titles=market_news_titles,
        fallback_candidate_titles=candidate_news_titles,
    )
    candidate_hints = _list_text(
        strategist_evidence_trace.get("candidate_hints"),
        limit=8,
        max_len=24,
    )
    market_headlines = _list_text(
        strategist_evidence_trace.get("market_headlines"),
        limit=3,
        max_len=180,
    ) or market_news_titles
    symbol_headlines = _list_text(
        strategist_evidence_trace.get("symbol_headlines"),
        limit=3,
        max_len=180,
    ) or candidate_news_titles
    global_sentiment_signal = (
        dict(strategist_evidence_trace.get("global_sentiment_signal") or {})
        if isinstance(strategist_evidence_trace.get("global_sentiment_signal"), dict)
        else {}
    )
    fear_index_trace = (
        dict(strategist_evidence_trace.get("fear_index") or {})
        if isinstance(strategist_evidence_trace.get("fear_index"), dict)
        else dict(fear_index or {})
    )
    key_events = _list_text(strategist_evidence_trace.get("key_events"), limit=6, max_len=180) or key_events_hint
    news_summary = (
        f"{news_total} headlines were considered across {query_count} targets "
        f"({market_signal_total} market / {candidate_signal_total} candidate signals)."
        if news_total > 0
        else "No strong news input was captured for this run."
    )
    stress_summary = (
        f"Macro stress was elevated because {', '.join(stress_flags)} remained active."
        if stress_flags
        else "No explicit macro stress flags were active in the strategist frame."
    )
    summary = (
        f"Market regime was {regime} with a {playbook} playbook. "
        f"Global sentiment scored {format_pct(global_sentiment_score)} and VIX was {format_pct(vix_level)}. "
        f"{stress_summary} {news_summary}"
    )
    bullets = [
        f"Market regime: {regime}",
        f"Market sentiment: {sentiment_state}",
        f"Playbook: {playbook}",
        f"Global sentiment score: {format_pct(global_sentiment_score)}",
        f"VIX / fear index level: {format_pct(vix_level)}",
        f"Dollar index move: {format_pct(dxy_pct)}%",
        f"Themes detected: {', '.join(themes) if themes else 'none captured'}",
        f"Defensive mode: {'enabled' if defensive_mode else 'not enabled'}",
        f"News input: {news_summary}",
    ]
    if query_targets:
        bullets.append(f"News query targets: {', '.join(query_targets)}")
    if key_events_hint:
        bullets.append("Key strategist inputs: " + "; ".join(key_events_hint[:3]))
    if candidate_hints:
        bullets.append("Strategist candidate hints: " + ", ".join(candidate_hints[:5]))
    if market_headlines:
        bullets.append("Strategist market headlines: " + "; ".join(market_headlines[:3]))
    if symbol_headlines:
        bullets.append("Strategist symbol headlines: " + "; ".join(symbol_headlines[:3]))
    return {
        "regime": regime,
        "market_sentiment": sentiment_state,
        "playbook": playbook,
        "themes": themes,
        "global_sentiment_score": global_sentiment_score,
        "global_sentiment_signal": global_sentiment_signal,
        "vix_level": vix_level,
        "fear_index": fear_index_trace,
        "stress_flags": stress_flags,
        "defensive_mode": defensive_mode,
        "headline_count": news_total,
        "news_query_count": query_count,
        "market_signal_total": market_signal_total,
        "candidate_signal_total": candidate_signal_total,
        "news_query_targets": query_targets,
        "key_events_hint": key_events_hint,
        "key_events": key_events,
        "candidate_hints": candidate_hints,
        "market_headlines": market_headlines,
        "symbol_headlines": symbol_headlines,
        "market_news_titles": market_headlines or market_news_titles,
        "candidate_news_titles": symbol_headlines or candidate_news_titles,
        "strategist_evidence_trace": strategist_evidence_trace,
        "news_input_summary": news_summary,
        "summary": summary,
        "bullets": bullets,
    }


def build_scanner_reason_human(scanner: Dict[str, Any], strategist: Dict[str, Any]) -> Dict[str, Any]:
    selected = scanner.get("selected_candidate") if isinstance(scanner.get("selected_candidate"), dict) else {}
    selected_symbol = str(selected.get("symbol") or scanner.get("top_stock") or "").strip()
    ranking_table = [dict(row) for row in list(scanner.get("ranking_table") or []) if isinstance(row, dict)]
    top_ranked_symbols = [str(row.get("symbol") or "").strip() for row in ranking_table if str(row.get("symbol") or "").strip()]
    if not top_ranked_symbols:
        top_ranked_symbols = [str(x or "") for x in list(scanner.get("top_ranked_symbols") or []) if str(x or "").strip()]
    selected_rank = 0
    selected_row = next(
        (row for row in ranking_table if str(row.get("symbol") or "").strip() == selected_symbol),
        {},
    )
    if selected_row:
        selected_rank = safe_int(selected_row.get("rank"), 0)
    elif selected_symbol and selected_symbol in top_ranked_symbols:
        selected_rank = int(top_ranked_symbols.index(selected_symbol) + 1)
    elif selected_symbol:
        selected_rank = 1
    universe_size = max(
        0,
        safe_int(scanner.get("universe_size"), 0)
        or safe_int(scanner.get("candidate_pool_after_filter"), 0)
        or safe_int(scanner.get("candidate_pool_before_filter"), 0)
        or len(ranking_table)
        or len(top_ranked_symbols),
    )
    selected_sources = [str(x or "") for x in list(selected.get("sources") or []) if str(x or "").strip()]
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    preview_map = {
        str(row.get("symbol") or "").strip(): dict(row)
        for row in list(scanner.get("candidate_preview") or [])
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    }
    basis: List[str] = []
    if safe_float(score_breakdown.get("trading_value"), 0.0) > 0:
        basis.append("trading value")
    if safe_float(score_breakdown.get("volume_surge"), 0.0) > 0 or "top_volume" in selected_sources:
        basis.append("turnover and volume")
    if safe_float(score_breakdown.get("theme_boost"), 0.0) > 0 or "sector_theme" in selected_sources:
        basis.append("theme and sector alignment")
    if safe_float(score_breakdown.get("sentiment"), 0.0) > 0:
        basis.append("sentiment support")
    if not basis:
        basis.append("combined scanner ranking score")
    coverage = normalized_feature_coverage(scanner, selected)
    selected_score = selected.get("score_total")
    if selected_score in (None, ""):
        selected_score = selected_row.get("score_total")
    selected_risk = selected.get("risk_score")
    if selected_risk in (None, ""):
        selected_risk = selected_row.get("risk_score")
    selected_confidence = selected.get("confidence")
    if selected_confidence in (None, ""):
        selected_confidence = selected_row.get("confidence")
    top_reasons: List[str] = [
        f"highest combined scanner score ({safe_float(selected_score, 0.0):.3f})",
        f"selected from {', '.join(selected_sources) if selected_sources else 'captured scanner sources'}",
        f"chart feature coverage {coverage['present']}/{coverage['total']}" if coverage["total"] > 0 else "chart feature coverage was not captured",
        f"aligned with strategist playbook {strategist.get('playbook') or 'not_captured'}",
    ]
    runner_ups: List[Dict[str, Any]] = []
    ranked_preview = ranking_table[:3] if ranking_table else []
    for row in ranked_preview:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol or symbol == selected_symbol:
            continue
        preview = preview_map.get(symbol, {})
        why_parts: List[str] = []
        preview_why = clip(preview.get("why") or row.get("why"), max_len=140)
        if preview_why:
            why_parts.append(preview_why)
        score_gap = None
        if selected_score not in (None, "") and row.get("score_total") not in (None, ""):
            score_gap = safe_float(selected_score, 0.0) - safe_float(row.get("score_total"), 0.0)
            why_parts.append(f"score gap {score_gap:.3f}")
        row_risk = row.get("risk_score")
        if selected_risk not in (None, "") and row_risk not in (None, "") and safe_float(row_risk, 0.0) > safe_float(selected_risk, 0.0):
            why_parts.append(
                f"higher risk ({safe_float(row_risk, 0.0):.3f} vs {safe_float(selected_risk, 0.0):.3f})"
            )
        row_confidence = row.get("confidence")
        if selected_confidence not in (None, "") and row_confidence not in (None, "") and safe_float(row_confidence, 0.0) < safe_float(selected_confidence, 0.0):
            why_parts.append(
                f"lower confidence ({safe_float(row_confidence, 0.0):.3f} vs {safe_float(selected_confidence, 0.0):.3f})"
            )
        runner_ups.append(
            {
                "symbol": symbol,
                "rank": safe_int(row.get("rank"), 0),
                "score_total": row.get("score_total"),
                "risk_score": row.get("risk_score"),
                "confidence": row.get("confidence"),
                "why": "; ".join(why_parts) if why_parts else "lower final ranking than the selected symbol",
            }
        )
        if len(runner_ups) >= 2:
            break
    top_candidates: List[Dict[str, Any]] = []
    for row in ranked_preview:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        top_candidates.append(
            {
                "rank": safe_int(row.get("rank"), 0),
                "symbol": symbol,
                "score_total": row.get("score_total"),
                "risk_score": row.get("risk_score"),
                "confidence": row.get("confidence"),
            }
        )
    bullets = [
        f"Universe scanned: {universe_size}",
        f"Selected rank: #{selected_rank}" if selected_rank else "Selected rank: not_captured",
        f"Ranking basis: {', '.join(basis)}",
        f"Selected because: {top_reasons[0]}",
        f"Selection sources: {', '.join(selected_sources) if selected_sources else 'not captured'}",
        f"Chart / feature coverage: {coverage['present']}/{coverage['total']}" if coverage["total"] else "Chart / feature coverage: not captured",
    ]
    if top_candidates:
        bullets.append(
            "Top candidates: "
            + "; ".join(
                f"#{safe_int(row.get('rank'), 0)} {row.get('symbol')} score {safe_float(row.get('score_total'), 0.0):.3f}"
                for row in top_candidates
            )
        )
    if runner_ups:
        bullets.append("Why not others: " + "; ".join(f"{row['symbol']} was weaker because {row['why']}" for row in runner_ups))
    scanner_selection_trace = _build_scanner_selection_trace(
        {
            "selected_symbol": selected_symbol,
            "selected_rank": selected_rank,
            "top_candidates": top_candidates,
            "score_breakdown": score_breakdown,
            "selection_basis": "; ".join(top_reasons[:3]) if top_reasons else "",
            "summary": (
                f"Scanner selected {selected_symbol or '-'} as rank #{selected_rank or 1} out of {universe_size or 0} candidates."
            ),
        },
        scanner,
    )
    return {
        "selected_symbol": selected_symbol,
        "selected_rank": selected_rank,
        "universe_size": universe_size,
        "selected_score": selected_score,
        "selected_sources": selected_sources,
        "source_scores": selected.get("source_scores") if isinstance(selected.get("source_scores"), dict) else {},
        "score_breakdown": score_breakdown,
        "ranking_basis": basis,
        "confidence": selected_confidence,
        "confidence_label": confidence_label(selected_confidence),
        "top_reasons": top_reasons,
        "top_candidates": top_candidates,
        "runner_ups": runner_ups,
        "ranked_candidates": list(scanner_selection_trace.get("ranked_candidates") or [])[:5],
        "selection_reason": clip(scanner_selection_trace.get("selection_reason"), max_len=260),
        "selected_symbol_score_drivers": dict(scanner_selection_trace.get("selected_symbol_score_drivers") or {}),
        "scanner_selection_trace": dict(scanner_selection_trace or {}),
        "summary": (
            f"Scanner selected {selected_symbol or '-'} as rank #{selected_rank or 1} out of {universe_size or 0} candidates "
            f"with score {safe_float(selected_score, 0.0):.3f} because it led on {', '.join(basis[:3])}."
        ),
        "comparison": (
            f"{selected_symbol} ranked #{selected_rank} out of {universe_size} because it had the strongest overall blend of "
            f"{', '.join(basis[:3])}."
            if selected_symbol
            else "Scanner did not record a selected symbol for this run."
        ),
        "bullets": bullets,
    }


def enrich_scanner_reason_from_evidence(
    scanner_reason_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(scanner_reason_human or {})
    evidence = scanner_evidence if isinstance(scanner_evidence, dict) else {}
    reason_rows = [dict(row) for row in list(evidence.get("candidate_selection_reasons") or []) if isinstance(row, dict)]
    payload = (
        reason_rows[0].get("payload")
        if reason_rows and isinstance(reason_rows[0].get("payload"), dict)
        else {}
    )
    if not isinstance(payload, dict):
        payload = {}

    why_selected = [str(x or "") for x in list(payload.get("why_selected") or []) if str(x or "").strip()][:4]
    selection_basis = clip(payload.get("final_decision_basis"), max_len=260)
    tie_break_rule = clip(payload.get("tie_break_rule"), max_len=180)
    runner_ups_lost: List[Dict[str, Any]] = []
    for row in list(payload.get("runner_ups_lost") or payload.get("runner_up_reasons") or []):
        if not isinstance(row, dict):
            continue
        symbol = clip(row.get("symbol"), max_len=24)
        why_lost = [
            clip(x, max_len=140)
            for x in list(row.get("why_lost") or row.get("lost_because") or [])
            if clip(x, max_len=140)
        ][:4]
        summary = clip(row.get("summary") or "; ".join(why_lost), max_len=240)
        if not symbol and not summary:
            continue
        runner_ups_lost.append(
            {
                "symbol": symbol,
                "why_lost": why_lost,
                "summary": summary,
            }
        )
        if len(runner_ups_lost) >= 3:
            break

    selected_symbol = str(out.get("selected_symbol") or "").strip()
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

    if why_selected:
        out["why_selected"] = why_selected
    if selection_basis:
        out["selection_basis"] = selection_basis
    if tie_break_rule:
        out["tie_break_rule"] = tie_break_rule
    if runner_ups_lost:
        out["runner_ups_lost"] = runner_ups_lost

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    if coverage:
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        updated_bullets: List[str] = []
        replaced_chart_bullet = False
        for bullet in bullets:
            if bullet.lower().startswith("chart / feature coverage:"):
                updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                replaced_chart_bullet = True
            else:
                updated_bullets.append(bullet)
        if not replaced_chart_bullet and present > 0 and total > 0:
            updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
        bullets = updated_bullets
    if why_selected:
        bullets.append("Selection decision: " + "; ".join(why_selected))
    if selection_basis:
        bullets.append(f"Final decision basis: {selection_basis}")
    if tie_break_rule:
        bullets.append(f"Tie-break rule: {tie_break_rule}")
    if runner_ups_lost:
        bullets.append(
            "Runner-ups lost because: "
            + "; ".join(
                f"{row.get('symbol')}: {row.get('summary')}" for row in runner_ups_lost if row.get("symbol")
            )
        )
    if bullets:
        deduped: List[str] = []
        seen: set[str] = set()
        for bullet in bullets:
            if bullet not in seen:
                deduped.append(bullet)
                seen.add(bullet)
        out["bullets"] = deduped[:12]
    return out


def _normalized_feature_coverage_from_scanner_evidence(
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip()
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
        row_symbol = str(row.get("symbol") or "").strip()
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


def enrich_filters_from_evidence(
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
    coverage_quality = str(coverage.get("quality") or "").strip().lower() or "missing"
    if total <= 0:
        chart_status = "NOT_AVAILABLE"
        chart_note = "feature snapshot not available"
    elif present >= 8:
        chart_status = "PASS"
        chart_note = f"{present}/{total} captured chart features"
    elif present >= 4:
        chart_status = "PARTIAL"
        chart_note = f"{present}/{total} captured chart features"
    else:
        chart_status = "FAIL"
        chart_note = f"{present}/{total} captured chart features"

    summary = str(out.get("summary") or "").strip()
    if summary:
        summary = re.sub(
            r"Chart completeness was [^.]*(?:\.)?",
            f"Chart completeness was {coverage_quality} with {present}/{total} captured features.",
            summary,
            flags=re.IGNORECASE,
        )
    else:
        summary = (
            "Scanner and guard checks were captured. "
            f"Chart completeness was {coverage_quality} with {present}/{total} captured features."
        )
    out["summary"] = summary

    checks = [dict(x) for x in list(out.get("checks") or []) if isinstance(x, dict)]
    updated_checks: List[Dict[str, Any]] = []
    replaced_check = False
    for check in checks:
        name = str(check.get("name") or "").strip().lower()
        if name == "chart completeness filter":
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


def build_filters_human(scanner: Dict[str, Any], strategist: Dict[str, Any], supervisor: Dict[str, Any]) -> Dict[str, Any]:
    selected = scanner.get("selected_candidate") if isinstance(scanner.get("selected_candidate"), dict) else {}
    sources = [str(x or "") for x in list(selected.get("sources") or []) if str(x or "").strip()]
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    components = selected.get("component_snapshot") if isinstance(selected.get("component_snapshot"), dict) else {}
    coverage = normalized_feature_coverage(scanner, selected)
    checks: List[Dict[str, str]] = []

    def add_check(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    liquidity_pass = "top_value" in sources or safe_float(components.get("trading_value_component"), 0.0) > 0
    turnover_pass = "top_volume" in sources or safe_float(score_breakdown.get("volume_surge"), 0.0) > 0
    theme_pass = "sector_theme" in sources or safe_float(score_breakdown.get("theme_boost"), 0.0) > 0 or bool(strategist.get("themes"))
    if coverage["total"] <= 0:
        chart_status = "NOT_AVAILABLE"
    elif coverage["present"] >= 8:
        chart_status = "PASS"
    elif coverage["present"] >= 4:
        chart_status = "PARTIAL"
    else:
        chart_status = "FAIL"
    sentiment_gate = safe_float(components.get("sentiment_component"), 0.0) >= 0 or safe_float(
        strategist.get("global_sentiment_score"),
        0.0,
    ) > -0.35
    risk_gate = bool(supervisor.get("supervisor_allow")) and safe_float(selected.get("risk_score"), 0.0) <= 1.0

    add_check("liquidity filter", "PASS" if liquidity_pass else "FAIL", "top value or trading-value input supported the selection")
    add_check("turnover filter", "PASS" if turnover_pass else "FAIL", "top volume or turnover input supported the selection")
    add_check("sector/theme alignment", "PASS" if theme_pass else "FAIL", "theme boost or sector source matched the strategist frame")
    add_check("chart completeness filter", chart_status, f"{coverage['present']}/{coverage['total']} captured chart features")
    add_check("sentiment gate", "PASS" if sentiment_gate else "FAIL", f"news/global sentiment contribution was {safe_float(components.get('sentiment_component'), 0.0):.3f}")
    add_check("risk gate", "PASS" if risk_gate else "FAIL", f"risk score was {safe_float(selected.get('risk_score'), 0.0):.3f} and supervisor allow={bool(supervisor.get('supervisor_allow'))}")
    add_check("price anomaly filter", "NOT_AVAILABLE", "price anomaly check was not captured in this run")
    add_check("spread/slippage filter", "NOT_AVAILABLE", "spread or slippage diagnostics were not captured in this run")

    passed = sum(1 for row in checks if row["status"] == "PASS")
    bullets = [f"{row['name']}: {row['status']} - {row['detail']}" for row in checks]
    condition_status = str(scanner.get("condition_search_status") or "").strip()
    if condition_status:
        bullets.append(f"Condition search source: {condition_status} ({scanner.get('condition_search_reason') or 'no extra reason captured'})")
    coverage_quality = str(coverage.get("quality") or chart_status.lower()).strip().lower()
    return {
        "checks": checks,
        "summary": (
            f"Scanner and guard checks passed {passed} of {len(checks)} visible gates. "
            f"Chart completeness was {coverage_quality} with {coverage['present']}/{coverage['total']} captured features."
        ),
        "bullets": bullets,
    }


def build_monitor_reason_human(monitor: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper()
    decision_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    thresholds = monitor.get("thresholds") if isinstance(monitor.get("thresholds"), dict) else {}
    thresholds_guards_used = (
        decision_trace.get("thresholds_guards_used")
        if isinstance(decision_trace.get("thresholds_guards_used"), dict)
        else (
            monitor.get("thresholds_guards_used")
            if isinstance(monitor.get("thresholds_guards_used"), dict)
            else {}
        )
    )
    threshold_snapshot = (
        monitor.get("threshold_snapshot")
        if isinstance(monitor.get("threshold_snapshot"), dict)
        else {}
    )
    thresholds = _merge_missing_values(
        thresholds,
        thresholds_guards_used.get("thresholds") if isinstance(thresholds_guards_used.get("thresholds"), dict) else {},
    )
    for key in (
        "stop_loss_pct",
        "effective_stop_loss_pct",
        "effective_stop_reason",
        "take_profit_pct",
        "peak_drawdown_exit_pct",
        "trailing_stop_pct",
        "vwap_breakdown_pct",
        "intraday_low_break_pct",
        "trend_strength_floor",
    ):
        if thresholds.get(key) in (None, "", [], {}):
            thresholds[key] = monitor.get(key)
    trigger_details = monitor.get("trigger_details") if isinstance(monitor.get("trigger_details"), dict) else {}
    decision_reason_chain = [str(x or "") for x in list(monitor.get("decision_reason_chain") or []) if str(x or "").strip()]
    timing_assessment = decision_trace.get("timing_assessment") if isinstance(decision_trace.get("timing_assessment"), dict) else {}
    policy_ref = decision_trace.get("policy_ref") if isinstance(decision_trace.get("policy_ref"), dict) else {}
    received_policy = (
        monitor.get("received_policy")
        if isinstance(monitor.get("received_policy"), dict)
        else (
            threshold_snapshot.get("received_policy")
            if isinstance(threshold_snapshot.get("received_policy"), dict)
            else (
                policy_ref.get("received_policy")
                if isinstance(policy_ref.get("received_policy"), dict)
                else {}
            )
        )
    )
    effective_policy = (
        monitor.get("effective_policy")
        if isinstance(monitor.get("effective_policy"), dict)
        else (
            threshold_snapshot.get("effective_policy")
            if isinstance(threshold_snapshot.get("effective_policy"), dict)
            else (
                policy_ref.get("effective_policy")
                if isinstance(policy_ref.get("effective_policy"), dict)
                else {}
            )
        )
    )
    policy_adjustment_summary = str(
        monitor.get("policy_adjustment_summary")
        or threshold_snapshot.get("policy_adjustment_summary")
        or policy_ref.get("policy_adjustment_summary")
        or ""
    ).strip()
    effective_policy_deltas = [
        dict(row)
        for row in list(
            monitor.get("effective_policy_deltas")
            or threshold_snapshot.get("effective_policy_deltas")
            or policy_ref.get("effective_policy_deltas")
            or []
        )[:8]
        if isinstance(row, dict)
    ]
    entry_check_summary = str(decision_trace.get("entry_check_summary") or "").strip()
    entry_blockers = [str(x or "") for x in list(decision_trace.get("entry_blockers") or []) if str(x or "").strip()]
    entry_reason = str(
        timing_assessment.get("entry_reason")
        or monitor.get("entry_reason")
        or ""
    ).strip()
    entry_pattern = str(
        timing_assessment.get("entry_pattern")
        or monitor.get("entry_pattern")
        or ""
    ).strip()
    entry_signal_chain = [str(x or "") for x in list(monitor.get("entry_signal_chain") or []) if str(x or "").strip()]
    entry_condition_path = str(monitor.get("entry_condition_path") or "").strip()
    entry_condition_paths_passed = [str(x or "") for x in list(monitor.get("entry_condition_paths_passed") or []) if str(x or "").strip()]
    entry_condition_scores = monitor.get("entry_condition_scores") if isinstance(monitor.get("entry_condition_scores"), dict) else {}
    entry_grouped_logic_trace = monitor.get("entry_grouped_logic_trace") if isinstance(monitor.get("entry_grouped_logic_trace"), dict) else {}
    entry_metrics = monitor.get("entry_metrics") if isinstance(monitor.get("entry_metrics"), dict) else {}
    entry_thresholds = (
        monitor.get("entry_thresholds")
        if isinstance(monitor.get("entry_thresholds"), dict)
        else {}
    )
    if not entry_thresholds and isinstance(effective_policy, dict):
        entry_thresholds = dict(effective_policy or {})
    if not entry_thresholds and isinstance(monitor.get("applied_policy"), dict):
        entry_thresholds = dict(monitor.get("applied_policy") or {})
    if not entry_thresholds and isinstance(threshold_snapshot.get("entry_thresholds"), dict):
        entry_thresholds = dict(threshold_snapshot.get("entry_thresholds") or {})
    if not entry_thresholds and isinstance(threshold_snapshot.get("applied_policy"), dict):
        entry_thresholds = dict(threshold_snapshot.get("applied_policy") or {})
    entry_guard_blocked = bool(monitor.get("entry_guard_blocked"))
    entry_guard_reason = str(monitor.get("entry_guard_reason") or "").strip()
    entry_evaluated = bool(monitor.get("entry_evaluated"))
    entry_triggered = bool(monitor.get("entry_triggered"))
    exit_reason = str(monitor.get("exit_reason") or "").strip()
    monitor_reason = str(monitor.get("monitor_reason") or monitor.get("evaluation_summary") or "").strip()
    price_source = str(monitor.get("price_source") or "").strip()
    price_source_policy = str(monitor.get("price_source_policy") or "").strip()
    feature_source = str(monitor.get("feature_source") or "").strip()
    current_price = monitor.get("current_price")
    if current_price in (None, ""):
        current_price = monitor.get("price")
    average_price = monitor.get("average_price")
    if average_price in (None, ""):
        average_price = monitor.get("avg_price")
    peak_price = monitor.get("peak_price")
    peak_drawdown = monitor.get("peak_drawdown")
    current_drawdown = monitor.get("current_drawdown")
    vwap_distance = monitor.get("vwap_distance")
    if current_drawdown in (None, "") and current_price not in (None, "") and peak_price not in (None, ""):
        current_drawdown = (safe_float(current_price, 0.0) / max(safe_float(peak_price, 1.0), 1e-9)) - 1.0
    if current_drawdown in (None, "") and peak_drawdown not in (None, ""):
        current_drawdown = peak_drawdown

    watch_axes: List[str] = [str(x or "") for x in list(monitor.get("watch_axes") or trigger_details.get("watch_axes") or []) if str(x or "").strip()]
    if "Hard stop" not in watch_axes and (thresholds.get("hard_stop_pct") not in (None, "") or thresholds.get("stop_loss_pct") not in (None, "")):
        watch_axes.append("Hard stop")
    if "Take profit" not in watch_axes and thresholds.get("take_profit_pct") not in (None, ""):
        watch_axes.append("Take profit")
    if "Trailing stop" not in watch_axes and thresholds.get("trailing_stop_pct") not in (None, ""):
        watch_axes.append("Trailing stop")
    if "Peak drawdown" not in watch_axes and thresholds.get("peak_drawdown_exit_pct") not in (None, ""):
        watch_axes.append("Peak drawdown")
    if "VWAP breakdown" not in watch_axes and thresholds.get("vwap_breakdown_pct") not in (None, ""):
        watch_axes.append("VWAP breakdown")
    if "Intraday low break" not in watch_axes and thresholds.get("intraday_low_break_pct") not in (None, ""):
        watch_axes.append("Intraday low break")
    if "Trend breakdown" not in watch_axes and thresholds.get("trend_strength_floor") not in (None, ""):
        watch_axes.append("Trend breakdown")
    if "Volatility expansion" not in watch_axes and thresholds.get("vol_expansion_ratio") not in (None, ""):
        watch_axes.append("Volatility expansion")

    trigger_type = str(monitor.get("trigger_type") or "").strip()
    if not trigger_type:
        trigger_type = exit_reason if action == "SELL" else entry_reason or monitor_reason
    if not trigger_type and decision_reason_chain:
        trigger_type = decision_reason_chain[-1]
    active_exit_axis = str(monitor.get("active_exit_axis") or trigger_details.get("active_exit_axis") or "").strip()
    if str(monitor_reason or "").strip().lower() in {"hold", "hold_position", "eod_carry_approved"} and not bool(monitor.get("exit_triggered")):
        active_exit_axis = "Hold"
    elif not active_exit_axis:
        active_exit_axis = format_exit_label(trigger_type)
    confirm_required = safe_int(
        thresholds_guards_used.get("exit_confirm_ticks"),
        safe_int(thresholds_guards_used.get("exit_confirm_required"), safe_int(monitor.get("exit_confirm_required"), 0)),
    )
    confirm_count = safe_int(
        thresholds_guards_used.get("exit_confirm_count"),
        safe_int(monitor.get("exit_confirm_count"), 0),
    )
    guard_blocked = bool(trigger_details.get("sell_guard_blocked") or monitor.get("guard_blocked") or monitor.get("sell_guard_blocked"))
    guard_reason = str(trigger_details.get("sell_guard_reason") or monitor.get("guard_reason") or monitor.get("sell_guard_reason") or "").strip()
    eod_carry_evaluated = bool(monitor.get("eod_carry_evaluated"))
    eod_carry_approved = bool(monitor.get("eod_carry_approved"))
    eod_carry_action = str(monitor.get("eod_carry_action") or "").strip()
    eod_carry_reason = str(monitor.get("eod_carry_reason") or "").strip()
    eod_carry_positive_signals = _list_text(monitor.get("eod_carry_positive_signals"), limit=6, max_len=120)
    eod_carry_blockers = _list_text(monitor.get("eod_carry_blockers"), limit=6, max_len=120)
    minutes_to_close = monitor.get("minutes_to_close")
    entry_threshold_gaps: List[str] = []
    if entry_metrics.get("volume_ratio") not in (None, "") and entry_thresholds.get("volume_ratio_min") not in (None, ""):
        volume_ratio = safe_float(entry_metrics.get("volume_ratio"), 0.0)
        volume_ratio_min = safe_float(entry_thresholds.get("volume_ratio_min"), 0.0)
        if volume_ratio < volume_ratio_min:
            entry_threshold_gaps.append(f"volume ratio {volume_ratio:.2f} below min {volume_ratio_min:.2f}")
    if entry_metrics.get("extended_from_vwap_pct") not in (None, "") and entry_thresholds.get("max_extended_from_vwap_pct") not in (None, ""):
        extended = safe_float(entry_metrics.get("extended_from_vwap_pct"), 0.0)
        extended_max = safe_float(entry_thresholds.get("max_extended_from_vwap_pct"), 0.0)
        if extended > extended_max:
            entry_threshold_gaps.append(
                f"VWAP extension {format_ratio_pct(extended)}% above max {format_ratio_pct(extended_max)}%"
            )
    if entry_metrics.get("pullback_depth_pct") not in (None, "") and entry_thresholds.get("pullback_min_pct") not in (None, ""):
        pullback_depth = safe_float(entry_metrics.get("pullback_depth_pct"), 0.0)
        pullback_min = safe_float(entry_thresholds.get("pullback_min_pct"), 0.0)
        if pullback_depth < pullback_min:
            entry_threshold_gaps.append(
                f"pullback depth {format_ratio_pct(pullback_depth)}% below min {format_ratio_pct(pullback_min)}%"
            )
    monitor_stop_policy_trace = _build_monitor_stop_policy_trace(monitor, thresholds)
    monitor_blocker_trace = _build_monitor_blocker_trace(
        {
            "entry_check_summary": entry_check_summary,
            "entry_blockers": entry_blockers,
            "entry_metrics": entry_metrics,
            "entry_thresholds": entry_thresholds,
            "timing_assessment": timing_assessment,
            "policy_ref": policy_ref,
            "entry_condition_path": entry_condition_path,
            "entry_condition_paths_passed": entry_condition_paths_passed,
            "condition_scores": entry_condition_scores,
            "grouped_logic_trace": entry_grouped_logic_trace,
        }
    )
    if eod_carry_approved and action not in ("BUY", "SELL"):
        summary = (
            f"Monitor kept the position into the close because overnight carry was approved "
            f"{safe_float(minutes_to_close, 0.0):.1f} minutes before the close."
        )
    elif action == "BUY":
        summary = f"BUY was triggered because {entry_reason or monitor_reason or 'the intraday entry condition passed'}."
        if entry_pattern:
            summary += f" Pattern: {entry_pattern}."
        if entry_condition_path:
            summary += f" Path: {entry_condition_path.replace('_', ' ')}."
    elif action == "SELL":
        if eod_carry_evaluated and not eod_carry_approved and str(trigger_type or "").strip().lower() in ("eod_flat", "carry_overnight_approved"):
            summary = (
                f"SELL was triggered to flatten before the close because overnight carry was not approved "
                f"({eod_carry_reason or 'carry conditions were not met'})."
            )
        else:
            summary = f"SELL was triggered because {trigger_type or monitor_reason or 'the exit condition passed'}."
    elif entry_evaluated and not entry_triggered:
        summary = f"Monitor stayed on WAIT because {entry_check_summary or entry_reason or monitor_reason or 'the intraday entry signal was not confirmed'}."
        if entry_threshold_gaps:
            summary += " Threshold gaps: " + "; ".join(entry_threshold_gaps[:3]) + "."
    else:
        summary = f"Monitor posture was {action or 'WAIT'} with trigger {trigger_type or 'not_captured'}."
    bullets = [
        f"Posture: {action or 'WAIT'}",
        f"Trigger type: {trigger_type or 'not_captured'}",
        f"Monitor reason: {monitor_reason or trigger_type or 'not_captured'}",
        f"Position age: {safe_int(monitor.get('position_age_seconds'), 0)} seconds",
        f"Stop loss: {format_ratio_pct(thresholds.get('stop_loss_pct'))}%",
        f"Effective stop: {format_ratio_pct(thresholds.get('effective_stop_loss_pct'))}%",
        f"Effective stop reason: {str(thresholds.get('effective_stop_reason') or 'not_captured')}",
        f"Take profit: {format_ratio_pct(thresholds.get('take_profit_pct'))}%",
        f"Active exit axis: {active_exit_axis or 'not_captured'}",
        f"Exit confirmation: {confirm_count}/{confirm_required}" if confirm_required > 0 else "Exit confirmation: not required",
        f"Min hold blocked: {'yes' if monitor.get('min_hold_blocked') else 'no'}",
        f"Sell cooldown blocked: {'yes' if monitor.get('sell_cooldown_blocked') else 'no'}",
        f"Exit triggered: {'yes' if monitor.get('exit_triggered') else 'no'}",
    ]
    if monitor_stop_policy_trace.get("hard_stop_pct") not in (None, ""):
        bullets.append(
            f"Hard fail-safe stop: {format_ratio_pct(monitor_stop_policy_trace.get('hard_stop_pct'))}%"
        )
    if monitor_stop_policy_trace.get("adaptive_stop_loss_pct") not in (None, ""):
        bullets.append(
            f"Active adaptive stop: {format_ratio_pct(monitor_stop_policy_trace.get('adaptive_stop_loss_pct'))}%"
        )
    if monitor_stop_policy_trace.get("strategist_baseline_stop_loss_pct") not in (None, ""):
        bullets.append(
            f"Strategist baseline adaptive stop: {format_ratio_pct(monitor_stop_policy_trace.get('strategist_baseline_stop_loss_pct'))}%"
        )
    if monitor_stop_policy_trace.get("effective_stop_loss_pct") not in (None, ""):
        bullets.append(
            f"Effective stop in this run: {format_ratio_pct(monitor_stop_policy_trace.get('effective_stop_loss_pct'))}%"
        )
    if monitor_stop_policy_trace.get("trailing_stop_pct") not in (None, ""):
        bullets.append(
            f"Trailing stop: {format_ratio_pct(monitor_stop_policy_trace.get('trailing_stop_pct'))}%"
        )
    if monitor_stop_policy_trace.get("strategist_baseline_trailing_stop_pct") not in (None, ""):
        bullets.append(
            f"Strategist baseline trailing stop: {format_ratio_pct(monitor_stop_policy_trace.get('strategist_baseline_trailing_stop_pct'))}%"
        )
    if monitor_stop_policy_trace.get("take_profit_pct") not in (None, ""):
        bullets.append(
            f"Take profit target: {format_ratio_pct(monitor_stop_policy_trace.get('take_profit_pct'))}%"
        )
    if monitor_stop_policy_trace.get("strategist_baseline_take_profit_pct") not in (None, ""):
        bullets.append(
            f"Strategist baseline take profit: {format_ratio_pct(monitor_stop_policy_trace.get('strategist_baseline_take_profit_pct'))}%"
        )
    if entry_evaluated:
        bullets.append(f"Entry triggered: {'yes' if entry_triggered else 'no'}")
        bullets.append(f"Entry pattern: {entry_pattern or 'not_captured'}")
        if entry_signal_chain:
            bullets.append("Entry signal chain: " + " -> ".join(entry_signal_chain[:6]))
        if entry_condition_path:
            bullets.append(f"Grouped entry path: {entry_condition_path}")
        if entry_condition_paths_passed:
            bullets.append("Grouped paths passed: " + ", ".join(entry_condition_paths_passed[:3]))
        if entry_condition_scores:
            bullets.append(
                "Condition scores: "
                + "; ".join(
                    [
                        f"{key}={safe_float(value, 0.0):.2f}"
                        for key, value in list(entry_condition_scores.items())[:6]
                        if value not in (None, "")
                    ]
                )
            )
        if entry_guard_blocked or entry_guard_reason:
            bullets.append(
                f"Entry guard blocked: {'yes' if entry_guard_blocked else 'no'} "
                f"({entry_guard_reason or 'no guard reason captured'})"
            )
        if entry_metrics.get("timeframe_minutes") not in (None, ""):
            bullets.append(f"Entry timeframe: {safe_int(entry_metrics.get('timeframe_minutes'), 1)}m")
        if entry_metrics.get("recent_high") not in (None, ""):
            bullets.append(f"Recent high: {safe_float(entry_metrics.get('recent_high'), 0.0):.2f}")
        if entry_metrics.get("breakout_level") not in (None, ""):
            bullets.append(f"Breakout level: {safe_float(entry_metrics.get('breakout_level'), 0.0):.2f}")
        if entry_metrics.get("vwap") not in (None, ""):
            bullets.append(f"Entry VWAP: {safe_float(entry_metrics.get('vwap'), 0.0):.2f}")
        if entry_metrics.get("volume_ratio") not in (None, ""):
            bullets.append(
                f"Volume ratio: {safe_float(entry_metrics.get('volume_ratio'), 0.0):.2f} "
                f"(min {safe_float(entry_thresholds.get('volume_ratio_min'), 0.0):.2f})"
            )
        if entry_metrics.get("extended_from_vwap_pct") not in (None, ""):
            bullets.append(
                f"Extended from VWAP: {format_ratio_pct(entry_metrics.get('extended_from_vwap_pct'))}% "
                f"(max {format_ratio_pct(entry_thresholds.get('max_extended_from_vwap_pct'))}%)"
            )
        if entry_metrics.get("pullback_depth_pct") not in (None, ""):
            pullback_bullet = f"Pullback depth: {format_ratio_pct(entry_metrics.get('pullback_depth_pct'))}%"
            if entry_thresholds.get("pullback_min_pct") not in (None, ""):
                pullback_bullet += f" (min {format_ratio_pct(entry_thresholds.get('pullback_min_pct'))}%)"
            if entry_thresholds.get("pullback_max_pct") not in (None, ""):
                pullback_bullet += f" (max {format_ratio_pct(entry_thresholds.get('pullback_max_pct'))}%)"
            bullets.append(pullback_bullet)
        if entry_check_summary:
            bullets.append(f"Entry check summary: {entry_check_summary}")
        if entry_blockers:
            bullets.append("Entry blockers: " + "; ".join(entry_blockers[:6]))
        if entry_threshold_gaps:
            bullets.append("Threshold gaps: " + "; ".join(entry_threshold_gaps[:3]))
        if policy_adjustment_summary:
            bullets.append(f"Policy adjustment summary: {policy_adjustment_summary}")
        if effective_policy_deltas:
            bullets.append(
                "Effective policy deltas: "
                + "; ".join(
                    [
                        f"{str((row or {}).get('field') or '')}: {(row or {}).get('from')} -> {(row or {}).get('to')}"
                        for row in effective_policy_deltas[:4]
                        if str((row or {}).get("field") or "").strip()
                    ]
                )
            )
        if policy_ref:
            policy_bits: List[str] = []
            for key in ("monitor_mission", "flow_instruction", "risk_mode", "command_intent"):
                value = str(policy_ref.get(key) or "").strip()
                if value:
                    policy_bits.append(f"{key}={value}")
            if policy_bits:
                bullets.append("Policy reference: " + ", ".join(policy_bits[:4]))
    if eod_carry_evaluated:
        bullets.append(
            f"EOD carry decision: {'approved' if eod_carry_approved else 'flatten before close'} "
            f"({eod_carry_reason or 'not_captured'})"
        )
        if minutes_to_close not in (None, ""):
            bullets.append(f"Minutes to close at decision: {safe_float(minutes_to_close, 0.0):.1f}")
        if eod_carry_positive_signals:
            bullets.append("Carry positives: " + "; ".join(eod_carry_positive_signals[:4]))
        if eod_carry_blockers:
            bullets.append("Carry blockers: " + "; ".join(eod_carry_blockers[:4]))
    if watch_axes:
        bullets.append("Watch axes: " + ", ".join(watch_axes[:8]))
    if decision_reason_chain:
        bullets.append("Decision chain: " + " -> ".join(decision_reason_chain[:5]))
    if guard_blocked or guard_reason:
        bullets.append(f"Guard blocked: {'yes' if guard_blocked else 'no'} ({guard_reason or 'no guard reason captured'})")
    if current_price not in (None, ""):
        bullets.append(f"Current price: {safe_float(current_price, 0.0):.2f}")
    if average_price not in (None, ""):
        bullets.append(f"Average price: {safe_float(average_price, 0.0):.2f}")
    if peak_price not in (None, ""):
        bullets.append(f"Peak price: {safe_float(peak_price, 0.0):.2f}")
    if current_drawdown not in (None, ""):
        bullets.append(f"Current drawdown: {format_ratio_pct(current_drawdown)}%")
    if peak_drawdown not in (None, ""):
        bullets.append(f"Peak drawdown: {format_ratio_pct(peak_drawdown)}%")
    if vwap_distance not in (None, ""):
        bullets.append(f"VWAP distance: {format_ratio_pct(vwap_distance)}%")
    if price_source:
        bullets.append(f"Price source: {price_source}")
    if feature_source:
        bullets.append(f"Feature source: {feature_source}")
    if price_source_policy:
        bullets.append(f"Price source policy: {price_source_policy}")
    return {
        "posture": action or "WAIT",
        "trigger_type": trigger_type,
        "summary": summary,
        "bullets": bullets,
        "position_age_seconds": safe_int(monitor.get("position_age_seconds"), 0),
        "stop_loss_pct": thresholds.get("stop_loss_pct"),
        "hard_stop_pct": monitor_stop_policy_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": monitor_stop_policy_trace.get("adaptive_stop_loss_pct"),
        "effective_stop_loss_pct": monitor_stop_policy_trace.get("effective_stop_loss_pct"),
        "effective_stop_reason": str(thresholds.get("effective_stop_reason") or "").strip(),
        "take_profit_pct": monitor_stop_policy_trace.get("take_profit_pct"),
        "trailing_stop_pct": monitor_stop_policy_trace.get("trailing_stop_pct"),
        "exit_triggered": bool(monitor.get("exit_triggered")),
        "entry_evaluated": entry_evaluated,
        "entry_triggered": entry_triggered,
        "entry_reason": entry_reason,
        "entry_pattern": entry_pattern,
        "entry_signal_chain": entry_signal_chain[:8],
        "entry_condition_path": entry_condition_path,
        "entry_condition_paths_passed": entry_condition_paths_passed[:4],
        "entry_condition_scores": dict(entry_condition_scores),
        "entry_grouped_logic_trace": dict(entry_grouped_logic_trace),
        "entry_metrics": dict(entry_metrics),
        "entry_thresholds": dict(entry_thresholds),
        "entry_check_summary": entry_check_summary,
        "entry_blockers": entry_blockers[:8],
        "threshold_shortfalls": entry_threshold_gaps[:4],
        "policy_ref": dict(policy_ref),
        "received_policy": dict(received_policy),
        "effective_policy": dict(effective_policy),
        "policy_adjustment_summary": policy_adjustment_summary,
        "effective_policy_deltas": effective_policy_deltas,
        "monitor_stop_policy_trace": monitor_stop_policy_trace,
        "monitor_blocker_trace": monitor_blocker_trace,
        "timing_assessment": dict(timing_assessment),
        "thresholds_guards_used": dict(thresholds_guards_used),
        "entry_guard_blocked": entry_guard_blocked,
        "entry_guard_reason": entry_guard_reason,
        "current_price": current_price,
        "average_price": average_price,
        "peak_price": peak_price,
        "current_drawdown": current_drawdown,
        "peak_drawdown": peak_drawdown,
        "vwap_distance": vwap_distance,
        "active_exit_axis": active_exit_axis,
        "watch_axes": watch_axes[:8],
        "confirm_required": confirm_required,
        "confirm_count": confirm_count,
        "guard_blocked": guard_blocked,
        "guard_reason": guard_reason,
        "eod_carry_evaluated": eod_carry_evaluated,
        "eod_carry_approved": eod_carry_approved,
        "eod_carry_action": eod_carry_action,
        "eod_carry_reason": eod_carry_reason,
        "eod_carry_positive_signals": eod_carry_positive_signals,
        "eod_carry_blockers": eod_carry_blockers,
        "decision_reason_chain": decision_reason_chain[:6],
        "price_source": price_source,
        "feature_source": feature_source,
        "price_source_policy": price_source_policy,
    }


def build_guard_reason_human(supervisor: Dict[str, Any]) -> Dict[str, Any]:
    allow = bool(supervisor.get("supervisor_allow"))
    verdict = str(supervisor.get("verdict") or "").strip() or ("approve" if allow else "block")
    reason = str(supervisor.get("supervisor_reason") or supervisor.get("guard_reason") or "").strip() or "not captured"
    summary = (
        f"Supervisor approved the order because {reason}."
        if allow
        else f"Supervisor blocked the order because {reason}."
    )
    bullets = [
        f"Supervisor verdict: {verdict}",
        f"Supervisor allow: {'yes' if allow else 'no'}",
        f"Guard reason: {reason}",
        f"Action reviewed: {supervisor.get('action') or 'not_captured'}",
        f"Symbol reviewed: {supervisor.get('symbol') or 'not_captured'}",
        "Approval mode: not captured in the execution trace",
    ]
    return {"summary": summary, "bullets": bullets, "allow": allow, "verdict": verdict}


def build_execution_outcome_human(
    execution: Dict[str, Any],
    executor: Dict[str, Any],
    *,
    story_type: str,
    mode_label: str,
) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper() or "WAIT"
    symbol = str(execution.get("symbol") or "").strip() or "unknown"
    qty = safe_int(execution.get("qty"), 0)
    status_text = str(execution.get("status") or executor.get("broker_message") or "").strip()
    if story_type == "simulation":
        summary = f"{action} order for {symbol} x{qty} was approved and recorded successfully in simulation mode."
        outcome = "recorded"
    elif story_type == "failed_execution":
        summary = f"{action} order for {symbol} x{qty} was attempted but did not complete successfully."
        outcome = "failed"
    elif story_type == "live_trade":
        summary = f"{action} order for {symbol} x{qty} completed as a live broker execution."
        outcome = "filled"
    else:
        summary = f"No broker-side execution was recorded for {symbol} in this story."
        outcome = "decision_only"
    bullets = [
        f"Execution outcome: {outcome}",
        f"Quantity: {qty}",
        f"Execution mode: {mode_label}",
        f"Broker environment: {executor.get('broker_env') or 'not_captured'}",
        f"Order status: {status_text or 'not_captured'}",
        f"Order number: {execution.get('ord_no') or 'not_captured'}",
    ]
    return {
        "summary": summary,
        "outcome": outcome,
        "quantity": qty,
        "status_text": status_text,
        "bullets": bullets,
    }


def build_reporter_status_human(reporter: Dict[str, Any], reporter_day_obj: Dict[str, Any]) -> Dict[str, Any]:
    linked = bool(reporter.get("reporter_analysis_found"))
    day_file_found = bool(reporter.get("reporter_analysis_day_file_found"))
    ai_summary = str(reporter.get("reporter_analysis_summary") or reporter_day_obj.get("ai_summary") or "").strip()
    grade = str(reporter_day_obj.get("ai_run_grade") or "N/A").strip()
    if linked:
        status = "linked"
        reason = "A same-day reporter analysis was linked to this run."
    elif day_file_found:
        status = "pending"
        reason = "A same-day reporter file exists, but this run was not linked to a run-specific evaluation yet."
    else:
        status = "missing"
        reason = "Same-day reporter analysis was not generated yet."
    if status == "linked":
        summary = ai_summary or reason
    elif ai_summary:
        summary = f"{reason} Interim summary: {ai_summary}"
    else:
        summary = reason
    bullets = [
        f"Reporter status: {status}",
        f"Reporter reason: {reason}",
        f"Reporter grade: {grade}",
        f"Reporter summary: {summary}",
    ]
    return {
        "status": status,
        "reason": reason,
        "grade": grade,
        "summary": summary,
        "bullets": bullets,
    }


def build_operator_conclusion_human(
    *,
    execution: Dict[str, Any],
    scanner_reason_human: Dict[str, Any],
    filters_human: Dict[str, Any],
    monitor_reason_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper() or "WAIT"
    watch_next: List[str] = []
    invalidation: List[str] = [
        "Negative macro regime shift",
        "Theme or sector weakening",
        "Scanner and monitor logic diverging from each other",
    ]
    if action == "BUY":
        watch_next.append("Watch the stop-loss and take-profit thresholds on the open position.")
        watch_next.append("Confirm that the selected theme keeps its relative strength.")
    elif action == "SELL":
        watch_next.append("Review whether the exit was a valid protection move or avoidable noise.")
        watch_next.append("Monitor the symbol for any re-entry only after the cooldown and fresh scanner confirmation.")
    else:
        watch_next.append("Wait for a fresh scanner ranking and monitor confirmation.")
    if reporter_status_human.get("status") != "linked":
        watch_next.append("Follow up once same-day reporter linkage becomes available.")
    if "FAIL" in " ".join(row.get("status") or "" for row in list(filters_human.get("checks") or [])):
        watch_next.append("Check failed or incomplete filters before trusting the next cycle too aggressively.")
    summary = (
        f"Current action is {action}. "
        f"{execution_outcome_human.get('summary') or scanner_reason_human.get('summary') or monitor_reason_human.get('summary')}"
    )
    return {
        "current_action": action,
        "summary": summary,
        "watch_next": watch_next[:6],
        "thesis_invalidation": invalidation[:6],
    }


def build_timeline(
    *,
    commander: Dict[str, Any],
    market_context_human: Dict[str, Any],
    scanner_reason_human: Dict[str, Any],
    monitor_reason_human: Dict[str, Any],
    guard_reason_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
    execution: Dict[str, Any],
) -> List[Dict[str, Any]]:
    route_ts = str(commander.get("route_ts") or "")
    execution_ts = str(execution.get("ts") or "")
    return [
        {"step": "strategist_frame", "status": "ok", "ts": route_ts, "summary": market_context_human.get("summary") or ""},
        {"step": "scanner_ranking", "status": "ok", "ts": route_ts, "summary": scanner_reason_human.get("summary") or ""},
        {"step": "monitor_signal", "status": "ok", "ts": execution_ts, "summary": monitor_reason_human.get("summary") or ""},
        {"step": "supervisor_approval", "status": "ok", "ts": execution_ts, "summary": guard_reason_human.get("summary") or ""},
        {"step": "broker_result", "status": "ok", "ts": execution_ts, "summary": execution_outcome_human.get("summary") or ""},
        {"step": "reporter_output", "status": "ok", "ts": utc_now_iso(), "summary": reporter_status_human.get("summary") or ""},
    ]


def collect_story_warnings(
    *,
    story_contract: Dict[str, Any],
    market_context_human: Dict[str, Any],
    filters_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
) -> List[str]:
    warnings = [str(x or "") for x in list(story_contract.get("warnings") or []) if str(x or "").strip()]
    if market_context_human.get("defensive_mode"):
        warnings.append("Macro or volatility context was defensive for this run.")
    if reporter_status_human.get("status") == "pending":
        warnings.append("Reporter evaluation is pending because same-day run linkage was not available yet.")
    elif reporter_status_human.get("status") == "missing":
        warnings.append("Reporter evaluation is missing because the same-day analysis file was not generated yet.")
    for row in list(filters_human.get("checks") or []):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").upper()
        if status in {"FAIL", "PARTIAL", "NOT_AVAILABLE"}:
            warnings.append(f"{row.get('name')}: {status} ({row.get('detail') or ''})")
    if execution_outcome_human.get("outcome") == "failed":
        warnings.append("Execution did not complete successfully and needs operator review.")
    deduped: List[str] = []
    for item in warnings:
        text = clip(item, max_len=260)
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:10]


def build_trade_story_input(
    bundle_out: Dict[str, Any],
    *,
    trade_lifecycle: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    story_contract = bundle_out.get("story_contract") if isinstance(bundle_out.get("story_contract"), dict) else {}
    section_provenance = build_section_provenance(bundle_out)
    canonical_agent_artifacts = dict(bundle_out.get("canonical_agent_artifacts") or {})
    evidence_provenance = dict(bundle_out.get("evidence_provenance") or {})
    # Reporting layers prefer the canonical reasoning snapshot when it is already
    # mirrored into bundle inputs; otherwise they derive a compatible mirror.
    bundle_reasoning_trace = bundle_out.get("reasoning_trace") if isinstance(bundle_out.get("reasoning_trace"), dict) else {}
    bundle_reasoning_provenance = (
        bundle_out.get("reasoning_provenance") if isinstance(bundle_out.get("reasoning_provenance"), dict) else {}
    )
    lifecycle = (
        trade_lifecycle
        if isinstance(trade_lifecycle, dict)
        else bundle_out.get("trade_lifecycle")
        if isinstance(bundle_out.get("trade_lifecycle"), dict)
        else {}
    )
    if lifecycle:
        entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        summary = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
        reporter = lifecycle.get("reporter") if isinstance(lifecycle.get("reporter"), dict) else {}
        symbol = str(lifecycle.get("symbol") or (bundle_out.get("execution") or {}).get("symbol") or "")
        status = str(lifecycle.get("status") or "open")
        entry_action = str(entry.get("action") or (bundle_out.get("execution") or {}).get("action") or "BUY")
        exit_action = str(exit_ctx.get("action") or "")
        lifecycle_action = exit_action or entry_action or "WAIT"
        market_context_human = dict(bundle_out.get("market_context_human") or {})
        scanner_reason_human = dict(bundle_out.get("scanner_reason_human") or {})
        scanner_evidence = dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {})
        scanner_reason_human = enrich_scanner_reason_from_evidence(scanner_reason_human, scanner_evidence)
        filters_human = dict(bundle_out.get("filters_human") or {})
        filters_human = enrich_filters_from_evidence(
            filters_human,
            scanner_evidence,
            selected_symbol=str(scanner_reason_human.get("selected_symbol") or (entry.get("scanner_context") or {}).get("selected_symbol") or symbol),
        )
        monitor_reason_human = dict(bundle_out.get("monitor_reason_human") or {})
        guard_reason_human = dict(bundle_out.get("guard_reason_human") or {})
        execution_outcome_human = dict(bundle_out.get("execution_outcome_human") or {})
        reporter_status_human = dict(bundle_out.get("reporter_status_human") or {})
        operator_conclusion_human = dict(bundle_out.get("operator_conclusion_human") or {})
        if not market_context_human:
            market_context_human = {
                "summary": str((entry.get("strategist_context") or {}).get("market_context_summary") or "Market context was not captured."),
                "bullets": [
                    f"Playbook: {str((entry.get('strategist_context') or {}).get('playbook') or 'not_captured')}",
                    "Lifecycle-level entry context was used.",
                ],
            }
        if not scanner_reason_human:
            scanner_reason_human = {
                "summary": str(entry.get("reason_human") or "Scanner selection rationale was not captured."),
                "bullets": [str(entry.get("reason_human") or "no scanner rationale captured")],
            }
        if not monitor_reason_human:
            monitor_reason_human = {
                "summary": (
                    f"Holding updates captured from {len(list(holding.get('run_ids') or []))} monitor runs."
                    if list(holding.get("run_ids") or [])
                    else "Holding monitor updates were not captured."
                ),
                "bullets": [str(x or "") for x in list(holding.get("monitor_updates") or [])[:8]],
            }
        if not execution_outcome_human:
            execution_outcome_human = {
                "summary": str(summary.get("lifecycle_summary_human") or "Execution outcome summary was not captured."),
                "bullets": [
                    f"Lifecycle status: {status}",
                    f"Entry action: {entry_action or 'not_captured'}",
                    f"Exit action: {exit_action or 'not_captured'}",
                ],
            }
        if not reporter_status_human:
            reporter_status_human = {
                "status": str(reporter.get("status_human") or "missing"),
                "summary": str(reporter.get("summary") or "Reporter linkage was not captured."),
                "grade": str(reporter.get("grade") or "N/A"),
                "bullets": [str(x or "") for x in list(reporter.get("improvement_points") or [])[:6]],
            }
        if not operator_conclusion_human:
            operator_conclusion_human = {
                "summary": str(summary.get("operator_conclusion_human") or "Lifecycle conclusion was not captured."),
                "current_action": "HOLD" if status == "open" else lifecycle_action,
                "watch_next": [f"Lifecycle status is {status}", "Monitor posture changes", "Macro/news regime changes"],
                "thesis_invalidation": ["stop-loss breach", "monitor/scanner divergence", "negative macro shift"],
            }
        canonical_strategist = (
            canonical_agent_artifacts.get("strategist")
            if isinstance(canonical_agent_artifacts.get("strategist"), dict)
            else bundle_out.get("strategist")
            if isinstance(bundle_out.get("strategist"), dict)
            else {}
        )
        canonical_scanner = (
            canonical_agent_artifacts.get("scanner")
            if isinstance(canonical_agent_artifacts.get("scanner"), dict)
            else bundle_out.get("scanner")
            if isinstance(bundle_out.get("scanner"), dict)
            else {}
        )
        canonical_monitor = (
            canonical_agent_artifacts.get("monitor")
            if isinstance(canonical_agent_artifacts.get("monitor"), dict)
            else bundle_out.get("monitor")
            if isinstance(bundle_out.get("monitor"), dict)
            else {}
        )
        selected_symbol = str(
            scanner_reason_human.get("selected_symbol")
            or (entry.get("scanner_context") or {}).get("selected_symbol")
            or canonical_scanner.get("selected_symbol")
            or canonical_scanner.get("top_stock")
            or (bundle_out.get("scanner_summary") or {}).get("selected_symbol")
            or symbol
            or ""
        ).strip()
        strategist_evidence_trace = _build_strategist_evidence_trace(
            canonical_strategist,
            selected_symbol=selected_symbol,
            fallback_market_titles=market_context_human.get("market_news_titles"),
            fallback_candidate_titles=market_context_human.get("candidate_news_titles"),
        )
        scanner_selection_trace = _build_scanner_selection_trace(scanner_reason_human, canonical_scanner)
        ranked_symbols = [
            str(row.get("symbol") or "").strip()
            for row in list(scanner_selection_trace.get("ranked_candidates") or [])
            if isinstance(row, dict) and str(row.get("symbol") or "").strip()
        ]
        news_symbol_linkage = build_news_symbol_linkage_view(
            strategist_summary=canonical_strategist,
            strategist_raw_input=dict(bundle_out.get("strategist_evidence") or (bundle_out.get("evidence") or {}).get("strategist") or {}),
            strategist_parsed_output=dict((bundle_out.get("strategist_summary") or {}).get("llm_parsed_output") or {}),
            selected_symbol=selected_symbol,
            top_ranked_symbols=ranked_symbols or canonical_scanner.get("top_ranked_symbols") or [],
        )
        monitor_stop_thresholds = (
            ((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"))
            if isinstance((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"), dict)
            else canonical_monitor.get("thresholds")
            if isinstance(canonical_monitor.get("thresholds"), dict)
            else canonical_monitor.get("threshold_snapshot")
            if isinstance(canonical_monitor.get("threshold_snapshot"), dict)
            else {}
        )
        monitor_stop_policy_trace = _build_monitor_stop_policy_trace(
            canonical_monitor,
            monitor_stop_thresholds,
        )
        monitor_blocker_trace = _build_monitor_blocker_trace(monitor_reason_human)
        market_context_human.setdefault("candidate_hints", strategist_evidence_trace.get("candidate_hints") or [])
        market_context_human.setdefault("market_headlines", strategist_evidence_trace.get("market_headlines") or [])
        market_context_human.setdefault("symbol_headlines", strategist_evidence_trace.get("symbol_headlines") or [])
        market_context_human.setdefault("strategist_evidence_trace", dict(strategist_evidence_trace))
        market_context_human.setdefault("news_symbol_linkage", dict(news_symbol_linkage))
        scanner_reason_human.setdefault("scanner_selection_trace", dict(scanner_selection_trace))
        scanner_reason_human.setdefault("ranked_candidates", list(scanner_selection_trace.get("ranked_candidates") or []))
        scanner_reason_human.setdefault("selection_reason", scanner_selection_trace.get("selection_reason"))
        scanner_reason_human.setdefault(
            "selected_symbol_score_drivers",
            dict(scanner_selection_trace.get("selected_symbol_score_drivers") or {}),
        )
        monitor_reason_human.setdefault("monitor_stop_policy_trace", dict(monitor_stop_policy_trace))
        monitor_reason_human.setdefault("monitor_blocker_trace", dict(monitor_blocker_trace))
        derived_reasoning_trace = build_reasoning_trace_from_summaries(
            commander_summary=dict(bundle_out.get("commander_summary") or {}),
            strategist_summary=dict(bundle_out.get("strategist_summary") or {}),
            scanner_summary=dict(bundle_out.get("scanner_summary") or {}),
            monitor_summary=dict(bundle_out.get("monitor_summary") or {}),
            market_context_human=market_context_human,
            scanner_reason_human=scanner_reason_human,
            monitor_reason_human=monitor_reason_human,
            operator_conclusion_human=operator_conclusion_human,
        )
        reasoning_trace = normalize_reasoning_trace_aliases(
            {
                "reasoning_trace": bundle_reasoning_trace,
                "latest_reasoning_trace": bundle_out.get("latest_reasoning_trace"),
            },
            fallback=derived_reasoning_trace,
        )
        commander_source_priority = _commander_reasoning_source_priority(bundle_out, dict(bundle_out.get("commander_summary") or {}))
        derived_reasoning_provenance = build_reasoning_provenance(
            commander_context_source="canonical" if canonical_agent_artifacts.get("canonical_commander_json") or canonical_agent_artifacts.get("canonical_commander") else str(evidence_provenance.get("commander") or ""),
            strategist_plan_source=str(
                (section_provenance.get("market_context_human") or {}).get("source")
                or evidence_provenance.get("strategist")
                or ("canonical" if canonical_agent_artifacts.get("canonical_strategist_json") or canonical_agent_artifacts.get("canonical_strategist") else "")
            ),
            scanner_reason_source=str(
                (section_provenance.get("scanner_reason_human") or {}).get("source")
                or evidence_provenance.get("scanner")
                or ("canonical" if canonical_agent_artifacts.get("canonical_scanner_json") or canonical_agent_artifacts.get("canonical_scanner") else "")
            ),
            monitor_reason_source=str(
                (section_provenance.get("monitor_reason_human") or {}).get("source")
                or evidence_provenance.get("monitor")
                or ("canonical" if canonical_agent_artifacts.get("canonical_monitor_json") or canonical_agent_artifacts.get("canonical_monitor") else "")
            ),
            commander_source_ref=_resolve_commander_source_ref(canonical_agent_artifacts, section_provenance),
            strategist_source_ref=str(
                canonical_agent_artifacts.get("canonical_strategist_json")
                or canonical_agent_artifacts.get("canonical_strategist")
                or (section_provenance.get("market_context_human") or {}).get("artifact_path")
                or ""
            ),
            scanner_source_ref=str(
                canonical_agent_artifacts.get("canonical_scanner_json")
                or canonical_agent_artifacts.get("canonical_scanner")
                or (section_provenance.get("scanner_reason_human") or {}).get("artifact_path")
                or ""
            ),
            monitor_source_ref=str(
                canonical_agent_artifacts.get("canonical_monitor_json")
                or canonical_agent_artifacts.get("canonical_monitor")
                or (section_provenance.get("monitor_reason_human") or {}).get("artifact_path")
                or ""
            ),
            shadow_used=_commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "shadow_used"),
            strategist_fallback_used=(
                _commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "strategist_fallback_used")
                or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
            ),
            source_priority=commander_source_priority,
        )
        reasoning_provenance = normalize_reasoning_provenance_aliases(
            {
                "reasoning_provenance": bundle_reasoning_provenance,
                "latest_reasoning_trace_provenance": bundle_out.get("latest_reasoning_trace_provenance"),
            },
            fallback=derived_reasoning_provenance,
        )
        if isinstance(bundle_out.get("commander"), dict) or isinstance(bundle_out.get("latest_reasoning_trace_provenance"), dict):
            reasoning_provenance["shadow_used"] = _commander_reasoning_flag(
                bundle_out,
                dict(bundle_out.get("commander_summary") or {}),
                "shadow_used",
            )
            reasoning_provenance["strategist_fallback_used"] = (
                _commander_reasoning_flag(
                    bundle_out,
                    dict(bundle_out.get("commander_summary") or {}),
                    "strategist_fallback_used",
                )
                or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
            )
            if commander_source_priority:
                reasoning_provenance["source_priority"] = list(commander_source_priority)
        story_out = {
            "schema_version": "trade_story_input.v2",
            "day": str(bundle_out.get("day") or ""),
            "trade_id": str(lifecycle.get("trade_id") or bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
            "story_id": str(lifecycle.get("trade_id") or bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
            "run_id": str(bundle_out.get("run_id") or entry.get("run_id") or ""),
            "symbol": symbol,
            "action": lifecycle_action,
            "status": status,
            "story_type": str(story_contract.get("story_type") or lifecycle.get("story_type") or ""),
            "execution_mode_label": str(story_contract.get("execution_mode_label") or lifecycle.get("execution_mode_label") or ""),
            "entry_summary": {
                "run_id": str(entry.get("run_id") or ""),
                "ts": str(entry.get("ts") or ""),
                "action": entry_action,
                "reason_human": str(entry.get("reason_human") or ""),
                "strategist_context": dict(entry.get("strategist_context") or {}),
                "scanner_context": dict(entry.get("scanner_context") or {}),
                "monitor_context": dict(entry.get("monitor_context") or {}),
                "guard_context": dict(entry.get("guard_context") or {}),
                "execution_context": dict(entry.get("execution_context") or {}),
            },
            "holding_summary": {
                "run_ids": [str(x or "") for x in list(holding.get("run_ids") or []) if str(x or "").strip()],
                "holding_events": [dict(x) for x in list(holding.get("holding_events") or []) if isinstance(x, dict)][:20],
                "posture_history": [dict(x) for x in list(holding.get("posture_history") or []) if isinstance(x, dict)][:20],
                "monitor_updates": [str(x or "") for x in list(holding.get("monitor_updates") or []) if str(x or "").strip()][:20],
                "hold_duration": str(holding.get("hold_duration") or bundle_out.get("hold_duration") or ""),
                "hold_duration_sec": holding.get("hold_duration_sec") if holding.get("hold_duration_sec") is not None else bundle_out.get("hold_duration_sec"),
                "holding_phase_summary": str(holding.get("holding_phase_summary") or bundle_out.get("holding_phase_summary") or ""),
                "hold_events_count": holding.get("hold_events_count") if holding.get("hold_events_count") is not None else bundle_out.get("hold_events_count"),
                "monitor_context_snapshots": [dict(x) for x in list(holding.get("monitor_context_snapshots") or bundle_out.get("monitor_context_snapshots") or []) if isinstance(x, dict)][:20],
                "hold_signal_transitions": [dict(x) for x in list(holding.get("hold_signal_transitions") or bundle_out.get("hold_signal_transitions") or []) if isinstance(x, dict)][:20],
                "pre_exit_context_summary": dict(holding.get("pre_exit_context_summary") or bundle_out.get("pre_exit_context_summary") or {}),
            },
            "exit_summary": {
                "run_id": str(exit_ctx.get("run_id") or ""),
                "ts": str(exit_ctx.get("ts") or ""),
                "action": exit_action,
                "reason_human": str(exit_ctx.get("reason_human") or ""),
                "monitor_context": dict(exit_ctx.get("monitor_context") or {}),
                "guard_context": dict(exit_ctx.get("guard_context") or {}),
                "execution_context": dict(exit_ctx.get("execution_context") or {}),
            },
            "lifecycle_summary": {
                "holding_duration": str(summary.get("holding_duration") or ""),
                "entry_reason_human": str(summary.get("entry_reason_human") or ""),
                "exit_reason_human": str(summary.get("exit_reason_human") or ""),
                "lifecycle_summary_human": str(summary.get("lifecycle_summary_human") or ""),
                "operator_conclusion_human": str(summary.get("operator_conclusion_human") or ""),
            },
            "market_context_human": market_context_human,
            "scanner_reason_human": scanner_reason_human,
            "filters_human": filters_human,
            "monitor_reason_human": monitor_reason_human,
            "guard_reason_human": guard_reason_human,
            "execution_outcome_human": execution_outcome_human,
            "reporter_status_human": reporter_status_human,
            "same_day_reporter_linkage": dict(
                lifecycle.get("same_day_reporter_linkage")
                if isinstance(lifecycle.get("same_day_reporter_linkage"), dict)
                else bundle_out.get("same_day_reporter_linkage")
                if isinstance(bundle_out.get("same_day_reporter_linkage"), dict)
                else {}
            ),
            "operator_conclusion_human": operator_conclusion_human,
            "timeline": [dict(x) for x in list(lifecycle.get("timeline") or bundle_out.get("timeline") or []) if isinstance(x, dict)][:40],
            "warnings": [str(x or "") for x in list(bundle_out.get("warnings") or lifecycle.get("warnings") or []) if str(x or "").strip()][:20],
            "improvement_points": [str(x or "") for x in list(reporter.get("improvement_points") or []) if str(x or "").strip()][:12],
            "strategist_evidence": dict(bundle_out.get("strategist_evidence") or (bundle_out.get("evidence") or {}).get("strategist") or {}),
            "strategist_candidate_hints": list(strategist_evidence_trace.get("candidate_hints") or [])[:8],
            "strategist_market_headlines": list(strategist_evidence_trace.get("market_headlines") or [])[:3],
            "strategist_symbol_headlines": list(strategist_evidence_trace.get("symbol_headlines") or [])[:3],
            "strategist_evidence_trace": dict(strategist_evidence_trace),
            "news_symbol_linkage": dict(news_symbol_linkage),
            "scanner_evidence": scanner_evidence,
            "scanner_selection_trace": dict(scanner_selection_trace),
            "monitor_timeline": dict(bundle_out.get("monitor_timeline") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
            "monitor_stop_policy_trace": dict(monitor_stop_policy_trace),
            "monitor_blocker_trace": dict(monitor_blocker_trace),
            "canonical_agent_artifacts": canonical_agent_artifacts,
            "evidence_provenance": evidence_provenance,
            "section_provenance": dict(section_provenance),
            "reasoning_trace": dict(reasoning_trace),
            "reasoning_provenance": dict(reasoning_provenance),
            "evidence_source": "canonical" if any(
                str(source or "").strip().lower() == "canonical"
                for source in evidence_provenance.values()
            ) else "direct_artifact",
            "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
            "execution_details": dict(bundle_out.get("execution_details") or lifecycle.get("execution_details") or {}),
            "entry_execution_details": dict((entry.get("execution_details") if isinstance(entry.get("execution_details"), dict) else {}) or bundle_out.get("entry_execution_details") or {}),
            "exit_execution_details": dict((exit_ctx.get("execution_details") if isinstance(exit_ctx.get("execution_details"), dict) else {}) or bundle_out.get("exit_execution_details") or {}),
            "failure_classification": dict(bundle_out.get("failure_classification") or lifecycle.get("failure_classification") or {}),
        }
        story_out["strategist_feedback_input"] = build_strategist_feedback_input_view(story_out)
        return story_out

    derived_reasoning_trace = build_reasoning_trace_from_summaries(
        commander_summary=dict(bundle_out.get("commander_summary") or {}),
        strategist_summary=dict(bundle_out.get("strategist_summary") or {}),
        scanner_summary=dict(bundle_out.get("scanner_summary") or {}),
        monitor_summary=dict(bundle_out.get("monitor_summary") or {}),
        market_context_human=dict(bundle_out.get("market_context_human") or {}),
        scanner_reason_human=dict(bundle_out.get("scanner_reason_human") or {}),
        monitor_reason_human=dict(bundle_out.get("monitor_reason_human") or {}),
        operator_conclusion_human=dict(bundle_out.get("operator_conclusion_human") or {}),
    )
    reasoning_trace = normalize_reasoning_trace_aliases(
        {
            "reasoning_trace": bundle_reasoning_trace,
            "latest_reasoning_trace": bundle_out.get("latest_reasoning_trace"),
        },
        fallback=derived_reasoning_trace,
    )
    commander_source_priority = _commander_reasoning_source_priority(bundle_out, dict(bundle_out.get("commander_summary") or {}))
    derived_reasoning_provenance = build_reasoning_provenance(
        commander_context_source="canonical" if canonical_agent_artifacts.get("canonical_commander_json") or canonical_agent_artifacts.get("canonical_commander") else str(evidence_provenance.get("commander") or ""),
        strategist_plan_source=str(
            (section_provenance.get("market_context_human") or {}).get("source")
            or evidence_provenance.get("strategist")
            or ("canonical" if canonical_agent_artifacts.get("canonical_strategist_json") or canonical_agent_artifacts.get("canonical_strategist") else "")
        ),
        scanner_reason_source=str(
            (section_provenance.get("scanner_reason_human") or {}).get("source")
            or evidence_provenance.get("scanner")
            or ("canonical" if canonical_agent_artifacts.get("canonical_scanner_json") or canonical_agent_artifacts.get("canonical_scanner") else "")
        ),
        monitor_reason_source=str(
            (section_provenance.get("monitor_reason_human") or {}).get("source")
            or evidence_provenance.get("monitor")
            or ("canonical" if canonical_agent_artifacts.get("canonical_monitor_json") or canonical_agent_artifacts.get("canonical_monitor") else "")
        ),
        commander_source_ref=_resolve_commander_source_ref(canonical_agent_artifacts, section_provenance),
        strategist_source_ref=str(
            canonical_agent_artifacts.get("canonical_strategist_json")
            or canonical_agent_artifacts.get("canonical_strategist")
            or (section_provenance.get("market_context_human") or {}).get("artifact_path")
            or ""
        ),
        scanner_source_ref=str(
            canonical_agent_artifacts.get("canonical_scanner_json")
            or canonical_agent_artifacts.get("canonical_scanner")
            or (section_provenance.get("scanner_reason_human") or {}).get("artifact_path")
            or ""
        ),
        monitor_source_ref=str(
            canonical_agent_artifacts.get("canonical_monitor_json")
            or canonical_agent_artifacts.get("canonical_monitor")
            or (section_provenance.get("monitor_reason_human") or {}).get("artifact_path")
            or ""
        ),
        shadow_used=_commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "shadow_used"),
        strategist_fallback_used=(
            _commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "strategist_fallback_used")
            or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
        ),
        source_priority=commander_source_priority,
    )
    reasoning_provenance = normalize_reasoning_provenance_aliases(
        {
            "reasoning_provenance": bundle_reasoning_provenance,
            "latest_reasoning_trace_provenance": bundle_out.get("latest_reasoning_trace_provenance"),
        },
        fallback=derived_reasoning_provenance,
    )
    if isinstance(bundle_out.get("commander"), dict) or isinstance(bundle_out.get("latest_reasoning_trace_provenance"), dict):
        reasoning_provenance["shadow_used"] = _commander_reasoning_flag(
            bundle_out,
            dict(bundle_out.get("commander_summary") or {}),
            "shadow_used",
        )
        reasoning_provenance["strategist_fallback_used"] = (
            _commander_reasoning_flag(
                bundle_out,
                dict(bundle_out.get("commander_summary") or {}),
                "strategist_fallback_used",
            )
            or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
        )
        if commander_source_priority:
            reasoning_provenance["source_priority"] = list(commander_source_priority)
    market_context_human = dict(bundle_out.get("market_context_human") or {})
    scanner_reason_human = enrich_scanner_reason_from_evidence(
        dict(bundle_out.get("scanner_reason_human") or {}),
        dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
    )
    monitor_reason_human = dict(bundle_out.get("monitor_reason_human") or {})
    canonical_strategist = (
        canonical_agent_artifacts.get("strategist")
        if isinstance(canonical_agent_artifacts.get("strategist"), dict)
        else bundle_out.get("strategist")
        if isinstance(bundle_out.get("strategist"), dict)
        else {}
    )
    canonical_scanner = (
        canonical_agent_artifacts.get("scanner")
        if isinstance(canonical_agent_artifacts.get("scanner"), dict)
        else bundle_out.get("scanner")
        if isinstance(bundle_out.get("scanner"), dict)
        else {}
    )
    canonical_monitor = (
        canonical_agent_artifacts.get("monitor")
        if isinstance(canonical_agent_artifacts.get("monitor"), dict)
        else bundle_out.get("monitor")
        if isinstance(bundle_out.get("monitor"), dict)
        else {}
    )
    selected_symbol = str(
        scanner_reason_human.get("selected_symbol")
        or canonical_scanner.get("selected_symbol")
        or canonical_scanner.get("top_stock")
        or (bundle_out.get("scanner_summary") or {}).get("selected_symbol")
        or ((bundle_out.get("execution") or {}).get("symbol"))
        or ""
    ).strip()
    strategist_evidence_trace = _build_strategist_evidence_trace(
        canonical_strategist,
        selected_symbol=selected_symbol,
        fallback_market_titles=market_context_human.get("market_news_titles"),
        fallback_candidate_titles=market_context_human.get("candidate_news_titles"),
    )
    scanner_selection_trace = _build_scanner_selection_trace(scanner_reason_human, canonical_scanner)
    ranked_symbols = [
        str(row.get("symbol") or "").strip()
        for row in list(scanner_selection_trace.get("ranked_candidates") or [])
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    ]
    news_symbol_linkage = build_news_symbol_linkage_view(
        strategist_summary=canonical_strategist,
        strategist_raw_input=dict(bundle_out.get("strategist_evidence") or (bundle_out.get("evidence") or {}).get("strategist") or {}),
        strategist_parsed_output=dict((bundle_out.get("strategist_summary") or {}).get("llm_parsed_output") or {}),
        selected_symbol=selected_symbol,
        top_ranked_symbols=ranked_symbols or canonical_scanner.get("top_ranked_symbols") or [],
    )
    monitor_stop_thresholds = (
        ((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"))
        if isinstance((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"), dict)
        else canonical_monitor.get("thresholds")
        if isinstance(canonical_monitor.get("thresholds"), dict)
        else canonical_monitor.get("threshold_snapshot")
        if isinstance(canonical_monitor.get("threshold_snapshot"), dict)
        else {}
    )
    monitor_stop_policy_trace = _build_monitor_stop_policy_trace(
        canonical_monitor,
        monitor_stop_thresholds,
    )
    monitor_blocker_trace = _build_monitor_blocker_trace(monitor_reason_human)
    market_context_human.setdefault("candidate_hints", strategist_evidence_trace.get("candidate_hints") or [])
    market_context_human.setdefault("market_headlines", strategist_evidence_trace.get("market_headlines") or [])
    market_context_human.setdefault("symbol_headlines", strategist_evidence_trace.get("symbol_headlines") or [])
    market_context_human.setdefault("strategist_evidence_trace", dict(strategist_evidence_trace))
    market_context_human.setdefault("news_symbol_linkage", dict(news_symbol_linkage))
    scanner_reason_human.setdefault("scanner_selection_trace", dict(scanner_selection_trace))
    scanner_reason_human.setdefault("ranked_candidates", list(scanner_selection_trace.get("ranked_candidates") or []))
    scanner_reason_human.setdefault("selection_reason", scanner_selection_trace.get("selection_reason"))
    scanner_reason_human.setdefault(
        "selected_symbol_score_drivers",
        dict(scanner_selection_trace.get("selected_symbol_score_drivers") or {}),
    )
    monitor_reason_human.setdefault("monitor_stop_policy_trace", dict(monitor_stop_policy_trace))
    monitor_reason_human.setdefault("monitor_blocker_trace", dict(monitor_blocker_trace))
    story_out = {
        "schema_version": "trade_story_input.v1",
        "day": str(bundle_out.get("day") or ""),
        "trade_id": str(bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
        "story_id": str(bundle_out.get("story_id") or ""),
        "run_id": str(bundle_out.get("run_id") or ""),
        "symbol": str((bundle_out.get("execution") or {}).get("symbol") or ""),
        "action": str((bundle_out.get("execution") or {}).get("action") or ""),
        "status": str(bundle_out.get("trade_lifecycle_status") or "closed"),
        "story_type": str(story_contract.get("story_type") or ""),
        "execution_mode_label": str(story_contract.get("execution_mode_label") or ""),
        "market_context_human": market_context_human,
        "scanner_reason_human": scanner_reason_human,
        "filters_human": enrich_filters_from_evidence(
            dict(bundle_out.get("filters_human") or {}),
            dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
            selected_symbol=str(((bundle_out.get("scanner_reason_human") or {}).get("selected_symbol")) or ((bundle_out.get("execution") or {}).get("symbol")) or ""),
        ),
        "monitor_reason_human": monitor_reason_human,
        "guard_reason_human": dict(bundle_out.get("guard_reason_human") or {}),
        "execution_outcome_human": dict(bundle_out.get("execution_outcome_human") or {}),
        "reporter_status_human": dict(bundle_out.get("reporter_status_human") or {}),
        "operator_conclusion_human": dict(bundle_out.get("operator_conclusion_human") or {}),
        "timeline": list(bundle_out.get("timeline") or []),
        "warnings": list(bundle_out.get("warnings") or []),
        "strategist_evidence": dict(bundle_out.get("strategist_evidence") or (bundle_out.get("evidence") or {}).get("strategist") or {}),
        "strategist_candidate_hints": list(strategist_evidence_trace.get("candidate_hints") or [])[:8],
        "strategist_market_headlines": list(strategist_evidence_trace.get("market_headlines") or [])[:3],
        "strategist_symbol_headlines": list(strategist_evidence_trace.get("symbol_headlines") or [])[:3],
        "strategist_evidence_trace": dict(strategist_evidence_trace),
        "news_symbol_linkage": dict(news_symbol_linkage),
        "scanner_evidence": dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
        "scanner_selection_trace": dict(scanner_selection_trace),
        "monitor_timeline": dict(bundle_out.get("monitor_timeline") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
        "monitor_stop_policy_trace": dict(monitor_stop_policy_trace),
        "monitor_blocker_trace": dict(monitor_blocker_trace),
        "canonical_agent_artifacts": canonical_agent_artifacts,
        "evidence_provenance": evidence_provenance,
        "section_provenance": dict(section_provenance),
        "reasoning_trace": dict(reasoning_trace),
        "reasoning_provenance": dict(reasoning_provenance),
        "evidence_source": "canonical" if any(
            str(source or "").strip().lower() == "canonical"
            for source in evidence_provenance.values()
        ) else "direct_artifact",
        "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
    }
    story_out["strategist_feedback_input"] = build_strategist_feedback_input_view(story_out)
    return story_out


def render_bundle_markdown(out: Dict[str, Any]) -> str:
    story_contract = out.get("story_contract") if isinstance(out.get("story_contract"), dict) else {}
    lines: List[str] = []
    lines.append(f"# Aggregated Execution Bundle ({out.get('run_id')})")
    lines.append("")
    lines.append(f"- day: **{out.get('day')}**")
    lines.append(f"- story_anchor: **{story_contract.get('story_anchor') or '-'}**")
    lines.append(f"- story_type: **{story_contract.get('story_type') or '-'}**")
    lines.append(f"- execution_mode: **{story_contract.get('execution_mode_label') or '-'}**")
    lines.append("")
    sections = [
        ("Market Context", out.get("market_context_human")),
        ("Why This Symbol", out.get("scanner_reason_human")),
        ("Filters / Gates", out.get("filters_human")),
        ("Monitor / Trigger Reasoning", out.get("monitor_reason_human")),
        ("Guard / Approval", out.get("guard_reason_human")),
        ("Execution Outcome", out.get("execution_outcome_human")),
        ("Reporter Status", out.get("reporter_status_human")),
        ("Operator Conclusion", out.get("operator_conclusion_human")),
    ]
    for title, section in sections:
        data = section if isinstance(section, dict) else {}
        lines.append(f"## {title}")
        lines.append("")
        if data.get("summary"):
            lines.append(str(data.get("summary")))
            lines.append("")
        for bullet in list(data.get("bullets") or [])[:8]:
            lines.append(f"- {bullet}")
        lines.append("")
    lines.append("## Timeline")
    lines.append("")
    for row in list(out.get("timeline") or [])[:10]:
        if not isinstance(row, dict):
            continue
        lines.append(f"- {row.get('step')}: {row.get('summary') or '-'}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    for key, value in dict(out.get("artifacts") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def render_summary_markdown(out: Dict[str, Any]) -> str:
    bundles = out.get("bundles") if isinstance(out.get("bundles"), list) else []
    lines: List[str] = []
    lines.append(f"# Live Execution Bundles ({out.get('day')})")
    lines.append("")
    lines.append(f"- bundle_count: **{out.get('bundle_count')}**")
    lines.append(f"- canonical_trades_root: `{out.get('canonical_trades_root')}`")
    lines.append("")
    if not bundles:
        lines.append("No executed BUY/SELL runs were found for the selected day.")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Bundles")
    lines.append("")
    for row in bundles:
        lines.append(
            f"- `{row.get('run_id')}` {row.get('action')} {row.get('symbol')} x{row.get('qty')} "
            f"story=`{row.get('story_type')}` report=`{row.get('trade_report_json_path')}`"
        )
    lines.append("")
    return "\n".join(lines)
