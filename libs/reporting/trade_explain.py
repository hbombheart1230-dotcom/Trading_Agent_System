from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.core.symbols import normalize_symbol
from libs.reporting.narrative_axes import build_narrative_explanation, narrative_axis_policy
from libs.reporting.report_metadata import (
    build_data_freshness,
    build_route_provenance,
    render_data_freshness_markdown,
)
from libs.reporting.report_source_helpers import (
    build_commander_route_summary,
    epoch_to_iso,
    utc_now_iso,
)

OFFICIAL_TRADE_EXPLAIN_RELATIVE_DIR = Path("dev") / "analysis" / "trade_explain"
OFFICIAL_TRADE_EXPLAIN_REPORT_DIR = (Path("reports") / OFFICIAL_TRADE_EXPLAIN_RELATIVE_DIR).as_posix()


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


def _canonical_report_root(report_dir: Path) -> Path:
    for candidate in (report_dir, *report_dir.parents):
        if candidate.name == "reports":
            return candidate
    if report_dir.name in {"trade_explain", "daily", "metrics", "run_cards", "decision_story", "operator_summary"}:
        return report_dir.parent
    return report_dir


def official_trade_explain_report_dir(reports_root: Path) -> Path:
    return Path(reports_root) / OFFICIAL_TRADE_EXPLAIN_RELATIVE_DIR


def build_trade_explain_output_path_metadata(report_dir: Path) -> Dict[str, Any]:
    canonical_reports_root = _canonical_report_root(report_dir)
    requested_dir = Path(report_dir)
    official_dir = official_trade_explain_report_dir(canonical_reports_root)
    is_official = requested_dir == official_dir
    return {
        "official_report_dir": str(official_dir),
        "requested_report_dir": str(requested_dir),
        "path_status": "official" if is_official else "custom_nonofficial",
        "deprecated_note": ""
        if is_official
        else f"Official trade_explain path is `{official_dir}`; custom output path is supported but non-canonical.",
    }


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
        "strategist_policy_resolution": {},
        "decision": {},
        "scanner": {},
        "monitor": {},
        "monitor_entry": {},
        "commander_route": {},
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
        elif stage == "strategist" and event == "policy_resolution":
            ctx["strategist_policy_resolution"] = dict(payload)
        elif stage == "decision" and event == "trace":
            ctx["decision"] = _extract_decision_context(payload)
        elif stage == "scanner" and event == "summary":
            ctx["scanner"] = dict(payload)
        elif stage == "scanner" and event == "candidate_selection_reason":
            scanner = ctx.get("scanner") if isinstance(ctx.get("scanner"), dict) else {}
            ctx["scanner"] = {**dict(scanner), **dict(payload)}
        elif stage == "monitor" and event == "summary":
            ctx["monitor"] = dict(payload)
        elif stage == "monitor" and event == "entry_decision_detail":
            ctx["monitor_entry"] = dict(payload)
        elif stage == "execute_from_packet" and event == "verdict":
            ctx["verdict"] = dict(payload)
        elif stage == "execute_from_packet" and event == "execution":
            ctx["execution"] = dict(payload)
        elif stage == "commander_router" and event in {"route_selected", "end"}:
            existing = ctx.get("commander_route") if isinstance(ctx.get("commander_route"), dict) else {}
            merged = {**dict(existing), **dict(payload)}
            route_obs = payload.get("route_observability") if isinstance(payload.get("route_observability"), dict) else {}
            if route_obs:
                merged.update(dict(route_obs))
            ctx["commander_route"] = merged
    return by_run, stage_counts


