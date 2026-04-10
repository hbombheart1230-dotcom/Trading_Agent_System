from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.llm.model_catalog import resolve_policy_llm_execution_slot, resolve_policy_llm_slot
from libs.llm.model_names import normalize_openrouter_model_name
from libs.reporting.llm_artifacts import daily_artifact_paths
from libs.reporting.narrative_axes import build_narrative_explanation, narrative_axis_policy
from libs.reporting.report_metadata import (
    build_data_freshness,
    build_route_provenance,
    render_data_freshness_markdown,
)
from libs.reporting.report_source_helpers import (
    build_commander_route_summary,
    build_policy_surface_quality_snapshot,
)


_REASON_LABELS: Dict[str, str] = {
    "none": "none",
    "unspecified": "UNSPECIFIED",
    "NO_CANDIDATE": "NO_CANDIDATE (no candidate met entry conditions)",
    "MARKET_CLOSED": "MARKET_CLOSED (outside session window)",
    "GUARD_BLOCK": "GUARD_BLOCK (blocked by safety guard)",
    "noop_intent_skipped": "NOOP intent skipped (no order sent)",
    "denied_by_test": "Blocked by supervisor test rule",
    "duplicate_buy_position_exists": "Blocked duplicate buy (position already open)",
    "insufficient_mock_cash": "Insufficient mock cash",
    "position_already_open": "Position already open",
    "model_no_signal": "Model returned no trade signal",
    "missing_rationale": "Trade rationale missing",
    "strategist_error": "Strategist runtime error",
    "post_exit_cooldown": "Post-exit cooldown active",
    "strategy_v1_noop": "Strategy-v1 returned NOOP",
    "conditions_not_met": "Rule entry conditions not met",
}


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)

    s = str(ts).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
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

    def _gen() -> Iterable[Dict[str, Any]]:
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
                    yield obj

    return _gen()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


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


def _pick_day(rows: List[Dict[str, Any]], requested_day: Optional[str]) -> str:
    if requested_day:
        return str(requested_day).strip()
    days = sorted({str(r.get("_day")) for r in rows if r.get("_day")})
    if days:
        return days[-1]
    return date.today().isoformat()


def _find_day_artifact(base_dir: Path, prefix: str, day: str) -> Dict[str, Any]:
    path = base_dir / f"{prefix}_{day}.json"
    return _read_json(path)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _epoch_to_iso(epoch: Any) -> str:
    try:
        n = int(float(epoch))
    except Exception:
        return ""
    if n <= 0:
        return ""
    return datetime.fromtimestamp(n, tz=timezone.utc).isoformat(timespec="seconds")


