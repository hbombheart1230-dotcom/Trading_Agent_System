from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.core.symbols import normalize_symbol
from libs.runtime.same_symbol_loss_reentry import evaluate_same_symbol_loss_reentry

from .artifacts import q10_artifact_paths, q12_hypothesis_path, read_json
from .contracts import (
    DEFAULT_ORDER_QTY,
    INDEPENDENT_LANES,
    LANE_WINDOWS_KST,
    SCHEMA_VERSION,
)
from .ledger import (
    lane_already_submitted,
    record_accepted_submission,
    record_attempt,
    record_evaluations,
    reconcile_submissions_with_broker_orders,
    signal_already_attempted,
)
from .signals import (
    build_q10_index_candidate,
    build_q10_semiconductor_candidate,
    build_q12_candidate,
)


KST = timezone(timedelta(hours=9))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _enabled() -> bool:
    return _text(os.getenv("CONTROLLED_MOCK_LANES_ENABLED", "true")).lower() not in {
        "0", "false", "no", "off", "disabled"
    }


def _now_epoch(state: Mapping[str, Any]) -> int:
    for key in ("now_epoch", "ts_epoch", "current_epoch"):
        value = _int(state.get(key))
        if value > 0:
            return value
    raw = state.get("ts")
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    return int(time.time())


def _inside_lane_window(lane_id: str, now: datetime) -> bool:
    start, end = LANE_WINDOWS_KST[lane_id]
    minute = now.hour * 60 + now.minute
    return start[0] * 60 + start[1] <= minute <= end[0] * 60 + end[1]


def _positions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    snapshot = _mapping(state.get("portfolio_snapshot"))
    rows = snapshot.get("positions")
    if not isinstance(rows, list):
        rows = _mapping(state.get("persisted_state")).get("mock_positions")
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def _held_symbols(state: Mapping[str, Any]) -> set[str]:
    return {
        normalize_symbol(row.get("symbol") or row.get("stk_cd") or row.get("code"))
        for row in _positions(state)
        if _int(row.get("qty") or row.get("quantity") or row.get("hold_qty")) > 0
    } - {""}


def _pending_buy_symbols(state: Mapping[str, Any]) -> set[str]:
    output: set[str] = set()
    containers = (
        state.get("account_orders"),
        _mapping(state.get("portfolio_snapshot")).get("orders"),
        _mapping(state.get("persisted_state")).get("pending_unfilled_orders"),
    )
    for container in containers:
        rows = container.values() if isinstance(container, Mapping) else container or []
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            side = _text(raw.get("side") or raw.get("action") or raw.get("ord_dvsn_name")).upper()
            remaining = _int(
                raw.get("remaining_qty")
                or raw.get("unfilled_qty")
                or raw.get("rmn_qty")
                or raw.get("qty")
            )
            if "BUY" not in side and "매수" not in side:
                continue
            if remaining <= 0:
                continue
            symbol = normalize_symbol(raw.get("symbol") or raw.get("stk_cd") or raw.get("code"))
            if symbol:
                output.add(symbol)
    return output


def _max_positions(state: Mapping[str, Any]) -> int:
    risk_context = _mapping(state.get("risk_context"))
    policy = _mapping(state.get("policy"))
    for value in (
        risk_context.get("max_positions"),
        _mapping(state.get("risk")).get("max_positions"),
        policy.get("max_positions"),
        os.getenv("RISK_MAX_POSITIONS"),
    ):
        number = _int(value)
        if number > 0:
            return number
    return 3


def _restricted_symbols(state: Mapping[str, Any]) -> set[str]:
    raw = _mapping(_mapping(state.get("persisted_state")).get("mock_broker_restricted_symbols"))
    return {normalize_symbol(key) for key in raw if normalize_symbol(key)}


