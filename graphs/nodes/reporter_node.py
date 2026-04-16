from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from libs.reporting.intraday_trade_reports import generate_intraday_trade_artifacts
from libs.reporting.single_trade_report import (
    build_single_trade_report_id,
    generate_single_trade_report,
)


def _normalize_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"single_trade", "single", "direct", "intraday_single_trade"}:
        return "single_trade"
    if raw in {"bundle", "intraday_bundle"}:
        return "bundle"
    return "single_trade"


def _resolve_runtime_mode(state: Dict[str, Any]) -> str:
    state_mode = (
        state.get("intraday_report_runtime_mode")
        or state.get("report_runtime_mode")
        or state.get("reporter_runtime_mode")
    )
    if str(state_mode or "").strip():
        return _normalize_mode(state_mode)
    return _normalize_mode(os.getenv("INTRADAY_REPORT_RUNTIME_MODE", "single_trade"))


def reporter_node(state: Dict[str, Any], *, root: Path | None = None) -> Dict[str, Any]:
    """Thin report node for intraday trade reporting.

    Default behavior uses focused single-trade generation.
    Bundle mode is still available via explicit state/env override.
    """
    mode = _resolve_runtime_mode(state)
    if mode == "single_trade":
        repo_root = Path(root) if root is not None else None
        trade_id = build_single_trade_report_id(state, root=repo_root)
        out = generate_single_trade_report(trade_id, state=state, root=repo_root)
        return {
            **dict(out or {}),
            "report_runtime_mode": "single_trade",
            "bundle_used": False,
            "trade_id": str((out or {}).get("trade_id") or trade_id),
        }

    out = generate_intraday_trade_artifacts(state, root=root)
    return {
        **dict(out or {}),
        "report_runtime_mode": "bundle",
        "bundle_used": bool((out or {}).get("bundle_used", True)),
    }
