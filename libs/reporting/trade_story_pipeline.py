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
    fear_index = strategist.get("fear_index") if isinstance(strategist.get("fear_index"), dict) else {}
    macro_overlay = strategist.get("macro_stress_overlay") if isinstance(strategist.get("macro_stress_overlay"), dict) else {}
    regime = str(llm_parsed.get("market_regime") or strategist.get("market_regime") or "not_captured")
    sentiment_state = str(llm_parsed.get("market_sentiment") or strategist.get("market_sentiment") or strategist.get("global_sentiment_status") or "not_captured")
    playbook = str(strategist.get("playbook") or llm_parsed.get("playbook") or "not_captured")
    themes = [str(x or "") for x in list(strategist.get("themes") or []) if str(x or "").strip()][:4]
    global_sentiment_score = strategist.get("global_sentiment_score")
    vix_level = fear_index.get("level") if fear_index else None
    dxy_pct = (strategist.get("global_macro_moves") or {}).get("dxy_pct") if isinstance(strategist.get("global_macro_moves"), dict) else None
    news_total = safe_int(strategist.get("market_news_total_headlines"), safe_int(strategist.get("news_total_headlines"), 0))
    query_count = safe_int(strategist.get("market_news_query_count"), safe_int(strategist.get("news_symbol_count"), 0))
    stress_flags = [str(x or "") for x in list(macro_overlay.get("stress_flags") or []) if str(x or "").strip()]
    defensive_mode = bool(macro_overlay.get("active")) or bool(stress_flags) or (safe_float(vix_level, 0.0) >= 25.0)
    news_summary = (
        f"{news_total} headlines were considered across {query_count} market or symbol targets."
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
    return {
        "regime": regime,
        "market_sentiment": sentiment_state,
        "playbook": playbook,
        "themes": themes,
        "global_sentiment_score": global_sentiment_score,
        "vix_level": vix_level,
        "stress_flags": stress_flags,
        "defensive_mode": defensive_mode,
        "news_input_summary": news_summary,
        "summary": summary,
        "bullets": bullets,
    }


def build_scanner_reason_human(scanner: Dict[str, Any], strategist: Dict[str, Any]) -> Dict[str, Any]:
    selected = scanner.get("selected_candidate") if isinstance(scanner.get("selected_candidate"), dict) else {}
    selected_symbol = str(selected.get("symbol") or scanner.get("top_stock") or "").strip()
    top_ranked_symbols = [str(x or "") for x in list(scanner.get("top_ranked_symbols") or []) if str(x or "").strip()]
    selected_rank = 0
    if selected_symbol and selected_symbol in top_ranked_symbols:
        selected_rank = int(top_ranked_symbols.index(selected_symbol) + 1)
    elif selected_symbol:
        selected_rank = 1
    universe_size = max(
        0,
        safe_int(scanner.get("candidate_pool_after_filter"), 0)
        or safe_int(scanner.get("candidate_pool_before_filter"), 0)
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
    coverage = feature_coverage(selected)
    top_reasons: List[str] = [
        f"highest combined scanner score ({safe_float(selected.get('score_total'), 0.0):.3f})",
        f"selected from {', '.join(selected_sources) if selected_sources else 'captured scanner sources'}",
        f"chart feature coverage {coverage['present']}/{coverage['total']}" if coverage["total"] > 0 else "chart feature coverage was not captured",
        f"aligned with strategist playbook {strategist.get('playbook') or 'not_captured'}",
    ]
    runner_ups: List[Dict[str, Any]] = []
    for symbol in top_ranked_symbols[1:3]:
        preview = preview_map.get(symbol, {})
        runner_ups.append(
            {
                "symbol": symbol,
                "why": clip(preview.get("why"), max_len=120) or "lower final ranking than the selected symbol",
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
    if runner_ups:
        bullets.append("Why not others: " + "; ".join(f"{row['symbol']} was weaker because {row['why']}" for row in runner_ups))
    return {
        "selected_symbol": selected_symbol,
        "selected_rank": selected_rank,
        "universe_size": universe_size,
        "ranking_basis": basis,
        "confidence": selected.get("confidence"),
        "confidence_label": confidence_label(selected.get("confidence")),
        "top_reasons": top_reasons,
        "runner_ups": runner_ups,
        "summary": (
            f"Scanner selected {selected_symbol or '-'} as rank #{selected_rank or 1} out of {universe_size or 0} candidates "
            f"because it led on {', '.join(basis[:3])}."
        ),
        "comparison": (
            f"{selected_symbol} ranked #{selected_rank} out of {universe_size} because it had the strongest overall blend of "
            f"{', '.join(basis[:3])}."
            if selected_symbol
            else "Scanner did not record a selected symbol for this run."
        ),
        "bullets": bullets,
    }


def build_filters_human(scanner: Dict[str, Any], strategist: Dict[str, Any], supervisor: Dict[str, Any]) -> Dict[str, Any]:
    selected = scanner.get("selected_candidate") if isinstance(scanner.get("selected_candidate"), dict) else {}
    sources = [str(x or "") for x in list(selected.get("sources") or []) if str(x or "").strip()]
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    components = selected.get("component_snapshot") if isinstance(selected.get("component_snapshot"), dict) else {}
    coverage = feature_coverage(selected)
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
    return {
        "checks": checks,
        "summary": (
            f"Scanner and guard checks passed {passed} of {len(checks)} visible gates. "
            f"Chart completeness was {chart_status.lower()} with {coverage['present']}/{coverage['total']} captured features."
        ),
        "bullets": bullets,
    }


def build_monitor_reason_human(monitor: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper()
    entry_reason = str(monitor.get("entry_reason") or "").strip()
    exit_reason = str(monitor.get("exit_reason") or "").strip()
    monitor_reason = str(monitor.get("monitor_reason") or "").strip()
    thresholds = monitor.get("thresholds") if isinstance(monitor.get("thresholds"), dict) else {}
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

    watch_axes: List[str] = []
    if thresholds.get("hard_stop_pct") not in (None, "") or thresholds.get("stop_loss_pct") not in (None, ""):
        watch_axes.append("Hard stop")
    if thresholds.get("take_profit_pct") not in (None, ""):
        watch_axes.append("Take profit")
    if thresholds.get("trailing_stop_pct") not in (None, ""):
        watch_axes.append("Trailing stop")
    if thresholds.get("peak_drawdown_exit_pct") not in (None, ""):
        watch_axes.append("Peak drawdown")
    if thresholds.get("vwap_breakdown_pct") not in (None, ""):
        watch_axes.append("VWAP breakdown")
    if thresholds.get("intraday_low_break_pct") not in (None, ""):
        watch_axes.append("Intraday low break")
    if thresholds.get("trend_strength_floor") not in (None, ""):
        watch_axes.append("Trend breakdown")
    if thresholds.get("vol_expansion_ratio") not in (None, ""):
        watch_axes.append("Volatility expansion")

    trigger_type = exit_reason if action == "SELL" else entry_reason or monitor_reason
    active_exit_axis = format_exit_label(trigger_type)
    if action == "BUY":
        summary = f"BUY was triggered because {entry_reason or monitor_reason or 'the entry condition passed'}."
    elif action == "SELL":
        summary = f"SELL was triggered because {exit_reason or monitor_reason or 'the exit condition passed'}."
    else:
        summary = f"Monitor posture was {action or 'WAIT'} with trigger {trigger_type or 'not_captured'}."
    bullets = [
        f"Posture: {action or 'WAIT'}",
        f"Trigger type: {trigger_type or 'not_captured'}",
        f"Monitor reason: {monitor_reason or 'not_captured'}",
        f"Position age: {safe_int(monitor.get('position_age_seconds'), 0)} seconds",
        f"Stop loss: {format_ratio_pct(thresholds.get('stop_loss_pct'))}%",
        f"Effective stop: {format_ratio_pct(thresholds.get('effective_stop_loss_pct'))}%",
        f"Effective stop reason: {str(thresholds.get('effective_stop_reason') or 'not_captured')}",
        f"Take profit: {format_ratio_pct(thresholds.get('take_profit_pct'))}%",
        f"Min hold blocked: {'yes' if monitor.get('min_hold_blocked') else 'no'}",
        f"Sell cooldown blocked: {'yes' if monitor.get('sell_cooldown_blocked') else 'no'}",
        f"Exit triggered: {'yes' if monitor.get('exit_triggered') else 'no'}",
    ]
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
        "current_price": current_price,
        "average_price": average_price,
        "peak_price": peak_price,
        "current_drawdown": current_drawdown,
        "peak_drawdown": peak_drawdown,
        "vwap_distance": vwap_distance,
        "active_exit_axis": active_exit_axis,
        "watch_axes": watch_axes[:8],
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
        filters_human = dict(bundle_out.get("filters_human") or {})
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
            "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
        }

    return {
        "schema_version": "trade_story_input.v1",
        "trade_id": str(bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
        "story_id": str(bundle_out.get("story_id") or ""),
        "run_id": str(bundle_out.get("run_id") or ""),
        "symbol": str((bundle_out.get("execution") or {}).get("symbol") or ""),
        "action": str((bundle_out.get("execution") or {}).get("action") or ""),
        "status": str(bundle_out.get("trade_lifecycle_status") or "closed"),
        "story_type": str(story_contract.get("story_type") or ""),
        "execution_mode_label": str(story_contract.get("execution_mode_label") or ""),
        "market_context_human": dict(bundle_out.get("market_context_human") or {}),
        "scanner_reason_human": dict(bundle_out.get("scanner_reason_human") or {}),
        "filters_human": dict(bundle_out.get("filters_human") or {}),
        "monitor_reason_human": dict(bundle_out.get("monitor_reason_human") or {}),
        "guard_reason_human": dict(bundle_out.get("guard_reason_human") or {}),
        "execution_outcome_human": dict(bundle_out.get("execution_outcome_human") or {}),
        "reporter_status_human": dict(bundle_out.get("reporter_status_human") or {}),
        "operator_conclusion_human": dict(bundle_out.get("operator_conclusion_human") or {}),
        "timeline": list(bundle_out.get("timeline") or []),
        "warnings": list(bundle_out.get("warnings") or []),
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
