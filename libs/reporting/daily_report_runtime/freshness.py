from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from libs.reporting.report_metadata import build_data_freshness


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_epoch(ts: Any) -> int:
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except Exception:
        pass
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def epoch_to_iso(epoch: Any) -> str:
    try:
        n = int(float(epoch))
    except Exception:
        return ""
    if n <= 0:
        return ""
    return datetime.fromtimestamp(n, tz=timezone.utc).isoformat(timespec="seconds")


def build_report_freshness(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_row: Dict[str, Any] | None = None
    latest_epoch = 0
    run_ids = {
        str(row.get("run_id") or "").strip()
        for row in rows
        if str(row.get("run_id") or "").strip()
    }
    for row in rows:
        ts = row.get("ts") or (row.get("payload") or {}).get("ts")
        epoch = to_epoch(ts)
        if epoch >= latest_epoch:
            latest_epoch = epoch
            latest_row = row
    return {
        "generated_at": utc_now_iso(),
        "source_run_count": int(len(run_ids)),
        "latest_run_id": str((latest_row or {}).get("run_id") or ""),
        "latest_run_ts": epoch_to_iso(latest_epoch),
    }


def build_snapshot_freshness(
    *,
    snapshot: Dict[str, Any],
    source_freshness: Dict[str, Any],
) -> Dict[str, Any]:
    snapshot_run_count = 0
    if isinstance(snapshot.get("trading_activity_summary"), dict):
        try:
            snapshot_run_count = int(float((snapshot.get("trading_activity_summary") or {}).get("run_total") or 0))
        except Exception:
            snapshot_run_count = 0
    snapshot_latest_ts = str(snapshot.get("latest_run_ts") or "")
    source_latest_ts = str(source_freshness.get("latest_run_ts") or "")
    snapshot_stale = False
    notes: List[str] = []
    if snapshot and snapshot_run_count and int(source_freshness.get("source_run_count") or 0) > snapshot_run_count:
        snapshot_stale = True
        notes.append("operator_summary_run_count_behind_daily_source")
    if snapshot and snapshot_latest_ts and source_latest_ts and to_epoch(source_latest_ts) > to_epoch(snapshot_latest_ts):
        snapshot_stale = True
        notes.append("operator_summary_latest_run_behind_daily_source")
    stale_reason = "aligned_with_source_window"
    if not bool(snapshot.get("available")):
        stale_reason = "snapshot_unavailable"
    elif snapshot_stale:
        stale_reason = "source_window_advanced_since_snapshot_generation"
    meta = {
        "available": bool(snapshot.get("available")),
        "stale": bool(snapshot_stale),
        "notes": notes,
        "snapshot_run_total": int(snapshot_run_count),
        "snapshot_latest_run_id": str(snapshot.get("latest_run_id") or ""),
        "snapshot_latest_run_ts": snapshot_latest_ts,
        "source_run_count": int(source_freshness.get("source_run_count") or 0),
        "source_latest_run_id": str(source_freshness.get("latest_run_id") or ""),
        "source_latest_run_ts": source_latest_ts,
    }
    meta.update(
        build_data_freshness(
            generated_at=str(snapshot.get("generated_at") or source_freshness.get("generated_at") or ""),
            source_run_count=int(source_freshness.get("source_run_count") or 0),
            latest_run_id=str(source_freshness.get("latest_run_id") or ""),
            latest_run_ts=str(source_freshness.get("latest_run_ts") or ""),
            stale=bool(snapshot_stale),
            stale_reason=stale_reason,
        )
    )
    return meta