def _build_report_freshness(day_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_row: Dict[str, Any] | None = None
    latest_epoch = 0
    run_ids = {
        str(row.get("run_id") or "").strip()
        for row in day_rows
        if str(row.get("run_id") or "").strip()
    }
    for row in day_rows:
        epoch = int(row.get("_epoch") or 0)
        if epoch <= 0:
            continue
        if epoch >= latest_epoch:
            latest_epoch = epoch
            latest_row = row
    return {
        "generated_at": _utc_now_iso(),
        "source_run_count": int(len(run_ids)),
        "latest_run_id": str((latest_row or {}).get("run_id") or ""),
        "latest_run_ts": _epoch_to_iso(latest_epoch),
    }

def _load_or_build_metrics(events_path: Path, metrics_report_dir: Path, day: str) -> Dict[str, Any]:
    metrics_report_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = metrics_report_dir / f"metrics_{day}.json"
    obj = _read_json(metrics_path)
    if obj:
        return obj

    try:
        from scripts.generate_metrics_report import generate_metrics_report

        _, js = generate_metrics_report(events_path, metrics_report_dir, day=day)
        return _read_json(js)
    except Exception:
        return {}


def _compact_kv_text(raw: Any, *, topn: int = 4) -> str:
    if isinstance(raw, dict):
        pairs = []
        for k, v in raw.items():
            if isinstance(v, (dict, list)):
                continue
            pairs.append((str(k), str(v)))
        pairs = pairs[:topn]
        if not pairs:
            return "-"
        return ", ".join(f"{k}={v}" for k, v in pairs)
    if isinstance(raw, list):
        vals = [str(x) for x in raw[:topn] if x is not None]
        return ", ".join(vals) if vals else "-"
    if raw is None:
        return "-"
    s = str(raw).strip()
    return s if s else "-"


def _reason_text(intent: Dict[str, Any], trace: Dict[str, Any], llm: Dict[str, Any]) -> str:
    cand = [
        intent.get("reason"),
        intent.get("rationale"),
        trace.get("rationale"),
        (trace.get("raw_intent") if isinstance(trace.get("raw_intent"), dict) else {}).get("reason"),
        llm.get("intent_reason"),
        llm.get("intent_rationale"),
    ]
    for v in cand:
        s = str(v or "").strip()
        if s:
            return s
    return "unspecified"


def _humanize_reason(raw: Any) -> str:
    reason = str(raw or "").strip()
    if not reason:
        return _REASON_LABELS["unspecified"]
    low = reason.lower()
    if low in _REASON_LABELS:
        return _REASON_LABELS[low]
    if reason in _REASON_LABELS:
        return _REASON_LABELS[reason]
    if low.startswith("exit_policy:"):
        tail = reason.split(":", 1)[1].replace("_", " ").strip()
        return f"Exit policy triggered ({tail})"
    if low.startswith("score_override:"):
        tail = reason.split(":", 1)[1].strip()
        return f"Score override applied ({tail})"
    if low.startswith("eod_force_liquidation:"):
        return f"EOD force liquidation ({reason.split(':', 1)[1]})"
    return reason


def _normalize_reason_code(
    raw_reason: Any,
    *,
    action: str,
    execution_status: str,
    guard_status: str,
) -> str:
    reason = str(raw_reason or "").strip()
    if reason:
        low = reason.lower()
        if any(k in low for k in ("allowlist", "notional", "guard", "blocked")):
            return "GUARD_BLOCK"
        if "market_closed" in low or ("market" in low and "closed" in low):
            return "MARKET_CLOSED"
        if low in ("unspecified", "none"):
            reason = ""

    if guard_status == "intervened" or execution_status == "BLOCKED":
        return "GUARD_BLOCK"
    if action == "NOOP":
        return "NO_CANDIDATE"
    if execution_status in ("UNKNOWN", "SKIPPED"):
        return "MARKET_CLOSED"
    return reason or "unspecified"


def _health_badge(level: str) -> str:
    lv = str(level or "").strip().upper()
    if lv not in ("GREEN", "YELLOW", "RED"):
        return f"[{lv or 'UNKNOWN'}]"
    return f"[{lv}]"


def _render_reason_top(counter: Counter[str], *, topn: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for reason, cnt in counter.most_common(topn):
        out.append(
            {
                "reason": str(reason or ""),
                "label": _humanize_reason(reason),
                "count": int(cnt),
            }
        )
    return out


def _format_reason_rows(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "none"
    return "; ".join(
        f"{str(r.get('label') or r.get('reason') or '-')} ({int(r.get('count') or 0)})"
        for r in rows
    )


def _compact_distance_to_ready_text(raw: Any) -> str:
    row = raw if isinstance(raw, dict) else {}
    if not row:
        return "-"
    parts: List[str] = []
    for key in ("reclaim_score_gap", "breakout_gap", "volume_gap", "confidence_gap"):
        if row.get(key) in (None, ""):
            continue
        try:
            parts.append(f"{key}={float(row.get(key)):.4f}")
        except Exception:
            parts.append(f"{key}={row.get(key)}")
    return ", ".join(parts) if parts else "-"


def _compact_blocking_features(raw: Any, *, limit: int = 3) -> str:
    values = raw if isinstance(raw, list) else []
    clipped = [str(v or "").strip() for v in values if str(v or "").strip()]
    return ", ".join(clipped[:limit]) if clipped else "-"


def _merge_scanner_handoff_with_selection(
    handoff: Any,
    selection: Any,
) -> Dict[str, Any]:
    handoff_row = handoff if isinstance(handoff, dict) else {}
    selection_row = selection if isinstance(selection, dict) else {}
    if not handoff_row and not selection_row:
        return {}
    merged = dict(selection_row)
    merged.update(dict(handoff_row))
    return merged


def _broker_code_success(value: Any) -> Optional[bool]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s)) == 0
    except Exception:
        pass
    t = s.lower()
    if t in ("ok", "success", "accepted"):
        return True
    if t in ("error", "failed", "rejected"):
        return False
    return False


def _decision_axis(story: Dict[str, Any]) -> str:
    action = str(story.get("action") or "").strip().upper()
    no_trade = story.get("no_trade_surface") if isinstance(story.get("no_trade_surface"), dict) else {}
    outcome = str(no_trade.get("decision_outcome") or "").strip().upper()
    if action == "SELL" or outcome == "SELL":
        return "exit"
    return "entry"


def _story_explanation(story: Dict[str, Any]) -> Dict[str, str]:
    no_trade = story.get("no_trade_surface") if isinstance(story.get("no_trade_surface"), dict) else {}
    explanation = build_narrative_explanation(
        action=story.get("action"),
        decision_outcome=no_trade.get("decision_outcome"),
        final_outcome=story.get("final_outcome"),
        key_reason=story.get("key_reason"),
        no_trade_reason_summary=no_trade.get("no_trade_reason_summary"),
        dominant_blocker=no_trade.get("dominant_blocker"),
        distance_to_ready=_compact_distance_to_ready_text(no_trade.get("distance_to_ready")),
        exit_reason=story.get("key_reason") if _decision_axis(story) == "exit" else "",
    )
    return {
        "axis": str(explanation.get("decision_axis") or "unknown"),
        "primary_summary": str(explanation.get("primary_explanation") or "-"),
        "entry_narrative": str(explanation.get("entry_narrative") or "-"),
        "exit_narrative": str(explanation.get("exit_narrative") or "-"),
        "why_not_buy_summary": str(explanation.get("why_not_buy_summary") or "-"),
        "dominant_blocker": str(explanation.get("dominant_blocker_display") or "-"),
        "entry_context_blocker": str(explanation.get("entry_context_blocker") or "-"),
        "distance_to_ready": str(explanation.get("distance_to_ready") or "-"),
        "exit_trigger_basis": str(explanation.get("why_exit_summary") or "-"),
        "narrative_order": list(explanation.get("narrative_order") or []),
        "narrative_order_text": str(explanation.get("narrative_order_text") or "-"),
        "narrative_consistency_flag": bool(explanation.get("narrative_consistency_flag")),
        "explanation_mode": str(explanation.get("explanation_mode") or "unknown"),
        "explanation_source": str(explanation.get("explanation_source") or "-"),
        "mixed_reason": str(explanation.get("mixed_reason") or "-"),
    }


def _canonical_report_root(report_dir: Path) -> Path:
    if report_dir.name in {"operator_summary", "daily", "run_cards", "decision_story", "metrics", "trade_explain"}:
        return report_dir.parent
    return report_dir


def _apply_commander_route_overlay(
    stories: List[Dict[str, Any]],
    route_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    by_run = route_summary.get("by_run") if isinstance(route_summary.get("by_run"), dict) else {}
    if not by_run:
        return stories
    for story in stories:
        run_id = str(story.get("run_id") or "").strip()
        if not run_id:
            continue
        route_row = by_run.get(run_id)
        if not isinstance(route_row, dict):
            continue
        existing = story.get("commander_route") if isinstance(story.get("commander_route"), dict) else {}
        merged = {**dict(existing), **dict(route_row)}
        story["commander_route"] = merged
    return stories


def build_operator_summary_snapshot_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    executive = payload.get("executive_summary") if isinstance(payload.get("executive_summary"), dict) else {}
    system_health = payload.get("system_health_status") if isinstance(payload.get("system_health_status"), dict) else {}
    trading_activity = (
        payload.get("trading_activity_summary")
        if isinstance(payload.get("trading_activity_summary"), dict)
        else {}
    )
    top_issues = payload.get("top_issues") if isinstance(payload.get("top_issues"), list) else []
    recommended_actions = (
        payload.get("recommended_operator_actions")
        if isinstance(payload.get("recommended_operator_actions"), list)
        else []
    )
    route_summary = payload.get("route_summary") if isinstance(payload.get("route_summary"), dict) else {}
    data_freshness = build_data_freshness(
        generated_at=str(payload.get("generated_at") or ""),
        source_run_count=payload.get("source_run_count"),
        latest_run_id=str(payload.get("latest_run_id") or ""),
        latest_run_ts=str(payload.get("latest_run_ts") or ""),
        stale=False,
    )
    return {
        "available": True,
        "generated_at": str(payload.get("generated_at") or ""),
        "source_run_count": payload.get("source_run_count"),
        "latest_run_id": str(payload.get("latest_run_id") or ""),
        "latest_run_ts": str(payload.get("latest_run_ts") or ""),
        "data_freshness": data_freshness,
        "executive_summary": {
            "system_status": str(executive.get("system_status") or ""),
            "summary_lines": [str(x or "") for x in list(executive.get("summary_lines") or []) if str(x or "").strip()][:5],
        },
        "system_health_status": {
            "system_health_level": str(system_health.get("system_health_level") or ""),
            "reasoning": [str(x or "") for x in list(system_health.get("reasoning") or []) if str(x or "").strip()][:5],
            "recommended_action": [str(x or "") for x in list(system_health.get("recommended_action") or []) if str(x or "").strip()][:3],
        },
        "trading_activity_summary": {
            "run_total": trading_activity.get("run_total"),
            "decision_action_counts": dict(trading_activity.get("decision_action_counts") or {}),
            "strategy_counts": dict(trading_activity.get("strategy_counts") or {}),
            "executions_total": trading_activity.get("executions_total"),
            "executions_ok_total": trading_activity.get("executions_ok_total"),
            "executions_fail_total": trading_activity.get("executions_fail_total"),
            "blocked_total": trading_activity.get("blocked_total"),
        },
        "route_summary": {
            "route_source": str(route_summary.get("route_source") or ""),
            "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
            "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
            "route_source_breakdown": dict(route_summary.get("route_source_breakdown") or {}),
            "route_selected_total": dict(route_summary.get("route_selected_total") or {}),
            "strategy_generation_mode_total": dict(route_summary.get("strategy_generation_mode_total") or {}),
        },
        "route_provenance": build_route_provenance(route_summary),
        "top_issues": [
            {
                "code": str((issue or {}).get("code") or ""),
                "severity": str((issue or {}).get("severity") or ""),
                "detail": str((issue or {}).get("detail") or ""),
            }
            for issue in top_issues[:5]
            if isinstance(issue, dict)
        ],
        "recommended_operator_actions": [str(x or "") for x in recommended_actions[:5] if str(x or "").strip()],
        "narrative_axis_policy": dict(payload.get("narrative_axis_policy") or narrative_axis_policy()),
    }


def _run_context_default(run_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "first_epoch": 0,
        "last_epoch": 0,
        "symbol": "",
        "action": "",
        "qty": 0,
        "execution_status": "UNKNOWN",
        "guard_status": "none",
        "guard_reason": "",
        "guard_reason_human": "none",
        "key_reason": "",
        "key_reason_raw": "",
        "technical_evidence": "",
        "sentiment_evidence": "",
        "policy_evidence": "",
        "news_status": {"symbol_sentiment_status": "", "global_sentiment_status": ""},
        "invalidation": {},
        "operator_intervention": [],
        "final_outcome": "",
        "risk_flags": [],
        "llm": {},
        "decision": {},
        "monitor_entry": {},
        "scanner_selection": {},
        "strategist_policy_resolution": {},
        "commander_route": {},
        "verdict": {},
        "execution": {},
        "strategy_frame": {},
    }


def _is_trade_story(story: Dict[str, Any]) -> bool:
    action = str(story.get("action") or "").strip().upper()
    status = str(story.get("execution_status") or "").strip().upper()
    guard_status = str(story.get("guard_status") or "").strip().lower()
    no_trade = story.get("no_trade_surface") if isinstance(story.get("no_trade_surface"), dict) else {}
    if action in ("BUY", "SELL"):
        return True
    if status in ("EXECUTED", "EXECUTED_OK", "EXECUTED_FAIL", "BLOCKED", "INTENT_ONLY"):
        return True
    if guard_status == "intervened":
        return True
    if str(no_trade.get("no_trade_stage") or "").strip() in {"guard_block", "pre_intent_wait", "pre_intent_noop"}:
        return True
    return False


def _decision_trace_inner(payload: Dict[str, Any]) -> Dict[str, Any]:
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    return inner if isinstance(inner, dict) else {}


def _build_run_contexts(day_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_run: Dict[str, Dict[str, Any]] = {}
    sorted_rows = sorted(day_rows, key=lambda r: int(r.get("_epoch") or 0))
    for row in sorted_rows:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        ctx = by_run.setdefault(run_id, _run_context_default(run_id))
        epoch = int(row.get("_epoch") or 0)
        if ctx["first_epoch"] <= 0 or epoch < int(ctx["first_epoch"]):
            ctx["first_epoch"] = epoch
        if epoch > int(ctx["last_epoch"]):
            ctx["last_epoch"] = epoch

        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}

        if stage == "strategist_llm" and event == "result":
            ctx["llm"] = dict(payload)
            continue

        if stage == "strategist" and event == "policy_resolution":
            ctx["strategist_policy_resolution"] = dict(payload)
            continue

        if stage == "decision" and event == "trace":
            packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
            trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
            intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
            why = packet.get("why") if isinstance(packet.get("why"), dict) else {}
            llm_ctx = trace.get("llm_context") if isinstance(trace.get("llm_context"), dict) else {}
            technical = why.get("technical") if isinstance(why.get("technical"), dict) else {}
            news = why.get("news") if isinstance(why.get("news"), dict) else {}
            policy = why.get("policy") if isinstance(why.get("policy"), dict) else {}
            if not technical:
                technical = llm_ctx.get("technical") if isinstance(llm_ctx.get("technical"), dict) else {}
            if not news:
                news = llm_ctx.get("news") if isinstance(llm_ctx.get("news"), dict) else {}
            if not policy:
                policy = llm_ctx.get("decision_policy") if isinstance(llm_ctx.get("decision_policy"), dict) else {}
            symbol_status = str(news.get("symbol_sentiment_status") or "").strip().lower()
            global_status = str(news.get("global_sentiment_status") or "").strip().lower()

            action = str(intent.get("action") or "").strip().upper()
            symbol = str(intent.get("symbol") or "").strip().upper()
            qty = _safe_int(intent.get("qty"), 0)

            if action:
                ctx["action"] = action
            if symbol:
                ctx["symbol"] = symbol
            if qty > 0:
                ctx["qty"] = qty

            reason_raw = _reason_text(intent, trace, ctx.get("llm") if isinstance(ctx.get("llm"), dict) else {})
            ctx["key_reason_raw"] = reason_raw
            ctx["key_reason"] = _humanize_reason(reason_raw)
            ctx["technical_evidence"] = _compact_kv_text(technical, topn=6)
            ctx["sentiment_evidence"] = _compact_kv_text(news, topn=6)
            ctx["policy_evidence"] = _compact_kv_text(policy, topn=6)
            ctx["invalidation"] = packet.get("invalidation") if isinstance(packet.get("invalidation"), dict) else {}
            ctx["news_status"] = {
                "symbol_sentiment_status": symbol_status,
                "global_sentiment_status": global_status,
            }
            if symbol_status and symbol_status != "ok":
                ctx["risk_flags"].append(f"symbol_sentiment_{symbol_status}")
            if global_status and global_status != "ok":
                ctx["risk_flags"].append(f"global_sentiment_{global_status}")
            ctx["decision"] = dict(payload)
            continue

        if stage == "decision_trace":
            inner = _decision_trace_inner(payload)

            if event == "strategic_frame":
                ctx["strategy_frame"] = dict(inner)
                if not str(ctx.get("key_reason_raw") or "").strip():
                    key_events = inner.get("key_events") if isinstance(inner.get("key_events"), list) else []
                    if key_events:
                        ctx["key_reason_raw"] = str(key_events[0])
                        ctx["key_reason"] = _humanize_reason(ctx["key_reason_raw"])
                continue

            if event == "candidate_selection":
                symbol = str(inner.get("selected_symbol") or "").strip().upper()
                if symbol:
                    ctx["symbol"] = symbol
                selected = inner.get("selected_candidate") if isinstance(inner.get("selected_candidate"), dict) else {}
                score_summary = inner.get("score_breakdown_summary") if isinstance(inner.get("score_breakdown_summary"), dict) else {}
                reason_raw = str(
                    selected.get("why")
                    or inner.get("candidate_source")
                    or ctx.get("key_reason_raw")
                    or ""
                ).strip()
                if reason_raw:
                    ctx["key_reason_raw"] = reason_raw
                    ctx["key_reason"] = _humanize_reason(reason_raw)
                if not str(ctx.get("technical_evidence") or "").strip():
                    technical_bits = {
                        "playbook": inner.get("playbook"),
                        "candidate_pool_size": inner.get("candidate_pool_size"),
                        "score_total": selected.get("score_total") or inner.get("top_score"),
                        "risk_score": selected.get("risk_score"),
                    }
                    if score_summary:
                        technical_bits["score_breakdown"] = _compact_kv_text(score_summary, topn=5)
                    ctx["technical_evidence"] = _compact_kv_text(technical_bits, topn=6)
                continue

            if event == "entry_exit_decision":
                symbol = str(inner.get("selected_symbol") or "").strip().upper()
                if symbol:
                    ctx["symbol"] = symbol
                exit_reason = str(inner.get("exit_reason") or "").strip()
                entry_reason = str(inner.get("entry_reason") or "").strip()
                reason_raw = exit_reason or entry_reason
                if reason_raw:
                    ctx["key_reason_raw"] = reason_raw
                    ctx["key_reason"] = _humanize_reason(reason_raw)
                thresholds = inner.get("thresholds") if isinstance(inner.get("thresholds"), dict) else {}
                if thresholds:
                    ctx["technical_evidence"] = _compact_kv_text(thresholds, topn=6)
                if bool(inner.get("min_hold_blocked")):
                    ctx["risk_flags"].append("min_hold_blocked")
                if bool(inner.get("sell_cooldown_blocked")):
                    ctx["risk_flags"].append("sell_cooldown_blocked")
                continue

        if stage == "scanner" and event == "candidate_selection_reason":
            ctx["scanner_selection"] = dict(payload)
            continue

        if stage == "scanner" and event == "selection_output":
            existing = ctx.get("scanner_selection") if isinstance(ctx.get("scanner_selection"), dict) else {}
            ctx["scanner_selection"] = {**dict(existing), **dict(payload)}
            continue

        if stage == "monitor" and event == "entry_decision_detail":
            ctx["monitor_entry"] = dict(payload)
            continue

        if stage == "commander_router" and event in {"route", "route_selected", "end"}:
            existing = ctx.get("commander_route") if isinstance(ctx.get("commander_route"), dict) else {}
            merged = {**dict(existing), **dict(payload)}
            route_obs = payload.get("route_observability") if isinstance(payload.get("route_observability"), dict) else {}
            if route_obs:
                merged.update(dict(route_obs))
            ctx["commander_route"] = merged
            continue

        if stage == "execute_from_packet" and event == "verdict":
            ctx["verdict"] = dict(payload)
            allowed = payload.get("allowed")
            if allowed is False:
                ctx["execution_status"] = "BLOCKED"
                ctx["guard_status"] = "intervened"
                ctx["guard_reason"] = str(payload.get("reason") or "blocked_by_guard")
                ctx["guard_reason_human"] = _humanize_reason(ctx.get("guard_reason"))
            continue

        if stage == "execute_from_packet" and event == "execution":
            order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
            ex_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            action = str(order.get("action") or "").strip().upper()
            symbol = str(order.get("symbol") or "").strip().upper()
            qty = _safe_int(order.get("qty"), 0)
            if action:
                ctx["action"] = action
            if symbol:
                ctx["symbol"] = symbol
            if qty > 0:
                ctx["qty"] = qty

            broker_ok = _broker_code_success(ex_payload.get("broker_code"))
            if broker_ok is True:
                ctx["execution_status"] = "EXECUTED_OK"
            elif broker_ok is False:
                ctx["execution_status"] = "EXECUTED_FAIL"
            else:
                ctx["execution_status"] = "EXECUTED"
            ctx["execution"] = dict(payload)
            continue

        if stage == "commander_router" and event == "intervention":
            p_type = str(payload.get("type") or "operator_intervention").strip()
            if p_type:
                ctx["operator_intervention"].append(p_type)
            continue

        if event == "error":
            st = str(row.get("stage") or "unknown").strip() or "unknown"
            ctx["risk_flags"].append(f"error:{st}")
            continue

        if stage == "commander_router" and event == "transition":
            transition = str(payload.get("transition") or "").strip().lower()
            if transition == "cooldown":
                ctx["risk_flags"].append("cooldown_transition")

    stories: List[Dict[str, Any]] = []
    for ctx in by_run.values():
        action = str(ctx.get("action") or "").strip().upper()
        if not action:
            llm = ctx.get("llm") if isinstance(ctx.get("llm"), dict) else {}
            action = str(llm.get("intent_action") or "").strip().upper()
            if action:
                ctx["action"] = action

        if not str(ctx.get("execution_status") or "").strip() or str(ctx.get("execution_status")) == "UNKNOWN":
            if str(ctx.get("guard_status")) == "intervened":
                ctx["execution_status"] = "BLOCKED"
            elif action == "NOOP":
                ctx["execution_status"] = "NOOP"
            elif action in ("BUY", "SELL"):
                ctx["execution_status"] = "INTENT_ONLY"
            else:
                ctx["execution_status"] = "UNKNOWN"

        if not str(ctx.get("guard_reason") or "").strip():
            ctx["guard_reason"] = "none"
        ctx["guard_reason_human"] = _humanize_reason(ctx.get("guard_reason") or "none")
        if not str(ctx.get("key_reason") or "").strip():
            llm = ctx.get("llm") if isinstance(ctx.get("llm"), dict) else {}
            raw_reason = str(llm.get("intent_reason") or llm.get("intent_rationale") or "unspecified")
            ctx["key_reason_raw"] = raw_reason

        normalized_reason = _normalize_reason_code(
            ctx.get("key_reason_raw"),
            action=str(ctx.get("action") or "").strip().upper(),
            execution_status=str(ctx.get("execution_status") or "").strip().upper(),
            guard_status=str(ctx.get("guard_status") or "").strip().lower(),
        )
        ctx["key_reason_raw"] = normalized_reason
        ctx["key_reason"] = _humanize_reason(normalized_reason)

        monitor_entry = ctx.get("monitor_entry") if isinstance(ctx.get("monitor_entry"), dict) else {}
        no_trade_surface = monitor_entry.get("no_trade_surface") if isinstance(monitor_entry.get("no_trade_surface"), dict) else {}
        scanner_handoff = monitor_entry.get("scanner_monitor_handoff") if isinstance(monitor_entry.get("scanner_monitor_handoff"), dict) else {}
        scanner_selection = ctx.get("scanner_selection") if isinstance(ctx.get("scanner_selection"), dict) else {}
        strategist_resolution = (
            ctx.get("strategist_policy_resolution") if isinstance(ctx.get("strategist_policy_resolution"), dict) else {}
        )
        commander_route = ctx.get("commander_route") if isinstance(ctx.get("commander_route"), dict) else {}
        if no_trade_surface:
            ctx["no_trade_surface"] = dict(no_trade_surface)
            dominant_blocker = str(no_trade_surface.get("dominant_blocker") or no_trade_surface.get("no_trade_reason_code") or "").strip()
            if dominant_blocker and normalized_reason in {"NO_CANDIDATE", "GUARD_BLOCK", "unspecified"}:
                ctx["key_reason_raw"] = dominant_blocker
                ctx["key_reason"] = _humanize_reason(dominant_blocker)
            ctx["decision_outcome"] = str(no_trade_surface.get("decision_outcome") or "")
            ctx["dominant_blocker"] = dominant_blocker
            ctx["near_ready_flag"] = bool(no_trade_surface.get("near_ready_flag"))
            ctx["distance_to_ready_text"] = _compact_distance_to_ready_text(no_trade_surface.get("distance_to_ready"))
            ctx["no_trade_summary"] = str(no_trade_surface.get("no_trade_reason_summary") or "")
        merged_handoff = _merge_scanner_handoff_with_selection(scanner_handoff, scanner_selection)
        if merged_handoff:
            ctx["scanner_monitor_handoff"] = merged_handoff
            if not str(ctx.get("symbol") or "").strip():
                ctx["symbol"] = str(
                    merged_handoff.get("scanner_selected_symbol")
                    or merged_handoff.get("selected_symbol")
                    or ""
                ).strip().upper()
        if strategist_resolution:
            ctx["strategist_policy_resolution"] = dict(strategist_resolution)
        if commander_route:
            ctx["commander_route"] = dict(commander_route)

        if not str(ctx.get("final_outcome") or "").strip():
            if str(ctx.get("execution_status")) == "EXECUTED_OK":
                ctx["final_outcome"] = "order accepted"
            elif str(ctx.get("execution_status")) == "EXECUTED_FAIL":
                ctx["final_outcome"] = "order rejected"
            elif str(ctx.get("execution_status")) == "BLOCKED":
                ctx["final_outcome"] = f"blocked:{ctx.get('guard_reason')}"
            elif no_trade_surface:
                ctx["final_outcome"] = str(no_trade_surface.get("no_trade_reason_summary") or "no trade")
            elif str(ctx.get("execution_status")) == "NOOP":
                ctx["final_outcome"] = "no trade"
            else:
                ctx["final_outcome"] = str(ctx.get("execution_status")).lower()

        if ctx.get("operator_intervention"):
            dedup = []
            seen = set()
            for item in ctx.get("operator_intervention") or []:
                s = str(item)
                if s and s not in seen:
                    seen.add(s)
                    dedup.append(s)
            ctx["operator_intervention"] = dedup

        risk_flags = [str(x) for x in (ctx.get("risk_flags") or []) if str(x).strip()]
        if str(ctx.get("execution_status")) == "EXECUTED_FAIL":
            risk_flags.append("broker_reject")
        if str(ctx.get("guard_status")) == "intervened":
            risk_flags.append("guard_block")
        ctx["risk_flags"] = sorted(set(risk_flags))

        stories.append(ctx)

    stories.sort(key=lambda x: int(x.get("first_epoch") or 0))
    return stories


def build_operator_daily_summary_payload(
    events_path: Path,
    report_dir: Path,
    *,
    day: Optional[str] = None,
    metrics_report_dir: Optional[Path] = None,
    m30_post_golive_dir: Optional[Path] = None,
    m30_golive_dir: Optional[Path] = None,
    m31_slo_incident_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for raw in _iter_jsonl(events_path):
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        rows.append({**raw, "_epoch": _to_epoch(ts), "_day": _utc_day(ts)})

    target_day = _pick_day(rows, day)
    day_rows = [r for r in rows if str(r.get("_day") or "") == target_day]
    canonical_report_root = _canonical_report_root(report_dir)
    route_summary = build_commander_route_summary(
        reports_root=canonical_report_root,
        day=target_day,
        day_rows=day_rows,
    )
    run_stories = _apply_commander_route_overlay(_build_run_contexts(day_rows), route_summary)
    freshness = _build_report_freshness(day_rows)

    metrics_dir = metrics_report_dir or (Path("reports") / "metrics")
    metrics = _load_or_build_metrics(events_path, metrics_dir, target_day)
    m30_post_dir = m30_post_golive_dir or (Path("reports") / "milestones" / "m30_post_golive")
    m30_go_dir = m30_golive_dir or (Path("reports") / "milestones" / "m30_golive")
    m31_dir = m31_slo_incident_dir or (Path("reports") / "m31_slo_incident")
    m30_policy = _find_day_artifact(m30_post_dir, "m30_post_golive_policy", target_day)
    m30_signoff = _find_day_artifact(m30_go_dir, "m30_final_golive_signoff", target_day)
    m31_slo = _find_day_artifact(m31_dir, "m31_slo_incident", target_day)

    action_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    blocked_reason_counts: Counter[str] = Counter()
    noop_reason_counts: Counter[str] = Counter()
    fallback_signal_status_counts: Counter[str] = Counter()
    stage_error_counts: Counter[str] = Counter()
    executions_ok = 0
    executions_fail = 0
    executions_total = 0
    operator_intervention_total = 0
    cooldown_transition_total = 0
    duplicate_execution_total = 0
    guard_precedence_violation_total = 0

    for row in day_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        payload_text = json.dumps(payload, ensure_ascii=False).lower()

        if stage == "decision" and event == "trace":
            packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
            intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
            action = str(intent.get("action") or "").strip().upper()
            if action:
                action_counts[action] += 1
            trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
            strategy = str(trace.get("strategy") or "").strip()
            if strategy:
                strategy_counts[strategy] += 1
        if stage == "decision_trace" and event == "strategic_frame":
            inner = _decision_trace_inner(payload)
            strategy = str(inner.get("playbook") or inner.get("market_regime") or "").strip()
            if strategy:
                strategy_counts[strategy] += 1

        if stage == "execute_from_packet" and event == "verdict" and payload.get("allowed") is False:
            blocked_reason_counts[str(payload.get("reason") or "blocked")] += 1

        if stage == "execute_from_packet" and event == "execution":
            executions_total += 1
            ex_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            broker_ok = _broker_code_success(ex_payload.get("broker_code"))
            if broker_ok is True:
                executions_ok += 1
            elif broker_ok is False:
                executions_fail += 1

        if stage == "commander_router" and event == "intervention":
            operator_intervention_total += 1
        if stage == "commander_router" and event == "transition":
            if str(payload.get("transition") or "").strip().lower() == "cooldown":
                cooldown_transition_total += 1

        if event == "error":
            stage_error_counts[str(stage or "unknown")] += 1
        if "duplicate_execution" in payload_text:
            duplicate_execution_total += 1
        if "guard_precedence_violation" in payload_text:
            guard_precedence_violation_total += 1

    metrics_exec = metrics.get("execution") if isinstance(metrics.get("execution"), dict) else {}
    metrics_broker = metrics.get("broker_api") if isinstance(metrics.get("broker_api"), dict) else {}
    metrics_commander = metrics.get("commander_resilience") if isinstance(metrics.get("commander_resilience"), dict) else {}

    intents_created = _safe_int(metrics_exec.get("intents_created"), 0)
    intents_blocked = _safe_int(metrics_exec.get("intents_blocked"), 0)
    blocked_rate = (float(intents_blocked) / float(intents_created)) if intents_created > 0 else 0.0
    api_429_rate = _safe_float(metrics_broker.get("api_429_rate"), 0.0)

    issues: List[Dict[str, str]] = []
    health = "GREEN"

    def _raise_health(level: str) -> None:
        nonlocal health
        order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
        if order.get(level, 0) > order.get(health, 0):
            health = level

    if duplicate_execution_total > 0:
        _raise_health("RED")
        issues.append({"code": "duplicate_execution_detected", "severity": "RED", "detail": f"duplicate_execution={duplicate_execution_total}"})
    if guard_precedence_violation_total > 0:
        _raise_health("RED")
        issues.append({"code": "guard_precedence_violation", "severity": "RED", "detail": f"guard_precedence_violation={guard_precedence_violation_total}"})
    if api_429_rate > 0.20:
        _raise_health("YELLOW")
        issues.append({"code": "high_api_error_rate", "severity": "YELLOW", "detail": f"api_429_rate={api_429_rate:.2%}"})
    if intents_created >= 5 and blocked_rate > 0.60:
        _raise_health("YELLOW")
        issues.append({"code": "excessive_blocked_orders", "severity": "YELLOW", "detail": f"blocked_rate={blocked_rate:.2%} ({intents_blocked}/{intents_created})"})

    escalation_level = str(m30_policy.get("escalation_level") or "").strip().lower()
    if escalation_level == "incident":
        _raise_health("RED")
        issues.append({"code": "policy_escalation_incident", "severity": "RED", "detail": "m30_post_golive escalation_level=incident"})
    elif escalation_level == "watch":
        _raise_health("YELLOW")
        issues.append({"code": "policy_escalation_watch", "severity": "YELLOW", "detail": "m30_post_golive escalation_level=watch"})

    if m31_slo and not bool(m31_slo.get("ok")):
        _raise_health("RED")
        issues.append({"code": "slo_incident_gate_failed", "severity": "RED", "detail": f"m31_slo_incident failure_total={_safe_int(m31_slo.get('failure_total'), 0)}"})
    if not issues:
        issues.append({"code": "none", "severity": "GREEN", "detail": "no critical or warning issues detected"})

    recommended_actions: List[str] = []
    issue_codes = {str(i.get("code") or "") for i in issues}
    if "duplicate_execution_detected" in issue_codes or "guard_precedence_violation" in issue_codes:
        recommended_actions.append("Pause auto execution and run guard/idempotency diagnostic checks before next session.")
    if "high_api_error_rate" in issue_codes:
        recommended_actions.append("Lower request burst, verify broker/API quota, and inspect 429 retry configuration.")
    if "excessive_blocked_orders" in issue_codes:
        recommended_actions.append("Review allowlist, notional limits, and decision thresholds causing frequent guard blocks.")
    if "policy_escalation_incident" in issue_codes:
        recommended_actions.append("Switch to manual approval only and complete incident review with clear owner/action items.")
    if "none" in issue_codes:
        recommended_actions.append("Continue current configuration and monitor next session for regression signals.")
    if not recommended_actions:
        recommended_actions.append("Inspect top issues and run closeout checks before enabling broader automation.")

    top_block_reason = blocked_reason_counts.most_common(1)
    run_total = len({str(r.get("run_id") or "").strip() for r in day_rows if str(r.get("run_id") or "").strip()})
    blocked_total = int(sum(int(v) for v in blocked_reason_counts.values()))
    llm_success_rate = _safe_float((metrics.get("strategist_llm") if isinstance(metrics.get("strategist_llm"), dict) else {}).get("success_rate"), 0.0)

    for story in run_stories:
        action = str(story.get("action") or "").strip().upper()
        execution_status = str(story.get("execution_status") or "").strip().upper()
        if action == "NOOP" or execution_status == "NOOP":
            reason_raw = str(story.get("key_reason_raw") or story.get("key_reason") or "unspecified").strip() or "unspecified"
            noop_reason_counts[reason_raw] += 1
        news_status = story.get("news_status") if isinstance(story.get("news_status"), dict) else {}
        symbol_status = str(news_status.get("symbol_sentiment_status") or "").strip().lower()
        global_status = str(news_status.get("global_sentiment_status") or "").strip().lower()
        if symbol_status and symbol_status != "ok":
            fallback_signal_status_counts[f"symbol_sentiment_status:{symbol_status}"] += 1
        if global_status and global_status != "ok":
            fallback_signal_status_counts[f"global_sentiment_status:{global_status}"] += 1

    blocked_reason_top_human = _render_reason_top(blocked_reason_counts, topn=5)
    noop_reason_top_human = _render_reason_top(noop_reason_counts, topn=5)
    fallback_signal_status_top = _render_reason_top(fallback_signal_status_counts, topn=5)

    if not action_counts:
        for story in run_stories:
            action = str(story.get("action") or "").strip().upper()
            if action:
                action_counts[action] += 1

    summary_lines = [
        f"{_health_badge(health)} runs={run_total}, executions={executions_total} (ok={executions_ok}, fail={executions_fail}), blocks={blocked_total}.",
        f"Top guard block: {_humanize_reason(top_block_reason[0][0])} ({top_block_reason[0][1]})" if top_block_reason else "Top guard block: none",
        f"LLM success_rate={llm_success_rate:.2%}, interventions={operator_intervention_total}, cooldowns={cooldown_transition_total}.",
    ]
    route_selected_total = dict(route_summary.get("route_selected_total") or {})
    if route_selected_total:
        summary_lines.append(f"Route source={route_summary.get('route_source') or 'canonical_commander_preferred'} route_total={json.dumps(route_selected_total, ensure_ascii=False)}")
    summary_lines.append("Narrative display policy: exit-first for SELL/EXIT, entry-first for BUY/WAIT/NO_TRADE.")

    reasoning_lines = [str(i.get("detail") or "") for i in issues if str(i.get("detail") or "").strip()]
    system_health_status = {"system_health_level": health, "reasoning": reasoning_lines, "recommended_action": recommended_actions[:3]}

    out: Dict[str, Any] = {
        "schema_version": "operator_summary.v1",
        "day": target_day,
        "generated_at": freshness["generated_at"],
        "source_run_count": int(freshness["source_run_count"]),
        "latest_run_id": freshness["latest_run_id"],
        "latest_run_ts": freshness["latest_run_ts"],
        "data_freshness": build_data_freshness(
            generated_at=freshness["generated_at"],
            source_run_count=freshness["source_run_count"],
            latest_run_id=freshness["latest_run_id"],
            latest_run_ts=freshness["latest_run_ts"],
            stale=False,
        ),
        "inputs": {
            "event_log_path": str(events_path),
            "metrics_json_path": str((metrics_dir / f"metrics_{target_day}.json")),
            "m30_post_golive_json_path": str((m30_post_dir / f"m30_post_golive_policy_{target_day}.json")),
            "m30_golive_json_path": str((m30_go_dir / f"m30_final_golive_signoff_{target_day}.json")),
            "m31_slo_incident_json_path": str((m31_dir / f"m31_slo_incident_{target_day}.json")),
        },
        "executive_summary": {"system_status": health, "summary_lines": summary_lines},
        "system_health_status": system_health_status,
        "trading_activity_summary": {
            "run_total": int(run_total),
            "decision_action_counts": dict(action_counts),
            "strategy_counts": dict(strategy_counts),
            "executions_total": int(executions_total),
            "executions_ok_total": int(executions_ok),
            "executions_fail_total": int(executions_fail),
            "blocked_total": int(blocked_total),
            "blocked_reason_top": dict(blocked_reason_counts.most_common(5)),
            "blocked_reason_top_human": blocked_reason_top_human,
            "noop_reason_top_human": noop_reason_top_human,
            "fallback_signal_status_top_human": fallback_signal_status_top,
        },
        "route_summary": {
            "route_source": str(route_summary.get("route_source") or "canonical_commander_preferred"),
            "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
            "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
            "route_source_breakdown": dict(route_summary.get("route_source_breakdown") or {}),
            "route_selected_total": dict(route_summary.get("route_selected_total") or {}),
            "strategy_generation_mode_total": dict(route_summary.get("strategy_generation_mode_total") or {}),
            "strategist_fallback_total": int(route_summary.get("strategist_fallback_total") or 0),
        },
        "route_provenance": build_route_provenance(route_summary),
        "safety_guard_interventions": {
            "blocked_total": int(blocked_total),
            "blocked_reason_top": dict(blocked_reason_counts.most_common(5)),
            "blocked_reason_top_human": blocked_reason_top_human,
            "operator_intervention_total": int(operator_intervention_total),
            "cooldown_transition_total": int(cooldown_transition_total),
            "duplicate_execution_total": int(duplicate_execution_total),
            "guard_precedence_violation_total": int(guard_precedence_violation_total),
        },
        "top_issues": issues[:10],
        "recommended_operator_actions": recommended_actions[:5],
        "narrative_axis_policy": narrative_axis_policy(),
        "raw_snapshot": {
            "metrics_execution": metrics_exec,
            "metrics_commander_resilience": metrics_commander,
            "metrics_broker_api": metrics_broker,
            "m30_post_golive": m30_policy,
            "m30_golive": m30_signoff,
            "m31_slo_incident": m31_slo,
            "stage_error_top": dict(stage_error_counts.most_common(5)),
            "run_story_total": len(run_stories),
        },
    }

    policy_snapshot = build_policy_surface_quality_snapshot(events_path, canonical_report_root, target_day)
    policy_surface_executive_summary = dict(policy_snapshot.get("executive_summary") or {})
    chart_structure_decision_hint_executive_summary = dict(policy_snapshot.get("chart_structure_executive_summary") or {})
    executive_headline = str(policy_surface_executive_summary.get("headline") or "").strip()
    chart_structure_headline = str(chart_structure_decision_hint_executive_summary.get("headline") or "").strip()
    if executive_headline:
        out["executive_summary"]["summary_lines"].append(executive_headline)
    if chart_structure_headline:
        out["executive_summary"]["summary_lines"].append(chart_structure_headline)
    out["policy_surface_quality_summary"] = dict(policy_snapshot.get("summary") or {})
    out["policy_surface_quality_executive_summary"] = policy_surface_executive_summary
    out["chart_structure_decision_hint_summary"] = dict(policy_snapshot.get("chart_structure_summary") or {})
    out["chart_structure_decision_hint_executive_summary"] = chart_structure_decision_hint_executive_summary
    out["policy_surface_quality_source"] = dict(policy_snapshot.get("source") or {})
    out["chart_structure_decision_hint_source"] = dict(policy_snapshot.get("source") or {})
    return out


def generate_operator_daily_summary(
    events_path: Path,
    report_dir: Path,
    *,
    day: Optional[str] = None,
    metrics_report_dir: Optional[Path] = None,
    m30_post_golive_dir: Optional[Path] = None,
    m30_golive_dir: Optional[Path] = None,
    m31_slo_incident_dir: Optional[Path] = None,
) -> Tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    out = build_operator_daily_summary_payload(
        events_path,
        report_dir,
        day=day,
        metrics_report_dir=metrics_report_dir,
        m30_post_golive_dir=m30_post_golive_dir,
        m30_golive_dir=m30_golive_dir,
        m31_slo_incident_dir=m31_slo_incident_dir,
    )

    target_day = str(out.get("day") or day or "")
    canonical_report_root = _canonical_report_root(report_dir)
    paths = daily_artifact_paths(canonical_report_root, target_day)
    js_path = paths["operator_summary_json"]
    md_path = paths["operator_summary_md"]
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    health = str((out.get("executive_summary") if isinstance(out.get("executive_summary"), dict) else {}).get("system_status") or "UNKNOWN")
    system_health_status = out.get("system_health_status") if isinstance(out.get("system_health_status"), dict) else {}
    reasoning_lines = list(system_health_status.get("reasoning") or [])

    md_lines = [
        f"# Operator Daily Summary ({target_day})",
        "",
    ]
    md_lines += render_data_freshness_markdown(out.get("data_freshness") if isinstance(out.get("data_freshness"), dict) else {})
    md_lines += [
        "",
        "## Executive Summary",
        "",
        f"- system_status: **{_health_badge(health)}**",
    ]
    for line in list(((out.get("executive_summary") if isinstance(out.get("executive_summary"), dict) else {}).get("summary_lines") or [])):
        md_lines.append(f"- {line}")

    md_lines += ["", "## Top Issues", ""]
    for issue in list(out.get("top_issues") or []):
        if not isinstance(issue, dict):
            continue
        md_lines.append(f"- [{issue.get('severity')}] {issue.get('code')}: {_humanize_reason(issue.get('detail') or issue.get('code'))}")

    md_lines += ["", "## Recommended Operator Actions", ""]
    for action in list(out.get("recommended_operator_actions") or []):
        md_lines.append(f"- {action}")

    md_lines += [
        "",
        "## System Health Status",
        "",
        f"- system_health_level: **{_health_badge(system_health_status.get('system_health_level') or 'UNKNOWN')}**",
        "- reasoning:",
    ]
    if reasoning_lines:
        for line in reasoning_lines[:5]:
            md_lines.append(f"  - {line}")
    else:
        md_lines.append("  - (none)")
    md_lines.append("- recommended_action:")
    for line in list(system_health_status.get("recommended_action") or []):
        md_lines.append(f"  - {line}")

    tas = out.get("trading_activity_summary") if isinstance(out.get("trading_activity_summary"), dict) else {}
    route_summary = out.get("route_summary") if isinstance(out.get("route_summary"), dict) else {}
    md_lines += [
        "",
        "## Trading Activity Summary",
        "",
        f"- run_total: **{tas.get('run_total') or 0}**",
        f"- decision_action_counts: `{json.dumps(tas.get('decision_action_counts') or {}, ensure_ascii=False)}`",
        f"- strategy_counts: `{json.dumps(tas.get('strategy_counts') or {}, ensure_ascii=False)}`",
        f"- executions_total: **{tas.get('executions_total') or 0}**",
        f"- blocked_total: **{tas.get('blocked_total') or 0}**",
        f"- noop_reason_top_human: {_format_reason_rows(list(tas.get('noop_reason_top_human') or []))}",
        f"- fallback_signal_status_top_human: {_format_reason_rows(list(tas.get('fallback_signal_status_top_human') or []))}",
        "",
        "## Route Provenance",
        "",
        f"- route_source: `{route_summary.get('route_source') or '-'}`",
        f"- route_source_run_count: **{int(route_summary.get('route_source_run_count') or 0)}**",
        f"- route_source_missing_count: **{int(route_summary.get('route_source_missing_count') or 0)}**",
        f"- route_source_breakdown: `{json.dumps(route_summary.get('route_source_breakdown') or {}, ensure_ascii=False)}`",
        f"- route_selected_total: `{json.dumps(route_summary.get('route_selected_total') or {}, ensure_ascii=False)}`",
        f"- strategy_generation_mode_total: `{json.dumps(route_summary.get('strategy_generation_mode_total') or {}, ensure_ascii=False)}`",
    ]

    sgi = out.get("safety_guard_interventions") if isinstance(out.get("safety_guard_interventions"), dict) else {}
    md_lines += [
        "",
        "## Safety Guard Interventions",
        "",
        f"- blocked_total: **{sgi.get('blocked_total') or 0}**",
        f"- blocked_reason_top_human: {_format_reason_rows(list(sgi.get('blocked_reason_top_human') or []))}",
        f"- operator_intervention_total: **{sgi.get('operator_intervention_total') or 0}**",
        f"- cooldown_transition_total: **{sgi.get('cooldown_transition_total') or 0}**",
        f"- duplicate_execution_total: **{sgi.get('duplicate_execution_total') or 0}**",
        f"- guard_precedence_violation_total: **{sgi.get('guard_precedence_violation_total') or 0}**",
        "",
    ]
    narrative_policy = out.get("narrative_axis_policy") if isinstance(out.get("narrative_axis_policy"), dict) else {}
    md_lines += [
        "## Narrative Axis Policy",
        "",
        f"- entry_primary_for: `{narrative_policy.get('entry_primary_for') or []}`",
        f"- exit_primary_for: `{narrative_policy.get('exit_primary_for') or []}`",
        f"- mixed_only_for_ambiguous_cases: **{bool(narrative_policy.get('mixed_only_for_ambiguous_cases'))}**",
        f"- runtime_semantics_unchanged: **{bool(narrative_policy.get('runtime_semantics_unchanged'))}**",
        "",
    ]

    policy_surface_executive_summary = out.get("policy_surface_quality_executive_summary") if isinstance(out.get("policy_surface_quality_executive_summary"), dict) else {}
    chart_structure_decision_hint_executive_summary = out.get("chart_structure_decision_hint_executive_summary") if isinstance(out.get("chart_structure_decision_hint_executive_summary"), dict) else {}
    executive_headline = str(policy_surface_executive_summary.get("headline") or "").strip()
    chart_structure_headline = str(chart_structure_decision_hint_executive_summary.get("headline") or "").strip()
    if executive_headline:
        md_lines += ["", "## Policy Surface Executive Summary", "", f"- status: **{str(policy_surface_executive_summary.get('status') or 'unknown').upper()}**", f"- headline: {executive_headline}"]
    if chart_structure_headline:
        md_lines += ["", "## Chart Structure Decision Hint Executive Summary", "", f"- status: **{str(chart_structure_decision_hint_executive_summary.get('status') or 'unknown').upper()}**", f"- headline: {chart_structure_headline}"]
        chart_structure_examples = chart_structure_decision_hint_executive_summary.get("applied_examples") if isinstance(chart_structure_decision_hint_executive_summary.get("applied_examples"), list) else []
        if chart_structure_examples:
            md_lines += ["", "## Chart Structure Decision Hint Applied Examples", ""]
            for example in chart_structure_examples[:3]:
                if not isinstance(example, dict):
                    continue
                md_lines.append(
                    f"- `{example.get('run_id') or '-'}` "
                    f"[{str(example.get('entry_style') or '-').upper()}] "
                    f"{example.get('reason_transition') or '-'} "
                    f"blockers=`{json.dumps(example.get('blocking_features') or [], ensure_ascii=False)}`"
                )

    js_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return md_path, js_path


def generate_decision_story_report(
    events_path: Path,
    report_dir: Path,
    *,
    day: Optional[str] = None,
    max_runs: Optional[int] = 120,
    trade_only: bool = True,
) -> Tuple[Path, Dict[str, Any]]:
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for raw in _iter_jsonl(events_path):
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        rows.append({**raw, "_epoch": _to_epoch(ts), "_day": _utc_day(ts)})

    target_day = _pick_day(rows, day)
    day_rows = [r for r in rows if str(r.get("_day") or "") == target_day]
    route_summary = build_commander_route_summary(
        reports_root=_canonical_report_root(report_dir),
        day=target_day,
        day_rows=day_rows,
    )
    stories_all = _apply_commander_route_overlay(_build_run_contexts(day_rows), route_summary)
    freshness = _build_report_freshness(day_rows)
    if bool(trade_only):
        stories_all = [s for s in stories_all if _is_trade_story(s)]
    limit = int(max_runs or 0)
    stories = stories_all[:limit] if limit > 0 else stories_all

    md_lines = [f"# Decision Story Report ({target_day})", ""]
    md_lines += render_data_freshness_markdown(
        build_data_freshness(
            generated_at=freshness["generated_at"],
            source_run_count=freshness["source_run_count"],
            latest_run_id=freshness["latest_run_id"],
            latest_run_ts=freshness["latest_run_ts"],
            stale=False,
        )
    )
    md_lines += [
        f"- story_total: **{int(len(stories_all))}**",
        f"- rendered_story_total: **{int(len(stories))}**",
    ]
    if len(stories) < len(stories_all):
        md_lines.append(f"- note: output truncated to first {len(stories)} runs")
    md_lines.append("")

    if not stories:
        md_lines += ["No decision stories found.", ""]
    else:
        for s in stories:
            action = str(s.get("action") or "UNKNOWN")
            qty = _safe_int(s.get("qty"), 0)
            final_action = f"{action} {qty}" if (qty > 0 and action in ("BUY", "SELL")) else action
            operator_int = s.get("operator_intervention") if isinstance(s.get("operator_intervention"), list) else []
            no_trade = s.get("no_trade_surface") if isinstance(s.get("no_trade_surface"), dict) else {}
            handoff = s.get("scanner_monitor_handoff") if isinstance(s.get("scanner_monitor_handoff"), dict) else {}
            strategist_resolution = s.get("strategist_policy_resolution") if isinstance(s.get("strategist_policy_resolution"), dict) else {}
            commander_route = s.get("commander_route") if isinstance(s.get("commander_route"), dict) else {}
            explanation = _story_explanation(s)
            md_lines += [
                f"## Run {s.get('run_id')}",
                "",
                f"- run_id: `{s.get('run_id')}`",
                f"- symbol: **{s.get('symbol') or 'N/A'}**",
                f"- final_action: **{final_action}**",
                f"- execution_status: **{s.get('execution_status')}**",
                f"- final_outcome: {s.get('final_outcome') or '-'}",
                f"- decision_axis: {explanation.get('axis') or '-'}",
                f"- primary_explanation: {explanation.get('primary_summary') or '-'}",
                f"- explanation_mode: {explanation.get('explanation_mode') or '-'}",
                f"- explanation_source: {explanation.get('explanation_source') or '-'}",
                f"- narrative_order: {explanation.get('narrative_order_text') or '-'}",
                f"- narrative_consistency_flag: {bool(explanation.get('narrative_consistency_flag'))}",
                f"- pre_intent_decision: {str(no_trade.get('pre_intent_decision') or '-')}",
                f"- guard_decision: {str(no_trade.get('no_trade_stage') or '-')}",
                f"- decision_reason_summary: {s.get('key_reason') or _humanize_reason('unspecified')}",
                f"- entry_narrative: {explanation.get('entry_narrative') or '-'}",
                f"- exit_narrative: {explanation.get('exit_narrative') or '-'}",
                f"- why_not_buy_summary: {explanation.get('why_not_buy_summary') or '-'}",
                f"- why_exit_summary: {explanation.get('exit_trigger_basis') if explanation.get('axis') == 'exit' else '-'}",
                f"- dominant_blocker: {explanation.get('dominant_blocker') or '-'}",
                f"- entry_context_blocker: {explanation.get('entry_context_blocker') if explanation.get('axis') == 'exit' else '-'}",
                f"- distance_to_ready: {explanation.get('distance_to_ready') or '-'}",
                f"- technical_evidence: {s.get('technical_evidence') or '-'}",
                f"- sentiment_evidence: {s.get('sentiment_evidence') or '-'}",
                f"- scanner_monitor_handoff: top1={handoff.get('scanner_selected_symbol') or '-'} "
                f"(rank={handoff.get('scanner_rank') or '-'}) -> "
                f"alignment={handoff.get('scanner_vs_monitor_alignment') or '-'} / "
                f"monitor_reason={handoff.get('monitor_rejection_reason_code') or '-'}",
                f"- strategist_provenance: mode={strategist_resolution.get('strategy_generation_mode') or '-'} / "
                f"llm_ok={strategist_resolution.get('llm_ok')} / "
                f"fallback_used={strategist_resolution.get('fallback_used')} / "
                f"fallback_source={strategist_resolution.get('fallback_source') or '-'}",
                f"- commander_route_provenance: route={commander_route.get('route_selected') or '-'} / "
                f"call_decision={commander_route.get('strategist_call_decision') or '-'} / "
                f"call_reason={commander_route.get('strategist_call_reason') or commander_route.get('strategist_skip_reason') or '-'} / "
                f"source={commander_route.get('route_source') or '-'}",
                f"- guard_intervention: {s.get('guard_reason_human') or _humanize_reason(s.get('guard_reason') or 'none')}",
                f"- operator_intervention: {', '.join(operator_int) if operator_int else 'none'}",
                "",
            ]

    md_path = report_dir / f"decision_story_{target_day}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    out = {
        "schema_version": "decision_story.v1",
        "day": target_day,
        "generated_at": freshness["generated_at"],
        "source_run_count": int(freshness["source_run_count"]),
        "latest_run_id": freshness["latest_run_id"],
        "latest_run_ts": freshness["latest_run_ts"],
        "data_freshness": build_data_freshness(
            generated_at=freshness["generated_at"],
            source_run_count=freshness["source_run_count"],
            latest_run_id=freshness["latest_run_id"],
            latest_run_ts=freshness["latest_run_ts"],
            stale=False,
        ),
        "route_source": str(route_summary.get("route_source") or "canonical_commander_preferred"),
        "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
        "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
        "route_provenance": build_route_provenance(route_summary),
        "story_total": int(len(stories_all)),
        "rendered_story_total": int(len(stories)),
        "truncated": bool(len(stories) < len(stories_all)),
        "trade_only": bool(trade_only),
        "report_md_path": str(md_path),
    }
    return md_path, out


def generate_run_card_report(
    events_path: Path,
    report_dir: Path,
    *,
    day: Optional[str] = None,
    max_runs: Optional[int] = 120,
    trade_only: bool = True,
) -> Tuple[Path, Dict[str, Any]]:
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for raw in _iter_jsonl(events_path):
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        rows.append({**raw, "_epoch": _to_epoch(ts), "_day": _utc_day(ts)})

    target_day = _pick_day(rows, day)
    day_rows = [r for r in rows if str(r.get("_day") or "") == target_day]
    route_summary = build_commander_route_summary(
        reports_root=_canonical_report_root(report_dir),
        day=target_day,
        day_rows=day_rows,
    )
    stories_all = _apply_commander_route_overlay(_build_run_contexts(day_rows), route_summary)
    freshness = _build_report_freshness(day_rows)
    if bool(trade_only):
        stories_all = [s for s in stories_all if _is_trade_story(s)]
    stories_all = sorted(stories_all, key=lambda s: int(s.get("first_epoch") or 0))
    limit = int(max_runs or 0)
    stories = stories_all[:limit] if limit > 0 else stories_all

    lines = [f"# Run Cards ({target_day})", ""]
    lines += render_data_freshness_markdown(
        build_data_freshness(
            generated_at=freshness["generated_at"],
            source_run_count=freshness["source_run_count"],
            latest_run_id=freshness["latest_run_id"],
            latest_run_ts=freshness["latest_run_ts"],
            stale=False,
        )
    )
    lines += [
        f"- card_total: **{int(len(stories_all))}**",
        f"- rendered_card_total: **{int(len(stories))}**",
    ]
    if len(stories) < len(stories_all):
        lines.append(f"- note: output truncated to first {len(stories)} runs")
    lines.append("")

    if not stories:
        lines += ["No run cards found.", ""]
    else:
        for s in stories:
            risk_flags = s.get("risk_flags") if isinstance(s.get("risk_flags"), list) else []
            risk_text = ", ".join(str(x) for x in risk_flags) if risk_flags else "none"
            action = str(s.get("action") or "UNKNOWN")
            qty = max(0, _safe_int(s.get("qty"), 0))
            action_text = f"{action} {qty}" if (action in ("BUY", "SELL") and qty > 0) else action
            no_trade = s.get("no_trade_surface") if isinstance(s.get("no_trade_surface"), dict) else {}
            handoff = s.get("scanner_monitor_handoff") if isinstance(s.get("scanner_monitor_handoff"), dict) else {}
            strategist_resolution = s.get("strategist_policy_resolution") if isinstance(s.get("strategist_policy_resolution"), dict) else {}
            commander_route = s.get("commander_route") if isinstance(s.get("commander_route"), dict) else {}
            explanation = _story_explanation(s)
            lines += [
                f"Run: {s.get('run_id')}",
                f"Symbol: {s.get('symbol') or 'N/A'}",
                f"Route: {commander_route.get('route_selected') or '-'}",
                f"Route Source: {commander_route.get('route_source') or '-'}",
                f"Decision Axis: {explanation.get('axis') or '-'}",
                f"Scanner Top-1: {(handoff.get('scanner_selected_symbol') or '-')}/{handoff.get('scanner_score_total') if handoff else '-'}",
                f"Monitor Outcome: {no_trade.get('decision_outcome') or s.get('execution_status') or '-'}",
                f"Primary Explanation: {explanation.get('primary_summary') or '-'}",
                f"Narrative Order: {explanation.get('narrative_order_text') or '-'}",
                f"Entry Narrative: {explanation.get('entry_narrative') or '-'}",
                f"Exit Narrative: {explanation.get('exit_narrative') or '-'}",
                f"Dominant Blocker: {explanation.get('dominant_blocker') or '-'}",
                f"Entry Context Blocker: {explanation.get('entry_context_blocker') if explanation.get('axis') == 'exit' else '-'}",
                f"Near Ready: {bool(no_trade.get('near_ready_flag'))}",
                f"Strategist Mode: {strategist_resolution.get('strategy_generation_mode') or '-'}",
                f"Action: {action_text}",
                f"Status: {s.get('execution_status')}",
                f"Guard: {s.get('guard_status')} ({s.get('guard_reason_human') or _humanize_reason(s.get('guard_reason') or 'none')})",
                f"Reason: {s.get('key_reason') or _humanize_reason('unspecified')}",
                f"Risk Flags: {risk_text}",
                "",
            ]

    md_path = report_dir / f"run_cards_{target_day}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    out = {
        "schema_version": "run_cards.v1",
        "day": target_day,
        "generated_at": freshness["generated_at"],
        "source_run_count": int(freshness["source_run_count"]),
        "latest_run_id": freshness["latest_run_id"],
        "latest_run_ts": freshness["latest_run_ts"],
        "data_freshness": build_data_freshness(
            generated_at=freshness["generated_at"],
            source_run_count=freshness["source_run_count"],
            latest_run_id=freshness["latest_run_id"],
            latest_run_ts=freshness["latest_run_ts"],
            stale=False,
        ),
        "route_source": str(route_summary.get("route_source") or "canonical_commander_preferred"),
        "route_source_run_count": int(route_summary.get("route_source_run_count") or 0),
        "route_source_missing_count": int(route_summary.get("route_source_missing_count") or 0),
        "route_provenance": build_route_provenance(route_summary),
        "card_total": int(len(stories_all)),
        "rendered_card_total": int(len(stories)),
        "truncated": bool(len(stories) < len(stories_all)),
        "trade_only": bool(trade_only),
        "report_md_path": str(md_path),
    }
    return md_path, out


def generate_operator_visibility_bundle(
    *,
    events_path: Path,
    report_root: Path,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    summary_md, summary_js = generate_operator_daily_summary(
        events_path,
        report_root / "operator_summary",
        day=day,
        metrics_report_dir=report_root / "metrics",
        m30_post_golive_dir=report_root / "milestones" / "m30_post_golive",
        m30_golive_dir=report_root / "milestones" / "m30_golive",
        m31_slo_incident_dir=report_root / "m31_slo_incident",
    )
    summary_obj = _read_json(summary_js)
    target_day = str(summary_obj.get("day") or day or "")

    decision_md, decision_obj = generate_decision_story_report(
        events_path,
        report_root / "decision_story",
        day=target_day or day,
    )
    run_cards_md, run_cards_obj = generate_run_card_report(
        events_path,
        report_root / "run_cards",
        day=target_day or day,
    )

    return {
        "day": target_day or (day or ""),
        "operator_summary_md": str(summary_md),
        "operator_summary_json": str(summary_js),
        "decision_story_md": str(decision_md),
        "decision_story_total": int(decision_obj.get("story_total") or 0),
        "run_cards_md": str(run_cards_md),
        "run_card_total": int(run_cards_obj.get("card_total") or 0),
    }


def build_separated_operator_brief(trade_dir: str, symbol: str, trades_root: str, *, model: Optional[str] = None) -> Dict[str, Any]:
    """Phase 6-1 Task 4: Fact/Narrative separated operator brief."""
    from libs.reporting.trade_read_model import build_trade_read_model
    from libs.reporting.symbol_read_model import build_symbol_read_model
    from libs.reporting.fact_narrative_report import build_separated_report
    
    try:
        trade_model = build_trade_read_model(str(trade_dir))
    except Exception:
        trade_model = {}
    try:
        symbol_model = build_symbol_read_model(str(trades_root), str(symbol))
    except Exception:
        symbol_model = {}
    llm_scope = trade_model if isinstance(trade_model, dict) and trade_model else symbol_model
    chosen_model = normalize_openrouter_model_name(
        str(model or "").strip()
        or str(resolve_policy_llm_slot(llm_scope if isinstance(llm_scope, dict) else {}, "reporter", "intraday", default_profile="fast_free").get("primary") or "").strip()
        or "minimax/minimax-m2.5"
    )
    execution_profile = resolve_policy_llm_execution_slot(
        llm_scope if isinstance(llm_scope, dict) else {},
        "reporter",
        "intraday",
        default_profile="concise_review",
        defaults={
            "profile_name": "concise_review",
            "name": "concise_review",
            "temperature": 0.2,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {"max_attempts": 2, "backoff_sec": 0.0},
            "retry_max": 2,
            "retry_backoff_sec": 0.0,
        },
    )
    return build_separated_report(
        trade_model=trade_model,
        symbol_model=symbol_model,
        model=chosen_model,
        execution_profile=execution_profile,
    )
