from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from libs.reporting.trade_symbol_context import (
    normalize_scanner_context_for_executed_symbol,
)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _normalize_entry(entry: Any, *, symbol: str) -> tuple[Any, bool]:
    if not isinstance(entry, Mapping):
        return entry, False
    out = dict(entry)
    scanner = out.get("scanner_context")
    if not isinstance(scanner, Mapping):
        return out, False
    normalized = normalize_scanner_context_for_executed_symbol(
        scanner,
        executed_symbol=symbol,
    )
    changed = normalized != dict(scanner)
    out["scanner_context"] = normalized
    return out, changed


def repair_trade_symbol_artifacts(
    trade_dir: Path,
    *,
    write: bool = True,
) -> Dict[str, Any]:
    trade_dir = Path(trade_dir)
    lifecycle_path = trade_dir / "lifecycle_bundle.json"
    entry_path = trade_dir / "entry.json"
    lifecycle = _read_json(lifecycle_path)
    entry = _read_json(entry_path)
    name_parts = trade_dir.name.split("_")
    name_symbol = name_parts[2] if len(name_parts) >= 3 else ""
    symbol = str(
        lifecycle.get("symbol")
        or entry.get("symbol")
        or name_symbol
    ).strip().upper()
    changed_files: list[str] = []
    if not symbol:
        return {
            "trade_dir": str(trade_dir),
            "symbol": "",
            "changed": False,
            "changed_files": [],
            "reason": "symbol_unavailable",
        }

    if entry:
        normalized_entry, changed = _normalize_entry(entry, symbol=symbol)
        if changed:
            entry = normalized_entry
            changed_files.append(str(entry_path))
            if write:
                _write_json(entry_path, entry)

    if lifecycle:
        lifecycle_changed = False
        for key_path in (("entry",), ("lifecycle", "entry")):
            parent = lifecycle
            for key in key_path[:-1]:
                value = parent.get(key)
                if not isinstance(value, dict):
                    parent = {}
                    break
                parent = value
            leaf = key_path[-1]
            if parent and leaf in parent:
                normalized_entry, changed = _normalize_entry(parent.get(leaf), symbol=symbol)
                if changed:
                    parent[leaf] = normalized_entry
                    lifecycle_changed = True
        scanner_reason = lifecycle.get("scanner_reason_human")
        if isinstance(scanner_reason, Mapping):
            normalized_reason = normalize_scanner_context_for_executed_symbol(
                scanner_reason,
                executed_symbol=symbol,
            )
            if normalized_reason != dict(scanner_reason):
                lifecycle["scanner_reason_human"] = normalized_reason
                lifecycle_changed = True
        if lifecycle_changed:
            changed_files.append(str(lifecycle_path))
            if write:
                _write_json(lifecycle_path, lifecycle)

    return {
        "trade_dir": str(trade_dir),
        "symbol": symbol,
        "changed": bool(changed_files),
        "changed_files": changed_files,
        "reason": "normalized" if changed_files else "already_consistent",
    }


def repair_all_trade_symbol_artifacts(
    reports_root: Path = Path("reports"),
    *,
    day: str = "",
    write: bool = True,
) -> Dict[str, Any]:
    root = Path(reports_root) / "trades"
    if day:
        root = root / day
    trade_dirs = sorted(
        {
            path.parent
            for path in root.rglob("lifecycle_bundle.json")
        }
    ) if root.exists() else []
    results = [
        repair_trade_symbol_artifacts(trade_dir, write=write)
        for trade_dir in trade_dirs
    ]
    changed = [row for row in results if row.get("changed")]
    return {
        "schema_version": "trade_symbol_integrity_repair.v1",
        "reports_root": str(reports_root),
        "day": day,
        "write": write,
        "trade_count": len(results),
        "changed_trade_count": len(changed),
        "changed_file_count": sum(len(row.get("changed_files") or []) for row in changed),
        "results": results,
    }


__all__ = [
    "repair_all_trade_symbol_artifacts",
    "repair_trade_symbol_artifacts",
]
