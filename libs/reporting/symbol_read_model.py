from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

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


def build_symbol_read_model(trades_root: str, symbol: str) -> Dict[str, Any]:
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
            if str(t.get(f) or "").strip().lower() == "unknown":
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