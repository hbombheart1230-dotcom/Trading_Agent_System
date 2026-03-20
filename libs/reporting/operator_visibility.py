from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.reporting.llm_artifacts import daily_artifact_paths


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
        "verdict": {},
        "execution": {},
        "strategy_frame": {},
    }


def _is_trade_story(story: Dict[str, Any]) -> bool:
    action = str(story.get("action") or "").strip().upper()
    status = str(story.get("execution_status") or "").strip().upper()
    guard_status = str(story.get("guard_status") or "").strip().lower()
    if action in ("BUY", "SELL"):
        return True
    if status in ("EXECUTED", "EXECUTED_OK", "EXECUTED_FAIL", "BLOCKED", "INTENT_ONLY"):
        return True
    if guard_status == "intervened":
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

        if not str(ctx.get("final_outcome") or "").strip():
            if str(ctx.get("execution_status")) == "EXECUTED_OK":
                ctx["final_outcome"] = "order accepted"
            elif str(ctx.get("execution_status")) == "EXECUTED_FAIL":
                ctx["final_outcome"] = "order rejected"
            elif str(ctx.get("execution_status")) == "BLOCKED":
                ctx["final_outcome"] = f"blocked:{ctx.get('guard_reason')}"
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

    rows: List[Dict[str, Any]] = []
    for raw in _iter_jsonl(events_path):
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        rows.append({**raw, "_epoch": _to_epoch(ts), "_day": _utc_day(ts)})

    target_day = _pick_day(rows, day)
    day_rows = [r for r in rows if str(r.get("_day") or "") == target_day]
    run_stories = _build_run_contexts(day_rows)

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

        if stage == "execute_from_packet" and event == "verdict":
            if payload.get("allowed") is False:
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
        issues.append(
            {
                "code": "duplicate_execution_detected",
                "severity": "RED",
                "detail": f"duplicate_execution={duplicate_execution_total}",
            }
        )

    if guard_precedence_violation_total > 0:
        _raise_health("RED")
        issues.append(
            {
                "code": "guard_precedence_violation",
                "severity": "RED",
                "detail": f"guard_precedence_violation={guard_precedence_violation_total}",
            }
        )

    if api_429_rate > 0.20:
        _raise_health("YELLOW")
        issues.append(
            {
                "code": "high_api_error_rate",
                "severity": "YELLOW",
                "detail": f"api_429_rate={api_429_rate:.2%}",
            }
        )

    if intents_created >= 5 and blocked_rate > 0.60:
        _raise_health("YELLOW")
        issues.append(
            {
                "code": "excessive_blocked_orders",
                "severity": "YELLOW",
                "detail": f"blocked_rate={blocked_rate:.2%} ({intents_blocked}/{intents_created})",
            }
        )

    escalation_level = str(m30_policy.get("escalation_level") or "").strip().lower()
    if escalation_level == "incident":
        _raise_health("RED")
        issues.append(
            {
                "code": "policy_escalation_incident",
                "severity": "RED",
                "detail": "m30_post_golive escalation_level=incident",
            }
        )
    elif escalation_level == "watch":
        _raise_health("YELLOW")
        issues.append(
            {
                "code": "policy_escalation_watch",
                "severity": "YELLOW",
                "detail": "m30_post_golive escalation_level=watch",
            }
        )

    if m31_slo and not bool(m31_slo.get("ok")):
        _raise_health("RED")
        issues.append(
            {
                "code": "slo_incident_gate_failed",
                "severity": "RED",
                "detail": f"m31_slo_incident failure_total={_safe_int(m31_slo.get('failure_total'), 0)}",
            }
        )

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
    top_block_text = f"{top_block_reason[0][0]} ({top_block_reason[0][1]})" if top_block_reason else "none"
    run_total = len({str(r.get("run_id") or "").strip() for r in day_rows if str(r.get("run_id") or "").strip()})
    blocked_total = int(sum(int(v) for v in blocked_reason_counts.values()))
    llm_success_rate = _safe_float(
        (metrics.get("strategist_llm") if isinstance(metrics.get("strategist_llm"), dict) else {}).get("success_rate"),
        0.0,
    )
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
        (
            f"{_health_badge(health)} runs={run_total}, executions={executions_total} "
            f"(ok={executions_ok}, fail={executions_fail}), blocks={blocked_total}."
        ),
        f"Top guard block: {_humanize_reason(top_block_reason[0][0])} ({top_block_reason[0][1]})" if top_block_reason else "Top guard block: none",
        f"LLM success_rate={llm_success_rate:.2%}, interventions={operator_intervention_total}, cooldowns={cooldown_transition_total}.",
    ]

    reasoning_lines = [str(i.get("detail") or "") for i in issues if str(i.get("detail") or "").strip()]
    system_health_status = {
        "system_health_level": health,
        "reasoning": reasoning_lines,
        "recommended_action": recommended_actions[:3],
    }

    out: Dict[str, Any] = {
        "schema_version": "operator_summary.v1",
        "day": target_day,
        "inputs": {
            "event_log_path": str(events_path),
            "metrics_json_path": str((metrics_dir / f"metrics_{target_day}.json")),
            "m30_post_golive_json_path": str((m30_post_dir / f"m30_post_golive_policy_{target_day}.json")),
            "m30_golive_json_path": str((m30_go_dir / f"m30_final_golive_signoff_{target_day}.json")),
            "m31_slo_incident_json_path": str((m31_dir / f"m31_slo_incident_{target_day}.json")),
        },
        "executive_summary": {
            "system_status": health,
            "summary_lines": summary_lines,
        },
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

    md_lines = [
        f"# Operator Daily Summary ({target_day})",
        "",
        "## Executive Summary",
        "",
        f"- system_status: **{_health_badge(health)}**",
    ]
    for line in summary_lines:
        md_lines.append(f"- {line}")

    md_lines += ["", "## Top Issues", ""]
    for issue in out["top_issues"]:
        md_lines.append(
            f"- [{issue.get('severity')}] {issue.get('code')}: {_humanize_reason(issue.get('detail') or issue.get('code'))}"
        )

    md_lines += ["", "## Recommended Operator Actions", ""]
    for action in out["recommended_operator_actions"]:
        md_lines.append(f"- {action}")

    md_lines += [
        "",
        "## System Health Status",
        "",
        f"- system_health_level: **{_health_badge(system_health_status['system_health_level'])}**",
        "- reasoning:",
    ]
    if reasoning_lines:
        for line in reasoning_lines[:5]:
            md_lines.append(f"  - {line}")
    else:
        md_lines.append("  - (none)")
    md_lines.append("- recommended_action:")
    for line in system_health_status["recommended_action"]:
        md_lines.append(f"  - {line}")

    tas = out["trading_activity_summary"]
    md_lines += [
        "",
        "## Trading Activity Summary",
        "",
        f"- run_total: **{tas['run_total']}**",
        f"- decision_action_counts: `{json.dumps(tas['decision_action_counts'], ensure_ascii=False)}`",
        f"- strategy_counts: `{json.dumps(tas['strategy_counts'], ensure_ascii=False)}`",
        f"- executions_total: **{tas['executions_total']}**",
        f"- blocked_total: **{tas['blocked_total']}**",
        f"- noop_reason_top_human: {_format_reason_rows(list(tas.get('noop_reason_top_human') or []))}",
        f"- fallback_signal_status_top_human: {_format_reason_rows(list(tas.get('fallback_signal_status_top_human') or []))}",
    ]

    sgi = out["safety_guard_interventions"]
    md_lines += [
        "",
        "## Safety Guard Interventions",
        "",
        f"- blocked_total: **{sgi['blocked_total']}**",
        f"- blocked_reason_top_human: {_format_reason_rows(list(sgi.get('blocked_reason_top_human') or []))}",
        f"- operator_intervention_total: **{sgi['operator_intervention_total']}**",
        f"- cooldown_transition_total: **{sgi['cooldown_transition_total']}**",
        f"- duplicate_execution_total: **{sgi['duplicate_execution_total']}**",
        f"- guard_precedence_violation_total: **{sgi['guard_precedence_violation_total']}**",
    ]
    md_lines.append("")

    if report_dir.name in {"operator_summary", "daily"}:
        canonical_report_root = report_dir.parent
    else:
        canonical_report_root = report_dir
    paths = daily_artifact_paths(canonical_report_root, target_day)
    js_path = paths["operator_summary_json"]
    md_path = paths["operator_summary_md"]
    js_path.parent.mkdir(parents=True, exist_ok=True)
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
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
    stories_all = _build_run_contexts(day_rows)
    if bool(trade_only):
        stories_all = [s for s in stories_all if _is_trade_story(s)]
    limit = int(max_runs or 0)
    stories = stories_all[:limit] if limit > 0 else stories_all

    md_lines = [f"# Decision Story Report ({target_day})", ""]
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
            md_lines += [
                f"## Run {s.get('run_id')}",
                "",
                f"- run_id: `{s.get('run_id')}`",
                f"- symbol: **{s.get('symbol') or 'N/A'}**",
                f"- final_action: **{final_action}**",
                f"- execution_status: **{s.get('execution_status')}**",
                f"- decision_reason_summary: {s.get('key_reason') or _humanize_reason('unspecified')}",
                f"- technical_evidence: {s.get('technical_evidence') or '-'}",
                f"- sentiment_evidence: {s.get('sentiment_evidence') or '-'}",
                f"- guard_intervention: {s.get('guard_reason_human') or _humanize_reason(s.get('guard_reason') or 'none')}",
                f"- operator_intervention: {', '.join(operator_int) if operator_int else 'none'}",
                f"- final_outcome: {s.get('final_outcome') or '-'}",
                "",
            ]

    md_path = report_dir / f"decision_story_{target_day}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    out = {
        "schema_version": "decision_story.v1",
        "day": target_day,
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
    stories_all = _build_run_contexts(day_rows)
    if bool(trade_only):
        stories_all = [s for s in stories_all if _is_trade_story(s)]
    stories_all = sorted(stories_all, key=lambda s: int(s.get("first_epoch") or 0))
    limit = int(max_runs or 0)
    stories = stories_all[:limit] if limit > 0 else stories_all

    lines = [f"# Run Cards ({target_day})", ""]
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
            lines += [
                f"Run: {s.get('run_id')}",
                f"Symbol: {s.get('symbol') or 'N/A'}",
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