def _load_candidates(
    *, reports_root: Path, day: str, now_epoch: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output = []
    diagnostics: list[dict[str, Any]] = []
    q12_payload = read_json(q12_hypothesis_path(reports_root, day))
    q12 = build_q12_candidate(q12_payload, now_epoch=now_epoch)
    if q12:
        output.append(q12)
        diagnostics.append({"lane_id": "BTC_WOORI", "status": "CANDIDATE_READY", "reason": "", "signal_id": q12.get("signal_id")})
    else:
        q12_features = _mapping(q12_payload.get("features"))
        q12_btc = _mapping(q12_features.get("btc_0855"))
        input_missing = not q12_payload or q12_btc.get("status") != "OBSERVED"
        if not q12_payload:
            reason = "q12_hypothesis_artifact_missing"
        elif input_missing:
            reason = _text(q12_btc.get("reason")) or "btc_0855_not_observed"
        else:
            reason = "q12_fixed_conditions_not_met"
        diagnostics.append({
            "lane_id": "BTC_WOORI",
            "status": "INPUT_MISSING" if input_missing else "NO_CANDIDATE",
            "reason": reason,
            "signal_id": "",
        })
    q10_paths = q10_artifact_paths(reports_root, day)
    preopen = read_json(q10_paths["preopen"])
    reactions = read_json(q10_paths["reactions"])
    expected = read_json(q10_paths["expected_actual"])
    semiconductor = build_q10_semiconductor_candidate(
        preopen=preopen,
        reactions=reactions,
        expected_actual=expected,
        now_epoch=now_epoch,
    )
    if semiconductor:
        output.append(semiconductor)
        diagnostics.append({"lane_id": "Q10_SEMICONDUCTOR", "status": "CANDIDATE_READY", "reason": "", "signal_id": semiconductor.get("signal_id")})
    else:
        preopen_status = _text(preopen.get("capture_status"))
        input_missing = preopen_status != "CAPTURED" or not reactions or not expected
        if preopen_status != "CAPTURED":
            reason = _text(preopen.get("reason")) or "q10_preopen_capture_missing"
        elif input_missing:
            reason = "q10_reaction_or_expected_artifact_missing"
        else:
            reason = "q10_semiconductor_signal_not_confirmed"
        diagnostics.append({
            "lane_id": "Q10_SEMICONDUCTOR",
            "status": "INPUT_MISSING" if input_missing else "NO_CANDIDATE",
            "reason": reason,
            "signal_id": "",
        })
    index = build_q10_index_candidate(
        preopen=preopen,
        reactions=reactions,
        expected_actual=expected,
        now_epoch=now_epoch,
    )
    if index:
        output.append(index)
        diagnostics.append({"lane_id": "Q10_INDEX", "status": "CANDIDATE_READY", "reason": "", "signal_id": index.get("signal_id")})
    else:
        preopen_status = _text(preopen.get("capture_status"))
        input_missing = preopen_status != "CAPTURED" or not reactions or not expected
        if preopen_status != "CAPTURED":
            reason = _text(preopen.get("reason")) or "q10_preopen_capture_missing"
        elif input_missing:
            reason = "q10_reaction_or_expected_artifact_missing"
        else:
            reason = "q10_index_signal_not_confirmed"
        diagnostics.append({
            "lane_id": "Q10_INDEX",
            "status": "INPUT_MISSING" if input_missing else "NO_CANDIDATE",
            "reason": reason,
            "signal_id": "",
        })
    return output, diagnostics


def _strategy_snapshot(candidate: Mapping[str, Any]) -> dict[str, Any]:
    horizon = _text(candidate.get("horizon")) or "intraday"
    return {
        "strategy_horizon": horizon,
        "expected_hold_window": {
            "min_sec": 300,
            "target_sec": 1800,
            "max_sec": 14400,
        },
        "playbook": "controlled_signal_validation",
        "tactical_subtype": _text(candidate.get("lane_id")).lower(),
        "llm_used": False,
        "controlled_mock_lane": True,
        "horizon_revision_allowed": False,
    }


def _intent(candidate: Mapping[str, Any]) -> dict[str, Any]:
    lane_id = _text(candidate.get("lane_id"))
    return {
        "symbol": normalize_symbol(candidate.get("symbol")),
        "side": "BUY",
        "qty": DEFAULT_ORDER_QTY,
        "price": candidate.get("price"),
        "risk_score": 0.0,
        "confidence": 1.0,
        "thesis": f"controlled mock validation lane: {lane_id}",
        "meta": {
            "entry_signal_source": "monitor_intraday_entry",
            "entry_lane": f"controlled_mock:{lane_id}",
            "entry_reason": "controlled_mock_lane_signal_confirmed",
            "controlled_mock_lane": {
                "schema_version": SCHEMA_VERSION,
                **dict(candidate),
                "daily_limit": 1,
                "submission_state": "PENDING_BROKER_RESULT",
            },
            "position_strategy_snapshot": _strategy_snapshot(candidate),
            "price": candidate.get("price"),
            "current_price": candidate.get("price"),
            "order_price_source": "controlled_mock_lane_artifact",
        },
    }


def inject_controlled_mock_lane_intent(
    state: dict[str, Any],
    *,
    reports_root: Path | str = Path("reports"),
    ledger_root: Path | str | None = None,
) -> dict[str, Any]:
    now_epoch = _now_epoch(state)
    now = datetime.fromtimestamp(now_epoch, tz=KST)
    day = now.date().isoformat()
    surface: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "enabled": _enabled(),
        "evaluated": False,
        "injected": False,
        "day": day,
        "now_epoch": now_epoch,
        "reason": "",
        "candidates": [],
    }

    def finish(reason: str) -> dict[str, Any]:
        surface["reason"] = reason
        state["controlled_mock_lanes"] = surface
        return state

    if not surface["enabled"]:
        return finish("disabled")
    if _text(os.getenv("KIWOOM_MODE")).lower() != "mock":
        return finish("kiwoom_mock_required")
    if _text(os.getenv("EXECUTION_MODE")).lower() != "real":
        return finish("mock_broker_http_execution_required")
    if _text(state.get("runtime_phase") or "session").lower() != "session":
        return finish("session_phase_required")
    try:
        from graphs.nodes.skill_contracts import extract_account_orders_rows

        broker_orders, _broker_order_meta = extract_account_orders_rows(state)
    except Exception:
        broker_orders = []
    surface["broker_truth_reconciliation"] = reconcile_submissions_with_broker_orders(
        day=day,
        broker_orders=broker_orders,
        recorded_at=datetime.fromtimestamp(now_epoch, tz=KST).isoformat(),
        root=ledger_root,
    )
    prior_surface = _mapping(state.get("controlled_mock_lanes"))
    if (
        prior_surface.get("injected")
        and _text(prior_surface.get("submission_state")) == "PENDING_BROKER_RESULT"
    ):
        return finish("submission_pending_broker_result")
    intents = state.get("intents")
    if isinstance(intents, list) and intents:
        return finish("existing_monitor_intent_has_priority")
    held = _held_symbols(state)
    if len(held) >= _max_positions(state):
        return finish("max_positions_reached")

    candidates, diagnostics = _load_candidates(
        reports_root=Path(reports_root), day=day, now_epoch=now_epoch
    )
    recorded_at = datetime.fromtimestamp(now_epoch, tz=KST).isoformat()
    surface["evaluation_ledger"] = record_evaluations(
        day=day,
        rows=diagnostics,
        recorded_at=recorded_at,
        root=ledger_root,
    )
    surface["diagnostics"] = diagnostics
    surface["evaluated"] = True
    surface["candidates"] = [dict(row) for row in candidates]
    pending = _pending_buy_symbols(state)
    restricted = _restricted_symbols(state)
    eligible = []
    blocked = []
    for candidate in candidates:
        lane_id = _text(candidate.get("lane_id"))
        symbol = normalize_symbol(candidate.get("symbol"))
        reason = ""
        if lane_id not in INDEPENDENT_LANES:
            reason = "unknown_lane"
        elif not _inside_lane_window(lane_id, now):
            reason = "outside_lane_window"
        elif lane_already_submitted(day, lane_id, root=ledger_root):
            reason = "daily_lane_limit_reached"
        elif signal_already_attempted(day, _text(candidate.get("signal_id")), root=ledger_root):
            reason = "signal_already_attempted"
        elif symbol in held:
            reason = "symbol_already_held"
        elif symbol in pending:
            reason = "symbol_pending_buy"
        elif symbol in restricted:
            reason = "mock_broker_restricted_symbol"
        else:
            reentry = evaluate_same_symbol_loss_reentry(
                state, symbol=symbol, now_epoch=now_epoch
            )
            if reentry.get("blocked"):
                reason = "same_symbol_loss_reentry_blocked"
        if reason:
            blocked.append({"lane_id": lane_id, "symbol": symbol, "reason": reason})
        else:
            eligible.append(candidate)
    surface["blocked"] = blocked
    if blocked:
        record_evaluations(
            day=day,
            rows=[
                {
                    "lane_id": row.get("lane_id"),
                    "status": "CANDIDATE_BLOCKED",
                    "reason": row.get("reason"),
                    "signal_id": next(
                        (_text(candidate.get("signal_id")) for candidate in candidates if _text(candidate.get("lane_id")) == _text(row.get("lane_id"))),
                        "",
                    ),
                }
                for row in blocked
            ],
            recorded_at=recorded_at,
            root=ledger_root,
        )
    if not eligible:
        return finish("no_eligible_independent_lane")

    candidate = max(eligible, key=lambda row: float(row.get("score") or 0.0))
    intent = _intent(candidate)
    state["intents"] = [intent]
    surface["injected"] = True
    surface["selected_lane"] = _text(candidate.get("lane_id"))
    surface["selected_symbol"] = normalize_symbol(candidate.get("symbol"))
    surface["selected_candidate"] = dict(candidate)
    surface["submission_state"] = "PENDING_BROKER_RESULT"
    surface["reason"] = "controlled_mock_lane_intent_injected"
    state["controlled_mock_lanes"] = surface
    return state


