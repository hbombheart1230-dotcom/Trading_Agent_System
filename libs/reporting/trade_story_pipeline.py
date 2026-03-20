from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List


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


def _source_confidence_label(source: Any) -> str:
    raw = str(source or "").strip().lower()
    if raw == "canonical":
        return "high"
    if raw in {"direct_artifact", "direct"}:
        return "medium"
    if raw in {"event_log", "fallback", "inferred"}:
        return "low"
    return "low"


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
    return {
        "regime": regime,
        "market_sentiment": sentiment_state,
        "playbook": playbook,
        "themes": themes,
        "global_sentiment_score": global_sentiment_score,
        "vix_level": vix_level,
        "stress_flags": stress_flags,
        "defensive_mode": defensive_mode,
        "headline_count": news_total,
        "news_query_count": query_count,
        "market_signal_total": market_signal_total,
        "candidate_signal_total": candidate_signal_total,
        "news_query_targets": query_targets,
        "key_events_hint": key_events_hint,
        "market_news_titles": market_news_titles,
        "candidate_news_titles": candidate_news_titles,
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
    thresholds = monitor.get("thresholds") if isinstance(monitor.get("thresholds"), dict) else {}
    thresholds_guards_used = (
        monitor.get("thresholds_guards_used")
        if isinstance(monitor.get("thresholds_guards_used"), dict)
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
    entry_reason = str(monitor.get("entry_reason") or "").strip()
    entry_pattern = str(monitor.get("entry_pattern") or "").strip()
    entry_signal_chain = [str(x or "") for x in list(monitor.get("entry_signal_chain") or []) if str(x or "").strip()]
    entry_metrics = monitor.get("entry_metrics") if isinstance(monitor.get("entry_metrics"), dict) else {}
    entry_thresholds = monitor.get("entry_thresholds") if isinstance(monitor.get("entry_thresholds"), dict) else {}
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
    if eod_carry_approved and action not in ("BUY", "SELL"):
        summary = (
            f"Monitor kept the position into the close because overnight carry was approved "
            f"{safe_float(minutes_to_close, 0.0):.1f} minutes before the close."
        )
    elif action == "BUY":
        summary = f"BUY was triggered because {entry_reason or monitor_reason or 'the intraday entry condition passed'}."
        if entry_pattern:
            summary += f" Pattern: {entry_pattern}."
    elif action == "SELL":
        if eod_carry_evaluated and not eod_carry_approved and str(trigger_type or "").strip().lower() in ("eod_flat", "carry_overnight_approved"):
            summary = (
                f"SELL was triggered to flatten before the close because overnight carry was not approved "
                f"({eod_carry_reason or 'carry conditions were not met'})."
            )
        else:
            summary = f"SELL was triggered because {trigger_type or monitor_reason or 'the exit condition passed'}."
    elif entry_evaluated and not entry_triggered:
        summary = f"Monitor stayed on WAIT because {entry_reason or monitor_reason or 'the intraday entry signal was not confirmed'}."
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
    if entry_evaluated:
        bullets.append(f"Entry triggered: {'yes' if entry_triggered else 'no'}")
        bullets.append(f"Entry pattern: {entry_pattern or 'not_captured'}")
        if entry_signal_chain:
            bullets.append("Entry signal chain: " + " -> ".join(entry_signal_chain[:6]))
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
            bullets.append(
                f"Pullback depth: {format_ratio_pct(entry_metrics.get('pullback_depth_pct'))}% "
                f"(max {format_ratio_pct(entry_thresholds.get('pullback_max_pct'))}%)"
            )
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
        "effective_stop_loss_pct": thresholds.get("effective_stop_loss_pct"),
        "effective_stop_reason": str(thresholds.get("effective_stop_reason") or "").strip(),
        "take_profit_pct": thresholds.get("take_profit_pct"),
        "exit_triggered": bool(monitor.get("exit_triggered")),
        "entry_evaluated": entry_evaluated,
        "entry_triggered": entry_triggered,
        "entry_reason": entry_reason,
        "entry_pattern": entry_pattern,
        "entry_signal_chain": entry_signal_chain[:8],
        "entry_metrics": dict(entry_metrics),
        "entry_thresholds": dict(entry_thresholds),
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
        return {
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
            "operator_conclusion_human": operator_conclusion_human,
            "timeline": [dict(x) for x in list(lifecycle.get("timeline") or bundle_out.get("timeline") or []) if isinstance(x, dict)][:40],
            "warnings": [str(x or "") for x in list(bundle_out.get("warnings") or lifecycle.get("warnings") or []) if str(x or "").strip()][:20],
            "improvement_points": [str(x or "") for x in list(reporter.get("improvement_points") or []) if str(x or "").strip()][:12],
            "strategist_evidence": dict(bundle_out.get("strategist_evidence") or (bundle_out.get("evidence") or {}).get("strategist") or {}),
            "scanner_evidence": scanner_evidence,
            "monitor_timeline": dict(bundle_out.get("monitor_timeline") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
            "canonical_agent_artifacts": dict(bundle_out.get("canonical_agent_artifacts") or {}),
            "evidence_provenance": dict(bundle_out.get("evidence_provenance") or {}),
            "section_provenance": dict(section_provenance),
            "evidence_source": "canonical" if any(
                str(source or "").strip().lower() == "canonical"
                for source in dict(bundle_out.get("evidence_provenance") or {}).values()
            ) else "direct_artifact",
            "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
        }

    return {
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
        "market_context_human": dict(bundle_out.get("market_context_human") or {}),
        "scanner_reason_human": enrich_scanner_reason_from_evidence(
            dict(bundle_out.get("scanner_reason_human") or {}),
            dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
        ),
        "filters_human": enrich_filters_from_evidence(
            dict(bundle_out.get("filters_human") or {}),
            dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
            selected_symbol=str(((bundle_out.get("scanner_reason_human") or {}).get("selected_symbol")) or ((bundle_out.get("execution") or {}).get("symbol")) or ""),
        ),
        "monitor_reason_human": dict(bundle_out.get("monitor_reason_human") or {}),
        "guard_reason_human": dict(bundle_out.get("guard_reason_human") or {}),
        "execution_outcome_human": dict(bundle_out.get("execution_outcome_human") or {}),
        "reporter_status_human": dict(bundle_out.get("reporter_status_human") or {}),
        "operator_conclusion_human": dict(bundle_out.get("operator_conclusion_human") or {}),
        "timeline": list(bundle_out.get("timeline") or []),
        "warnings": list(bundle_out.get("warnings") or []),
        "strategist_evidence": dict(bundle_out.get("strategist_evidence") or (bundle_out.get("evidence") or {}).get("strategist") or {}),
        "scanner_evidence": dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
        "monitor_timeline": dict(bundle_out.get("monitor_timeline") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
        "canonical_agent_artifacts": dict(bundle_out.get("canonical_agent_artifacts") or {}),
        "evidence_provenance": dict(bundle_out.get("evidence_provenance") or {}),
        "section_provenance": dict(section_provenance),
        "evidence_source": "canonical" if any(
            str(source or "").strip().lower() == "canonical"
            for source in dict(bundle_out.get("evidence_provenance") or {}).values()
        ) else "direct_artifact",
        "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
    }


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
