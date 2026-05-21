from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.core.symbols import normalize_symbol
from libs.reporting.live_execution_report_context import to_epoch, utc_day
from libs.reporting.trade_execution_snapshot import normalize_execution_row
from libs.reporting.trade_story_pipeline import safe_int


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def normalize_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_execution_row(payload if isinstance(payload, dict) else {})


def latest_execution_day(event_log_path: Path) -> str:
    best_day = ""
    best_epoch = -1
    for row in iter_jsonl(event_log_path):
        if str(row.get("stage") or "") != "execute_from_packet" or str(row.get("event") or "") != "execution":
            continue
        execution = normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"}:
            continue
        if not str(execution.get("symbol") or "").strip():
            continue
        epoch = to_epoch(row.get("ts"))
        if epoch is None or epoch < best_epoch:
            continue
        best_epoch = epoch
        best_day = utc_day(row.get("ts"))
    return best_day


def resolve_execution_runs(
    event_log_path: Path,
    day: str,
    *,
    event_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    source_rows = list(event_rows) if isinstance(event_rows, list) else list(iter_jsonl(event_log_path))
    rows = sorted(source_rows, key=lambda row: to_epoch(row.get("ts")) or 0, reverse=True)
    for row in rows:
        if str(row.get("stage") or "") != "execute_from_packet" or str(row.get("event") or "") != "execution":
            continue
        if day and utc_day(row.get("ts")) != day:
            continue
        run_id = str(row.get("run_id") or "").strip()
        if not run_id or run_id in seen:
            continue
        execution = normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        if str(execution.get("action") or "").upper() not in {"BUY", "SELL"} or not str(execution.get("symbol") or "").strip():
            continue
        seen.add(run_id)
        out.append(
            {
                "run_id": run_id,
                "ts": str(row.get("ts") or ""),
                "action": str(execution.get("action") or "").upper(),
                "symbol": str(execution.get("symbol") or ""),
                "qty": safe_int(execution.get("qty"), 0),
                "status": str(execution.get("status") or ""),
                "ord_no": str(execution.get("ord_no") or ""),
            }
        )
    out.sort(key=lambda row: to_epoch(row.get("ts")) or 0)
    return out


def targeted_execution_context(
    execution_runs: List[Dict[str, Any]],
    *,
    target_run_id: str = "",
    target_symbol: str = "",
    max_runs: int = 50,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = list(execution_runs or [])
    normalized_symbol = normalize_symbol(target_symbol, allow_test_symbols=True)
    targeted_mode = False
    target_row: Dict[str, Any] = {}
    if target_run_id:
        target_row = next(
            (row for row in rows if str(row.get("run_id") or "").strip() == str(target_run_id or "").strip()),
            {},
        )
        if isinstance(target_row, dict) and target_row:
            targeted_mode = True
            normalized_symbol = normalize_symbol(target_row.get("symbol") or normalized_symbol, allow_test_symbols=True)
            target_ts_epoch = to_epoch(target_row.get("ts")) or 0.0
            lifecycle_context_rows = [
                row
                for row in rows
                if (
                    not normalized_symbol
                    or normalize_symbol(row.get("symbol") or "", allow_test_symbols=True) == normalized_symbol
                )
                and ((to_epoch(row.get("ts")) or 0.0) <= target_ts_epoch)
            ]
            rows = [dict(target_row)]
        else:
            lifecycle_context_rows = []
    elif normalized_symbol:
        targeted_mode = True
        rows = [
            row
            for row in rows
            if normalize_symbol(row.get("symbol") or "", allow_test_symbols=True) == normalized_symbol
        ]
        lifecycle_context_rows = list(rows)
    else:
        rows = rows[: max(1, int(max_runs))]
        lifecycle_context_rows = list(rows)
    return rows, {
        "targeted_mode": bool(targeted_mode),
        "target_run_id": str(target_run_id or ""),
        "target_symbol": str(normalized_symbol or ""),
        "target_row": dict(target_row or {}),
        "execution_run_count": len(rows),
        "lifecycle_context_run_ids": [
            str(row.get("run_id") or "").strip()
            for row in lifecycle_context_rows
            if str(row.get("run_id") or "").strip()
        ],
        "lifecycle_context_run_count": len(lifecycle_context_rows),
    }


def lifecycle_matches_target(lifecycle: Dict[str, Any], *, target_run_id: str = "", target_symbol: str = "") -> bool:
    run_id_target = str(target_run_id or "").strip()
    symbol_target = normalize_symbol(target_symbol, allow_test_symbols=True)
    if not run_id_target and not symbol_target:
        return True
    lifecycle_symbol = normalize_symbol(lifecycle.get("symbol") or "", allow_test_symbols=True)
    if symbol_target and lifecycle_symbol and lifecycle_symbol != symbol_target:
        return False
    run_ids = {str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()}
    entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    run_ids.add(str(entry_ctx.get("run_id") or "").strip())
    run_ids.add(str(exit_ctx.get("run_id") or "").strip())
    run_ids.update(str(x or "").strip() for x in list(holding.get("run_ids") or []) if str(x or "").strip())
    if run_id_target:
        return run_id_target in run_ids
    return True
