from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re

from libs.llm.llm_router import LLMRouter
from libs.core.symbols import normalize_symbol


KST = timezone(timedelta(hours=9), name="KST")


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


def _to_datetime(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST)
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(KST)
        except Exception:
            return None
    raw = str(ts).strip()
    if not raw:
        return None
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST)
    except Exception:
        return None


def _iso_to_display(ts: Any) -> str:
    dt = _to_datetime(ts)
    if dt is None:
        return str(ts or "")
    return dt.strftime("%Y-%m-%d %H:%M:%S KST")


def _event_day(ts: Any) -> str:
    dt = _to_datetime(ts)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
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
                rows.append(obj)
    return rows


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _latest_matching(path: Path, prefix: str) -> Dict[str, Any]:
    if not path.exists():
        return {}
    files = sorted(path.glob(f"{prefix}_*.json"))
    if not files:
        return {}
    return _read_json(files[-1])


def _read_day_or_latest(path: Path, prefix: str, day: str) -> Dict[str, Any]:
    if path.exists() and day:
        exact = path / f"{prefix}_{day}.json"
        if exact.exists():
            return _read_json(exact)
    return _latest_matching(path, prefix)


def _latest_matching_path(path: Path, prefix: str) -> str:
    if not path.exists():
        return ""
    files = sorted(path.glob(f"{prefix}_*.json"))
    if not files:
        return ""
    return str(files[-1])


def _day_or_latest_path(path: Path, prefix: str, day: str) -> str:
    if path.exists() and day:
        exact = path / f"{prefix}_{day}.json"
        if exact.exists():
            return str(exact)
    return _latest_matching_path(path, prefix)


def _latest_event_day(event_log_path: Path) -> str:
    latest_day = ""
    latest_epoch = -1
    for row in _iter_jsonl(event_log_path):
        ts = row.get("ts_kst") or row.get("ts")
        epoch = _to_epoch(ts)
        if epoch is None or epoch < latest_epoch:
            continue
        latest_epoch = epoch
        latest_day = _event_day(ts)
    return latest_day


