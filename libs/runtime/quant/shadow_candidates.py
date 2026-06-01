from __future__ import annotations

import json
from datetime import UTC, datetime, time as dt_time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from libs.runtime.quant.opening_largecap_surge_shadow import (
    OPENING_LARGECAP_SURGE_WATCHLIST,
    build_opening_largecap_surge_shadow,
)

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python fallback only
    ZoneInfo = None  # type: ignore


SHADOW_CANDIDATE_ROOT = Path("data/logs/quant_shadow_candidates")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _compact_ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M%SZ")


def _today_kst() -> str:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    return datetime.now().date().isoformat()


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"none", "null", "unknown", "not_captured"} else text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _resolve_day(state: Mapping[str, Any]) -> str:
    for key in ("trade_day", "execution_day", "report_day", "day", "date"):
        day = _text(state.get(key))
        if day:
            return day[:10]
    return _today_kst()


def _kst_datetime_from_state(state: Mapping[str, Any]) -> datetime:
    epoch = 0.0
    for key in ("tick_ts", "now_epoch", "timestamp"):
        try:
            epoch = float(state.get(key) or 0.0)
        except Exception:
            epoch = 0.0
        if epoch > 0:
            break
    if epoch > 0 and ZoneInfo is not None:
        return datetime.fromtimestamp(epoch, tz=ZoneInfo("Asia/Seoul"))
    if epoch > 0:
        return datetime.fromtimestamp(epoch)
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Seoul"))
    return datetime.now()


