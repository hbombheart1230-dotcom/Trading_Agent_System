from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from libs.reporting.llm_artifacts import symbol_artifact_paths
from libs.reporting.symbol_trade_report import generate_symbol_trade_report


def read_json_list(path: Path) -> List[Any]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def symbol_report_mode() -> str:
    raw = str(os.getenv("DAILY_REPORT_SYMBOL_REPORT_MODE") or "missing_or_stale").strip().lower()
    if raw in {"always", "refresh", "force"}:
        return "always"
    if raw in {"skip", "none", "false", "0", "off"}:
        return "skip"
    return "missing_or_stale"


def expected_trade_ids_by_symbol(trade_index: List[Dict[str, Any]]) -> Dict[str, set[str]]:
    expected: Dict[str, set[str]] = {}
    for row in trade_index:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        trade_id = str(row.get("trade_id") or "").strip()
        if not symbol or not trade_id:
            continue
        expected.setdefault(symbol, set()).add(trade_id)
    return expected


def symbol_report_is_current(reports_root: Path, symbol: str, expected_trade_ids: set[str]) -> bool:
    paths = symbol_artifact_paths(reports_root, symbol)
    report_json = paths["symbol_trade_report_json"]
    history_json = paths["trade_history_json"]
    if not report_json.exists() or not history_json.exists():
        return False
    if not expected_trade_ids:
        return True
    history = read_json_list(history_json)
    covered = {
        str(row.get("trade_id") or "").strip()
        for row in history
        if isinstance(row, dict) and str(row.get("trade_id") or "").strip()
    }
    return expected_trade_ids.issubset(covered)


def refresh_symbol_reports(
    *,
    events_path: Path,
    reports_root: Path,
    symbols: List[str],
    trade_index: List[Dict[str, Any]],
) -> Dict[str, Any]:
    mode = symbol_report_mode()
    generated: List[Dict[str, Any]] = []
    skipped_existing: List[str] = []
    skipped_mode: List[str] = []
    expected_by_symbol = expected_trade_ids_by_symbol(trade_index)

    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            continue
        if mode == "skip":
            skipped_mode.append(symbol)
            continue
        if mode == "missing_or_stale" and symbol_report_is_current(
            reports_root,
            symbol,
            expected_by_symbol.get(symbol, set()),
        ):
            skipped_existing.append(symbol)
            continue
        generated.append(
            generate_symbol_trade_report(
                events_path=events_path,
                reports_root=reports_root,
                symbol=symbol,
            )
        )

    return {
        "mode": mode,
        "symbol_count": len([symbol for symbol in symbols if str(symbol or "").strip()]),
        "generated": generated,
        "generated_count": len(generated),
        "skipped_existing_count": len(skipped_existing),
        "skipped_by_mode_count": len(skipped_mode),
        "skipped_existing_symbols": skipped_existing[:20],
        "skipped_by_mode_symbols": skipped_mode[:20],
    }