# 2026-09-05 Codex audit: `execution` (state["execution"]) not accepted does
# NOT mean the broker rejected it -- most non-accept outcomes here are guards
# (order_notional_price_missing, executable_quote_missing, price drift block,
# etc.) that block BEFORE any broker API call, i.e. Step5B BrokerOutcome
# NOT_SENT, not REJECTED. `_normalize_execution()` in execute_from_packet.py
# already computes the correct Step5B classification into
# `execution["broker_outcome"]` -- this reads that value instead of
# re-deriving a collapsed accepted/not-accepted boolean. Falls back to a
# minimal allowed/ok-based heuristic only for execution dicts that never went
# through `_normalize_execution` (e.g. hand-built test doubles), and never
# guesses REJECTED without an explicit broker-side signal.
_VALID_BROKER_OUTCOMES = frozenset({"NOT_SENT", "ACCEPTED", "REJECTED", "UNKNOWN"})


# 2026-09-05 PRE-STEP5C CLEANUP FIX 2 (item 4, Codex independent re-audit):
# the original fallback guessed REJECTED from any truthy broker_code/
# broker_message, and NOT_SENT from allowed=False alone -- both wrong.
# broker_code=="0" is Kiwoom's own no-business-error convention (see
# KiwoomMarketIndexReader._request: `if not code or code == "0": return`),
# so treating it as a rejection signal was a straight misclassification. A
# timeout/ambiguous broker_message was also being read as a confident
# rejection when it actually means we do not know what happened. And
# allowed=False does not by itself PROVE the broker was never contacted --
# it is only proof when there is no positive dispatch evidence either.
# Rewritten around real dispatch evidence (Step5B fields written by
# execute_from_packet.py::_normalize_execution: submission_attempts,
# submission_phase) plus response evidence (broker_code/broker_message/
# order_id, which can only exist if a response was actually received):
#   explicit execution["broker_outcome"] -> authoritative (unchanged)
#   proven never dispatched                -> NOT_SENT
#   dispatched + explicit success          -> ACCEPTED
#   dispatched + explicit broker rejection -> REJECTED
#   dispatched + timeout/ambiguous/no clear signal -> UNKNOWN
#   evidence insufficient either way       -> UNKNOWN (fail-honest default)
# 2026-09-05 PRE-STEP5C CLEANUP FIX 3 (item 7, second independent Codex
# re-audit -- rejected FIX 2's version of this fallback too): still too
# willing to infer. Concretely wrong before this pass:
#   - `{}` (no fields at all) resolved to NOT_SENT, because
#     `bool(execution.get("allowed"))` treats an ABSENT "allowed" key the
#     same as an explicit `allowed=False`. An empty dict proves nothing --
#     it must resolve to UNKNOWN, not NOT_SENT.
#   - a bare `broker_message` (e.g. descriptive text mentioning
#     "pre_submit"/"rejected" that is NOT a genuine broker business-code
#     response) could trigger REJECTED on its own. Message TEXT is never
#     sufficient evidence of an explicit broker rejection response by
#     itself now -- only a real, non-"0" `broker_code` counts.
# Rewritten around EXPLICIT, PROVEN facts only:
#   explicit execution["broker_outcome"]        -> authoritative (unchanged)
#   proven no physical dispatch (an EXPLICIT
#     allowed=False / guard_blocked phase, with
#     no dispatch evidence otherwise)            -> NOT_SENT
#   dispatched + explicit success                -> ACCEPTED
#   dispatched + explicit broker_code reject
#     (non-"0", not an ambiguous/timeout signal) -> REJECTED
#   everything else (insufficient evidence,
#     timeout/ambiguous, message-text-only)      -> UNKNOWN
_AMBIGUOUS_OUTCOME_MARKERS = ("timeout", "ambiguous", "parse")


