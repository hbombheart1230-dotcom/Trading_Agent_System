from __future__ import annotations

import json
import os
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_STRATEGY_MEMORY_PATH = Path("data/strategy_memory/feedback.jsonl")
DEFAULT_STRATEGY_MEMORY_DAILY_DIR = Path("data/strategy_memory/daily")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_epoch(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        pass
    iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(iso)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
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


def resolve_strategy_memory_path(path: Optional[Path | str] = None) -> Path:
    candidate = path or os.getenv("STRATEGY_MEMORY_PATH")
    if candidate:
        resolved = Path(candidate)
    elif os.getenv("PYTEST_CURRENT_TEST"):
        test_name = str(os.getenv("PYTEST_CURRENT_TEST") or "")
        test_hash = hashlib.sha1(test_name.encode("utf-8")).hexdigest()[:12]
        resolved = Path(tempfile.gettempdir()) / "trading_agent_system" / "strategy_memory" / f"{test_hash}.jsonl"
    else:
        resolved = DEFAULT_STRATEGY_MEMORY_PATH
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    return resolved


def resolve_strategy_memory_daily_dir(path: Optional[Path | str] = None) -> Path:
    candidate = path or os.getenv("STRATEGY_MEMORY_DAILY_DIR")
    if candidate:
        resolved = Path(candidate)
    elif os.getenv("PYTEST_CURRENT_TEST"):
        test_name = str(os.getenv("PYTEST_CURRENT_TEST") or "")
        test_hash = hashlib.sha1(test_name.encode("utf-8")).hexdigest()[:12]
        resolved = Path(tempfile.gettempdir()) / "trading_agent_system" / "strategy_memory" / "daily" / test_hash
    else:
        resolved = DEFAULT_STRATEGY_MEMORY_DAILY_DIR
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    return resolved


def _compact_dict(raw: Any, allowed_keys: List[str]) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out: Dict[str, Any] = {}
    for key in allowed_keys:
        if key in src:
            out[key] = src.get(key)
    return out


def _compact_incidents(raw: Any, *, limit: int = 10) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in list(raw or [])[: max(0, int(limit))]:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "type": str(row.get("type") or ""),
                "severity": str(row.get("severity") or ""),
                "detail": str(row.get("detail") or ""),
            }
        )
    return out


def _build_performance_summary(reporter_output: Dict[str, Any]) -> Dict[str, Any]:
    trade_section = (
        reporter_output.get("trade_decision_summaries")
        if isinstance(reporter_output.get("trade_decision_summaries"), dict)
        else {}
    )
    trades = trade_section.get("trade_summaries") if isinstance(trade_section.get("trade_summaries"), list) else []

    pnl_values: List[float] = []
    hold_values: List[int] = []
    positive = 0
    negative = 0
    for row in trades:
        if not isinstance(row, dict):
            continue
        pnl = _safe_float(row.get("estimated_realized_pnl"), 0.0)
        hold = _safe_int(row.get("holding_duration_sec"), 0)
        pnl_values.append(pnl)
        hold_values.append(hold)
        if pnl > 0:
            positive += 1
        elif pnl < 0:
            negative += 1

    trade_total = len(trades)
    pnl_total = round(sum(pnl_values), 6)
    avg_pnl = round(pnl_total / trade_total, 6) if trade_total > 0 else 0.0
    avg_hold = round(sum(hold_values) / max(1, len(hold_values)), 2) if hold_values else 0.0
    return {
        "trade_summary_total": int(trade_total),
        "estimated_realized_pnl_total": float(pnl_total),
        "avg_estimated_realized_pnl": float(avg_pnl),
        "positive_trade_count": int(positive),
        "negative_trade_count": int(negative),
        "avg_holding_duration_sec": float(avg_hold),
    }


def _build_feedback_record(
    *,
    run_id: str,
    reporter_output: Dict[str, Any],
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    ts = str(timestamp or datetime.now(timezone.utc).isoformat())
    trade_summary_src = reporter_output.get("trade_summary") if isinstance(reporter_output.get("trade_summary"), dict) else {}
    compact_trade_summary = {
        "trade_count": _safe_int(trade_summary_src.get("trade_count"), 0),
        "symbols_traded": list(trade_summary_src.get("symbols_traded") or [])[:12],
        "symbol_hold_durations": list(trade_summary_src.get("symbol_hold_durations") or [])[:12],
        "decision_chain_run_total": _safe_int(trade_summary_src.get("decision_chain_run_total"), 0),
    }
    return {
        "schema_version": "strategy_feedback.v1",
        "run_id": str(run_id or reporter_output.get("run_id") or "").strip(),
        "timestamp": ts,
        "day": str(reporter_output.get("day") or ""),
        "strategy_frame_summary": dict(reporter_output.get("strategy_frame_summary") or {}),
        "strategist_evaluation": _compact_dict(
            reporter_output.get("strategist_evaluation"),
            [
                "themes_proposed",
                "actual_market_leaders_by_scanner",
                "theme_filter_applied_total",
                "scanner_summary_total",
                "theme_alignment_status",
                "assessment",
            ],
        ),
        "scanner_evaluation": _compact_dict(
            reporter_output.get("scanner_evaluation"),
            [
                "candidate_source_top",
                "selected_symbol_top",
                "no_candidate_total",
                "avg_top_score",
                "avg_candidate_pool_after_filter",
                "selection_status",
                "assessment",
            ],
        ),
        "monitor_evaluation": _compact_dict(
            reporter_output.get("monitor_evaluation"),
            [
                "monitor_summary_total",
                "monitor_reason_top",
                "min_hold_blocked_total",
                "sell_cooldown_blocked_total",
                "exit_signal_pending_confirmation_total",
                "confirmed_exit_total",
                "rapid_buy_sell_cycles",
                "monitor_status",
                "assessment",
            ],
        ),
        "supervisor_activity": _compact_dict(
            reporter_output.get("supervisor_activity"),
            [
                "verdict_total",
                "approved_total",
                "blocked_total",
                "blocked_rate",
                "blocked_reason_top",
                "assessment",
            ],
        ),
        "incidents": _compact_incidents(
            (reporter_output.get("incident_postmortem") or {}).get("incidents")
            if isinstance(reporter_output.get("incident_postmortem"), dict)
            else []
        ),
        "ai_findings": [str(x) for x in list(reporter_output.get("ai_findings") or [])[:8]],
        "ai_root_causes": [str(x) for x in list(reporter_output.get("ai_root_causes") or [])[:8]],
        "ai_improvement_suggestions": [
            str(x) for x in list(reporter_output.get("ai_improvement_suggestions") or [])[:8]
        ],
        "trade_summary": compact_trade_summary,
        "performance_summary": _build_performance_summary(reporter_output),
        "report_focus_targets": [str(x) for x in list(reporter_output.get("report_focus_targets") or [])[:8]],
        "operator_facing_summary": _compact_dict(
            reporter_output.get("operator_facing_summary"),
            ["system_health", "summary_lines", "recommended_actions"],
        ),
        "market_context": dict(reporter_output.get("market_context") or {}),
        "improvement_suggestions": [str(x) for x in list(reporter_output.get("improvement_suggestions") or [])[:8]],
        "report_json_path": str(reporter_output.get("report_json_path") or ""),
    }


def _dedupe_feedback_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_by_key: Dict[str, Dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        run_id = str(row.get("run_id") or "").strip()
        day = str(row.get("day") or "").strip()
        report_json_path = str(row.get("report_json_path") or "").strip()
        key = run_id or day or report_json_path or f"row-{idx}"
        existing = latest_by_key.get(key)
        if existing is None:
            latest_by_key[key] = row
            continue
        current_epoch = _to_epoch(row.get("timestamp")) or 0
        existing_epoch = _to_epoch(existing.get("timestamp")) or 0
        if current_epoch >= existing_epoch:
            latest_by_key[key] = row
    return sorted(
        latest_by_key.values(),
        key=lambda row: (
            _to_epoch(row.get("timestamp")) or 0,
            str(row.get("run_id") or ""),
            str(row.get("day") or ""),
        ),
    )


def _write_daily_summary(
    record: Dict[str, Any],
    *,
    daily_dir: Optional[Path | str] = None,
    source_feedback_path: Optional[Path] = None,
) -> Path:
    day = str(record.get("day") or "").strip()
    target_dir = resolve_strategy_memory_daily_dir(daily_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    if not day:
        return target_dir / "unknown.json"
    target = target_dir / f"{day}.json"
    summary = {
        "schema_version": "strategy_feedback_daily.v1",
        "day": day,
        "updated_at": str(record.get("timestamp") or ""),
        "source_feedback_path": str(source_feedback_path or resolve_strategy_memory_path()),
        "latest_run_id": str(record.get("run_id") or ""),
        "latest_feedback": dict(record),
    }
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def save_strategy_feedback(
    run_id: str,
    reporter_output: Dict[str, Any],
    *,
    path: Optional[Path | str] = None,
    daily_dir: Optional[Path | str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    target = resolve_strategy_memory_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = _build_feedback_record(run_id=run_id, reporter_output=reporter_output, timestamp=timestamp)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    daily_summary_path = _write_daily_summary(record, daily_dir=daily_dir, source_feedback_path=target)
    record["_strategy_memory_meta"] = {
        "strategy_memory_path": str(target),
        "daily_summary_path": str(daily_summary_path),
        "storage_mode": "append_jsonl_with_daily_latest",
    }
    return record


def load_recent_daily_strategy_feedback(
    n: int,
    *,
    daily_dir: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    target_dir = resolve_strategy_memory_daily_dir(daily_dir)
    if int(n) <= 0 or not target_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(target_dir.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        latest = obj.get("latest_feedback") if isinstance(obj.get("latest_feedback"), dict) else {}
        if latest:
            rows.append(dict(latest))
    rows = _dedupe_feedback_rows(rows)
    if int(n) <= 0:
        return []
    return rows[-int(n) :]


def load_recent_strategy_feedback(
    n: int,
    *,
    path: Optional[Path | str] = None,
    daily_dir: Optional[Path | str] = None,
    prefer_daily: bool = True,
    dedupe: bool = True,
) -> List[Dict[str, Any]]:
    if int(n) <= 0:
        return []
    if prefer_daily:
        daily_rows = load_recent_daily_strategy_feedback(n, daily_dir=daily_dir)
        if daily_rows:
            return daily_rows[-int(n) :]
    target = resolve_strategy_memory_path(path)
    rows = list(_iter_jsonl(target))
    if dedupe:
        rows = _dedupe_feedback_rows(rows)
    if int(n) <= 0:
        return []
    return rows[-int(n) :]


def load_strategy_feedback_window(
    start: Any,
    end: Any,
    *,
    path: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    target = resolve_strategy_memory_path(path)
    start_epoch = _to_epoch(start)
    end_epoch = _to_epoch(end)
    out: List[Dict[str, Any]] = []
    for row in _iter_jsonl(target):
        ts_epoch = _to_epoch(row.get("timestamp"))
        if ts_epoch is None:
            continue
        if start_epoch is not None and ts_epoch < start_epoch:
            continue
        if end_epoch is not None and ts_epoch > end_epoch:
            continue
        out.append(row)
    return out


def summarize_recent_feedback(
    n: int,
    *,
    path: Optional[Path | str] = None,
    daily_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    rows = load_recent_strategy_feedback(n, path=path, daily_dir=daily_dir)
    ai_findings: List[str] = []
    improvements: List[str] = []
    for row in rows:
        ai_findings.extend([str(x) for x in list(row.get("ai_findings") or [])])
        improvements.extend([str(x) for x in list(row.get("ai_improvement_suggestions") or [])])
    return {
        "feedback_window_size": int(len(rows)),
        "run_ids": [str(r.get("run_id") or "") for r in rows][-max(0, int(n)) :],
        "top_ai_findings": ai_findings[:5],
        "top_improvement_suggestions": improvements[:5],
        "strategy_memory_path": str(resolve_strategy_memory_path(path)),
        "strategy_memory_daily_dir": str(resolve_strategy_memory_daily_dir(daily_dir)),
        "storage_mode": "daily_latest_preferred",
    }
