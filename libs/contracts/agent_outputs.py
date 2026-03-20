from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, TypedDict


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


def _run_day(state: Dict[str, Any]) -> str:
    for key in ("started_at", "ts", "tick_ts_iso", "now_iso"):
        value = str(state.get(key) or "").strip()
        if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            return value[:10]
    tick_epoch = _safe_int(state.get("tick_ts"), 0)
    if tick_epoch > 0:
        return datetime.fromtimestamp(tick_epoch, tz=timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
            "evaluation_summary",
            "decision",
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


def validate_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    obj = dict(artifact or {}) if isinstance(artifact, dict) else {}
    agent = str(obj.get("agent") or "").strip().lower()
    expected = _required_keys_for_agent(agent)
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
            "strategy_thesis": _clip(
                strategist_output.get("news_query_reasoning")
                or strategist_output.get("monitor_guidance")
                or summary,
                max_len=500,
            ),
            "playbook": playbook,
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
                "market_news_context": market_news_context,
                "candidate_news_context": candidate_news_context,
                "key_events": list(strategist_output.get("key_events") or [])[:10],
            },
            "strategy_frame": {
                "market_regime": market_regime,
                "market_sentiment": market_sentiment,
                "themes": themes,
                "avoid_themes": avoid_themes,
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
            "themes": themes,
            "avoid_themes": avoid_themes,
            "llm_metadata_summary": {
                "status": _clip(strategist_llm.get("status"), max_len=40),
                "model": _clip(strategist_llm.get("model"), max_len=120),
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
    top_ranked_symbols = [str(row.get("symbol") or "") for row in ranked[:5] if str(row.get("symbol") or "").strip()]
    pool_meta = _dict(state.get("scanner_candidate_pool"))
    candidate_preview: List[Dict[str, Any]] = []
    for rank, row in enumerate(ranked[:5], start=1):
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
    artifact = _base_output(state, agent="scanner", symbol=symbol)
    artifact.update(
        {
            "candidate_pool_snapshot": {
                "candidate_source": _clip(pool_meta.get("candidate_source"), max_len=80),
                "candidate_pool_before_filter": _safe_int(pool_meta.get("candidate_pool_before_filter")),
                "candidate_pool_after_filter": _safe_int(pool_meta.get("candidate_pool_after_filter") or len(ranked)),
                "source_mix": _dict(pool_meta.get("pool_source_mix")),
                "fallback_reason": _clip(pool_meta.get("fallback_reason"), max_len=160),
            },
            "filter_funnel": {
                "before": _safe_int(pool_meta.get("candidate_pool_before_filter")),
                "after": _safe_int(pool_meta.get("candidate_pool_after_filter") or len(ranked)),
                "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
                "avoid_filter_applied": bool(pool_meta.get("avoid_filter_applied")),
                "blocked_static_fallback": bool(pool_meta.get("blocked_static_fallback")),
                "strict_kiwoom_only": bool(pool_meta.get("strict_kiwoom_only")),
            },
            "universe_size": _safe_int(scanner_output.get("candidate_pool_size") or scanner_output.get("candidate_count")),
            "candidate_list_summary": {
                "candidate_source": _clip(scanner_output.get("candidate_source"), max_len=80),
                "source_mix": _dict(scanner_output.get("source_mix")),
                "candidate_count": _safe_int(scanner_output.get("candidate_count")),
            },
            "ranking_table": candidate_preview,
            "ranked_candidates": candidate_preview,
            "selected_symbol": symbol,
            "selected_rank": selected_rank,
            "selection_reason": selection_summary,
            "selection_reason_detail": selection_reason_detail,
            "rejection_summary": rejection_rows,
            "filter_feature_summary": {
                "feature_source": _clip(state.get("scanner_feature", {}).get("source") if isinstance(state.get("scanner_feature"), dict) else "", max_len=80),
                "feature_symbol_count": _safe_int(_dict(state.get("scanner_feature")).get("symbol_count")),
                "condition_search_status": _clip(scanner_output.get("condition_search_status"), max_len=80),
                "condition_search_reason": _clip(scanner_output.get("condition_search_reason"), max_len=160),
            },
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
    exit_info = _dict(state.get("monitor_exit"))
    entry_info = _dict(state.get("monitor_entry"))
    transition = _dict(state.get("monitor_state_transition"))
    symbol = str(exit_info.get("symbol") or monitor_output.get("selected_symbol") or monitor.get("selected_symbol") or "").strip()
    thresholds = _dict(exit_info.get("thresholds"))
    watch_axes = list(exit_info.get("watch_axes") or [])
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
    artifact = _base_output(state, agent="monitor", symbol=symbol)
    artifact.update(
        {
            "position_snapshot": {
                "open_position_count": _safe_int(monitor.get("open_position_count")),
                "symbol": symbol,
                "qty": _safe_int(exit_info.get("qty")),
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
            "decision_reason_chain": decision_reason_chain,
            "monitor_evaluation": {
                "triggered_rules": triggered_rules,
                "blocked_rules": blocked_rules[:8],
                "posture": posture,
                "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
                "entry_pattern": _clip(entry_info.get("pattern"), max_len=80),
                "entry_passed_checks": list(entry_info.get("passed_checks") or []),
                "entry_failed_checks": list(entry_info.get("failed_checks") or []),
                "entry_threshold_margins": _dict(entry_info.get("threshold_margins")),
            },
            "monitor_action_decision": {
                "decision": str(monitor_output.get("intent_side") or "NOOP").strip().upper(),
                "action_reason_human": _clip(monitor_output.get("entry_exit_reason") or exit_info.get("monitor_reason") or exit_info.get("reason"), max_len=240),
                "decision_reason_chain": decision_reason_chain,
                "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
                "confidence": _safe_float(entry_info.get("confidence"), 0.0),
                "triggered_rules": triggered_rules,
                "blocked_rules": blocked_rules[:8],
            },
            "trigger_details": {
                "active_exit_axis": _clip(exit_info.get("active_exit_axis"), max_len=120),
                "watch_axes": watch_axes[:8],
                "exit_triggered": bool(exit_info.get("triggered")),
                "sell_guard_blocked": bool(exit_info.get("sell_guard_blocked")),
                "sell_guard_reason": _clip(exit_info.get("sell_guard_reason"), max_len=180),
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
            "average_price": exit_info.get("avg_price"),
            "avg_price": exit_info.get("avg_price"),
            "peak_price": exit_info.get("peak_price"),
            "current_drawdown": exit_info.get("current_drawdown"),
            "peak_drawdown": exit_info.get("peak_drawdown"),
            "vwap_distance": exit_info.get("vwap_distance"),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "price_source": _clip(exit_info.get("price_source"), max_len=120),
            "price_source_policy": _clip(exit_info.get("price_source_policy"), max_len=260),
            "feature_source": _clip(exit_info.get("feature_source"), max_len=120),
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
    symbol = str(execution.get("symbol") or order.get("symbol") or "").strip()
    artifact = _base_output(
        state,
        agent="executor",
        symbol=symbol,
        status="ok" if bool(execution.get("allowed")) and bool(execution.get("execution_ok", True)) else "error",
    )
    artifact.update(
        {
            "action": str(execution.get("action") or order.get("action") or "").strip().upper(),
            "allowed": bool(execution.get("allowed")),
            "symbol": symbol,
            "qty": _safe_int(order.get("qty") or execution.get("qty")),
            "status": _clip(execution.get("status"), max_len=80),
            "reason": _clip(execution.get("reason"), max_len=220),
            "broker_env": _clip(execution.get("broker_env"), max_len=32),
            "effective_mode": _clip(execution.get("effective_mode"), max_len=64),
            "broker_message": _clip(execution.get("broker_message"), max_len=200),
            "ord_no": _clip(execution.get("ord_no"), max_len=64),
            "execution_ok": bool(execution.get("execution_ok", execution.get("allowed"))),
            "order_request_summary": {
                "action": str(order.get("action") or execution.get("action") or "").strip().upper(),
                "symbol": symbol,
                "qty": _safe_int(order.get("qty") or execution.get("qty")),
                "order_type": _clip(order.get("order_type"), max_len=32),
            },
            "execution_enabled": bool(execution.get("allowed")),
            "approval_mode": _clip(execution.get("approval_mode"), max_len=32),
            "broker_result": {
                "status": _clip(execution.get("status"), max_len=80),
                "broker_message": _clip(execution.get("broker_message"), max_len=200),
                "ord_no": _clip(execution.get("ord_no"), max_len=64),
                "effective_mode": _clip(execution.get("effective_mode"), max_len=64),
                "broker_env": _clip(execution.get("broker_env"), max_len=32),
            },
            "final_execution_status": _clip(execution.get("status"), max_len=80) or ("allowed" if execution.get("allowed") else "blocked"),
            "failure_reason": _clip(execution.get("reason"), max_len=220),
            "strategy_policy_summary": _dict(execution.get("strategy_policy_summary")),
        }
    )
    artifact["validation"] = validate_artifact(artifact)
    return artifact


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
    runtime_plan = _dict(state.get("runtime_plan"))
    strategist_output = _dict(state.get("strategist_output"))
    portfolio_snapshot = _dict(state.get("portfolio_snapshot"))
    positions = list(portfolio_snapshot.get("positions") or [])
    status_text = str(status or "ok")
    handoff_instruction = _clip(
        decision_frame.get("handoff_instruction")
        or ("Proceed with planned agent chain." if status_text in {"ok", "ready", "preopen_ready", "closeout_ready"} else "Stop downstream execution and inspect runtime status."),
        max_len=220,
    )
    artifact = _base_output(state, agent="commander", status=status or "ok")
    artifact.update(
        {
            "mode": str(mode or "").strip(),
            "phase": str(phase or "").strip(),
            "path": str(path or "").strip(),
            "session_type": _clip(decision_frame.get("session_type") or runtime_plan.get("phase") or phase, max_len=40),
            "market_clock_phase": _clip(decision_frame.get("market_clock_phase") or phase or runtime_plan.get("phase"), max_len=40),
            "portfolio_state_summary": {
                "position_count": _safe_int(len(positions)),
                "cash": portfolio_snapshot.get("cash"),
                "positions_source": _clip(_dict(state.get("portfolio_preflight")).get("positions_source"), max_len=80),
                "preflight_status": _clip(_dict(state.get("portfolio_preflight")).get("status"), max_len=80),
            },
            "market_regime_summary": {
                "market_regime": _clip(strategist_output.get("market_regime"), max_len=80),
                "market_sentiment": _clip(strategist_output.get("market_sentiment"), max_len=80),
                "playbook": _clip(strategist_output.get("playbook"), max_len=80),
            },
            "goal": _clip(
                decision_frame.get("goal")
                or ("Execute full session chain." if phase == "session" else f"Run {phase} phase safely."),
                max_len=180,
            ),
            "agent_invocation_plan": list(runtime_plan.get("agents") or []),
            "decision_checkpoints": {
                "runtime_transition": _clip(state.get("runtime_transition"), max_len=60),
                "runtime_status": _clip(state.get("runtime_status"), max_len=80),
                "portfolio_preflight": _dict(state.get("portfolio_preflight")),
                "runtime_fast_path": _dict(state.get("runtime_fast_path")),
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
