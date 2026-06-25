from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from libs.runtime.kiwoom_market_status import (
    CLOSEOUT_NOTICE_CODES,
    FINAL_REFRESH_CODES,
    REGULAR_CLOSE_CODES,
    SESSION_OPEN_CODES,
    load_market_status,
)

KST = timezone(timedelta(hours=9))


def _event_day_kst(event: Dict[str, Any]) -> str:
    raw = str(event.get("received_at") or "").strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(KST).date().isoformat()
    except Exception:
        return datetime.now(KST).date().isoformat()


def apply_market_status_closeout_events(state: Dict[str, Any]) -> Dict[str, Any]:
    status = load_market_status()
    events = [dict(row) for row in list(status.get("events") or []) if isinstance(row, dict)]
    if not events:
        return state

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    processed = set(str(x) for x in list(persisted.get("processed_market_status_event_ids") or []))
    processed_actions = set(str(x) for x in list(persisted.get("processed_market_status_action_keys") or []))
    current = status.get("current") if isinstance(status.get("current"), dict) else {}
    state["kiwoom_market_status"] = dict(current)
    persisted["kiwoom_market_status"] = dict(current)
    current_code = str(current.get("code") or "")
    current_day = _event_day_kst(current) if current else datetime.now(KST).date().isoformat()

    for event in events:
        event_id = str(event.get("event_id") or "")
        code = str(event.get("code") or "")
        if not event_id or event_id in processed:
            continue
        day = _event_day_kst(event)
        if day != current_day:
            continue
        if code in SESSION_OPEN_CODES:
            state["kiwoom_closeout_notice_active"] = False
            persisted["kiwoom_closeout_notice_active"] = False
        elif code in CLOSEOUT_NOTICE_CODES:
            state["kiwoom_closeout_notice_active"] = True
            persisted["kiwoom_closeout_notice_active"] = True
        elif code in REGULAR_CLOSE_CODES | FINAL_REFRESH_CODES:
            from libs.reporting.closeout_maintenance import (
                run_closeout_maintenance,
                write_closeout_maintenance_report,
            )

            action_name = "regular_close" if code in REGULAR_CLOSE_CODES else "final_refresh"
            action_key = f"{day}:{action_name}"
            if action_key in processed_actions:
                processed.add(event_id)
                continue
            trigger = f"kiwoom_market_status_{code}"
            result = run_closeout_maintenance(day=day, trigger=trigger)
            write_closeout_maintenance_report(result, reports_root=Path("reports"))
            persisted["last_market_status_closeout_result"] = {
                "event_id": event_id,
                "code": code,
                "trigger": trigger,
                "ok": bool(result.get("ok")),
            }
            processed_actions.add(action_key)
        processed.add(event_id)

    # Historical events drive one-time actions, but the latest websocket state
    # is authoritative for the live closeout guard after replay completes.
    if current_code in SESSION_OPEN_CODES:
        state["kiwoom_closeout_notice_active"] = False
        persisted["kiwoom_closeout_notice_active"] = False
    elif current_code in CLOSEOUT_NOTICE_CODES:
        state["kiwoom_closeout_notice_active"] = True
        persisted["kiwoom_closeout_notice_active"] = True

    persisted["processed_market_status_event_ids"] = [
        str(event.get("event_id") or "")
        for event in events
        if str(event.get("event_id") or "") in processed
    ][-100:]
    persisted["processed_market_status_action_keys"] = sorted(processed_actions)[-30:]
    state["persisted_state"] = persisted
    return state


__all__ = ["apply_market_status_closeout_events"]
