from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from libs.runtime.dates import kst_day_str, to_kst
from libs.runtime.decision_observability import (
    build_entry_blocker_surface,
    build_commander_route_observability_surface,
    build_monitor_no_trade_surface,
    build_scanner_monitor_handoff_surface,
    build_strategist_policy_resolution_surface,
)
from libs.runtime.commander_memory_application_trace import (
    build_monitor_commander_memory_application_trace,
    build_scanner_commander_memory_application_trace,
)
from libs.runtime.strategist_explanation import build_strategist_explanation_fields
from libs.runtime.strategist_packet_visibility import build_strategist_memory_packet_visibility


AGENT_OUTPUT_SCHEMA_VERSION = "agent_output.v1"
AGENT_VALIDATION_SCHEMA_VERSION = "agent_output_validation.v1"


class AgentOutput(TypedDict, total=False):
    schema_version: str
    agent: str
    run_id: str
    day: str
    ts: str
    phase: str
    symbol: str
    status: str
    evidence_refs: Dict[str, Any]
    source_refs: Dict[str, Any]
    validation: Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _clip(value: Any, *, max_len: int = 280) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _listify(values: Any, *, limit: int = 8, max_len: int = 180) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = _clip(value, max_len=max_len)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_list(value: Any, *, limit: int = 8) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in value:
        if isinstance(row, dict):
            out.append(dict(row))
        if len(out) >= max(1, int(limit)):
            break
    return out


def _scanner_candidate_visibility_limit(scanner_output: Dict[str, Any]) -> int:
    policy = _dict(scanner_output.get("applied_scanner_policy"))
    entry_control = _dict(policy.get("entry_control"))
    raw = (
        entry_control.get("max_priority_rank")
        or policy.get("max_priority_rank")
        or scanner_output.get("max_priority_rank")
        or 5
    )
    return min(10, max(5, _safe_int(raw, 5)))


def _dedupe_text(values: List[str], *, limit: int = 10, max_len: int = 180) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clip(value, max_len=max_len)
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _format_trace_number(value: Any, *, digits: int = 3, missing: str = "not_captured") -> str:
    if value in (None, ""):
        return missing
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return _clip(value, max_len=24) or missing


def _build_strategist_trace_summary(
    *,
    strategist_output: Dict[str, Any],
    global_signal: Dict[str, Any],
    macro_overlay: Dict[str, Any],
    news_context: Dict[str, Any],
    themes: List[str],
    avoid_themes: List[str],
    market_regime: str,
    market_sentiment: str,
    playbook: str,
) -> Dict[str, Any]:
    fear_index = _dict(global_signal.get("fear_index"))
    reason_chain = _listify(strategist_output.get("reason_chain"), limit=8, max_len=180)
    if not reason_chain:
        strategy_policy_summary = _dict(strategist_output.get("strategy_policy_summary"))
        market_policy = _dict(strategy_policy_summary.get("market_policy"))
        reason_chain = _listify(market_policy.get("reason_chain"), limit=8, max_len=180)
    news_targets = _listify(strategist_output.get("news_query_targets"), limit=8, max_len=80)
    stress_flags = _listify(macro_overlay.get("stress_flags"), limit=6, max_len=60)
    headline_count = _safe_int(
        news_context.get("headline_count")
        or strategist_output.get("news_total_headlines")
        or strategist_output.get("market_news_total_headlines")
    )
    query_count = _safe_int(
        strategist_output.get("market_news_query_count")
        or len(news_targets)
    )
    global_sentiment_score = strategist_output.get("global_sentiment_score")
    vix_level = (
        fear_index.get("level")
        if fear_index.get("level") not in (None, "")
        else global_signal.get("vix_level")
        if global_signal.get("vix_level") not in (None, "")
        else macro_overlay.get("vix_level")
    )
    missing_flags: List[str] = []
    if global_sentiment_score in (None, ""):
        missing_flags.append("global_sentiment_score_missing")
    if vix_level in (None, ""):
        missing_flags.append("vix_level_missing")
    if headline_count <= 0:
        missing_flags.append("news_headlines_missing")
    if not reason_chain:
        missing_flags.append("reason_chain_missing")
    summary = (
        f"Strategist used regime={market_regime or 'not_captured'}, sentiment={market_sentiment or 'not_captured'}, "
        f"playbook={playbook or 'not_captured'}, global_sentiment={_format_trace_number(global_sentiment_score, digits=3)}, "
        f"vix={_format_trace_number(vix_level, digits=2)}, headlines={headline_count}, targets={query_count}."
    )
    highlights = _dedupe_text(
        [
            f"Regime {market_regime or 'not_captured'} / playbook {playbook or 'not_captured'}",
            (
                "Themes: "
                + (", ".join(themes[:4]) if themes else "none")
                + (" | avoid: " + ", ".join(avoid_themes[:4]) if avoid_themes else "")
            ),
            (
                f"Sentiment { _format_trace_number(global_sentiment_score, digits=3) } / "
                f"VIX { _format_trace_number(vix_level, digits=2) } / "
                f"stress {', '.join(stress_flags) if stress_flags else 'none'}"
            ),
            f"News evidence: {headline_count} headlines across {query_count} targets",
        ],
        limit=6,
        max_len=220,
    )
    return {
        "summary": _clip(summary, max_len=320),
        "highlights": highlights,
        "reason_chain": reason_chain,
        "headline_count": headline_count,
        "news_query_count": query_count,
        "news_query_targets": news_targets,
        "global_sentiment_score": global_sentiment_score,
        "vix_level": vix_level,
        "stress_flags": stress_flags,
        "market_regime": market_regime,
        "market_sentiment": market_sentiment,
        "playbook": playbook,
        "themes": list(themes),
        "avoid_themes": list(avoid_themes),
        "missing_flags": missing_flags,
    }


def _build_strategist_decision_frame(
    *,
    state: Dict[str, Any],
    strategist_output: Dict[str, Any],
    market_regime: str,
    market_sentiment: str,
    playbook: str,
    themes: List[str],
    avoid_themes: List[str],
) -> Dict[str, Any]:
    event_payload = _dict(state.get("strategist_decision_frame"))
    if event_payload:
        out = dict(event_payload)
        theme_packet = _dict(strategist_output.get("theme_strength_packet"))
        if theme_packet and not _dict(out.get("theme_strength_packet")):
            out["theme_strength_packet"] = theme_packet
        if not out.get("theme_source") and (theme_packet.get("source") or strategist_output.get("theme_source")):
            out["theme_source"] = _clip(strategist_output.get("theme_source") or theme_packet.get("source"), max_len=80)
        if not out.get("theme_source_status") and (theme_packet.get("status") or strategist_output.get("theme_source_status")):
            out["theme_source_status"] = _clip(
                strategist_output.get("theme_source_status") or theme_packet.get("status"),
                max_len=80,
            )
        if not out.get("theme_source_reason") and (theme_packet.get("reason") or strategist_output.get("theme_source_reason")):
            out["theme_source_reason"] = _clip(
                strategist_output.get("theme_source_reason") or theme_packet.get("reason"),
                max_len=160,
            )
        if not out.get("available_themes") and isinstance(strategist_output.get("available_themes"), list):
            out["available_themes"] = list(strategist_output.get("available_themes") or [])[:8]
        if not out.get("selected_themes") and isinstance(strategist_output.get("selected_themes"), list):
            out["selected_themes"] = _listify(strategist_output.get("selected_themes"), limit=5, max_len=80)
        if not out.get("theme_strategy") and isinstance(strategist_output.get("theme_strategy"), dict):
            out["theme_strategy"] = _dict(strategist_output.get("theme_strategy"))
        return out
    strategy_policy_summary = _dict(strategist_output.get("strategy_policy_summary"))
    strategy_memory = _dict(strategist_output.get("strategy_memory"))
    theme_packet = _dict(strategist_output.get("theme_strength_packet"))
    theme_strength = _dict(strategist_output.get("theme_strength")) or _dict(theme_packet.get("theme_scores"))
    reason_chain = _listify(
        strategist_output.get("reason_chain")
        or _dict(strategy_policy_summary.get("market_policy")).get("reason_chain"),
        limit=8,
        max_len=180,
    )
    return {
        "market_regime": market_regime,
        "market_sentiment": market_sentiment,
        "playbook": playbook,
        "themes": list(themes),
        "selected_themes": _listify(strategist_output.get("selected_themes"), limit=5, max_len=80),
        "avoid_themes": list(avoid_themes),
        "scanner_bias": _clip(strategist_output.get("scanner_bias"), max_len=80),
        "scanner_priority": _listify(strategist_output.get("scanner_priority"), limit=8, max_len=80),
        "trade_aggressiveness": _clip(strategist_output.get("trade_aggressiveness"), max_len=40),
        "risk_tone": _clip(strategist_output.get("risk_tone"), max_len=40),
        "monitor_guidance": _clip(strategist_output.get("monitor_guidance"), max_len=80),
        "report_focus": _listify(strategist_output.get("report_focus"), limit=8, max_len=80),
        "strategy_memory": strategy_memory,
        "reason_chain": reason_chain,
        "strategy_policy_summary": strategy_policy_summary,
        "theme_strength": theme_strength,
        "theme_strength_packet": theme_packet,
        "available_themes": list(strategist_output.get("available_themes") or [])[:8]
        if isinstance(strategist_output.get("available_themes"), list)
        else [],
        "theme_strategy": _dict(strategist_output.get("theme_strategy")),
        "theme_source": _clip(strategist_output.get("theme_source") or theme_packet.get("source"), max_len=80),
        "theme_source_status": _clip(
            strategist_output.get("theme_source_status") or theme_packet.get("status"),
            max_len=80,
        ),
        "theme_source_reason": _clip(
            strategist_output.get("theme_source_reason") or theme_packet.get("reason"),
            max_len=160,
        ),
    }


def _build_strategist_news_evidence_ranked(
    *,
    state: Dict[str, Any],
    strategist_output: Dict[str, Any],
    news_context: Dict[str, Any],
    market_news_context: Dict[str, Any],
    candidate_news_context: Dict[str, Any],
) -> Dict[str, Any]:
    event_payload = _dict(state.get("strategist_news_evidence_ranked"))
    if event_payload:
        return dict(event_payload)
    return {
        "news_query_targets": _listify(strategist_output.get("news_query_targets"), limit=12, max_len=80),
        "candidate_news_ranked": list(candidate_news_context.get("ranked_rows") or [])[:8],
        "market_news_ranked": list(market_news_context.get("ranked_rows") or [])[:8],
        "candidate_news_context": dict(candidate_news_context),
        "market_news_context": dict(market_news_context),
        "news_context": dict(news_context),
    }


def _build_global_sentiment_signal_payload(
    *,
    state: Dict[str, Any],
    global_signal: Dict[str, Any],
    macro_overlay: Dict[str, Any],
) -> Dict[str, Any]:
    event_payload = _dict(state.get("strategist_global_sentiment_breakdown"))
    if event_payload:
        return dict(event_payload)
    fear_index = _dict(global_signal.get("fear_index"))
    return {
        "score": global_signal.get("score"),
        "status": _clip(global_signal.get("status"), max_len=40),
        "source": _clip(global_signal.get("source"), max_len=80),
        "fear_index": {
            "level": fear_index.get("level"),
            "change_pct": fear_index.get("change_pct"),
            "level_pressure": fear_index.get("level_pressure"),
        },
        "index_moves": _dict(global_signal.get("index_moves")),
        "macro_moves": _dict(global_signal.get("macro_moves")),
        "stress_flags": _listify(macro_overlay.get("stress_flags"), limit=8, max_len=80),
    }


def _build_scanner_trace_summary(
    *,
    symbol: str,
    selected_rank: int,
    universe_size: int,
    selected_score_total: float,
    margin_vs_second: float,
    selected_score_breakdown: Dict[str, Any],
    selected: Dict[str, Any],
    candidate_preview: List[Dict[str, Any]],
    selection_summary: str,
    scanner_bias_applied: bool = False,
    scanner_bias_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    selected_candidate = _dict(selected.get("candidate"))
    selected_sources = _listify(selected_candidate.get("sources"), limit=6, max_len=60)
    positive_factors = [f"{k}:{_safe_float(v, 0.0):.3f}" for k, v in selected_score_breakdown.items() if _safe_float(v, 0.0) > 0][:4]
    negative_factors = [f"{k}:{_safe_float(v, 0.0):.3f}" for k, v in selected_score_breakdown.items() if _safe_float(v, 0.0) < 0][:4]
    runner_ups = [
        {
            "symbol": str(row.get("symbol") or ""),
            "rank": _safe_int(row.get("rank")),
            "score_total": _safe_float(row.get("score_total")),
            "why": _clip(row.get("why"), max_len=160),
        }
        for row in candidate_preview[1:3]
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    ]
    missing_flags: List[str] = []
    if not symbol:
        missing_flags.append("selected_symbol_missing")
    if universe_size <= 0:
        missing_flags.append("candidate_pool_missing")
    if not positive_factors and not negative_factors:
        missing_flags.append("score_breakdown_missing")
    bias_summary_dict = _dict(scanner_bias_summary)
    summary = (
        f"Scanner selected {symbol or 'not_captured'} rank #{selected_rank or 0}/{universe_size or 0} "
        f"with score={selected_score_total:.3f} and margin_vs_second={margin_vs_second:.3f}."
    )
    highlights = _dedupe_text(
        [
            f"Selected {symbol or 'not_captured'} rank #{selected_rank or 0} out of {universe_size or 0}",
            f"Score {selected_score_total:.3f} with margin {margin_vs_second:.3f} vs runner-up",
            f"Source mix: {', '.join(selected_sources) if selected_sources else 'not_captured'}",
            (
                "Positive factors: " + ", ".join(positive_factors)
                if positive_factors
                else "Positive factors were not captured"
            ),
            (
                "Negative factors: " + ", ".join(negative_factors)
                if negative_factors
                else "Negative factors were not captured"
            ),
            (
                "Bias: " + str(bias_summary_dict.get("summary") or "")
                if scanner_bias_applied and str(bias_summary_dict.get("summary") or "").strip()
                else ""
            ),
        ],
        limit=6,
        max_len=220,
    )
    return {
        "summary": _clip(selection_summary or summary, max_len=320),
        "highlights": highlights,
        "selected_symbol": symbol,
        "runner_up_symbol": str(runner_ups[0].get("symbol") or "") if runner_ups else "",
        "selected_rank": selected_rank,
        "universe_size": universe_size,
        "candidate_count": universe_size,
        "selected_score_total": selected_score_total,
        "margin_vs_second": margin_vs_second,
        "selected_sources": selected_sources,
        "critical_positive_factors": positive_factors,
        "critical_negative_factors": negative_factors,
        "top_candidates": candidate_preview[:3],
        "runner_ups": runner_ups,
        "scanner_bias_applied": bool(scanner_bias_applied),
        "scanner_bias_summary": bias_summary_dict,
        "missing_flags": missing_flags,
    }


def _build_scanner_candidate_ranking_table(
    *,
    state: Dict[str, Any],
    candidate_preview: List[Dict[str, Any]],
) -> Dict[str, Any]:
    event_payload = _dict(state.get("scanner_candidate_ranking_table"))
    if event_payload:
        rows = list(event_payload.get("rows") or [])
        return {
            "tie_break_rule": _clip(event_payload.get("tie_break_rule"), max_len=120),
            "rows": [dict(row) for row in rows if isinstance(row, dict)],
        }
    return {
        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
        "rows": [dict(row) for row in candidate_preview],
    }


def _build_scanner_candidate_selection_reason(
    *,
    state: Dict[str, Any],
    selected_symbol: str,
    selected_rank: int,
    selected_score_total: float,
    margin_vs_second: float,
    critical_positive_factors: List[str],
    critical_negative_factors: List[str],
    selection_summary: str,
    runner_ups: List[Dict[str, Any]],
    selected: Dict[str, Any],
) -> Dict[str, Any]:
    event_payload = _dict(state.get("scanner_candidate_selection_reason"))
    if event_payload:
        return dict(event_payload)
    selected_candidate = _dict(selected.get("candidate"))
    why_selected = _listify(selected.get("top_reasons"), limit=6, max_len=180)
    if not why_selected:
        why_selected = _dedupe_text(
            [
                f"highest total score ({selected_score_total:.3f})" if selected_score_total else "",
                f"confidence {_safe_float(selected.get('confidence')):.2f} and risk {_safe_float(selected.get('risk_score')):.2f}",
                f"source mix: {', '.join(_listify(selected_candidate.get('sources'), limit=4, max_len=40))}",
            ],
            limit=4,
            max_len=180,
        )
    return {
        "selected_symbol": selected_symbol,
        "selected_rank": selected_rank,
        "selected_score_total": selected_score_total,
        "margin_vs_second": margin_vs_second,
        "critical_positive_factors": list(critical_positive_factors),
        "critical_negative_factors": list(critical_negative_factors),
        "selection_summary": selection_summary,
        "why_selected": why_selected,
        "runner_ups_lost": list(runner_ups),
        "entry_compatibility_score": _safe_float(selected.get("entry_compatibility_score"), 0.0),
        "compatibility_bias": _safe_float(selected.get("compatibility_bias"), 0.0),
        "expected_monitor_block_reason": _clip(selected.get("expected_monitor_block_reason"), max_len=120),
        "compatibility_trace": _dict(selected.get("compatibility_trace")),
        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
        "final_decision_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties.",
    }


def _monitor_decision_summary(
    *,
    decision_phase: str,
    primary_reason_text: str,
    threshold_snapshot: Dict[str, Any],
    signal_snapshot: Dict[str, Any],
    missing_inputs: List[str],
) -> str:
    if missing_inputs:
        missing = ",".join([_clip(item, max_len=24) for item in list(missing_inputs)[:3] if _clip(item, max_len=24)])
        return _clip(f"Decision: insufficient data ({missing or 'unavailable'})", max_len=120)
    phase = str(decision_phase or "").strip().lower()
    reason = _clip(primary_reason_text, max_len=64) or "unavailable"
    if phase == "entry":
        entry_signal = _clip(_dict(signal_snapshot).get("entry_pattern"), max_len=42) or reason
        entry_thresholds = _dict(_dict(threshold_snapshot).get("entry_thresholds"))
        threshold_text = (
            _clip(entry_thresholds.get("max_extended_from_vwap_pct"), max_len=24)
            or _clip(entry_thresholds.get("volume_ratio_min"), max_len=24)
            or "thresholds"
        )
        return _clip(f"Entry: {entry_signal} met with {threshold_text} -> BUY", max_len=120)
    if phase == "exit":
        trigger = _clip(_dict(signal_snapshot).get("exit_triggered_rule"), max_len=48) or reason
        return _clip(f"Exit: {trigger}", max_len=120)
    if phase == "hold":
        return "Hold: conditions stable, no exit trigger"
    return _clip(f"No action: {reason}", max_len=120)


def _phase(state: Dict[str, Any]) -> str:
    return str(state.get("runtime_phase") or state.get("phase") or "").strip()


def _run_ts(state: Dict[str, Any]) -> str:
    for key in ("started_at", "ts", "tick_ts_iso", "now_iso"):
        value = str(state.get(key) or "").strip()
        if value:
            return value
    tick_epoch = _safe_int(state.get("tick_ts"), 0)
    if tick_epoch > 0:
        return datetime.fromtimestamp(tick_epoch, tz=timezone.utc).isoformat()
    return _utc_now_iso()


def _parse_day_from_timestamp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) == 10 and text[4:5] == "-" and text[7:8] == "-":
        return text
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        return kst_day_str(datetime.fromisoformat(normalized))
    except Exception:
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
    return ""


def _run_day(state: Dict[str, Any]) -> str:
    for key in ("day", "trade_day", "session_day", "runtime_day"):
        value = str(state.get(key) or "").strip()
        if len(value) == 10 and value[4:5] == "-" and value[7:8] == "-":
            return value
    for key in ("started_at", "ts", "tick_ts_iso", "now_iso"):
        resolved = _parse_day_from_timestamp(str(state.get(key) or "").strip())
        if resolved:
            return resolved
    tick_epoch = _safe_int(state.get("tick_ts"), 0)
    if tick_epoch > 0:
        return kst_day_str(datetime.fromtimestamp(tick_epoch, tz=timezone.utc))
    return kst_day_str(to_kst(datetime.now(timezone.utc)))


def _base_output(state: Dict[str, Any], *, agent: str, symbol: str = "", status: str = "ok") -> AgentOutput:
    return {
        "schema_version": AGENT_OUTPUT_SCHEMA_VERSION,
        "agent": str(agent or "").strip(),
        "run_id": str(state.get("run_id") or "").strip(),
        "day": _run_day(state),
        "ts": _run_ts(state),
        "phase": _phase(state),
        "symbol": str(symbol or "").strip(),
        "status": str(status or "ok").strip(),
    }


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _required_keys_for_agent(agent: str) -> List[str]:
    base = ["schema_version", "agent", "run_id", "day", "ts", "phase", "status"]
    specific: Dict[str, List[str]] = {
        "strategist": [
            "market_regime",
            "market_context_summary",
            "news_evidence_summary",
            "sentiment_evidence_summary",
            "volatility_context",
            "strategy_thesis",
            "playbook",
            "market_context",
            "news_context",
            "strategy_frame",
            "policy_selected",
            "llm_trace",
            "decision_summary",
            "llm_metadata_summary",
            "source_refs",
        ],
        "scanner": [
            "candidate_pool_snapshot",
            "filter_funnel",
            "universe_size",
            "candidate_list_summary",
            "ranking_table",
            "selected_symbol",
            "selected_rank",
            "selection_reason",
            "selection_reason_detail",
            "rejection_summary",
            "filter_feature_summary",
            "evidence_refs",
        ],
        "monitor": [
            "position_snapshot",
            "monitor_evaluation",
            "monitor_action_decision",
            "thresholds_guards_used",
            "threshold_snapshot",
            "signal_snapshot",
            "market_snapshot_refs",
            "evaluation_summary",
            "decision",
            "decision_phase",
            "decision_action",
            "decision_status",
            "decision_summary",
            "primary_reason_code",
            "primary_reason_text",
            "secondary_reason_codes",
            "intent_emitted",
            "evidence_quality",
            "missing_inputs",
            "generated_at",
            "decision_reason_chain",
            "trigger_details",
            "evidence_refs",
        ],
        "supervisor": [
            "invoked_agents",
            "command",
            "decision",
            "approval_result",
            "reason",
            "blocked_allowed_details",
        ],
        "executor": [
            "action",
            "order_request_summary",
            "execution_enabled",
            "approval_mode",
            "broker_result",
            "final_execution_status",
            "failure_reason",
        ],
        "commander": [
            "mode",
            "phase",
            "path",
            "runtime_mode",
            "runtime_phase",
            "selected_route",
            "route_reason_codes",
            "route_reason_text",
            "open_position_count",
            "open_position_symbols",
            "strategist_cache_used",
            "strategist_blocked",
            "cooldown_applied",
            "incident_state",
            "portfolio_preflight_result",
            "generated_at",
            "session_type",
            "market_clock_phase",
            "portfolio_state_summary",
            "market_regime_summary",
            "goal",
            "agent_invocation_plan",
            "decision_checkpoints",
            "final_runtime_path",
            "final_reason",
            "handoff_instruction",
            "invoked_agents",
            "command",
            "decision",
            "approval_result",
            "reason",
            "blocked_allowed_details",
        ],
    }
    out = list(base)
    out.extend(list(specific.get(str(agent or "").strip().lower(), [])))
    return out


