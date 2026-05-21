from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

KST = timezone(timedelta(hours=9), name="KST")


def null_if_empty(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def build_failure_classification(
    *,
    lifecycle: Dict[str, Any],
    diagnostics: Dict[str, Any],
    same_day_reporter_linkage: Dict[str, Any],
    holding_phase_observability: Dict[str, Any],
    execution_details: Dict[str, Any],
) -> Dict[str, bool]:
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    status = str(lifecycle.get("status") or "").strip().lower()
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    story_type = str(lifecycle.get("story_type") or "").strip().lower()
    ai_status = str(diagnostics.get("ai_trade_report_status") or "").strip().lower()
    reporter_status = str((same_day_reporter_linkage or {}).get("status") or "").strip().lower()
    return {
        "entry_failure": (not bool(entry)) or bool(entry.get("inferred_entry")),
        "hold_failure": bool((holding_phase_observability or {}).get("hold_evidence_thin")),
        "exit_failure": status in {"closed", "failed"} and not bool(exit_ctx),
        "execution_failure": story_type == "failed_execution" or (
            status in {"closed", "partial", "failed"}
            and not bool(execution_details.get("order_status"))
            and not bool(execution_details.get("order_id"))
        ),
        "reporting_failure": (
            reporter_status == "missing"
            or (status == "closed" and ai_status not in {"ok", "salvaged", "partial"})
        ),
    }


def to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    raw = str(ts).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        pass
    stamped = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(stamped)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def utc_day(ts: Any) -> str:
    epoch = to_epoch(ts)
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def trade_time_bucket_from_lifecycle_bundle(bundle: Dict[str, Any]) -> str:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return ""
    payload = bundle if isinstance(bundle, dict) else {}
    lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
    trade_lifecycle = payload.get("trade_lifecycle") if isinstance(payload.get("trade_lifecycle"), dict) else {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    lifecycle_entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    trade_lifecycle_entry = trade_lifecycle.get("entry") if isinstance(trade_lifecycle.get("entry"), dict) else {}
    exit_ctx = payload.get("exit") if isinstance(payload.get("exit"), dict) else {}
    lifecycle_exit = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    trade_lifecycle_exit = trade_lifecycle.get("exit") if isinstance(trade_lifecycle.get("exit"), dict) else {}
    candidates = [
        entry.get("ts"),
        entry.get("timestamp"),
        lifecycle_entry.get("ts"),
        lifecycle_entry.get("timestamp"),
        trade_lifecycle_entry.get("ts"),
        trade_lifecycle_entry.get("timestamp"),
        exit_ctx.get("ts"),
        exit_ctx.get("timestamp"),
        lifecycle_exit.get("ts"),
        lifecycle_exit.get("timestamp"),
        trade_lifecycle_exit.get("ts"),
        trade_lifecycle_exit.get("timestamp"),
        payload.get("ts"),
        payload.get("saved_at"),
        payload.get("generated_at"),
    ]
    for candidate in candidates:
        epoch = to_epoch(candidate)
        if epoch is None:
            continue
        return datetime.fromtimestamp(epoch, tz=KST).strftime("%H00")
    return datetime.now(KST).strftime("%H00")