def _opening_minutes_since_open(state: Mapping[str, Any]) -> int | None:
    now = _kst_datetime_from_state(state)
    market_open = datetime.combine(now.date(), dt_time(hour=9, minute=0), tzinfo=now.tzinfo)
    minutes = int((now - market_open).total_seconds() // 60)
    if minutes < 0:
        return None
    return minutes


def _symbol(row: Mapping[str, Any]) -> str:
    return _text(row.get("symbol") or row.get("stk_cd") or row.get("code"))


def _rank(row: Mapping[str, Any]) -> Any:
    return row.get("rank") or row.get("priority_rank") or row.get("scanner_rank")


def _score(row: Mapping[str, Any]) -> Any:
    return row.get("score_total") or row.get("score") or row.get("total_score")


def _candidate_lookup(rows: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = _symbol(row)
        if symbol and symbol not in out:
            out[symbol] = dict(row)
    return out


def _candidate_context(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": _symbol(row),
        "name": _text(row.get("name") or row.get("stock_name") or row.get("symbol_name")),
        "rank": _rank(row),
        "score_total": _score(row),
        "theme": _text(row.get("theme") or row.get("matched_theme") or row.get("theme_name")),
        "quant_tactic_id": _text(row.get("quant_tactic_id") or row.get("tactic_id")),
        "tactic_suitability_tier": _text(row.get("tactic_suitability_tier")),
        "tactic_suitability_score": row.get("tactic_suitability_score"),
        "entry_quant_cost_floor_state": _text(row.get("entry_quant_cost_floor_state")),
    }


def _cost_floor_state_from_entry(entry_info: Mapping[str, Any]) -> str:
    direct = _text(entry_info.get("entry_quant_cost_floor_state"))
    if direct:
        return direct
    decision = _as_dict(entry_info.get("entry_quant_decision"))
    cost_edge = _as_dict(decision.get("cost_edge"))
    from_decision = _text(cost_edge.get("cost_floor_state"))
    if from_decision:
        return from_decision
    factors = _as_dict(_as_dict(entry_info.get("quant_factor_snapshot")).get("factors"))
    return _text(factors.get("cost_floor_state"))


def _factor_snapshot(row: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = _as_dict(row.get("quant_factor_snapshot"))
    return _as_dict(snapshot.get("factors"))


def _candidate_factor_snapshot(row: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = _as_dict(row.get("quant_factor_snapshot"))
    if snapshot:
        return snapshot
    factors: Dict[str, Any] = {}
    features = _as_dict(row.get("features"))
    metrics = _as_dict(row.get("metrics"))
    for key in (
        "volume_ratio",
        "vwap_distance_pct",
        "vwap_distance",
        "breakout_ok",
        "weighted_score_passed",
        "human_chart_entry_score",
        "cost_floor_state",
        "cost_adjusted_edge_ok",
    ):
        if key in row:
            factors[key] = row.get(key)
        if key in features and key not in factors:
            factors[key] = features.get(key)
        if key in metrics and key not in factors:
            factors[key] = metrics.get(key)
    if "vwap_distance_pct" not in factors and "vwap_distance" in factors:
        factors["vwap_distance_pct"] = factors.get("vwap_distance")
    return {"factors": factors} if factors else {}


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _cost_ok_for_opening_probe(row: Mapping[str, Any]) -> bool:
    if _bool(row.get("cost_adjusted_edge_ok")):
        return True
    decision = _as_dict(row.get("entry_quant_decision"))
    cost_edge = _as_dict(decision.get("cost_edge"))
    if _bool(cost_edge.get("ok")):
        return True
    factors = _factor_snapshot(row)
    if _bool(factors.get("cost_adjusted_edge_ok")):
        return True
    return _text(row.get("entry_quant_cost_floor_state")) == "met" or _text(factors.get("cost_floor_state")) == "met"


def _opening_probe_payload(row: Mapping[str, Any], *, opening_minutes: int | None) -> Dict[str, Any]:
    if opening_minutes is None or opening_minutes > 20:
        return {
            "eligible": False,
            "would_probe": False,
            "reason": "outside_opening_window",
            "minutes_since_open": opening_minutes,
        }

    factors = _factor_snapshot(row)
    volume_ratio = _float(row.get("volume_ratio"), _float(factors.get("volume_ratio"), 0.0)) or 0.0
    vwap_distance = _float(row.get("vwap_distance"), _float(factors.get("vwap_distance_pct"), 0.0)) or 0.0
    human_chart_entry_score = _float(factors.get("human_chart_entry_score"), 0.0) or 0.0
    breakout_ok = _bool(row.get("breakout_ok")) or _bool(factors.get("breakout_ok"))
    weighted_score_passed = _bool(factors.get("weighted_score_passed"))
    cost_ok = _cost_ok_for_opening_probe(row)
    momentum_ok = bool(
        cost_ok
        and volume_ratio >= 0.8
        and vwap_distance >= 0.0
        and (
            breakout_ok
            or weighted_score_passed
            or human_chart_entry_score >= 0.65
        )
    )
    reason_parts: List[str] = []
    if not cost_ok:
        reason_parts.append("cost_edge_not_met")
    if volume_ratio < 0.8:
        reason_parts.append("volume_ratio_below_probe_floor")
    if vwap_distance < 0.0:
        reason_parts.append("below_vwap")
    if not (breakout_ok or weighted_score_passed or human_chart_entry_score >= 0.65):
        reason_parts.append("momentum_structure_not_confirmed")
    return {
        "eligible": True,
        "would_probe": momentum_ok,
        "reason": "opening_momentum_probe_ready" if momentum_ok else ",".join(reason_parts),
        "minutes_since_open": opening_minutes,
        "cost_ok": cost_ok,
        "volume_ratio": volume_ratio,
        "vwap_distance_pct": vwap_distance,
        "breakout_ok": breakout_ok,
        "weighted_score_passed": weighted_score_passed,
        "human_chart_entry_score": human_chart_entry_score,
        "probe_size_hint": "small",
        "behavior_effect": "observation_only",
    }


def _attach_opening_probe(row: Dict[str, Any], *, opening_minutes: int | None) -> Dict[str, Any]:
    probe = _opening_probe_payload(row, opening_minutes=opening_minutes)
    largecap_probe = build_opening_largecap_surge_shadow(row, opening_minutes=opening_minutes)
    row["opening_momentum_probe_shadow"] = dict(probe)
    row["opening_momentum_probe_would_enter"] = bool(probe.get("would_probe"))
    row["opening_largecap_surge_shadow"] = dict(largecap_probe)
    row["opening_largecap_surge_would_enter"] = bool(largecap_probe.get("would_probe"))
    return row


def _top_pick_row(
    *,
    selected: Mapping[str, Any],
    cascade: Mapping[str, Any],
    entry_info: Mapping[str, Any],
) -> Dict[str, Any]:
    symbol = _text(cascade.get("top_pick_symbol")) or _symbol(selected)
    row = _candidate_context(selected)
    cost_floor_state = _cost_floor_state_from_entry(entry_info)
    if cost_floor_state:
        row["entry_quant_cost_floor_state"] = cost_floor_state
    row.update(
        {
            "symbol": symbol,
            "shadow_role": "top_pick",
            "evaluated": True,
            "triggered": _bool(cascade.get("top_pick_triggered")),
            "guard_blocked": _bool(cascade.get("top_pick_guard_blocked")),
            "reason": _text(cascade.get("top_pick_reason") or entry_info.get("reason")),
            "primary_failure_axis": _text(entry_info.get("primary_failure_axis")),
            "guard_reason": _text(entry_info.get("guard_reason")),
            "intent_submitted": _bool(entry_info.get("intent_submitted")),
            "buy_blocked_open_position": _bool(entry_info.get("buy_blocked_open_position")),
            "buy_blocked_same_symbol": _bool(entry_info.get("buy_blocked_same_symbol")),
            "buy_blocked_pending_buy": _bool(entry_info.get("buy_blocked_pending_buy")),
            "buy_blocked_post_exit_cooldown": _bool(entry_info.get("buy_blocked_post_exit_cooldown")),
            "buy_blocked_closeout_window": _bool(entry_info.get("buy_blocked_closeout_window")),
            "would_enter": _bool(entry_info.get("intent_submitted"))
            and not _bool(cascade.get("top_pick_guard_blocked")),
            "final_selected": symbol == _text(cascade.get("final_selected_symbol")),
            "entry_lane": _text(entry_info.get("entry_lane")),
            "cost_adjusted_edge_ok": _bool(entry_info.get("cost_adjusted_edge_ok")),
            "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
            "cost_drag_pct": entry_info.get("cost_drag_pct"),
            "quant_factor_snapshot": _as_dict(entry_info.get("quant_factor_snapshot")),
            "entry_quant_decision": _as_dict(entry_info.get("entry_quant_decision")),
        }
    )
    return row


def _runner_row(trace: Mapping[str, Any], ranked_by_symbol: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    symbol = _symbol(trace)
    base = _candidate_context(ranked_by_symbol.get(symbol, {}))
    base.update(
        {
            "symbol": symbol,
            "shadow_role": "runner_up_evaluated",
            "evaluated": True,
            "rank": trace.get("rank") or base.get("rank"),
            "score_total": trace.get("score_total") or base.get("score_total"),
            "triggered": _bool(trace.get("triggered")),
            "guard_blocked": _bool(trace.get("guard_blocked")),
            "guard_reason": _text(trace.get("guard_reason")),
            "intent_submitted": _bool(trace.get("intent_submitted")),
            "buy_blocked_open_position": _bool(trace.get("buy_blocked_open_position")),
            "buy_blocked_same_symbol": _bool(trace.get("buy_blocked_same_symbol")),
            "buy_blocked_pending_buy": _bool(trace.get("buy_blocked_pending_buy")),
            "buy_blocked_post_exit_cooldown": _bool(trace.get("buy_blocked_post_exit_cooldown")),
            "buy_blocked_closeout_window": _bool(trace.get("buy_blocked_closeout_window")),
            "reason": _text(trace.get("reason")),
            "primary_failure_axis": _text(trace.get("primary_failure_axis")),
            "transition_readiness_score": trace.get("transition_readiness_score"),
            "vwap_distance": trace.get("vwap_distance"),
            "volume_ratio": trace.get("volume_ratio"),
            "breakout_ok": trace.get("breakout_ok"),
            "pullback_ok": trace.get("pullback_ok"),
            "extension_ok": trace.get("extension_ok"),
            "confidence_score": trace.get("confidence_score"),
            "confidence_threshold": trace.get("confidence_threshold"),
            "runner_up_quality_gate": _as_dict(trace.get("runner_up_quality_gate")),
            "pullback_evidence_profile": _as_dict(trace.get("pullback_evidence_profile")),
            "runner_up_quality_blocked": _bool(trace.get("runner_up_quality_blocked")),
            "weak_fallback_blocked": _bool(trace.get("weak_fallback_blocked")),
        }
    )
    base["would_enter"] = (
        _bool(base.get("triggered"))
        and not _bool(base.get("guard_blocked"))
        and not _bool(base.get("runner_up_quality_blocked"))
        and not _bool(base.get("weak_fallback_blocked"))
    )
    return base


def _skipped_row(row: Mapping[str, Any], ranked_by_symbol: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    symbol = _symbol(row)
    base = _candidate_context(ranked_by_symbol.get(symbol, row))
    base.update(
        {
            "symbol": symbol,
            "shadow_role": "runner_up_skipped",
            "evaluated": False,
            "reason": _text(row.get("reason") or row.get("skip_reason")),
            "would_enter": False,
        }
    )
    return base


def _metric_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _has_metric_data(row: Mapping[str, Any]) -> bool:
    factors = _factor_snapshot(row)
    return any(
        _metric_value(
            row.get(key),
            factors.get(key),
            factors.get("vwap_distance_pct") if key == "vwap_distance" else None,
        )
        not in (None, "")
        for key in ("volume_ratio", "vwap_distance", "breakout_ok", "cost_floor_state")
    ) or _bool(row.get("cost_adjusted_edge_ok"))


def _same_symbol_metric_row(symbol: str, candidates: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    for row in candidates:
        if _text(row.get("symbol")) == symbol and _has_metric_data(row):
            return dict(row)
    return {}


def _opening_largecap_watchlist_row(row: Mapping[str, Any], *, metric_row: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    base = _candidate_context(row)
    symbol = _symbol(row)
    metrics = _as_dict(metric_row)
    row_features = _as_dict(row.get("features"))
    row_metrics = _as_dict(row.get("metrics"))
    metric_factors = _factor_snapshot(metrics)
    row_factors = _factor_snapshot(row)
    volume_ratio = _metric_value(
        metrics.get("volume_ratio"),
        metric_factors.get("volume_ratio"),
        row.get("volume_ratio"),
        row_factors.get("volume_ratio"),
        row_features.get("volume_ratio"),
        row_metrics.get("volume_ratio"),
    )
    vwap_distance = _metric_value(
        metrics.get("vwap_distance"),
        metric_factors.get("vwap_distance_pct"),
        metric_factors.get("vwap_distance"),
        row.get("vwap_distance"),
        row.get("vwap_distance_pct"),
        row_factors.get("vwap_distance_pct"),
        row_factors.get("vwap_distance"),
        row_features.get("vwap_distance_pct"),
        row_metrics.get("vwap_distance_pct"),
    )
    breakout_ok = _metric_value(
        metrics.get("breakout_ok"),
        metric_factors.get("breakout_ok"),
        row.get("breakout_ok"),
        row_factors.get("breakout_ok"),
        row_features.get("breakout_ok"),
        row_metrics.get("breakout_ok"),
    )
    cost_adjusted_edge_ok = _metric_value(
        metrics.get("cost_adjusted_edge_ok"),
        metric_factors.get("cost_adjusted_edge_ok"),
        row.get("cost_adjusted_edge_ok"),
        row_factors.get("cost_adjusted_edge_ok"),
    )
    metric_source = (
        f"{_text(metrics.get('shadow_role'))}_same_symbol"
        if metrics
        else "ranked_candidates"
    )
    metric_missing = not any(value not in (None, "") for value in (volume_ratio, vwap_distance, breakout_ok, cost_adjusted_edge_ok))
    factor_snapshot = _candidate_factor_snapshot(row)
    if metrics:
        merged_factors = _as_dict(factor_snapshot.get("factors"))
        merged_factors.update({key: value for key, value in metric_factors.items() if value not in (None, "")})
        if volume_ratio not in (None, ""):
            merged_factors["volume_ratio"] = volume_ratio
        if vwap_distance not in (None, ""):
            merged_factors["vwap_distance_pct"] = vwap_distance
        if breakout_ok not in (None, ""):
            merged_factors["breakout_ok"] = breakout_ok
        if cost_adjusted_edge_ok not in (None, ""):
            merged_factors["cost_adjusted_edge_ok"] = cost_adjusted_edge_ok
        factor_snapshot = {"factors": merged_factors} if merged_factors else factor_snapshot
    base.update(
        {
            "symbol": symbol,
            "shadow_role": "opening_largecap_watchlist",
            "evaluated": False,
            "reason": "opening_largecap_watchlist_not_evaluated_by_monitor",
            "would_enter": False,
            "volume_ratio": volume_ratio,
            "vwap_distance": vwap_distance,
            "breakout_ok": breakout_ok,
            "cost_adjusted_edge_ok": _bool(cost_adjusted_edge_ok),
            "quant_factor_snapshot": factor_snapshot,
            "source": "ranked_candidates",
            "metric_source": metric_source,
            "metric_missing_reason": "minute_metrics_not_available" if metric_missing else "",
        }
    )
    return base


def build_quant_shadow_candidate_payload(
    state: Mapping[str, Any],
    *,
    trigger: str = "monitor_cycle",
) -> Dict[str, Any]:
    cascade = _as_dict(
        state.get("monitor_entry_cascade")
        or _as_dict(state.get("monitor_output")).get("entry_candidate_cascade")
    )
    selected = _as_dict(state.get("selected"))
    entry_info = _as_dict(state.get("monitor_entry"))
    ranked_by_symbol = _candidate_lookup(_as_list(state.get("ranked_candidates")))
    generated_at = _utc_now()
    opening_minutes = _opening_minutes_since_open(state)

    candidates: List[Dict[str, Any]] = []
    if _text(cascade.get("top_pick_symbol")) or _symbol(selected):
        candidates.append(
            _attach_opening_probe(
                _top_pick_row(selected=selected, cascade=cascade, entry_info=entry_info),
                opening_minutes=opening_minutes,
            )
        )

    for trace in _as_list(cascade.get("fallback_trace")):
        if isinstance(trace, Mapping) and _symbol(trace):
            candidates.append(
                _attach_opening_probe(
                    _runner_row(trace, ranked_by_symbol),
                    opening_minutes=opening_minutes,
                )
            )

    for skipped in _as_list(cascade.get("skipped")):
        if isinstance(skipped, Mapping) and _symbol(skipped):
            candidates.append(_skipped_row(skipped, ranked_by_symbol))

    seen_symbols = {_text(row.get("symbol")) for row in candidates if _text(row.get("symbol"))}
    if opening_minutes is not None and opening_minutes <= 20:
        for row in _as_list(state.get("ranked_candidates")):
            if not isinstance(row, Mapping):
                continue
            symbol = _symbol(row)
            if symbol not in OPENING_LARGECAP_SURGE_WATCHLIST or symbol in seen_symbols:
                continue
            metric_row = _same_symbol_metric_row(symbol, candidates)
            candidates.append(
                _attach_opening_probe(
                    _opening_largecap_watchlist_row(row, metric_row=metric_row),
                    opening_minutes=opening_minutes,
                )
            )
            seen_symbols.add(symbol)

    return {
        "schema_version": "quant_shadow_candidates.v1",
        "behavior_effect": "observation_only",
        "trigger": str(trigger or "monitor_cycle"),
        "run_id": _text(state.get("run_id")),
        "day": _resolve_day(state),
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "opening_momentum_probe_shadow": {
            "enabled": True,
            "window_minutes": 20,
            "minutes_since_open": opening_minutes,
            "behavior_effect": "observation_only",
        },
        "cascade": {
            "attempted": _bool(cascade.get("attempted")),
            "eligible": _bool(cascade.get("eligible")),
            "reason": _text(cascade.get("reason")),
            "fallback_used": _bool(cascade.get("fallback_used")),
            "fallback_from_symbol": _text(cascade.get("fallback_from_symbol")),
            "fallback_to_symbol": _text(cascade.get("fallback_to_symbol")),
            "final_selected_symbol": _text(cascade.get("final_selected_symbol")),
            "open_position_count": cascade.get("open_position_count"),
            "max_positions": cascade.get("max_positions"),
            "capacity_remaining": cascade.get("capacity_remaining"),
        },
        "summary": {
            "candidate_count": len(candidates),
            "evaluated_count": sum(1 for row in candidates if _bool(row.get("evaluated"))),
            "would_enter_count": sum(1 for row in candidates if _bool(row.get("would_enter"))),
            "opening_momentum_probe_would_enter_count": sum(
                1 for row in candidates if _bool(row.get("opening_momentum_probe_would_enter"))
            ),
            "opening_largecap_surge_would_enter_count": sum(
                1 for row in candidates if _bool(row.get("opening_largecap_surge_would_enter"))
            ),
        },
        "candidates": candidates,
    }


def save_quant_shadow_candidate_payload(
    payload: Mapping[str, Any],
    *,
    root: Path = SHADOW_CANDIDATE_ROOT,
) -> Dict[str, Any]:
    payload_dict = dict(payload)
    candidates = _as_list(payload_dict.get("candidates"))
    if not candidates:
        return {"status": "skipped", "reason": "no_shadow_candidates", "candidate_count": 0}

    day = _text(payload_dict.get("day")) or _today_kst()
    generated_at = _utc_now()
    day_dir = root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    run_id = _text(payload_dict.get("run_id")) or "monitor"
    safe_run_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in run_id)[:80]
    path = day_dir / f"{_compact_ts(generated_at)}_{safe_run_id}.json"
    latest_path = day_dir / "latest.json"
    payload_dict["path"] = str(path)
    payload_dict["latest_path"] = str(latest_path)
    text = json.dumps(payload_dict, ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return {
        "status": "ok",
        "path": str(path),
        "latest_path": str(latest_path),
        "candidate_count": len(candidates),
    }


def save_quant_shadow_candidates_for_state(
    state: Mapping[str, Any],
    *,
    trigger: str = "monitor_cycle",
    root: Path = SHADOW_CANDIDATE_ROOT,
) -> Dict[str, Any]:
    payload = build_quant_shadow_candidate_payload(state, trigger=trigger)
    return save_quant_shadow_candidate_payload(payload, root=root)