def _resolve_broker_outcome(execution: Mapping[str, Any]) -> str:
    declared = str(execution.get("broker_outcome") or "").strip().upper()
    if declared in _VALID_BROKER_OUTCOMES:
        return declared

    has_allowed_key = "allowed" in execution
    allowed_value = bool(execution.get("allowed")) if has_allowed_key else None

    submission_attempts = 0
    try:
        submission_attempts = int(execution.get("submission_attempts") or 0)
    except (TypeError, ValueError):
        submission_attempts = 0
    submission_phase = str(execution.get("submission_phase") or "").strip().lower()
    broker_code = str(execution.get("broker_code") or "").strip()
    broker_message = str(execution.get("broker_message") or "").strip()
    order_id = str(execution.get("order_id") or execution.get("ord_no") or "").strip()

    explicitly_not_dispatched = submission_phase in {"guard_blocked", "not_dispatched"}
    # Message text alone is deliberately NOT dispatch evidence -- only a
    # genuine broker-side identifier (code/order id) or an explicit
    # Step5B phase/attempt count counts.
    dispatched_evidence = bool(
        submission_attempts > 0
        or submission_phase in {"completed", "mutation_http_call", "dispatched"}
        or broker_code
        or order_id
    )

    proven_not_dispatched = explicitly_not_dispatched and not dispatched_evidence
    if explicitly_not_dispatched and (execution.get('ok') is True or execution.get('execution_ok') is True):
        return 'UNKNOWN'
    if proven_not_dispatched:
        return "NOT_SENT"
    if not dispatched_evidence:
        # Insufficient evidence either way -- an empty dict proves
        # nothing, never guessed as NOT_SENT.
        return "UNKNOWN"

    if explicitly_not_dispatched:
        return 'UNKNOWN'

    reason = str(execution.get("reason") or "").strip().lower()
    combined_text = f"{reason} {broker_message}".lower()
    if any(marker in combined_text for marker in _AMBIGUOUS_OUTCOME_MARKERS):
        return "UNKNOWN"
    if broker_code.isdigit() and int(broker_code) != 0:
        if execution.get('ok') is True or execution.get('execution_ok') is True:
            return 'UNKNOWN'
        return "REJECTED"
    if order_id and (broker_code == '0' or execution.get('ok') is True or execution.get('execution_ok') is True):
        return 'ACCEPTED'
    # A bare broker_message with no genuine broker_code is never, by
    # itself, proof of an explicit broker rejection response.
    return "UNKNOWN"