def _required_keys_for_artifact(obj: Dict[str, Any]) -> List[str]:
    artifact = dict(obj or {}) if isinstance(obj, dict) else {}
    agent = str(artifact.get("agent") or "").strip().lower()
    mode = str(artifact.get("mode") or "").strip().lower()
    if agent == "commander" and (mode == "shadow" or bool(artifact.get("shadow_only"))):
        base = ["schema_version", "agent", "run_id", "day", "ts", "phase", "status"]
        specific = [
            "mode",
            "decision",
            "strategist_action_recommendation",
            "llm_call_advice",
            "suggested_action",
            "next_action_recommendation",
            "no_trade_reason_code",
            "reason_summary",
            "observations",
            "actual_runtime",
            "monitor_gate_details",
            "context_delta_summary",
            "pre_strategist_shadow_snapshot",
            "post_strategist_assessment",
            "post_monitor_assessment",
            "end_of_cycle_summary",
            "shadow_only",
            "generated_at",
        ]
        return base + specific
    return _required_keys_for_agent(agent)


def validate_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    obj = dict(artifact or {}) if isinstance(artifact, dict) else {}
    expected = _required_keys_for_artifact(obj)
    present: List[str] = []
    missing: List[str] = []
    for key in expected:
        if _is_present(obj.get(key)):
            present.append(key)
        else:
            missing.append(key)
    completeness = float(len(present)) / float(len(expected)) if expected else 1.0
    if not missing:
        status = "ok"
    elif not present:
        status = "invalid"
    else:
        status = "partial"
    return {
        "schema_version": AGENT_VALIDATION_SCHEMA_VERSION,
        "status": status,
        "required_keys_expected": expected,
        "required_keys_present": present,
        "required_keys_missing": missing,
        "completeness_score": completeness,
    }


