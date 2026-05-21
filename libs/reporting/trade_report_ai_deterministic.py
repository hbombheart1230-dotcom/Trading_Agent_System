from __future__ import annotations

from typing import Any, Callable, Dict, List


def build_shared_facts(
    *,
    shared_seed: Dict[str, Any],
    action: str,
    symbol: str,
    trade_id: str,
    status_text: str,
    clip: Callable[..., str],
    as_dict: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "trade_id": trade_id,
        "action": action,
        "status": status_text,
        "holding_duration": clip(shared_seed.get("holding_duration"), max_len=80) or "unavailable",
        "exit_reason": clip(shared_seed.get("exit_reason"), max_len=280) or "unavailable",
        "pnl": shared_seed.get("pnl", "unavailable"),
        "pnl_pct": shared_seed.get("pnl_pct", "unavailable"),
        "broker_fee": shared_seed.get("broker_fee"),
        "broker_tax": shared_seed.get("broker_tax"),
        "pnl_truth_source": clip(shared_seed.get("pnl_truth_source"), max_len=80) or "unavailable",
        "broker_day_truth_source": clip(shared_seed.get("broker_day_truth_source"), max_len=80) or "",
        "broker_day_match_mode": clip(shared_seed.get("broker_day_match_mode"), max_len=40) or "",
        "broker_day_authoritative": bool(shared_seed.get("broker_day_authoritative")),
        "broker_day_row_count": shared_seed.get("broker_day_row_count"),
        "broker_truth_attempted": bool(shared_seed.get("broker_truth_attempted")),
        "broker_truth_error": clip(shared_seed.get("broker_truth_error"), max_len=240) or "",
        "broker_day_truth_attempted": bool(shared_seed.get("broker_day_truth_attempted")),
        "broker_day_truth_error": clip(shared_seed.get("broker_day_truth_error"), max_len=240) or "",
        "broker_fill_price": shared_seed.get("broker_fill_price"),
        "broker_buy_price": shared_seed.get("broker_buy_price"),
        "account_mark_price": shared_seed.get("account_mark_price"),
        "monitor_mark_price": shared_seed.get("monitor_mark_price"),
        "price_truth_source": clip(shared_seed.get("price_truth_source"), max_len=40) or "unavailable",
        "monitor_price_source": clip(shared_seed.get("monitor_price_source"), max_len=120) or "unavailable",
        "data_source": dict((as_dict(shared_seed.get("resolved_trade_facts")).get("data_source"))),
        "resolved_trade_facts": dict(shared_seed.get("resolved_trade_facts") or {}),
        "lifecycle_action": action,
        "lifecycle_status": status_text,
        "monitor_decision": dict(shared_seed.get("monitor_decision") or {}),
        "scanner_evidence_status": clip(shared_seed.get("scanner_evidence_status"), max_len=24),
        "strategist_evidence_status": clip(shared_seed.get("strategist_evidence_status"), max_len=24),
        "commander_route": dict(shared_seed.get("commander_route") or {}),
    }


