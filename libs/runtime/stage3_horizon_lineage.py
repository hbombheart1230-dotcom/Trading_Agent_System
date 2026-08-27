from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping

from libs.core.symbols import normalize_symbol


SCHEMA_VERSION = "stage3_horizon_lineage.v1"


def _non_fatal_observation(function: Callable[..., str]) -> Callable[..., str]:
    @wraps(function)
    def wrapped(state: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        try:
            return function(state, *args, **kwargs)
        except Exception as exc:
            state["stage3_horizon_lineage_write_error"] = f"{type(exc).__name__}:{exc}"
            return ""

    return wrapped


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _epoch(state: Mapping[str, Any]) -> int:
    for key in ("now_epoch", "tick_epoch", "ts_epoch"):
        try:
            value = int(float(state.get(key) or 0))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _iso_timestamp(state: Mapping[str, Any]) -> str:
    value = _epoch(state)
    if value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _day(state: Mapping[str, Any]) -> str:
    for key in ("day", "started_at", "ts", "now_iso", "tick_ts"):
        text = str(state.get(key) or "").strip()
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
    value = _epoch(state)
    if value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _artifact_path(state: Mapping[str, Any]) -> Path | None:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return None
    reports_root = Path(str(state.get("reports_root") or "reports").strip() or "reports")
    return reports_root / "canonical" / _day(state) / run_id / "stage3_horizon_lineage.json"


def _lineage(state: dict[str, Any]) -> dict[str, Any]:
    current = _dict(state.get("stage3_horizon_lineage"))
    if not current:
        current = {
            "schema_version": SCHEMA_VERSION,
            "behavior_effect": "observability_only",
            "run_id": str(state.get("run_id") or ""),
            "day": _day(state),
            "records": [],
        }
    current["schema_version"] = SCHEMA_VERSION
    current["behavior_effect"] = "observability_only"
    current["run_id"] = str(state.get("run_id") or current.get("run_id") or "")
    current["day"] = str(current.get("day") or _day(state))
    current["records"] = [dict(row) for row in list(current.get("records") or []) if isinstance(row, Mapping)]
    state["stage3_horizon_lineage"] = current
    return current


def _record(lineage: dict[str, Any], symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    records = list(lineage.get("records") or [])
    for row in records:
        if normalize_symbol(row.get("symbol")) == normalized:
            return row
    row = {"symbol": normalized, "consistency_issues": []}
    records.append(row)
    lineage["records"] = records
    return row


def _refresh_consistency(row: dict[str, Any]) -> None:
    issues: list[str] = []
    invocation = _dict(row.get("invocation"))
    application = _dict(row.get("commander_application"))
    response = _dict(row.get("response"))
    monitor = _dict(row.get("monitor_consumption"))
    symbol = normalize_symbol(row.get("symbol"))
    target = normalize_symbol(invocation.get("target_symbol"))
    applied_symbol = normalize_symbol(application.get("symbol"))
    consumed_symbol = normalize_symbol(monitor.get("symbol"))
    if invocation.get("requested") and not target:
        issues.append("missing_invocation_target")
    if target and symbol and target != symbol:
        issues.append("invocation_target_mismatch")
    if applied_symbol and symbol and applied_symbol != symbol:
        issues.append("application_target_mismatch")
    if consumed_symbol and symbol and consumed_symbol != symbol:
        issues.append("monitor_target_mismatch")
    if response.get("present") and not application.get("evaluated"):
        issues.append("response_not_evaluated_by_commander")
    decision = str(response.get("hold_review_decision") or "").strip().lower()
    action = str(response.get("horizon_action") or "").strip().lower()
    if decision == "exit_now" or action == "request_exit":
        if not application.get("exit_request_forwarded"):
            issues.append("exit_advisory_not_forwarded")
    if application.get("horizon_changed") and not monitor.get("consumed"):
        issues.append("changed_horizon_not_yet_observed_by_monitor")
    row["consistency_issues"] = issues


def _write(state: dict[str, Any]) -> str:
    lineage = _lineage(state)
    for row in lineage["records"]:
        _refresh_consistency(row)
    lineage["updated_at"] = _iso_timestamp(state)
    path = _artifact_path(state)
    if path is None:
        return ""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    artifacts = _dict(state.get("canonical_artifacts"))
    artifacts["stage3_horizon_lineage"] = str(path)
    state["canonical_artifacts"] = artifacts
    return str(path)


@_non_fatal_observation
def record_stage3_assessment(state: dict[str, Any], assessment: Mapping[str, Any] | None) -> str:
    data = _dict(assessment)
    positions = [dict(row) for row in list(data.get("positions") or []) if isinstance(row, Mapping)]
    relevant = bool(
        data.get("position_refresh_due")
        or data.get("override_suppressed")
        or any(bool(row.get("horizon_review_due")) or int(row.get("hold_repeat_count") or 0) >= 3 for row in positions)
    )
    if not relevant:
        return ""
    target = normalize_symbol(
        data.get("refresh_cooldown_symbol")
        or _dict(data.get("strategist_refresh_context")).get("selected_symbol")
    )
    focus = next((row for row in positions if normalize_symbol(row.get("symbol")) == target), {})
    lineage = _lineage(state)
    row = _record(lineage, target or focus.get("symbol"))
    horizon_state = _dict(focus.get("position_horizon_state"))
    row["scheduling"] = {
        "evaluated": True,
        "review_due": bool(focus.get("horizon_review_due")),
        "position_refresh_due": bool(data.get("position_refresh_due")),
        "trigger": str(data.get("position_refresh_trigger") or data.get("override_reason") or ""),
        "override_action": str(data.get("override_action") or ""),
        "suppressed": bool(data.get("override_suppressed")),
        "suppressed_reason": str(data.get("override_suppressed_reason") or ""),
        "position_age_seconds": focus.get("position_age_seconds"),
        "hold_repeat_count": int(focus.get("hold_repeat_count") or 0),
        "active_horizon": str(horizon_state.get("active_horizon") or ""),
        "next_review_epoch": horizon_state.get("next_review_epoch"),
        "observed_at": _iso_timestamp(state),
    }
    if not data.get("position_refresh_due"):
        row["invocation"] = {
            "requested": False,
            "status": "skipped",
            "target_symbol": target,
            "reason": str(
                data.get("override_suppressed_reason")
                or ("review_not_due" if not focus.get("horizon_review_due") else "refresh_not_requested")
            ),
            "observed_at": _iso_timestamp(state),
        }
    return _write(state)


def _stage3_context(state: Mapping[str, Any]) -> dict[str, Any]:
    commander = _dict(state.get("commander_decision"))
    context = _dict(commander.get("strategist_refresh_context"))
    if str(context.get("refresh_scope") or "").strip().lower() != "open_position_monitor_refresh":
        return {}
    return context


@_non_fatal_observation
def record_stage3_invocation(state: dict[str, Any]) -> str:
    context = _stage3_context(state)
    if not context:
        return ""
    target = normalize_symbol(context.get("selected_symbol"))
    lineage = _lineage(state)
    row = _record(lineage, target)
    row["invocation"] = {
        "requested": True,
        "status": "requested",
        "call_kind": "stale_intraday_hold_review",
        "target_symbol": target,
        "refresh_trigger": str(context.get("refresh_trigger") or ""),
        "requested_at": _iso_timestamp(state),
    }
    return _write(state)


@_non_fatal_observation
def record_stage3_response(state: dict[str, Any]) -> str:
    context = _stage3_context(state)
    output = _dict(state.get("strategist_output"))
    review = _dict(output.get("stale_intraday_hold_review"))
    if not context and not review:
        return ""
    target = normalize_symbol(context.get("selected_symbol"))
    lineage = _lineage(state)
    row = _record(lineage, target)
    llm = _dict(state.get("strategist_llm"))
    row["response"] = {
        "present": bool(review),
        "status": str(llm.get("status") or ("ok" if review else "missing")),
        "hold_review_decision": str(review.get("hold_review_decision") or ""),
        "horizon_action": str(review.get("horizon_action") or ""),
        "current_horizon": str(review.get("current_horizon") or ""),
        "proposed_horizon": str(review.get("proposed_horizon") or ""),
        "evidence_confidence": str(review.get("evidence_confidence") or ""),
        "data_quality": str(review.get("data_quality") or ""),
        "next_check_minutes": review.get("next_check_minutes"),
        "received_at": _iso_timestamp(state),
        "response_ref": str(llm.get("stage_response_ref") or llm.get("response_ref") or ""),
    }
    return _write(state)


@_non_fatal_observation
def record_stage3_application(
    state: dict[str, Any],
    *,
    symbol: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    review: Mapping[str, Any],
) -> str:
    normalized = normalize_symbol(symbol)
    prior = _dict(before)
    current = _dict(after)
    decision = _dict(review)
    lineage = _lineage(state)
    row = _record(lineage, normalized)
    last = _dict(current.get("last_stage3_decision"))
    before_window = _dict(prior.get("active_expected_hold_window"))
    after_window = _dict(current.get("active_expected_hold_window"))
    horizon_changed = (
        str(prior.get("active_horizon") or "") != str(current.get("active_horizon") or "")
        or before_window != after_window
    )
    row["commander_application"] = {
        "evaluated": True,
        "symbol": normalized,
        "hold_review_decision": str(decision.get("hold_review_decision") or ""),
        "horizon_action": str(decision.get("horizon_action") or ""),
        "approved": bool(last.get("commander_revision_approved")),
        "active_horizon_before": str(prior.get("active_horizon") or ""),
        "active_horizon_after": str(current.get("active_horizon") or ""),
        "active_window_before": before_window,
        "active_window_after": after_window,
        "horizon_changed": bool(horizon_changed),
        "exit_request_forwarded": False,
        "evaluated_at": _iso_timestamp(state),
    }
    return _write(state)


@_non_fatal_observation
def record_stage3_monitor_consumption(
    state: dict[str, Any],
    *,
    symbol: str,
    strategy_frame: Mapping[str, Any],
) -> str:
    normalized = normalize_symbol(symbol)
    lineage = _dict(state.get("stage3_horizon_lineage"))
    if not lineage:
        return ""
    records = [dict(row) for row in list(lineage.get("records") or []) if isinstance(row, Mapping)]
    if not any(normalize_symbol(row.get("symbol")) == normalized for row in records):
        return ""
    state["stage3_horizon_lineage"] = {**lineage, "records": records}
    row = _record(state["stage3_horizon_lineage"], normalized)
    frame = _dict(strategy_frame)
    policy = _dict(frame.get("commander_horizon_policy"))
    row["monitor_consumption"] = {
        "consumed": True,
        "symbol": normalized,
        "position_strategy_context_applied": bool(frame.get("position_strategy_context_applied")),
        "active_horizon": str(frame.get("active_horizon") or policy.get("strategy_horizon") or ""),
        "entry_horizon": str(frame.get("entry_horizon") or policy.get("entry_horizon") or ""),
        "expected_hold_window": _dict(policy.get("expected_hold_window")),
        "consumed_at": _iso_timestamp(state),
    }
    return _write(state)