def _apply_commander_route_overlay(
    by_run: Dict[str, Dict[str, Any]],
    route_summary: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    route_by_run = route_summary.get("by_run") if isinstance(route_summary.get("by_run"), dict) else {}
    if not route_by_run:
        return by_run
    for run_id, route_row in route_by_run.items():
        if not isinstance(route_row, dict):
            continue
        ctx = by_run.setdefault(run_id, _run_context_default(run_id))
        existing = ctx.get("commander_route") if isinstance(ctx.get("commander_route"), dict) else {}
        ctx["commander_route"] = {**dict(existing), **dict(route_row)}
    return by_run


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
        monitor_entry = ctx.get("monitor_entry") if isinstance(ctx.get("monitor_entry"), dict) else {}
        verdict = ctx.get("verdict") if isinstance(ctx.get("verdict"), dict) else {}
        strategist_llm = ctx.get("strategist_llm") if isinstance(ctx.get("strategist_llm"), dict) else {}
        strategist_policy_resolution = ctx.get("strategist_policy_resolution") if isinstance(ctx.get("strategist_policy_resolution"), dict) else {}
        commander_route = ctx.get("commander_route") if isinstance(ctx.get("commander_route"), dict) else {}

        news = decision.get("news") if isinstance(decision.get("news"), dict) else {}
        tech = decision.get("technical") if isinstance(decision.get("technical"), dict) else {}
        narrative = build_narrative_explanation(
            action=action,
            decision_rationale=decision.get("decision_rationale"),
            decision_reason=decision.get("decision_reason"),
            key_reason=decision.get("decision_reason"),
            entry_reason=monitor.get("monitor_reason") if action == "BUY" else "",
            dominant_blocker=((monitor_entry.get("no_trade_surface") if isinstance(monitor_entry.get("no_trade_surface"), dict) else {}) or {}).get("dominant_blocker"),
            exit_reason=monitor.get("exit_reason") if action == "SELL" else "",
            exit_monitor_reason=monitor.get("monitor_reason") if action == "SELL" else "",
        )

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
                "scanner_vs_monitor_alignment": str((((monitor_entry.get("scanner_monitor_handoff") if isinstance(monitor_entry.get("scanner_monitor_handoff"), dict) else {}) or {}).get("scanner_vs_monitor_alignment")) or ""),
                "monitor_exit_reason": str(monitor.get("exit_reason") or ""),
                "monitor_reason": str(monitor.get("monitor_reason") or ""),
                "monitor_dominant_blocker": str((((monitor_entry.get("no_trade_surface") if isinstance(monitor_entry.get("no_trade_surface"), dict) else {}) or {}).get("dominant_blocker")) or ""),
                "monitor_price_source": str(monitor.get("price_source") or ""),
                "monitor_price_source_policy": str(monitor.get("price_source_policy") or ""),
                "monitor_feature_source": str(monitor.get("feature_source") or ""),
                "guard_allowed": verdict.get("allowed"),
                "guard_reason": str(verdict.get("reason") or ""),
                "llm_provider": str(strategist_llm.get("provider") or ""),
                "llm_model": str(strategist_llm.get("model") or ""),
                "llm_ok": strategist_llm.get("ok"),
                "strategist_mode": str(
                    commander_route.get("strategy_generation_mode")
                    or strategist_policy_resolution.get("strategy_generation_mode")
                    or ""
                ),
                "strategist_fallback_used": bool(strategist_policy_resolution.get("fallback_used")),
                "route_selected": str(commander_route.get("route_selected") or ""),
                "route_source": str(commander_route.get("route_source") or "unavailable"),
                "decision_axis": str(narrative.get("decision_axis") or "unknown"),
                "primary_explanation": str(narrative.get("primary_explanation") or "-"),
                "entry_narrative": str(narrative.get("entry_narrative") or "-"),
                "exit_narrative": str(narrative.get("exit_narrative") or "-"),
                "why_not_buy_summary": str(narrative.get("why_not_buy_summary") or "-"),
                "why_exit_summary": str(narrative.get("why_exit_summary") or "-"),
                "narrative_order": list(narrative.get("narrative_order") or []),
                "narrative_order_text": str(narrative.get("narrative_order_text") or "-"),
                "narrative_consistency_flag": bool(narrative.get("narrative_consistency_flag")),
                "entry_context_blocker": str(narrative.get("entry_context_blocker") or "-"),
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
        narrative = build_narrative_explanation(
            action="SELL",
            decision_rationale=row.get("decision_rationale"),
            decision_reason=row.get("decision_reason"),
            key_reason=row.get("decision_reason") or row.get("monitor_exit_reason"),
            exit_reason=row.get("monitor_exit_reason"),
            exit_monitor_reason=row.get("monitor_reason"),
            dominant_blocker=row.get("monitor_dominant_blocker"),
        )
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
                "route_selected": str(row.get("route_selected") or ""),
                "route_source": str(row.get("route_source") or "unavailable"),
                "strategist_mode": str(row.get("strategist_mode") or ""),
                "decision_axis": str(narrative.get("decision_axis") or "unknown"),
                "primary_explanation": str(narrative.get("primary_explanation") or "-"),
                "entry_narrative": str(narrative.get("entry_narrative") or "-"),
                "exit_narrative": str(narrative.get("exit_narrative") or "-"),
                "why_not_buy_summary": str(narrative.get("why_not_buy_summary") or "-"),
                "why_exit_summary": str(narrative.get("why_exit_summary") or "-"),
                "narrative_order": list(narrative.get("narrative_order") or []),
                "narrative_order_text": str(narrative.get("narrative_order_text") or "-"),
                "narrative_consistency_flag": bool(narrative.get("narrative_consistency_flag")),
                "entry_context_blocker": str(narrative.get("entry_context_blocker") or "-"),
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
    route_summary: Dict[str, Any],
    freshness: Dict[str, Any],
    data_freshness: Dict[str, Any],
    route_provenance: Dict[str, Any],
    output_path_policy: Dict[str, Any],
    execution_summary: Dict[str, Any],
    agent_activity: Dict[str, Any],
    sell_pairs: List[Dict[str, Any]],
    executions: List[Dict[str, Any]],
    report_inventory: List[str],
    no_trade_summary: Dict[str, Any],
    data_gaps: Dict[str, Any],
) -> str:
    lines: List[str] = []
    lines.append(f"# Trade Explain Report ({day})")
    lines.append("")
    lines.append(f"- event_log_path: `{event_log_path}`")
    lines.append(f"- narrative_policy: exit-first for SELL/EXIT, entry-first for BUY/WAIT/NO_TRADE")
    lines.append("")
    lines += render_data_freshness_markdown(data_freshness)
    lines += [
        "",
        "## Output Path Policy",
        "",
        f"- official_report_dir: `{output_path_policy.get('official_report_dir') or ''}`",
        f"- requested_report_dir: `{output_path_policy.get('requested_report_dir') or ''}`",
        f"- path_status: `{output_path_policy.get('path_status') or 'unknown'}`",
        f"- note: {output_path_policy.get('deprecated_note') or 'requested path is canonical'}",
        "",
        "## Route Provenance",
        "",
        f"- route_source: `{route_provenance.get('route_source') or 'unavailable'}`",
        f"- route_source_run_count: **{int(route_provenance.get('route_source_run_count') or 0)}**",
        f"- route_source_missing_count: **{int(route_provenance.get('route_source_missing_count') or 0)}**",
        f"- route_source_breakdown: `{route_provenance.get('route_source_breakdown') or {}}`",
        "",
    ]
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- executions_total: **{int(execution_summary.get('executions_total') or 0)}**")
    lines.append(f"- sell_pairs_total: **{int(execution_summary.get('sell_pairs_total') or 0)}**")
    lines.append(f"- symbols_executed: `{execution_summary.get('symbols_executed') or []}`")
    lines.append(f"- action_counts: `{execution_summary.get('action_counts') or {}}`")
    lines.append(f"- symbol_side_counts: `{execution_summary.get('symbol_side_counts') or {}}`")
    lines.append(f"- short_holds_lt_120s: **{int(execution_summary.get('short_holds_lt_120s') or 0)}**")
    lines.append("")
    lines.append("## Route Summary")
    lines.append("")
    lines.append(f"- route_source: `{route_summary.get('route_source') or 'unavailable'}`")
    lines.append(f"- route_source_run_count: **{int(route_summary.get('route_source_run_count') or 0)}**")
    lines.append(f"- route_source_missing_count: **{int(route_summary.get('route_source_missing_count') or 0)}**")
    lines.append(f"- route_source_breakdown: `{route_summary.get('route_source_breakdown') or {}}`")
    lines.append(f"- route_selected_total: `{route_summary.get('route_selected_total') or {}}`")
    lines.append(f"- strategy_generation_mode_total: `{route_summary.get('strategy_generation_mode_total') or {}}`")
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
    lines.append("## No-Trade Summary")
    lines.append("")
    lines.append(f"- no_trade_runs_total: **{int(no_trade_summary.get('no_trade_runs_total') or 0)}**")
    lines.append(f"- near_ready_runs_total: **{int(no_trade_summary.get('near_ready_runs_total') or 0)}**")
    lines.append(f"- strategist_fallback_total: **{int(no_trade_summary.get('strategist_fallback_total') or 0)}**")
    lines.append(f"- route_selected_total: `{no_trade_summary.get('route_selected_total') or {}}`")
    lines.append(f"- scanner_monitor_mismatch_total: **{int(no_trade_summary.get('scanner_monitor_mismatch_total') or 0)}**")
    lines.append(f"- dominant_blocker_topN: `{no_trade_summary.get('dominant_blocker_topN') or []}`")
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
                    reason=str(row.get("primary_explanation") or "-"),
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
            lines.append(f"- decision_axis: {pair.get('decision_axis') or '-'}")
            lines.append(f"- primary_explanation: {pair.get('primary_explanation') or '-'}")
            lines.append(f"- narrative_order: {pair.get('narrative_order_text') or '-'}")
            lines.append(f"- narrative_consistency_flag: {bool(pair.get('narrative_consistency_flag'))}")
            lines.append(f"- strategy: {pair.get('strategy') or '-'}")
            lines.append(f"- sell_reason: {pair.get('decision_rationale') or pair.get('decision_reason') or '-'}")
            lines.append(f"- entry_narrative: {pair.get('entry_narrative') or '-'}")
            lines.append(f"- exit_narrative: {pair.get('exit_narrative') or '-'}")
            lines.append(f"- entry_context_blocker: {pair.get('entry_context_blocker') or '-'}")
            lines.append(
                f"- scanner_context: source={pair.get('scanner_source') or '-'}, top_stock={pair.get('scanner_top_stock') or '-'}, top_score={pair.get('scanner_top_score')}"
            )
            lines.append(
                f"- commander_route: route={pair.get('route_selected') or '-'}, source={pair.get('route_source') or 'unavailable'}, strategist_mode={pair.get('strategist_mode') or '-'}"
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
    output_path_policy = build_trade_explain_output_path_metadata(report_dir)

    if not selected_day:
        out = {
            "schema_version": "trade_explain.v1",
            "day": "",
            "event_log_path": str(event_log_path),
            "output_path_policy": output_path_policy,
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

    canonical_report_root = _canonical_report_root(report_dir)
    route_summary = build_commander_route_summary(
        reports_root=canonical_report_root,
        day=selected_day,
        day_rows=day_rows,
    )
    by_run, stage_counts = _build_run_contexts(day_rows)
    by_run = _apply_commander_route_overlay(by_run, route_summary)
    execution_rows = _build_execution_rows(day_rows, by_run)
    sell_pairs = _build_sell_pairs_fifo(execution_rows)
    latest_row: Dict[str, Any] | None = None
    latest_epoch = 0
    run_ids = {str(r.get("run_id") or "").strip() for r in day_rows if str(r.get("run_id") or "").strip()}
    for row in day_rows:
        epoch = _to_epoch(row.get("ts")) or 0
        if epoch >= latest_epoch:
            latest_epoch = epoch
            latest_row = row

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
    no_trade_runs_total = 0
    near_ready_runs_total = 0
    strategist_fallback_total = 0
    route_selected_total: Counter[str] = Counter()
    scanner_monitor_mismatch_total = 0
    dominant_blocker_total: Counter[str] = Counter()
    for ctx in by_run.values():
        if not isinstance(ctx, dict):
            continue
        execution = ctx.get("execution") if isinstance(ctx.get("execution"), dict) else {}
        if execution:
            pass
        monitor_entry = ctx.get("monitor_entry") if isinstance(ctx.get("monitor_entry"), dict) else {}
        no_trade = monitor_entry.get("no_trade_surface") if isinstance(monitor_entry.get("no_trade_surface"), dict) else {}
        handoff = monitor_entry.get("scanner_monitor_handoff") if isinstance(monitor_entry.get("scanner_monitor_handoff"), dict) else {}
        strategist_resolution = ctx.get("strategist_policy_resolution") if isinstance(ctx.get("strategist_policy_resolution"), dict) else {}
        commander_route = ctx.get("commander_route") if isinstance(ctx.get("commander_route"), dict) else {}
        route_selected = str(commander_route.get("route_selected") or "").strip()
        if route_selected:
            route_selected_total[route_selected] += 1
        if bool(commander_route.get("strategist_fallback_used")) or bool(strategist_resolution.get("fallback_used")):
            strategist_fallback_total += 1
        if handoff and str(handoff.get("scanner_vs_monitor_alignment") or "").strip() in {"mismatch", "partial_mismatch", "guard_block"}:
            scanner_monitor_mismatch_total += 1
        if no_trade and str(no_trade.get("no_trade_stage") or "").strip() in {"guard_block", "pre_intent_wait", "pre_intent_noop"} and not execution:
            no_trade_runs_total += 1
            if bool(no_trade.get("near_ready_flag")):
                near_ready_runs_total += 1
            dominant_blocker = str(no_trade.get("dominant_blocker") or no_trade.get("no_trade_reason_code") or "").strip()
            if dominant_blocker:
                dominant_blocker_total[dominant_blocker] += 1
    no_trade_summary = {
        "no_trade_runs_total": int(no_trade_runs_total),
        "dominant_blocker_topN": [
            {"reason": str(reason), "count": int(cnt)}
            for reason, cnt in dominant_blocker_total.most_common(5)
        ],
        "near_ready_runs_total": int(near_ready_runs_total),
        "strategist_fallback_total": int(route_summary.get("strategist_fallback_total") or strategist_fallback_total),
        "route_selected_total": dict(route_summary.get("route_selected_total") or route_selected_total),
        "route_source": str(route_summary.get("route_source") or "unavailable"),
        "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
        "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
        "route_source_breakdown": dict(route_summary.get("route_source_breakdown") or {}),
        "scanner_monitor_mismatch_total": int(scanner_monitor_mismatch_total),
    }
    freshness = {
        "generated_at": utc_now_iso(),
        "source_run_count": int(len(run_ids)),
        "latest_run_id": str((latest_row or {}).get("run_id") or ""),
        "latest_run_ts": epoch_to_iso(latest_epoch),
    }
    data_freshness = build_data_freshness(
        generated_at=freshness["generated_at"],
        source_run_count=freshness["source_run_count"],
        latest_run_id=freshness["latest_run_id"],
        latest_run_ts=freshness["latest_run_ts"],
        stale=False,
    )
    route_provenance = build_route_provenance(route_summary)

    out: Dict[str, Any] = {
        "schema_version": "trade_explain.v1",
        "day": selected_day,
        "event_log_path": str(event_log_path),
        "generated_at": freshness["generated_at"],
        "source_run_count": freshness["source_run_count"],
        "latest_run_id": freshness["latest_run_id"],
        "latest_run_ts": freshness["latest_run_ts"],
        "data_freshness": data_freshness,
        "route_provenance": route_provenance,
        "narrative_axis_policy": narrative_axis_policy(),
        "output_path_policy": output_path_policy,
        "route_summary": {
            "route_source": str(route_summary.get("route_source") or "unavailable"),
            "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
            "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
            "route_source_breakdown": dict(route_summary.get("route_source_breakdown") or {}),
            "route_selected_total": dict(route_summary.get("route_selected_total") or {}),
            "strategy_generation_mode_total": dict(route_summary.get("strategy_generation_mode_total") or {}),
            "strategist_fallback_total": int(route_summary.get("strategist_fallback_total") or 0),
        },
        "route_source": str(route_summary.get("route_source") or "unavailable"),
        "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
        "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
        "execution_summary": execution_summary,
        "agent_activity": agent_activity,
        "report_inventory": inventory,
        "executions": execution_tail,
        "sell_pairs": pair_tail,
        "no_trade_summary": no_trade_summary,
        "data_gaps": data_gaps,
    }

    js_path = report_dir / f"trade_explain_{selected_day}.json"
    md_path = report_dir / f"trade_explain_{selected_day}.md"

    md_body = _to_markdown(
        day=selected_day,
        event_log_path=event_log_path,
        route_summary=out["route_summary"],
        freshness=freshness,
        data_freshness=data_freshness,
        route_provenance=route_provenance,
        output_path_policy=output_path_policy,
        execution_summary=execution_summary,
        agent_activity=agent_activity,
        sell_pairs=pair_tail,
        executions=execution_tail,
        report_inventory=inventory,
        no_trade_summary=no_trade_summary,
        data_gaps=data_gaps,
    )

    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md_body, encoding="utf-8")
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path, out