def attach_backward_compatible_aliases(report: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(report or {})
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return out


def fallback_section_seeds(
    shared_seed: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    seeds = (
        shared_seed.get("report_section_seeds")
        if isinstance(shared_seed.get("report_section_seeds"), dict)
        else {}
    )
    return {
        "market_context": as_dict(seeds.get("market_context_at_entry")),
        "strategist_summary": as_dict(seeds.get("strategist_summary")),
        "why_symbol": as_dict(seeds.get("why_this_symbol_was_chosen")),
        "entry_decision": as_dict(seeds.get("entry_decision")),
        "holding_story": as_dict(seeds.get("holding_monitoring_story")),
        "exit_decision": as_dict(seeds.get("exit_decision")),
        "scanner_filters": as_dict(seeds.get("scanner_filters")),
        "execution_quality": as_dict(seeds.get("execution_quality")),
        "guard_approval": as_dict(seeds.get("guard_approval_result")),
        "reporter_evaluation": as_dict(seeds.get("reporter_evaluation")),
        "final_operator_conclusion": as_dict(seeds.get("final_operator_conclusion")),
    }


def append_news_scanner_choice_details(
    why_symbol_bullets: List[str],
    news_scanner_contribution: Dict[str, Any],
    *,
    listify: Callable[..., List[Any]],
) -> List[str]:
    if not news_scanner_contribution:
        return list(why_symbol_bullets or [])

    core = (
        news_scanner_contribution.get("core_score_contributions")
        if isinstance(news_scanner_contribution.get("core_score_contributions"), dict)
        else {}
    )
    sentiment_inputs = (
        news_scanner_contribution.get("sentiment_inputs")
        if isinstance(news_scanner_contribution.get("sentiment_inputs"), dict)
        else {}
    )
    theme_trace = (
        news_scanner_contribution.get("theme_alignment_trace")
        if isinstance(news_scanner_contribution.get("theme_alignment_trace"), dict)
        else {}
    )
    news_linkage = (
        news_scanner_contribution.get("news_linkage_trace")
        if isinstance(news_scanner_contribution.get("news_linkage_trace"), dict)
        else {}
    )

    def _core_value(key: str) -> float:
        row = core.get(key)
        if isinstance(row, dict):
            return float(row.get("value") or 0.0)
        try:
            return float(row or 0.0)
        except Exception:
            return 0.0

    extra_rows: List[str] = [
        "점수 기여 세부값은 "
        f"거래대금 {_core_value('trading_value'):+.3f}, "
        f"모멘텀 {_core_value('momentum'):+.3f}, "
        f"추세 {_core_value('trend'):+.3f}, "
        f"테마 가점 {_core_value('theme_boost'):+.3f}, "
        f"감성 {_core_value('sentiment'):+.3f}였습니다.",
        "감성 입력은 "
        f"뉴스 {float(sentiment_inputs.get('news_sentiment_score') or 0.0):+.3f}, "
        f"글로벌 {float(sentiment_inputs.get('global_sentiment_score') or 0.0):+.3f}, "
        f"혼합 {float(sentiment_inputs.get('blended_sentiment_component') or 0.0):+.3f}, "
        f"최종 반영 {float(sentiment_inputs.get('weighted_sentiment_score_contribution') or 0.0):+.3f}였습니다.",
        "테마 정렬은 "
        f"일치 여부 {bool(theme_trace.get('theme_source_matched'))}, "
        f"테마 가점 {float(theme_trace.get('theme_boost_score_contribution') or 0.0):+.3f}, "
        f"전략가 테마 {', '.join(listify(theme_trace.get('strategist_themes'), max_items=4, max_len=60)) or '기록 없음'} 기준으로 반영됐습니다.",
    ]
    if theme_trace.get("theme_source") or theme_trace.get("theme_source_status") or theme_trace.get("theme_source_reason"):
        extra_rows.append(
            "테마 packet 출처는 "
            f"source={theme_trace.get('theme_source') or 'not_captured'}, "
            f"status={theme_trace.get('theme_source_status') or 'not_captured'}, "
            f"reason={theme_trace.get('theme_source_reason') or 'not_captured'} 기준으로 남았습니다."
        )
    extra_rows.append(
        "뉴스 연계는 "
        f"종목 헤드라인 {int(float(news_linkage.get('symbol_headline_count') or 0))}건, "
        f"시장 헤드라인 {int(float(news_linkage.get('market_headline_count') or 0))}건, "
        f"조회 대상 {', '.join(listify(news_linkage.get('news_query_targets'), max_items=6, max_len=60)) or '기록 없음'} 기준으로 남았습니다."
    )

    out = list(why_symbol_bullets or [])
    existing = set(str(row) for row in out)
    for row in extra_rows:
        if row not in existing:
            out.append(row)
    return out


def build_monitor_snapshot(
    *,
    monitor_reason: Dict[str, Any],
    story_input: Dict[str, Any],
    action: str,
    clip: Callable[..., str],
    listify: Callable[..., List[Any]],
    as_dict: Callable[[Any], Dict[str, Any]],
    entry_execution_visibility: Dict[str, Any] | None = None,
    compact_entry_candidate_cascade: Callable[[Any], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    monitor_stop_trace = as_dict(
        monitor_reason.get("monitor_stop_policy_trace")
        or story_input.get("monitor_stop_policy_trace")
    )
    out = {
        "posture": clip(monitor_reason.get("posture"), max_len=40) or action or "WAIT",
        "trigger_type": clip(monitor_reason.get("trigger_type"), max_len=80) or "not_captured",
        "position_age_seconds": int(monitor_reason.get("position_age_seconds") or 0),
        "hard_stop_pct": monitor_reason.get("hard_stop_pct") or monitor_stop_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": monitor_reason.get("adaptive_stop_loss_pct") or monitor_stop_trace.get("adaptive_stop_loss_pct"),
        "stop_loss_pct": monitor_reason.get("stop_loss_pct"),
        "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct") or monitor_stop_trace.get("effective_stop_loss_pct"),
        "effective_stop_reason": clip(monitor_reason.get("effective_stop_reason"), max_len=80) or "not_captured",
        "strategist_baseline_stop_loss_pct": monitor_reason.get("strategist_baseline_stop_loss_pct")
        or monitor_stop_trace.get("strategist_baseline_stop_loss_pct"),
        "strategist_baseline_take_profit_pct": monitor_reason.get("strategist_baseline_take_profit_pct")
        or monitor_stop_trace.get("strategist_baseline_take_profit_pct"),
        "strategist_baseline_trailing_stop_pct": monitor_reason.get("strategist_baseline_trailing_stop_pct")
        or monitor_stop_trace.get("strategist_baseline_trailing_stop_pct"),
        "take_profit_pct": monitor_reason.get("take_profit_pct") or monitor_stop_trace.get("take_profit_pct"),
        "trailing_stop_pct": monitor_reason.get("trailing_stop_pct") or monitor_stop_trace.get("trailing_stop_pct"),
        "exit_triggered": bool(monitor_reason.get("exit_triggered")),
        "current_price": monitor_reason.get("current_price"),
        "average_price": monitor_reason.get("average_price"),
        "peak_price": monitor_reason.get("peak_price"),
        "current_drawdown": monitor_reason.get("current_drawdown"),
        "peak_drawdown": monitor_reason.get("peak_drawdown"),
        "vwap_distance": monitor_reason.get("vwap_distance"),
        "active_exit_axis": clip(monitor_reason.get("active_exit_axis"), max_len=80),
        "watch_axes": listify(monitor_reason.get("watch_axes"), max_items=8, max_len=120),
        "price_source": clip(monitor_reason.get("price_source"), max_len=120) or "not_captured",
        "feature_source": clip(monitor_reason.get("feature_source"), max_len=120) or "not_captured",
        "price_source_policy": clip(monitor_reason.get("price_source_policy"), max_len=260) or "",
    }
    entry_visibility = entry_execution_visibility if isinstance(entry_execution_visibility, dict) else {}
    cascade = as_dict(entry_visibility.get("monitor_entry_candidate_cascade"))
    if not cascade and compact_entry_candidate_cascade is not None:
        cascade = compact_entry_candidate_cascade(monitor_reason.get("entry_candidate_cascade"))
    if cascade:
        out["entry_candidate_cascade"] = cascade
    for key in ("quant_factor_snapshot", "entry_quant_decision", "exit_quant_decision"):
        value = monitor_reason.get(key)
        if not isinstance(value, dict):
            value = story_input.get(key)
        if isinstance(value, dict) and value:
            out[key] = dict(value)
    return out


def enrich_market_context_for_fallback(
    *,
    market_context: Dict[str, Any],
    strategist_context: Dict[str, Any],
    policy_ref_context: Dict[str, Any],
    scanner_bias_summary: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(market_context or {})
    if strategist_context.get("playbook") and not out.get("playbook"):
        out["playbook"] = strategist_context.get("playbook")
    if strategist_context.get("selected_playbook") and not out.get("selected_playbook"):
        out["selected_playbook"] = strategist_context.get("selected_playbook")
    if strategist_context.get("policy_source") and not out.get("policy_source"):
        out["policy_source"] = strategist_context.get("policy_source")
    if strategist_context.get("risk_tone") and not out.get("risk_tone"):
        out["risk_tone"] = strategist_context.get("risk_tone")
    if strategist_context.get("trade_aggressiveness") and not out.get("trade_aggressiveness"):
        out["trade_aggressiveness"] = strategist_context.get("trade_aggressiveness")
    if strategist_context.get("monitor_guidance") and not out.get("monitor_guidance"):
        out["monitor_guidance"] = strategist_context.get("monitor_guidance")
    if strategist_context.get("themes") and not out.get("themes"):
        out["themes"] = list(strategist_context.get("themes") or [])
    if strategist_context.get("preferred_themes") and not out.get("preferred_themes"):
        out["preferred_themes"] = list(strategist_context.get("preferred_themes") or [])
    for theme_key in (
        "theme_strength_packet",
        "theme_source",
        "theme_source_status",
        "theme_source_reason",
        "theme_strength_top_themes",
        "theme_strength_scores",
    ):
        if strategist_context.get(theme_key) not in (None, "", [], {}) and not out.get(theme_key):
            out[theme_key] = strategist_context.get(theme_key)
    if strategist_context.get("market_context_summary") and not out.get("summary"):
        out["summary"] = strategist_context.get("market_context_summary")
    if policy_ref_context.get("risk_mode") and not out.get("risk_mode"):
        out["risk_mode"] = policy_ref_context.get("risk_mode")
    if policy_ref_context.get("selected_playbook") and not out.get("selected_playbook"):
        out["selected_playbook"] = policy_ref_context.get("selected_playbook")
    if policy_ref_context.get("preferred_themes") and not out.get("preferred_themes"):
        out["preferred_themes"] = policy_ref_context.get("preferred_themes")
    if policy_ref_context.get("avoid_themes") and not out.get("avoid_themes"):
        out["avoid_themes"] = policy_ref_context.get("avoid_themes")
    if scanner_bias_summary and not out.get("scanner_bias_summary"):
        out["scanner_bias_summary"] = scanner_bias_summary
    return out


def enrich_scanner_reason_for_fallback(
    *,
    scanner_reason: Dict[str, Any],
    shared_scanner_reasoning: Dict[str, Any],
    shared_selection_trace: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(scanner_reason or {})
    if shared_scanner_reasoning.get("selection_reason_with_bias") and not out.get("selection_reason_with_bias"):
        out["selection_reason_with_bias"] = shared_scanner_reasoning.get("selection_reason_with_bias")
    if shared_scanner_reasoning.get("selection_reason_with_bias") and not out.get("summary"):
        out["summary"] = shared_scanner_reasoning.get("selection_reason_with_bias")
    if shared_selection_trace.get("selected_symbol") and not out.get("selected_symbol"):
        out["selected_symbol"] = shared_selection_trace.get("selected_symbol")
    if shared_selection_trace.get("selected_rank") and not out.get("selected_rank"):
        out["selected_rank"] = shared_selection_trace.get("selected_rank")
    if shared_selection_trace.get("selected_symbol_score_drivers") and not out.get("selected_symbol_score_drivers"):
        out["selected_symbol_score_drivers"] = dict(shared_selection_trace.get("selected_symbol_score_drivers") or {})
    if shared_selection_trace.get("ranked_candidates") and not out.get("top_candidates"):
        out["top_candidates"] = list(shared_selection_trace.get("ranked_candidates") or [])
    return out


def merge_trade_report_candidate(
    story_input: Dict[str, Any],
    candidate: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
    fallback_report: Callable[..., Dict[str, Any]],
    normalize_section: Callable[..., Dict[str, Any]],
    merge_section_with_fallback: Callable[..., Dict[str, Any]],
    prefer_fallback_text: Callable[[Any, Any], str],
    listify: Callable[..., List[Any]],
    clip: Callable[..., str],
    normalize_trade_report_output: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    out = fallback_report(
        story_input,
        status=status,
        mode=mode,
        model=model,
        reason=reason,
    )
    out["generation"] = {
        "status": status,
        "mode": mode,
        "model": clip(model, max_len=120),
        "reason": clip(reason, max_len=320),
    }
    used_fallback_sections: List[str] = []

    def _merge_into(section_key: str, source_value: Any, fallback_key: str | None = None) -> None:
        normalized = normalize_section(
            source_value,
            default_summary=(out.get(section_key) or {}).get("summary") or "",
        )
        merged = merge_section_with_fallback(
            normalized,
            out.get(section_key) if isinstance(out.get(section_key), dict) else {},
            section_key=section_key,
        )
        if not (isinstance(source_value, dict) and source_value):
            used_fallback_sections.append(section_key)
        out[section_key] = merged
        if fallback_key:
            out[fallback_key] = dict(merged)

    _merge_into("executive_summary", candidate.get("executive_summary"))
    _merge_into("market_context_at_entry", candidate.get("market_context_at_entry") or candidate.get("market_context"), "market_context")
    _merge_into("strategist_summary", candidate.get("strategist_summary"))
    _merge_into("strategist_refresh_trace", candidate.get("strategist_refresh_trace"))
    _merge_into("why_this_symbol_was_chosen", candidate.get("why_this_symbol_was_chosen") or candidate.get("why_this_symbol"), "why_this_symbol")
    _merge_into("entry_decision", candidate.get("entry_decision"))
    _merge_into("holding_monitoring_story", candidate.get("holding_monitoring_story") or candidate.get("monitor_trigger_reasoning"), "monitor_trigger_reasoning")
    _merge_into("exit_decision", candidate.get("exit_decision"))
    _merge_into("execution_quality", candidate.get("execution_quality") or candidate.get("execution_result"), "execution_result")
    _merge_into("scanner_filters", candidate.get("scanner_filters") or candidate.get("scanner_logic_and_filters"), "scanner_logic_and_filters")
    _merge_into("guard_approval_result", candidate.get("guard_approval_result"))
    out["reporter_evaluation"] = merge_section_with_fallback(
        normalize_section(candidate.get("reporter_evaluation"), default_summary=out["reporter_evaluation"]["summary"]),
        out["reporter_evaluation"],
        section_key="reporter_evaluation",
    )
    if not isinstance(candidate.get("reporter_evaluation"), dict):
        used_fallback_sections.append("reporter_evaluation")
    out["errors_weaknesses_improvement_points"] = merge_section_with_fallback(
        normalize_section(
            candidate.get("errors_weaknesses_improvement_points"),
            default_summary=out["errors_weaknesses_improvement_points"]["summary"],
        ),
        out["errors_weaknesses_improvement_points"],
        section_key="errors_weaknesses_improvement_points",
    )
    if not isinstance(candidate.get("errors_weaknesses_improvement_points"), dict):
        used_fallback_sections.append("errors_weaknesses_improvement_points")

    final_conclusion = candidate.get("final_operator_conclusion") if isinstance(candidate.get("final_operator_conclusion"), dict) else {}
    out["final_operator_conclusion"] = {
        "summary": prefer_fallback_text(final_conclusion.get("summary"), out["final_operator_conclusion"]["summary"]),
        "current_action": clip(final_conclusion.get("current_action"), max_len=24) or out["final_operator_conclusion"]["current_action"],
        "watch_next": listify(final_conclusion.get("watch_next"), max_items=6, max_len=200) or out["final_operator_conclusion"]["watch_next"],
        "thesis_invalidation": listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=200)
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
    return normalize_trade_report_output(story_input, out)


def build_deterministic_trade_report(
    story_input: Dict[str, Any],
    *,
    fallback_report: Callable[..., Dict[str, Any]],
    attach_report_status_matrix: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    report = fallback_report(
        story_input,
        status="ok",
        mode="deterministic",
        model="",
        reason="deterministic_report_generated",
    )
    return attach_report_status_matrix(
        report,
        story_input,
        ai_trade_report_status="skipped",
        deterministic_report_status="ok",
    )


def failure_report(
    story_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
    error: str = "",
    build_shared_summary_seed: Callable[[Dict[str, Any]], Dict[str, Any]],
    clip: Callable[..., str],
    actual_lifecycle_action: Callable[[Dict[str, Any]], str],
    as_dict: Callable[[Any], Dict[str, Any]],
    utc_now_iso: Callable[[], str],
    build_report_strategist_refresh_trace: Callable[[Dict[str, Any]], Dict[str, Any]],
    listify: Callable[..., List[Any]],
    build_monitor_snapshot_fn: Callable[..., Dict[str, Any]],
    normalize_trade_report_output: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    shared_seed = build_shared_summary_seed(story_input)
    trade_id = clip(shared_seed.get("trade_id"), max_len=120) or clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120)
    action = clip(shared_seed.get("lifecycle_action"), max_len=24) or actual_lifecycle_action(story_input)
    symbol = clip(shared_seed.get("symbol"), max_len=32) or clip(story_input.get("symbol"), max_len=32) or "unknown"
    status_text = clip(shared_seed.get("lifecycle_status"), max_len=32) or clip(story_input.get("status"), max_len=32) or "unknown"
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    full_timeline = [
        row
        for row in list(story_input.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]
    out = {
        "schema_version": "ai_trade_report.v2",
        "generated_at": utc_now_iso(),
        "trade_id": trade_id,
        "story_id": clip(story_input.get("story_id"), max_len=120) or trade_id,
        "run_id": clip(story_input.get("run_id"), max_len=120),
        "symbol": symbol,
        "action": action,
        "status": status_text,
        "story_type": clip(story_input.get("story_type"), max_len=40),
        "execution_mode_label": clip(story_input.get("execution_mode_label"), max_len=80),
        "generation": {
            "status": status,
            "mode": mode,
            "model": clip(model, max_len=120),
            "reason": clip(reason, max_len=320),
        },
        "failure": {
            "status": status,
            "reason": clip(reason, max_len=320),
            "error": clip(error, max_len=500),
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
        "strategist_summary": {
            "summary": "AI generation failed before a rendered strategist-summary section was produced.",
            "bullets": [],
        },
        "strategist_refresh_trace": build_report_strategist_refresh_trace(story_input),
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
            "bullets": listify(monitor_reason.get("bullets"), max_items=8, max_len=260),
        },
        "exit_decision": {
            "summary": "AI generation failed before a rendered exit-decision section was produced.",
            "bullets": [],
        },
        "execution_quality": {
            "summary": "AI generation failed before a rendered execution-quality section was produced.",
            "bullets": [],
        },
        "monitor_snapshot": build_monitor_snapshot_fn(
            monitor_reason=monitor_reason,
            story_input=story_input,
            action=action,
        ),
        "scanner_filters": {
            "summary": "AI generation failed before a rendered scanner-filter section was produced.",
            "bullets": [],
        },
        "guard_approval_result": {
            "summary": "AI generation failed before a rendered guard-approval section was produced.",
            "bullets": [],
        },
        "reporter_evaluation": {
            "summary": clip(reporter_status.get("summary"), max_len=600) or "Reporter linkage status was recorded separately.",
            "status": clip(reporter_status.get("status"), max_len=40) or "missing",
            "grade": clip(reporter_status.get("grade"), max_len=16) or "N/A",
            "bullets": listify(reporter_status.get("bullets"), max_items=8, max_len=260),
        },
        "errors_weaknesses_improvement_points": {
            "summary": "AI generation failed and no rendered improvement section is available.",
            "bullets": [entry for entry in [clip(reason, max_len=240), clip(error, max_len=240)] if entry],
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
    return normalize_trade_report_output(story_input, out)