_SUBMISSION_STATE_BY_BROKER_OUTCOME = {
    "NOT_SENT": "PRE_SUBMISSION_BLOCKED",
    "REJECTED": "BROKER_REJECTED",
    "UNKNOWN": "BROKER_OUTCOME_UNKNOWN",
}
_ATTEMPT_STATUS_BY_BROKER_OUTCOME = {
    "NOT_SENT": "PRE_SUBMISSION_BLOCKED",
    "REJECTED": "BROKER_REJECTED",
    "UNKNOWN": "BROKER_OUTCOME_UNKNOWN",
}


def finalize_controlled_mock_lane_submission(
    state: dict[str, Any], *, ledger_root: Path | str | None = None
) -> dict[str, Any]:
    surface = _mapping(state.get("controlled_mock_lanes"))
    candidate = _mapping(surface.get("selected_candidate"))
    if not surface.get("injected") or not candidate:
        return state
    execution = _mapping(state.get("execution"))
    if not execution:
        decision = _text(state.get("decision")).lower()
        if decision and decision != "approve":
            surface["submission_state"] = "APPROVAL_REJECTED"
            surface["evaluation_ledger"] = record_evaluations(
                day=_text(surface.get("day")),
                rows=[{
                    "lane_id": candidate.get("lane_id"),
                    "status": "APPROVAL_REJECTED",
                    "reason": _text(state.get("decision_reason")) or decision,
                    "signal_id": candidate.get("signal_id"),
                }],
                recorded_at=datetime.fromtimestamp(_now_epoch(state), tz=KST).isoformat(),
                root=ledger_root,
            )
        else:
            surface["submission_state"] = "EXECUTION_RESULT_MISSING"
        state["controlled_mock_lanes"] = surface
        return state
    broker_outcome = _resolve_broker_outcome(execution)
    accepted = broker_outcome == "ACCEPTED"
    status = "BROKER_ACCEPTED" if accepted else _ATTEMPT_STATUS_BY_BROKER_OUTCOME.get(broker_outcome, "BROKER_OUTCOME_UNKNOWN")
    day = _text(surface.get("day"))
    recorded_at = datetime.fromtimestamp(_now_epoch(state), tz=KST).isoformat()
    attempt = record_attempt(
        day=day,
        candidate=candidate,
        run_id=_text(state.get("run_id")),
        recorded_at=recorded_at,
        execution=execution,
        status=status,
        broker_outcome=broker_outcome,
        root=ledger_root,
    )
    surface["attempt_ledger"] = dict(attempt)
    if accepted:
        submission = record_accepted_submission(
            day=day,
            candidate=candidate,
            run_id=_text(state.get("run_id")),
            recorded_at=recorded_at,
            execution=execution,
            root=ledger_root,
        )
        surface["submission_ledger"] = dict(submission)
        surface["submission_state"] = _text(
            _mapping(submission.get("row")).get("status")
        ) or "BROKER_ACCEPTED"
    else:
        surface["submission_state"] = _SUBMISSION_STATE_BY_BROKER_OUTCOME.get(broker_outcome, "BROKER_OUTCOME_UNKNOWN")
    state["controlled_mock_lanes"] = surface
    return state


__all__ = [
    "finalize_controlled_mock_lane_submission",
    "inject_controlled_mock_lane_intent",
]
