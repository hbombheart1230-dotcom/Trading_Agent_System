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
from libs.core.path_isolation import isolate_canonical_path_for_pytest

KST = timezone(timedelta(hours=9))


def _event_day_kst(event: Dict[str, Any]) -> str:
    raw = str(event.get("received_at") or "").strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(KST).date().isoformat()
    except Exception:
        return datetime.now(KST).date().isoformat()


def _log_market_status_closeout_exception(
    exc: BaseException, *, day: str, event_id: str, code: str, action_key: str, trigger: str
) -> None:
    """Durable diagnostic record for an exception raised while dispatching a
    market-status closeout action (2026-09-30 closeout diagnostic
    hardening). Writes via the existing EventLogger (data/logs/events.jsonl,
    fsync'd on every write) -- additive only, never replaces the caller's
    own containment/re-raise. Never itself raises: a diagnostic-logging
    failure must never mask or replace the real exception being reported.
    """
    try:
        import traceback

        from libs.core.event_logger import EventLogger, new_run_id, resolve_event_log_path

        EventLogger(resolve_event_log_path()).log(
            run_id=new_run_id(),
            stage="market_status_closeout",
            event="exception",
            level="error",
            payload={
                "function": "apply_market_status_closeout_events",
                "target_day": day,
                "event_id": event_id,
                "code": code,
                "action_key": action_key,
                "trigger": trigger,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:2000],
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:8000],
            },
        )
    except Exception:  # noqa: BLE001 - diagnostics must never mask the real exception
        pass


def apply_market_status_closeout_events(state: Dict[str, Any]) -> Dict[str, Any]:
    status = load_market_status()
    events = [dict(row) for row in list(status.get("events") or []) if isinstance(row, dict)]
    if not events:
        return state

    today = datetime.now(KST).date().isoformat()
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    processed = set(str(x) for x in list(persisted.get("processed_market_status_event_ids") or []))
    processed_actions = set(str(x) for x in list(persisted.get("processed_market_status_action_keys") or []))
    current = status.get("current") if isinstance(status.get("current"), dict) else {}
    state["kiwoom_market_status"] = dict(current)
    persisted["kiwoom_market_status"] = dict(current)
    current_code = str(current.get("code") or "")
    current_day = _event_day_kst(current) if current else today
    current_is_today = bool(current) and current_day == today
    if current and not current_is_today:
        state["kiwoom_market_status_stale"] = True
        persisted["kiwoom_market_status_stale"] = True
        persisted["kiwoom_closeout_notice_active"] = False
        state["kiwoom_closeout_notice_active"] = False

    for event in events:
        event_id = str(event.get("event_id") or "")
        code = str(event.get("code") or "")
        if not event_id or event_id in processed:
            continue
        day = _event_day_kst(event)
        if day != today:
            continue
        if code in SESSION_OPEN_CODES:
            state["kiwoom_closeout_notice_active"] = False
            persisted["kiwoom_closeout_notice_active"] = False
        elif code in CLOSEOUT_NOTICE_CODES:
            state["kiwoom_closeout_notice_active"] = True
            persisted["kiwoom_closeout_notice_active"] = True
        elif code in REGULAR_CLOSE_CODES | FINAL_REFRESH_CODES:
            action_name = "regular_close" if code in REGULAR_CLOSE_CODES else "final_refresh"
            action_key = f"{day}:{action_name}"
            if action_key in processed_actions:
                processed.add(event_id)
                continue
            trigger = f"kiwoom_market_status_{code}"
            try:
                from libs.reporting.closeout_maintenance import (
                    run_closeout_maintenance_with_lock,
                    write_closeout_maintenance_report,
                )

                # 2026-09-30 closeout single-owner safety fix: this trigger and
                # the scheduled fallback (scripts/run_closeout_maintenance.py)
                # both used to call run_closeout_maintenance() directly, with
                # no coordination -- nothing prevented both from executing
                # concurrently. run_closeout_maintenance_with_lock() wraps the
                # exact same call with a PID-based single-owner lock (reusing
                # libs/runtime/live_loop_lock.py, already proven for the m13
                # live loop's own single-instance guard); see its own
                # docstring for the full design.
                result = run_closeout_maintenance_with_lock(
                    day=day, trigger=trigger, run_id=f"tick-{day}-{action_key}"
                )
                if result.get("skipped"):
                    # Another owner (the scheduled fallback, or a still-active
                    # prior tick) is genuinely running this same closeout right
                    # now -- do not write a report at all here, to avoid a
                    # race against whatever the real owner is about to write.
                    processed.add(event_id)
                    continue
                reports_root = isolate_canonical_path_for_pytest(
                    "reports", canonical_path="reports", isolated_name="reports"
                )
                write_closeout_maintenance_report(result, reports_root=reports_root)
            except Exception as exc:
                # 2026-09-30 closeout diagnostic hardening: this exception still
                # propagates unchanged (control flow preserved exactly -- the
                # caller, graphs/pipelines/m13_live_loop.py::run_m13_once, keeps
                # its own outer except Exception as its final backstop). What
                # changes is durability: without this, the exception's only
                # trace was state["market_status_closeout_error"], a field
                # save_state() never persists (it only writes
                # state["persisted_state"]) -- confirmed directly as the reason
                # processed_market_status_action_keys in data/state.json shows
                # no recorded action for this path since 2026-09-23 despite
                # valid close/final-refresh events continuing to arrive: any
                # exception here was structurally invisible after the tick
                # ended. Logging the specific day/event/action before
                # re-raising gives the next occurrence a durable trace this one
                # never had.
                _log_market_status_closeout_exception(
                    exc, day=day, event_id=event_id, code=code, action_key=action_key, trigger=trigger,
                )
                raise
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
    if current_is_today and current_code in SESSION_OPEN_CODES:
        state["kiwoom_closeout_notice_active"] = False
        persisted["kiwoom_closeout_notice_active"] = False
        state["kiwoom_market_status_stale"] = False
        persisted["kiwoom_market_status_stale"] = False
    elif current_is_today and current_code in CLOSEOUT_NOTICE_CODES:
        state["kiwoom_closeout_notice_active"] = True
        persisted["kiwoom_closeout_notice_active"] = True
        state["kiwoom_market_status_stale"] = False
        persisted["kiwoom_market_status_stale"] = False

    persisted["processed_market_status_event_ids"] = [
        str(event.get("event_id") or "")
        for event in events
        if str(event.get("event_id") or "") in processed
    ][-100:]
    persisted["processed_market_status_action_keys"] = sorted(processed_actions)[-30:]
    state["persisted_state"] = persisted
    return state


__all__ = ["apply_market_status_closeout_events"]
