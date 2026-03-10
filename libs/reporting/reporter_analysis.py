from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .operator_visibility import (
    generate_decision_story_report,
    generate_operator_daily_summary,
    generate_run_card_report,
)
from .trade_explain import generate_trade_explain_report


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
    epoch = _to_epoch(ts)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


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


def _latest_day(path: Path) -> Optional[str]:
    best: Optional[str] = None
    for row in _iter_jsonl(path):
        day = _utc_day(row.get("ts"))
        if not day:
            continue
        if best is None or day > best:
            best = day
    return best


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _reason_text(reason: Any) -> str:
    s = str(reason or "").strip()
    return s if s else "unspecified"


def _execution_rows_by_run(executions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in executions:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        out.setdefault(run_id, []).append(row)
    return out


def _build_trade_decision_summaries(trade_explain_obj: Dict[str, Any]) -> Dict[str, Any]:
    executions = trade_explain_obj.get("executions") if isinstance(trade_explain_obj.get("executions"), list) else []
    sell_pairs = trade_explain_obj.get("sell_pairs") if isinstance(trade_explain_obj.get("sell_pairs"), list) else []
    by_run = _execution_rows_by_run([x for x in executions if isinstance(x, dict)])

    summaries: List[Dict[str, Any]] = []
    for pair in sell_pairs:
        if not isinstance(pair, dict):
            continue
        buy_runs = pair.get("matched_buy_run_ids") if isinstance(pair.get("matched_buy_run_ids"), list) else []
        buy_run_id = str(buy_runs[0] or "").strip() if buy_runs else ""
        buy_info = {}
        if buy_run_id and by_run.get(buy_run_id):
            for row in by_run[buy_run_id]:
                if str(row.get("action") or "").upper() == "BUY":
                    buy_info = row
                    break
        sell_reason = _reason_text(pair.get("decision_reason") or pair.get("decision_rationale"))
        monitor_reason = _reason_text(pair.get("monitor_reason"))
        exit_trigger = _reason_text(pair.get("monitor_exit_reason") or pair.get("monitor_reason") or sell_reason)
        summaries.append(
            {
                "symbol": str(pair.get("symbol") or ""),
                "buy_run_id": buy_run_id,
                "sell_run_id": str(pair.get("sell_run_id") or ""),
                "buy_reason": _reason_text(
                    buy_info.get("decision_reason") if isinstance(buy_info, dict) else ""
                    or buy_info.get("decision_rationale") if isinstance(buy_info, dict) else ""
                ),
                "sell_reason": sell_reason,
                "holding_duration_sec": _safe_int(pair.get("hold_duration_sec_avg"), 0),
                "exit_trigger": exit_trigger,
                "monitor_signals": {
                    "monitor_reason": monitor_reason,
                    "monitor_exit_reason": _reason_text(pair.get("monitor_exit_reason")),
                    "signal_score": pair.get("signal_score"),
                    "rsi14": pair.get("rsi14"),
                    "volatility20": pair.get("volatility20"),
                },
                "estimated_realized_pnl": _safe_float(pair.get("estimated_realized_pnl"), 0.0),
                "buy_ts": buy_info.get("ts") if isinstance(buy_info, dict) else "",
                "sell_ts": str(pair.get("sell_ts") or ""),
            }
        )

    return {
        "trade_summary_total": int(len(summaries)),
        "trade_summaries": summaries,
    }


def _build_intent_flow_analysis(
    *,
    day_rows: List[Dict[str, Any]],
    intents_path: Optional[Path],
    day: str,
    operator_summary_obj: Dict[str, Any],
) -> Dict[str, Any]:
    created = 0
    approved = 0
    executed = 0
    blocked = 0
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    if intents_path is not None and intents_path.exists():
        for row in _iter_jsonl(intents_path):
            ts = row.get("ts")
            if _utc_day(ts) != day:
                continue
            status = str(row.get("status") or "").strip().lower()
            reason = _reason_text(row.get("reason"))
            if status:
                status_counts[status] += 1
                if status == "approved":
                    approved += 1
                elif status == "executed":
                    executed += 1
                elif status in ("rejected", "failed"):
                    blocked += 1
                    reason_counts[reason] += 1
            else:
                created += 1

    for row in day_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "execute_from_packet" and event == "verdict" and payload.get("allowed") is False:
            blocked += 1
            reason_counts[_reason_text(payload.get("reason"))] += 1
        if stage == "monitor" and event == "summary":
            if bool(payload.get("min_hold_blocked")):
                reason_counts["min_hold_blocked"] += 1
            if bool(payload.get("sell_cooldown_blocked")):
                reason_counts["sell_cooldown_blocked"] += 1
            mr = str(payload.get("monitor_reason") or "").strip()
            if mr:
                reason_counts[f"monitor:{mr}"] += 1

    metrics_exec = (
        operator_summary_obj.get("raw_snapshot", {}).get("metrics_execution", {})
        if isinstance(operator_summary_obj.get("raw_snapshot"), dict)
        else {}
    )
    if created <= 0:
        created = _safe_int(metrics_exec.get("intents_created"), created)
    if blocked <= 0:
        blocked = _safe_int(metrics_exec.get("intents_blocked"), blocked)
    if approved <= 0:
        approved = _safe_int(metrics_exec.get("intents_approved"), approved)
    if executed <= 0:
        executed = _safe_int(metrics_exec.get("intents_executed"), executed)

    return {
        "intents_created": int(created),
        "intents_blocked": int(blocked),
        "intents_approved": int(approved),
        "intents_executed": int(executed),
        "status_counts": dict(status_counts),
        "reason_top": dict(reason_counts.most_common(12)),
    }


def _build_strategy_effectiveness(
    *,
    day_rows: List[Dict[str, Any]],
    trade_explain_obj: Dict[str, Any],
) -> Dict[str, Any]:
    theme_counts: Counter[str] = Counter()
    scanner_top_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    exit_reason_counts: Counter[str] = Counter()

    for row in day_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "strategist_llm" and event == "result":
            for key in ("themes", "top_themes"):
                v = payload.get(key)
                if isinstance(v, list):
                    for item in v:
                        t = str(item or "").strip().lower()
                        if t:
                            theme_counts[t] += 1
        if stage == "scanner" and event == "summary":
            top_stock = str(payload.get("top_stock") or "").strip().upper()
            if top_stock:
                scanner_top_counts[top_stock] += 1
        if stage == "monitor" and event == "summary":
            ex = str(payload.get("exit_reason") or "").strip().lower()
            if ex:
                exit_reason_counts[ex] += 1

    executions = trade_explain_obj.get("executions") if isinstance(trade_explain_obj.get("executions"), list) else []
    for row in executions:
        if not isinstance(row, dict):
            continue
        st = str(row.get("strategy") or "").strip()
        if st:
            strategy_counts[st] += 1

    top_theme = theme_counts.most_common(1)
    top_symbol = scanner_top_counts.most_common(1)
    top_exit = exit_reason_counts.most_common(1)
    strategy_line = (
        f"Strategist favored {top_theme[0][0]} theme."
        if top_theme
        else "Strategist theme evidence was not captured in current event payload."
    )
    scanner_line = (
        f"Scanner selected {top_symbol[0][0]} most frequently."
        if top_symbol
        else "Scanner top-stock evidence was not captured for this day."
    )
    monitor_line = (
        f"Monitor exited mostly due to {top_exit[0][0]}."
        if top_exit
        else "Monitor exit trigger evidence was limited for this day."
    )

    return {
        "theme_counts": dict(theme_counts.most_common(10)),
        "scanner_top_stock_counts": dict(scanner_top_counts.most_common(10)),
        "strategy_counts": dict(strategy_counts.most_common(10)),
        "monitor_exit_reason_counts": dict(exit_reason_counts.most_common(10)),
        "narrative": [strategy_line, scanner_line, monitor_line],
    }


def _build_overtrading_diagnostics(
    *,
    trade_explain_obj: Dict[str, Any],
    intent_flow: Dict[str, Any],
    rapid_threshold_sec: int,
) -> Dict[str, Any]:
    sell_pairs = trade_explain_obj.get("sell_pairs") if isinstance(trade_explain_obj.get("sell_pairs"), list) else []
    short_pairs = 0
    for p in sell_pairs:
        if not isinstance(p, dict):
            continue
        if _safe_int(p.get("hold_duration_sec_avg"), 0) < int(rapid_threshold_sec):
            short_pairs += 1

    reason_top = intent_flow.get("reason_top") if isinstance(intent_flow.get("reason_top"), dict) else {}
    noise_related = 0
    guard_related = 0
    for k, v in reason_top.items():
        key = str(k).lower()
        cnt = _safe_int(v, 0)
        if "cooldown" in key or "confirmation" in key or "post_exit" in key:
            noise_related += cnt
        if "guard" in key or "allowlist" in key or "notional" in key or "risk" in key:
            guard_related += cnt

    created = _safe_int(intent_flow.get("intents_created"), 0)
    blocked = _safe_int(intent_flow.get("intents_blocked"), 0)
    blocked_rate = (float(blocked) / float(created)) if created > 0 else 0.0

    return {
        "rapid_buy_sell_cycles": int(short_pairs),
        "rapid_threshold_sec": int(rapid_threshold_sec),
        "noise_exit_related_count": int(noise_related),
        "frequent_guard_block_count": int(guard_related),
        "guard_block_rate": float(round(blocked_rate, 4)),
    }


def _build_incident_postmortem(
    *,
    overtrading: Dict[str, Any],
    intent_flow: Dict[str, Any],
) -> Dict[str, Any]:
    incidents: List[Dict[str, Any]] = []

    if _safe_int(overtrading.get("rapid_buy_sell_cycles"), 0) > 0:
        incidents.append(
            {
                "type": "unexpected_rapid_exit",
                "severity": "YELLOW",
                "detail": f"rapid_buy_sell_cycles={_safe_int(overtrading.get('rapid_buy_sell_cycles'), 0)}",
            }
        )

    frequent_guard = _safe_int(overtrading.get("frequent_guard_block_count"), 0)
    if frequent_guard >= 3:
        incidents.append(
            {
                "type": "repeated_guard_blocks",
                "severity": "YELLOW",
                "detail": f"guard_related_block_reasons={frequent_guard}",
            }
        )

    if _safe_float(overtrading.get("guard_block_rate"), 0.0) >= 0.5 and _safe_int(intent_flow.get("intents_created"), 0) >= 5:
        incidents.append(
            {
                "type": "high_block_rate",
                "severity": "RED",
                "detail": f"guard_block_rate={_safe_float(overtrading.get('guard_block_rate'), 0.0):.2%}",
            }
        )

    return {
        "incident_total": int(len(incidents)),
        "incidents": incidents,
    }


def _build_market_context(*, trade_explain_obj: Dict[str, Any], day_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    global_scores: List[float] = []
    symbol_scores: List[float] = []
    for row in trade_explain_obj.get("executions") or []:
        if not isinstance(row, dict):
            continue
        gs = row.get("news_global_sentiment_score")
        ss = row.get("news_symbol_sentiment_score")
        if gs is not None:
            global_scores.append(_safe_float(gs, 0.0))
        if ss is not None:
            symbol_scores.append(_safe_float(ss, 0.0))

    providers: Counter[str] = Counter()
    models: Counter[str] = Counter()
    for row in day_rows:
        if str(row.get("stage") or "") != "strategist_llm" or str(row.get("event") or "") != "result":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        p = str(payload.get("provider") or "").strip()
        m = str(payload.get("model") or "").strip()
        if p:
            providers[p] += 1
        if m:
            models[m] += 1

    return {
        "global_sentiment_avg": float(round(sum(global_scores) / len(global_scores), 6)) if global_scores else None,
        "symbol_sentiment_avg": float(round(sum(symbol_scores) / len(symbol_scores), 6)) if symbol_scores else None,
        "llm_provider_top": dict(providers.most_common(3)),
        "llm_model_top": dict(models.most_common(3)),
    }


def _to_markdown(out: Dict[str, Any]) -> str:
    day = str(out.get("day") or "")
    trade_section = out.get("trade_decision_summaries") if isinstance(out.get("trade_decision_summaries"), dict) else {}
    flow = out.get("intent_flow_analysis") if isinstance(out.get("intent_flow_analysis"), dict) else {}
    eff = out.get("strategy_effectiveness") if isinstance(out.get("strategy_effectiveness"), dict) else {}
    over = out.get("overtrading_diagnostics") if isinstance(out.get("overtrading_diagnostics"), dict) else {}
    market = out.get("market_context") if isinstance(out.get("market_context"), dict) else {}
    incidents = out.get("incident_postmortem") if isinstance(out.get("incident_postmortem"), dict) else {}
    operator = out.get("daily_operator_report") if isinstance(out.get("daily_operator_report"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Reporter Analysis ({day})")
    lines.append("")
    lines.append("## Daily Operator Report")
    lines.append("")
    lines.append(f"- market_context: `{json.dumps(market, ensure_ascii=False)}`")
    lines.append(f"- trades_executed: **{_safe_int(operator.get('trades_executed'), 0)}**")
    lines.append(f"- trades_blocked: **{_safe_int(operator.get('trades_blocked'), 0)}**")
    lines.append(f"- major_decisions: `{json.dumps(operator.get('major_decisions') or [], ensure_ascii=False)}`")
    lines.append(f"- anomalies: `{json.dumps(operator.get('anomalies') or [], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Trade Decision Summaries")
    lines.append("")
    lines.append(f"- trade_summary_total: **{_safe_int(trade_section.get('trade_summary_total'), 0)}**")
    lines.append("| symbol | buy_reason | sell_reason | holding_duration_sec | exit_trigger |")
    lines.append("| --- | --- | --- | ---: | --- |")
    for row in (trade_section.get("trade_summaries") or [])[:40]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('symbol') or '-'} | {row.get('buy_reason') or '-'} | {row.get('sell_reason') or '-'} | "
            f"{_safe_int(row.get('holding_duration_sec'), 0)} | {row.get('exit_trigger') or '-'} |"
        )
    lines.append("")
    lines.append("## Intent Flow Analysis")
    lines.append("")
    lines.append(f"- intents_created: **{_safe_int(flow.get('intents_created'), 0)}**")
    lines.append(f"- intents_blocked: **{_safe_int(flow.get('intents_blocked'), 0)}**")
    lines.append(f"- intents_approved: **{_safe_int(flow.get('intents_approved'), 0)}**")
    lines.append(f"- intents_executed: **{_safe_int(flow.get('intents_executed'), 0)}**")
    lines.append(f"- reason_top: `{json.dumps(flow.get('reason_top') or {}, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Strategy Effectiveness")
    lines.append("")
    for text in (eff.get("narrative") or []):
        lines.append(f"- {text}")
    lines.append("")
    lines.append("## Overtrading Diagnostics")
    lines.append("")
    lines.append(f"- rapid_buy_sell_cycles(<{_safe_int(over.get('rapid_threshold_sec'), 0)}s): **{_safe_int(over.get('rapid_buy_sell_cycles'), 0)}**")
    lines.append(f"- noise_exit_related_count: **{_safe_int(over.get('noise_exit_related_count'), 0)}**")
    lines.append(f"- frequent_guard_block_count: **{_safe_int(over.get('frequent_guard_block_count'), 0)}**")
    lines.append(f"- guard_block_rate: **{_safe_float(over.get('guard_block_rate'), 0.0):.2%}**")
    lines.append("")
    lines.append("## Incident / Post-Mortem Support")
    lines.append("")
    lines.append(f"- incident_total: **{_safe_int(incidents.get('incident_total'), 0)}**")
    for item in (incidents.get("incidents") or []):
        if not isinstance(item, dict):
            continue
        lines.append(f"- [{item.get('severity')}] {item.get('type')}: {item.get('detail')}")
    lines.append("")
    lines.append("## Source Artifacts")
    lines.append("")
    refs = out.get("source_reports") if isinstance(out.get("source_reports"), dict) else {}
    for k, v in refs.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    return "\n".join(lines)


def generate_reporter_analysis_report(
    event_log_path: Path,
    report_dir: Path,
    *,
    day: Optional[str] = None,
    intents_path: Optional[Path] = None,
    reports_root: Optional[Path] = None,
    rapid_cycle_threshold_sec: int = 120,
) -> Tuple[Path, Path, Dict[str, Any]]:
    """Generate enhanced reporter analysis from append-only logs.

    Reporter remains passive: this function reads logs only and derives reports.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    root = reports_root or report_dir.parent
    target_day = str(day or _latest_day(event_log_path) or date.today().isoformat())

    rows = []
    for row in _iter_jsonl(event_log_path):
        ts = row.get("ts") or (row.get("payload") or {}).get("ts")
        rows.append({**row, "_day": _utc_day(ts)})
    day_rows = [r for r in rows if str(r.get("_day") or "") == target_day]

    trade_md, trade_js, trade_obj = generate_trade_explain_report(
        event_log_path,
        root / "trade_explain",
        day=target_day,
        max_executions=300,
        max_sell_pairs=300,
    )
    op_md, op_js = generate_operator_daily_summary(
        event_log_path,
        root / "operator_summary",
        day=target_day,
        metrics_report_dir=root / "metrics",
        m30_post_golive_dir=root / "m30_post_golive",
        m30_golive_dir=root / "m30_golive",
        m31_slo_incident_dir=root / "m31_slo_incident",
    )
    ds_md, ds_obj = generate_decision_story_report(
        event_log_path,
        root / "decision_story",
        day=target_day,
    )
    rc_md, rc_obj = generate_run_card_report(
        event_log_path,
        root / "run_cards",
        day=target_day,
    )

    op_obj = _read_json(op_js)
    trade_decision = _build_trade_decision_summaries(trade_obj)
    intent_flow = _build_intent_flow_analysis(
        day_rows=day_rows,
        intents_path=intents_path,
        day=target_day,
        operator_summary_obj=op_obj,
    )
    strategy_eff = _build_strategy_effectiveness(day_rows=day_rows, trade_explain_obj=trade_obj)
    overtrading = _build_overtrading_diagnostics(
        trade_explain_obj=trade_obj,
        intent_flow=intent_flow,
        rapid_threshold_sec=max(1, int(rapid_cycle_threshold_sec)),
    )
    incident = _build_incident_postmortem(overtrading=overtrading, intent_flow=intent_flow)
    market_context = _build_market_context(trade_explain_obj=trade_obj, day_rows=day_rows)

    trading_activity = (
        op_obj.get("trading_activity_summary") if isinstance(op_obj.get("trading_activity_summary"), dict) else {}
    )
    daily_operator = {
        "market_context": market_context,
        "trades_executed": _safe_int(trading_activity.get("executions_total"), 0),
        "trades_blocked": _safe_int(trading_activity.get("blocked_total"), 0),
        "major_decisions": list((trading_activity.get("strategy_counts") or {}).keys())[:5]
        if isinstance(trading_activity.get("strategy_counts"), dict)
        else [],
        "anomalies": [i.get("type") for i in (incident.get("incidents") or []) if isinstance(i, dict)],
    }

    out: Dict[str, Any] = {
        "schema_version": "reporter_analysis.v1",
        "day": target_day,
        "trade_decision_summaries": trade_decision,
        "intent_flow_analysis": intent_flow,
        "strategy_effectiveness": strategy_eff,
        "overtrading_diagnostics": overtrading,
        "daily_operator_report": daily_operator,
        "incident_postmortem": incident,
        "market_context": market_context,
        "source_reports": {
            "trade_explain_json": str(trade_js),
            "trade_explain_md": str(trade_md),
            "operator_summary_json": str(op_js),
            "operator_summary_md": str(op_md),
            "decision_story_md": str(ds_md),
            "run_cards_md": str(rc_md),
            "decision_story_total": int(ds_obj.get("story_total") or 0),
            "run_card_total": int(rc_obj.get("card_total") or 0),
        },
    }

    js_path = report_dir / f"reporter_analysis_{target_day}.json"
    md_path = report_dir / f"reporter_analysis_{target_day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(out), encoding="utf-8")
    return md_path, js_path, out

