from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

from libs.runtime.canonical_artifacts import load_run_canonical_artifacts


def _has_meaningful_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    for value in payload.values():
        if isinstance(value, dict) and _has_meaningful_payload(value):
            return True
        if isinstance(value, list) and any(item not in ({}, [], None, "") for item in value):
            return True
        if value not in ({}, [], None, ""):
            return True
    return False


def load_run_canonical_sources(reports_root: Path, run_id: str, run_day: str = "") -> Dict[str, Any]:
    return load_run_canonical_artifacts(
        reports_root=Path(reports_root),
        run_id=str(run_id or "").strip(),
        day_hint=str(run_day or "").strip(),
    )


def prefer_canonical_agent_payload(
    canonical_sources: Dict[str, Any],
    agent: str,
    fallback: Dict[str, Any],
    *,
    fallback_source: str = "event_log",
) -> Tuple[Dict[str, Any], str]:
    artifact = (
        (canonical_sources.get("artifacts") or {}).get(agent)
        if isinstance(canonical_sources.get("artifacts"), dict)
        else {}
    )
    merged = dict(fallback or {})
    if _has_meaningful_payload(artifact):
        merged.update(dict(artifact or {}))
        return merged, "canonical"
    return dict(fallback or {}), str(fallback_source or "fallback")
