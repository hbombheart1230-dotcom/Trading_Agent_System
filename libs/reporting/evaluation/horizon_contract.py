from __future__ import annotations

from typing import Any, Mapping


CHECKPOINT_SECONDS = {
    "+5m": 300,
    "+15m": 900,
    "+30m": 1800,
    "+60m": 3600,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "60m": 3600,
}

HARD_EXIT_TOKENS = {
    "hard_stop",
    "stop_loss",
    "손절",
    "broker_truth_mismatch",
    "liquidity_collapse",
    "theme_breakdown",
    "market_regime_flip",
    "data_quality_guard",
    "forced_close",
    "closeout",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def _walk_dicts(value: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, Mapping):
        current = dict(value)
        rows.append((path, current))
        for key, child in current.items():
            child_path = f"{path}.{key}" if path else str(key)
            rows.extend(_walk_dicts(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value[:20]):
            rows.extend(_walk_dicts(child, f"{path}[{index}]"))
    return rows


def _candidate_score(path: str, row: Mapping[str, Any]) -> int:
    score = 0
    if isinstance(row.get("commander_horizon_policy"), Mapping):
        score += 40
    if row.get("schema_version") in {"commander_horizon_policy.v1", "strategy_horizon_feedback.v1"}:
        score += 35
    if isinstance(row.get("expected_hold_window"), Mapping):
        score += 20
    if row.get("strategy_horizon") or row.get("source_strategy_horizon"):
        score += 10
    if "commander_horizon_policy" in path:
        score += 10
    if "strategist_horizon_proposal" in path:
        score += 5
    return score


def _find_horizon_policy(*sources: Any) -> tuple[dict[str, Any], str]:
    best: tuple[int, str, dict[str, Any]] | None = None
    for source_index, source in enumerate(sources):
        for path, row in _walk_dicts(source, f"source[{source_index}]"):
            nested = row.get("commander_horizon_policy")
            if isinstance(nested, Mapping):
                nested_path = f"{path}.commander_horizon_policy"
                nested_row = dict(nested)
                score = _candidate_score(nested_path, nested_row)
                if best is None or score > best[0]:
                    best = (score, nested_path, nested_row)
            if not (
                isinstance(row.get("expected_hold_window"), Mapping)
                or row.get("strategy_horizon")
                or row.get("source_strategy_horizon")
            ):
                continue
            score = _candidate_score(path, row)
            if best is None or score > best[0]:
                best = (score, path, dict(row))
    if best is None:
        return {}, ""
    return best[2], best[1]


def build_horizon_contract(
    *,
    bundle: Mapping[str, Any],
    entry: Mapping[str, Any],
    exit_row: Mapping[str, Any],
    entry_artifact: Mapping[str, Any],
    exit_artifact: Mapping[str, Any],
    scanner_context: Mapping[str, Any],
    strategist_context: Mapping[str, Any],
    monitor_context: Mapping[str, Any],
) -> dict[str, Any]:
    policy, source_path = _find_horizon_policy(
        monitor_context,
        scanner_context,
        strategist_context,
        entry_artifact,
        exit_artifact,
        entry,
        exit_row,
        bundle,
    )
    window = _as_dict(policy.get("expected_hold_window"))
    source_window = _as_dict(policy.get("source_expected_hold_window"))
    if not source_window:
        source_window = _as_dict((policy.get("strategist_horizon_proposal") or {}).get("expected_hold_window"))
    min_sec = _number(window.get("min_sec"))
    target_sec = _number(window.get("target_sec"))
    max_sec = _number(window.get("max_sec"))
    strategy_horizon = str(policy.get("strategy_horizon") or policy.get("source_strategy_horizon") or "").strip()
    available = bool(strategy_horizon or window)
    early_reasons = policy.get("early_exit_allowed_reasons")
    if not isinstance(early_reasons, list):
        early_reasons = _as_dict(policy.get("exit_guidance")).get("early_exit_allowed_reasons")
    avoid_reasons = policy.get("avoid_early_exit_reasons")
    if not isinstance(avoid_reasons, list):
        avoid_reasons = _as_dict(policy.get("exit_guidance")).get("avoid_early_exit_reasons")
    return {
        "schema_version": "q9_horizon_contract.v1",
        "available": available,
        "source_path": source_path,
        "strategy_horizon": strategy_horizon,
        "source_strategy_horizon": str(policy.get("source_strategy_horizon") or strategy_horizon or "").strip(),
        "expected_hold_window": {
            "min_sec": min_sec,
            "target_sec": target_sec,
            "max_sec": max_sec,
        },
        "source_expected_hold_window": source_window,
        "early_exit_allowed_reasons": list(early_reasons or []),
        "avoid_early_exit_reasons": list(avoid_reasons or []),
        "profit_take_style": _as_dict(policy.get("exit_guidance")).get("profit_take_style"),
        "hold_control_bias": _as_dict(policy.get("behavior_translation")).get("hold_control_bias"),
        "stale_hold_review_sec": _number(_as_dict(policy.get("behavior_translation")).get("stale_hold_review_sec")),
        "observability_only": _truthy(policy.get("observability_only")),
        "allow_behavior_change": _truthy(policy.get("allow_behavior_change")),
        "do_not_force_hold": _truthy(policy.get("do_not_force_hold")),
    }


def _checkpoint_seconds(label: str) -> int | None:
    return CHECKPOINT_SECONDS.get(str(label or "").strip())


def _checkpoint_return_pct(row: Mapping[str, Any]) -> float | None:
    for key in ("return_pct", "pct", "change_pct", "post_exit_return_pct"):
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _closest_observed_checkpoint(
    checkpoints: Mapping[str, Any],
    target_sec: float | None,
) -> dict[str, Any]:
    if target_sec is None:
        return {}
    best: tuple[float, str, dict[str, Any], float | None] | None = None
    for label, raw in checkpoints.items():
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("status") or "") != "observed":
            continue
        sec = _checkpoint_seconds(str(label))
        if sec is None:
            continue
        delta = abs(float(sec) - float(target_sec))
        row = dict(raw)
        item = (delta, str(label), row, _checkpoint_return_pct(row))
        if best is None or item[0] < best[0]:
            best = item
    if best is None:
        return {}
    return {
        "label": best[1],
        "seconds": _checkpoint_seconds(best[1]),
        "post_exit_return_pct": best[3],
        "raw": best[2],
    }


def evaluate_horizon_contract(
    *,
    contract: Mapping[str, Any],
    actual_hold_sec: Any,
    exit_reason: str,
    net_return_pct: Any,
    post_exit: Mapping[str, Any],
) -> dict[str, Any]:
    if not contract or not contract.get("available"):
        return {
            "schema_version": "q9_horizon_alignment.v1",
            "status": "unavailable",
            "reason": "horizon_contract_missing",
        }
    actual = _number(actual_hold_sec)
    window = _as_dict(contract.get("expected_hold_window"))
    min_sec = _number(window.get("min_sec"))
    target_sec = _number(window.get("target_sec"))
    max_sec = _number(window.get("max_sec"))
    if actual is None:
        return {
            "schema_version": "q9_horizon_alignment.v1",
            "status": "unavailable",
            "reason": "actual_hold_sec_missing",
            "contract": dict(contract),
        }

    before_min = min_sec is not None and actual < min_sec
    before_target = target_sec is not None and actual < target_sec
    beyond_max = max_sec is not None and actual > max_sec
    if before_min:
        bucket = "before_min_hold"
    elif before_target:
        bucket = "before_target_hold"
    elif beyond_max:
        bucket = "beyond_max_hold"
    else:
        bucket = "within_target_window"

    exit_text = str(exit_reason or "").lower()
    allowed = {str(value or "").lower() for value in contract.get("early_exit_allowed_reasons") or []}
    allowed.update(HARD_EXIT_TOKENS)
    early_exit_allowed_match = sorted(token for token in allowed if token and token in exit_text)
    valid_early_exit = bool(early_exit_allowed_match)
    checkpoints = _as_dict(post_exit.get("checkpoints"))
    target_checkpoint = _closest_observed_checkpoint(checkpoints, target_sec)
    target_return = _number(target_checkpoint.get("post_exit_return_pct"))
    max_upside = _number(post_exit.get("max_post_exit_upside_pct"))
    max_drawdown = _number(post_exit.get("max_post_exit_drawdown_pct"))
    net_return = _number(net_return_pct)
    target_hold_would_improve_exit = target_return is not None and target_return > 0
    early_exit_cost_pct = target_return if before_target and target_return is not None else None
    violation = bool(before_min and not valid_early_exit)
    if before_target and target_hold_would_improve_exit and not valid_early_exit:
        violation = True
    return {
        "schema_version": "q9_horizon_alignment.v1",
        "status": "observed",
        "strategy_horizon": contract.get("strategy_horizon"),
        "actual_hold_sec": actual,
        "expected_hold_window": {
            "min_sec": min_sec,
            "target_sec": target_sec,
            "max_sec": max_sec,
        },
        "bucket": bucket,
        "exited_before_min_hold": before_min,
        "exited_before_target_hold": before_target,
        "exited_beyond_max_hold": beyond_max,
        "early_exit_allowed_match": early_exit_allowed_match,
        "valid_early_exit": valid_early_exit,
        "horizon_violation_candidate": violation,
        "target_checkpoint": target_checkpoint,
        "target_hold_would_improve_exit": target_hold_would_improve_exit,
        "early_exit_cost_pct": early_exit_cost_pct,
        "realized_net_return_pct": net_return,
        "max_post_exit_upside_pct": max_upside,
        "max_post_exit_drawdown_pct": max_drawdown,
        "contract": dict(contract),
    }