def _feature_coverage(feature_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(feature_snapshot, dict) or not feature_snapshot:
        return {"present": 0, "total": 0, "coverage_ratio": 0.0, "quality": "missing", "present_keys": [], "missing_keys": []}
    key_fields = [
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
    for key in key_fields:
        value = feature_snapshot.get(key)
        if value is None:
            missing.append(key)
        else:
            present.append(key)
    total = len(key_fields)
    present_total = len(present)
    ratio = float(present_total) / float(total) if total else 0.0
    if ratio >= 0.75:
        quality = "strong"
    elif ratio >= 0.35:
        quality = "partial"
    else:
        quality = "missing"
    return {
        "present": present_total,
        "total": total,
        "coverage_ratio": ratio,
        "quality": quality,
        "present_keys": present,
        "missing_keys": missing,
    }


def _quote_metrics_snapshot(feature_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(feature_snapshot, dict) or not feature_snapshot:
        return {
            "present": False,
            "skill_quote_price": None,
            "quote_volume": None,
            "quote_trading_value": None,
            "intraday_change_pct": None,
        }
    price = feature_snapshot.get("skill_quote_price")
    volume = feature_snapshot.get("quote_volume")
    trading_value = feature_snapshot.get("quote_trading_value")
    change_pct = feature_snapshot.get("intraday_change_pct")
    return {
        "present": any(v is not None and v != 0 for v in (price, volume, trading_value, change_pct)),
        "skill_quote_price": price,
        "quote_volume": volume,
        "quote_trading_value": trading_value,
        "intraday_change_pct": change_pct,
    }


def _truncate_json(v: Any, max_len: int = 800) -> str:
    try:
        s = json.dumps(v, ensure_ascii=False, indent=2)
    except Exception:
        s = str(v)
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _clean_brief_text(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    s = re.sub(r"^\s*From\s+[A-Za-z0-9_]+\s*-\s*", "", s)
    s = re.sub(r"^\s*[A-Za-z0-9_]+_hint\s*-\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s


def _clean_brief_list(v: Any, *, limit: int) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v:
        cleaned = _clean_brief_text(item)
        if cleaned:
            out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _extract_json_object(text: Any) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[idx:])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            continue
    return {}


def _salvage_operator_brief_fields(text: Any) -> Dict[str, Any]:
    raw = str(text or "")
    if not raw.strip():
        return {}
    fields = [
        "headline",
        "commander_summary",
        "strategist_summary",
        "scanner_summary",
        "monitor_summary",
        "supervisor_summary",
        "executor_summary",
        "reporter_summary",
    ]
    out: Dict[str, Any] = {}
    for key in fields:
        pattern = rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"'
        match = re.search(pattern, raw, flags=re.DOTALL)
        if not match:
            continue
        try:
            out[key] = json.loads('"' + match.group(1) + '"')
        except Exception:
            out[key] = match.group(1).replace('\\"', '"')
    takeaways_match = re.search(r'"operator_takeaways"\s*:\s*\[(.*)', raw, flags=re.DOTALL)
    if takeaways_match:
        items = re.findall(r'"((?:[^"\\]|\\.)*)"', takeaways_match.group(1), flags=re.DOTALL)
        cleaned: List[str] = []
        for item in items[:5]:
            try:
                cleaned.append(json.loads('"' + item + '"'))
            except Exception:
                cleaned.append(item.replace('\\"', '"'))
        if cleaned:
            out["operator_takeaways"] = cleaned
    return out


def _is_free_model(model: str) -> bool:
    raw = str(model or "").strip().lower()
    return ":free" in raw or raw.endswith("/free")


def _normalize_role_model_name(model: str) -> str:
    raw = str(model or "").strip()
    lowered = raw.lower()
    if lowered == "auto":
        return "openrouter/auto"
    if lowered == "free":
        return "openrouter/free"
    return raw


def _parse_operator_brief_lines(text: Any) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    keys = [
        "headline",
        "commander_summary",
        "strategist_summary",
        "scanner_summary",
        "monitor_summary",
        "supervisor_summary",
        "executor_summary",
        "reporter_summary",
        "operator_takeaways",
    ]
    out: Dict[str, Any] = {}
    for key in keys:
        pattern = rf"{key}\s*:\s*(.+)"
        matches = re.findall(pattern, raw, flags=re.IGNORECASE)
        if not matches:
            continue
        if key == "operator_takeaways":
            for candidate in reversed(matches):
                items = [item.strip(" -*") for item in str(candidate).split("|") if item.strip(" -*")]
                if not items:
                    continue
                if all(item.lower().startswith("item") for item in items):
                    continue
                out[key] = items[:5]
                break
            continue
        for candidate in reversed(matches):
            cleaned = str(candidate).strip().strip('"')
            if not cleaned:
                continue
            if cleaned in {"...", "?"}:
                continue
            out[key] = cleaned
            break
    return out


def _read_exact_day(path: Path, prefix: str, day: str) -> Dict[str, Any]:
    if not path.exists() or not day:
        return {}
    exact = path / f"{prefix}_{day}.json"
    return _read_json(exact)


def _normalize_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "action": "",
            "symbol": "",
            "qty": 0,
            "status": "",
            "ord_no": "",
        }
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    broker = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    response_payload = broker.get("response_payload") if isinstance(broker.get("response_payload"), dict) else {}
    return {
        "action": str(payload.get("action") or order.get("action") or "").upper(),
        "symbol": str(payload.get("symbol") or order.get("symbol") or order.get("stk_cd") or "").strip(),
        "qty": _safe_int(payload.get("qty"), _safe_int(order.get("qty"), _safe_int(order.get("ord_qty"), 0))),
        "status": str(payload.get("fill_status_summary") or payload.get("status") or broker.get("broker_message") or response_payload.get("return_msg") or ""),
        "ord_no": str(payload.get("ord_no") or broker.get("order_id") or response_payload.get("ord_no") or ""),
    }


@dataclass(frozen=True)
class OperatorUIConfig:
    repo_root: Path
    reports_root: Path
    event_log_path: Path
    evidence_log_path: Path
    strategy_memory_path: Path
    operator_ui_cache_path: Path

    @staticmethod
    def from_env(repo_root: Optional[Path] = None) -> "OperatorUIConfig":
        root = Path(repo_root or Path(__file__).resolve().parents[2])
        return OperatorUIConfig(
            repo_root=root,
            reports_root=Path(os.getenv("OPERATOR_UI_REPORTS_ROOT", str(root / "reports"))),
            event_log_path=Path(os.getenv("OPERATOR_UI_EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))),
            evidence_log_path=Path(os.getenv("OPERATOR_UI_EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))),
            strategy_memory_path=Path(os.getenv("OPERATOR_UI_STRATEGY_MEMORY_PATH", str(root / "data" / "strategy_memory" / "daily"))),
            operator_ui_cache_path=Path(os.getenv("OPERATOR_UI_CACHE_PATH", str(root / "data" / "operator_ui" / "brief_cache"))),
        )


def load_overview(config: OperatorUIConfig) -> Dict[str, Any]:
    latest_day = _latest_event_day(config.event_log_path)
    daily = _read_exact_day(config.reports_root / "daily", "daily", latest_day)
    operator_summary = _read_exact_day(config.reports_root / "operator_summary", "operator_summary", latest_day)
    reporter = _read_exact_day(config.reports_root / "dev" / "analysis" / "reporter_analysis", "reporter_analysis", latest_day)
    reconciliation = _read_exact_day(config.reports_root / "reconciliation", "broker_trade_reconciliation", latest_day)

    executive = operator_summary.get("executive_summary") if isinstance(operator_summary.get("executive_summary"), dict) else {}
    health = operator_summary.get("system_health_status") if isinstance(operator_summary.get("system_health_status"), dict) else {}
    trading = operator_summary.get("trading_activity_summary") if isinstance(operator_summary.get("trading_activity_summary"), dict) else {}
    recon_summary = reconciliation.get("summary") if isinstance(reconciliation.get("summary"), dict) else {}
    strategy_memory_timeline = load_strategy_memory_timeline(config, limit=7)
    latest_day = str(latest_day or "")
    all_today_trades = load_recent_trades_for_day(config, latest_day, limit=200)
    today_trades = all_today_trades[:8]
    traded_symbol_summary = summarize_trades_by_symbol(all_today_trades)
    overtrading_warning = build_overtrading_warning(all_today_trades, traded_symbol_summary, reporter)
    latest_prompt = load_latest_strategist_prompt_summary(config, latest_day)
    today_rows = list(_iter_jsonl(config.event_log_path))
    today_rows = [row for row in today_rows if not latest_day or _event_day(row.get("ts_kst") or row.get("ts")) == latest_day]
    live_route_rows = [
        row
        for row in today_rows
        if str(row.get("stage") or "") == "commander_router"
        and str(row.get("event") or "") == "route"
    ]
    live_verdict_rows = [
        row
        for row in today_rows
        if str(row.get("stage") or "") == "execute_from_packet"
        and str(row.get("event") or "") == "verdict"
        and isinstance(row.get("payload"), dict)
    ]
    live_blocked_total = sum(1 for row in live_verdict_rows if not bool((row.get("payload") or {}).get("allowed")))
    live_run_total = len(live_route_rows)
    live_execution_total = len(all_today_trades)

    if not operator_summary and latest_day:
        operator_summary_live_lines: List[str] = []
        if live_run_total:
            operator_summary_live_lines.append(f"live event log fallback active for {latest_day}")
        if live_execution_total:
            operator_summary_live_lines.append(f"today executions observed in log: {live_execution_total}")
        if live_blocked_total:
            operator_summary_live_lines.append(f"today blocked verdicts observed in log: {live_blocked_total}")
        live_status = "LIVE" if (live_run_total or live_execution_total or live_blocked_total) else "UNKNOWN"
        executive = {
            "system_status": live_status,
            "summary_lines": operator_summary_live_lines[:4],
        }
        health = {
            "system_health_level": live_status,
            "recommended_action": (
                [f"review same-day overtrading warning: {overtrading_warning.get('level')}"]
                if str(overtrading_warning.get("level") or "normal") in {"elevated", "high"}
                else ["generate operator summary after closeout to replace live fallback"]
            )[:4],
        }
        trading = {
            "run_total": live_run_total,
            "executions_total": live_execution_total,
            "blocked_total": live_blocked_total,
        }

    if not reporter and latest_day:
        reporter = {
            "ai_review": {"status": "not_generated_yet"},
            "ai_run_grade": "-",
            "ai_summary": "Same-day reporter analysis has not been generated yet.",
            "trade_summary": {
                "trade_count": live_execution_total,
                "symbols_traded": [str(row.get("symbol") or "") for row in traded_symbol_summary[:8]],
            },
        }
    ai_review = reporter.get("ai_review") if isinstance(reporter.get("ai_review"), dict) else {}
    trade_summary = reporter.get("trade_summary") if isinstance(reporter.get("trade_summary"), dict) else {}

    return {
        "latest_day": latest_day,
        "daily": {
            "events": _safe_int(daily.get("events"), 0),
            "decision_actions": dict(daily.get("decision_actions") or {}),
            "approvals": _safe_int(daily.get("approvals"), 0),
            "blocks": _safe_int(daily.get("blocks"), 0),
            "path": str(config.reports_root / "daily" / f"daily_{latest_day}.json") if latest_day else "",
        },
        "operator_summary": {
            "system_status": str(executive.get("system_status") or "UNKNOWN"),
            "summary_lines": list(executive.get("summary_lines") or [])[:4],
            "health_level": str(health.get("system_health_level") or "UNKNOWN"),
            "recommended_action": list(health.get("recommended_action") or [])[:4],
            "run_total": _safe_int(trading.get("run_total"), 0),
            "executions_total": _safe_int(trading.get("executions_total"), 0),
            "blocked_total": _safe_int(trading.get("blocked_total"), 0),
            "path": str(config.reports_root / "operator_summary" / f"operator_summary_{latest_day}.json") if latest_day else "",
        },
        "reporter": {
            "trade_count": _safe_int(trade_summary.get("trade_count"), 0),
            "symbols_traded": list(trade_summary.get("symbols_traded") or [])[:8],
            "ai_status": str(ai_review.get("status") or "disabled"),
            "ai_run_grade": str(reporter.get("ai_run_grade") or "N/A"),
            "ai_summary": str(reporter.get("ai_summary") or ""),
            "path": str(config.reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{latest_day}.json") if latest_day else "",
        },
        "reconciliation": {
            "local_total": _safe_int(recon_summary.get("local_total"), 0),
            "broker_total": _safe_int(recon_summary.get("broker_total"), 0),
            "matched_by_ord_no": _safe_int(recon_summary.get("matched_by_ord_no"), 0),
            "broker_window_limited": bool(recon_summary.get("broker_window_limited")),
            "path": str(config.reports_root / "reconciliation" / f"broker_trade_reconciliation_{latest_day}.json") if latest_day else "",
        },
        "today_trades": today_trades,
        "today_traded_symbols": traded_symbol_summary,
        "overtrading_warning": overtrading_warning,
        "latest_strategist_prompt": latest_prompt,
        "strategy_memory_timeline": strategy_memory_timeline,
    }


def load_recent_trades_for_day(config: OperatorUIConfig, day: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    rows = list(_iter_jsonl(config.event_log_path))
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("stage") or "") != "execute_from_packet":
            continue
        if str(row.get("event") or "") != "execution":
            continue
        if day and _event_day(row.get("ts_kst") or row.get("ts")) != day:
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        action = str(execution.get("action") or "").upper()
        symbol = normalize_symbol(execution.get("symbol"), allow_test_symbols=True)
        if action not in {"BUY", "SELL"}:
            continue
        if not symbol:
            continue
        out.append(
            {
                "ts": _iso_to_display(row.get("ts_kst") or row.get("ts")),
                "run_id": str(row.get("run_id") or ""),
                "action": action,
                "symbol": symbol,
                "qty": _safe_int(execution.get("qty"), 0),
                "status": str(execution.get("status") or ""),
                "ord_no": str(execution.get("ord_no") or ""),
            }
        )
    out = sorted(out, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    return out[: max(1, int(limit))]


def summarize_trades_by_symbol(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for trade in trades:
        symbol = normalize_symbol(trade.get("symbol"), allow_test_symbols=True)
        if not symbol:
            continue
        row = grouped.setdefault(
            symbol,
            {
                "symbol": symbol,
                "buy_count": 0,
                "sell_count": 0,
                "net_qty": 0,
                "latest_action": "",
                "latest_ts": "",
                "latest_status": "",
            },
        )
        action = str(trade.get("action") or "").upper()
        qty = _safe_int(trade.get("qty"), 0)
        if action == "BUY":
            row["buy_count"] += 1
            row["net_qty"] += qty
        elif action == "SELL":
            row["sell_count"] += 1
            row["net_qty"] -= qty
        if (_to_epoch(trade.get("ts")) or 0) >= (_to_epoch(row.get("latest_ts")) or 0):
            row["latest_action"] = action
            row["latest_ts"] = str(trade.get("ts") or "")
            row["latest_status"] = str(trade.get("status") or "")
    out = list(grouped.values())
    out.sort(key=lambda row: (_to_epoch(row.get("latest_ts")) or 0, row.get("symbol") or ""), reverse=True)
    return out


def build_overtrading_warning(
    trades: List[Dict[str, Any]],
    traded_symbols: List[Dict[str, Any]],
    reporter_report: Dict[str, Any],
) -> Dict[str, Any]:
    total_executions = len(trades)
    round_trip_symbols = [
        {
            "symbol": row.get("symbol"),
            "buy_count": _safe_int(row.get("buy_count"), 0),
            "sell_count": _safe_int(row.get("sell_count"), 0),
            "round_trips": min(_safe_int(row.get("buy_count"), 0), _safe_int(row.get("sell_count"), 0)),
        }
        for row in traded_symbols
        if _safe_int(row.get("buy_count"), 0) > 0 and _safe_int(row.get("sell_count"), 0) > 0
    ]
    round_trip_symbols.sort(key=lambda row: (row.get("round_trips") or 0, row.get("symbol") or ""), reverse=True)
    ai_findings = list(reporter_report.get("ai_findings") or [])[:4] if isinstance(reporter_report, dict) else []
    reasons: List[str] = []
    level = "normal"
    if total_executions >= 10:
        level = "high"
        reasons.append(f"execution count elevated ({total_executions})")
    elif total_executions >= 5:
        level = "elevated"
        reasons.append(f"execution count moderately elevated ({total_executions})")
    if round_trip_symbols:
        if level == "normal":
            level = "elevated"
        top = round_trip_symbols[0]
        reasons.append(
            f"same-symbol round trips detected on {top.get('symbol')} ({top.get('round_trips')} cycles)"
        )
    if any("overtrading" in str(item).lower() for item in ai_findings):
        if level == "normal":
            level = "elevated"
        reasons.append("reporter flagged overtrading risk")
    if not reasons:
        reasons.append("no immediate overtrading signal in latest execution window")
    return {
        "level": level,
        "total_executions": total_executions,
        "round_trip_symbols": round_trip_symbols[:5],
        "reasons": reasons[:4],
    }


def load_symbol_run_chain(config: OperatorUIConfig, day: str, symbol: str, *, limit: int = 3) -> List[Dict[str, Any]]:
    if not symbol:
        return []
    rows = list(_iter_jsonl(config.event_log_path))
    route_rows = [
        row
        for row in rows
        if str(row.get("stage") or "") == "commander_router"
        and str(row.get("event") or "") == "route"
        and (not day or _event_day(row.get("ts")) == day)
    ]
    route_rows = sorted(route_rows, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        rid = str(row.get("run_id") or "").strip()
        if not rid:
            continue
        grouped.setdefault(rid, []).append(row)

    out: List[Dict[str, Any]] = []
    for route in route_rows:
        rid = str(route.get("run_id") or "").strip()
        run_rows = grouped.get(rid) or []
        scanner_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "scanner" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        candidate_selection = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "candidate_selection"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "scanner"
            ),
            {},
        )
        execution_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        strategist_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "strategist" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        monitor_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        verdict_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "verdict" and isinstance(r.get("payload"), dict)),
            {},
        )
        run_symbol = normalize_symbol(
            execution.get("symbol")
            or scanner_summary.get("top_stock")
            or candidate_selection.get("selected_symbol")
            or "",
            allow_test_symbols=True,
        ).strip()
        if run_symbol != symbol:
            continue
        out.append(
            {
                "ts": _iso_to_display(route.get("ts")),
                "run_id": rid,
                "phase": str((route.get("payload") or {}).get("phase") or ""),
                "playbook": str(strategist_summary.get("playbook") or ""),
                "risk_tone": str(strategist_summary.get("risk_tone") or ""),
                "symbol": run_symbol,
                "action": str(execution.get("action") or ""),
                "execution_status": str(execution.get("status") or ""),
                "monitor_reason": str(monitor_summary.get("monitor_reason") or ""),
                "exit_reason": str(monitor_summary.get("exit_reason") or ""),
                "guard_reason": str(verdict_payload.get("reason") or ""),
                "allowed": verdict_payload.get("allowed"),
            }
        )
        if len(out) >= max(1, int(limit)):
            break
    return out


def load_latest_strategist_prompt_summary(config: OperatorUIConfig, day: str) -> Dict[str, Any]:
    rows = list(_iter_jsonl(config.evidence_log_path))
    target = {}
    for row in reversed(rows):
        if str(row.get("agent") or "") != "strategist":
            continue
        if str(row.get("stage") or "") != "theme_selection":
            continue
        if day and _event_day(row.get("timestamp")) != day:
            continue
        target = row
        break
    if not target:
        return {}
    raw_input = target.get("raw_input") if isinstance(target.get("raw_input"), dict) else {}
    parsed_output = target.get("parsed_output") if isinstance(target.get("parsed_output"), dict) else {}
    prompt = str(target.get("llm_prompt") or "")
    compact_prompt = prompt if len(prompt) <= 400 else prompt[:397] + "..."
    return {
        "run_id": str(target.get("run_id") or ""),
        "timestamp": str(target.get("timestamp") or ""),
        "news_query_targets": list(raw_input.get("news_query_targets") or [])[:8],
        "themes": list(parsed_output.get("themes") or [])[:6],
        "playbook": str(parsed_output.get("playbook") or ""),
        "market_regime": str(parsed_output.get("market_regime") or ""),
        "prompt_excerpt": compact_prompt,
    }


def load_recent_runs(config: OperatorUIConfig, *, limit: int = 50) -> List[Dict[str, Any]]:
    rows = list(_iter_jsonl(config.event_log_path))
    route_rows = [row for row in rows if str(row.get("stage") or "") == "commander_router" and str(row.get("event") or "") == "route"]
    route_rows = sorted(route_rows, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)[: max(1, int(limit))]
    target_run_ids = {str(row.get("run_id") or "").strip() for row in route_rows if str(row.get("run_id") or "").strip()}
    grouped: Dict[str, List[Dict[str, Any]]] = {rid: [] for rid in target_run_ids}
    for row in rows:
        rid = str(row.get("run_id") or "").strip()
        if rid in grouped:
            grouped[rid].append(row)

    out: List[Dict[str, Any]] = []
    for route in route_rows:
        rid = str(route.get("run_id") or "").strip()
        run_rows = grouped.get(rid) or []
        strategist_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "strategist" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        scanner_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "scanner" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        monitor_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        strategic_frame = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "strategic_frame"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "strategist"
            ),
            {},
        )
        candidate_selection = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "candidate_selection"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "scanner"
            ),
            {},
        )
        verdict_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "verdict" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        selected_candidate = candidate_selection.get("selected_candidate") if isinstance(candidate_selection.get("selected_candidate"), dict) else {}
        feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
        feature_coverage = _feature_coverage(feature_snapshot)
        macro_stress_overlay = strategic_frame.get("macro_stress_overlay") if isinstance(strategic_frame.get("macro_stress_overlay"), dict) else {}
        out.append(
            {
                "run_id": rid,
                "ts": _iso_to_display(route.get("ts")),
                "mode": str((route.get("payload") or {}).get("mode") or ""),
                "phase": str((route.get("payload") or {}).get("phase") or ""),
                "strategist_playbook": str(strategist_summary.get("playbook") or ""),
                "strategist_risk_tone": str(strategist_summary.get("risk_tone") or ""),
                "scanner_top_stock": str(scanner_summary.get("top_stock") or ""),
                "scanner_top_score": _safe_float(scanner_summary.get("top_score"), 0.0),
                "monitor_reason": str(monitor_summary.get("monitor_reason") or ""),
                "exit_reason": str(monitor_summary.get("exit_reason") or ""),
                "supervisor_allowed": verdict_payload.get("allowed"),
                "guard_reason": str(verdict_payload.get("reason") or ""),
                "execution_status": str(execution.get("status") or ""),
                "execution_action": str(execution.get("action") or ""),
                "symbol": normalize_symbol(execution.get("symbol") or scanner_summary.get("top_stock") or "", allow_test_symbols=True),
                "macro_stress_active": bool(macro_stress_overlay.get("active")),
                "macro_stress_flags": list(macro_stress_overlay.get("stress_flags") or [])[:3],
                "feature_coverage_quality": str(feature_coverage.get("quality") or "missing"),
                "feature_coverage_ratio": _safe_float(feature_coverage.get("coverage_ratio"), 0.0),
            }
        )
    return out


def _latest_evidence(rows: List[Dict[str, Any]], *, agent: str, stage: str) -> Dict[str, Any]:
    for row in reversed(rows):
        if str(row.get("agent") or "").strip() != agent:
            continue
        if str(row.get("stage") or "").strip() != stage:
            continue
        return row
    return {}


def _reporter_snippet_for_run(config: OperatorUIConfig, run_id: str, run_day: str) -> Dict[str, Any]:
    path = config.reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{run_day}.json"
    report = _read_json(path)
    if not report:
        return {
            "report_path": str(path),
            "found": False,
            "ai_summary": "",
            "ai_run_grade": "",
            "reason": "same_day_report_missing",
        }
    chains = ((report.get("decision_trace_chain_summary") or {}).get("chains") or []) if isinstance(report.get("decision_trace_chain_summary"), dict) else []
    chain = next((c for c in chains if isinstance(c, dict) and str(c.get("run_id") or "").strip() == run_id), {})
    if not chain:
        return {
            "report_path": str(path),
            "found": False,
            "ai_summary": "",
            "ai_run_grade": str(report.get("ai_run_grade") or ""),
            "reason": "run_not_linked_in_same_day_report",
        }
    return {
        "report_path": str(path),
        "found": True,
        "ai_summary": str(report.get("ai_summary") or ""),
        "ai_run_grade": str(report.get("ai_run_grade") or ""),
        "chain": chain,
    }





def _fallback_operator_brief(detail: Dict[str, Any]) -> Dict[str, Any]:
    strategist = detail.get("strategist") if isinstance(detail.get("strategist"), dict) else {}
    strategist_summary = strategist.get("summary") if isinstance(strategist.get("summary"), dict) else {}
    strategist_evidence = strategist.get("evidence") if isinstance(strategist.get("evidence"), dict) else {}
    raw_input = strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {}
    global_inputs = raw_input.get("global_sentiment_inputs") if isinstance(raw_input.get("global_sentiment_inputs"), dict) else {}
    fear_index = global_inputs.get("fear_index") if isinstance(global_inputs.get("fear_index"), dict) else {}
    scanner = detail.get("scanner") if isinstance(detail.get("scanner"), dict) else {}
    scanner_summary = scanner.get("summary") if isinstance(scanner.get("summary"), dict) else {}
    scanner_trace = scanner.get("decision_trace") if isinstance(scanner.get("decision_trace"), dict) else {}
    selected = (scanner_trace.get("selected_candidate") or {}) if isinstance(scanner_trace.get("selected_candidate"), dict) else {}
    monitor = detail.get("monitor") if isinstance(detail.get("monitor"), dict) else {}
    monitor_summary = monitor.get("summary") if isinstance(monitor.get("summary"), dict) else {}
    monitor_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    supervisor = (detail.get("supervisor") or {}).get("verdict") if isinstance(detail.get("supervisor"), dict) else {}
    executor = (detail.get("executor") or {}).get("execution") if isinstance(detail.get("executor"), dict) else {}
    reporter = detail.get("reporter") if isinstance(detail.get("reporter"), dict) else {}

    global_bits: List[str] = []
    if global_inputs.get("score") is not None:
        global_bits.append(f"\uae00\ub85c\ubc8c \uac10\uc131 \uc810\uc218={_safe_float(global_inputs.get('score'), 0.0):.2f}")
    if fear_index.get("level") is not None:
        global_bits.append(f"VIX={_safe_float(fear_index.get('level'), 0.0):.2f}")
    macro_moves = global_inputs.get("macro_moves") if isinstance(global_inputs.get("macro_moves"), dict) else {}
    if macro_moves.get("dxy_pct") is not None:
        global_bits.append(f"\ub2ec\ub7ec\uc9c0\uc218={_safe_float(macro_moves.get('dxy_pct'), 0.0):.2f}")

    feature_coverage = scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {}
    quote_metrics = scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else {}

    return {
        "status": "fallback",
        "model": "",
        "headline": f"{detail.get('run_id') or '-'} \uc6b4\uc601 \uc694\uc57d",
        "commander_summary": (
            f"\uc9c0\ud718\uc790\ub294 {((detail.get('commander') or {}).get('phase') or '-')} phase\uc5d0\uc11c "
            f"{((detail.get('commander') or {}).get('path') or '-')} \uacbd\ub85c\ub97c \uc2e4\ud589\ud588\uc2b5\ub2c8\ub2e4."
        ),
        "strategist_summary": (
            f"\uc804\ub7b5\uac00\ub294 {', '.join(global_bits) or '\uc2dc\uc7a5 \uc785\ub825'}\uc744 \ucc38\uace0\ud558\uace0, \ub274\uc2a4 \uc9c8\uc758 "
            f"{', '.join(_clean_brief_list(strategist_summary.get('news_query_targets'), limit=6)) or '-'}\ub85c \ubd84\uc704\uae30\ub97c \ud655\uc778\ud55c \ub4a4 "
            f"\ud14c\ub9c8 {', '.join(_clean_brief_list(strategist_summary.get('themes'), limit=4)) or '-'}, "
            f"\ud50c\ub808\uc774\ubd81 {strategist_summary.get('playbook') or '-'}\ub85c \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4."
        ),
        "scanner_summary": (
            f"\uc2a4\uce90\ub108\ub294 Kiwoom \ud6c4\ubcf4 {int(scanner_summary.get('candidate_pool_after_filter') or 0)}\uac1c \uc911 "
            f"{_clean_brief_text(scanner_summary.get('top_stock') or selected.get('symbol') or '-')}\ub97c 1\ub4f1\uc73c\ub85c \uace8\ub790\uace0 \uc774\uc720\ub294 "
            f"{selected.get('why') or '-'}\uc785\ub2c8\ub2e4."
        ),
        "monitor_summary": (
            f"\ubaa8\ub2c8\ud130\ub294 {monitor_summary.get('monitor_reason') or monitor_trace.get('monitor_reason') or '-'} \uc0c1\ud0dc\ub97c \ubcf4\uace0, "
            f"exit={monitor_summary.get('exit_reason') or monitor_trace.get('exit_reason') or '-'}\ub85c \ud310\ub2e8\ud588\uc2b5\ub2c8\ub2e4."
        ),
        "supervisor_summary": (
            f"\uac10\ub3c5\uad00\uc740 allowed={supervisor.get('allowed')} / reason={supervisor.get('reason') or '-'}\ub85c \uacb0\ub860\ub0c8\uc2b5\ub2c8\ub2e4."
        ),
        "executor_summary": (
            f"\uc218\ud589\uc790\ub294 {executor.get('action') or 'NOOP'} {executor.get('symbol') or ''} "
            f"status={executor.get('fill_status_summary') or executor.get('status') or '-'}\ub85c \ub9c8\ubb34\ub9ac\ud588\uc2b5\ub2c8\ub2e4."
        ),
        "reporter_summary": (
            f"\ub9ac\ud3ec\ud130\ub294 grade={reporter.get('ai_run_grade') or '-'} / "
            f"summary={reporter.get('ai_summary') or '\uac19\uc740 \ub0a0\uc9dc reporter \uc694\uc57d\uc774 \uc544\uc9c1 \uc5c6\uc2b5\ub2c8\ub2e4.'}"
        ),
        "operator_takeaways": [
            f"\ub274\uc2a4/\uac70\uc2dc \uc785\ub825: {', '.join(global_bits) or '\uc2dc\uc7a5 \uc785\ub825 \uc5c6\uc74c'}",
            f"\ucc28\ud2b8/feature coverage: {feature_coverage.get('quality') or '-'} ({feature_coverage.get('present') or 0}/{feature_coverage.get('total') or 0})",
            f"\uc2e4\uc2dc\uac04 quote: \uac00\uaca9 {quote_metrics.get('skill_quote_price') or '-'} \uac70\ub798\ub7c9 {quote_metrics.get('quote_volume') or '-'} \uac70\ub798\ub300\uae08 {quote_metrics.get('quote_trading_value') or '-'}",
        ],
    }


def _build_operator_brief_input(detail: Dict[str, Any]) -> Dict[str, Any]:
    strategist = detail.get("strategist") if isinstance(detail.get("strategist"), dict) else {}
    scanner = detail.get("scanner") if isinstance(detail.get("scanner"), dict) else {}
    monitor = detail.get("monitor") if isinstance(detail.get("monitor"), dict) else {}
    commander = detail.get("commander") if isinstance(detail.get("commander"), dict) else {}
    reporter = detail.get("reporter") if isinstance(detail.get("reporter"), dict) else {}
    strategist_summary = strategist.get("summary") if isinstance(strategist.get("summary"), dict) else {}
    strategist_evidence = strategist.get("evidence") if isinstance(strategist.get("evidence"), dict) else {}
    raw_input = strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {}
    scanner_trace = scanner.get("decision_trace") if isinstance(scanner.get("decision_trace"), dict) else {}
    selected = scanner_trace.get("selected_candidate") if isinstance(scanner_trace.get("selected_candidate"), dict) else {}
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    component_snapshot = selected.get("component_snapshot") if isinstance(selected.get("component_snapshot"), dict) else {}
    feature_snapshot = selected.get("feature_snapshot") if isinstance(selected.get("feature_snapshot"), dict) else {}
    monitor_summary = monitor.get("summary") if isinstance(monitor.get("summary"), dict) else {}
    monitor_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    return {
        "run_id": detail.get("run_id"),
        "commander": {
            "mode": commander.get("mode"),
            "phase": commander.get("phase"),
            "path": commander.get("path"),
            "status": commander.get("status"),
        },
        "strategist": {
            "market_regime": strategist_summary.get("market_regime"),
            "market_sentiment": strategist_summary.get("market_sentiment"),
            "themes": list(strategist_summary.get("themes") or [])[:5],
            "playbook": strategist_summary.get("playbook"),
            "scanner_bias": strategist_summary.get("scanner_bias"),
            "risk_tone": strategist_summary.get("risk_tone"),
            "monitor_guidance": strategist_summary.get("monitor_guidance"),
            "news_query_targets": list(strategist_summary.get("news_query_targets") or [])[:8],
            "news_query_reasoning": strategist_summary.get("news_query_reasoning"),
            "global_sentiment_inputs": raw_input.get("global_sentiment_inputs") if isinstance(raw_input.get("global_sentiment_inputs"), dict) else {},
            "market_news_titles": [str((x or {}).get("title") or "") for x in list(raw_input.get("collected_market_news") or [])[:4] if isinstance(x, dict)],
            "candidate_news_titles": [str((x or {}).get("title") or "") for x in list(raw_input.get("collected_candidate_news") or [])[:4] if isinstance(x, dict)],
            "llm_status": strategist_summary.get("llm_frame_status"),
            "llm_low_confidence": strategist_summary.get("llm_frame_low_confidence"),
        },
        "scanner": {
            "candidate_source": scanner.get("summary", {}).get("candidate_source") if isinstance(scanner.get("summary"), dict) else "",
            "candidate_pool_before_filter": (scanner.get("summary") or {}).get("candidate_pool_before_filter") if isinstance(scanner.get("summary"), dict) else None,
            "candidate_pool_after_filter": (scanner.get("summary") or {}).get("candidate_pool_after_filter") if isinstance(scanner.get("summary"), dict) else None,
            "top_ranked_symbols": list((scanner.get("summary") or {}).get("top_ranked_symbols") or [])[:5] if isinstance(scanner.get("summary"), dict) else [],
            "source_mix": scanner_trace.get("kiwoom_pool_source_mix") if isinstance(scanner_trace.get("kiwoom_pool_source_mix"), dict) else {},
            "selected_symbol": scanner_trace.get("selected_symbol") or selected.get("symbol"),
            "selected_reason": selected.get("why"),
            "source_scores": selected.get("source_scores") if isinstance(selected.get("source_scores"), dict) else {},
            "score_total": selected.get("score_total"),
            "confidence": selected.get("confidence"),
            "feature_coverage": scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {},
            "quote_metrics": scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else {},
            "score_breakdown": score_breakdown,
            "component_snapshot": component_snapshot,
            "feature_snapshot": feature_snapshot,
        },
        "monitor": {
            "monitor_reason": monitor_summary.get("monitor_reason") or monitor_trace.get("monitor_reason"),
            "exit_reason": monitor_summary.get("exit_reason") or monitor_trace.get("exit_reason"),
            "position_age_seconds": monitor_summary.get("position_age_seconds"),
            "thresholds": monitor_trace.get("thresholds") if isinstance(monitor_trace.get("thresholds"), dict) else {},
            "strategy_frame_adjustments": list(monitor_trace.get("strategy_frame_adjustments") or [])[:6],
            "exit_policy_guard_adjustments": list(monitor_trace.get("exit_policy_guard_adjustments") or [])[:6],
        },
        "supervisor": ((detail.get("supervisor") or {}).get("verdict") or {}) if isinstance(detail.get("supervisor"), dict) else {},
        "executor": ((detail.get("executor") or {}).get("execution") or {}) if isinstance(detail.get("executor"), dict) else {},
        "reporter": {
            "ai_summary": reporter.get("ai_summary"),
            "ai_run_grade": reporter.get("ai_run_grade"),
            "found": reporter.get("found"),
        },
    }


def _build_operator_brief_messages(compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
    contract = {
        "headline": "string",
        "commander_summary": "string",
        "strategist_summary": "string",
        "scanner_summary": "string",
        "monitor_summary": "string",
        "supervisor_summary": "string",
        "executor_summary": "string",
        "reporter_summary": "string",
        "operator_takeaways": ["string"],
    }
    system_prompt = (
        "\ub2f9\uc2e0\uc740 \ud2b8\ub808\uc774\ub529 \uc6b4\uc601 \ud654\uba74\uc6a9 \ud55c\uae00 \ube0c\ub9ac\ud504 \uc791\uc131\uae30\uc785\ub2c8\ub2e4. "
        "\uc6b4\uc601\uc790\uac00 \ud55c \ubc88\uc5d0 \uc774\ud574\ud560 \uc218 \uc788\ub3c4\ub85d \uc9e7\uace0 \uc815\ud655\ud558\uac8c \uc815\ub9ac\ud558\uc138\uc694. "
        "\ubc18\ub4dc\uc2dc JSON\ub9cc \ucd9c\ub825\ud558\uace0 \uc124\uba85\ubb38\uc774\ub098 \uc8fc\uc11d\uc740 \uc4f0\uc9c0 \ub9c8\uc138\uc694."
    )
    user_prompt = (
        "\uc544\ub798 \uc2e4\ud589 \uae30\ub85d\uc744 \ubc14\ud0d5\uc73c\ub85c \uc9c0\ud718\uc790, \uc804\ub7b5\uac00, \uc2a4\uce90\ub108, \ubaa8\ub2c8\ud130, \uac10\ub3c5\uad00, \uc218\ud589\uc790, \ub9ac\ud3ec\ud130\uac00 \uac01\uac01 \ubb34\uc5c7\uc744 \ud588\ub294\uc9c0 "
        "\uc6b4\uc601\uc790\uc5d0\uac8c \ubc14\ub85c \uc77d\ud788\ub294 \ud55c\uad6d\uc5b4\ub85c \uc694\uc57d\ud558\uc138\uc694.\n"
        "\ube0c\ub9ac\ud504\uc5d0\ub294 \ub2e4\uc74c\uc774 \ud3ec\ud568\ub3fc\uc57c \ud569\ub2c8\ub2e4.\n"
        "- \uc804\ub7b5\uac00\uac00 \uc5b4\ub5a4 \ub274\uc2a4/\uae00\ub85c\ubc8c \uac10\uc131/VIX/\uac70\uc2dc \uc785\ub825\uc744 \ubd24\ub294\uc9c0\n"
        "- \uc2a4\uce90\ub108\uac00 Kiwoom \ud6c4\ubcf4 \uc911 \uc5b4\ub5a4 \uc885\ubaa9\uc744 \uc65c 1\ub4f1\uc73c\ub85c \uace8\ub790\ub294\uc9c0\n"
        "- \ucc28\ud2b8/feature/\uc2e4\uc2dc\uac04 quote\uac00 \uc5bc\ub9c8\ub098 \ucc44\uc6cc\uc84c\ub294\uc9c0\n"
        "- \ubaa8\ub2c8\ud130\uac00 \uc65c hold/buy/sell/block \ud588\ub294\uc9c0\n"
        "- \uac10\ub3c5\uad00\uacfc \uc218\ud589\uc790\uc758 \ucd5c\uc885 \uacb0\ub860\n"
        "- \ub9ac\ud3ec\ud130\uc758 \uc0ac\ud6c4 \ud3c9\uac00\n"
        "\uac01 \ud56d\ubaa9\uc740 \uc9e7\uace0 \uba85\ud655\ud558\uac8c \uc4f0\uace0, \uc804\uccb4\ub294 120\uc790 \ub0b4\uc678 \ubb38\uc7a5 \uc704\uc8fc\ub85c \uc815\ub9ac\ud558\uc138\uc694.\n"
        "operator_takeaways\ub294 3\uac1c \uc774\ud558\ub85c \uc791\uc131\ud558\uc138\uc694.\n"
        f"\uacc4\uc57d: {json.dumps(contract, ensure_ascii=False)}\n"
        f"\uc785\ub825: {json.dumps(compact_input, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_operator_brief_repair_messages(raw_text: str) -> List[Dict[str, str]]:
    contract = {
        "headline": "string",
        "commander_summary": "string",
        "strategist_summary": "string",
        "scanner_summary": "string",
        "monitor_summary": "string",
        "supervisor_summary": "string",
        "executor_summary": "string",
        "reporter_summary": "string",
        "operator_takeaways": ["string"],
    }
    return [
        {
            "role": "system",
            "content": (
                "\ub2f9\uc2e0\uc740 \ube0c\ub9ac\ud504 \ubcf5\uad6c\uae30\uc785\ub2c8\ub2e4. "
                "\uc785\ub825 \ud14d\uc2a4\ud2b8\ub97c \uacc4\uc57d\uc5d0 \ub9de\ub294 JSON \ud558\ub098\ub85c\ub9cc \uc815\ub9ac\ud558\uc138\uc694. "
                "\uc124\uba85\uc774\ub098 \uc8fc\uc11d \uc5c6\uc774 JSON \uac1d\uccb4\ub9cc \ucd9c\ub825\ud558\uc138\uc694."
            ),
        },
        {
            "role": "user",
            "content": (
                f"\uacc4\uc57d: {json.dumps(contract, ensure_ascii=False)}\n"
                f"\uc785\ub825: {raw_text}"
            ),
        },
    ]


def _build_operator_brief_line_messages(compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "\ub2f9\uc2e0\uc740 \ube0c\ub9ac\ud504 \ubcf5\uad6c\uae30\uc785\ub2c8\ub2e4. "
                "JSON\uc774 \uc5b4\ub824\uc6b0\uba74 \uc544\ub798 key:value \ud615\uc2dd\uc73c\ub85c\ub9cc \ub2f5\ud558\uc138\uc694. "
                "\ubd88\ud544\uc694\ud55c \uc11c\ub860 \uc5c6\uc774 \ud544\uc694\ud55c \uc904\ub9cc \ucd9c\ub825\ud558\uc138\uc694."
            ),
        },
        {
            "role": "user",
            "content": (
                "\ub2e4\uc74c \ud615\uc2dd\uc73c\ub85c\ub9cc \ub2f5\ud558\uc138\uc694:\n"
                "headline: ...\n"
                "commander_summary: ...\n"
                "strategist_summary: ...\n"
                "scanner_summary: ...\n"
                "monitor_summary: ...\n"
                "supervisor_summary: ...\n"
                "executor_summary: ...\n"
                "reporter_summary: ...\n"
                "operator_takeaways: item1 | item2 | item3\n"
                f"\uc785\ub825: {json.dumps(compact_input, ensure_ascii=False)}"
            ),
        },
    ]


def _load_operator_brief(detail: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _fallback_operator_brief(detail)
    router = LLMRouter.from_env()
    if router.client is None:
        return fallback
    explicit_model = str(
        os.getenv("OPERATOR_UI_RUN_BRIEF_MODEL", "")
        or os.getenv("OPENROUTER_MODEL_OPERATOR_UI", "")
        or os.getenv("OPENROUTER_MODEL_REPORTER_INTRADAY", "")
        or ""
    ).strip()
    if hasattr(router, "resolve"):
        route = router.resolve("operator_ui", policy={"model": explicit_model} if explicit_model else None)
        model = str(getattr(route, "model", "") or explicit_model or "").strip()
    else:
        model = _normalize_role_model_name(
            explicit_model
            or os.getenv("OPENROUTER_DEFAULT_MODEL", "")
            or ""
        )
    compact_input = _build_operator_brief_input(detail)
    messages = _build_operator_brief_messages(compact_input)
    try:
        raw = router.chat(
            "operator_ui",
            messages,
            policy={
                "temperature": float(os.getenv("OPERATOR_UI_RUN_BRIEF_TEMPERATURE", "0.1")),
                "max_tokens": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_MAX_TOKENS", "700"))),
                "timeout_sec": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "2"))),
                "response_format": {"type": "json_object"},
                **({"model": model} if model else {}),
            },
        )
    except Exception as exc:
        fallback["model"] = model
        fallback["reason"] = f"llm_error:{exc}"
        return fallback
    parsed = _extract_json_object(raw)
    if not parsed:
        if _is_free_model(model) and not str(raw or "").strip():
            fallback["status"] = "fallback"
            fallback["model"] = model
            fallback["reason"] = "free_model_empty_response"
            return fallback
        try:
            repair_raw = router.chat(
                "operator_ui",
                _build_operator_brief_repair_messages(raw),
                policy={
                    "temperature": 0.0,
                    "max_tokens": 600,
                    "timeout_sec": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "2"))),
                    "response_format": {"type": "json_object"},
                    **({"model": model} if model else {}),
                },
            )
        except Exception:
            repair_raw = ""
        repaired = _extract_json_object(repair_raw)
        if repaired:
            return {
                "status": "repaired",
                "model": model,
                "headline": str(repaired.get("headline") or fallback.get("headline") or ""),
                "commander_summary": str(repaired.get("commander_summary") or fallback.get("commander_summary") or ""),
                "strategist_summary": str(repaired.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                "scanner_summary": str(repaired.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                "monitor_summary": str(repaired.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                "supervisor_summary": str(repaired.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                "executor_summary": str(repaired.get("executor_summary") or fallback.get("executor_summary") or ""),
                "reporter_summary": str(repaired.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                "operator_takeaways": [str(x or "") for x in list(repaired.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                "reason": "llm_repair_pass",
            }
        if _is_free_model(model):
            salvaged = _salvage_operator_brief_fields(raw)
            if salvaged:
                return {
                    "status": "salvaged",
                    "model": model,
                    "headline": str(salvaged.get("headline") or fallback.get("headline") or ""),
                    "commander_summary": str(salvaged.get("commander_summary") or fallback.get("commander_summary") or ""),
                    "strategist_summary": str(salvaged.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                    "scanner_summary": str(salvaged.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                    "monitor_summary": str(salvaged.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                    "supervisor_summary": str(salvaged.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                    "executor_summary": str(salvaged.get("executor_summary") or fallback.get("executor_summary") or ""),
                    "reporter_summary": str(salvaged.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                    "operator_takeaways": [str(x or "") for x in list(salvaged.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                    "reason": "free_model_salvage_pass",
                }
            try:
                line_raw = router.chat(
                    "operator_ui",
                    _build_operator_brief_line_messages(compact_input),
                    policy={
                        "temperature": 0.0,
                        "max_tokens": 500,
                        "timeout_sec": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "2"))),
                        **({"model": model} if model else {}),
                    },
                )
            except Exception:
                line_raw = ""
            line_parsed = _parse_operator_brief_lines(line_raw)
            if line_parsed:
                return {
                    "status": "line_repaired",
                    "model": model,
                    "headline": str(line_parsed.get("headline") or fallback.get("headline") or ""),
                    "commander_summary": str(line_parsed.get("commander_summary") or fallback.get("commander_summary") or ""),
                    "strategist_summary": str(line_parsed.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                    "scanner_summary": str(line_parsed.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                    "monitor_summary": str(line_parsed.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                    "supervisor_summary": str(line_parsed.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                    "executor_summary": str(line_parsed.get("executor_summary") or fallback.get("executor_summary") or ""),
                    "reporter_summary": str(line_parsed.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                    "operator_takeaways": [str(x or "") for x in list(line_parsed.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                    "reason": "llm_line_repair_pass",
                }
        salvaged = _salvage_operator_brief_fields(raw)
        if salvaged:
            return {
                "status": "salvaged",
                "model": model,
                "headline": str(salvaged.get("headline") or fallback.get("headline") or ""),
                "commander_summary": str(salvaged.get("commander_summary") or fallback.get("commander_summary") or ""),
                "strategist_summary": str(salvaged.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                "scanner_summary": str(salvaged.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                "monitor_summary": str(salvaged.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                "supervisor_summary": str(salvaged.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                "executor_summary": str(salvaged.get("executor_summary") or fallback.get("executor_summary") or ""),
                "reporter_summary": str(salvaged.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                "operator_takeaways": [str(x or "") for x in list(salvaged.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                "reason": "llm_partial_salvage",
            }
        fallback["model"] = model
        fallback["reason"] = "llm_parse_error"
        return fallback
    return {
        "status": "ok",
        "model": model,
        "headline": str(parsed.get("headline") or fallback.get("headline") or ""),
        "commander_summary": str(parsed.get("commander_summary") or fallback.get("commander_summary") or ""),
        "strategist_summary": str(parsed.get("strategist_summary") or fallback.get("strategist_summary") or ""),
        "scanner_summary": str(parsed.get("scanner_summary") or fallback.get("scanner_summary") or ""),
        "monitor_summary": str(parsed.get("monitor_summary") or fallback.get("monitor_summary") or ""),
        "supervisor_summary": str(parsed.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
        "executor_summary": str(parsed.get("executor_summary") or fallback.get("executor_summary") or ""),
        "reporter_summary": str(parsed.get("reporter_summary") or fallback.get("reporter_summary") or ""),
        "operator_takeaways": [str(x or "") for x in list(parsed.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
    }


def _load_cached_operator_brief(config: OperatorUIConfig, run_id: str) -> Dict[str, Any]:
    if not run_id:
        return {}
    path = config.operator_ui_cache_path / f"{run_id}.json"
    cached = _read_json(path)
    if not isinstance(cached, dict):
        return {}
    if int(cached.get("version") or 0) < 2:
        return {}
    return cached


def _save_cached_operator_brief(config: OperatorUIConfig, run_id: str, brief: Dict[str, Any]) -> None:
    if not run_id or not isinstance(brief, dict):
        return
    path = config.operator_ui_cache_path / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(brief)
    payload["version"] = 2
    payload["cached_at"] = datetime.now(tz=KST).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_operator_brief_with_cache(config: OperatorUIConfig, detail: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(detail.get("run_id") or "").strip()
    cached = _load_cached_operator_brief(config, run_id)
    if cached:
        return cached
    brief = _load_operator_brief(detail)
    _save_cached_operator_brief(config, run_id, brief)
    return brief


def load_run_detail(config: OperatorUIConfig, run_id: str) -> Dict[str, Any]:
    all_rows = [row for row in _iter_jsonl(config.event_log_path) if str(row.get("run_id") or "").strip() == str(run_id or "").strip()]
    all_rows = sorted(all_rows, key=lambda row: _to_epoch(row.get("ts")) or 0)
    evidence_rows = [row for row in _iter_jsonl(config.evidence_log_path) if str(row.get("run_id") or "").strip() == str(run_id or "").strip()]
    evidence_rows = sorted(evidence_rows, key=lambda row: _to_epoch(row.get("timestamp")) or 0)

    if not all_rows:
        return {"run_id": str(run_id or ""), "found": False}

    route_row = next((r for r in all_rows if str(r.get("stage") or "") == "commander_router" and str(r.get("event") or "") == "route"), {})
    end_row = next((r for r in reversed(all_rows) if str(r.get("stage") or "") == "commander_router" and str(r.get("event") or "") == "end"), {})
    strategist_summary = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "strategist" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)), {})
    strategist_llm = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "strategist_llm" and str(r.get("event") or "") == "result" and isinstance(r.get("payload"), dict)), {})
    scanner_summary = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "scanner" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)), {})
    monitor_summary = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)), {})
    verdict_payload = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "verdict" and isinstance(r.get("payload"), dict)), {})
    execution_payload = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)), {})
    normalized_execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})

    strategic_frame = next(
        (
            (r.get("payload") or {}).get("payload")
            for r in reversed(all_rows)
            if str(r.get("stage") or "") == "decision_trace"
            and str(r.get("event") or "") == "strategic_frame"
            and isinstance(r.get("payload"), dict)
            and str((r.get("payload") or {}).get("agent") or "") == "strategist"
        ),
        {},
    )
    candidate_selection = next(
        (
            (r.get("payload") or {}).get("payload")
            for r in reversed(all_rows)
            if str(r.get("stage") or "") == "decision_trace"
            and str(r.get("event") or "") == "candidate_selection"
            and isinstance(r.get("payload"), dict)
            and str((r.get("payload") or {}).get("agent") or "") == "scanner"
        ),
        {},
    )
    entry_exit_decision = next(
        (
            (r.get("payload") or {}).get("payload")
            for r in reversed(all_rows)
            if str(r.get("stage") or "") == "decision_trace"
            and str(r.get("event") or "") == "entry_exit_decision"
            and isinstance(r.get("payload"), dict)
            and str((r.get("payload") or {}).get("agent") or "") == "monitor"
        ),
        {},
    )
    selected_candidate = candidate_selection.get("selected_candidate") if isinstance(candidate_selection.get("selected_candidate"), dict) else {}
    feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
    feature_coverage = _feature_coverage(feature_snapshot)
    quote_metrics = _quote_metrics_snapshot(feature_snapshot)

    strategist_evidence = _latest_evidence(evidence_rows, agent="strategist", stage="theme_selection")
    reporter_evidence = _latest_evidence(evidence_rows, agent="reporter", stage="post_run_analysis")
    first_dt = _to_datetime(all_rows[0].get("ts"))
    run_day = first_dt.strftime("%Y-%m-%d") if first_dt else ""
    primary_symbol = normalize_symbol(
        normalized_execution.get("symbol")
        or scanner_summary.get("top_stock")
        or candidate_selection.get("selected_symbol")
        or "",
        allow_test_symbols=True,
    ).strip()
    same_day_symbol_trades = []
    if primary_symbol:
        same_day_symbol_trades = [
            trade
            for trade in load_recent_trades_for_day(config, run_day, limit=500)
            if str(trade.get("symbol") or "").strip() == primary_symbol
        ]
    same_day_symbol_run_chain = load_symbol_run_chain(config, run_day, primary_symbol, limit=3) if primary_symbol else []

    detail = {
        "found": True,
        "run_id": str(run_id or ""),
        "started_at": _iso_to_display(route_row.get("ts")),
        "completed_at": _iso_to_display(end_row.get("ts")),
        "commander": {
            "mode": str((route_row.get("payload") or {}).get("mode") or ""),
            "phase": str((route_row.get("payload") or {}).get("phase") or ""),
            "agents": list((route_row.get("payload") or {}).get("agents") or []),
            "status": str((end_row.get("payload") or {}).get("status") or ""),
            "path": str((end_row.get("payload") or {}).get("path") or ""),
        },
        "strategist": {
            "summary": strategist_summary,
            "llm": strategist_llm,
            "decision_trace": strategic_frame if isinstance(strategic_frame, dict) else {},
            "evidence": {
                "raw_input": strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {},
                "llm_prompt": str(strategist_evidence.get("llm_prompt") or ""),
                "llm_response": str(strategist_evidence.get("llm_response") or ""),
                "parsed_output": strategist_evidence.get("parsed_output") if isinstance(strategist_evidence.get("parsed_output"), dict) else {},
            },
        },
        "scanner": {
            "summary": scanner_summary,
            "decision_trace": candidate_selection if isinstance(candidate_selection, dict) else {},
            "feature_coverage": feature_coverage,
            "quote_metrics": quote_metrics,
        },
        "monitor": {
            "summary": monitor_summary,
            "decision_trace": entry_exit_decision if isinstance(entry_exit_decision, dict) else {},
        },
        "supervisor": {
            "verdict": verdict_payload,
        },
        "executor": {
            "execution": execution_payload,
        },
        "same_day_symbol_trade_history": {
            "day": run_day,
            "symbol": primary_symbol,
            "trade_count": len(same_day_symbol_trades),
            "trades": same_day_symbol_trades[:20],
        },
        "same_day_symbol_run_chain": {
            "day": run_day,
            "symbol": primary_symbol,
            "run_count": len(same_day_symbol_run_chain),
            "runs": same_day_symbol_run_chain,
        },
        "reporter": _reporter_snippet_for_run(config, str(run_id or ""), run_day),
        "raw_event_count": len(all_rows),
        "stage_counts": _count_stages(all_rows),
        "event_preview": [
            {
                "ts": _iso_to_display(row.get("ts")),
                "stage": str(row.get("stage") or ""),
                "event": str(row.get("event") or ""),
                "payload": _truncate_json(row.get("payload")),
            }
            for row in all_rows[:120]
        ],
    }
    detail["operator_brief"] = _load_operator_brief_with_cache(config, detail)
    return detail


def load_strategy_memory_timeline(config: OperatorUIConfig, *, limit: int = 7) -> List[Dict[str, Any]]:
    root = config.strategy_memory_path
    if not root.exists():
        return []
    files = sorted(root.glob("*.json"), reverse=True)[: max(1, int(limit))]
    out: List[Dict[str, Any]] = []
    for path in files:
        obj = _read_json(path)
        latest = obj.get("latest_feedback") if isinstance(obj.get("latest_feedback"), dict) else {}
        out.append(
            {
                "day": str(obj.get("day") or path.stem),
                "updated_at": str(obj.get("updated_at") or ""),
                "latest_run_id": str(obj.get("latest_run_id") or ""),
                "trade_count": _safe_int((latest.get("trade_summary") or {}).get("trade_count"), 0) if isinstance(latest.get("trade_summary"), dict) else 0,
                "monitor_status": str((latest.get("monitor_evaluation") or {}).get("monitor_status") or "") if isinstance(latest.get("monitor_evaluation"), dict) else "",
                "theme_alignment_status": str((latest.get("strategist_evaluation") or {}).get("theme_alignment_status") or "") if isinstance(latest.get("strategist_evaluation"), dict) else "",
                "ai_findings": list(latest.get("ai_findings") or [])[:2],
                "path": str(path),
            }
        )
    return out


def _count_stages(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("stage") or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def load_health(config: OperatorUIConfig) -> Dict[str, Any]:
    latest_day = _latest_event_day(config.event_log_path)
    operator_summary = _read_exact_day(config.reports_root / "operator_summary", "operator_summary", latest_day)
    reporter = _read_exact_day(config.reports_root / "dev" / "analysis" / "reporter_analysis", "reporter_analysis", latest_day)
    if operator_summary:
        executive = operator_summary.get("executive_summary") if isinstance(operator_summary.get("executive_summary"), dict) else {}
        system_status = str(executive.get("system_status") or "UNKNOWN")
    else:
        system_status = "LIVE" if latest_day else "UNKNOWN"
    if reporter:
        ai_review = reporter.get("ai_review") if isinstance(reporter.get("ai_review"), dict) else {}
        ai_review_status = str(ai_review.get("status") or "disabled")
    else:
        ai_review_status = "not_generated_yet" if latest_day else "disabled"
    return {
        "status": "ok",
        "latest_day": latest_day,
        "system_status": system_status,
        "ai_review_status": ai_review_status,
        "event_log_path": str(config.event_log_path),
        "reports_root": str(config.reports_root),
    }
