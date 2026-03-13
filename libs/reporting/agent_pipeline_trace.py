from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> Optional[str]:
    e = _to_epoch(ts)
    if e is None:
        return None
    return datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%d")


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _latest_row(rows: List[Dict[str, Any]], *, stage: str, event: str) -> Dict[str, Any]:
    for row in reversed(rows):
        if str(row.get("stage") or "").strip() == stage and str(row.get("event") or "").strip() == event:
            return row
    return {}


def _latest_decision_trace_payload(rows: List[Dict[str, Any]], *, event: str, agent: str) -> Dict[str, Any]:
    for row in reversed(rows):
        if str(row.get("stage") or "").strip() != "decision_trace":
            continue
        if str(row.get("event") or "").strip() != event:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        row_agent = str(payload.get("agent") or "").strip().lower()
        if row_agent != agent:
            continue
        agent_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        return dict(agent_payload or {})
    return {}


def _pick_run_id(rows: List[Dict[str, Any]], *, run_id: Optional[str], day: Optional[str]) -> str:
    if run_id:
        return str(run_id).strip()

    target_day = str(day or "").strip()
    for row in reversed(rows):
        rid = str(row.get("run_id") or "").strip()
        if not rid:
            continue
        if target_day and _utc_day(row.get("ts")) != target_day:
            continue
        if str(row.get("stage") or "") == "commander_router" and str(row.get("event") or "") == "route":
            return rid

    for row in reversed(rows):
        rid = str(row.get("run_id") or "").strip()
        if rid and (not target_day or _utc_day(row.get("ts")) == target_day):
            return rid
    return ""


def _extract_title(sample_row: str) -> str:
    s = str(sample_row or "")
    m = re.search(r"title='([^']+)'", s)
    if m:
        return m.group(1)
    return s[:120]


def _summarize_collected_news(raw_input: Dict[str, Any], *, key: str = "collected_news", max_titles: int = 5) -> Dict[str, Any]:
    collected = raw_input.get(key) if isinstance(raw_input.get(key), dict) else {}
    by_symbol: Dict[str, Dict[str, Any]] = {}
    total_headline_count = 0
    sample_titles: List[str] = []
    for symbol, row in collected.items():
        item = row if isinstance(row, dict) else {}
        count = _safe_int(item.get("count"), 0)
        total_headline_count += count
        sample = item.get("sample") if isinstance(item.get("sample"), list) else []
        titles = [_extract_title(x) for x in sample[:max_titles]]
        by_symbol[str(symbol)] = {"count": count, "sample_titles": titles}
        for t in titles:
            if len(sample_titles) < max_titles:
                sample_titles.append(t)
    return {
        "total_headline_count": int(total_headline_count),
        "symbol_count": int(len(by_symbol)),
        "by_symbol": by_symbol,
        "sample_titles": sample_titles,
    }


