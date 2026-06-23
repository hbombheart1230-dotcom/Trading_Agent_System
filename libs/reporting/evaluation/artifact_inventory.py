from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def iter_trade_dirs(reports_root: Path, day: str) -> list[Path]:
    root = Path(reports_root) / "trades" / day
    if not root.exists():
        return []
    return sorted({path.parent for path in root.rglob("lifecycle_bundle.json")})


def _record(path: Path, *, required: bool) -> dict[str, Any]:
    exists = path.exists()
    payload = read_json(path) if exists and path.suffix.lower() == ".json" else {}
    return {
        "path": str(path),
        "required": required,
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "modified_epoch": path.stat().st_mtime if exists else None,
        "schema_version": str(payload.get("schema_version") or ""),
        "missing_reason": "" if exists else "artifact_not_found",
    }


def inventory_trade(trade_dir: Path) -> dict[str, Any]:
    paths: Iterable[tuple[str, Path, bool]] = (
        ("lifecycle_bundle", trade_dir / "lifecycle_bundle.json", True),
        ("entry", trade_dir / "entry.json", True),
        ("exit", trade_dir / "exit.json", False),
        ("scanner_evidence", trade_dir / "evidence" / "scanner_evidence.json", True),
        ("strategist_evidence", trade_dir / "evidence" / "strategist_evidence.json", True),
        ("commander_evidence", trade_dir / "evidence" / "commander_evidence.json", True),
        ("monitor_evidence", trade_dir / "evidence" / "monitor_evidence.json", True),
        ("ai_trade_summary", trade_dir / "reports" / "ai_trade_summary.json", False),
        ("post_exit_shadow", trade_dir / "reports" / "post_exit_shadow.json", False),
    )
    artifacts = {name: _record(path, required=required) for name, path, required in paths}
    missing_required = [name for name, row in artifacts.items() if row["required"] and not row["exists"]]
    return {
        "trade_dir": str(trade_dir),
        "trade_id": trade_dir.name,
        "artifacts": artifacts,
        "missing_required": missing_required,
        "complete": not missing_required,
    }


def build_artifact_inventory(reports_root: Path, day: str) -> dict[str, Any]:
    trades = [inventory_trade(path) for path in iter_trade_dirs(reports_root, day)]
    daily_root = Path(reports_root) / "operator_summary" / "daily" / day
    daily = {
        name: _record(daily_root / filename, required=required)
        for name, filename, required in (
            ("daily_summary", "daily_summary.json", True),
            ("operator_summary", "operator_summary.json", False),
            ("q8_shadow_blocker_review", "q8_shadow_blocker_review.json", True),
            ("closeout_maintenance", "closeout_maintenance.json", False),
            ("q9_decision_windows", "q9_decision_windows.json", False),
        )
    }
    required_count = sum(
        1 for trade in trades for row in trade["artifacts"].values() if row["required"]
    ) + sum(1 for row in daily.values() if row["required"])
    present_required_count = sum(
        1 for trade in trades for row in trade["artifacts"].values() if row["required"] and row["exists"]
    ) + sum(1 for row in daily.values() if row["required"] and row["exists"])
    return {
        "schema_version": "artifact_inventory.v1",
        "day": day,
        "trade_count": len(trades),
        "required_artifact_count": required_count,
        "present_required_artifact_count": present_required_count,
        "required_coverage": round(present_required_count / required_count, 4) if required_count else 0.0,
        "trades": trades,
        "daily_artifacts": daily,
    }
