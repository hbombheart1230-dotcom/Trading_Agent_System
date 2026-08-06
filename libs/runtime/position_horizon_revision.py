from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from libs.core.symbols import normalize_symbol
from libs.runtime.strategy_horizon_feedback import build_commander_horizon_policy


ALLOWED_HORIZONS = ("scalp", "intraday", "overnight_probe", "1_2day_swing")
INTRADAY_HORIZONS = ("scalp", "intraday")
DEFAULT_WINDOWS = {
    "scalp": {"min_sec": 60, "target_sec": 300, "max_sec": 900},
    "intraday": {"min_sec": 300, "target_sec": 1800, "max_sec": 14400},
    "overnight_probe": {"min_sec": 1800, "target_sec": 14400, "max_sec": 86400},
    "1_2day_swing": {"min_sec": 3600, "target_sec": 86400, "max_sec": 172800},
}
STALE_REVIEW_SEC = {
    "scalp": 600,
    "intraday": 1800,
    "overnight_probe": 7200,
    "1_2day_swing": 14400,
}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _horizon(value: Any, default: str = "intraday") -> str:
    text = str(value or "").strip().lower()
    return text if text in ALLOWED_HORIZONS else default


def _window(value: Any, horizon: str) -> dict[str, int]:
    defaults = dict(DEFAULT_WINDOWS[_horizon(horizon)])
    raw = _dict(value)
    result = {
        "min_sec": max(0, _int(raw.get("min_sec"), defaults["min_sec"])),
        "target_sec": max(0, _int(raw.get("target_sec"), defaults["target_sec"])),
        "max_sec": max(0, _int(raw.get("max_sec"), defaults["max_sec"])),
    }
    result["target_sec"] = max(result["min_sec"], result["target_sec"])
    result["max_sec"] = max(result["target_sec"], result["max_sec"])
    return result


def horizon_from_output(output: Mapping[str, Any] | None) -> tuple[str, dict[str, int]]:
    obj = _dict(output)
    policy = _dict(obj.get("commander_horizon_policy"))
    feedback = _dict(obj.get("strategy_horizon_feedback"))
    horizon = _horizon(
        policy.get("strategy_horizon")
        or obj.get("strategy_horizon")
        or feedback.get("strategy_horizon")
    )
    window = _window(
        policy.get("expected_hold_window")
        or obj.get("expected_hold_window")
        or feedback.get("expected_hold_window"),
        horizon,
    )
    return horizon, window


def initialize_horizon_state(
    output: Mapping[str, Any] | None,
    *,
    now_epoch: int,
) -> dict[str, Any]:
    horizon, window = horizon_from_output(output)
    return {
        "schema_version": "position_horizon_state.v1",
        "entry_horizon": horizon,
        "active_horizon": horizon,
        "entry_expected_hold_window": dict(window),
        "active_expected_hold_window": dict(window),
        "entry_epoch": int(now_epoch),
        "last_review_epoch": None,
        "next_review_epoch": int(now_epoch + STALE_REVIEW_SEC[horizon]),
        "last_stage3_decision": {},
        "last_stage4_decision": {},
        "stage4_carry_approved": False,
        "revision_history": [],
        "applied_revision_ids": [],
    }


def ensure_horizon_state(row: Mapping[str, Any] | None) -> dict[str, Any]:
    context = _dict(row)
    existing = _dict(context.get("horizon_state"))
    output = _dict(context.get("output"))
    entry_horizon, entry_window = horizon_from_output(output)
    state = initialize_horizon_state(
        output,
        now_epoch=_int(existing.get("entry_epoch") or context.get("generated_epoch"), 0),
    )
    if existing:
        state.update(existing)
    state["schema_version"] = "position_horizon_state.v1"
    state["entry_horizon"] = _horizon(state.get("entry_horizon"), entry_horizon)
    state["active_horizon"] = _horizon(state.get("active_horizon"), state["entry_horizon"])
    state["entry_expected_hold_window"] = _window(
        state.get("entry_expected_hold_window") or entry_window,
        state["entry_horizon"],
    )
    state["active_expected_hold_window"] = _window(
        state.get("active_expected_hold_window"),
        state["active_horizon"],
    )
    state["revision_history"] = [
        dict(item) for item in list(state.get("revision_history") or []) if isinstance(item, Mapping)
    ][-30:]
    state["applied_revision_ids"] = [
        str(item) for item in list(state.get("applied_revision_ids") or []) if str(item or "").strip()
    ][-30:]
    return state


def position_review_due(
    row: Mapping[str, Any] | None,
    *,
    position_age_seconds: int | None,
    now_epoch: int,
) -> bool:
    context = _dict(row)
    state = ensure_horizon_state(context)
    if not context or not _dict(context.get("horizon_state")):
        age = max(0, _int(position_age_seconds, 0))
        return age >= STALE_REVIEW_SEC[_horizon(state.get("active_horizon"))]
    next_epoch = _int(state.get("next_review_epoch"), 0)
    if next_epoch > 0 and now_epoch > 0:
        return now_epoch >= next_epoch
    age = max(0, _int(position_age_seconds, 0))
    return age >= STALE_REVIEW_SEC[_horizon(state.get("active_horizon"))]


