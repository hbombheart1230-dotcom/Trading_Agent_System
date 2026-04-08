from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def build_data_freshness(
    *,
    generated_at: Any,
    source_run_count: Any,
    latest_run_id: Any,
    latest_run_ts: Any,
    stale: Any = False,
    stale_reason: str = "",
    freshness_status: str = "",
    source_window_summary: str = "",
) -> Dict[str, Any]:
    run_count = _safe_int(source_run_count, 0)
    latest_id = str(latest_run_id or "").strip()
    latest_ts = str(latest_run_ts or "").strip()
    stale_flag = _safe_bool(stale)

    if not freshness_status:
        if run_count <= 0:
            freshness_status = "empty"
        elif stale_flag:
            freshness_status = "stale"
        else:
            freshness_status = "fresh"

    if not stale_reason:
        if run_count <= 0:
            stale_reason = "no_source_runs"
        elif stale_flag:
            stale_reason = "source_window_advanced_since_generation"
        else:
            stale_reason = "aligned_with_source_window"

    if not source_window_summary:
        source_window_summary = (
            f"runs={run_count}, latest_run_id={latest_id or '-'}, latest_run_ts={latest_ts or '-'}"
        )

    return {
        "generated_at": str(generated_at or ""),
        "source_run_count": int(run_count),
        "latest_run_id": latest_id,
        "latest_run_ts": latest_ts,
        "freshness_status": str(freshness_status or "unknown"),
        "stale": bool(stale_flag),
        "stale_reason": str(stale_reason or ""),
        "source_window_summary": str(source_window_summary or ""),
    }


def build_route_provenance(route_summary: Mapping[str, Any] | None) -> Dict[str, Any]:
    summary = dict(route_summary or {})
    return {
        "route_source": str(summary.get("route_source") or "unavailable"),
        "route_source_run_count": int(_safe_int(summary.get("route_source_run_count"), 0)),
        "route_source_missing_count": int(_safe_int(summary.get("route_source_missing_count"), 0)),
        "route_source_breakdown": dict(summary.get("route_source_breakdown") or {}),
    }


def render_data_freshness_markdown(data_freshness: Mapping[str, Any], *, title: str = "## Data Freshness") -> List[str]:
    meta = dict(data_freshness or {})
    return [
        title,
        "",
        f"- generated_at: `{str(meta.get('generated_at') or '')}`",
        f"- source_run_count: **{_safe_int(meta.get('source_run_count'), 0)}**",
        f"- latest_run_id: `{str(meta.get('latest_run_id') or '-')}`",
        f"- latest_run_ts: `{str(meta.get('latest_run_ts') or '-')}`",
        f"- freshness_status: `{str(meta.get('freshness_status') or 'unknown')}`",
        f"- stale: **{bool(meta.get('stale'))}**",
        f"- stale_reason: `{str(meta.get('stale_reason') or '')}`",
        f"- source_window_summary: `{str(meta.get('source_window_summary') or '')}`",
    ]