def _summarize_scanner_sources(candidates: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in candidates:
        srcs = row.get("sources") if isinstance(row.get("sources"), list) else []
        for src in srcs:
            key = str(src or "").strip()
            if not key:
                continue
            counts[key] = int(counts.get(key, 0) + 1)
    return counts


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _reporter_analysis_has_run(report_obj: Dict[str, Any], run_id: str) -> bool:
    rid = str(run_id or "").strip()
    if not rid:
        return False

    trace_summary = report_obj.get("decision_trace_chain_summary")
    if isinstance(trace_summary, dict):
        chains = trace_summary.get("chains")
        if isinstance(chains, list):
            for row in chains:
                if isinstance(row, dict) and str(row.get("run_id") or "").strip() == rid:
                    return True

    decision_chains = report_obj.get("decision_chains")
    if isinstance(decision_chains, dict):
        chains = decision_chains.get("chains")
        if isinstance(chains, list):
            for row in chains:
                if isinstance(row, dict) and str(row.get("run_id") or "").strip() == rid:
                    return True

    trade_summaries = report_obj.get("trade_decision_summaries")
    if isinstance(trade_summaries, dict):
        summaries = trade_summaries.get("trade_summaries")
        if isinstance(summaries, list):
            for row in summaries:
                if not isinstance(row, dict):
                    continue
                buy_run = str(row.get("buy_run_id") or "").strip()
                sell_run = str(row.get("sell_run_id") or "").strip()
                if buy_run == rid or sell_run == rid:
                    return True

    return False


def _build_markdown(out: Dict[str, Any]) -> str:
    commander = out.get("commander") if isinstance(out.get("commander"), dict) else {}
    strategist = out.get("strategist") if isinstance(out.get("strategist"), dict) else {}
    scanner = out.get("scanner") if isinstance(out.get("scanner"), dict) else {}
    monitor = out.get("monitor") if isinstance(out.get("monitor"), dict) else {}
    supervisor = out.get("supervisor") if isinstance(out.get("supervisor"), dict) else {}
    executor = out.get("executor") if isinstance(out.get("executor"), dict) else {}
    reporter = out.get("reporter") if isinstance(out.get("reporter"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Agent Pipeline Trace ({out.get('run_id')})")
    lines.append("")
    lines.append(f"- day: **{out.get('day')}**")
    lines.append(f"- event_log_path: `{out.get('event_log_path')}`")
    lines.append(f"- evidence_log_path: `{out.get('evidence_log_path')}`")
    lines.append("")
    lines.append("## Commander")
    lines.append(f"- mode: **{commander.get('mode')}**")
    lines.append(f"- agents: `{json.dumps(commander.get('agents') or [], ensure_ascii=False)}`")
    lines.append(f"- route_ts: `{commander.get('route_ts')}`")
    lines.append(f"- end_status: **{commander.get('end_status')}**")
    lines.append("")
    lines.append("## Strategist")
    lines.append(
        f"- news_source: **{strategist.get('news_source')}** "
        f"headlines={_safe_int(strategist.get('news_total_headlines'), 0)} "
        f"symbols={_safe_int(strategist.get('news_symbol_count'), 0)}"
    )
    if strategist.get("news_query_targets"):
        lines.append(
            f"- news_query_targets: `{json.dumps(strategist.get('news_query_targets') or [], ensure_ascii=False)}`"
        )
    if strategist.get("news_query_reasoning"):
        lines.append(f"- news_query_reasoning: {strategist.get('news_query_reasoning')}")
    lines.append(
        f"- global_sentiment: score={_safe_float(strategist.get('global_sentiment_score'), 0.0):.4f} "
        f"status={strategist.get('global_sentiment_status')} source={strategist.get('global_sentiment_source')}"
    )
    if strategist.get("global_index_moves"):
        lines.append(
            f"- global_index_moves: `{json.dumps(strategist.get('global_index_moves') or {}, ensure_ascii=False)}`"
        )
    lines.append(
        f"- llm: provider={strategist.get('llm_provider')} model={strategist.get('llm_model')} "
        f"ok={strategist.get('llm_ok')} latency_ms={strategist.get('llm_latency_ms')}"
    )
    lines.append(f"- llm_prompt_captured: **{bool(strategist.get('llm_prompt'))}**")
    lines.append(f"- llm_response_captured: **{bool(strategist.get('llm_response'))}**")
    lines.append(f"- themes: `{json.dumps(strategist.get('themes') or [], ensure_ascii=False)}`")
    lines.append(f"- playbook: **{strategist.get('playbook')}**")
    if strategist.get("scanner_source_policy"):
        lines.append(
            f"- scanner_source_policy: `{json.dumps(strategist.get('scanner_source_policy') or {}, ensure_ascii=False)}`"
        )
    if strategist.get("news_sample_titles"):
        lines.append(
            f"- news_sample_titles: `{json.dumps(strategist.get('news_sample_titles') or [], ensure_ascii=False)}`"
        )
    lines.append("")
    lines.append("## Scanner")
    lines.append(f"- candidate_source: **{scanner.get('candidate_source')}**")
    lines.append(
        f"- pool: before={_safe_int(scanner.get('candidate_pool_before_filter'), 0)} "
        f"after={_safe_int(scanner.get('candidate_pool_after_filter'), 0)}"
    )
    lines.append(f"- kiwoom_source_mix: `{json.dumps(scanner.get('kiwoom_source_mix') or {}, ensure_ascii=False)}`")
    if scanner.get("scanner_source_policy"):
        lines.append(
            f"- scanner_source_policy: `{json.dumps(scanner.get('scanner_source_policy') or {}, ensure_ascii=False)}`"
        )
    lines.append(f"- top_stock: **{scanner.get('top_stock')}** top_score={scanner.get('top_score')}")
    lines.append(f"- top_ranked_symbols: `{json.dumps(scanner.get('top_ranked_symbols') or [], ensure_ascii=False)}`")
    lines.append(
        f"- score_breakdown_summary: `{json.dumps(scanner.get('score_breakdown_summary') or {}, ensure_ascii=False)}`"
    )
    if scanner.get("selected_candidate"):
        lines.append(
            f"- selected_candidate: `{json.dumps(scanner.get('selected_candidate') or {}, ensure_ascii=False)}`"
        )
    lines.append("")
    lines.append("## Monitor")
    lines.append(f"- selected_symbol: **{monitor.get('selected_symbol')}**")
    lines.append(
        f"- entry_reason={monitor.get('entry_reason')} exit_reason={monitor.get('exit_reason')} "
        f"monitor_reason={monitor.get('monitor_reason')}"
    )
    lines.append(
        f"- position_age_seconds={monitor.get('position_age_seconds')} "
        f"min_hold_blocked={monitor.get('min_hold_blocked')} "
        f"sell_cooldown_blocked={monitor.get('sell_cooldown_blocked')}"
    )
    lines.append(
        f"- thresholds: `{json.dumps(monitor.get('thresholds') or {}, ensure_ascii=False)}` "
        f"min_hold={_safe_int(monitor.get('min_hold_sec'), 0)} "
        f"sell_cooldown={_safe_int(monitor.get('sell_cooldown_sec'), 0)} "
        f"confirm_ticks={_safe_int(monitor.get('exit_confirm_ticks'), 0)}"
    )
    if monitor.get("strategy_frame_adjustments"):
        lines.append(
            f"- strategy_frame_adjustments: `{json.dumps(monitor.get('strategy_frame_adjustments') or [], ensure_ascii=False)}`"
        )
    lines.append("")
    lines.append("## Supervisor")
    lines.append(
        f"- verdict={supervisor.get('verdict')} allow={supervisor.get('supervisor_allow')} "
        f"reason={supervisor.get('supervisor_reason') or supervisor.get('guard_reason')}"
    )
    lines.append("")
    lines.append("## Executor")
    lines.append(
        f"- execution_attempted={executor.get('execution_attempted')} "
        f"ok={executor.get('execution_ok')} broker_code={executor.get('broker_code')}"
    )
    lines.append(
        f"- execution_mode={executor.get('execution_mode')} kiwoom_mode={executor.get('kiwoom_mode')} "
        f"broker_env={executor.get('broker_env')} effective_mode={executor.get('effective_mode')}"
    )
    lines.append(
        f"- api_id={executor.get('order_api_id')} url={executor.get('order_url')} "
        f"action={executor.get('order_action')} symbol={executor.get('order_symbol')} qty={executor.get('order_qty')}"
    )
    lines.append("")
    lines.append("## Reporter")
    lines.append(f"- in_run_trace_available: **{reporter.get('in_run_trace_available')}**")
    lines.append(f"- reporter_analysis_day_file_found: **{reporter.get('reporter_analysis_day_file_found')}**")
    lines.append(f"- reporter_analysis_found: **{reporter.get('reporter_analysis_found')}**")
    lines.append(f"- reporter_analysis_path: `{reporter.get('reporter_analysis_path')}`")
    lines.append("")
    lines.append("## Next Command")
    lines.append(f"- `python scripts/run_agent_pipeline_trace_report.py --run-id {out.get('run_id')} --json`")
    lines.append(f"- `python scripts/query_trade_reason_chain.py --run-id {out.get('run_id')} --only-broker-success`")
    return "\n".join(lines)


def generate_agent_pipeline_trace_report(
    event_log_path: Path,
    evidence_log_path: Path,
    report_dir: Path,
    *,
    run_id: Optional[str] = None,
    day: Optional[str] = None,
    reports_root: Optional[Path] = None,
    max_news_titles: int = 5,
) -> Tuple[Path, Path, Dict[str, Any]]:
    event_rows = list(_iter_jsonl(event_log_path))
    rid = _pick_run_id(event_rows, run_id=run_id, day=day)
    if not rid:
        raise RuntimeError("No run_id could be resolved from event log.")

    run_rows = [r for r in event_rows if str(r.get("run_id") or "").strip() == rid]
    run_rows.sort(key=lambda r: _to_epoch(r.get("ts")) or 0)
    run_day = day or (_utc_day((run_rows[0] if run_rows else {}).get("ts")) or "")

    evidence_rows_all = list(_iter_jsonl(evidence_log_path))
    evidence_rows = [r for r in evidence_rows_all if str(r.get("run_id") or "").strip() == rid]

    route = _latest_row(run_rows, stage="commander_router", event="route")
    route_payload = route.get("payload") if isinstance(route.get("payload"), dict) else {}
    route_end = _latest_row(run_rows, stage="commander_router", event="end")
    route_end_payload = route_end.get("payload") if isinstance(route_end.get("payload"), dict) else {}

    strategist_llm = _latest_row(run_rows, stage="strategist_llm", event="result")
    strategist_llm_payload = strategist_llm.get("payload") if isinstance(strategist_llm.get("payload"), dict) else {}
    strategist_summary = _latest_row(run_rows, stage="strategist", event="summary")
    strategist_summary_payload = strategist_summary.get("payload") if isinstance(strategist_summary.get("payload"), dict) else {}

    scanner_summary = _latest_row(run_rows, stage="scanner", event="summary")
    scanner_summary_payload = scanner_summary.get("payload") if isinstance(scanner_summary.get("payload"), dict) else {}
    scanner_trace = _latest_decision_trace_payload(run_rows, event="candidate_selection", agent="scanner")

    monitor_summary = _latest_row(run_rows, stage="monitor", event="summary")
    monitor_summary_payload = monitor_summary.get("payload") if isinstance(monitor_summary.get("payload"), dict) else {}
    monitor_trace = _latest_decision_trace_payload(run_rows, event="entry_exit_decision", agent="monitor")

    supervisor_trace = _latest_decision_trace_payload(run_rows, event="verdict", agent="supervisor")
    executor_trace = _latest_decision_trace_payload(run_rows, event="result", agent="executor")
    execution_row = _latest_row(run_rows, stage="execute_from_packet", event="execution")
    execution_payload = execution_row.get("payload") if isinstance(execution_row.get("payload"), dict) else {}
    execution_order = execution_payload.get("order") if isinstance(execution_payload.get("order"), dict) else {}
    execution_inner = execution_payload.get("payload") if isinstance(execution_payload.get("payload"), dict) else {}
    execution_meta = execution_inner.get("meta") if isinstance(execution_inner.get("meta"), dict) else {}

    # Strategist evidence chain
    strat_theme_rows = [
        r for r in evidence_rows
        if str(r.get("agent") or "").lower() == "strategist" and str(r.get("stage") or "") == "theme_selection"
    ]
    strat_raw = {}
    strat_prompt = ""
    strat_response = ""
    strat_parsed = {}
    for r in strat_theme_rows:
        ri = r.get("raw_input") if isinstance(r.get("raw_input"), dict) else {}
        lp = str(r.get("llm_prompt") or "")
        lr = str(r.get("llm_response") or "")
        po = r.get("parsed_output") if isinstance(r.get("parsed_output"), dict) else {}
        if ri and not strat_raw:
            strat_raw = dict(ri)
        if lp and not strat_prompt:
            strat_prompt = lp
        if lr and not strat_response:
            strat_response = lr
        if po and not strat_parsed:
            strat_parsed = dict(po)
    if not strat_parsed:
        strat_bridge = [
            r for r in evidence_rows
            if str(r.get("agent") or "").lower() == "strategist" and str(r.get("stage") or "") == "decision_bridge"
        ]
        if strat_bridge:
            po = strat_bridge[-1].get("parsed_output")
            if isinstance(po, dict):
                strat_parsed = dict(po)

    news_summary = _summarize_collected_news(strat_raw, max_titles=max_news_titles)
    market_news_summary = _summarize_collected_news(strat_raw, key="collected_market_news", max_titles=max_news_titles)
    candidate_news_summary = _summarize_collected_news(strat_raw, key="collected_candidate_news", max_titles=max_news_titles)
    global_inputs = strat_raw.get("global_sentiment_inputs") if isinstance(strat_raw.get("global_sentiment_inputs"), dict) else {}
    global_index_moves = global_inputs.get("index_moves") if isinstance(global_inputs.get("index_moves"), dict) else {}
    global_macro_moves = global_inputs.get("macro_moves") if isinstance(global_inputs.get("macro_moves"), dict) else {}
    llm_payload = strat_raw.get("llm_payload") if isinstance(strat_raw.get("llm_payload"), dict) else {}
    news_context = llm_payload.get("news_context") if isinstance(llm_payload.get("news_context"), dict) else {}
    news_query_targets = list(strat_raw.get("news_query_targets") or []) if isinstance(strat_raw.get("news_query_targets"), list) else []
    market_summary = strat_raw.get("market_summary") if isinstance(strat_raw.get("market_summary"), dict) else {}
    news_query_reasoning = str(strategist_summary_payload.get("news_query_reasoning") or "").strip()
    if not news_query_reasoning:
        news_query_reasoning = str(strat_parsed.get("news_query_reasoning") or "").strip()
    if not news_query_reasoning:
        news_query_reasoning = str(market_summary.get("news_query_reasoning") or "").strip()
    news_source = "none"
    effective_news_summary = market_news_summary if _safe_int(market_news_summary.get("total_headline_count"), 0) > 0 else news_summary
    if _safe_int(effective_news_summary.get("total_headline_count"), 0) > 0:
        # best-effort source inference from sample strings
        first = ""
        if effective_news_summary.get("sample_titles"):
            first = str((effective_news_summary.get("sample_titles") or [""])[0])
        news_source = "naver_or_yfinance"
        if "Reuters" in first or "Yahoo" in first:
            news_source = "yfinance"
        elif first:
            news_source = "naver"

    scanner_symbol_rows = [
        r for r in evidence_rows
        if str(r.get("agent") or "").lower() == "scanner" and str(r.get("stage") or "") == "symbol_selection"
    ]
    scanner_raw = {}
    if scanner_symbol_rows:
        ri = scanner_symbol_rows[-1].get("raw_input")
        if isinstance(ri, dict):
            scanner_raw = dict(ri)
    scanner_candidates = scanner_raw.get("candidates") if isinstance(scanner_raw.get("candidates"), list) else []
    scanner_source_mix = _summarize_scanner_sources([c for c in scanner_candidates if isinstance(c, dict)])
    raw_strategist_guidance = scanner_raw.get("strategist_guidance") if isinstance(scanner_raw.get("strategist_guidance"), dict) else {}
    scanner_source_policy = (
        scanner_trace.get("scanner_source_policy")
        if isinstance(scanner_trace.get("scanner_source_policy"), dict)
        else raw_strategist_guidance.get("scanner_source_policy")
    )
    if not isinstance(scanner_source_policy, dict):
        scanner_source_policy = {}
    kiwoom_source_mix = (
        scanner_trace.get("kiwoom_pool_source_mix")
        if isinstance(scanner_trace.get("kiwoom_pool_source_mix"), dict)
        else scanner_source_mix
    )

    reporter_rows = [r for r in evidence_rows if str(r.get("agent") or "").lower() == "reporter"]
    reporter_in_run = bool(reporter_rows)
    reporter_analysis_path = ""
    reporter_analysis_day_file_found = False
    reporter_analysis_found = False
    if reports_root is None:
        reports_root = Path("reports")
    if run_day:
        candidate = reports_root / "reporter_analysis" / f"reporter_analysis_{run_day}.json"
        if candidate.exists():
            reporter_analysis_path = str(candidate)
            reporter_analysis_day_file_found = True
            report_obj = _read_json(candidate)
            reporter_analysis_found = _reporter_analysis_has_run(report_obj, rid)

    out: Dict[str, Any] = {
        "schema_version": "agent_pipeline_trace.v1",
        "run_id": rid,
        "day": run_day,
        "event_log_path": str(event_log_path),
        "evidence_log_path": str(evidence_log_path),
        "commander": {
            "mode": str(route_payload.get("mode") or ""),
            "agents": list(route_payload.get("agents") or []),
            "route_ts": str(route.get("ts") or ""),
            "end_ts": str(route_end.get("ts") or ""),
            "end_status": str(route_end_payload.get("status") or ""),
            "path": str(route_end_payload.get("path") or ""),
        },
        "strategist": {
            "news_source": news_source,
            "news_total_headlines": _safe_int(news_summary.get("total_headline_count"), 0),
            "news_symbol_count": _safe_int(news_summary.get("symbol_count"), 0),
            "news_by_symbol": news_summary.get("by_symbol") or {},
            "news_sample_titles": news_summary.get("sample_titles") or [],
            "news_query_targets": news_query_targets,
            "news_query_reasoning": news_query_reasoning,
            "market_news_total_headlines": _safe_int(market_news_summary.get("total_headline_count"), 0),
            "market_news_query_count": _safe_int(market_news_summary.get("symbol_count"), 0),
            "market_news_sample_titles": market_news_summary.get("sample_titles") or [],
            "candidate_news_total_headlines": _safe_int(candidate_news_summary.get("total_headline_count"), 0),
            "news_context": news_context,
            "global_sentiment_score": _safe_float(global_inputs.get("score"), 0.0),
            "global_sentiment_status": str(global_inputs.get("status") or ""),
            "global_sentiment_source": str(global_inputs.get("source") or ""),
            "global_sentiment_reason": str(global_inputs.get("reason") or ""),
            "global_index_moves": dict(global_index_moves),
            "global_macro_moves": dict(global_macro_moves),
            "llm_provider": str(strategist_llm_payload.get("provider") or ""),
            "llm_model": str(strategist_llm_payload.get("model") or ""),
            "llm_ok": bool(strategist_llm_payload.get("ok")),
            "llm_latency_ms": _safe_int(strategist_llm_payload.get("latency_ms"), 0),
            "llm_prompt": strat_prompt,
            "llm_response": strat_response,
            "llm_parsed_output": strat_parsed,
            "themes": list(strategist_summary_payload.get("themes") or []),
            "playbook": str(strategist_summary_payload.get("playbook") or ""),
            "scanner_bias": str(strategist_summary_payload.get("scanner_bias") or ""),
            "scanner_priority": list(strategist_summary_payload.get("scanner_priority") or []),
            "scanner_source_policy": dict(strategist_summary_payload.get("scanner_source_policy") or {}),
            "monitor_guidance": str(strategist_summary_payload.get("monitor_guidance") or ""),
            "risk_tone": str(strategist_summary_payload.get("risk_tone") or ""),
        },
        "scanner": {
            "candidate_source": str(scanner_summary_payload.get("candidate_source") or scanner_raw.get("candidate_source") or ""),
            "candidate_pool_before_filter": _safe_int(
                scanner_summary_payload.get("candidate_pool_before_filter"), _safe_int(scanner_raw.get("candidate_pool_before_filter"), 0)
            ),
            "candidate_pool_after_filter": _safe_int(
                scanner_summary_payload.get("candidate_pool_after_filter"),
                _safe_int(
                    scanner_raw.get("candidate_pool_after_filter"),
                    _safe_int(scanner_raw.get("candidate_pool_before_filter"), 0),
                ),
            ),
            "top_stock": str(scanner_summary_payload.get("top_stock") or scanner_trace.get("selected_symbol") or ""),
            "top_score": scanner_summary_payload.get("top_score"),
            "top_ranked_symbols": list(scanner_summary_payload.get("top_ranked_symbols") or []),
            "score_breakdown_summary": dict(scanner_trace.get("score_breakdown_summary") or {}),
            "selected_candidate": dict(scanner_trace.get("selected_candidate") or {}),
            "kiwoom_source_mix": dict(kiwoom_source_mix or {}),
            "scanner_source_policy": dict(scanner_source_policy or {}),
            "candidate_preview": [c for c in scanner_candidates[:10] if isinstance(c, dict)],
        },
        "monitor": {
            "selected_symbol": str(monitor_summary_payload.get("selected_symbol") or ""),
            "entry_reason": str(monitor_trace.get("entry_reason") or ""),
            "exit_reason": str(monitor_trace.get("exit_reason") or ""),
            "monitor_reason": str(monitor_trace.get("monitor_reason") or monitor_summary_payload.get("monitor_reason") or ""),
            "thresholds": dict(monitor_trace.get("thresholds") or {}),
            "position_age_seconds": monitor_trace.get("position_age_seconds"),
            "min_hold_sec": _safe_int(monitor_trace.get("min_hold_sec"), 0),
            "sell_cooldown_sec": _safe_int(monitor_trace.get("sell_cooldown_sec"), 0),
            "exit_confirm_ticks": _safe_int(monitor_trace.get("exit_confirm_ticks"), 0),
            "min_hold_blocked": bool(monitor_trace.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(monitor_trace.get("sell_cooldown_blocked")),
            "exit_triggered": bool(monitor_summary_payload.get("exit_triggered")),
            "strategy_frame_adjustments": list(monitor_trace.get("strategy_frame_adjustments") or []),
        },
        "supervisor": {
            "verdict": str(supervisor_trace.get("verdict") or ""),
            "guard_reason": str(supervisor_trace.get("guard_reason") or ""),
            "supervisor_allow": supervisor_trace.get("supervisor_allow"),
            "supervisor_reason": str(supervisor_trace.get("supervisor_reason") or ""),
            "action": str(supervisor_trace.get("action") or ""),
            "symbol": str(supervisor_trace.get("symbol") or ""),
        },
        "executor": {
            "execution_attempted": bool(executor_trace.get("execution_attempted")) or bool(execution_payload),
            "execution_ok": bool((executor_trace.get("order_result") if isinstance(executor_trace.get("order_result"), dict) else {}).get("ok"))
            or bool(execution_payload.get("ok")),
            "broker_code": str(
                (executor_trace.get("order_result") if isinstance(executor_trace.get("order_result"), dict) else {}).get("broker_code")
                or execution_inner.get("broker_code")
                or ""
            ),
            "broker_message": str(
                (executor_trace.get("order_result") if isinstance(executor_trace.get("order_result"), dict) else {}).get("broker_message")
                or execution_inner.get("broker_message")
                or ""
            ),
            "order_api_id": str(execution_order.get("order_api_id") or execution_order.get("api_id") or ""),
            "order_action": str(execution_order.get("action") or ""),
            "order_symbol": str(execution_order.get("symbol") or ""),
            "order_qty": execution_order.get("qty"),
            "order_url": str(execution_meta.get("url") or ""),
            "mode": str(execution_inner.get("mode") or ""),
            "execution_mode": str(execution_inner.get("execution_mode") or ""),
            "kiwoom_mode": str(execution_inner.get("kiwoom_mode") or ""),
            "broker_env": str(execution_inner.get("broker_env") or ""),
            "effective_mode": str(execution_inner.get("effective_mode") or ""),
        },
        "reporter": {
            "in_run_trace_available": reporter_in_run,
            "reporter_analysis_day_file_found": reporter_analysis_day_file_found,
            "reporter_analysis_found": reporter_analysis_found,
            "reporter_analysis_path": reporter_analysis_path,
        },
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    safe_run = re.sub(r"[^a-zA-Z0-9_-]+", "", rid)[:20] or "run"
    js_path = report_dir / f"agent_pipeline_trace_{safe_run}.json"
    md_path = report_dir / f"agent_pipeline_trace_{safe_run}.md"
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")
    return md_path, js_path, out