def _revision_id(*, run_id: str, stage: str, symbol: str, decision: str) -> str:
    return ":".join((run_id or "unknown_run", stage, symbol, decision or "unknown"))


def _append_revision(
    state: dict[str, Any],
    *,
    revision_id: str,
    stage: str,
    now_epoch: int,
    prior_horizon: str,
    active_horizon: str,
    decision: str,
    reason: str,
    approved: bool,
) -> None:
    if revision_id in list(state.get("applied_revision_ids") or []):
        return
    state.setdefault("revision_history", []).append(
        {
            "revision_id": revision_id,
            "stage": stage,
            "review_epoch": int(now_epoch),
            "prior_horizon": prior_horizon,
            "active_horizon": active_horizon,
            "decision": decision,
            "approved": bool(approved),
            "reason": str(reason or ""),
        }
    )
    state["revision_history"] = list(state["revision_history"])[-30:]
    state.setdefault("applied_revision_ids", []).append(revision_id)
    state["applied_revision_ids"] = list(state["applied_revision_ids"])[-30:]


def _apply_stage3(
    horizon_state: dict[str, Any],
    review: Mapping[str, Any],
    *,
    run_id: str,
    symbol: str,
    now_epoch: int,
) -> dict[str, Any]:
    data = _dict(review)
    decision = str(data.get("hold_review_decision") or "wait_until_next_check").strip().lower()
    action = str(data.get("horizon_action") or "maintain").strip().lower()
    proposed = _horizon(data.get("proposed_horizon"), _horizon(horizon_state.get("active_horizon")))
    confidence = str(data.get("evidence_confidence") or "low").strip().lower()
    quality = str(data.get("data_quality") or "insufficient").strip().lower()
    prior = _horizon(horizon_state.get("active_horizon"))
    revision_id = _revision_id(
        run_id=run_id or str(now_epoch),
        stage="stage3",
        symbol=symbol,
        decision=f"{decision}:{action}:{proposed}",
    )
    if revision_id in list(horizon_state.get("applied_revision_ids") or []):
        return horizon_state
    approved = confidence in {"medium", "high"} and quality in {"ok", "partial"}
    reason = str(data.get("reason") or "")
    if action in {"shorten", "extend"} and proposed not in INTRADAY_HORIZONS:
        approved = False
        reason = f"stage3_cannot_authorize_overnight:{reason}"
    if action not in {"shorten", "extend"}:
        proposed = prior
    if approved and action in {"shorten", "extend"}:
        horizon_state["active_horizon"] = proposed
        horizon_state["active_expected_hold_window"] = _window(
            data.get("revised_hold_window"), proposed
        )
    next_minutes = max(1, _int(data.get("next_check_minutes"), 5))
    horizon_state["last_review_epoch"] = int(now_epoch)
    horizon_state["next_review_epoch"] = int(now_epoch + next_minutes * 60)
    horizon_state["last_stage3_decision"] = {
        **data,
        "commander_revision_approved": bool(approved and action in {"shorten", "extend"}),
    }
    _append_revision(
        horizon_state,
        revision_id=revision_id,
        stage="stale_intraday_hold_review",
        now_epoch=now_epoch,
        prior_horizon=prior,
        active_horizon=_horizon(horizon_state.get("active_horizon")),
        decision=f"{decision}:{action}",
        reason=reason,
        approved=bool(approved),
    )
    return horizon_state


def _apply_stage4(
    horizon_state: dict[str, Any],
    review: Mapping[str, Any],
    *,
    portfolio_decision: str,
    run_id: str,
    symbol: str,
    now_epoch: int,
    best_one_already_selected: bool,
) -> tuple[dict[str, Any], bool]:
    data = _dict(review)
    decision = str(data.get("decision") or "flatten_today").strip().lower()
    confidence = str(data.get("carry_confidence") or "low").strip().lower()
    prior = _horizon(horizon_state.get("active_horizon"))
    revision_id = _revision_id(
        run_id=run_id or str(now_epoch),
        stage="stage4",
        symbol=symbol,
        decision=decision,
    )
    if revision_id in list(horizon_state.get("applied_revision_ids") or []):
        return horizon_state, bool(horizon_state.get("stage4_carry_approved"))
    carry_requested = decision == "carry_overnight" and portfolio_decision != "flatten_all"
    if portfolio_decision == "carry_only_best_one" and best_one_already_selected:
        carry_requested = False
    approved = carry_requested and confidence in {"medium", "high"}
    if approved:
        active = prior if prior == "1_2day_swing" else "overnight_probe"
        horizon_state["active_horizon"] = active
        horizon_state["active_expected_hold_window"] = _window({}, active)
    else:
        active = "intraday" if prior in {"overnight_probe", "1_2day_swing"} else prior
        horizon_state["active_horizon"] = active
        horizon_state["active_expected_hold_window"] = _window({}, active)
    horizon_state["stage4_carry_approved"] = bool(approved)
    horizon_state["last_stage4_decision"] = {
        **data,
        "portfolio_level_decision": portfolio_decision,
        "commander_revision_approved": bool(approved),
    }
    horizon_state["last_review_epoch"] = int(now_epoch)
    _append_revision(
        horizon_state,
        revision_id=revision_id,
        stage="end_of_day_carry_review",
        now_epoch=now_epoch,
        prior_horizon=prior,
        active_horizon=_horizon(horizon_state.get("active_horizon")),
        decision=decision,
        reason=str(data.get("reason") or ""),
        approved=bool(approved),
    )
    return horizon_state, bool(approved)


