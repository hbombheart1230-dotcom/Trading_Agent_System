from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from libs.reporting.intraday_trade_reports import generate_intraday_trade_artifacts


def _normalize_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"bundle", "intraday_bundle"}:
        return "bundle"
    if raw in {"single_trade", "single", "direct", "intraday_single_trade"}:
        return "single_trade"
    return "bundle"


def _resolve_runtime_mode(state: Dict[str, Any]) -> str:
    state_mode = (
        state.get("intraday_report_runtime_mode")
        or state.get("report_runtime_mode")
        or state.get("reporter_runtime_mode")
    )
    if str(state_mode or "").strip():
        return _normalize_mode(state_mode)
    return _normalize_mode(os.getenv("INTRADAY_REPORT_RUNTIME_MODE", "bundle"))


def reporter_node(state: Dict[str, Any], *, root: Path | None = None) -> Dict[str, Any]:
    """Thin report node for intraday trade reporting.

    Live intraday reporting is bundle-only.
    Any single-trade request is ignored in this operating path.
    """
    requested_mode = _resolve_runtime_mode(state)
    out = generate_intraday_trade_artifacts(state, root=root)
    return {
        **dict(out or {}),
        "report_runtime_mode": "bundle",
        "bundle_used": bool((out or {}).get("bundle_used", True)),
        "requested_report_runtime_mode": requested_mode,
        "runtime_mode_forced": bool(requested_mode != "bundle"),
    }
