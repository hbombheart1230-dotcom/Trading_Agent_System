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
from .reporter_ai_review import build_ai_reporter_review
from .trade_explain import generate_trade_explain_report
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input


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


def _decision_trace_agent_payload(row: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Return (agent, payload) from `stage=decision_trace` rows.

    Expected event payload shape:
    {
      "agent": "strategist|scanner|monitor|supervisor|executor",
      "payload": {...}
    }
    """
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    agent = str(payload.get("agent") or "").strip().lower()
    agent_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    return agent, dict(agent_payload or {})


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
    report_focus_counts: Counter[str] = Counter()
    scanner_priority_counts: Counter[str] = Counter()

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
        if stage == "strategist" and event == "summary":
            v_themes = payload.get("themes")
            if isinstance(v_themes, list):
                for item in v_themes:
                    t = str(item or "").strip().lower()
                    if t:
                        theme_counts[t] += 1
            v_report_focus = payload.get("report_focus")
            if isinstance(v_report_focus, list):
                for item in v_report_focus:
                    f = str(item or "").strip()
                    if f:
                        report_focus_counts[f] += 1
            v_priority = payload.get("scanner_priority")
            if isinstance(v_priority, list):
                for item in v_priority:
                    p = str(item or "").strip().lower()
                    if p:
                        scanner_priority_counts[p] += 1
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
    focus_line = (
        f"Reporter focus priority: {report_focus_counts.most_common(1)[0][0]}"
        if report_focus_counts
        else "Reporter focus guidance was limited."
    )

    return {
        "theme_counts": dict(theme_counts.most_common(10)),
        "scanner_top_stock_counts": dict(scanner_top_counts.most_common(10)),
        "strategy_counts": dict(strategy_counts.most_common(10)),
        "monitor_exit_reason_counts": dict(exit_reason_counts.most_common(10)),
        "scanner_priority_counts": dict(scanner_priority_counts.most_common(10)),
        "report_focus_counts": dict(report_focus_counts.most_common(10)),
        "narrative": [strategy_line, scanner_line, monitor_line, focus_line],
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
    day_rows: List[Dict[str, Any]],
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

    execution_anomaly_total = 0
    for row in day_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "execute_from_packet" and event == "execution":
            if payload.get("ok") is False:
                execution_anomaly_total += 1
                continue
            px = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            broker_code = str(px.get("broker_code") or "").strip()
            if broker_code and broker_code != "0":
                execution_anomaly_total += 1
                continue
        if stage == "decision_trace" and event == "result":
            agent, ap = _decision_trace_agent_payload(row)
            if agent != "executor":
                continue
            if bool(ap.get("execution_attempted")) and str(ap.get("fill_status_summary") or "").strip().lower() in (
                "failed",
                "rejected",
                "error",
            ):
                execution_anomaly_total += 1

    if execution_anomaly_total > 0:
        incidents.append(
            {
                "type": "execution_anomaly",
                "severity": "RED",
                "detail": f"execution_anomaly_total={execution_anomaly_total}",
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


def _extract_report_focus_targets(day_rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for row in day_rows:
        if str(row.get("stage") or "").strip() != "strategist" or str(row.get("event") or "").strip() != "summary":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        focus = payload.get("report_focus")
        if not isinstance(focus, list):
            continue
        for item in focus:
            s = str(item or "").strip().lower()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
    return out[:12]


def _build_decision_chains(day_rows: List[Dict[str, Any]], *, limit: int = 200) -> Dict[str, Any]:
    by_run: Dict[str, Dict[str, Any]] = {}
    ordered = sorted(day_rows, key=lambda r: _to_epoch(r.get("ts") or (r.get("payload") or {}).get("ts")) or 0)
    for row in ordered:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        chain = by_run.setdefault(
            run_id,
            {
                "run_id": run_id,
                "symbol": "",
                "action": "",
                "buy_reason": "",
                "sell_reason": "",
                "monitor_reason": "",
                "execution_status": "UNKNOWN",
                "supervisor_verdict": "UNKNOWN",
                "guard_reason": "",
                "strategist_frame": {},
                "scanner_selection": {},
                "monitor_decision": {},
                "events": [],
            },
        )
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        chain["events"].append(f"{stage}:{event}")

        if stage == "decision" and event == "trace":
            packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
            intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
            action = str(intent.get("action") or "").strip().upper()
            symbol = str(intent.get("symbol") or "").strip().upper()
            reason = _reason_text(intent.get("reason") or intent.get("rationale"))
            if action:
                chain["action"] = action
            if symbol:
                chain["symbol"] = symbol
            if action == "BUY" and reason:
                chain["buy_reason"] = reason
            if action == "SELL" and reason:
                chain["sell_reason"] = reason
        elif stage == "monitor" and event == "summary":
            mr = _reason_text(payload.get("monitor_reason") or payload.get("exit_reason"))
            if mr:
                chain["monitor_reason"] = mr
        elif stage == "execute_from_packet" and event == "verdict":
            allowed = payload.get("allowed")
            if allowed is True:
                chain["supervisor_verdict"] = "APPROVED"
            elif allowed is False:
                chain["supervisor_verdict"] = "BLOCKED"
                chain["guard_reason"] = _reason_text(payload.get("reason"))
                chain["execution_status"] = "BLOCKED"
        elif stage == "execute_from_packet" and event == "execution":
            ex_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
            symbol = str(order.get("symbol") or "").strip().upper()
            action = str(order.get("action") or "").strip().upper()
            if symbol:
                chain["symbol"] = symbol
            if action:
                chain["action"] = action
            broker_code = str(ex_payload.get("broker_code") or "").strip()
            if broker_code == "0":
                chain["execution_status"] = "EXECUTED_OK"
            elif broker_code:
                chain["execution_status"] = "EXECUTED_FAIL"
            else:
                chain["execution_status"] = "EXECUTED"
        elif stage == "decision_trace":
            agent, ap = _decision_trace_agent_payload(row)
            if agent == "strategist":
                chain["strategist_frame"] = {
                    "market_regime": str(ap.get("market_regime") or ""),
                    "themes": list(ap.get("themes") or []),
                    "playbook": str(ap.get("playbook") or ""),
                    "scanner_bias": str(ap.get("scanner_bias") or ""),
                    "risk_tone": str(ap.get("risk_tone") or ""),
                    "monitor_guidance": str(ap.get("monitor_guidance") or ""),
                }
            elif agent == "scanner":
                chain["scanner_selection"] = {
                    "candidate_pool_size": _safe_int(ap.get("candidate_pool_size"), 0),
                    "selected_symbol": str(ap.get("selected_symbol") or ""),
                    "top_candidates": list(ap.get("top_candidates") or [])[:3],
                }
                if not chain.get("symbol"):
                    sel = str(ap.get("selected_symbol") or "").strip().upper()
                    if sel:
                        chain["symbol"] = sel
            elif agent == "monitor":
                chain["monitor_decision"] = {
                    "entry_reason": _reason_text(ap.get("entry_reason")),
                    "exit_reason": _reason_text(ap.get("exit_reason")),
                    "monitor_reason": _reason_text(ap.get("monitor_reason")),
                    "min_hold_blocked": bool(ap.get("min_hold_blocked")),
                    "sell_cooldown_blocked": bool(ap.get("sell_cooldown_blocked")),
                }
                mr = _reason_text(ap.get("monitor_reason"))
                if mr != "unspecified":
                    chain["monitor_reason"] = mr
            elif agent == "supervisor":
                verdict = str(ap.get("verdict") or "").strip().upper()
                if verdict:
                    chain["supervisor_verdict"] = verdict
                gr = _reason_text(ap.get("guard_reason"))
                if gr != "unspecified":
                    chain["guard_reason"] = gr
                if verdict in ("REJECT", "BLOCKED"):
                    chain["execution_status"] = "BLOCKED"
            elif agent == "executor":
                fs = str(ap.get("fill_status_summary") or "").strip().upper()
                if fs:
                    chain["execution_status"] = fs

    chains = list(by_run.values())
    for c in chains:
        if not c.get("buy_reason") and str(c.get("action") or "").upper() == "BUY":
            c["buy_reason"] = "unspecified"
        if not c.get("sell_reason") and str(c.get("action") or "").upper() == "SELL":
            c["sell_reason"] = "unspecified"
        c["events"] = list(c.get("events") or [])[:24]

    chains = chains[: max(1, int(limit))]
    return {
        "run_total": int(len(by_run)),
        "rendered_run_total": int(len(chains)),
        "chains": chains,
    }


def _build_decision_trace_chain_summary(day_rows: List[Dict[str, Any]], *, limit: int = 200) -> Dict[str, Any]:
    by_run: Dict[str, Dict[str, Any]] = {}
    for row in sorted(day_rows, key=lambda r: _to_epoch(r.get("ts") or (r.get("payload") or {}).get("ts")) or 0):
        if str(row.get("stage") or "").strip() != "decision_trace":
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        agent, ap = _decision_trace_agent_payload(row)
        if not agent:
            continue
        chain = by_run.setdefault(
            run_id,
            {
                "run_id": run_id,
                "strategist": {},
                "scanner": {},
                "monitor": {},
                "supervisor": {},
                "executor": {},
                "agent_sequence": [],
            },
        )
        chain["agent_sequence"].append(agent)
        if agent == "strategist":
            chain["strategist"] = {
                "market_regime": str(ap.get("market_regime") or ""),
                "themes": list(ap.get("themes") or [])[:5],
                "playbook": str(ap.get("playbook") or ""),
                "scanner_bias": str(ap.get("scanner_bias") or ""),
                "risk_tone": str(ap.get("risk_tone") or ""),
                "monitor_guidance": str(ap.get("monitor_guidance") or ""),
            }
        elif agent == "scanner":
            chain["scanner"] = {
                "candidate_pool_size": _safe_int(ap.get("candidate_pool_size"), 0),
                "selected_symbol": str(ap.get("selected_symbol") or ""),
                "top_candidates": list(ap.get("top_candidates") or [])[:3],
                "score_breakdown_summary": dict(ap.get("score_breakdown_summary") or {}),
            }
        elif agent == "monitor":
            chain["monitor"] = {
                "entry_reason": _reason_text(ap.get("entry_reason")),
                "exit_reason": _reason_text(ap.get("exit_reason")),
                "monitor_reason": _reason_text(ap.get("monitor_reason")),
                "min_hold_blocked": bool(ap.get("min_hold_blocked")),
                "sell_cooldown_blocked": bool(ap.get("sell_cooldown_blocked")),
            }
        elif agent == "supervisor":
            chain["supervisor"] = {
                "verdict": str(ap.get("verdict") or ""),
                "guard_reason": _reason_text(ap.get("guard_reason")),
            }
        elif agent == "executor":
            chain["executor"] = {
                "execution_attempted": bool(ap.get("execution_attempted")),
                "fill_status_summary": str(ap.get("fill_status_summary") or ""),
                "order_result": dict(ap.get("order_result") or {}),
            }

    chains = list(by_run.values())
    complete_total = 0
    for chain in chains:
        seq = list(chain.get("agent_sequence") or [])
        chain["agent_sequence"] = seq[:16]
        complete = (
            bool(chain.get("strategist"))
            and bool(chain.get("scanner"))
            and bool(chain.get("monitor"))
            and bool(chain.get("supervisor"))
            and bool(chain.get("executor"))
        )
        if complete:
            complete_total += 1
        chain["complete_chain"] = bool(complete)

    chains = chains[: max(1, int(limit))]
    return {
        "run_total": int(len(by_run)),
        "rendered_run_total": int(len(chains)),
        "complete_chain_total": int(complete_total),
        "chains": chains,
    }


def _build_trade_summary_section(
    *,
    trade_decision: Dict[str, Any],
    decision_chains: Dict[str, Any],
) -> Dict[str, Any]:
    trade_rows = trade_decision.get("trade_summaries") if isinstance(trade_decision.get("trade_summaries"), list) else []
    symbols = sorted({str(r.get("symbol") or "").strip().upper() for r in trade_rows if isinstance(r, dict) and str(r.get("symbol") or "").strip()})
    hold_rows: List[Dict[str, Any]] = []
    for row in trade_rows:
        if not isinstance(row, dict):
            continue
        hold_rows.append(
            {
                "symbol": str(row.get("symbol") or "").strip().upper(),
                "holding_duration_sec": _safe_int(row.get("holding_duration_sec"), 0),
                "buy_reason": _reason_text(row.get("buy_reason")),
                "sell_reason": _reason_text(row.get("sell_reason")),
            }
        )
    return {
        "trade_count": int(_safe_int(trade_decision.get("trade_summary_total"), 0)),
        "symbols_traded": symbols,
        "symbol_hold_durations": hold_rows,
        "decision_chain_run_total": int(_safe_int(decision_chains.get("run_total"), 0)),
    }


def _build_strategist_evaluation(day_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    theme_counts: Counter[str] = Counter()
    leader_symbol_counts: Counter[str] = Counter()
    theme_filter_applied_total = 0
    scanner_summary_total = 0
    for row in day_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "strategist" and event == "summary":
            for t in payload.get("themes") or []:
                s = str(t or "").strip().lower()
                if s:
                    theme_counts[s] += 1
        if stage == "strategist_llm" and event == "result":
            for key in ("themes", "top_themes"):
                vals = payload.get(key)
                if isinstance(vals, list):
                    for t in vals:
                        s = str(t or "").strip().lower()
                        if s:
                            theme_counts[s] += 1
        if stage == "scanner" and event == "summary":
            scanner_summary_total += 1
            if bool(payload.get("theme_filter_applied")):
                theme_filter_applied_total += 1
            top = str(payload.get("top_stock") or "").strip().upper()
            if top:
                leader_symbol_counts[top] += 1

    themes = [k for k, _ in theme_counts.most_common(8)]
    leaders = [k for k, _ in leader_symbol_counts.most_common(8)]
    if not themes or scanner_summary_total <= 0:
        alignment = "insufficient_data"
    elif theme_filter_applied_total > 0:
        alignment = "aligned"
    else:
        alignment = "partial"
    return {
        "themes_proposed": themes,
        "actual_market_leaders_by_scanner": leaders,
        "theme_filter_applied_total": int(theme_filter_applied_total),
        "scanner_summary_total": int(scanner_summary_total),
        "theme_alignment_status": alignment,
        "assessment": (
            "Strategist themes were reflected in scanner filtering."
            if alignment == "aligned"
            else (
                "Theme guidance existed but scanner theme-filter evidence was limited."
                if alignment == "partial"
                else "Insufficient strategist/scanner evidence to evaluate theme correctness."
            )
        ),
    }


def _build_scanner_evaluation(day_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    top_score_values: List[float] = []
    candidate_pool_values: List[int] = []
    top_stock_counts: Counter[str] = Counter()
    no_candidate_total = 0
    source_counts: Counter[str] = Counter()

    for row in day_rows:
        if str(row.get("stage") or "").strip() != "scanner" or str(row.get("event") or "").strip() != "summary":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        source = str(payload.get("candidate_source") or "").strip().lower()
        if source:
            source_counts[source] += 1
        top = str(payload.get("top_stock") or "").strip().upper()
        if top:
            top_stock_counts[top] += 1
        else:
            no_candidate_total += 1
        top_score = payload.get("top_score")
        if top_score is not None:
            top_score_values.append(_safe_float(top_score, 0.0))
        pool = payload.get("candidate_pool_after_filter")
        if pool is not None:
            candidate_pool_values.append(_safe_int(pool, 0))

    total = int(sum(source_counts.values()) + no_candidate_total)
    avg_top_score = (sum(top_score_values) / len(top_score_values)) if top_score_values else None
    avg_pool = (sum(candidate_pool_values) / len(candidate_pool_values)) if candidate_pool_values else None
    status = "insufficient_data"
    if total > 0:
        status = "appropriate" if (no_candidate_total / max(1, total)) <= 0.40 else "needs_review"

    return {
        "scanner_summary_total": int(total),
        "candidate_source_top": dict(source_counts.most_common(5)),
        "selected_symbol_top": dict(top_stock_counts.most_common(10)),
        "no_candidate_total": int(no_candidate_total),
        "avg_top_score": float(round(avg_top_score, 6)) if avg_top_score is not None else None,
        "avg_candidate_pool_after_filter": float(round(avg_pool, 3)) if avg_pool is not None else None,
        "selection_status": status,
        "assessment": (
            "Scanner selected symbols consistently with sufficient candidate pool."
            if status == "appropriate"
            else (
                "Scanner produced too many empty selections; candidate sourcing/filtering should be tuned."
                if status == "needs_review"
                else "Insufficient scanner summary events."
            )
        ),
    }


def _build_monitor_evaluation(
    *,
    day_rows: List[Dict[str, Any]],
    overtrading: Dict[str, Any],
) -> Dict[str, Any]:
    monitor_total = 0
    min_hold_blocked = 0
    sell_cooldown_blocked = 0
    confirm_pending = 0
    confirmed_exit = 0
    monitor_reason_counts: Counter[str] = Counter()
    for row in day_rows:
        if str(row.get("stage") or "").strip() != "monitor" or str(row.get("event") or "").strip() != "summary":
            continue
        monitor_total += 1
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if bool(payload.get("min_hold_blocked")):
            min_hold_blocked += 1
        if bool(payload.get("sell_cooldown_blocked")):
            sell_cooldown_blocked += 1
        reason = str(payload.get("monitor_reason") or "").strip().lower()
        if reason:
            monitor_reason_counts[reason] += 1
            if reason == "exit_signal_pending_confirmation":
                confirm_pending += 1
            if reason in ("confirmed_exit_signal", "emergency_exit_signal"):
                confirmed_exit += 1

    rapid_cycles = _safe_int(overtrading.get("rapid_buy_sell_cycles"), 0)
    status = "stable"
    if rapid_cycles > 0:
        status = "overtrading_risk"
    elif monitor_total <= 0:
        status = "insufficient_data"
    return {
        "monitor_summary_total": int(monitor_total),
        "monitor_reason_top": dict(monitor_reason_counts.most_common(12)),
        "min_hold_blocked_total": int(min_hold_blocked),
        "sell_cooldown_blocked_total": int(sell_cooldown_blocked),
        "exit_signal_pending_confirmation_total": int(confirm_pending),
        "confirmed_exit_total": int(confirmed_exit),
        "rapid_buy_sell_cycles": int(rapid_cycles),
        "monitor_status": status,
        "assessment": (
            "Monitor shows overtrading risk; tighten exit confirmation or thresholds."
            if status == "overtrading_risk"
            else ("Monitor flow is stable under current guards." if status == "stable" else "Insufficient monitor summary events.")
        ),
    }


def _build_supervisor_activity(day_rows: List[Dict[str, Any]], *, intent_flow: Dict[str, Any]) -> Dict[str, Any]:
    verdict_total = 0
    blocked_total = 0
    approved_total = 0
    reason_counts: Counter[str] = Counter()
    for row in day_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "execute_from_packet" and event == "verdict":
            verdict_total += 1
            if payload.get("allowed") is True:
                approved_total += 1
            elif payload.get("allowed") is False:
                blocked_total += 1
                reason_counts[_reason_text(payload.get("reason"))] += 1
            continue
        if stage == "decision_trace" and event == "verdict":
            agent, ap = _decision_trace_agent_payload(row)
            if agent != "supervisor":
                continue
            verdict_total += 1
            verdict = str(ap.get("verdict") or "").strip().upper()
            if verdict in ("APPROVE", "APPROVED", "ALLOW"):
                approved_total += 1
            elif verdict in ("REJECT", "BLOCKED", "DENY"):
                blocked_total += 1
                reason_counts[_reason_text(ap.get("guard_reason"))] += 1

    if blocked_total <= 0:
        blocked_total = _safe_int(intent_flow.get("intents_blocked"), blocked_total)
    if approved_total <= 0:
        approved_total = _safe_int(intent_flow.get("intents_approved"), approved_total)

    block_rate = float(blocked_total / max(1, blocked_total + approved_total))
    return {
        "verdict_total": int(verdict_total),
        "approved_total": int(approved_total),
        "blocked_total": int(blocked_total),
        "blocked_rate": float(round(block_rate, 6)),
        "blocked_reason_top": dict(reason_counts.most_common(12)),
        "assessment": (
            "Supervisor blocks are elevated; review guard thresholds."
            if block_rate >= 0.40
            else "Supervisor activity within normal range."
        ),
    }


def _build_report_views(
    *,
    day: str,
    trade_summary: Dict[str, Any],
    monitor_eval: Dict[str, Any],
    scanner_eval: Dict[str, Any],
    supervisor_activity: Dict[str, Any],
    incidents: Dict[str, Any],
    improvement_suggestions: List[str],
) -> Dict[str, Any]:
    incident_total = _safe_int(incidents.get("incident_total"), 0)
    blocked_rate = _safe_float(supervisor_activity.get("blocked_rate"), 0.0)
    monitor_status = str(monitor_eval.get("monitor_status") or "unknown")
    scanner_status = str(scanner_eval.get("selection_status") or "unknown")
    health = "GREEN"
    if incident_total > 0 or monitor_status == "overtrading_risk":
        health = "YELLOW"
    if blocked_rate >= 0.5:
        health = "RED"
    operator_lines: List[str] = [
        f"{day}: health={health}",
        f"trade_count={_safe_int(trade_summary.get('trade_count'), 0)} symbols={len(trade_summary.get('symbols_traded') or [])}",
        f"monitor_status={monitor_status} scanner_status={scanner_status} supervisor_blocked_rate={blocked_rate:.2%}",
    ]
    if incident_total > 0:
        operator_lines.append(f"incident_total={incident_total}")
    if improvement_suggestions:
        operator_lines.append(f"next_action={improvement_suggestions[0]}")

    developer_lines: List[str] = [
        f"decision_chain_run_total={_safe_int(trade_summary.get('decision_chain_run_total'), 0)}",
        f"blocked_total={_safe_int(supervisor_activity.get('blocked_total'), 0)} approved_total={_safe_int(supervisor_activity.get('approved_total'), 0)}",
        f"monitor_confirmed_exit_total={_safe_int(monitor_eval.get('confirmed_exit_total'), 0)}",
        f"scanner_no_candidate_total={_safe_int(scanner_eval.get('no_candidate_total'), 0)}",
    ]
    return {
        "operator_facing_summary": {
            "system_health": health,
            "summary_lines": operator_lines[:4],
            "recommended_actions": improvement_suggestions[:3],
        },
        "developer_facing_summary": {
            "summary_lines": developer_lines,
            "blocked_reason_top": dict((supervisor_activity.get("blocked_reason_top") or {})),
            "monitor_reason_top": dict((monitor_eval.get("monitor_reason_top") or {})),
        },
    }


def _build_improvement_suggestions(
    *,
    strategist_eval: Dict[str, Any],
    scanner_eval: Dict[str, Any],
    monitor_eval: Dict[str, Any],
    supervisor_activity: Dict[str, Any],
    incidents: Dict[str, Any],
    report_focus_targets: List[str],
) -> List[str]:
    focus = {str(x or "").strip().lower() for x in list(report_focus_targets or [])}
    wants_theme = bool(focus & {"theme_accuracy", "theme", "themes"})
    wants_scanner = bool(focus & {"scanner_fit", "scanner", "selection"})
    wants_exit = bool(focus & {"exit_quality", "exit", "overtrading"})
    wants_guard = bool(focus & {"guard_blocks", "supervisor", "risk_guard"})
    no_focus = len(focus) == 0

    suggestions: List[str] = []
    if (no_focus or wants_theme) and str(strategist_eval.get("theme_alignment_status") or "") in ("partial", "insufficient_data"):
        suggestions.append("Improve strategist-to-market alignment evidence: add stronger theme mapping and leader validation inputs.")
    if (no_focus or wants_scanner) and str(scanner_eval.get("selection_status") or "") == "needs_review":
        suggestions.append("Tune scanner candidate pool reduction (TOP_CANDIDATE_POOL/MIN_TRADING_VALUE/MIN_VOLUME) to reduce empty selections.")
    if (no_focus or wants_exit) and str(monitor_eval.get("monitor_status") or "") == "overtrading_risk":
        suggestions.append("Reduce monitor flip risk by increasing confirmation strictness or widening non-emergency exit thresholds.")
    if (no_focus or wants_guard) and _safe_float(supervisor_activity.get("blocked_rate"), 0.0) >= 0.40:
        suggestions.append("High supervisor block rate: recalibrate strategy aggressiveness and guard limits for better intent quality.")
    if _safe_int(incidents.get("incident_total"), 0) > 0:
        suggestions.append("Run incident postmortem and convert top anomaly into explicit preopen/checklist gate before next session.")
    if not suggestions:
        suggestions.append("No critical gaps detected; keep current baseline and continue daily report-driven calibration.")
    return suggestions[:8]


def _to_markdown(out: Dict[str, Any]) -> str:
    day = str(out.get("day") or "")
    trade_section = out.get("trade_decision_summaries") if isinstance(out.get("trade_decision_summaries"), dict) else {}
    flow = out.get("intent_flow_analysis") if isinstance(out.get("intent_flow_analysis"), dict) else {}
    eff = out.get("strategy_effectiveness") if isinstance(out.get("strategy_effectiveness"), dict) else {}
    over = out.get("overtrading_diagnostics") if isinstance(out.get("overtrading_diagnostics"), dict) else {}
    market = out.get("market_context") if isinstance(out.get("market_context"), dict) else {}
    incidents = out.get("incident_postmortem") if isinstance(out.get("incident_postmortem"), dict) else {}
    operator = out.get("daily_operator_report") if isinstance(out.get("daily_operator_report"), dict) else {}
    trade_summary = out.get("trade_summary") if isinstance(out.get("trade_summary"), dict) else {}
    decision_chains = out.get("decision_chains") if isinstance(out.get("decision_chains"), dict) else {}
    trace_summary = out.get("decision_trace_chain_summary") if isinstance(out.get("decision_trace_chain_summary"), dict) else {}
    strategist_eval = out.get("strategist_evaluation") if isinstance(out.get("strategist_evaluation"), dict) else {}
    scanner_eval = out.get("scanner_evaluation") if isinstance(out.get("scanner_evaluation"), dict) else {}
    monitor_eval = out.get("monitor_evaluation") if isinstance(out.get("monitor_evaluation"), dict) else {}
    supervisor_activity = out.get("supervisor_activity") if isinstance(out.get("supervisor_activity"), dict) else {}
    improvement = out.get("improvement_suggestions") if isinstance(out.get("improvement_suggestions"), list) else []
    report_focus_targets = out.get("report_focus_targets") if isinstance(out.get("report_focus_targets"), list) else []
    operator_view = out.get("operator_facing_summary") if isinstance(out.get("operator_facing_summary"), dict) else {}
    developer_view = out.get("developer_facing_summary") if isinstance(out.get("developer_facing_summary"), dict) else {}
    ai_review = out.get("ai_review") if isinstance(out.get("ai_review"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Reporter Analysis ({day})")
    lines.append("")
    lines.append("## Daily Operator Report")
    lines.append("")
    lines.append(f"- system_health: **{operator_view.get('system_health') or 'UNKNOWN'}**")
    for txt in (operator_view.get("summary_lines") or [])[:4]:
        lines.append(f"- {txt}")
    lines.append(f"- recommended_actions: `{json.dumps(operator_view.get('recommended_actions') or [], ensure_ascii=False)}`")
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
    lines.append("## Trade Summary")
    lines.append("")
    lines.append(f"- trade_count: **{_safe_int(trade_summary.get('trade_count'), 0)}**")
    lines.append(f"- symbols_traded: `{json.dumps(trade_summary.get('symbols_traded') or [], ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Decision Chains")
    lines.append("")
    lines.append(f"- run_total: **{_safe_int(decision_chains.get('run_total'), 0)}**")
    lines.append(f"- rendered_run_total: **{_safe_int(decision_chains.get('rendered_run_total'), 0)}**")
    for chain in (decision_chains.get("chains") or [])[:10]:
        if not isinstance(chain, dict):
            continue
        lines.append(
            f"- run_id={chain.get('run_id')} symbol={chain.get('symbol') or '-'} action={chain.get('action') or '-'} "
            f"supervisor={chain.get('supervisor_verdict') or '-'} execution={chain.get('execution_status') or '-'} "
            f"buy_reason={chain.get('buy_reason') or '-'} sell_reason={chain.get('sell_reason') or '-'}"
        )
    lines.append("")
    lines.append("## Decision Trace Chain Summary")
    lines.append("")
    lines.append(f"- run_total: **{_safe_int(trace_summary.get('run_total'), 0)}**")
    lines.append(f"- complete_chain_total: **{_safe_int(trace_summary.get('complete_chain_total'), 0)}**")
    for chain in (trace_summary.get("chains") or [])[:10]:
        if not isinstance(chain, dict):
            continue
        scanner = chain.get("scanner") if isinstance(chain.get("scanner"), dict) else {}
        monitor = chain.get("monitor") if isinstance(chain.get("monitor"), dict) else {}
        supervisor = chain.get("supervisor") if isinstance(chain.get("supervisor"), dict) else {}
        executor = chain.get("executor") if isinstance(chain.get("executor"), dict) else {}
        lines.append(
            f"- run_id={chain.get('run_id')} selected={scanner.get('selected_symbol') or '-'} "
            f"monitor={monitor.get('monitor_reason') or '-'} supervisor={supervisor.get('verdict') or '-'} "
            f"executor={executor.get('fill_status_summary') or '-'} complete={bool(chain.get('complete_chain'))}"
        )
    lines.append("")
    lines.append("## Strategist Evaluation")
    lines.append("")
    lines.append(f"- themes_proposed: `{json.dumps(strategist_eval.get('themes_proposed') or [], ensure_ascii=False)}`")
    lines.append(
        f"- actual_market_leaders_by_scanner: `{json.dumps(strategist_eval.get('actual_market_leaders_by_scanner') or [], ensure_ascii=False)}`"
    )
    lines.append(f"- theme_alignment_status: **{strategist_eval.get('theme_alignment_status') or 'unknown'}**")
    lines.append(f"- assessment: {strategist_eval.get('assessment') or '-'}")
    lines.append("")
    lines.append("## Scanner Evaluation")
    lines.append("")
    lines.append(f"- scanner_summary_total: **{_safe_int(scanner_eval.get('scanner_summary_total'), 0)}**")
    lines.append(f"- selected_symbol_top: `{json.dumps(scanner_eval.get('selected_symbol_top') or {}, ensure_ascii=False)}`")
    lines.append(f"- no_candidate_total: **{_safe_int(scanner_eval.get('no_candidate_total'), 0)}**")
    if scanner_eval.get("avg_top_score") is not None:
        lines.append(f"- avg_top_score: **{_safe_float(scanner_eval.get('avg_top_score'), 0.0):.4f}**")
    lines.append(f"- selection_status: **{scanner_eval.get('selection_status') or 'unknown'}**")
    lines.append(f"- assessment: {scanner_eval.get('assessment') or '-'}")
    lines.append("")
    lines.append("## Monitor Evaluation")
    lines.append("")
    lines.append(f"- monitor_summary_total: **{_safe_int(monitor_eval.get('monitor_summary_total'), 0)}**")
    lines.append(f"- monitor_reason_top: `{json.dumps(monitor_eval.get('monitor_reason_top') or {}, ensure_ascii=False)}`")
    lines.append(f"- rapid_buy_sell_cycles: **{_safe_int(monitor_eval.get('rapid_buy_sell_cycles'), 0)}**")
    lines.append(f"- monitor_status: **{monitor_eval.get('monitor_status') or 'unknown'}**")
    lines.append(f"- assessment: {monitor_eval.get('assessment') or '-'}")
    lines.append("")
    lines.append("## Supervisor Activity")
    lines.append("")
    lines.append(f"- verdict_total: **{_safe_int(supervisor_activity.get('verdict_total'), 0)}**")
    lines.append(f"- approved_total: **{_safe_int(supervisor_activity.get('approved_total'), 0)}**")
    lines.append(f"- blocked_total: **{_safe_int(supervisor_activity.get('blocked_total'), 0)}**")
    lines.append(f"- blocked_rate: **{_safe_float(supervisor_activity.get('blocked_rate'), 0.0):.2%}**")
    lines.append(f"- blocked_reason_top: `{json.dumps(supervisor_activity.get('blocked_reason_top') or {}, ensure_ascii=False)}`")
    lines.append(f"- assessment: {supervisor_activity.get('assessment') or '-'}")
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
    lines.append("## Improvement Suggestions")
    lines.append("")
    lines.append(f"- report_focus_targets: `{json.dumps(report_focus_targets, ensure_ascii=False)}`")
    for item in improvement[:8]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## AI Review (Passive Optional Layer)")
    lines.append("")
    lines.append(f"- ai_review_status: **{ai_review.get('status') or 'disabled'}**")
    if ai_review.get("model"):
        lines.append(f"- ai_review_model: `{ai_review.get('model')}`")
    if ai_review.get("reason"):
        lines.append(f"- ai_review_reason: {ai_review.get('reason')}")
    lines.append(f"- ai_run_grade: **{out.get('ai_run_grade') or 'N/A'}**")
    if out.get("ai_summary"):
        lines.append(f"- ai_summary: {out.get('ai_summary')}")
    lines.append(f"- ai_findings: `{json.dumps(out.get('ai_findings') or [], ensure_ascii=False)}`")
    lines.append(f"- ai_root_causes: `{json.dumps(out.get('ai_root_causes') or [], ensure_ascii=False)}`")
    lines.append(
        f"- ai_improvement_suggestions: `{json.dumps(out.get('ai_improvement_suggestions') or [], ensure_ascii=False)}`"
    )
    lines.append(f"- ai_agent_evaluations: `{json.dumps(out.get('ai_agent_evaluations') or {}, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Developer Summary")
    lines.append("")
    for txt in (developer_view.get("summary_lines") or [])[:8]:
        lines.append(f"- {txt}")
    lines.append(f"- blocked_reason_top: `{json.dumps(developer_view.get('blocked_reason_top') or {}, ensure_ascii=False)}`")
    lines.append(f"- monitor_reason_top: `{json.dumps(developer_view.get('monitor_reason_top') or {}, ensure_ascii=False)}`")
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
    ai_review_enabled: Optional[bool] = None,
    ai_review_model: Optional[str] = None,
    ai_review_temperature: Optional[float] = None,
    ai_review_max_tokens: int = 900,
) -> Tuple[Path, Path, Dict[str, Any]]:
    """Generate enhanced reporter analysis from append-only logs.

    Reporter remains passive: this function reads logs only and derives reports.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    root = reports_root or report_dir.parent
    target_day = str(day or _latest_day(event_log_path) or date.today().isoformat())
    reporter_run_id = f"reporter-{target_day}"

    rows = []
    for row in _iter_jsonl(event_log_path):
        ts = row.get("ts") or (row.get("payload") or {}).get("ts")
        rows.append({**row, "_day": _utc_day(ts)})
    day_rows = [r for r in rows if str(r.get("_day") or "") == target_day]
    try:
        record_raw_input(
            run_id=reporter_run_id,
            agent="reporter",
            stage="post_run_analysis",
            raw_input={
                "target_day": target_day,
                "event_log_path": str(event_log_path),
                "day_row_count": int(len(day_rows)),
                "rapid_cycle_threshold_sec": int(rapid_cycle_threshold_sec),
                "reports_root": str(root),
            },
            decision_link={"stage": "reporter_analysis_start"},
        )
    except Exception:
        pass

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
        m30_post_golive_dir=root / "milestones" / "m30_post_golive",
        m30_golive_dir=root / "milestones" / "m30_golive",
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
    report_focus_targets = _extract_report_focus_targets(day_rows)
    overtrading = _build_overtrading_diagnostics(
        trade_explain_obj=trade_obj,
        intent_flow=intent_flow,
        rapid_threshold_sec=max(1, int(rapid_cycle_threshold_sec)),
    )
    incident = _build_incident_postmortem(overtrading=overtrading, intent_flow=intent_flow, day_rows=day_rows)
    market_context = _build_market_context(trade_explain_obj=trade_obj, day_rows=day_rows)
    decision_chains = _build_decision_chains(day_rows, limit=200)
    decision_trace_chain_summary = _build_decision_trace_chain_summary(day_rows, limit=200)
    trade_summary = _build_trade_summary_section(trade_decision=trade_decision, decision_chains=decision_chains)
    strategist_eval = _build_strategist_evaluation(day_rows)
    scanner_eval = _build_scanner_evaluation(day_rows)
    monitor_eval = _build_monitor_evaluation(day_rows=day_rows, overtrading=overtrading)
    supervisor_activity = _build_supervisor_activity(day_rows, intent_flow=intent_flow)
    improvement_suggestions = _build_improvement_suggestions(
        strategist_eval=strategist_eval,
        scanner_eval=scanner_eval,
        monitor_eval=monitor_eval,
        supervisor_activity=supervisor_activity,
        incidents=incident,
        report_focus_targets=report_focus_targets,
    )
    report_views = _build_report_views(
        day=target_day,
        trade_summary=trade_summary,
        monitor_eval=monitor_eval,
        scanner_eval=scanner_eval,
        supervisor_activity=supervisor_activity,
        incidents=incident,
        improvement_suggestions=improvement_suggestions,
    )

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
        "trade_summary": trade_summary,
        "decision_chains": decision_chains,
        "decision_trace_chain_summary": decision_trace_chain_summary,
        "trade_decision_summaries": trade_decision,
        "strategist_evaluation": strategist_eval,
        "scanner_evaluation": scanner_eval,
        "monitor_evaluation": monitor_eval,
        "supervisor_activity": supervisor_activity,
        "intent_flow_analysis": intent_flow,
        "strategy_effectiveness": strategy_eff,
        "overtrading_diagnostics": overtrading,
        "daily_operator_report": daily_operator,
        "incident_postmortem": incident,
        "incidents": incident,
        "improvement_suggestions": improvement_suggestions,
        "operator_facing_summary": report_views.get("operator_facing_summary", {}),
        "developer_facing_summary": report_views.get("developer_facing_summary", {}),
        "market_context": market_context,
        "report_focus_targets": list(report_focus_targets),
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

    try:
        ai_review = build_ai_reporter_review(
            day=target_day,
            reporter_output=out,
            enabled=ai_review_enabled,
            model=ai_review_model,
            temperature=ai_review_temperature,
            max_tokens=max(256, int(ai_review_max_tokens)),
        )
    except Exception as e:
        ai_review = {
            "enabled": bool(ai_review_enabled),
            "status": "error",
            "reason": f"ai_review_exception:{e}",
            "model": str(ai_review_model or ""),
            "ai_summary": "",
            "ai_findings": [],
            "ai_root_causes": [],
            "ai_improvement_suggestions": [],
            "ai_run_grade": "N/A",
            "ai_agent_evaluations": {},
        }
    out["ai_review"] = dict(ai_review)
    out["ai_summary"] = str(ai_review.get("ai_summary") or "")
    out["ai_findings"] = list(ai_review.get("ai_findings") or [])
    out["ai_root_causes"] = list(ai_review.get("ai_root_causes") or [])
    out["ai_improvement_suggestions"] = list(ai_review.get("ai_improvement_suggestions") or [])
    out["ai_run_grade"] = str(ai_review.get("ai_run_grade") or "N/A")
    out["ai_agent_evaluations"] = dict(ai_review.get("ai_agent_evaluations") or {})
    try:
        record_decision_bridge(
            run_id=reporter_run_id,
            agent="reporter",
            stage="post_run_analysis",
            raw_input={
                "source_reports": dict(out.get("source_reports") or {}),
                "report_focus_targets": list(out.get("report_focus_targets") or []),
            },
            parsed_output={
                "trade_summary": dict(out.get("trade_summary") or {}),
                "decision_trace_chain_summary": dict(out.get("decision_trace_chain_summary") or {}),
                "monitor_evaluation": dict(out.get("monitor_evaluation") or {}),
                "supervisor_activity": dict(out.get("supervisor_activity") or {}),
                "ai_review": dict(out.get("ai_review") or {}),
            },
            decision_link={
                "decision_chain": {
                    "theme": str(((out.get("strategist_evaluation") or {}).get("themes_proposed") or [""])[0] if isinstance((out.get("strategist_evaluation") or {}).get("themes_proposed"), list) and ((out.get("strategist_evaluation") or {}).get("themes_proposed") or []) else ""),
                    "scanner_selected": str(((out.get("scanner_evaluation") or {}).get("selected_symbol_top") or {}).get("symbol") or ""),
                    "entry_reason": str(((out.get("monitor_evaluation") or {}).get("monitor_reason_top") or {}).get("entry_signal") or ""),
                    "exit_reason": str(((out.get("monitor_evaluation") or {}).get("monitor_reason_top") or {}).get("confirmed_exit_signal") or ""),
                }
            },
        )
    except Exception:
        pass

    js_path = report_dir / f"reporter_analysis_{target_day}.json"
    md_path = report_dir / f"reporter_analysis_{target_day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(out), encoding="utf-8")
    return md_path, js_path, out