def apply_strategist_horizon_revision(
    state: dict[str, Any],
    *,
    now_epoch: int,
) -> dict[str, Any]:
    output = _dict(state.get("strategist_output"))
    persisted = _dict(state.get("persisted_state"))
    contexts = _dict(persisted.get("position_strategy_context"))
    if not output or not contexts:
        return state
    run_id = str(state.get("run_id") or "")
    applied: list[dict[str, Any]] = []

    stage3 = _dict(output.get("stale_intraday_hold_review"))
    if stage3:
        commander = _dict(state.get("commander_decision"))
        refresh = _dict(commander.get("strategist_refresh_context"))
        symbol = normalize_symbol(refresh.get("selected_symbol"))
        row = _dict(contexts.get(symbol))
        if symbol and row:
            horizon_state = _apply_stage3(
                ensure_horizon_state(row), stage3, run_id=run_id, symbol=symbol, now_epoch=now_epoch
            )
            row["horizon_state"] = horizon_state
            contexts[symbol] = row
            applied.append({"symbol": symbol, "stage": "stage3", "horizon_state": dict(horizon_state)})

    stage4 = _dict(output.get("end_of_day_carry_review"))
    if stage4:
        portfolio_decision = str(stage4.get("portfolio_level_decision") or "flatten_all").strip().lower()
        carry_selected = False
        by_symbol = {
            normalize_symbol(item.get("symbol")): dict(item)
            for item in list(stage4.get("carry_review") or [])
            if isinstance(item, Mapping) and normalize_symbol(item.get("symbol"))
        }
        for symbol, raw_row in list(contexts.items()):
            row = _dict(raw_row)
            review = by_symbol.get(normalize_symbol(symbol), {"symbol": symbol, "decision": "flatten_today"})
            horizon_state, approved = _apply_stage4(
                ensure_horizon_state(row),
                review,
                portfolio_decision=portfolio_decision,
                run_id=run_id,
                symbol=normalize_symbol(symbol),
                now_epoch=now_epoch,
                best_one_already_selected=carry_selected,
            )
            carry_selected = carry_selected or approved
            row["horizon_state"] = horizon_state
            contexts[normalize_symbol(symbol)] = row
            applied.append({"symbol": normalize_symbol(symbol), "stage": "stage4", "horizon_state": dict(horizon_state)})

    if applied:
        persisted["position_strategy_context"] = contexts
        state["persisted_state"] = persisted
        state["position_horizon_revision"] = {
            "schema_version": "position_horizon_revision.v1",
            "applied": True,
            "rows": applied,
        }
    return state


def active_horizon_policy_for_context(row: Mapping[str, Any] | None) -> dict[str, Any]:
    context = _dict(row)
    horizon_state = ensure_horizon_state(context)
    horizon = _horizon(horizon_state.get("active_horizon"))
    window = _window(horizon_state.get("active_expected_hold_window"), horizon)
    policy = build_commander_horizon_policy(
        {
            "strategy_horizon": horizon,
            "expected_hold_window": window,
            "source": "position_horizon_revision",
        },
        commander_context={},
        live_validation_mode=True,
        source="position_horizon_revision",
    )
    policy["expected_hold_window"] = dict(window)
    policy["source_expected_hold_window"] = dict(window)
    policy["entry_horizon"] = str(horizon_state.get("entry_horizon") or horizon)
    policy["active_horizon"] = horizon
    policy["horizon_revision_applied"] = bool(horizon_state.get("revision_history"))
    policy["decision_reason"] = "commander_applies_position_active_horizon"
    return policy


def overlay_active_horizon_on_output(
    output: Mapping[str, Any] | None,
    row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = deepcopy(_dict(output))
    if not result:
        return result
    horizon_state = ensure_horizon_state(row)
    policy = active_horizon_policy_for_context(row)
    horizon = str(policy.get("strategy_horizon") or "intraday")
    window = dict(policy.get("expected_hold_window") or {})
    result["commander_horizon_policy"] = dict(policy)
    result["strategy_horizon"] = horizon
    result["expected_hold_window"] = window
    result["position_horizon_state"] = dict(horizon_state)
    strategy_policy = _dict(result.get("strategy_policy"))
    strategy_policy["commander_horizon_policy"] = dict(policy)
    monitor_policy = _dict(strategy_policy.get("monitor_policy"))
    monitor_policy["commander_horizon_policy"] = dict(policy)
    monitor_policy["horizon_policy"] = dict(policy)
    strategy_policy["monitor_policy"] = monitor_policy
    result["strategy_policy"] = strategy_policy
    return result