def build_strategist_output_artifact(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output = _dict(state.get("strategist_output"))
    strategist_llm = _dict(state.get("strategist_llm"))
    strategy_policy = _dict(strategist_output.get("strategy_policy"))
    macro_overlay = _dict(strategist_output.get("macro_stress_overlay"))
    news_context = _dict(strategist_output.get("news_context"))
    global_signal = _dict(state.get("global_signal"))
    fear_index = _dict(global_signal.get("fear_index"))
    evidence_log_path = str(Path("data/evidence_ledger/events.jsonl"))
    themes = _listify(strategist_output.get("themes"), limit=6)
    avoid_themes = _listify(strategist_output.get("avoid_themes"), limit=6)
    market_news_context = _dict(strategist_output.get("market_news_context"))
    candidate_news_context = _dict(strategist_output.get("candidate_news_context"))
    playbook = _clip(strategist_output.get("playbook"), max_len=80)
    market_regime = _clip(strategist_output.get("market_regime"), max_len=80)
    market_sentiment = _clip(strategist_output.get("market_sentiment"), max_len=80)
    selected = _dict(state.get("selected"))
    selected_score_total = _safe_float(selected.get("score_total") if selected.get("score_total") is not None else selected.get("score"), 0.0)
    score_breakdown = _dict(selected.get("score_breakdown"))
    positive_factors = [f"{k}:{_safe_float(v, 0.0):.3f}" for k, v in score_breakdown.items() if _safe_float(v, 0.0) > 0][:4]
    negative_factors = [f"{k}:{_safe_float(v, 0.0):.3f}" for k, v in score_breakdown.items() if _safe_float(v, 0.0) < 0][:4]
    decision_status = "blocked" if bool(state.get("strategist_blocked")) else "ready"
    summary = (
        f"Regime {market_regime or 'not_captured'} with playbook {playbook or 'not_captured'}; "
        f"themes {', '.join(themes) if themes else 'none'}."
    )
    artifact = _base_output(state, agent="strategist", status="blocked" if bool(state.get("strategist_blocked")) else "ok")
    trace_summary = _build_strategist_trace_summary(
        strategist_output=strategist_output,
        global_signal=global_signal,
        macro_overlay=macro_overlay,
        news_context=news_context,
        themes=themes,
        avoid_themes=avoid_themes,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        playbook=playbook,
    )
    memory_packet_visibility = build_strategist_memory_packet_visibility(
        state=state,
        strategist_output=strategist_output,
    )
    decision_frame = _build_strategist_decision_frame(
        state=state,
        strategist_output=strategist_output,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        playbook=playbook,
        themes=themes,
        avoid_themes=avoid_themes,
    )
    theme_strength_packet = _dict(strategist_output.get("theme_strength_packet")) or _dict(
        decision_frame.get("theme_strength_packet")
    )
    theme_strength = _dict(strategist_output.get("theme_strength")) or _dict(
        theme_strength_packet.get("theme_scores")
    )
    theme_source = _clip(strategist_output.get("theme_source") or theme_strength_packet.get("source"), max_len=80)
    theme_source_status = _clip(
        strategist_output.get("theme_source_status") or theme_strength_packet.get("status"),
        max_len=80,
    )
    theme_source_reason = _clip(
        strategist_output.get("theme_source_reason") or theme_strength_packet.get("reason"),
        max_len=160,
    )
    theme_source_fallback_used = bool(
        strategist_output.get("theme_source_fallback_used")
        if strategist_output.get("theme_source_fallback_used") is not None
        else theme_strength_packet.get("fallback_used")
    )
    news_evidence_ranked = _build_strategist_news_evidence_ranked(
        state=state,
        strategist_output=strategist_output,
        news_context=news_context,
        market_news_context=market_news_context,
        candidate_news_context=candidate_news_context,
    )
    news_collection_policy = _dict(strategist_output.get("news_collection_policy")) or _dict(
        state.get("news_collection_policy")
    )
    global_sentiment_signal = _build_global_sentiment_signal_payload(
        state=state,
        global_signal=global_signal,
        macro_overlay=macro_overlay,
    )
    commander_context = _dict(strategy_policy.get("commander_context"))
    if not commander_context:
        commander_context = _dict(state.get("commander_decision"))
    strategist_plan = _dict(strategy_policy.get("strategist_plan"))
    market_policy = _dict(strategy_policy.get("market_policy"))
    scanner_policy = _dict(strategy_policy.get("scanner_policy"))
    strategy_scores = _dict(strategist_output.get("strategy_scores")) or _dict(market_policy.get("strategy_scores"))
    rejected_strategy_reasons = _dict(strategist_output.get("rejected_strategy_reasons")) or _dict(
        market_policy.get("rejected_strategy_reasons")
    )
    candidate_watch_policy = _dict(strategist_output.get("candidate_watch_policy")) or _dict(
        scanner_policy.get("candidate_watch_policy")
    )
    strategy_detail = {
        "pre_llm_playbook": _clip(strategist_output.get("pre_llm_playbook"), max_len=80),
        "llm_requested_playbook": _clip(strategist_output.get("llm_requested_playbook"), max_len=80),
        "requested_playbook": _clip(strategist_output.get("requested_playbook"), max_len=80),
        "requested_playbook_source": _clip(strategist_output.get("requested_playbook_source"), max_len=80),
        "final_playbook": _clip(strategist_output.get("final_playbook") or strategist_output.get("playbook"), max_len=80),
        "tactical_strategy": _clip(
            strategist_output.get("tactical_strategy") or market_policy.get("tactical_strategy"),
            max_len=120,
        ),
        "strategy_scores": dict(strategy_scores),
        "rejected_strategy_reasons": dict(rejected_strategy_reasons),
        "candidate_watch_policy": dict(candidate_watch_policy),
    }
    policy_provenance = _dict(strategy_policy.get("provenance"))
    monitor_entry_policy = _dict(strategist_output.get("monitor_entry_policy"))
    policy_rationale = _clip(strategist_output.get("policy_rationale"), max_len=320)
    policy_validation_status = _clip(strategist_output.get("policy_validation_status"), max_len=80)
    policy_source = _clip(strategist_output.get("policy_source"), max_len=80)
    policy_fallback_reason = _clip(strategist_output.get("policy_fallback_reason"), max_len=220)
    policy_validation_issues = _listify(strategist_output.get("policy_validation_issues"), limit=8, max_len=120)
    market_regime_summary = _clip(strategist_output.get("market_regime_summary"), max_len=220)
    confidence = strategist_output.get("confidence")
    selected_playbook = _clip(
        strategist_output.get("selected_playbook")
        or strategist_plan.get("selected_playbook")
        or playbook,
        max_len=80,
    )
    candidate_hypotheses = _dict_list(
        strategist_output.get("candidate_hypotheses")
        if strategist_output.get("candidate_hypotheses") is not None
        else strategist_plan.get("candidate_hypotheses"),
        limit=8,
    )
    symbol_plan = _dict(
        strategist_output.get("symbol_plan")
        if strategist_output.get("symbol_plan") is not None
        else strategist_output.get("symbol_constraints")
    )
    if not symbol_plan:
        symbol_plan = _dict(
            strategist_plan.get("symbol_plan")
            if strategist_plan.get("symbol_plan") is not None
            else strategist_plan.get("symbol_constraints")
        )
    entry_plan = _dict(strategist_output.get("entry_plan"))
    if not entry_plan:
        entry_plan = _dict(strategist_plan.get("entry_plan"))
    exit_plan = _dict(strategist_output.get("exit_plan"))
    if not exit_plan:
        exit_plan = _dict(strategist_plan.get("exit_plan"))
    strategy_horizon_feedback = _dict(strategist_output.get("strategy_horizon_feedback"))
    if not strategy_horizon_feedback:
        strategy_horizon_feedback = _dict(_dict(strategy_policy.get("monitor_policy")).get("strategy_horizon_feedback"))
    strategist_horizon_proposal = _dict(strategist_output.get("strategist_horizon_proposal")) or dict(strategy_horizon_feedback)
    commander_horizon_policy = (
        _dict(strategist_output.get("commander_horizon_policy"))
        or _dict(_dict(strategy_policy.get("monitor_policy")).get("commander_horizon_policy"))
        or _dict(strategy_policy.get("commander_horizon_policy"))
    )
    horizon_context = _dict(strategist_output.get("horizon_context")) or _dict(
        _dict(strategy_policy.get("monitor_policy")).get("horizon_context")
    )
    strategy_summary = _clip(
        strategist_output.get("strategy_summary")
        or strategist_plan.get("strategy_summary")
        or summary,
        max_len=320,
    )
    candidate_symbols_hint = _listify(
        state.get("strategist_candidate_symbols_hint")
        if state.get("strategist_candidate_symbols_hint") is not None
        else state.get("candidate_symbols"),
        limit=10,
        max_len=24,
    )
    news_evidence_missing = not bool(
        list(news_evidence_ranked.get("candidate_news_ranked") or [])
        or list(news_evidence_ranked.get("market_news_ranked") or [])
        or _safe_int(news_context.get("headline_count") or news_context.get("total_headlines"))
    )
    llm_status = str(strategist_llm.get("status") or "").strip().lower()
    fallback_used = bool(strategist_llm.get("blocked")) or llm_status in {"fallback", "error", "blocked"}
    fallback_reason = _clip(
        strategist_llm.get("blocked_reason")
        or strategist_output.get("llm_frame_status")
        or strategist_llm.get("status"),
        max_len=180,
    )
    policy_resolution = build_strategist_policy_resolution_surface(
        strategist_output=strategist_output,
        strategist_llm=strategist_llm,
        commander_context=commander_context,
    )
    explanation_fields = build_strategist_explanation_fields(
        strategist_output={
            **dict(strategist_output),
            "news_evidence_ranked": news_evidence_ranked,
        },
        state=state,
        news_evidence_ranked=news_evidence_ranked,
    )
    strategy_thesis_text = _clip(
        strategist_output.get("news_query_reasoning")
        or strategist_output.get("monitor_guidance")
        or summary,
        max_len=500,
    )
    artifact.update(
        {
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "market_context_summary": summary,
            "news_evidence_summary": _clip(news_context.get("summary") or strategist_output.get("news_query_reasoning"), max_len=400),
            "sentiment_evidence_summary": (
                f"global_sentiment_score={_safe_float(strategist_output.get('global_sentiment_score'), 0.0):.4f}"
                if strategist_output.get("global_sentiment_score") not in (None, "")
                else "global_sentiment_score=not_captured"
            ),
            "volatility_context": {
                "vix_level": fear_index.get("level"),
                "vix_pressure": fear_index.get("level_pressure"),
                "stress_flags": list(macro_overlay.get("stress_flags") or []),
            },
            "strategy_thesis": dict(explanation_fields.get("strategy_thesis") or {}),
            "strategy_thesis_text": strategy_thesis_text,
            "playbook": playbook,
            "pre_llm_playbook": strategy_detail["pre_llm_playbook"],
            "llm_requested_playbook": strategy_detail["llm_requested_playbook"],
            "requested_playbook": strategy_detail["requested_playbook"],
            "requested_playbook_source": strategy_detail["requested_playbook_source"],
            "final_playbook": strategy_detail["final_playbook"],
            "tactical_strategy": strategy_detail["tactical_strategy"],
            "strategy_scores": dict(strategy_detail["strategy_scores"]),
            "rejected_strategy_reasons": dict(strategy_detail["rejected_strategy_reasons"]),
            "candidate_watch_policy": dict(strategy_detail["candidate_watch_policy"]),
            "strategy_detail": dict(strategy_detail),
            "policy_selected": {
                "strategy_policy": _dict(strategist_output.get("strategy_policy")),
                "monitor_guidance": _clip(strategist_output.get("monitor_guidance"), max_len=80),
                "risk_tone": _clip(strategist_output.get("risk_tone"), max_len=40),
                "trade_aggressiveness": _clip(strategist_output.get("trade_aggressiveness"), max_len=40),
            },
            "market_context": {
                "market_structure": _clip(strategist_output.get("market_structure"), max_len=80),
                "market_context_inputs": _dict(strategist_output.get("market_context_inputs")),
                "global_signal": _dict(state.get("global_signal")),
                "macro_stress_overlay": macro_overlay,
                "regime_score": strategist_output.get("regime_score"),
                "sentiment_score": strategist_output.get("sentiment_score"),
            },
            "news_context": {
                "summary": _clip(news_context.get("summary") or strategist_output.get("news_query_reasoning"), max_len=400),
                "news_query_targets": list(strategist_output.get("news_query_targets") or [])[:12],
                "news_collection_policy": news_collection_policy,
                "market_news_context": market_news_context,
                "candidate_news_context": candidate_news_context,
                "key_events": list(strategist_output.get("key_events") or [])[:10],
            },
            "strategy_frame": {
                "market_regime": market_regime,
                "market_sentiment": market_sentiment,
                "themes": themes,
                "selected_themes": _listify(strategist_output.get("selected_themes"), limit=5, max_len=80),
                "avoid_themes": avoid_themes,
                "theme_strength": theme_strength,
                "theme_strength_packet": theme_strength_packet,
                "available_themes": list(strategist_output.get("available_themes") or [])[:8]
                if isinstance(strategist_output.get("available_themes"), list)
                else [],
                "theme_strategy": _dict(strategist_output.get("theme_strategy")),
                "theme_source": theme_source,
                "theme_source_status": theme_source_status,
                "theme_source_reason": theme_source_reason,
                "playbook": playbook,
                "scanner_bias": _clip(strategist_output.get("scanner_bias"), max_len=80),
                "scanner_priority": _listify(strategist_output.get("scanner_priority"), limit=8, max_len=80),
                "monitor_guidance": _clip(strategist_output.get("monitor_guidance"), max_len=80),
                "trade_aggressiveness": _clip(strategist_output.get("trade_aggressiveness"), max_len=40),
                "risk_tone": _clip(strategist_output.get("risk_tone"), max_len=40),
            },
            "llm_trace": {
                "llm_status": _clip(strategist_llm.get("status"), max_len=40),
                "model": _clip(strategist_llm.get("model"), max_len=120),
                "llm_call_trace": _dict(strategist_llm.get("llm_call_trace")),
                "prompt_hash": _clip(strategist_llm.get("prompt_hash"), max_len=80),
                "response_hash": _clip(strategist_llm.get("response_hash"), max_len=80),
                "prompt_ref": _clip(strategist_llm.get("prompt_ref"), max_len=240),
                "response_ref": _clip(strategist_llm.get("response_ref"), max_len=240),
                "blocked": bool(strategist_llm.get("blocked")),
                "blocked_reason": _clip(strategist_llm.get("blocked_reason"), max_len=180),
            },
            "decision_summary": {
                "decision_status": decision_status,
                "selected_symbol": _clip(selected.get("symbol"), max_len=24),
                "selected_score_total": selected_score_total,
                "margin_vs_second": state.get("scanner_margin_vs_second"),
                "critical_positive_factors": positive_factors,
                "critical_negative_factors": negative_factors,
                "selection_summary": _clip(selected.get("why"), max_len=240),
                "strategy_thesis": _clip(
                    strategist_output.get("news_query_reasoning")
                    or strategist_output.get("monitor_guidance")
                    or summary,
                    max_len=320,
                ),
            },
            "decision_frame": decision_frame,
            "theme_strength": theme_strength,
            "theme_strength_packet": theme_strength_packet,
            "available_themes": list(strategist_output.get("available_themes") or [])[:8]
            if isinstance(strategist_output.get("available_themes"), list)
            else [],
            "selected_themes": _listify(strategist_output.get("selected_themes"), limit=5, max_len=80),
            "theme_strategy": _dict(strategist_output.get("theme_strategy")),
            "theme_source": theme_source,
            "theme_source_status": theme_source_status,
            "theme_source_reason": theme_source_reason,
            "theme_source_fallback_used": theme_source_fallback_used,
            "theme_fallback_used": theme_source_fallback_used,
            "candidate_symbols_hint": candidate_symbols_hint,
            "news_evidence_ranked": news_evidence_ranked,
            "news_collection_policy": news_collection_policy,
            "global_sentiment_signal": global_sentiment_signal,
            "fear_index": fear_index,
            "stress_flags": _listify(macro_overlay.get("stress_flags"), limit=8, max_len=80),
            "news_evidence_missing": bool(news_evidence_missing),
            "candidate_symbols_hint_missing": not bool(candidate_symbols_hint),
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
            "commander_context_ref": {
                "source": _clip(
                    (
                        _dict(strategist_output.get("commander_context_ref")).get("source")
                        if isinstance(strategist_output.get("commander_context_ref"), dict)
                        else commander_context.get("source")
                    ),
                    max_len=80,
                ),
                "market_regime": _clip(commander_context.get("market_regime"), max_len=80),
                "session_bias": _clip(commander_context.get("session_bias"), max_len=80),
                "risk_mode": _clip(commander_context.get("risk_mode"), max_len=80),
                "strategist_refresh_requested": bool(
                    strategist_output.get("commander_refresh_requested")
                    if strategist_output.get("commander_refresh_requested") is not None
                    else commander_context.get("strategist_refresh_requested")
                ),
                "strategist_refresh_reason": _clip(
                    strategist_output.get("commander_refresh_reason")
                    or _dict(strategist_output.get("commander_context_ref")).get("strategist_refresh_reason")
                    or commander_context.get("strategist_refresh_reason"),
                    max_len=120,
                ),
                "strategist_refresh_context": _dict(
                    strategist_output.get("commander_refresh_context")
                    or _dict(strategist_output.get("commander_context_ref")).get("strategist_refresh_context")
                    or commander_context.get("strategist_refresh_context")
                ),
                "decision_summary": _clip(
                    (
                        _dict(strategist_output.get("commander_context_ref")).get("decision_summary")
                        if isinstance(strategist_output.get("commander_context_ref"), dict)
                        else commander_context.get("decision_summary")
                    ),
                    max_len=220,
                ),
            },
            "commander_invocation_hint": _clip(
                strategist_output.get("commander_invocation_hint")
                or commander_context.get("strategist_invocation"),
                max_len=80,
            ),
            "commander_llm_policy": _clip(
                strategist_output.get("commander_llm_policy")
                or commander_context.get("llm_policy"),
                max_len=80,
            ),
            "commander_no_trade_reason_code": _clip(
                strategist_output.get("commander_no_trade_reason_code")
                or commander_context.get("no_trade_reason_code"),
                max_len=80,
            ),
            "commander_refresh_requested": bool(
                strategist_output.get("commander_refresh_requested")
                if strategist_output.get("commander_refresh_requested") is not None
                else commander_context.get("strategist_refresh_requested")
            ),
            "commander_refresh_reason": _clip(
                strategist_output.get("commander_refresh_reason")
                or commander_context.get("strategist_refresh_reason"),
                max_len=120,
            ),
            "commander_refresh_context": _dict(
                strategist_output.get("commander_refresh_context")
                or commander_context.get("strategist_refresh_context")
            ),
            "shadow_used": bool(
                strategist_output.get("shadow_used")
                if strategist_output.get("shadow_used") is not None
                else commander_context.get("shadow_used")
            ),
            "strategist_fallback_used": bool(
                strategist_output.get("strategist_fallback_used")
                if strategist_output.get("strategist_fallback_used") is not None
                else commander_context.get("strategist_fallback_used")
            ),
            "selected_playbook": selected_playbook,
            "strategy_horizon_feedback": dict(strategy_horizon_feedback),
            "strategist_horizon_proposal": dict(strategist_horizon_proposal),
            "commander_horizon_policy": dict(commander_horizon_policy),
            "horizon_context": dict(horizon_context),
            "strategy_horizon": _clip(
                strategist_output.get("strategy_horizon") or strategy_horizon_feedback.get("strategy_horizon"),
                max_len=40,
            ),
            "expected_hold_window": _dict(
                strategist_output.get("expected_hold_window")
                or strategy_horizon_feedback.get("expected_hold_window")
            ),
            "exit_guidance": _dict(
                strategist_output.get("exit_guidance")
                or strategy_horizon_feedback.get("exit_guidance")
            ),
            "candidate_hypotheses": candidate_hypotheses,
            "symbol_plan": symbol_plan,
            "entry_plan": entry_plan,
            "exit_plan": exit_plan,
            "policy_provenance": policy_provenance,
            "strategy_summary": strategy_summary,
            "market_regime_summary": market_regime_summary,
            "monitor_entry_policy": monitor_entry_policy,
            "policy_rationale": policy_rationale,
            "policy_source": policy_source,
            "policy_validation_status": policy_validation_status,
            "policy_fallback_used": bool(strategist_output.get("policy_fallback_used")),
            "policy_fallback_reason": policy_fallback_reason,
            "policy_validation_issues": policy_validation_issues,
            "policy_resolution": dict(policy_resolution),
            "strategy_delta_trace": dict(explanation_fields.get("strategy_delta_trace") or {}),
            "strategy_refresh_trace": dict(explanation_fields.get("strategy_refresh_trace") or {}),
            "memory_usage_trace": dict(explanation_fields.get("memory_usage_trace") or {}),
            "news_usage_trace": dict(explanation_fields.get("news_usage_trace") or {}),
            "scanner_handoff": dict(explanation_fields.get("scanner_handoff") or {}),
            "monitor_handoff": dict(explanation_fields.get("monitor_handoff") or {}),
            "conflict_analysis": dict(explanation_fields.get("conflict_analysis") or {}),
            "trade_permission_frame": dict(explanation_fields.get("trade_permission_frame") or {}),
            "responsibility_boundary": dict(explanation_fields.get("responsibility_boundary") or {}),
            "llm_attempted": bool(policy_resolution.get("llm_attempted")),
            "llm_ok": bool(policy_resolution.get("llm_ok")),
            "strategy_memory_snapshot": _dict(strategist_output.get("strategy_memory_snapshot")),
            "strategist_feedback": _dict(strategist_output.get("strategist_feedback")),
            "performance_summary": _dict(strategist_output.get("performance_summary")),
            "llm_error_type": _clip(policy_resolution.get("llm_error_type"), max_len=80),
            "llm_error_message_short": _clip(policy_resolution.get("llm_error_message_short"), max_len=180),
            "latency_ms": policy_resolution.get("latency_ms"),
            "fallback_source": _clip(policy_resolution.get("fallback_source"), max_len=120),
            "fallback_policy_id": _clip(policy_resolution.get("fallback_policy_id"), max_len=120),
            "effective_policy_source": _clip(policy_resolution.get("effective_policy_source"), max_len=120),
            "effective_prompt_version": _clip(policy_resolution.get("effective_prompt_version"), max_len=120),
            "effective_schema_version": _clip(policy_resolution.get("effective_schema_version"), max_len=120),
            "policy_staleness": policy_resolution.get("policy_staleness"),
            "reused_cached_strategy": bool(policy_resolution.get("reused_cached_strategy")),
            "strategy_generation_mode": _clip(policy_resolution.get("strategy_generation_mode"), max_len=40),
            "confidence": confidence,
            "scanner_bias": _clip(strategist_output.get("scanner_bias"), max_len=80),
            "scanner_bias_context": _dict(strategist_output.get("scanner_bias_context")),
            "scanner_bias_summary": _dict(strategist_output.get("scanner_bias_summary")),
            "scanner_bias_validation_status": _clip(
                strategist_output.get("scanner_bias_validation_status"),
                max_len=80,
            ),
            "scanner_bias_validation_issues": _listify(
                strategist_output.get("scanner_bias_validation_issues"),
                limit=8,
                max_len=180,
            ),
            "trace_summary": trace_summary,
            "memory_packet_visibility": memory_packet_visibility,
            "themes": themes,
            "avoid_themes": avoid_themes,
            "llm_metadata_summary": {
                "status": _clip(strategist_llm.get("status"), max_len=40),
                "model": _clip(strategist_llm.get("model"), max_len=120),
                "llm_call_trace": _dict(strategist_llm.get("llm_call_trace")),
                "blocked": bool(strategist_llm.get("blocked")),
                "blocked_reason": _clip(strategist_llm.get("blocked_reason"), max_len=180),
                "prompt_hash": _clip(strategist_llm.get("prompt_hash"), max_len=80),
                "response_hash": _clip(strategist_llm.get("response_hash"), max_len=80),
                "llm_status": _clip(strategist_llm.get("status"), max_len=40),
            },
            "source_refs": {
                "event_names": [
                    "strategist.market_context_snapshot",
                    "strategist.global_sentiment_breakdown",
                    "strategist.news_evidence_ranked",
                    "strategist.decision_frame",
                    "strategist.llm_response_saved",
                ],
                "evidence_log_path": evidence_log_path,
            },
            "evidence_refs": {
                "news_query_targets": list(strategist_output.get("news_query_targets") or [])[:8],
                "key_events": list(strategist_output.get("key_events") or [])[:8],
                "themes": themes,
                "avoid_themes": avoid_themes,
            },
            # compatibility-rich fields for downstream readers
            "global_sentiment_score": strategist_output.get("global_sentiment_score"),
            "global_macro_moves": _dict(global_signal.get("macro_moves")),
            "fear_index": fear_index,
            "macro_stress_overlay": macro_overlay,
            "market_context_inputs": _dict(strategist_output.get("market_context_inputs")),
            "news_query_reasoning": _clip(strategist_output.get("news_query_reasoning"), max_len=240),
            "news_query_targets": list(strategist_output.get("news_query_targets") or [])[:8],
            "market_news_total_headlines": market_news_context.get("total_headlines") or news_context.get("market_total_headlines") or news_context.get("total_headlines"),
            "market_news_query_count": market_news_context.get("query_count") or len(list(strategist_output.get("news_query_targets") or [])),
            "news_total_headlines": news_context.get("total_headlines") or market_news_context.get("total_headlines"),
            "news_symbol_count": candidate_news_context.get("symbol_count") or len(list(strategist_output.get("news_query_targets") or [])),
            "playbook_summary": summary,
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


def build_scanner_output_artifact(state: Dict[str, Any]) -> Dict[str, Any]:
    scanner_output = _dict(state.get("scanner_output"))
    selected = _dict(state.get("selected"))
    selected_candidate = _dict(selected.get("candidate"))
    selected_features = _dict(selected.get("features"))
    ranked = [row for row in list(state.get("ranked_candidates") or []) if isinstance(row, dict)]
    candidate_visibility_limit = _scanner_candidate_visibility_limit(scanner_output)
    visible_ranked = ranked[:candidate_visibility_limit]
    top_ranked_symbols = [str(row.get("symbol") or "") for row in visible_ranked if str(row.get("symbol") or "").strip()]
    pool_meta = _dict(state.get("scanner_candidate_pool"))
    candidate_preview: List[Dict[str, Any]] = []
    for rank, row in enumerate(visible_ranked, start=1):
        row_breakdown = _dict(row.get("score_breakdown"))
        row_sources = _dict((row.get("candidate") or {}).get("source_scores")) if isinstance(row.get("candidate"), dict) else {}
        compact_features = _dict((row.get("features") or row.get("feature_snapshot") or {}))
        candidate_preview.append(
            {
                "rank": rank,
                "symbol": str(row.get("symbol") or ""),
                "score_total": _safe_float(row.get("score_total") or row.get("score")),
                "score_breakdown": row_breakdown,
                "source_scores": row_sources,
                "risk_score": _safe_float(row.get("risk_score")),
                "confidence": _safe_float(row.get("confidence")),
                "theme_match": _safe_float(row.get("theme_match")),
                "feature_coverage": _safe_float(row.get("feature_coverage")),
                "status": _clip(row.get("status"), max_len=40) or "active",
                "market_representative_guard_applied": bool(row.get("market_representative_guard_applied")),
                "market_representative_guard_penalty": _safe_float(row.get("market_representative_guard_penalty"), 0.0),
                "market_representative_guard_reason": _clip(row.get("market_representative_guard_reason"), max_len=160),
                "asset_class_detected": _clip(row.get("asset_class_detected"), max_len=80),
                "detection_source": _clip(row.get("detection_source"), max_len=40),
                "excluded_by_asset_policy": bool(row.get("excluded_by_asset_policy")),
                "exclusion_reason": _clip(row.get("exclusion_reason"), max_len=160),
                "compact_feature_snapshot": {
                    "engine_trend_strength": compact_features.get("engine_trend_strength"),
                    "engine_volume_spike20": compact_features.get("engine_volume_spike20"),
                    "engine_volatility20": compact_features.get("engine_volatility20"),
                    "engine_vwap_distance": compact_features.get("engine_vwap_distance"),
                    "intraday_change_pct": compact_features.get("intraday_change_pct"),
                },
                "why": _clip(row.get("why"), max_len=180),
            }
        )
    symbol = str(selected.get("symbol") or scanner_output.get("top_stock") or "").strip()
    selected_rank = int(top_ranked_symbols.index(symbol) + 1) if symbol in top_ranked_symbols else (1 if symbol else 0)
    selected_score_total = _safe_float(selected.get("score_total") if selected.get("score_total") is not None else selected.get("score"))
    second_score = _safe_float((ranked[1].get("score_total") if len(ranked) > 1 else None) if len(ranked) > 1 else None)
    margin_vs_second = (selected_score_total - second_score) if len(ranked) > 1 else selected_score_total
    selected_score_breakdown = _dict(selected.get("score_breakdown"))
    critical_positive_factors = [f"{k}:{_safe_float(v, 0.0):.3f}" for k, v in selected_score_breakdown.items() if _safe_float(v, 0.0) > 0][:4]
    critical_negative_factors = [f"{k}:{_safe_float(v, 0.0):.3f}" for k, v in selected_score_breakdown.items() if _safe_float(v, 0.0) < 0][:4]
    selection_summary = _clip(selected.get("why"), max_len=240) or _clip(scanner_output.get("selection_summary"), max_len=240)
    playbook = _clip(
        scanner_output.get("playbook")
        or scanner_output.get("strategist_playbook")
        or _dict(state.get("strategist_output")).get("playbook"),
        max_len=80,
    )
    policy_provenance_ref = _dict(scanner_output.get("policy_provenance_ref"))
    policy_source = _clip(
        scanner_output.get("policy_source")
        or policy_provenance_ref.get("policy_source")
        or _dict(scanner_output.get("policy_provenance")).get("applied_policy_source")
        or _dict(scanner_output.get("policy_provenance")).get("monitor_entry_policy_source"),
        max_len=120,
    )
    applied_policy_present = bool(
        scanner_output.get("applied_policy_present")
        if scanner_output.get("applied_policy_present") is not None
        else policy_provenance_ref.get("applied_policy_present")
    )
    monitor_entry_policy_summary = _dict(
        scanner_output.get("monitor_entry_policy_summary")
        or policy_provenance_ref.get("monitor_entry_policy_summary")
    )
    rejection_rows = [row for row in list(state.get("scanner_runner_up_reasons") or []) if isinstance(row, dict)]
    selection_reason_detail = {
        "selected_symbol": symbol,
        "selected_rank": selected_rank,
        "selected_score_total": selected_score_total,
        "margin_vs_second": margin_vs_second,
        "critical_positive_factors": critical_positive_factors,
        "critical_negative_factors": critical_negative_factors,
        "selection_summary": selection_summary,
    }
    candidate_ranking_table = _build_scanner_candidate_ranking_table(
        state=state,
        candidate_preview=candidate_preview,
    )
    candidate_selection_reason = _build_scanner_candidate_selection_reason(
        state=state,
        selected_symbol=symbol,
        selected_rank=selected_rank,
        selected_score_total=selected_score_total,
        margin_vs_second=margin_vs_second,
        critical_positive_factors=critical_positive_factors,
        critical_negative_factors=critical_negative_factors,
        selection_summary=selection_summary,
        runner_ups=rejection_rows,
        selected=selected,
    )
    scanner_bias_summary = _dict(
        scanner_output.get("scanner_bias_summary")
        or policy_provenance_ref.get("scanner_bias_summary")
        or candidate_selection_reason.get("scanner_bias_summary")
    )
    scanner_bias_applied = bool(
        scanner_output.get("scanner_bias_applied")
        if scanner_output.get("scanner_bias_applied") is not None
        else candidate_selection_reason.get("scanner_bias_applied")
    )
    candidate_bias_adjustments = _dict_list(
        scanner_output.get("candidate_bias_adjustments")
        or candidate_selection_reason.get("candidate_bias_adjustments"),
        limit=candidate_visibility_limit,
    )
    scanner_memory_bias = _dict(
        scanner_output.get("scanner_memory_bias")
        or candidate_selection_reason.get("scanner_memory_bias")
    )
    scanner_memory_bias_summary = _dict(
        scanner_output.get("scanner_memory_bias_summary")
        or candidate_selection_reason.get("scanner_memory_bias_summary")
    )
    scanner_memory_bias_applied = bool(
        scanner_output.get("scanner_memory_bias_applied")
        if scanner_output.get("scanner_memory_bias_applied") is not None
        else candidate_selection_reason.get("scanner_memory_bias_applied")
    )
    candidate_memory_bias_adjustments = _dict_list(
        scanner_output.get("candidate_memory_bias_adjustments")
        or candidate_selection_reason.get("candidate_memory_bias_adjustments"),
        limit=candidate_visibility_limit,
    )
    selected_memory_bias_result = {
        "bias_adjustment": selected.get("memory_bias_adjustment"),
        "source_delta": selected.get("memory_bias_source_delta"),
        "symbol_delta": selected.get("memory_bias_symbol_delta"),
        "adjustments": list(selected.get("memory_bias_adjustments") or []),
    }
    commander_memory_application_trace = _dict(
        scanner_output.get("commander_memory_application_trace")
        or scanner_output.get("scanner_memory_application_trace")
        or candidate_selection_reason.get("commander_memory_application_trace")
        or candidate_selection_reason.get("scanner_memory_application_trace")
    )
    if not commander_memory_application_trace:
        commander_memory_application_trace = build_scanner_commander_memory_application_trace(
            scanner_memory_bias=scanner_memory_bias,
            selected_symbol=symbol,
            candidate_sources=list(selected_candidate.get("sources") or []),
            selected_memory_bias_result=selected_memory_bias_result,
            candidate_memory_bias_adjustments=candidate_memory_bias_adjustments,
            scanner_memory_bias_summary=scanner_memory_bias_summary,
            scanner_memory_bias_applied=bool(scanner_memory_bias_applied),
        )
    selection_reason_with_bias = _clip(
        scanner_output.get("selection_reason_with_bias")
        or candidate_selection_reason.get("selection_reason_with_bias")
        or selection_summary,
        max_len=320,
    )
    entry_compatibility_score = _safe_float(
        scanner_output.get("entry_compatibility_score")
        if scanner_output.get("entry_compatibility_score") not in (None, "")
        else candidate_selection_reason.get("entry_compatibility_score"),
        0.0,
    )
    compatibility_bias = _safe_float(
        scanner_output.get("compatibility_bias")
        if scanner_output.get("compatibility_bias") not in (None, "")
        else candidate_selection_reason.get("compatibility_bias"),
        0.0,
    )
    expected_monitor_block_reason = _clip(
        scanner_output.get("expected_monitor_block_reason")
        or candidate_selection_reason.get("expected_monitor_block_reason"),
        max_len=120,
    )
    dominant_block_reason = _clip(
        scanner_output.get("dominant_block_reason")
        or candidate_selection_reason.get("dominant_block_reason"),
        max_len=120,
    )
    dominant_block_reason_ratio = _safe_float(
        scanner_output.get("dominant_block_reason_ratio")
        if scanner_output.get("dominant_block_reason_ratio") not in (None, "")
        else candidate_selection_reason.get("dominant_block_reason_ratio"),
        0.0,
    )
    bias_scale = _safe_float(
        scanner_output.get("bias_scale")
        if scanner_output.get("bias_scale") not in (None, "")
        else candidate_selection_reason.get("bias_scale"),
        0.0,
    )
    soft_penalty = _safe_float(
        scanner_output.get("soft_penalty")
        if scanner_output.get("soft_penalty") not in (None, "")
        else candidate_selection_reason.get("soft_penalty"),
        0.0,
    )
    compatibility_score_pre_penalty = _safe_float(
        scanner_output.get("compatibility_score_pre_penalty")
        if scanner_output.get("compatibility_score_pre_penalty") not in (None, "")
        else candidate_selection_reason.get("compatibility_score_pre_penalty"),
        entry_compatibility_score,
    )
    compatibility_score_post_penalty = _safe_float(
        scanner_output.get("compatibility_score_post_penalty")
        if scanner_output.get("compatibility_score_post_penalty") not in (None, "")
        else candidate_selection_reason.get("compatibility_score_post_penalty"),
        entry_compatibility_score,
    )
    compatibility_trace = _dict(
        scanner_output.get("compatibility_trace")
        or candidate_selection_reason.get("compatibility_trace")
    )
    compatibility_components = _dict(
        scanner_output.get("compatibility_components")
        or candidate_selection_reason.get("compatibility_components")
        or compatibility_trace.get("compatibility_components")
    )
    pre_adjust_score_total = _safe_float(
        scanner_output.get("pre_adjust_score_total")
        if scanner_output.get("pre_adjust_score_total") not in (None, "")
        else candidate_selection_reason.get("pre_adjust_score_total"),
        selected_score_total,
    )
    post_adjust_score_total = _safe_float(
        scanner_output.get("post_adjust_score_total")
        if scanner_output.get("post_adjust_score_total") not in (None, "")
        else candidate_selection_reason.get("post_adjust_score_total"),
        selected_score_total,
    )
    quote_data_diagnostic = _dict(scanner_output.get("quote_data_diagnostic") or state.get("scanner_quote_diagnostic"))
    runner_up_symbol = ""
    ranking_rows = [row for row in list(candidate_ranking_table.get("rows") or []) if isinstance(row, dict)]
    if len(ranking_rows) > 1:
        runner_up_symbol = str(ranking_rows[1].get("symbol") or "").strip()
    score_breakdown_by_symbol = {
        str(row.get("symbol") or "").strip(): _dict(row.get("score_breakdown"))
        for row in ranking_rows
        if str(row.get("symbol") or "").strip()
    }
    confidence_by_symbol = {
        str(row.get("symbol") or "").strip(): row.get("confidence")
        for row in ranking_rows
        if str(row.get("symbol") or "").strip()
    }
    risk_score_by_symbol = {
        str(row.get("symbol") or "").strip(): row.get("risk_score")
        for row in ranking_rows
        if str(row.get("symbol") or "").strip()
    }
    fallback_reason = _clip(
        pool_meta.get("fallback_reason")
        or scanner_output.get("fallback_reason")
        or ("backfill_used" if bool(pool_meta.get("backfill_used")) else ""),
        max_len=180,
    )
    fallback_used = bool(fallback_reason)
    trace_summary = _build_scanner_trace_summary(
        symbol=symbol,
        selected_rank=selected_rank,
        universe_size=_safe_int(scanner_output.get("candidate_pool_size") or scanner_output.get("candidate_count")) or _safe_int(pool_meta.get("candidate_pool_after_filter") or len(ranked)),
        selected_score_total=selected_score_total,
        margin_vs_second=margin_vs_second,
        selected_score_breakdown=selected_score_breakdown,
        selected=selected,
        candidate_preview=candidate_preview,
        selection_summary=selection_summary,
        scanner_bias_applied=scanner_bias_applied,
        scanner_bias_summary=scanner_bias_summary,
    )
    artifact = _base_output(state, agent="scanner", symbol=symbol)
    artifact.update(
        {
            "candidate_pool_snapshot": {
                "candidate_source": _clip(pool_meta.get("candidate_source"), max_len=80),
                "scanner_candidate_source": _clip(pool_meta.get("scanner_candidate_source"), max_len=40),
                "scanner_policy_source": _clip(pool_meta.get("scanner_policy_source"), max_len=80),
                "scanner_fallback_mode": _clip(pool_meta.get("scanner_fallback_mode"), max_len=80),
                "scanner_strict_mode": bool(pool_meta.get("scanner_strict_mode")),
                "asset_universe_policy": _clip(scanner_output.get("asset_universe_policy") or pool_meta.get("asset_universe_policy"), max_len=80),
                "asset_universe_policy_source": _clip(scanner_output.get("asset_universe_policy_source") or pool_meta.get("asset_universe_policy_source"), max_len=80),
                "excluded_candidate_count_by_asset_policy": _safe_int(scanner_output.get("excluded_candidate_count_by_asset_policy") or pool_meta.get("asset_policy_excluded_count")),
                "excluded_candidates_by_asset_policy": _dict_list(scanner_output.get("excluded_candidates_by_asset_policy") or pool_meta.get("asset_policy_exclusions"), limit=20),
                "excluded_candidate_count_by_mock_broker_restricted": _safe_int(
                    scanner_output.get("excluded_candidate_count_by_mock_broker_restricted")
                    or pool_meta.get("mock_broker_restricted_excluded_count")
                ),
                "excluded_candidates_by_mock_broker_restricted": _dict_list(
                    scanner_output.get("excluded_candidates_by_mock_broker_restricted")
                    or pool_meta.get("mock_broker_restricted_exclusions"),
                    limit=20,
                ),
                "asset_detection_stats": _dict(scanner_output.get("asset_detection_stats") or pool_meta.get("asset_detection_stats")),
                "unknown_asset_candidate_count": _safe_int(scanner_output.get("unknown_asset_candidate_count") or pool_meta.get("unknown_asset_candidate_count")),
                "total_candidates_before_filter": _safe_int(scanner_output.get("total_candidates_before_filter") or pool_meta.get("total_candidates_before_filter")),
                "total_candidates_after_filter": _safe_int(scanner_output.get("total_candidates_after_filter") or pool_meta.get("total_candidates_after_filter")),
                "candidate_pool_before_filter": _safe_int(pool_meta.get("candidate_pool_before_filter")),
                "candidate_pool_after_filter": _safe_int(pool_meta.get("candidate_pool_after_filter") or len(ranked)),
                "source_mix": _dict(pool_meta.get("pool_source_mix")),
                "fallback_reason": _clip(pool_meta.get("fallback_reason"), max_len=160),
            },
            "filter_funnel": {
                "before": _safe_int(pool_meta.get("candidate_pool_before_filter")),
                "after": _safe_int(pool_meta.get("candidate_pool_after_filter") or len(ranked)),
                "excluded_by_asset_policy": _safe_int(scanner_output.get("excluded_candidate_count_by_asset_policy") or pool_meta.get("asset_policy_excluded_count")),
                "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
                "avoid_filter_applied": bool(pool_meta.get("avoid_filter_applied")),
                "blocked_static_fallback": bool(pool_meta.get("blocked_static_fallback")),
                "strict_kiwoom_only": bool(pool_meta.get("strict_kiwoom_only")),
            },
            "universe_size": _safe_int(scanner_output.get("candidate_pool_size") or scanner_output.get("candidate_count")),
            "candidate_list_summary": {
                "candidate_source": _clip(scanner_output.get("candidate_source"), max_len=80),
                "scanner_candidate_source": _clip(scanner_output.get("scanner_candidate_source"), max_len=40),
                "scanner_policy_source": _clip(scanner_output.get("scanner_policy_source"), max_len=80),
                "scanner_fallback_mode": _clip(scanner_output.get("scanner_fallback_mode"), max_len=80),
                "scanner_strict_mode": bool(scanner_output.get("scanner_strict_mode")),
                "asset_universe_policy": _clip(scanner_output.get("asset_universe_policy"), max_len=80),
                "asset_universe_policy_source": _clip(scanner_output.get("asset_universe_policy_source"), max_len=80),
                "excluded_candidate_count_by_asset_policy": _safe_int(scanner_output.get("excluded_candidate_count_by_asset_policy")),
                "excluded_candidate_count_by_mock_broker_restricted": _safe_int(scanner_output.get("excluded_candidate_count_by_mock_broker_restricted")),
                "asset_detection_stats": _dict(scanner_output.get("asset_detection_stats")),
                "unknown_asset_candidate_count": _safe_int(scanner_output.get("unknown_asset_candidate_count")),
                "total_candidates_before_filter": _safe_int(scanner_output.get("total_candidates_before_filter")),
                "total_candidates_after_filter": _safe_int(scanner_output.get("total_candidates_after_filter")),
                "source_mix": _dict(scanner_output.get("source_mix")),
                "candidate_count": _safe_int(scanner_output.get("candidate_count")),
            },
            "candidate_ranking_table": candidate_ranking_table,
            "candidate_selection_reason": candidate_selection_reason,
            "ranking_table": candidate_preview,
            "ranked_candidates": candidate_preview,
            "selected_symbol": symbol,
            "selected_rank": selected_rank,
            "scanner_selected_symbol": symbol,
            "scanner_rank": selected_rank,
            "scanner_score_total": selected_score_total,
            "scanner_score_breakdown": selected_score_breakdown,
            "scanner_top_candidates": candidate_preview[:3],
            "runner_up_symbol": runner_up_symbol,
            "playbook": playbook,
            "policy_source": policy_source,
            "applied_policy_present": applied_policy_present,
            "monitor_entry_policy_summary": monitor_entry_policy_summary,
            "entry_compatibility_score": entry_compatibility_score,
            "compatibility_bias": compatibility_bias,
            "compatibility_components": compatibility_components,
            "expected_monitor_block_reason": expected_monitor_block_reason,
            "dominant_block_reason": dominant_block_reason,
            "dominant_block_reason_ratio": dominant_block_reason_ratio,
            "bias_scale": bias_scale,
            "soft_penalty": soft_penalty,
            "compatibility_score_pre_penalty": compatibility_score_pre_penalty,
            "compatibility_score_post_penalty": compatibility_score_post_penalty,
            "compatibility_trace": compatibility_trace,
            "pre_adjust_score_total": pre_adjust_score_total,
            "post_adjust_score_total": post_adjust_score_total,
            "scanner_bias_context": _dict(scanner_output.get("scanner_bias_context")),
            "scanner_bias_applied": scanner_bias_applied,
            "scanner_bias_summary": scanner_bias_summary,
            "scanner_memory_bias_applied": scanner_memory_bias_applied,
            "scanner_memory_bias": scanner_memory_bias,
            "scanner_memory_bias_summary": scanner_memory_bias_summary,
            "candidate_memory_bias_adjustments": candidate_memory_bias_adjustments,
            "commander_memory_application_trace": commander_memory_application_trace,
            "scanner_memory_application_trace": commander_memory_application_trace,
            "candidate_bias_adjustments": candidate_bias_adjustments,
            "selection_reason_with_bias": selection_reason_with_bias,
            "selection_reason": selection_summary,
            "selection_reason_detail": selection_reason_detail,
            "score_breakdown_by_symbol": score_breakdown_by_symbol,
            "confidence_by_symbol": confidence_by_symbol,
            "risk_score_by_symbol": risk_score_by_symbol,
            "ranking_table_missing": not bool(ranking_rows),
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
            "trace_summary": trace_summary,
            "rejection_summary": rejection_rows,
            "filter_feature_summary": {
                "feature_source": _clip(state.get("scanner_feature", {}).get("source") if isinstance(state.get("scanner_feature"), dict) else "", max_len=80),
                "feature_symbol_count": _safe_int(_dict(state.get("scanner_feature")).get("symbol_count")),
                "condition_search_status": _clip(scanner_output.get("condition_search_status"), max_len=80),
                "condition_search_reason": _clip(scanner_output.get("condition_search_reason"), max_len=160),
            },
            "quote_data_diagnostic": quote_data_diagnostic,
            "applied_scanner_policy": _dict(scanner_output.get("applied_scanner_policy")),
            "score_adjustment_trace": list(scanner_output.get("score_adjustment_trace") or []),
            "reentry_penalty_applied": bool(scanner_output.get("reentry_penalty_applied")),
            "reentry_penalty_value": float(scanner_output.get("reentry_penalty_value") or 0.0),
            "diversification_applied": bool(scanner_output.get("diversification_applied")),
            "diversification_bonus_value": float(scanner_output.get("diversification_bonus_value") or 0.0),
            "entry_bias_cap_applied": bool(scanner_output.get("entry_bias_cap_applied")),
            "market_representative_guard_enabled": bool(scanner_output.get("market_representative_guard_enabled")),
            "market_representative_guard_applied": bool(scanner_output.get("market_representative_guard_applied")),
            "market_representative_guard_policy": _dict(scanner_output.get("market_representative_guard_policy")),
            "market_representative_guard_symbol": _clip(scanner_output.get("market_representative_guard_symbol"), max_len=16),
            "market_representative_guard_penalty": float(scanner_output.get("market_representative_guard_penalty") or 0.0),
            "market_representative_guard_score_gap": float(scanner_output.get("market_representative_guard_score_gap") or 0.0),
            "market_representative_guard_reason": _clip(scanner_output.get("market_representative_guard_reason"), max_len=200),
            "market_representative_guard_confirmation_sources": list(scanner_output.get("market_representative_guard_confirmation_sources") or []),
            "market_representative_guard_before_top": list(scanner_output.get("market_representative_guard_before_top") or []),
            "market_representative_guard_after_top": list(scanner_output.get("market_representative_guard_after_top") or []),
            "raw_entry_compatibility_bias": float(scanner_output.get("raw_entry_compatibility_bias") or 0.0),
            "effective_entry_compatibility_bias": float(scanner_output.get("effective_entry_compatibility_bias") or 0.0),
            "adjusted_score_total": float(scanner_output.get("adjusted_score_total") or 0.0),
            "ranking_before_policy": list(scanner_output.get("ranking_before_policy") or []),
            "ranking_after_policy": list(scanner_output.get("ranking_after_policy") or []),
            "scanner_policy_source": "commander",
            "scanner_policy_version": "1.0",
            "evidence_refs": {
                "event_names": [
                    "scanner.candidate_pool_snapshot",
                    "scanner.candidate_ranking_table",
                    "scanner.candidate_selection_reason",
                    "scanner.selection_output",
                ],
                "top_ranked_symbols": top_ranked_symbols,
            },
            "source_refs": {
                "scanner_source_policy": _dict(scanner_output.get("scanner_source_policy")),
                "strategist_playbook": _clip(scanner_output.get("strategist_playbook"), max_len=80),
            },
            # compatibility-rich fields for downstream readers
            "top_stock": scanner_output.get("top_stock"),
            "top_score": scanner_output.get("top_score"),
            "candidate_pool_after_filter": _safe_int(scanner_output.get("candidate_pool_size") or scanner_output.get("candidate_count")),
            "top_ranked_symbols": top_ranked_symbols,
            "selected_candidate": {
                "symbol": symbol,
                "why": _clip(selected.get("why"), max_len=180),
                "asset_class_detected": _clip(selected.get("asset_class_detected") or scanner_output.get("selected_asset_class_detected"), max_len=80),
                "detection_source": _clip(selected.get("detection_source") or scanner_output.get("selected_asset_detection_source"), max_len=40),
                "detection_field": _clip(selected.get("detection_field") or scanner_output.get("selected_asset_detection_field"), max_len=80),
                "sources": list(selected_candidate.get("sources") or [])[:8],
                "source_scores": _dict(selected_candidate.get("source_scores")),
                "score_total": _safe_float(selected.get("score_total") or selected.get("score")),
                "risk_score": _safe_float(selected.get("risk_score")),
                "confidence": _safe_float(selected.get("confidence")),
                "score_breakdown": _dict(selected.get("score_breakdown")),
                "component_snapshot": _dict(selected.get("components")),
                "feature_snapshot": {
                    "skill_quote_price": selected_features.get("skill_quote_price"),
                    "quote_volume": selected_features.get("quote_volume"),
                    "quote_trading_value": selected_features.get("quote_trading_value"),
                    "intraday_change_pct": selected_features.get("intraday_change_pct"),
                    "engine_trend_strength": selected_features.get("engine_trend_strength"),
                    "engine_volume_spike20": selected_features.get("engine_volume_spike20"),
                    "engine_volatility20": selected_features.get("engine_volatility20"),
                    "engine_vwap_distance": selected_features.get("engine_vwap_distance"),
                    "engine_sector_relative_strength": selected_features.get("engine_sector_relative_strength"),
                    "engine_cross_section_rank": selected_features.get("engine_cross_section_rank"),
                },
            },
            "candidate_preview": candidate_preview,
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


def build_monitor_output_artifact(state: Dict[str, Any]) -> Dict[str, Any]:
    monitor = _dict(state.get("monitor"))
    monitor_output = _dict(state.get("monitor_output"))
    monitor_focus_state = _dict(state.get("monitor_focus_context"))
    monitor_evaluation = _dict(state.get("monitor_evaluation"))
    monitor_action = _dict(state.get("monitor_action_decision"))
    exit_info = _dict(state.get("monitor_exit"))
    entry_info = _dict(state.get("monitor_entry"))
    transition = _dict(state.get("monitor_state_transition"))
    entry_detail = _dict(state.get("monitor_entry_decision_detail"))
    exit_detail = _dict(state.get("monitor_exit_decision_detail"))
    selected = _dict(state.get("selected"))
    scanner_selected_snapshot = _dict(state.get("scanner_selected_snapshot"))
    trace_sources = [
        monitor_output,
        monitor_focus_state,
        monitor_action,
        monitor_evaluation,
        entry_detail,
        exit_detail,
        monitor,
        entry_info,
        exit_info,
    ]

    def _first_trace_dict(key: str) -> Dict[str, Any]:
        for source in trace_sources:
            value = source.get(key)
            if isinstance(value, dict) and value:
                return dict(value)
        return {}

    def _first_trace_list(key: str) -> List[Any]:
        for source in trace_sources:
            value = source.get(key)
            if isinstance(value, list) and value:
                return list(value)
        return []

    def _first_trace_text(key: str) -> str:
        for source in trace_sources:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _first_trace_bool(key: str) -> Any:
        for source in trace_sources:
            value = source.get(key)
            if isinstance(value, bool):
                return value
        return None

    def _first_trace_value(key: str) -> Any:
        for source in trace_sources:
            if key not in source:
                continue
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    policy_trace = {
        "policy_ref": _first_trace_dict("policy_ref"),
        "entry_check_summary": _first_trace_text("entry_check_summary"),
        "entry_blockers": _first_trace_list("entry_blockers"),
        "timing_assessment": _first_trace_dict("timing_assessment"),
        "exit_trigger_basis": _first_trace_dict("exit_trigger_basis"),
        "commander_context_consumed": _first_trace_bool("commander_context_consumed"),
        "consumed_fields": _first_trace_list("consumed_fields"),
        "flow_instruction_applied": _first_trace_bool("flow_instruction_applied"),
        "no_trade_reason_applied": _first_trace_bool("no_trade_reason_applied"),
        "shadow_used": _first_trace_bool("shadow_used"),
        "strategist_fallback_used": _first_trace_bool("strategist_fallback_used"),
    }
    exit_vs_strategy_intent = _first_trace_dict("exit_vs_strategy_intent")
    monitor_no_trade_surface = _first_trace_dict("no_trade_surface")
    if not monitor_no_trade_surface:
        commander_decision = _dict(state.get("commander_decision"))
        monitor_no_trade_surface = build_monitor_no_trade_surface(
            entry_info,
            final_decision=str(monitor_output.get("intent_side") or "NOOP").strip().upper() or "WAIT",
            buy_submitted=str(monitor_output.get("intent_side") or "").strip().upper() == "BUY",
            guard_blocked=bool(entry_info.get("guard_blocked")),
            guard_reason=entry_info.get("guard_reason"),
            commander_no_trade_reason_code=commander_decision.get("no_trade_reason_code"),
        )
    scanner_monitor_handoff = _first_trace_dict("scanner_monitor_handoff")
    if not scanner_monitor_handoff:
        scanner_monitor_handoff = build_scanner_monitor_handoff_surface(
            selected=scanner_selected_snapshot or selected,
            ranked_candidates=[row for row in list(state.get("ranked_candidates") or []) if isinstance(row, dict)],
            scanner_output=_dict(state.get("scanner_output")),
            final_decision=str(monitor_output.get("intent_side") or "NOOP").strip().upper() or "WAIT",
            no_trade_surface=monitor_no_trade_surface,
            entry_info=entry_info,
        )
    entry_candidate_cascade = _first_trace_dict("entry_candidate_cascade")
    entry_blocker_surface = _first_trace_dict("entry_blocker_surface")
    if not entry_blocker_surface:
        entry_blocker_surface = build_entry_blocker_surface(
            entry_info,
            final_decision=str(monitor_output.get("intent_side") or "NOOP").strip().upper() or "WAIT",
            no_trade_surface=monitor_no_trade_surface,
            entry_blockers=_first_trace_list("entry_blockers"),
            buy_blocked_open_position=bool(monitor.get("buy_blocked_open_position")),
            buy_blocked_post_exit_cooldown=bool(monitor.get("buy_blocked_post_exit_cooldown")),
            post_exit_cooldown_remaining_sec=monitor.get("post_exit_cooldown_remaining_sec"),
            open_position_count=monitor.get("open_position_count"),
        )
    symbol = str(exit_info.get("symbol") or monitor_output.get("selected_symbol") or monitor.get("selected_symbol") or "").strip()
    thresholds = _dict(exit_info.get("thresholds"))
    watch_axes = list(exit_info.get("watch_axes") or [])
    intents = [row for row in list(state.get("intents") or []) if isinstance(row, dict)]
    first_intent = intents[0] if intents else {}
    intent_side = str(monitor_output.get("intent_side") or first_intent.get("side") or "NOOP").strip().upper()
    open_position_count = _safe_int(monitor.get("open_position_count"))
    monitor_focus_context = _first_trace_dict("monitor_focus_context")
    if not monitor_focus_context and monitor_focus_state:
        monitor_focus_context = dict(monitor_focus_state)
    if not monitor_focus_context:
        entry_candidate_symbol = _clip(
            monitor_output.get("entry_candidate_symbol")
            or entry_info.get("selected_symbol")
            or entry_info.get("symbol")
            or selected.get("symbol"),
            max_len=24,
        )
        entry_final_symbol = _clip(
            monitor_output.get("entry_final_symbol")
            or _dict(scanner_monitor_handoff.get("entry_candidate_cascade")).get("final_selected_symbol")
            or entry_candidate_symbol,
            max_len=24,
        )
        position_focus_symbol = _clip(
            monitor_output.get("position_focus_symbol")
            or exit_info.get("symbol")
            or "",
            max_len=24,
        )
        if position_focus_symbol and entry_final_symbol and position_focus_symbol != entry_final_symbol:
            focus_mode = "entry_candidate_and_position_focus"
        elif position_focus_symbol:
            focus_mode = "position_focus"
        elif entry_final_symbol:
            focus_mode = "entry_candidate_focus"
        else:
            focus_mode = ""
        if focus_mode:
            monitor_focus_context = {
                "schema_version": "monitor.focus_context.v1",
                "focus_mode": focus_mode,
                "scanner_selected_symbol": _clip(scanner_monitor_handoff.get("scanner_selected_symbol"), max_len=24),
                "entry_candidate_symbol": entry_candidate_symbol,
                "entry_final_symbol": entry_final_symbol,
                "position_focus_symbol": position_focus_symbol,
                "monitor_output_symbol": _clip(position_focus_symbol or entry_final_symbol, max_len=24),
                "open_position_count": open_position_count,
                "max_positions": _safe_int(monitor.get("max_positions")),
                "capacity_remaining": _safe_int(monitor.get("multi_position_capacity_remaining")),
                "entry_decision": str(monitor_output.get("intent_side") or "NOOP").strip().upper(),
                "entry_reason": _clip(entry_info.get("guard_reason") or entry_info.get("reason"), max_len=160),
                "entry_primary_failure_axis": _clip(entry_info.get("primary_failure_axis"), max_len=120),
                "exit_reason": _clip(exit_info.get("reason"), max_len=160),
                "exit_monitor_reason": _clip(exit_info.get("monitor_reason"), max_len=160),
            }
    triggered_rules: List[str] = []
    if bool(exit_info.get("triggered")) and str(exit_info.get("reason") or "").strip():
        triggered_rules.append(str(exit_info.get("reason") or "").strip())
    if bool(entry_info.get("triggered")) and str(entry_info.get("pattern") or "").strip():
        triggered_rules.append(f"entry:{str(entry_info.get('pattern') or '').strip()}")
    blocked_rules: List[str] = []
    if bool(entry_info.get("guard_blocked")) and str(entry_info.get("guard_reason") or "").strip():
        blocked_rules.append(str(entry_info.get("guard_reason") or "").strip())
    if bool(exit_info.get("sell_guard_blocked")) and str(exit_info.get("sell_guard_reason") or "").strip():
        blocked_rules.append(str(exit_info.get("sell_guard_reason") or "").strip())
    blocked_rules.extend([str(x or "").strip() for x in list(entry_info.get("failed_checks") or []) if str(x or "").strip()])
    posture = _clip(state.get("monitor_posture") or transition.get("current_posture"), max_len=60)
    decision_reason_chain = [
        _clip(exit_info.get("monitor_reason"), max_len=180),
        _clip(exit_info.get("reason"), max_len=180),
        _clip(entry_info.get("reason"), max_len=180),
        _clip(monitor_output.get("entry_exit_reason"), max_len=180),
    ]
    decision_reason_chain = [x for x in decision_reason_chain if x]
    entry_reason_code = _clip(
        entry_detail.get("reason")
        or entry_info.get("guard_reason")
        or entry_info.get("reason"),
        max_len=160,
    )
    entry_metrics_seed = _dict(entry_info.get("metrics"))
    entry_has_structural_evidence = bool(
        bool(entry_info.get("evaluated"))
        or bool(entry_info.get("failed_checks"))
        or bool(entry_reason_code)
        or bool(entry_metrics_seed.get("minute_source_present"))
        or bool(entry_metrics_seed.get("minute_refetch_attempted"))
        or entry_metrics_seed.get("current_price") not in (None, "")
        or entry_metrics_seed.get("price") not in (None, "")
    )
    missing_inputs: List[str] = []
    if not symbol:
        missing_inputs.append("selected_symbol_missing")
    if not bool(entry_info.get("evaluated")) and entry_reason_code in {"minute_candle_missing", "data_incomplete"}:
        missing_inputs.append(entry_reason_code)
    if (
        exit_info.get("price") in (None, "")
        and not bool(entry_info.get("triggered"))
        and not entry_has_structural_evidence
    ):
        missing_inputs.append("price_unavailable")
    if intent_side == "BUY":
        decision_phase = "entry"
        decision_action = "buy"
    elif intent_side == "SELL":
        decision_phase = "exit"
        decision_action = "sell"
    elif open_position_count > 0:
        decision_phase = "hold"
        decision_action = "hold"
    else:
        decision_phase = "no_intent"
        decision_action = "none"
    if intent_side in {"BUY", "SELL"}:
        decision_status = "ok"
    elif missing_inputs:
        decision_status = "unavailable"
    elif blocked_rules:
        decision_status = "blocked"
    else:
        decision_status = "skipped"
    if decision_phase == "no_intent" and open_position_count <= 0 and entry_reason_code:
        primary_reason_raw = entry_reason_code
    else:
        primary_reason_raw = (
            exit_detail.get("triggered_rule")
            or exit_info.get("reason")
            or entry_detail.get("reason")
            or entry_info.get("guard_reason")
            or entry_info.get("reason")
            or monitor_output.get("entry_exit_reason")
            or exit_info.get("monitor_reason")
        )
    primary_reason_code = _clip(primary_reason_raw, max_len=180)
    secondary_reason_codes = _dedupe_text(
        [text for text in blocked_rules + decision_reason_chain if text and text != primary_reason_code],
        limit=12,
        max_len=160,
    )
    price_source = _clip(exit_info.get("price_source"), max_len=120)
    feature_source = _clip(exit_info.get("feature_source"), max_len=120)
    evidence_quality = "unavailable"
    if decision_status == "ok" and (bool(entry_info.get("evaluated")) or bool(exit_info.get("evaluated"))):
        evidence_quality = "strong"
    elif bool(entry_info.get("evaluated")) or bool(exit_info.get("evaluated")) or bool(secondary_reason_codes):
        evidence_quality = "partial"
    elif decision_reason_chain:
        evidence_quality = "weak"
    threshold_snapshot = {
        "applied_policy": _dict(entry_info.get("applied_policy")) or _dict(entry_info.get("thresholds")),
        "received_policy": _dict(entry_info.get("received_policy")),
        "received_policy_source": _clip(entry_info.get("received_policy_source"), max_len=120),
        "effective_policy": _dict(entry_info.get("effective_policy")) or _dict(entry_info.get("applied_policy")) or _dict(entry_info.get("thresholds")),
        "effective_policy_source": _clip(entry_info.get("effective_policy_source"), max_len=120),
        "effective_policy_source_chain": _listify(entry_info.get("effective_policy_source_chain"), limit=6, max_len=80),
        "policy_adjustments": _dict(entry_info.get("policy_adjustments")),
        "policy_adjustment_summary": _clip(entry_info.get("policy_adjustment_summary"), max_len=220),
        "policy_adjustment_reasoning": _clip(entry_info.get("policy_adjustment_reasoning"), max_len=260),
        "monitor_memory_bias_applied": bool(entry_info.get("monitor_memory_bias_applied")),
        "monitor_memory_bias": _dict(entry_info.get("monitor_memory_bias")),
        "monitor_memory_bias_summary": _dict(entry_info.get("monitor_memory_bias_summary")),
        "monitor_memory_bias_deltas": [
            {
                "field": _clip((row or {}).get("field"), max_len=80),
                "delta": (row or {}).get("delta"),
                "from": (row or {}).get("from"),
                "to": (row or {}).get("to"),
            }
            for row in list(entry_info.get("monitor_memory_bias_deltas") or [])[:8]
            if isinstance(row, dict)
        ],
        "commander_memory_application_trace": _dict(entry_info.get("commander_memory_application_trace")),
        "monitor_memory_application_trace": _dict(entry_info.get("monitor_memory_application_trace")),
        "effective_policy_deltas": [
            {
                "field": _clip((row or {}).get("field"), max_len=80),
                "from": (row or {}).get("from"),
                "to": (row or {}).get("to"),
            }
            for row in list(entry_info.get("effective_policy_deltas") or [])[:8]
            if isinstance(row, dict)
        ],
        "entry_thresholds": _dict(entry_info.get("thresholds")),
        "entry_threshold_margins": _dict(entry_info.get("threshold_margins")),
        "entry_condition_path": _clip(entry_info.get("entry_condition_path"), max_len=80),
        "entry_condition_paths_passed": _listify(entry_info.get("entry_condition_paths_passed"), limit=4, max_len=80),
        "entry_condition_scores": _dict(entry_info.get("condition_scores")),
        "entry_grouped_logic_trace": _dict(entry_info.get("grouped_logic_trace")),
        "entry_latest_candle_ts": entry_info.get("metrics", {}).get("latest_candle_ts") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_snapshot_age_minutes": entry_info.get("metrics", {}).get("minute_snapshot_age_minutes") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_snapshot_was_stale": entry_info.get("metrics", {}).get("minute_snapshot_was_stale") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_refetch_attempted": entry_info.get("metrics", {}).get("minute_refetch_attempted") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_refetch_succeeded": entry_info.get("metrics", {}).get("minute_refetch_succeeded") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_refetch_reason": entry_info.get("metrics", {}).get("minute_refetch_reason") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_refetch_trigger_reason": entry_info.get("metrics", {}).get("minute_refetch_trigger_reason") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_refetch_failure_reason": entry_info.get("metrics", {}).get("minute_refetch_failure_reason") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_minute_refetch_produced_fresh_snapshot": entry_info.get("metrics", {}).get("minute_refetch_produced_fresh_snapshot") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_inferred_spacing_minutes": entry_info.get("metrics", {}).get("inferred_spacing_minutes") if isinstance(entry_info.get("metrics"), dict) else None,
        "entry_series_class": entry_info.get("metrics", {}).get("series_class") if isinstance(entry_info.get("metrics"), dict) else None,
        "exit_thresholds": thresholds,
        "exit_confirm_ticks": _safe_int(exit_info.get("exit_confirm_ticks")),
        "exit_confirm_count": _safe_int(exit_info.get("exit_confirm_count")),
    }
    entry_metrics = (
        _dict(entry_info.get("metrics"))
        or _dict(entry_detail.get("metrics"))
        or _dict(monitor.get("entry_metrics"))
    )
    entry_chart_structure_features = (
        _dict(monitor_output.get("chart_structure_features"))
        or _dict(entry_info.get("chart_structure_features"))
        or _dict(monitor.get("entry_chart_structure_features"))
    )
    entry_policy_interpreter_trace = (
        _dict(monitor_output.get("policy_interpreter_trace"))
        or _dict(entry_info.get("policy_interpreter_trace"))
        or _dict(monitor.get("entry_policy_interpreter_trace"))
    )
    entry_policy_alignment_summary = (
        _dict(monitor_output.get("policy_alignment_summary"))
        or _dict(entry_info.get("policy_alignment_summary"))
        or _dict(monitor.get("entry_policy_alignment_summary"))
    )
    entry_minute_source_present = threshold_snapshot.get("entry_minute_source_present")
    if entry_minute_source_present is None:
        entry_minute_source_present = entry_metrics.get("minute_source_present")
    if entry_minute_source_present is None:
        entry_minute_source_present = _first_trace_value("entry_minute_source_present")
    entry_minute_source_used = threshold_snapshot.get("entry_minute_source_used")
    if entry_minute_source_used in (None, ""):
        entry_minute_source_used = entry_metrics.get("minute_source_used")
    if entry_minute_source_used in (None, ""):
        entry_minute_source_used = _first_trace_value("entry_minute_source_used")
    entry_minute_refetch_attempted = threshold_snapshot.get("entry_minute_refetch_attempted")
    if entry_minute_refetch_attempted is None:
        entry_minute_refetch_attempted = entry_metrics.get("minute_refetch_attempted")
    if entry_minute_refetch_attempted is None:
        entry_minute_refetch_attempted = _first_trace_value("entry_minute_refetch_attempted")
    entry_minute_refetch_succeeded = threshold_snapshot.get("entry_minute_refetch_succeeded")
    if entry_minute_refetch_succeeded is None:
        entry_minute_refetch_succeeded = entry_metrics.get("minute_refetch_succeeded")
    if entry_minute_refetch_succeeded is None:
        entry_minute_refetch_succeeded = _first_trace_value("entry_minute_refetch_succeeded")
    entry_minute_refetch_failure_reason = threshold_snapshot.get("entry_minute_refetch_failure_reason")
    if entry_minute_refetch_failure_reason in (None, ""):
        entry_minute_refetch_failure_reason = entry_metrics.get("minute_refetch_failure_reason")
    if entry_minute_refetch_failure_reason in (None, ""):
        entry_minute_refetch_failure_reason = _first_trace_value("entry_minute_refetch_failure_reason")
    entry_minute_refetch_failure_detail = entry_metrics.get("minute_refetch_failure_detail")
    if entry_minute_refetch_failure_detail in (None, ""):
        entry_minute_refetch_failure_detail = _first_trace_value("entry_minute_refetch_failure_detail")
    entry_minute_refetch_runner_source = entry_metrics.get("minute_refetch_runner_source")
    if entry_minute_refetch_runner_source in (None, ""):
        entry_minute_refetch_runner_source = _first_trace_value("entry_minute_refetch_runner_source")
    monitor_memory_bias_applied = _first_trace_value("monitor_memory_bias_applied")
    if monitor_memory_bias_applied is None:
        monitor_memory_bias_applied = threshold_snapshot.get("monitor_memory_bias_applied")
    if monitor_memory_bias_applied is None:
        monitor_memory_bias_applied = _dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_applied")
    monitor_memory_bias_summary = _first_trace_value("monitor_memory_bias_summary")
    if not isinstance(monitor_memory_bias_summary, dict) or not monitor_memory_bias_summary:
        monitor_memory_bias_summary = _dict(threshold_snapshot.get("monitor_memory_bias_summary"))
    if not isinstance(monitor_memory_bias_summary, dict) or not monitor_memory_bias_summary:
        monitor_memory_bias_summary = _dict(_dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_summary"))
    monitor_memory_bias_deltas = _first_trace_value("monitor_memory_bias_deltas")
    if not isinstance(monitor_memory_bias_deltas, list) or not monitor_memory_bias_deltas:
        monitor_memory_bias_deltas = list(threshold_snapshot.get("monitor_memory_bias_deltas") or [])
    if not isinstance(monitor_memory_bias_deltas, list) or not monitor_memory_bias_deltas:
        monitor_memory_bias_deltas = list(_dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_deltas") or [])
    monitor_memory_bias = _first_trace_dict("monitor_memory_bias")
    if not monitor_memory_bias:
        monitor_memory_bias = _dict(threshold_snapshot.get("monitor_memory_bias"))
    if not monitor_memory_bias:
        monitor_memory_bias = _dict(_dict(policy_trace.get("policy_ref")).get("monitor_memory_bias"))
    monitor_memory_bias_hold_applied = _first_trace_value("monitor_memory_bias_hold_applied")
    if monitor_memory_bias_hold_applied is None:
        monitor_memory_bias_hold_applied = _dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_hold_applied")
    monitor_memory_bias_hold_deltas = _first_trace_value("monitor_memory_bias_hold_deltas")
    if not isinstance(monitor_memory_bias_hold_deltas, list) or not monitor_memory_bias_hold_deltas:
        monitor_memory_bias_hold_deltas = list(_dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_hold_deltas") or [])
    monitor_memory_bias_exit_applied = _first_trace_value("monitor_memory_bias_exit_applied")
    if monitor_memory_bias_exit_applied is None:
        monitor_memory_bias_exit_applied = _dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_exit_applied")
    monitor_memory_bias_exit_deltas = _first_trace_value("monitor_memory_bias_exit_deltas")
    if not isinstance(monitor_memory_bias_exit_deltas, list) or not monitor_memory_bias_exit_deltas:
        monitor_memory_bias_exit_deltas = list(_dict(policy_trace.get("policy_ref")).get("monitor_memory_bias_exit_deltas") or [])
    commander_memory_application_trace = _first_trace_dict("commander_memory_application_trace")
    if not commander_memory_application_trace:
        commander_memory_application_trace = _first_trace_dict("monitor_memory_application_trace")
    if not commander_memory_application_trace:
        commander_memory_application_trace = _dict(threshold_snapshot.get("commander_memory_application_trace"))
    if not commander_memory_application_trace:
        commander_memory_application_trace = _dict(_dict(policy_trace.get("policy_ref")).get("commander_memory_application_trace"))
    if not commander_memory_application_trace:
        commander_memory_application_trace = build_monitor_commander_memory_application_trace(
            monitor_memory_bias=monitor_memory_bias,
            entry_result={
                "applied": bool(monitor_memory_bias_applied),
                "deltas": list(monitor_memory_bias_deltas or []),
            },
            hold_result={
                "applied": bool(monitor_memory_bias_hold_applied),
                "deltas": list(monitor_memory_bias_hold_deltas or []),
            },
            exit_result={
                "applied": bool(monitor_memory_bias_exit_applied),
                "deltas": list(monitor_memory_bias_exit_deltas or []),
            },
            monitor_memory_bias_summary=monitor_memory_bias_summary,
            effective_policy_source=_clip(entry_info.get("effective_policy_source"), max_len=120),
            effective_policy_source_chain=_listify(entry_info.get("effective_policy_source_chain"), limit=8, max_len=80),
        )
    signal_snapshot = {
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_pattern": _clip(entry_info.get("pattern"), max_len=80),
        "entry_signal_chain": _listify(entry_info.get("signal_chain"), limit=8, max_len=120),
        "entry_condition_path": _clip(entry_info.get("entry_condition_path"), max_len=80),
        "entry_condition_paths_passed": _listify(entry_info.get("entry_condition_paths_passed"), limit=4, max_len=80),
        "entry_condition_scores": _dict(entry_info.get("condition_scores")),
        "entry_grouped_logic_trace": _dict(entry_info.get("grouped_logic_trace")),
        "exit_signal_detected": bool(exit_info.get("exit_signal_detected")),
        "exit_triggered": bool(exit_info.get("triggered")),
        "exit_triggered_rule": _clip(exit_info.get("reason"), max_len=180),
    }
    decision_summary = _monitor_decision_summary(
        decision_phase=decision_phase,
        primary_reason_text=_clip(primary_reason_code.replace("_", " "), max_len=220),
        threshold_snapshot=threshold_snapshot,
        signal_snapshot=signal_snapshot,
        missing_inputs=missing_inputs,
    )
    market_snapshot_refs = {
        "selected_symbol": symbol,
        "selected_price": selected.get("price"),
        "price_source": price_source,
        "feature_source": feature_source,
        "playbook": _clip(exit_info.get("playbook"), max_len=60),
        "monitor_guidance": _clip(exit_info.get("monitor_guidance"), max_len=120),
    }
    artifact = _base_output(state, agent="monitor", symbol=symbol)
    artifact.update(
        {
            "cycle_id": _clip(state.get("cycle_id"), max_len=80),
            "session_id": _clip(state.get("session_id"), max_len=80),
            "trade_id": _clip(state.get("trade_id") or state.get("story_id"), max_len=120),
            "position_snapshot": {
                "open_position_count": open_position_count,
                "symbol": symbol,
                "qty": _safe_int(exit_info.get("qty")),
                "exit_qty": _safe_int(exit_info.get("exit_qty") or exit_info.get("qty")),
                "avg_price": exit_info.get("avg_price"),
                "current_price": exit_info.get("price"),
                "peak_price": exit_info.get("peak_price"),
            },
            "thresholds_guards_used": {
                "thresholds": thresholds,
                "min_hold_sec": _safe_int(exit_info.get("min_hold_sec")),
                "sell_cooldown_sec": _safe_int(exit_info.get("sell_cooldown_sec")),
                "exit_confirm_ticks": _safe_int(exit_info.get("exit_confirm_ticks")),
                "exit_confirm_count": _safe_int(exit_info.get("exit_confirm_count")),
            },
            "evaluation_summary": _clip(exit_info.get("monitor_reason") or exit_info.get("reason") or monitor_output.get("entry_exit_reason"), max_len=220),
            "decision": str(monitor_output.get("intent_side") or "NOOP").strip().upper(),
            "decision_phase": decision_phase,
            "decision_action": decision_action,
            "decision_status": decision_status,
            "decision_summary": decision_summary,
            "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
            "primary_reason_code": primary_reason_code,
            "primary_reason_text": _clip(primary_reason_code.replace("_", " "), max_len=220),
            "secondary_reason_codes": secondary_reason_codes,
            "no_trade_surface": dict(monitor_no_trade_surface),
            "decision_outcome": _clip(monitor_no_trade_surface.get("decision_outcome"), max_len=16),
            "pre_intent_decision": _clip(monitor_no_trade_surface.get("pre_intent_decision"), max_len=16),
            "no_trade_stage": _clip(monitor_no_trade_surface.get("no_trade_stage"), max_len=32),
            "no_trade_reason_code": _clip(monitor_no_trade_surface.get("no_trade_reason_code"), max_len=120),
            "no_trade_reason_summary": _clip(monitor_no_trade_surface.get("no_trade_reason_summary"), max_len=220),
            "dominant_blocker": _clip(monitor_no_trade_surface.get("dominant_blocker"), max_len=120),
            "blocker_family": _clip(monitor_no_trade_surface.get("blocker_family"), max_len=80),
            "blocker_metrics": _dict(monitor_no_trade_surface.get("blocker_metrics")),
            "distance_to_ready": _dict(monitor_no_trade_surface.get("distance_to_ready")),
            "near_ready_flag": bool(monitor_no_trade_surface.get("near_ready_flag")),
            "required_checks_failed": _listify(monitor_no_trade_surface.get("required_checks_failed"), limit=8, max_len=120),
            "preferred_checks_failed": _listify(monitor_no_trade_surface.get("preferred_checks_failed"), limit=8, max_len=120),
            "relaxable_checks_failed": _listify(monitor_no_trade_surface.get("relaxable_checks_failed"), limit=8, max_len=120),
            "evidence_snapshot": _dict(monitor_no_trade_surface.get("evidence_snapshot")),
            "entry_blocker_surface": dict(entry_blocker_surface),
            "scanner_monitor_handoff": dict(scanner_monitor_handoff),
            "scanner_selected_symbol": _clip(scanner_monitor_handoff.get("scanner_selected_symbol"), max_len=24),
            "scanner_rank": _safe_int(scanner_monitor_handoff.get("scanner_rank")),
            "scanner_score_total": scanner_monitor_handoff.get("scanner_score_total"),
            "scanner_score_breakdown": _dict(scanner_monitor_handoff.get("scanner_score_breakdown")),
            "scanner_top_candidates": _dict_list(scanner_monitor_handoff.get("scanner_top_candidates"), limit=3),
            "scanner_vs_monitor_alignment": _clip(scanner_monitor_handoff.get("scanner_vs_monitor_alignment"), max_len=80),
            "monitor_rejection_after_top_pick": bool(scanner_monitor_handoff.get("monitor_rejection_after_top_pick")),
            "monitor_rejection_reason_code": _clip(scanner_monitor_handoff.get("monitor_rejection_reason_code"), max_len=120),
            "monitor_rejection_reason_summary": _clip(scanner_monitor_handoff.get("monitor_rejection_reason_summary"), max_len=220),
            "handoff_trace": _listify(scanner_monitor_handoff.get("handoff_trace"), limit=6, max_len=120),
            "entry_candidate_cascade": dict(entry_candidate_cascade),
            "monitor_focus_context": dict(monitor_focus_context),
            "entry_candidate_symbol": _clip(monitor_focus_context.get("entry_candidate_symbol"), max_len=24),
            "entry_final_symbol": _clip(monitor_focus_context.get("entry_final_symbol"), max_len=24),
            "position_focus_symbol": _clip(monitor_focus_context.get("position_focus_symbol"), max_len=24),
            "monitor_output_symbol": _clip(monitor_focus_context.get("monitor_output_symbol"), max_len=24),
            "monitor_focus_mode": _clip(monitor_focus_context.get("focus_mode"), max_len=80),
            "threshold_snapshot": threshold_snapshot,
            "applied_policy": _dict(entry_info.get("applied_policy")) or _dict(entry_info.get("thresholds")),
            "received_policy": _dict(entry_info.get("received_policy")),
            "received_policy_source": _clip(entry_info.get("received_policy_source"), max_len=120),
            "effective_policy": _dict(entry_info.get("effective_policy")) or _dict(entry_info.get("applied_policy")) or _dict(entry_info.get("thresholds")),
            "effective_policy_source": _clip(entry_info.get("effective_policy_source"), max_len=120),
            "effective_policy_source_chain": _listify(entry_info.get("effective_policy_source_chain"), limit=6, max_len=80),
            "monitor_memory_bias_applied": bool(monitor_memory_bias_applied) if monitor_memory_bias_applied is not None else None,
            "monitor_memory_bias": monitor_memory_bias,
            "monitor_memory_bias_summary": monitor_memory_bias_summary,
            "monitor_memory_bias_deltas": [
                {
                    "field": _clip((row or {}).get("field"), max_len=80),
                    "delta": (row or {}).get("delta"),
                    "from": (row or {}).get("from"),
                    "to": (row or {}).get("to"),
                }
                for row in list(monitor_memory_bias_deltas or [])[:8]
                if isinstance(row, dict)
            ],
            "monitor_memory_bias_hold_applied": bool(monitor_memory_bias_hold_applied) if monitor_memory_bias_hold_applied is not None else None,
            "monitor_memory_bias_hold_deltas": [
                {
                    "field": _clip((row or {}).get("field"), max_len=80),
                    "delta": (row or {}).get("delta"),
                    "from": (row or {}).get("from"),
                    "to": (row or {}).get("to"),
                }
                for row in list(monitor_memory_bias_hold_deltas or [])[:8]
                if isinstance(row, dict)
            ],
            "monitor_memory_bias_exit_applied": bool(monitor_memory_bias_exit_applied) if monitor_memory_bias_exit_applied is not None else None,
            "monitor_memory_bias_exit_deltas": [
                {
                    "field": _clip((row or {}).get("field"), max_len=80),
                    "delta": (row or {}).get("delta"),
                    "from": (row or {}).get("from"),
                    "to": (row or {}).get("to"),
                }
                for row in list(monitor_memory_bias_exit_deltas or [])[:8]
                if isinstance(row, dict)
            ],
            "commander_memory_application_trace": commander_memory_application_trace,
            "monitor_memory_application_trace": commander_memory_application_trace,
            "policy_adjustments": _dict(entry_info.get("policy_adjustments")),
            "policy_adjustment_summary": _clip(entry_info.get("policy_adjustment_summary"), max_len=220),
            "policy_adjustment_reasoning": _clip(entry_info.get("policy_adjustment_reasoning"), max_len=260),
            "effective_policy_deltas": [
                {
                    "field": _clip((row or {}).get("field"), max_len=80),
                    "from": (row or {}).get("from"),
                    "to": (row or {}).get("to"),
                }
                for row in list(entry_info.get("effective_policy_deltas") or [])[:8]
                if isinstance(row, dict)
            ],
            "policy_source": _clip(_dict(policy_trace.get("policy_ref")).get("policy_source"), max_len=120),
            "policy_validation_status": _clip(_dict(policy_trace.get("policy_ref")).get("policy_validation_status"), max_len=80),
            "policy_fallback_used": _dict(policy_trace.get("policy_ref")).get("policy_fallback_used"),
            "policy_fallback_reason": _clip(_dict(policy_trace.get("policy_ref")).get("policy_fallback_reason"), max_len=220),
            "policy_partial_normalized": _dict(policy_trace.get("policy_ref")).get("policy_partial_normalized"),
            "policy_default_filled_fields": _listify(_dict(policy_trace.get("policy_ref")).get("policy_default_filled_fields"), limit=12, max_len=80),
            "policy_validation_missing_fields": _listify(_dict(policy_trace.get("policy_ref")).get("policy_validation_missing_fields"), limit=12, max_len=80),
            "policy_validation_invalid_fields": _listify(_dict(policy_trace.get("policy_ref")).get("policy_validation_invalid_fields"), limit=12, max_len=80),
            "override_reason": _clip(_dict(policy_trace.get("policy_ref")).get("override_reason"), max_len=180),
            "applied_policy_source_chain": _listify(_dict(policy_trace.get("policy_ref")).get("applied_policy_source_chain"), limit=6, max_len=80),
            "signal_snapshot": signal_snapshot,
            "entry_minute_source_present": entry_minute_source_present,
            "entry_minute_source_used": _clip(entry_minute_source_used, max_len=80),
            "entry_minute_refetch_attempted": entry_minute_refetch_attempted,
            "entry_minute_refetch_succeeded": entry_minute_refetch_succeeded,
            "entry_minute_refetch_failure_reason": _clip(entry_minute_refetch_failure_reason, max_len=120),
            "entry_minute_refetch_failure_detail": _clip(entry_minute_refetch_failure_detail, max_len=220),
            "entry_minute_refetch_runner_source": _clip(entry_minute_refetch_runner_source, max_len=80),
            "entry_chart_structure_features": entry_chart_structure_features,
            "policy_interpreter_trace": entry_policy_interpreter_trace,
            "policy_alignment_summary": entry_policy_alignment_summary,
            "entry_condition_path": _clip(entry_info.get("entry_condition_path"), max_len=80),
            "entry_condition_paths_passed": _listify(entry_info.get("entry_condition_paths_passed"), limit=4, max_len=80),
            "entry_condition_scores": _dict(entry_info.get("condition_scores")),
            "entry_grouped_logic_trace": _dict(entry_info.get("grouped_logic_trace")),
            "market_snapshot_refs": market_snapshot_refs,
            "policy_ref": dict(policy_trace.get("policy_ref") or {}),
            "entry_check_summary": str(policy_trace.get("entry_check_summary") or ""),
            "entry_blockers": list(policy_trace.get("entry_blockers") or []),
            "timing_assessment": dict(policy_trace.get("timing_assessment") or {}),
            "exit_trigger_basis": dict(policy_trace.get("exit_trigger_basis") or {}),
            "commander_context_consumed": policy_trace.get("commander_context_consumed"),
            "consumed_fields": list(policy_trace.get("consumed_fields") or []),
            "flow_instruction_applied": policy_trace.get("flow_instruction_applied"),
            "no_trade_reason_applied": policy_trace.get("no_trade_reason_applied"),
            "shadow_used": policy_trace.get("shadow_used"),
            "strategist_fallback_used": policy_trace.get("strategist_fallback_used"),
            "decision_trace": {
                "policy_ref": dict(policy_trace.get("policy_ref") or {}),
                "entry_check_summary": str(policy_trace.get("entry_check_summary") or ""),
                "entry_blockers": list(policy_trace.get("entry_blockers") or []),
                "timing_assessment": dict(policy_trace.get("timing_assessment") or {}),
                "exit_trigger_basis": dict(policy_trace.get("exit_trigger_basis") or {}),
                "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
                "commander_context_consumed": policy_trace.get("commander_context_consumed"),
                "consumed_fields": list(policy_trace.get("consumed_fields") or []),
                "flow_instruction_applied": policy_trace.get("flow_instruction_applied"),
                "no_trade_reason_applied": policy_trace.get("no_trade_reason_applied"),
                "shadow_used": policy_trace.get("shadow_used"),
                "strategist_fallback_used": policy_trace.get("strategist_fallback_used"),
                "received_policy": _dict(entry_info.get("received_policy")),
                "received_policy_source": _clip(entry_info.get("received_policy_source"), max_len=120),
                "effective_policy": _dict(entry_info.get("effective_policy")) or _dict(entry_info.get("applied_policy")) or _dict(entry_info.get("thresholds")),
                "effective_policy_source": _clip(entry_info.get("effective_policy_source"), max_len=120),
                "effective_policy_source_chain": _listify(entry_info.get("effective_policy_source_chain"), limit=6, max_len=80),
                "policy_adjustments": _dict(entry_info.get("policy_adjustments")),
                "policy_adjustment_summary": _clip(entry_info.get("policy_adjustment_summary"), max_len=220),
                "policy_adjustment_reasoning": _clip(entry_info.get("policy_adjustment_reasoning"), max_len=260),
                "effective_policy_deltas": [
                    {
                        "field": _clip((row or {}).get("field"), max_len=80),
                        "from": (row or {}).get("from"),
                        "to": (row or {}).get("to"),
                    }
                    for row in list(entry_info.get("effective_policy_deltas") or [])[:8]
                    if isinstance(row, dict)
                ],
            },
            "decision_reason_chain": decision_reason_chain,
            "intent_emitted": bool(intents),
            "intent_id": _clip(first_intent.get("intent_id") or first_intent.get("id"), max_len=120),
            "evidence_quality": evidence_quality,
            "missing_inputs": missing_inputs,
            "generated_at": _utc_now_iso(),
            "monitor_evaluation": {
                "triggered_rules": triggered_rules,
                "blocked_rules": blocked_rules[:8],
                "posture": posture,
                "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
                "entry_pattern": _clip(entry_info.get("pattern"), max_len=80),
                "entry_passed_checks": list(entry_info.get("passed_checks") or []),
                "entry_failed_checks": list(entry_info.get("failed_checks") or []),
                "entry_threshold_margins": _dict(entry_info.get("threshold_margins")),
                "entry_condition_path": _clip(entry_info.get("entry_condition_path"), max_len=80),
                "entry_condition_paths_passed": _listify(entry_info.get("entry_condition_paths_passed"), limit=4, max_len=80),
                "entry_condition_scores": _dict(entry_info.get("condition_scores")),
                "entry_grouped_logic_trace": _dict(entry_info.get("grouped_logic_trace")),
                "policy_ref": dict(policy_trace.get("policy_ref") or {}),
                "entry_check_summary": str(policy_trace.get("entry_check_summary") or ""),
                "entry_blockers": list(policy_trace.get("entry_blockers") or []),
                "timing_assessment": dict(policy_trace.get("timing_assessment") or {}),
                "commander_context_consumed": policy_trace.get("commander_context_consumed"),
                "consumed_fields": list(policy_trace.get("consumed_fields") or []),
                "flow_instruction_applied": policy_trace.get("flow_instruction_applied"),
                "no_trade_reason_applied": policy_trace.get("no_trade_reason_applied"),
                "shadow_used": policy_trace.get("shadow_used"),
                "strategist_fallback_used": policy_trace.get("strategist_fallback_used"),
            },
            "monitor_action_decision": {
                "decision": str(monitor_output.get("intent_side") or "NOOP").strip().upper(),
                "action_reason_human": _clip(monitor_output.get("entry_exit_reason") or exit_info.get("monitor_reason") or exit_info.get("reason"), max_len=240),
                "decision_reason_chain": decision_reason_chain,
                "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
                "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
                "confidence": _safe_float(entry_info.get("confidence"), 0.0),
                "triggered_rules": triggered_rules,
                "blocked_rules": blocked_rules[:8],
                "policy_ref": dict(policy_trace.get("policy_ref") or {}),
                "entry_check_summary": str(policy_trace.get("entry_check_summary") or ""),
                "entry_blockers": list(policy_trace.get("entry_blockers") or []),
                "entry_condition_path": _clip(entry_info.get("entry_condition_path"), max_len=80),
                "entry_condition_paths_passed": _listify(entry_info.get("entry_condition_paths_passed"), limit=4, max_len=80),
                "entry_condition_scores": _dict(entry_info.get("condition_scores")),
                "entry_grouped_logic_trace": _dict(entry_info.get("grouped_logic_trace")),
                "exit_trigger_basis": dict(policy_trace.get("exit_trigger_basis") or {}),
                "commander_context_consumed": policy_trace.get("commander_context_consumed"),
                "consumed_fields": list(policy_trace.get("consumed_fields") or []),
                "shadow_used": policy_trace.get("shadow_used"),
                "strategist_fallback_used": policy_trace.get("strategist_fallback_used"),
            },
            "trigger_details": {
                "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
                "watch_axes": watch_axes[:8],
                "exit_triggered": bool(exit_info.get("triggered")),
                "sell_guard_blocked": bool(exit_info.get("sell_guard_blocked")),
                "sell_guard_reason": _clip(exit_info.get("sell_guard_reason"), max_len=180),
                "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
            },
            "evidence_refs": {
                "event_names": [
                    "monitor.threshold_snapshot",
                    "monitor.state_transition",
                    "monitor.exit_decision_detail",
                    "monitor.cycle_summary",
                ],
                "watch_axes": watch_axes[:8],
            },
            # compatibility-rich fields for downstream readers
            "entry_reason": _clip(monitor_output.get("entry_exit_reason"), max_len=160),
            "monitor_reason": _clip(exit_info.get("monitor_reason"), max_len=160),
            "exit_reason": _clip(exit_info.get("reason"), max_len=160),
            "thresholds": thresholds,
            "current_price": exit_info.get("price"),
            "price": exit_info.get("price"),
            "raw_price": exit_info.get("raw_price"),
            "technical_price": exit_info.get("technical_price"),
            "technical_price_source": _clip(exit_info.get("technical_price_source"), max_len=120),
            "effective_price": exit_info.get("effective_price"),
            "average_price": exit_info.get("avg_price"),
            "avg_price": exit_info.get("avg_price"),
            "peak_price": exit_info.get("peak_price"),
            "account_current_price": exit_info.get("account_current_price"),
            "account_mark_price": exit_info.get("account_mark_price"),
            "account_mark_price_source": _clip(exit_info.get("account_mark_price_source"), max_len=120),
            "account_unrealized_pnl": exit_info.get("account_unrealized_pnl"),
            "account_pnl_ratio_source": _clip(exit_info.get("account_pnl_ratio_source"), max_len=120),
            "current_drawdown": exit_info.get("current_drawdown"),
            "peak_drawdown": exit_info.get("peak_drawdown"),
            "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
            "peak_drawdown_source": _clip(exit_info.get("peak_drawdown_source"), max_len=120),
            "exit_trigger_metric_name": _clip(exit_info.get("exit_trigger_metric_name"), max_len=120),
            "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
            "exit_trigger_metric_source": _clip(exit_info.get("exit_trigger_metric_source"), max_len=120),
            "risk_reward_take_profit_target_pct": exit_info.get("risk_reward_take_profit_target_pct"),
            "risk_reward_take_profit_rung": exit_info.get("risk_reward_take_profit_rung"),
            "resistance_price": exit_info.get("resistance_price"),
            "resistance_price_source": _clip(exit_info.get("resistance_price_source"), max_len=120),
            "resistance_distance_pct": exit_info.get("resistance_distance_pct"),
            "profit_time_stop_peak_giveback_pct": exit_info.get("profit_time_stop_peak_giveback_pct"),
            "partial_exit": bool(exit_info.get("partial_exit")),
            "exit_qty": exit_info.get("exit_qty"),
            "exit_qty_fraction": exit_info.get("exit_qty_fraction"),
            "profit_ladder_level_pct": exit_info.get("profit_ladder_level_pct"),
            "profit_ladder_level_index": exit_info.get("profit_ladder_level_index"),
            "volume_ratio": exit_info.get("volume_ratio"),
            "execution_strength": exit_info.get("execution_strength"),
            "trade_strength": exit_info.get("trade_strength"),
            "opening_gap_chase_observed": bool(exit_info.get("opening_gap_chase_observed")),
            "open_gap_pct": exit_info.get("open_gap_pct"),
            "prev_close_distance_pct": exit_info.get("prev_close_distance_pct"),
            "vwap_distance": exit_info.get("vwap_distance"),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "price_source": price_source,
            "effective_price_source": _clip(exit_info.get("effective_price_source"), max_len=120),
            "price_source_policy": _clip(exit_info.get("price_source_policy"), max_len=260),
            "feature_source": feature_source,
            "raw_pnl_ratio": exit_info.get("raw_pnl_ratio"),
            "gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
            "technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
            "effective_pnl_ratio": exit_info.get("effective_pnl_ratio"),
            "stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
            "stop_pnl_ratio_source": _clip(exit_info.get("stop_pnl_ratio_source"), max_len=120),
            "hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
            "hard_stop_pnl_ratio_source": _clip(exit_info.get("hard_stop_pnl_ratio_source"), max_len=120),
            "cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
            "cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
            "cost_drag_pressure_reason": _clip(exit_info.get("cost_drag_pressure_reason"), max_len=180),
            "stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
            "stop_loss_cost_drag_blocked_reason": _clip(
                exit_info.get("stop_loss_cost_drag_blocked_reason"),
                max_len=180,
            ),
            "account_pnl_ratio": exit_info.get("account_pnl_ratio"),
            "pnl_crosscheck_applied": bool(exit_info.get("pnl_crosscheck_applied")),
            "pnl_crosscheck_reason": _clip(exit_info.get("pnl_crosscheck_reason"), max_len=180),
            "pnl_crosscheck_gap": exit_info.get("pnl_crosscheck_gap"),
            "price_crosscheck_gap": exit_info.get("price_crosscheck_gap"),
            "price_anomaly_flag": bool(exit_info.get("price_anomaly_flag")),
            "price_anomaly_reason": _clip(exit_info.get("price_anomaly_reason"), max_len=180),
            "pnl_fallback_applied": bool(exit_info.get("pnl_fallback_applied")),
            "fallback_price_source": _clip(exit_info.get("fallback_price_source"), max_len=120),
            "final_exit_thresholds": _dict(exit_info.get("final_exit_thresholds")),
            "exit_threshold_source": _clip(exit_info.get("exit_threshold_source"), max_len=120),
            "hold_block_reason": _clip(exit_info.get("hold_block_reason"), max_len=180),
            "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
            "watch_axes": watch_axes[:8],
            "exit_triggered": bool(exit_info.get("triggered")),
            "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


def build_supervisor_output_artifact(
    state: Dict[str, Any],
    *,
    order: Dict[str, Any],
    allowed: bool,
    reason: str,
    details: Dict[str, Any] | None = None,
    strategy_policy_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    symbol = str(order.get("symbol") or order.get("stk_cd") or "").strip()
    artifact = _base_output(state, agent="supervisor", symbol=symbol, status="ok" if allowed else "blocked")
    artifact.update(
        {
            "invoked_agents": ["supervisor"],
            "command": str(order.get("action") or "").strip().upper(),
            "decision": "approve" if allowed else "block",
            "approval_result": bool(allowed),
            "reason": _clip(reason, max_len=220),
            "blocked_allowed_details": _dict(details),
            "supervisor_allow": bool(allowed),
            "verdict": "approve" if allowed else "block",
            "supervisor_reason": _clip(reason, max_len=220),
            "guard_reason": _clip(reason, max_len=220),
            "action": str(order.get("action") or "").strip().upper(),
            "symbol": symbol,
            "order_request_summary": {
                "action": str(order.get("action") or "").strip().upper(),
                "symbol": symbol,
                "qty": _safe_int(order.get("qty")),
                "order_type": _clip(order.get("order_type"), max_len=32),
            },
            "strategy_policy_summary": _dict(strategy_policy_summary),
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


def build_executor_output_artifact(
    state: Dict[str, Any],
    *,
    execution: Dict[str, Any],
    order: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    execution = _dict(execution)
    order = _dict(order)
    execution_payload = _dict(execution.get("payload"))
    response_payload = _dict(execution_payload.get("response_payload"))
    quote_snapshot = _dict(execution.get("quote_snapshot"))
    symbol = str(execution.get("symbol") or order.get("symbol") or "").strip()
    if "execution_ok" in execution:
        execution_ok = bool(execution.get("execution_ok"))
    elif "ok" in execution:
        execution_ok = bool(execution.get("ok"))
    else:
        execution_ok = bool(execution.get("allowed"))
    artifact = _base_output(
        state,
        agent="executor",
        symbol=symbol,
        status="ok" if bool(execution.get("allowed")) and execution_ok else "error",
    )
    artifact.update(
        {
            "action": str(execution.get("action") or order.get("action") or "").strip().upper(),
            "allowed": bool(execution.get("allowed")),
            "symbol": symbol,
            "qty": _safe_int(order.get("qty") or execution.get("qty")),
            "status": _clip(
                execution.get("status")
                or execution_payload.get("status")
                or response_payload.get("return_msg"),
                max_len=80,
            ),
            "reason": _clip(execution.get("reason"), max_len=220),
            "broker_env": _clip(execution.get("broker_env") or execution_payload.get("broker_env"), max_len=32),
            "effective_mode": _clip(execution.get("effective_mode") or execution_payload.get("effective_mode"), max_len=64),
            "broker_message": _clip(
                execution.get("broker_message")
                or execution_payload.get("broker_message")
                or response_payload.get("return_msg"),
                max_len=200,
            ),
            "ord_no": _clip(
                execution.get("ord_no")
                or execution.get("order_id")
                or execution_payload.get("ord_no")
                or execution_payload.get("order_id")
                or response_payload.get("ord_no")
                or response_payload.get("order_id"),
                max_len=64,
            ),
            "execution_ok": execution_ok,
            "quote_snapshot": quote_snapshot,
            "best_bid": _safe_float(execution.get("best_bid") if execution.get("best_bid") not in (None, "") else quote_snapshot.get("best_bid")),
            "best_ask": _safe_float(execution.get("best_ask") if execution.get("best_ask") not in (None, "") else quote_snapshot.get("best_ask")),
            "spread_bps": _safe_float(execution.get("spread_bps") if execution.get("spread_bps") not in (None, "") else quote_snapshot.get("spread_bps")),
            "order_request_summary": {
                "action": str(order.get("action") or execution.get("action") or "").strip().upper(),
                "symbol": symbol,
                "qty": _safe_int(order.get("qty") or execution.get("qty")),
                "order_type": _clip(order.get("order_type"), max_len=32),
                "best_bid": _safe_float(execution.get("best_bid") if execution.get("best_bid") not in (None, "") else quote_snapshot.get("best_bid")),
                "best_ask": _safe_float(execution.get("best_ask") if execution.get("best_ask") not in (None, "") else quote_snapshot.get("best_ask")),
                "spread_bps": _safe_float(execution.get("spread_bps") if execution.get("spread_bps") not in (None, "") else quote_snapshot.get("spread_bps")),
            },
            "execution_enabled": bool(execution.get("allowed")),
            "approval_mode": _clip(execution.get("approval_mode"), max_len=32),
            "broker_result": {
                "status": _clip(
                    execution.get("status")
                    or execution_payload.get("status")
                    or response_payload.get("return_msg"),
                    max_len=80,
                ),
                "broker_message": _clip(
                    execution.get("broker_message")
                    or execution_payload.get("broker_message")
                    or response_payload.get("return_msg"),
                    max_len=200,
                ),
                "ord_no": _clip(
                    execution.get("ord_no")
                    or execution.get("order_id")
                    or execution_payload.get("ord_no")
                    or execution_payload.get("order_id")
                    or response_payload.get("ord_no")
                    or response_payload.get("order_id"),
                    max_len=64,
                ),
                "effective_mode": _clip(execution.get("effective_mode") or execution_payload.get("effective_mode"), max_len=64),
                "broker_env": _clip(execution.get("broker_env") or execution_payload.get("broker_env"), max_len=32),
            },
            "final_execution_status": _clip(
                execution.get("status")
                or execution_payload.get("status")
                or response_payload.get("return_msg"),
                max_len=80,
            ) or ("allowed" if execution.get("allowed") else "blocked"),
            "failure_reason": _clip(execution.get("reason"), max_len=220),
            "strategy_policy_summary": _dict(execution.get("strategy_policy_summary")),
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


def _build_commander_shadow_artifact_summary(
    state: Dict[str, Any],
    *,
    mode: str,
    phase: str,
    path: str,
    status: str,
    reason: str = "",
) -> Dict[str, Any]:
    try:
        return build_commander_shadow_artifact(
            state,
            mode=str(mode or ""),
            phase=str(phase or ""),
            path=str(path or ""),
            status=str(status or "ok"),
            reason=str(reason or ""),
        )
    except Exception:
        return {}


def build_commander_output_artifact(
    state: Dict[str, Any],
    *,
    mode: str,
    phase: str,
    path: str,
    status: str,
    reason: str = "",
) -> Dict[str, Any]:
    decision_frame = _dict(state.get("commander_decision_frame"))
    commander_decision = _dict(state.get("commander_decision"))
    shadow_assessment = _build_commander_shadow_artifact_summary(
        state,
        mode=mode,
        phase=phase,
        path=path,
        status=status,
        reason=reason,
    )
    runtime_plan = _dict(state.get("runtime_plan"))
    runtime_fast_path = _dict(state.get("runtime_fast_path"))
    resilience = _dict(state.get("runtime_resilience_state"))
    if not resilience:
        resilience = _dict(state.get("resilience"))
    strategist_output = _dict(state.get("strategist_output"))
    portfolio_snapshot = _dict(state.get("portfolio_snapshot"))
    preflight = _dict(state.get("portfolio_preflight"))
    positions = [row for row in list(portfolio_snapshot.get("positions") or []) if isinstance(row, dict)]
    open_symbols = _dedupe_text([str(row.get("symbol") or "").strip() for row in positions], limit=12, max_len=32)
    status_text = str(status or "ok")
    runtime_status = _clip(state.get("runtime_status"), max_len=80)
    path_text = str(path or "").strip()
    phase_text = str(phase or "").strip()
    selected_route = "full_cycle"
    if "monitor_only" in path_text:
        selected_route = "monitor_only"
    elif "cached" in path_text:
        selected_route = "cached_strategist"
    elif phase_text == "preopen" or "preopen" in path_text:
        selected_route = "preopen"
    elif phase_text == "closeout" or "closeout" in path_text:
        selected_route = "closeout"
    elif "blocked" in path_text or status_text in {"blocked", "preflight_blocked"}:
        selected_route = "blocked"
    elif runtime_status in {"error", "cooldown_wait", "degraded"}:
        selected_route = "degraded"
    route_reason_codes = _dedupe_text(
        [
            _clip(reason, max_len=120),
            _clip(runtime_status, max_len=120),
            _clip(state.get("runtime_transition"), max_len=120),
            _clip(runtime_fast_path.get("reason"), max_len=120),
            "portfolio_preflight_blocked" if bool(preflight.get("blocked")) else "",
            "strategist_blocked" if bool(state.get("strategist_blocked")) else "",
        ],
        limit=8,
        max_len=120,
    )
    cooldown_until_epoch = _safe_int(resilience.get("cooldown_until_epoch"), 0)
    cooldown_applied = (
        _clip(state.get("runtime_transition"), max_len=40) == "cooldown"
        or runtime_status == "cooldown_wait"
        or cooldown_until_epoch > 0
    )
    strategist_cache_used = selected_route == "cached_strategist" or bool(runtime_fast_path.get("cache_age_sec"))
    strategist_blocked = (
        bool(state.get("strategist_blocked"))
        or bool(strategist_output.get("llm_frame_blocked"))
        or ("strategist_blocked" in path_text)
    )
    handoff_instruction = _clip(
        decision_frame.get("handoff_instruction")
        or ("Proceed with planned agent chain." if status_text in {"ok", "ready", "preopen_ready", "closeout_ready"} else "Stop downstream execution and inspect runtime status."),
        max_len=220,
    )
    commander_market_regime = _clip(
        commander_decision.get("market_regime")
        or _dict(decision_frame.get("market_regime_summary")).get("market_regime")
        or strategist_output.get("market_regime"),
        max_len=80,
    )
    commander_session_bias = _clip(
        commander_decision.get("session_bias")
        or decision_frame.get("session_type")
        or phase,
        max_len=80,
    )
    commander_risk_mode = _clip(commander_decision.get("risk_mode"), max_len=80)
    allowed_playbooks = _listify(commander_decision.get("allowed_playbooks"), limit=6, max_len=40)
    banned_playbooks = _listify(commander_decision.get("banned_playbooks"), limit=6, max_len=40)
    scanner_mission = _clip(commander_decision.get("scanner_mission"), max_len=220)
    monitor_mission = _clip(commander_decision.get("monitor_mission"), max_len=220)
    llm_invocation_policy = _clip(
        commander_decision.get("llm_invocation_policy")
        or commander_decision.get("llm_policy"),
        max_len=120,
    )
    decision_summary = _clip(
        commander_decision.get("decision_summary")
        or decision_frame.get("final_reason")
        or reason
        or state.get("runtime_status"),
        max_len=280,
    )
    shadow_reason_code = _clip(shadow_assessment.get("no_trade_reason_code"), max_len=80)
    shadow_assessment_summary = _clip(
        shadow_assessment.get("reason_summary")
        or shadow_assessment.get("comparison_summary"),
        max_len=280,
    )
    shadow_alignment = _clip(
        (
            _dict(shadow_assessment.get("post_strategist_assessment")).get("recommendation_gap")
            or _dict(shadow_assessment.get("end_of_cycle_summary")).get("recommendation_gap")
        ),
        max_len=120,
    )
    source_priority = _listify(commander_decision.get("source_priority"), limit=4, max_len=40)
    strategist_fallback_used = bool(commander_decision.get("strategist_fallback_used"))
    strategist_refresh_requested = bool(commander_decision.get("strategist_refresh_requested"))
    strategist_refresh_reason = _clip(commander_decision.get("strategist_refresh_reason"), max_len=120)
    strategist_refresh_context = _dict(commander_decision.get("strategist_refresh_context"))
    strategist_cache_preferred = bool(commander_decision.get("strategist_cache_preferred"))
    strategist_cache_preference_reason = _clip(commander_decision.get("strategist_cache_preference_reason"), max_len=120)
    strategist_cache_preference_context = _dict(commander_decision.get("strategist_cache_preference_context"))
    shadow_runtime = _dict(state.get("commander_shadow_runtime"))
    runtime_refresh_requested = bool(shadow_runtime.get("pre_buy_refresh_requested"))
    runtime_refresh_reason = _clip(shadow_runtime.get("pre_buy_refresh_reason"), max_len=120)
    runtime_refresh_context = _dict(shadow_runtime.get("pre_buy_refresh_context"))
    post_scanner_refresh_requested = bool(shadow_runtime.get("post_scanner_refresh_requested"))
    post_scanner_refresh_reason = _clip(shadow_runtime.get("post_scanner_refresh_reason"), max_len=120)
    post_scanner_refresh_context = _dict(shadow_runtime.get("post_scanner_refresh_context"))
    if not post_scanner_refresh_requested and _clip(runtime_fast_path.get("reason"), max_len=120) == "post_scanner_selected_symbol_refresh":
        post_scanner_refresh_requested = True
        post_scanner_refresh_reason = _clip(runtime_fast_path.get("strategist_refresh_reason"), max_len=120)
        post_scanner_refresh_context = {"selected_symbol": _clip(runtime_fast_path.get("selected_symbol"), max_len=32)}
    runtime_cache_reuse_reason = _clip(
        runtime_fast_path.get("reason") if strategist_cache_used else "",
        max_len=120,
    )
    runtime_cache_reuse_context = _dict(runtime_fast_path) if strategist_cache_used else {}
    applied_policy = _dict(commander_decision.get("applied_policy"))
    commander_horizon_policy = (
        _dict(commander_decision.get("commander_horizon_policy"))
        or _dict(state.get("commander_horizon_policy"))
        or _dict(applied_policy.get("horizon"))
        or _dict(applied_policy.get("commander_horizon_policy"))
    )
    horizon_context = _dict(commander_decision.get("horizon_context")) or _dict(state.get("horizon_context"))
    policy_source = _clip(commander_decision.get("policy_source"), max_len=120)
    policy_validation_status = _clip(commander_decision.get("policy_validation_status"), max_len=80)
    policy_fallback_used = bool(commander_decision.get("policy_fallback_used"))
    policy_fallback_reason = _clip(commander_decision.get("policy_fallback_reason"), max_len=220)
    policy_partial_normalized = bool(commander_decision.get("policy_partial_normalized"))
    policy_default_filled_fields = _listify(commander_decision.get("policy_default_filled_fields"), limit=12, max_len=80)
    policy_validation_missing_fields = _listify(commander_decision.get("policy_validation_missing_fields"), limit=12, max_len=80)
    policy_validation_invalid_fields = _listify(commander_decision.get("policy_validation_invalid_fields"), limit=12, max_len=80)
    override_triggered = bool(commander_decision.get("override_triggered"))
    override_reason = _clip(commander_decision.get("override_reason"), max_len=180)
    override_action = _clip(commander_decision.get("override_action"), max_len=120)
    override_context = _dict(commander_decision.get("override_context"))
    applied_policy_source_chain = _listify(commander_decision.get("applied_policy_source_chain"), limit=6, max_len=80)
    reporter_feedback_mode = _clip(commander_decision.get("reporter_feedback_mode"), max_len=40)
    reporter_feedback_mode_source = _clip(commander_decision.get("reporter_feedback_mode_source"), max_len=80)
    reporter_feedback_mode_reason = _clip(commander_decision.get("reporter_feedback_mode_reason"), max_len=120)
    reporter_feedback_semantics = _clip(commander_decision.get("reporter_feedback_semantics"), max_len=40)
    commander_applied_policy_summary = _dict(commander_decision.get("commander_applied_policy_summary"))
    policy_sources = _dict(commander_decision.get("policy_sources"))
    strategist_runtime_policy_source = _clip(commander_decision.get("strategist_runtime_policy_source"), max_len=80)
    llm_policy_source = _clip(commander_decision.get("llm_policy_source"), max_len=80)
    llm_execution_profile_source = _clip(commander_decision.get("llm_execution_profile_source"), max_len=80)
    reporter_policy_source = _clip(commander_decision.get("reporter_policy_source"), max_len=80)
    monitor_policy_source = _clip(commander_decision.get("monitor_policy_source"), max_len=80)
    scanner_policy_source = _clip(commander_decision.get("scanner_policy_source"), max_len=80)
    execution_policy_source = _clip(commander_decision.get("execution_policy_source"), max_len=80)
    route_observability = (
        _dict(state.get("commander_route_observability"))
        or build_commander_route_observability_surface(
            selected_route=selected_route,
            route_reason=decision_summary,
            commander_decision=commander_decision,
            runtime_fast_path=runtime_fast_path,
            resilience=resilience,
            runtime_status=state.get("runtime_status"),
            runtime_transition=state.get("runtime_transition"),
        )
    )
    observations = {
        **_dict(commander_decision.get("observations")),
        **_commander_shadow_observations(state, path=path),
    }
    
    # Determine actual invocation and strategy source for explicit ownership
    actual_strategist_invocation = shadow_runtime.get("strategist_executed")
    if actual_strategist_invocation is None:
        actual_strategist_invocation = not strategist_cache_used and selected_route not in ("monitor_only", "blocked")
    actual_strategy_source = "cached_strategist" if strategist_cache_used else ("fresh_strategist" if actual_strategist_invocation else "none")

    artifact = _base_output(state, agent="commander", status=status or "ok")
    artifact.update(
        {
            "ownership_version": "1.0",
            "actual_strategist_invocation": bool(actual_strategist_invocation),
            "actual_strategy_source": actual_strategy_source,
            "mode": str(mode or "").strip(),
            "phase": str(phase or "").strip(),
            "path": str(path or "").strip(),
            "runtime_mode": str(mode or "").strip(),
            "runtime_phase": phase_text,
            "selected_route": selected_route,
            "route_reason_codes": route_reason_codes,
            "route_reason_text": _clip(
                " / ".join(route_reason_codes) if route_reason_codes else (reason or state.get("runtime_status") or ""),
                max_len=280,
            ),
            "open_position_count": _safe_int(len(positions)),
            "open_position_symbols": open_symbols,
            "strategist_cache_used": strategist_cache_used,
            "strategist_blocked": strategist_blocked,
            "cooldown_applied": cooldown_applied,
            "incident_state": {
                "incident_count": _safe_int(resilience.get("incident_count")),
                "cooldown_until_epoch": cooldown_until_epoch,
                "degrade_mode": _clip(resilience.get("degrade_mode"), max_len=80),
                "last_error_type": _clip(resilience.get("last_error_type"), max_len=120),
                "last_error_ts": _clip(resilience.get("last_error_ts"), max_len=80),
            },
            "portfolio_preflight_result": preflight,
            "generated_at": _utc_now_iso(),
            "session_type": _clip(decision_frame.get("session_type") or runtime_plan.get("phase") or phase, max_len=40),
            "market_clock_phase": _clip(decision_frame.get("market_clock_phase") or phase or runtime_plan.get("phase"), max_len=40),
            "portfolio_state_summary": {
                "position_count": _safe_int(len(positions)),
                "cash": portfolio_snapshot.get("cash"),
                "positions_source": _clip(preflight.get("positions_source"), max_len=80),
                "preflight_status": _clip(preflight.get("status"), max_len=80),
            },
            "market_regime_summary": {
                "market_regime": _clip(strategist_output.get("market_regime"), max_len=80),
                "market_sentiment": _clip(strategist_output.get("market_sentiment"), max_len=80),
                "playbook": _clip(strategist_output.get("playbook"), max_len=80),
            },
            "market_regime": commander_market_regime,
            "session_bias": commander_session_bias,
            "risk_mode": commander_risk_mode,
            "allowed_playbooks": allowed_playbooks,
            "banned_playbooks": banned_playbooks,
            "scanner_mission": scanner_mission,
            "monitor_mission": monitor_mission,
            "llm_invocation_policy": llm_invocation_policy,
            "scanner_policy": dict(commander_decision.get("scanner_policy") or {}),
            "monitor_feedback": _dict(commander_decision.get("monitor_feedback")),
            "adaptive_policy": _dict(commander_decision.get("adaptive_policy")),
            "policy_adjustment_trace": _listify(commander_decision.get("policy_adjustment_trace"), limit=10, max_len=200),
            "decision_summary": decision_summary,
            "commander_decision": commander_decision,
            "strategist_call_decision": _clip(commander_decision.get("strategist_call_decision") or route_observability.get("strategist_call_decision"), max_len=40),
            "strategist_call_reason": _clip(commander_decision.get("strategist_call_reason") or route_observability.get("strategist_call_reason"), max_len=180),
            "strategist_skip_reason": _clip(commander_decision.get("strategist_skip_reason") or route_observability.get("strategist_skip_reason"), max_len=180),
            "strategist_invocation_mode": _clip(commander_decision.get("strategist_invocation_mode"), max_len=40),
            "strategy_selection_mode": _clip(commander_decision.get("strategy_selection_mode"), max_len=40),
            "strategy_state": _clip(commander_decision.get("strategy_state"), max_len=40),
            "shadow_assessment_summary": shadow_assessment_summary,
            "shadow_used": bool(commander_decision.get("shadow_used") or shadow_assessment),
            "shadow_reason_code": shadow_reason_code,
            "shadow_alignment": shadow_alignment,
            "source_priority": source_priority,
            "strategist_fallback_used": strategist_fallback_used,
            "strategist_refresh_requested": strategist_refresh_requested,
            "strategist_refresh_reason": strategist_refresh_reason,
            "strategist_refresh_context": strategist_refresh_context,
            "strategist_cache_preferred": strategist_cache_preferred,
            "strategist_cache_preference_reason": strategist_cache_preference_reason,
            "strategist_cache_preference_context": strategist_cache_preference_context,
            "runtime_refresh_requested": runtime_refresh_requested,
            "runtime_refresh_reason": runtime_refresh_reason,
            "runtime_refresh_context": runtime_refresh_context,
            "post_scanner_refresh_requested": post_scanner_refresh_requested,
            "post_scanner_refresh_reason": post_scanner_refresh_reason,
            "post_scanner_refresh_context": post_scanner_refresh_context,
            "runtime_cache_reuse_reason": runtime_cache_reuse_reason,
            "runtime_cache_reuse_context": runtime_cache_reuse_context,
            "applied_policy": applied_policy,
            "commander_horizon_policy": commander_horizon_policy,
            "horizon_context": horizon_context,
            "policy_source": policy_source,
            "policy_validation_status": policy_validation_status,
            "policy_fallback_used": policy_fallback_used,
            "policy_fallback_reason": policy_fallback_reason,
            "policy_partial_normalized": policy_partial_normalized,
            "policy_default_filled_fields": policy_default_filled_fields,
            "policy_validation_missing_fields": policy_validation_missing_fields,
            "policy_validation_invalid_fields": policy_validation_invalid_fields,
            "override_triggered": override_triggered,
            "override_reason": override_reason,
            "override_action": override_action,
            "override_context": override_context,
            "applied_policy_source_chain": applied_policy_source_chain,
            "reporter_feedback_mode": reporter_feedback_mode,
            "reporter_feedback_mode_source": reporter_feedback_mode_source,
            "reporter_feedback_mode_reason": reporter_feedback_mode_reason,
            "reporter_feedback_semantics": reporter_feedback_semantics or "advisory_only",
            "commander_applied_policy_summary": commander_applied_policy_summary,
            "policy_sources": policy_sources,
            "strategist_runtime_policy_source": strategist_runtime_policy_source,
            "llm_policy_source": llm_policy_source,
            "llm_execution_profile_source": llm_execution_profile_source,
            "reporter_policy_source": reporter_policy_source,
            "monitor_policy_source": monitor_policy_source,
            "scanner_policy_source": scanner_policy_source,
            "execution_policy_source": execution_policy_source,
            "route_observability": dict(route_observability),
            "observations": observations,
            "route_selected": _clip(route_observability.get("route_selected"), max_len=80),
            "route_reason": _clip(route_observability.get("route_reason"), max_len=220),
            "policy_refresh_reason": _clip(route_observability.get("policy_refresh_reason"), max_len=180),
            "cache_hit": bool(strategist_cache_used or route_observability.get("cache_hit")),
            "cache_age_sec": _safe_int(route_observability.get("cache_age_sec") or runtime_fast_path.get("cache_age_sec")),
            "applied_policy_source": policy_source,
            "applied_policy_id": _clip(route_observability.get("applied_policy_id") or commander_decision.get("applied_policy_id"), max_len=120),
            "monitor_only_reason": _clip(route_observability.get("monitor_only_reason"), max_len=220),
            "full_cycle_reason": _clip(route_observability.get("full_cycle_reason"), max_len=220),
            "resilience_state": _dict(route_observability.get("resilience_state")),
            "intervention_reason": _clip(route_observability.get("intervention_reason"), max_len=180),
            "strategy_generation_mode": _clip(route_observability.get("strategy_generation_mode"), max_len=40),
            "goal": _clip(
                decision_frame.get("goal")
                or ("Execute full session chain." if phase == "session" else f"Run {phase} phase safely."),
                max_len=180,
            ),
            "agent_invocation_plan": list(runtime_plan.get("agents") or []),
            "decision_checkpoints": {
                "runtime_transition": _clip(state.get("runtime_transition"), max_len=60),
                "runtime_status": _clip(state.get("runtime_status"), max_len=80),
                "portfolio_preflight": preflight,
                "runtime_fast_path": runtime_fast_path,
            },
            "final_runtime_path": str(path or "").strip(),
            "final_reason": _clip(reason or state.get("runtime_status") or "", max_len=220),
            "handoff_instruction": handoff_instruction,
            "invoked_agents": list(_dict(state.get("runtime_plan")).get("agents") or []),
            "command": str(mode or "").strip(),
            "decision": str(path or "").strip(),
            "approval_result": status == "ok",
            "reason": _clip(reason or state.get("runtime_status") or "", max_len=220),
            "blocked_allowed_details": {
                "mode": str(mode or "").strip(),
                "phase": str(phase or "").strip(),
                "path": str(path or "").strip(),
                "portfolio_preflight": _dict(state.get("portfolio_preflight")),
                "runtime_transition": _clip(state.get("runtime_transition"), max_len=80),
            },
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


def _commander_shadow_has_open_order(state: Dict[str, Any]) -> Any:
    monitor = _dict(state.get("monitor"))
    order_lifecycle = _dict(monitor.get("order_lifecycle"))
    if not order_lifecycle:
        return None
    stage = _clip(order_lifecycle.get("stage"), max_len=40).lower()
    terminal = order_lifecycle.get("terminal")
    if stage:
        return stage not in {"filled", "cancelled", "canceled", "rejected"} and terminal is not True
    if terminal in (True, False):
        return not bool(terminal)
    return None


def _commander_shadow_actual_runtime(state: Dict[str, Any], *, path: str) -> Dict[str, Any]:
    shadow_runtime = _dict(state.get("commander_shadow_runtime"))
    strategist_llm = _dict(state.get("strategist_llm"))
    monitor_output = _dict(state.get("monitor_output"))
    monitor_action = _dict(state.get("monitor_action_decision"))
    execution = _dict(state.get("execution"))
    packet = _dict(state.get("decision_packet"))
    packet_intent = _dict(packet.get("intent"))
    runtime_fast_path = _dict(state.get("runtime_fast_path"))

    strategist_executed_raw = shadow_runtime.get("strategist_executed")
    strategist_executed = strategist_executed_raw if isinstance(strategist_executed_raw, bool) else None
    strategist_called_raw = shadow_runtime.get("strategist_called")
    strategist_called = strategist_called_raw if isinstance(strategist_called_raw, bool) else strategist_executed
    llm_called_raw = shadow_runtime.get("llm_called_by_strategist")
    if isinstance(llm_called_raw, bool):
        llm_called = llm_called_raw
    else:
        llm_called = None
        llm_status = _clip(strategist_llm.get("status") or strategist_llm.get("llm_status"), max_len=40).lower()
        if strategist_executed is True:
            llm_called = bool(
                llm_status not in {"", "disabled"}
                or _clip(strategist_llm.get("prompt_ref"), max_len=40)
                or _clip(strategist_llm.get("response_ref"), max_len=40)
            )
    runtime_path = _clip(path, max_len=80)
    selected_route = "cached_strategist" if "cached" in str(runtime_path or "") else ""
    used_cached_strategist = bool(shadow_runtime.get("used_cached_strategist"))
    if selected_route == "cached_strategist":
        if strategist_executed is None:
            strategist_executed = False
        if strategist_called is None:
            strategist_called = False
        if llm_called is None:
            llm_called = False
    if selected_route == "cached_strategist" and strategist_executed is False and llm_called is False:
        used_cached_strategist = True
        strategist_called = False
    elif strategist_called is None and llm_called is True:
        strategist_called = True

    monitor_decision = _clip(
        shadow_runtime.get("monitor_decision")
        or monitor_action.get("decision")
        or monitor_output.get("intent_side"),
        max_len=24,
    ).upper()
    if monitor_decision == "NOOP":
        monitor_decision = "WAIT"

    executor_action = _clip(
        shadow_runtime.get("executor_action")
        or _dict(execution.get("order")).get("action")
        or packet_intent.get("action"),
        max_len=24,
    ).upper()
    executor_status = _clip(
        shadow_runtime.get("executor_status")
        or execution.get("reason")
        or _dict(execution.get("payload")).get("broker_message")
        or execution.get("ok_source"),
        max_len=80,
    )
    post_scanner_refresh_requested = bool(shadow_runtime.get("post_scanner_refresh_requested"))
    post_scanner_refresh_reason = _clip(shadow_runtime.get("post_scanner_refresh_reason"), max_len=80)
    if not post_scanner_refresh_requested and _clip(runtime_fast_path.get("reason"), max_len=80) == "post_scanner_selected_symbol_refresh":
        post_scanner_refresh_requested = True
        post_scanner_refresh_reason = _clip(runtime_fast_path.get("strategist_refresh_reason"), max_len=80)

    return {
        "strategist_executed": strategist_executed,
        "strategist_called": strategist_called,
        "llm_called_by_strategist": llm_called,
        "used_cached_strategist": used_cached_strategist,
        "pre_buy_refresh_requested": bool(shadow_runtime.get("pre_buy_refresh_requested")),
        "pre_buy_refresh_reason": _clip(shadow_runtime.get("pre_buy_refresh_reason"), max_len=80),
        "post_scanner_refresh_requested": post_scanner_refresh_requested,
        "post_scanner_refresh_reason": post_scanner_refresh_reason,
        "monitor_decision": monitor_decision or "",
        "executor_action": executor_action or "",
        "executor_status": executor_status,
        "runtime_path": runtime_path,
    }


def _commander_shadow_observations(state: Dict[str, Any], *, path: str) -> Dict[str, Any]:
    shadow_runtime = _dict(state.get("commander_shadow_runtime"))
    strategist_llm = _dict(state.get("strategist_llm"))
    strategist_output = _dict(state.get("strategist_output"))
    selected = _dict(state.get("selected"))
    portfolio_snapshot = _dict(state.get("portfolio_snapshot"))
    positions = [row for row in list(portfolio_snapshot.get("positions") or []) if isinstance(row, dict)]
    risk_context = _dict(state.get("risk_context"))
    monitor = _dict(state.get("monitor"))
    runtime_fast_path = _dict(state.get("runtime_fast_path"))
    stress_flags = _listify(_dict(strategist_output.get("macro_stress_overlay")).get("stress_flags"), limit=6, max_len=60)
    post_scanner_refresh_requested = bool(shadow_runtime.get("post_scanner_refresh_requested"))
    post_scanner_refresh_reason = _clip(shadow_runtime.get("post_scanner_refresh_reason"), max_len=80)
    post_scanner_refresh_selected_symbol = _clip(_dict(shadow_runtime.get("post_scanner_refresh_context")).get("selected_symbol"), max_len=32)
    if not post_scanner_refresh_requested and _clip(runtime_fast_path.get("reason"), max_len=80) == "post_scanner_selected_symbol_refresh":
        post_scanner_refresh_requested = True
        post_scanner_refresh_reason = _clip(runtime_fast_path.get("strategist_refresh_reason"), max_len=80)
        post_scanner_refresh_selected_symbol = _clip(runtime_fast_path.get("selected_symbol"), max_len=32)

    score_total = selected.get("score_total")
    if score_total in (None, ""):
        score_total = selected.get("score")
    signal_strength = score_total
    if signal_strength in (None, ""):
        signal_strength = selected.get("confidence")

    retry_count_estimate = _safe_int(shadow_runtime.get("retry_count_estimate"), -1)
    if retry_count_estimate < 0:
        retry_count_estimate = max(0, _safe_int(strategist_llm.get("attempts"), 1) - 1)

    position_state = "open_position" if len(positions) > 0 else "flat"
    if "monitor_only" in str(path or ""):
        position_state = "open_position_monitor_only" if len(positions) > 0 else position_state

    return {
        "market_changed": shadow_runtime.get("market_changed"),
        "signal_strength": signal_strength,
        "risk_score": selected.get("risk_score") if selected.get("risk_score") not in (None, "") else risk_context.get("score"),
        "capital_available_for_sizing": risk_context.get("capital_available_for_sizing"),
        "cash_truth_source": _clip(risk_context.get("cash_truth_source"), max_len=80),
        "cash_truth_available": risk_context.get("cash_truth_available"),
        "broker_orderable_amount": risk_context.get("broker_orderable_amount"),
        "broker_withdrawable_cash": risk_context.get("broker_withdrawable_cash"),
        "broker_deposit": risk_context.get("broker_deposit"),
        "post_scanner_refresh_requested": post_scanner_refresh_requested,
        "post_scanner_refresh_reason": post_scanner_refresh_reason,
        "post_scanner_refresh_selected_symbol": post_scanner_refresh_selected_symbol,
        "macro_stress": float(len(stress_flags)) if stress_flags else (1.0 if bool(_dict(strategist_output.get("macro_stress_overlay")).get("active")) else 0.0),
        "last_llm_status": _clip(strategist_llm.get("status") or strategist_output.get("llm_frame_status"), max_len=40),
        "retry_count_estimate": int(max(0, retry_count_estimate)),
        "position_state": position_state,
        "has_open_order": _commander_shadow_has_open_order(state),
        "runtime_fast_path_reason": _clip(runtime_fast_path.get("reason"), max_len=80),
        "repeated_same_context": shadow_runtime.get("repeated_same_context"),
    }


def _gate_pass(metrics: Dict[str, Any], passed_checks: List[str], failed_checks: List[str], key: str) -> Any:
    if key in metrics:
        value = metrics.get(key)
        if isinstance(value, bool):
            return value
    if key in passed_checks:
        return True
    if key in failed_checks:
        return False
    return None


def _score_from_checks(*, passed_checks: List[str], failed_checks: List[str], fallback: Any) -> Any:
    try:
        if fallback not in (None, ""):
            return round(float(fallback), 4)
    except Exception:
        pass
    total = len(passed_checks) + len(failed_checks)
    if total <= 0:
        return None
    return round(float(len(passed_checks)) / float(total), 4)


def _commander_shadow_monitor_gate_details(state: Dict[str, Any]) -> Dict[str, Any]:
    monitor_entry = _dict(state.get("monitor_entry"))
    monitor_output = _dict(state.get("monitor_output"))
    metrics = _dict(monitor_entry.get("metrics"))
    thresholds = _dict(monitor_entry.get("thresholds"))
    passed_checks = [str(x or "").strip() for x in list(monitor_entry.get("passed_checks") or []) if str(x or "").strip()]
    failed_checks = [str(x or "").strip() for x in list(monitor_entry.get("failed_checks") or []) if str(x or "").strip()]
    pullback_flags = [key for key in ("pullback_ok", "pullback_mature", "pullback_not_too_deep") if key in metrics]
    pullback_values = [bool(metrics.get(key)) for key in pullback_flags if isinstance(metrics.get(key), bool)]

    pullback_passed: Any = None
    if pullback_values:
        pullback_passed = all(pullback_values)
    elif "pullback_ok" in passed_checks:
        pullback_passed = True
    elif "pullback_ok" in failed_checks:
        pullback_passed = False

    entry_block_reason = _clip(
        monitor_entry.get("guard_reason")
        or monitor_entry.get("reason")
        or monitor_output.get("entry_exit_reason"),
        max_len=180,
    )
    observed_features = {
        "price": metrics.get("price") if metrics.get("price") not in (None, "") else metrics.get("current_price"),
        "current_price": metrics.get("current_price"),
        "minute_source_present": metrics.get("minute_source_present"),
        "minute_source_used": metrics.get("minute_source_used"),
        "latest_candle_ts": metrics.get("latest_candle_ts"),
        "minute_snapshot_age_minutes": metrics.get("minute_snapshot_age_minutes"),
        "minute_snapshot_was_stale": metrics.get("minute_snapshot_was_stale"),
        "minute_refetch_attempted": metrics.get("minute_refetch_attempted"),
        "minute_refetch_succeeded": metrics.get("minute_refetch_succeeded"),
        "minute_refetch_reason": metrics.get("minute_refetch_reason"),
        "minute_refetch_trigger_reason": metrics.get("minute_refetch_trigger_reason"),
        "minute_refetch_failure_reason": metrics.get("minute_refetch_failure_reason"),
        "minute_refetch_produced_fresh_snapshot": metrics.get("minute_refetch_produced_fresh_snapshot"),
        "volume_ratio": metrics.get("volume_ratio"),
        "vwap_distance": metrics.get("vwap_distance") if metrics.get("vwap_distance") not in (None, "") else metrics.get("extended_from_vwap_pct"),
        "extended_from_vwap_pct": metrics.get("extended_from_vwap_pct"),
        "pullback_depth_pct": metrics.get("pullback_depth_pct") if metrics.get("pullback_depth_pct") not in (None, "") else metrics.get("pullback_pct"),
        "pullback_pct": metrics.get("pullback_pct"),
        "recent_high": metrics.get("recent_high"),
        "breakout_level": metrics.get("breakout_level"),
        "bar_count": metrics.get("bar_count"),
        "timeframe_minutes": metrics.get("timeframe_minutes"),
        "inferred_spacing_minutes": metrics.get("inferred_spacing_minutes"),
        "series_class": metrics.get("series_class"),
    }
    return {
        "breakout_passed": _gate_pass(metrics, passed_checks, failed_checks, "breakout_ok"),
        "volume_passed": _gate_pass(metrics, passed_checks, failed_checks, "volume_ok"),
        "vwap_extension_passed": _gate_pass(metrics, passed_checks, failed_checks, "extension_ok"),
        "pullback_passed": pullback_passed,
        "entry_score": _score_from_checks(
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            fallback=monitor_entry.get("confidence"),
        ),
        "entry_block_reason": entry_block_reason or "",
        "used_thresholds": thresholds,
        "observed_features": {k: v for k, v in observed_features.items() if v not in (None, "")},
        "passed_gates": passed_checks[:8],
        "failed_gates": failed_checks[:8],
        "primary_failure_axis": _clip(monitor_entry.get("primary_failure_axis"), max_len=80),
    }


def _commander_shadow_context_delta_summary(state: Dict[str, Any], *, observations: Dict[str, Any]) -> Dict[str, Any]:
    shadow_runtime = _dict(state.get("commander_shadow_runtime"))
    prior = _dict(shadow_runtime.get("prior_context"))
    strategist_output = _dict(state.get("strategist_output"))
    selected = _dict(state.get("selected"))
    monitor_output = _dict(state.get("monitor_output"))
    global_signal = _dict(state.get("global_signal"))
    fear_index = _dict(global_signal.get("fear_index"))
    overlay = _dict(strategist_output.get("macro_stress_overlay"))

    current_symbol = _clip(selected.get("symbol") or monitor_output.get("selected_symbol"), max_len=24)
    last_symbol = _clip(prior.get("selected_symbol"), max_len=24)
    current_score = selected.get("score_total")
    if current_score in (None, ""):
        current_score = selected.get("score")
    if current_score in (None, ""):
        current_score = selected.get("confidence")
    last_score = prior.get("selected_score_total")

    current_playbook = _clip(strategist_output.get("playbook"), max_len=40)
    last_playbook = _clip(prior.get("playbook"), max_len=40)
    current_regime = _clip(strategist_output.get("market_regime"), max_len=40)
    last_regime = _clip(prior.get("market_regime"), max_len=40)
    current_sentiment = _clip(strategist_output.get("market_sentiment"), max_len=40)
    last_sentiment = _clip(prior.get("market_sentiment"), max_len=40)
    current_sentiment_score = strategist_output.get("global_sentiment_score")
    last_sentiment_score = prior.get("global_sentiment_score")
    current_vix = fear_index.get("level") if fear_index.get("level") not in (None, "") else overlay.get("vix_level")
    last_vix = prior.get("vix_level")
    current_stress_flags = [str(x or "").strip() for x in list(overlay.get("stress_flags") or []) if str(x or "").strip()]
    last_stress_flags = [str(x or "").strip() for x in list(prior.get("stress_flags") or []) if str(x or "").strip()]

    symbol_same_as_last = None if not current_symbol or not last_symbol else (current_symbol == last_symbol)
    playbook_same_as_last = None if not current_playbook or not last_playbook else (current_playbook == last_playbook)
    market_regime_changed = None if not current_regime or not last_regime else (current_regime != last_regime)

    sentiment_changed: Any = None
    if current_sentiment and last_sentiment:
        sentiment_changed = current_sentiment != last_sentiment
    try:
        if current_sentiment_score not in (None, "") and last_sentiment_score not in (None, ""):
            sentiment_changed = abs(float(current_sentiment_score) - float(last_sentiment_score)) >= 0.03
    except Exception:
        pass

    volatility_changed: Any = None
    try:
        if current_vix not in (None, "") and last_vix not in (None, ""):
            volatility_changed = abs(float(current_vix) - float(last_vix)) >= 1.0
    except Exception:
        pass
    if volatility_changed is None and current_stress_flags and last_stress_flags:
        volatility_changed = sorted(current_stress_flags) != sorted(last_stress_flags)

    signal_changed: Any = None
    try:
        if current_score not in (None, "") and last_score not in (None, ""):
            signal_changed = abs(float(current_score) - float(last_score)) >= 0.05
    except Exception:
        signal_changed = None
    if signal_changed is None and symbol_same_as_last is not None:
        signal_changed = not symbol_same_as_last

    return {
        "symbol_same_as_last": symbol_same_as_last,
        "playbook_same_as_last": playbook_same_as_last,
        "market_regime_changed": market_regime_changed,
        "sentiment_changed": sentiment_changed,
        "volatility_changed": volatility_changed,
        "signal_changed": signal_changed,
        "last_llm_status": _clip(prior.get("llm_status") or observations.get("last_llm_status"), max_len=40),
        "repeated_same_context": observations.get("repeated_same_context"),
        "market_changed": observations.get("market_changed"),
    }


def _commander_shadow_no_trade_reason_code(
    state: Dict[str, Any],
    *,
    observations: Dict[str, Any],
    actual_runtime: Dict[str, Any],
    path: str,
) -> str:
    monitor = _dict(state.get("monitor"))
    monitor_entry = _dict(state.get("monitor_entry"))
    monitor_output = _dict(state.get("monitor_output"))
    execution = _dict(state.get("execution"))
    portfolio_preflight = _dict(state.get("portfolio_preflight"))
    runtime_fast_path = _dict(state.get("runtime_fast_path"))
    strategist_llm = _dict(state.get("strategist_llm"))
    selected = _dict(state.get("selected"))
    symbol = _clip(selected.get("symbol") or monitor_output.get("selected_symbol"), max_len=24)

    monitor_decision = _clip(actual_runtime.get("monitor_decision"), max_len=24).upper()
    executor_action = _clip(actual_runtime.get("executor_action"), max_len=24).upper()
    if monitor_decision in {"BUY", "SELL"} or executor_action in {"BUY", "SELL"}:
        return "NONE"

    if _safe_int(monitor.get("open_position_count"), 0) > 0 and (
        bool(monitor.get("buy_blocked_open_position"))
        or "monitor_only" in str(path or "")
    ):
        return "POSITION_ALREADY_OPEN"

    if bool(portfolio_preflight.get("blocked")) or _clip(state.get("decision_reason"), max_len=80) in {"risk_too_high", "portfolio_preflight_blocked"}:
        return "RISK_BLOCKED"

    if execution and execution.get("allowed") is False:
        reason = _clip(execution.get("reason"), max_len=120).lower()
        if reason not in {"", "noop_intent_skipped"}:
            return "EXECUTION_BLOCKED"

    failed_checks = [str(x or "").strip().lower() for x in list(monitor_entry.get("failed_checks") or []) if str(x or "").strip()]
    combined_reason = " ".join(
        [
            _clip(monitor_entry.get("guard_reason"), max_len=120),
            _clip(monitor_entry.get("reason"), max_len=120),
            _clip(monitor_output.get("entry_exit_reason"), max_len=120),
        ]
    ).strip().lower()
    if any(token in combined_reason for token in ("minute_candle_missing", "data_incomplete", "insufficient_data", "missing_data")):
        return "DATA_INSUFFICIENT"
    if any(token in failed_checks for token in ("data_incomplete", "minute_candle_missing", "vwap_missing", "volume_missing")):
        return "DATA_INSUFFICIENT"
    if not symbol and not combined_reason and not failed_checks and not execution and not strategist_llm:
        return "DATA_INSUFFICIENT"

    llm_status = _clip(strategist_llm.get("status") or strategist_llm.get("llm_status"), max_len=40).lower()
    if bool(strategist_llm.get("blocked")) or llm_status in {"error", "fallback"}:
        return "LLM_UNSTABLE"

    if observations.get("repeated_same_context") is True:
        return "REPEATED_SAME_CONTEXT"
    if observations.get("market_changed") is False or _clip(runtime_fast_path.get("reason"), max_len=80) == "flat_position_cached_strategist":
        return "NO_MARKET_CHANGE"

    confidence = selected.get("confidence")
    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = None
    if confidence_value is not None and confidence_value < 0.55:
        return "LOW_CONFIDENCE"

    if failed_checks or any(token in combined_reason for token in ("confirmation", "too_extended", "breakout", "pullback", "reclaim", "entry_wait", "wait")):
        return "WAIT_FOR_CONFIRMATION"

    if combined_reason:
        return "LOW_SIGNAL_QUALITY"
    return "NONE"


def _commander_shadow_strategist_recommendation(
    *,
    no_trade_reason_code: str,
    observations: Dict[str, Any],
) -> str:
    llm_status = str(observations.get("last_llm_status") or "").strip().lower()
    if no_trade_reason_code in {
        "POSITION_ALREADY_OPEN",
        "NO_MARKET_CHANGE",
        "REPEATED_SAME_CONTEXT",
        "DATA_INSUFFICIENT",
        "WAIT_FOR_CONFIRMATION",
        "LOW_SIGNAL_QUALITY",
        "LOW_CONFIDENCE",
        "RISK_BLOCKED",
        "EXECUTION_BLOCKED",
    }:
        return "SKIP"
    if no_trade_reason_code == "LLM_UNSTABLE":
        if llm_status in {"partial", "salvaged", "repaired"}:
            return "RETRY_COMPACT"
        if llm_status == "fallback":
            return "USE_FALLBACK"
        if llm_status == "error":
            return "RETRY_MINIMAL"
    return "RUN"


def _commander_shadow_llm_call_advice(
    *,
    strategist_action_recommendation: str,
    observations: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    strategist_llm = _dict(state.get("strategist_llm"))
    llm_status = str(observations.get("last_llm_status") or strategist_llm.get("status") or "").strip().lower()
    if strategist_action_recommendation == "SKIP" and observations.get("market_changed") is False:
        return "SKIP"
    if strategist_action_recommendation == "SKIP" and observations.get("repeated_same_context") is True:
        return "SKIP"
    if bool(strategist_llm.get("blocked")) or llm_status in {"error", "fallback"}:
        return "RETRY_MINIMAL"
    if llm_status in {"partial", "salvaged", "repaired"}:
        return "RETRY_COMPACT"
    if strategist_action_recommendation == "SKIP":
        return "SKIP"
    return "ALLOW"


def _commander_shadow_suggested_action(
    *,
    strategist_action_recommendation: str,
    llm_call_advice: str,
    no_trade_reason_code: str,
) -> str:
    if strategist_action_recommendation == "SKIP" and no_trade_reason_code == "POSITION_ALREADY_OPEN":
        return "monitor_only_observe"
    if strategist_action_recommendation == "SKIP" and no_trade_reason_code in {"NO_MARKET_CHANGE", "REPEATED_SAME_CONTEXT"}:
        return "skip_strategist_reuse_context"
    if llm_call_advice == "RETRY_COMPACT":
        return "compact_strategist_retry"
    if llm_call_advice == "RETRY_MINIMAL":
        return "minimal_strategist_retry"
    return "allow_current_flow"


def _commander_shadow_next_action_recommendation(
    *,
    strategist_action_recommendation: str,
    llm_call_advice: str,
    no_trade_reason_code: str,
    actual_runtime: Dict[str, Any],
) -> str:
    if no_trade_reason_code == "POSITION_ALREADY_OPEN":
        return "HOLD_OBSERVE"
    if strategist_action_recommendation in {"RETRY_COMPACT", "RETRY_MINIMAL", "USE_FALLBACK"} or llm_call_advice in {
        "RETRY_COMPACT",
        "RETRY_MINIMAL",
    }:
        return "RETRY_COMPACT_NEXT"
    if no_trade_reason_code in {"WAIT_FOR_CONFIRMATION", "LOW_SIGNAL_QUALITY", "LOW_CONFIDENCE", "DATA_INSUFFICIENT"}:
        return "WAIT_NEXT_BAR"
    monitor_decision = _clip(actual_runtime.get("monitor_decision"), max_len=24).upper()
    if monitor_decision in {"BUY", "SELL", "HOLD"}:
        return "HOLD_OBSERVE"
    return "NO_ACTION"


def _commander_shadow_reason_summary(
    *,
    no_trade_reason_code: str,
    observations: Dict[str, Any],
    actual_runtime: Dict[str, Any],
) -> str:
    llm_status = _clip(observations.get("last_llm_status"), max_len=40) or "unknown"
    monitor_decision = _clip(actual_runtime.get("monitor_decision"), max_len=24) or "WAIT"
    executor_action = _clip(actual_runtime.get("executor_action"), max_len=24) or "NONE"
    mapping = {
        "NONE": f"Observed runtime ended with monitor={monitor_decision} and executor={executor_action} without a stronger commander block signal.",
        "POSITION_ALREADY_OPEN": "Open position state already existed, so monitor-only observation was more appropriate than a fresh strategist cycle.",
        "RISK_BLOCKED": "Risk or portfolio guard signals were stronger than any need to refresh strategist context in this cycle.",
        "EXECUTION_BLOCKED": "Execution or approval constraints were the main reason to stand down, independent of strategist quality.",
        "DATA_INSUFFICIENT": "Available minute, feature, or symbol data was too thin to justify a fresh strategist-driven trade attempt.",
        "NO_MARKET_CHANGE": "The cycle looked materially similar to the prior context, so a new strategist run likely added little value.",
        "LLM_UNSTABLE": f"Recent strategist LLM status was {llm_status}, so a compact or minimal retry would have been safer than a full refresh.",
        "LOW_CONFIDENCE": "Signal confidence was weak enough that waiting for stronger confirmation looked safer than acting now.",
        "LOW_SIGNAL_QUALITY": "Monitor signal quality was too weak to justify a trade, even if strategist context was available.",
        "REPEATED_SAME_CONTEXT": "The cycle repeated nearly the same strategist context, suggesting reuse or skip would have been reasonable.",
        "WAIT_FOR_CONFIRMATION": "Monitor gates were not fully aligned yet, so waiting for another bar or clearer confirmation looked appropriate.",
    }
    return mapping.get(no_trade_reason_code, "Shadow commander observed the cycle, but the evidence was limited and should be treated as advisory only.")


def _commander_shadow_recommendation_gap(
    *,
    strategist_action_recommendation: str,
    llm_call_advice: str,
    actual_runtime: Dict[str, Any],
) -> str:
    strategist_executed = actual_runtime.get("strategist_executed")
    llm_called = actual_runtime.get("llm_called_by_strategist")
    if strategist_action_recommendation == "SKIP" and strategist_executed is True:
        return "strategist_ran_despite_skip_recommendation"
    if strategist_action_recommendation in {"RUN", "RETRY_COMPACT", "RETRY_MINIMAL", "USE_FALLBACK"} and strategist_executed is False:
        return "strategist_not_run_despite_refresh_recommendation"
    if llm_call_advice == "SKIP" and llm_called is True:
        return "llm_called_despite_skip_advice"
    if llm_call_advice in {"ALLOW", "RETRY_COMPACT", "RETRY_MINIMAL"} and llm_called is False and strategist_executed is True:
        return "llm_not_called_despite_refresh_advice"
    return "aligned"


def _commander_shadow_pre_strategist_snapshot(
    *,
    state: Dict[str, Any],
    observations: Dict[str, Any],
    context_delta_summary: Dict[str, Any],
    strategist_action_recommendation: str,
    llm_call_advice: str,
) -> Dict[str, Any]:
    prior = _dict(_dict(state.get("commander_shadow_runtime")).get("prior_context"))
    return {
        "market_changed": observations.get("market_changed"),
        "repeated_same_context": observations.get("repeated_same_context"),
        "last_llm_status": observations.get("last_llm_status"),
        "prior_symbol": _clip(prior.get("selected_symbol"), max_len=24),
        "prior_playbook": _clip(prior.get("playbook"), max_len=40),
        "strategist_action_recommendation": strategist_action_recommendation,
        "llm_call_advice": llm_call_advice,
        "reason": _clip(
            f"context_delta={context_delta_summary.get('signal_changed')} market_changed={observations.get('market_changed')} repeated={observations.get('repeated_same_context')}",
            max_len=180,
        ),
    }


def _commander_shadow_post_strategist_assessment(
    *,
    state: Dict[str, Any],
    actual_runtime: Dict[str, Any],
    context_delta_summary: Dict[str, Any],
    recommendation_gap: str,
) -> Dict[str, Any]:
    strategist_output = _dict(state.get("strategist_output"))
    strategist_llm = _dict(state.get("strategist_llm"))
    return {
        "strategist_executed": actual_runtime.get("strategist_executed"),
        "llm_called_by_strategist": actual_runtime.get("llm_called_by_strategist"),
        "used_cached_strategist": actual_runtime.get("used_cached_strategist"),
        "llm_status": _clip(strategist_llm.get("status") or strategist_output.get("llm_frame_status"), max_len=40),
        "playbook": _clip(strategist_output.get("playbook"), max_len=40),
        "market_regime": _clip(strategist_output.get("market_regime"), max_len=40),
        "market_sentiment": _clip(strategist_output.get("market_sentiment"), max_len=40),
        "recommendation_gap": recommendation_gap,
        "context_delta_summary": context_delta_summary,
    }


def _commander_shadow_post_monitor_assessment(
    *,
    actual_runtime: Dict[str, Any],
    monitor_gate_details: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "monitor_decision": _clip(actual_runtime.get("monitor_decision"), max_len=24),
        "entry_block_reason": _clip(monitor_gate_details.get("entry_block_reason"), max_len=180),
        "failed_gates": list(monitor_gate_details.get("failed_gates") or [])[:8],
        "passed_gates": list(monitor_gate_details.get("passed_gates") or [])[:8],
        "primary_failure_axis": _clip(monitor_gate_details.get("primary_failure_axis"), max_len=80),
        "monitor_gate_details": monitor_gate_details,
    }


def _commander_shadow_end_of_cycle_summary(
    *,
    no_trade_reason_code: str,
    reason_summary: str,
    actual_runtime: Dict[str, Any],
    next_action_recommendation: str,
    recommendation_gap: str,
) -> Dict[str, Any]:
    return {
        "no_trade_reason_code": no_trade_reason_code,
        "reason_summary": reason_summary,
        "actual_runtime": actual_runtime,
        "next_action_recommendation": next_action_recommendation,
        "recommendation_gap": recommendation_gap,
    }


def build_commander_shadow_artifact(
    state: Dict[str, Any],
    *,
    mode: str,
    phase: str,
    path: str,
    status: str,
    reason: str = "",
) -> Dict[str, Any]:
    observations = _commander_shadow_observations(state, path=path)
    actual_runtime = _commander_shadow_actual_runtime(state, path=path)
    monitor_gate_details = _commander_shadow_monitor_gate_details(state)
    context_delta_summary = _commander_shadow_context_delta_summary(state, observations=observations)
    no_trade_reason_code = _commander_shadow_no_trade_reason_code(
        state,
        observations=observations,
        actual_runtime=actual_runtime,
        path=path,
    )
    strategist_action_recommendation = _commander_shadow_strategist_recommendation(
        no_trade_reason_code=no_trade_reason_code,
        observations=observations,
    )
    llm_call_advice = _commander_shadow_llm_call_advice(
        strategist_action_recommendation=strategist_action_recommendation,
        observations=observations,
        state=state,
    )
    suggested_action = _commander_shadow_suggested_action(
        strategist_action_recommendation=strategist_action_recommendation,
        llm_call_advice=llm_call_advice,
        no_trade_reason_code=no_trade_reason_code,
    )
    next_action_recommendation = _commander_shadow_next_action_recommendation(
        strategist_action_recommendation=strategist_action_recommendation,
        llm_call_advice=llm_call_advice,
        no_trade_reason_code=no_trade_reason_code,
        actual_runtime=actual_runtime,
    )
    reason_summary = _commander_shadow_reason_summary(
        no_trade_reason_code=no_trade_reason_code,
        observations=observations,
        actual_runtime=actual_runtime,
    )
    recommendation_gap = _commander_shadow_recommendation_gap(
        strategist_action_recommendation=strategist_action_recommendation,
        llm_call_advice=llm_call_advice,
        actual_runtime=actual_runtime,
    )
    pre_strategist_shadow_snapshot = _commander_shadow_pre_strategist_snapshot(
        state=state,
        observations=observations,
        context_delta_summary=context_delta_summary,
        strategist_action_recommendation=strategist_action_recommendation,
        llm_call_advice=llm_call_advice,
    )
    post_strategist_assessment = _commander_shadow_post_strategist_assessment(
        state=state,
        actual_runtime=actual_runtime,
        context_delta_summary=context_delta_summary,
        recommendation_gap=recommendation_gap,
    )
    post_monitor_assessment = _commander_shadow_post_monitor_assessment(
        actual_runtime=actual_runtime,
        monitor_gate_details=monitor_gate_details,
    )
    end_of_cycle_summary = _commander_shadow_end_of_cycle_summary(
        no_trade_reason_code=no_trade_reason_code,
        reason_summary=reason_summary,
        actual_runtime=actual_runtime,
        next_action_recommendation=next_action_recommendation,
        recommendation_gap=recommendation_gap,
    )
    symbol = _clip(
        _dict(state.get("selected")).get("symbol")
        or _dict(state.get("monitor_output")).get("selected_symbol")
        or _dict(state.get("monitor_exit")).get("symbol"),
        max_len=24,
    )
    artifact = _base_output(state, agent="commander", symbol=symbol, status=status or "ok")
    artifact.update(
        {
            "schema_version": "commander_shadow.v1",
            "mode": "shadow",
            "cycle_id": _clip(state.get("cycle_id"), max_len=80),
            "observed_runtime_mode": _clip(mode, max_len=40),
            "observed_runtime_path": _clip(path, max_len=80),
            "decision": "OBSERVE_ONLY",
            "strategist_action_recommendation": strategist_action_recommendation,
            "llm_call_advice": llm_call_advice,
            "suggested_action": suggested_action,
            "next_action_recommendation": next_action_recommendation,
            "no_trade_reason_code": no_trade_reason_code,
            "reason_summary": reason_summary,
            "observations": observations,
            "actual_runtime": actual_runtime,
            "monitor_gate_details": monitor_gate_details,
            "context_delta_summary": context_delta_summary,
            "pre_strategist_shadow_snapshot": pre_strategist_shadow_snapshot,
            "post_strategist_assessment": post_strategist_assessment,
            "post_monitor_assessment": post_monitor_assessment,
            "end_of_cycle_summary": end_of_cycle_summary,
            "comparison_summary": (
                f"recommended={strategist_action_recommendation}/{llm_call_advice}, "
                f"next={next_action_recommendation}, "
                f"observed_monitor={actual_runtime.get('monitor_decision') or 'WAIT'}, "
                f"observed_executor={actual_runtime.get('executor_action') or 'NONE'}, "
                f"gap={recommendation_gap}"
            ),
            "integrated_into_commander_decision": True,
            "integration_version": "phase1_2",
            "integration_role": "upstream_assessment",
            "reason": _clip(reason or state.get("runtime_status") or "", max_len=220),
            "shadow_only": True,
            "generated_at": _utc_now_iso(),
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact
