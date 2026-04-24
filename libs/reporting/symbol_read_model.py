from __future__ import annotations

import os
import json
from collections import Counter
import re
from pathlib import Path
from typing import Any, Dict, List

from libs.reporting.llm_artifacts import symbol_artifact_paths
from libs.reporting.trade_read_model import build_trade_read_model


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den == 0.0:
        return default
    return num / den


def _get_dominant(items: List[str], exclude: str = "unknown") -> str:
    valid_items = [str(x).strip() for x in items if str(x).strip() and str(x).strip().lower() != exclude]
    if not valid_items:
        return exclude
    counter = Counter(valid_items)
    if not counter:
        return exclude
    return counter.most_common(1)[0][0]


def _is_unknown_quality_field(field_name: str, value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text or text == "unknown":
        return True
    # Raw lifecycle-only sourcing is still a sparse evidence state for the
    # cumulative symbol model, so keep counting it as incomplete quality.
    if field_name == "data_source" and text == "lifecycle_bundle":
        return True
    return False


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _date_from_trade_id(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"TRD_(\d{8})_", text)
    if not match:
        return ""
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _derive_symbol_read_model_from_memory(reports_root: Path, symbol: str) -> Dict[str, Any]:
    paths = symbol_artifact_paths(reports_root, symbol)
    memory = _read_json(paths["symbol_memory_json"])
    if not memory:
        return {}

    trade_stats = memory.get("trade_stats") if isinstance(memory.get("trade_stats"), dict) else {}
    playbook_stats = memory.get("playbook_stats") if isinstance(memory.get("playbook_stats"), dict) else {}
    pattern_stats = memory.get("pattern_stats") if isinstance(memory.get("pattern_stats"), dict) else {}
    monitor_patterns = memory.get("monitor_patterns") if isinstance(memory.get("monitor_patterns"), dict) else {}
    latest_snapshot = memory.get("latest_snapshot") if isinstance(memory.get("latest_snapshot"), dict) else {}

    closed_trade_count = int(_safe_float(trade_stats.get("completed_trade_count"), 0.0))
    win_rate = _safe_float(trade_stats.get("win_rate"), 0.0)
    win_count = int(round(closed_trade_count * win_rate))
    loss_count = max(0, closed_trade_count - win_count)

    dominant_playbook = "unknown"
    best_count = -1
    for playbook, stats in playbook_stats.items():
        count = int(_safe_float((stats or {}).get("count"), 0.0))
        if count > best_count and str(playbook or "").strip():
            best_count = count
            dominant_playbook = str(playbook).strip()

    recent_success_pattern: List[Dict[str, Any]] = []
    for name in list(pattern_stats.get("successful_entry_patterns") or [])[:3]:
        text = str(name or "").strip()
        if not text:
            continue
        recent_success_pattern.append(
            {
                "playbook": dominant_playbook if dominant_playbook != "unknown" else "",
                "entry_reason": text,
                "exit_reason": "unknown",
                "count": 0,
            }
        )

    repeated_failure_pattern: List[Dict[str, Any]] = []
    for name in list(pattern_stats.get("failed_entry_patterns") or [])[:2]:
        text = str(name or "").strip()
        if text:
            repeated_failure_pattern.append({"type": "entry_pattern", "value": text, "count": 0})
    for name in list(pattern_stats.get("common_monitor_failures") or [])[:2]:
        text = str(name or "").strip()
        if text:
            repeated_failure_pattern.append({"type": "blocker", "value": text, "count": 0})

    dominant_monitor_blocker = "unknown"
    blockers = [str(x or "").strip() for x in list(monitor_patterns.get("repeated_blockers") or []) if str(x or "").strip()]
    if blockers:
        dominant_monitor_blocker = blockers[0]

    return {
        "symbol": str(memory.get("symbol") or symbol).strip().upper(),
        "trade_count": int(_safe_float(trade_stats.get("trade_count"), 0.0)),
        "closed_trade_count": closed_trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "avg_pnl_pct": _safe_float(trade_stats.get("avg_return_pct"), 0.0),
        "avg_hold_duration_sec": _safe_float(trade_stats.get("avg_hold_seconds"), 0.0),
        "last_trade_date": str(latest_snapshot.get("last_trade_date") or ""),
        "last_status": str(latest_snapshot.get("last_status") or ""),
        "dominant_playbook": dominant_playbook,
        "dominant_entry_reason": "unknown",
        "dominant_exit_reason": str(monitor_patterns.get("dominant_exit_failure_axis") or "unknown"),
        "dominant_monitor_blocker": dominant_monitor_blocker,
        "recent_success_pattern": recent_success_pattern,
        "repeated_failure_pattern": repeated_failure_pattern,
        "data_quality": {
            "unknown_fields_ratio": 0.0,
            "data_source": "symbol_memory",
        },
    }


def _derive_symbol_read_model_from_trade_report(reports_root: Path, symbol: str) -> Dict[str, Any]:
    paths = symbol_artifact_paths(reports_root, symbol)
    trade_report = _read_json(paths["symbol_trade_report_json"])
    if not trade_report:
        return {}

    summary = trade_report.get("summary") if isinstance(trade_report.get("summary"), dict) else {}
    pattern_insights = trade_report.get("pattern_insights") if isinstance(trade_report.get("pattern_insights"), dict) else {}
    history_index = trade_report.get("history_index") if isinstance(trade_report.get("history_index"), list) else []
    latest_snapshot = trade_report.get("latest_snapshot") if isinstance(trade_report.get("latest_snapshot"), dict) else {}

    trade_count = int(_safe_float(summary.get("trade_count"), 0.0))
    closed_trade_count = int(_safe_float(summary.get("completed_trade_count"), 0.0))
    win_count = int(_safe_float(summary.get("win_count"), 0.0))
    loss_count = int(_safe_float(summary.get("loss_count"), 0.0))
    win_rate = _safe_div(float(win_count), float(closed_trade_count), 0.0)

    playbook_counter = Counter()
    entry_counter = Counter()
    exit_counter = Counter()
    for row in history_index:
        if not isinstance(row, dict):
            continue
        playbook = str(row.get("playbook") or "").strip()
        entry_reason = str(row.get("entry_reason") or "").strip()
        exit_reason = str(row.get("exit_reason") or "").strip()
        if playbook and playbook.lower() != "unknown":
            playbook_counter[playbook] += 1
        if entry_reason and entry_reason.lower() != "unknown":
            entry_counter[entry_reason] += 1
        if exit_reason and exit_reason.lower() != "unknown":
            exit_counter[exit_reason] += 1

    dominant_playbook = playbook_counter.most_common(1)[0][0] if playbook_counter else "unknown"
    dominant_entry_reason = entry_counter.most_common(1)[0][0] if entry_counter else "unknown"
    dominant_exit_reason = exit_counter.most_common(1)[0][0] if exit_counter else "unknown"

    repeated_failure_pattern: List[Dict[str, Any]] = []
    for name in list(pattern_insights.get("failed_entry_patterns") or [])[:2]:
        text = str(name or "").strip()
        if text:
            repeated_failure_pattern.append({"type": "entry_pattern", "value": text, "count": 0})
    for name in list(pattern_insights.get("common_monitor_failures") or [])[:2]:
        text = str(name or "").strip()
        if text:
            repeated_failure_pattern.append({"type": "blocker", "value": text, "count": 0})

    recent_success_pattern: List[Dict[str, Any]] = []
    for name in list(pattern_insights.get("successful_entry_patterns") or [])[:3]:
        text = str(name or "").strip()
        if not text:
            continue
        recent_success_pattern.append(
            {
                "playbook": dominant_playbook if dominant_playbook != "unknown" else "",
                "entry_reason": text,
                "exit_reason": dominant_exit_reason if dominant_exit_reason != "unknown" else "",
                "count": 0,
            }
        )

    dominant_monitor_blocker = "unknown"
    monitor_failures = [str(x or "").strip() for x in list(pattern_insights.get("common_monitor_failures") or []) if str(x or "").strip()]
    if monitor_failures:
        dominant_monitor_blocker = monitor_failures[0]

    return {
        "symbol": str(trade_report.get("symbol") or symbol).strip().upper(),
        "trade_count": trade_count,
        "closed_trade_count": closed_trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "avg_pnl_pct": _safe_float(summary.get("avg_return_pct"), 0.0),
        "avg_hold_duration_sec": _safe_float(summary.get("avg_hold_seconds"), 0.0),
        "last_trade_date": str(latest_snapshot.get("last_trade_date") or (history_index[-1].get("date") if history_index else "") or ""),
        "last_status": str(latest_snapshot.get("last_status") or ((history_index[-1].get("last_status") if history_index else "") or (history_index[-1].get("status") if history_index else "")) or ""),
        "dominant_playbook": dominant_playbook,
        "dominant_entry_reason": dominant_entry_reason,
        "dominant_exit_reason": dominant_exit_reason,
        "dominant_monitor_blocker": dominant_monitor_blocker,
        "recent_success_pattern": recent_success_pattern,
        "repeated_failure_pattern": repeated_failure_pattern,
        "data_quality": {
            "unknown_fields_ratio": 0.0,
            "data_source": "symbol_trade_report",
        },
    }


def build_symbol_read_model(trades_root: str, symbol: str, *, persisted_only: bool = False) -> Dict[str, Any]:
    """
    Phase 6-1 Task 3: Build a deterministic cumulative read model for a specific symbol.
    Aggregates historical trades using build_trade_read_model as the source of truth.
    """
    target_symbol = str(symbol or "").strip().upper()
    if not target_symbol:
        return _empty_symbol_read_model(target_symbol)

    root_path = Path(trades_root)
    if not root_path.exists() or not root_path.is_dir():
        return _empty_symbol_read_model(target_symbol)

    reports_root = root_path.parent if root_path.name.lower() == "trades" else root_path
    persisted = _derive_symbol_read_model_from_memory(reports_root, target_symbol)
    if persisted:
        return persisted

    persisted_trade_report = _derive_symbol_read_model_from_trade_report(reports_root, target_symbol)
    if persisted_trade_report:
        return persisted_trade_report

    if bool(persisted_only):
        return _empty_symbol_read_model(target_symbol)

    # Find valid trade directories (depth limited for safety, though rglob is used here for simplicity in read-model)
    trade_dirs: List[Path] = []
    for p in root_path.rglob("lifecycle_bundle.json"):
        trade_dirs.append(p.parent)
    for p in root_path.rglob("ai_trade_report.json"):
        if p.parent.name == "reports":
            trade_dirs.append(p.parent.parent)
        elif p.parent.name == "ai_trade_report":
            trade_dirs.append(p.parent.parent)

    # Deduplicate paths
    unique_trade_dirs = list({str(p.resolve()): p for p in trade_dirs}.values())

    trades: List[Dict[str, Any]] = []
    for td in unique_trade_dirs:
        try:
            trm = build_trade_read_model(str(td))
            if str(trm.get("symbol") or "").strip().upper() == target_symbol:
                trades.append(trm)
        except Exception:
            pass

    if not trades:
        return _empty_symbol_read_model(target_symbol)

    return _aggregate_symbol_trades(target_symbol, trades)


def _empty_symbol_read_model(symbol: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "trade_count": 0,
        "closed_trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "avg_pnl_pct": 0.0,
        "avg_hold_duration_sec": 0.0,
        "last_trade_date": "",
        "last_status": "",
        "dominant_playbook": "unknown",
        "dominant_entry_reason": "unknown",
        "dominant_exit_reason": "unknown",
        "dominant_monitor_blocker": "unknown",
        "recent_success_pattern": [],
        "repeated_failure_pattern": [],
        "data_quality": {
            "unknown_fields_ratio": 0.0
        }
    }


def _aggregate_symbol_trades(symbol: str, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    trade_count = len(trades)
    
    playbooks = []
    entry_reasons = []
    exit_reasons = []
    blockers = []
    
    closed_trade_count = 0
    win_count = 0
    loss_count = 0
    total_pnl = 0.0
    total_pnl_pct = 0.0
    total_hold_sec = 0
    last_trade_date = ""
    
    success_patterns_counter = Counter()
    failure_patterns_counter = Counter()
    
    total_fields_checked = 0
    unknown_fields_count = 0

    fields_to_check = ["playbook", "entry_reason", "exit_reason", "primary_blocker_if_no_buy", "execution_label", "data_source"]

    for t in trades:
        # Collect for dominant calculation
        playbooks.append(t.get("playbook"))
        entry_reasons.append(t.get("entry_reason"))
        exit_reasons.append(t.get("exit_reason"))
        blockers.append(t.get("primary_blocker_if_no_buy"))

        # Data quality tracking
        for f in fields_to_check:
            total_fields_checked += 1
            if _is_unknown_quality_field(f, t.get(f)):
                unknown_fields_count += 1

        pnl = float(t.get("pnl") or 0.0)
        pnl_pct = float(t.get("pnl_pct") or 0.0)
        
        # Execution labeling or presence of exit reason indicates a closed trade or a fully blocked cycle.
        # We count it as closed if it had an entry and an exit, or if pnl is non-zero.
        is_closed = str(t.get("exit_reason") or "unknown").lower() != "unknown" or pnl != 0.0
        
        if is_closed:
            closed_trade_count += 1
            total_pnl += pnl
            total_pnl_pct += pnl_pct
            total_hold_sec += int(t.get("hold_duration_sec") or 0)
            
            if pnl > 0:
                win_count += 1
                pattern = f"{t.get('playbook')}|{t.get('entry_reason')}|{t.get('exit_reason')}"
                success_patterns_counter[pattern] += 1
            elif pnl < 0:
                loss_count += 1
                failure_patterns_counter[("exit_reason", str(t.get("exit_reason")))] += 1
        
        blocker = str(t.get("primary_blocker_if_no_buy") or "unknown")
        if blocker.lower() != "unknown":
            failure_patterns_counter[("blocker", blocker)] += 1
        candidate_trade_date = str(t.get("trade_date") or t.get("date") or _date_from_trade_id(t.get("trade_id")) or "").strip()
        if candidate_trade_date and candidate_trade_date > last_trade_date:
            last_trade_date = candidate_trade_date

    # Format success patterns (Top 3)
    recent_success_pattern = []
    for pat, count in success_patterns_counter.most_common(3):
        pb, ent, ext = pat.split("|")
        recent_success_pattern.append({"playbook": pb, "entry_reason": ent, "exit_reason": ext, "count": count})

    # Format failure patterns (Top 3)
    repeated_failure_pattern = []
    for (ptype, pval), count in failure_patterns_counter.most_common(3):
        repeated_failure_pattern.append({"type": ptype, "value": pval, "count": count})

    return {
        "symbol": symbol,
        "trade_count": trade_count,
        "closed_trade_count": closed_trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": _safe_div(float(win_count), float(win_count + loss_count)),
        "total_pnl": float(total_pnl),
        "avg_pnl": _safe_div(total_pnl, float(closed_trade_count)),
        "avg_pnl_pct": _safe_div(total_pnl_pct, float(closed_trade_count)),
        "avg_hold_duration_sec": _safe_div(float(total_hold_sec), float(closed_trade_count)),
        "last_trade_date": last_trade_date,
        "last_status": "",
        "dominant_playbook": _get_dominant(playbooks),
        "dominant_entry_reason": _get_dominant(entry_reasons),
        "dominant_exit_reason": _get_dominant(exit_reasons),
        "dominant_monitor_blocker": _get_dominant(blockers),
        "recent_success_pattern": recent_success_pattern,
        "repeated_failure_pattern": repeated_failure_pattern,
        "data_quality": {
            "unknown_fields_ratio": _safe_div(float(unknown_fields_count), float(total_fields_checked))
        }
    }
