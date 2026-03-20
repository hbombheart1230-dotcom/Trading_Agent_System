from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.core.symbols import normalize_symbol


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


def _normalize_live_symbol(value: Any) -> str:
    return normalize_symbol(value, allow_test_symbols=False)


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
        d = _utc_day(row.get("ts"))
        if not d:
            continue
        if best is None or d > best:
            best = d
    return best


def _extract_news_items(news: Dict[str, Any], llm_ctx: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in ("headlines", "items", "news_items"):
        src = news.get(key)
        if src is None:
            src = llm_ctx.get(key)
        if isinstance(src, list):
            for it in src:
                if isinstance(it, str):
                    s = it.strip()
                    if s:
                        out.append(s)
                elif isinstance(it, dict):
                    title = str(it.get("title") or it.get("headline") or "").strip()
                    if title:
                        out.append(title)
    # Preserve order, remove duplicates.
    uniq: List[str] = []
    seen = set()
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def _extract_decision_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
    why = packet.get("why") if isinstance(packet.get("why"), dict) else {}
    llm_ctx = trace.get("llm_context") if isinstance(trace.get("llm_context"), dict) else {}

    technical = why.get("technical") if isinstance(why.get("technical"), dict) else {}
    if not technical:
        technical = llm_ctx.get("technical") if isinstance(llm_ctx.get("technical"), dict) else {}

    news = why.get("news") if isinstance(why.get("news"), dict) else {}
    if not news:
        news = llm_ctx.get("news") if isinstance(llm_ctx.get("news"), dict) else {}

    policy = why.get("policy") if isinstance(why.get("policy"), dict) else {}
    if not policy:
        policy = llm_ctx.get("decision_policy") if isinstance(llm_ctx.get("decision_policy"), dict) else {}

    decision_rationale = str(trace.get("rationale") or intent.get("rationale") or "").strip()
    decision_reason = str(intent.get("reason") or "").strip()

    return {
        "strategy": str(trace.get("strategy") or "").strip(),
        "decision_rationale": decision_rationale,
        "decision_reason": decision_reason,
        "intent_action": str(intent.get("action") or "").strip().upper(),
        "intent_symbol": _normalize_live_symbol(intent.get("symbol")),
        "intent_qty": _safe_int(intent.get("qty"), 0),
        "technical": technical if isinstance(technical, dict) else {},
        "news": news if isinstance(news, dict) else {},
        "policy": policy if isinstance(policy, dict) else {},
        "news_items": _extract_news_items(news if isinstance(news, dict) else {}, llm_ctx),
    }


def _run_context_default(run_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "strategist_llm": {},
        "decision": {},
        "scanner": {},
        "monitor": {},
        "verdict": {},
        "execution": {},
        "first_epoch": 0,
        "last_epoch": 0,
    }


def _build_run_contexts(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Counter]:
    by_run: Dict[str, Dict[str, Any]] = {}
    stage_counts: Counter = Counter()
    for row in rows:
        stage = str(row.get("stage") or "").strip()
        stage_counts[stage] += 1
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        ctx = by_run.setdefault(run_id, _run_context_default(run_id))
        epoch = _to_epoch(row.get("ts")) or 0
        if ctx["first_epoch"] <= 0 or epoch < int(ctx["first_epoch"]):
            ctx["first_epoch"] = epoch
        if epoch > int(ctx["last_epoch"]):
            ctx["last_epoch"] = epoch

        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "strategist_llm" and event == "result":
            ctx["strategist_llm"] = dict(payload)
        elif stage == "decision" and event == "trace":
            ctx["decision"] = _extract_decision_context(payload)
        elif stage == "scanner" and event == "summary":
            ctx["scanner"] = dict(payload)
        elif stage == "monitor" and event == "summary":
            ctx["monitor"] = dict(payload)
        elif stage == "execute_from_packet" and event == "verdict":
            ctx["verdict"] = dict(payload)
        elif stage == "execute_from_packet" and event == "execution":
            ctx["execution"] = dict(payload)
    return by_run, stage_counts


def _build_execution_rows(rows: List[Dict[str, Any]], by_run: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        if stage != "execute_from_packet" or event != "execution":
            continue
        run_id = str(row.get("run_id") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        action = str(order.get("action") or "").strip().upper()
        if action not in ("BUY", "SELL"):
            continue
        symbol = _normalize_live_symbol(order.get("symbol") or order.get("stk_cd"))
        qty = _safe_int(order.get("qty"), 0)
        if not symbol or qty <= 0:
            continue
        price = _safe_float(order.get("price"), 0.0)
        ts = str(row.get("ts") or "")
        epoch = _to_epoch(ts) or 0

        ctx = by_run.get(run_id) if isinstance(by_run.get(run_id), dict) else {}
        decision = ctx.get("decision") if isinstance(ctx.get("decision"), dict) else {}
        scanner = ctx.get("scanner") if isinstance(ctx.get("scanner"), dict) else {}
        monitor = ctx.get("monitor") if isinstance(ctx.get("monitor"), dict) else {}
        verdict = ctx.get("verdict") if isinstance(ctx.get("verdict"), dict) else {}
        strategist_llm = ctx.get("strategist_llm") if isinstance(ctx.get("strategist_llm"), dict) else {}

        news = decision.get("news") if isinstance(decision.get("news"), dict) else {}
        tech = decision.get("technical") if isinstance(decision.get("technical"), dict) else {}

        out.append(
            {
                "ts": ts,
                "epoch": int(epoch),
                "run_id": run_id,
                "symbol": symbol,
                "action": action,
                "qty": int(qty),
                "price": float(price),
                "order_type": str(order.get("order_type") or "").strip().lower(),
                "broker_code": str((payload.get("payload") or {}).get("broker_code") if isinstance(payload.get("payload"), dict) else ""),
                "broker_message": str((payload.get("payload") or {}).get("broker_message") if isinstance(payload.get("payload"), dict) else ""),
                "strategy": str(decision.get("strategy") or ""),
                "decision_rationale": str(decision.get("decision_rationale") or ""),
                "decision_reason": str(decision.get("decision_reason") or ""),
                "scanner_source": str(scanner.get("candidate_source") or ""),
                "scanner_top_stock": _normalize_live_symbol(scanner.get("top_stock")),
                "scanner_top_score": scanner.get("top_score"),
                "scanner_top_ranked_symbols": [
                    sym
                    for sym in (_normalize_live_symbol(x) for x in list(scanner.get("top_ranked_symbols") or []))
                    if sym
                ],
                "monitor_exit_reason": str(monitor.get("exit_reason") or ""),
                "monitor_reason": str(monitor.get("monitor_reason") or ""),
                "monitor_price_source": str(monitor.get("price_source") or ""),
                "monitor_price_source_policy": str(monitor.get("price_source_policy") or ""),
                "monitor_feature_source": str(monitor.get("feature_source") or ""),
                "guard_allowed": verdict.get("allowed"),
                "guard_reason": str(verdict.get("reason") or ""),
                "llm_provider": str(strategist_llm.get("provider") or ""),
                "llm_model": str(strategist_llm.get("model") or ""),
                "llm_ok": strategist_llm.get("ok"),
                "news_symbol_sentiment_score": news.get("symbol_sentiment_score"),
                "news_global_sentiment_score": news.get("global_sentiment_score"),
                "news_symbol_status": str(news.get("symbol_sentiment_status") or ""),
                "news_global_status": str(news.get("global_sentiment_status") or ""),
                "news_symbol_source": str(news.get("symbol_sentiment_source") or ""),
                "news_global_source": str(news.get("global_sentiment_source") or ""),
                "news_items": list(decision.get("news_items") or []),
                "signal_score": tech.get("signal_score"),
                "rsi14": tech.get("rsi14"),
                "ma20_gap": tech.get("ma20_gap"),
                "volatility20": tech.get("volatility20"),
                "composite_score": tech.get("composite_score"),
            }
        )
    out.sort(key=lambda x: int(x.get("epoch") or 0))
    return out


def _build_sell_pairs_fifo(executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    open_lots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    pairs: List[Dict[str, Any]] = []
    for row in executions:
        action = str(row.get("action") or "").upper()
        symbol = str(row.get("symbol") or "")
        qty = max(0, _safe_int(row.get("qty"), 0))
        price = _safe_float(row.get("price"), 0.0)
        if not symbol or qty <= 0:
            continue
        if action == "BUY":
            open_lots[symbol].append(
                {
                    "qty": qty,
                    "price": price,
                    "epoch": _safe_int(row.get("epoch"), 0),
                    "run_id": str(row.get("run_id") or ""),
                }
            )
            continue
        if action != "SELL":
            continue

        remain = qty
        matched_qty = 0
        realized_est = 0.0
        total_entry = 0.0
        weighted_hold = 0.0
        matched_buy_runs: List[str] = []
        while remain > 0 and open_lots.get(symbol):
            lot = open_lots[symbol][0]
            lot_qty = max(0, _safe_int(lot.get("qty"), 0))
            if lot_qty <= 0:
                open_lots[symbol].pop(0)
                continue
            take = min(remain, lot_qty)
            entry_px = _safe_float(lot.get("price"), 0.0)
            sell_px = _safe_float(row.get("price"), 0.0)
            realized_est += (sell_px - entry_px) * float(take)
            total_entry += entry_px * float(take)
            matched_qty += int(take)
            hold_sec = max(0, _safe_int(row.get("epoch"), 0) - _safe_int(lot.get("epoch"), 0))
            weighted_hold += float(hold_sec * take)
            buy_run_id = str(lot.get("run_id") or "")
            if buy_run_id:
                matched_buy_runs.append(buy_run_id)
            remain -= int(take)
            lot["qty"] = lot_qty - int(take)
            if _safe_int(lot.get("qty"), 0) <= 0:
                open_lots[symbol].pop(0)

        avg_entry = (total_entry / float(matched_qty)) if matched_qty > 0 else 0.0
        avg_hold_sec = (weighted_hold / float(matched_qty)) if matched_qty > 0 else 0.0
        pairs.append(
            {
                "sell_run_id": str(row.get("run_id") or ""),
                "sell_ts": str(row.get("ts") or ""),
                "symbol": symbol,
                "sell_qty": int(qty),
                "matched_qty": int(matched_qty),
                "unmatched_qty": int(max(0, remain)),
                "sell_price": _safe_float(row.get("price"), 0.0),
                "avg_entry_price": float(round(avg_entry, 4)),
                "hold_duration_sec_avg": int(round(avg_hold_sec)),
                "estimated_realized_pnl": float(round(realized_est, 4)),
                "decision_rationale": str(row.get("decision_rationale") or ""),
                "decision_reason": str(row.get("decision_reason") or ""),
                "strategy": str(row.get("strategy") or ""),
                "monitor_exit_reason": str(row.get("monitor_exit_reason") or ""),
                "monitor_reason": str(row.get("monitor_reason") or ""),
                "monitor_price_source": str(row.get("monitor_price_source") or ""),
                "monitor_price_source_policy": str(row.get("monitor_price_source_policy") or ""),
                "monitor_feature_source": str(row.get("monitor_feature_source") or ""),
                "scanner_source": str(row.get("scanner_source") or ""),
                "scanner_top_stock": str(row.get("scanner_top_stock") or ""),
                "scanner_top_score": row.get("scanner_top_score"),
                "scanner_top_ranked_symbols": list(row.get("scanner_top_ranked_symbols") or []),
                "news_symbol_sentiment_score": row.get("news_symbol_sentiment_score"),
                "news_global_sentiment_score": row.get("news_global_sentiment_score"),
                "news_symbol_status": str(row.get("news_symbol_status") or ""),
                "news_global_status": str(row.get("news_global_status") or ""),
                "signal_score": row.get("signal_score"),
                "rsi14": row.get("rsi14"),
                "ma20_gap": row.get("ma20_gap"),
                "volatility20": row.get("volatility20"),
                "composite_score": row.get("composite_score"),
                "matched_buy_run_ids": matched_buy_runs,
            }
        )
    return pairs


def _report_inventory(day: str, reports_root: Path) -> List[str]:
    candidates = [
        reports_root / "daily" / day / "operator_summary.md",
        reports_root / "operator_summary" / f"operator_summary_{day}.md",
        reports_root / "decision_story" / f"decision_story_{day}.md",
        reports_root / "run_cards" / f"run_cards_{day}.md",
        reports_root / "metrics" / f"metrics_{day}.md",
        reports_root / "daily" / day / "daily_report.md",
        reports_root / "daily" / f"daily_{day}.md",
        reports_root / "live_watch" / "live_watch_latest.md",
    ]
    out: List[str] = []
    for p in candidates:
        if p.exists():
            out.append(str(p))
    return out


def _to_markdown(
    *,
    day: str,
    event_log_path: Path,
    execution_summary: Dict[str, Any],
    agent_activity: Dict[str, Any],
    sell_pairs: List[Dict[str, Any]],
    executions: List[Dict[str, Any]],
    report_inventory: List[str],
    data_gaps: Dict[str, Any],
) -> str:
    lines: List[str] = []
    lines.append(f"# Trade Explain Report ({day})")
    lines.append("")
    lines.append(f"- event_log_path: `{event_log_path}`")
    lines.append(f"- executions_total: **{int(execution_summary.get('executions_total') or 0)}**")
    lines.append(f"- sell_pairs_total: **{int(execution_summary.get('sell_pairs_total') or 0)}**")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- symbols_executed: `{execution_summary.get('symbols_executed') or []}`")
    lines.append(f"- action_counts: `{execution_summary.get('action_counts') or {}}`")
    lines.append(f"- symbol_side_counts: `{execution_summary.get('symbol_side_counts') or {}}`")
    lines.append(f"- short_holds_lt_120s: **{int(execution_summary.get('short_holds_lt_120s') or 0)}**")
    lines.append("")
    lines.append("## Agent Activity Snapshot")
    lines.append("")
    stage_counts = agent_activity.get("stage_counts") if isinstance(agent_activity.get("stage_counts"), dict) else {}
    for stage, cnt in stage_counts.items():
        lines.append(f"- `{stage}`: {int(cnt)}")
    lines.append("")
    lines.append("## Report Inventory")
    lines.append("")
    if report_inventory:
        for path in report_inventory:
            lines.append(f"- `{path}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Execution Timeline (Latest)")
    lines.append("")
    if not executions:
        lines.append("No execution rows found.")
    else:
        lines.append("| ts | run_id | symbol | action | qty | price | strategy | reason |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | --- | --- |")
        for row in executions:
            lines.append(
                "| {ts} | `{run_id}` | {symbol} | {action} | {qty} | {price} | {strategy} | {reason} |".format(
                    ts=str(row.get("ts") or ""),
                    run_id=str(row.get("run_id") or ""),
                    symbol=str(row.get("symbol") or ""),
                    action=str(row.get("action") or ""),
                    qty=int(_safe_int(row.get("qty"), 0)),
                    price=round(_safe_float(row.get("price"), 0.0), 4),
                    strategy=str(row.get("strategy") or "-"),
                    reason=str(row.get("decision_rationale") or row.get("decision_reason") or "-"),
                )
            )
    lines.append("")
    lines.append("## Sell Pair Analysis (FIFO, Latest)")
    lines.append("")
    if not sell_pairs:
        lines.append("No SELL pairs found.")
    else:
        for pair in sell_pairs:
            lines.append(f"### SELL `{pair.get('sell_run_id')}` / {pair.get('symbol')}")
            lines.append(f"- sell_ts: {pair.get('sell_ts')}")
            lines.append(
                f"- qty: sell={int(pair.get('sell_qty') or 0)}, matched={int(pair.get('matched_qty') or 0)}, unmatched={int(pair.get('unmatched_qty') or 0)}"
            )
            lines.append(
                f"- hold_duration_sec_avg: **{int(pair.get('hold_duration_sec_avg') or 0)}** / estimated_realized_pnl: **{round(_safe_float(pair.get('estimated_realized_pnl'), 0.0), 4)}**"
            )
            lines.append(
                f"- entry_vs_exit_price: entry_avg={round(_safe_float(pair.get('avg_entry_price'), 0.0), 4)}, exit={round(_safe_float(pair.get('sell_price'), 0.0), 4)}"
            )
            lines.append(f"- strategy: {pair.get('strategy') or '-'}")
            lines.append(f"- sell_reason: {pair.get('decision_rationale') or pair.get('decision_reason') or '-'}")
            lines.append(
                f"- scanner_context: source={pair.get('scanner_source') or '-'}, top_stock={pair.get('scanner_top_stock') or '-'}, top_score={pair.get('scanner_top_score')}"
            )
            lines.append(
                f"- sentiment_context: symbol={pair.get('news_symbol_sentiment_score')}, global={pair.get('news_global_sentiment_score')}, status=({pair.get('news_symbol_status') or '-'}, {pair.get('news_global_status') or '-'})"
            )
            lines.append(
                f"- technical_context: signal_score={pair.get('signal_score')}, rsi14={pair.get('rsi14')}, ma20_gap={pair.get('ma20_gap')}, volatility20={pair.get('volatility20')}, composite={pair.get('composite_score')}"
            )
            lines.append(
                f"- monitor_context: exit_reason={pair.get('monitor_exit_reason') or '-'}, "
                f"monitor_reason={pair.get('monitor_reason') or '-'}, "
                f"price_source={pair.get('monitor_price_source') or '-'}, "
                f"feature_source={pair.get('monitor_feature_source') or '-'}"
            )
            if pair.get("monitor_price_source_policy"):
                lines.append(f"- monitor_price_policy: {pair.get('monitor_price_source_policy')}")
            lines.append(f"- matched_buy_runs: `{pair.get('matched_buy_run_ids') or []}`")
            lines.append("")
    lines.append("## Data Gaps")
    lines.append("")
    for k, v in data_gaps.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines).rstrip() + "\n"


def generate_trade_explain_report(
    event_log_path: Path,
    report_dir: Path,
    *,
    day: Optional[str] = None,
    max_executions: int = 120,
    max_sell_pairs: int = 120,
) -> Tuple[Path, Path, Dict[str, Any]]:
    selected_day = str(day or "").strip() or (_latest_day(event_log_path) or "")
    report_dir.mkdir(parents=True, exist_ok=True)

    if not selected_day:
        out = {
            "schema_version": "trade_explain.v1",
            "day": "",
            "event_log_path": str(event_log_path),
            "executions_total": 0,
            "sell_pairs_total": 0,
            "report_json_path": "",
            "report_md_path": "",
            "error": "no_day_detected_from_event_log",
        }
        js_path = report_dir / "trade_explain_unknown.json"
        md_path = report_dir / "trade_explain_unknown.md"
        js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text("# Trade Explain Report\n\nNo day detected from event log.\n", encoding="utf-8")
        out["report_json_path"] = str(js_path)
        out["report_md_path"] = str(md_path)
        return md_path, js_path, out

    day_rows: List[Dict[str, Any]] = []
    for row in _iter_jsonl(event_log_path):
        if _utc_day(row.get("ts")) != selected_day:
            continue
        day_rows.append(row)

    by_run, stage_counts = _build_run_contexts(day_rows)
    execution_rows = _build_execution_rows(day_rows, by_run)
    sell_pairs = _build_sell_pairs_fifo(execution_rows)

    action_counts: Counter = Counter()
    symbol_side_counts: Counter = Counter()
    symbols = set()
    for row in execution_rows:
        action = str(row.get("action") or "").upper()
        symbol = str(row.get("symbol") or "")
        action_counts[action] += 1
        symbol_side_counts[f"{symbol}:{action}"] += 1
        if symbol:
            symbols.add(symbol)

    short_holds = 0
    for pair in sell_pairs:
        if _safe_int(pair.get("hold_duration_sec_avg"), 0) < 120:
            short_holds += 1

    scanner_score_breakdown_missing_total = 0
    news_items_missing_total = 0
    for row in execution_rows:
        top_ranked = row.get("scanner_top_ranked_symbols")
        # Scanner summary currently logs symbols and top score but not per-candidate score_breakdown.
        if not top_ranked:
            scanner_score_breakdown_missing_total += 1
        news_items = row.get("news_items") if isinstance(row.get("news_items"), list) else []
        if not news_items:
            news_items_missing_total += 1

    reports_root = report_dir.parent if report_dir.name else report_dir
    inventory = _report_inventory(selected_day, reports_root)

    execution_tail = execution_rows[-max(1, int(max_executions)) :]
    pair_tail = sell_pairs[-max(1, int(max_sell_pairs)) :]

    execution_summary = {
        "executions_total": int(len(execution_rows)),
        "sell_pairs_total": int(len(sell_pairs)),
        "symbols_executed": sorted(symbols),
        "action_counts": dict(action_counts),
        "symbol_side_counts": dict(symbol_side_counts),
        "short_holds_lt_120s": int(short_holds),
    }
    agent_activity = {
        "stage_counts": dict(stage_counts),
    }
    data_gaps = {
        "scanner_score_breakdown_missing_total": int(scanner_score_breakdown_missing_total),
        "news_items_missing_total": int(news_items_missing_total),
        "note": "news headline text and scanner score_breakdown are limited by current event-log payload policy.",
    }

    out: Dict[str, Any] = {
        "schema_version": "trade_explain.v1",
        "day": selected_day,
        "event_log_path": str(event_log_path),
        "execution_summary": execution_summary,
        "agent_activity": agent_activity,
        "report_inventory": inventory,
        "executions": execution_tail,
        "sell_pairs": pair_tail,
        "data_gaps": data_gaps,
    }

    js_path = report_dir / f"trade_explain_{selected_day}.json"
    md_path = report_dir / f"trade_explain_{selected_day}.md"

    md_body = _to_markdown(
        day=selected_day,
        event_log_path=event_log_path,
        execution_summary=execution_summary,
        agent_activity=agent_activity,
        sell_pairs=pair_tail,
        executions=execution_tail,
        report_inventory=inventory,
        data_gaps=data_gaps,
    )

    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md_body, encoding="utf-8")
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path, out
