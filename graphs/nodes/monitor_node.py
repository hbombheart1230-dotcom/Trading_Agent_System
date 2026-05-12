from __future__ import annotations

"""Canonical Monitor node for integrated runtime.

Role boundary:
- monitors selected stock / active position state
- emits entry/exit intents only
- never re-ranks symbol universe and never executes orders
"""

import os
import time
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    account_order_is_pending,
    account_order_side,
    extract_account_orders_rows,
    extract_market_quotes,
    extract_minute_ohlcv_by_symbol,
    extract_order_status,
)
from libs.core.symbols import normalize_symbol
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input
from libs.runtime.canonical_artifacts import write_monitor_artifact
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.decision_observability import (
    build_entry_blocker_surface,
    build_monitor_no_trade_surface,
    build_scanner_monitor_handoff_surface,
)
from libs.runtime.monitor_candidate_cascade import build_entry_candidate_cascade_plan
from libs.runtime.commander_memory_application_trace import build_monitor_commander_memory_application_trace
from libs.runtime.exit_policy import (
    apply_account_pnl_crosscheck_context,
    apply_env_stop_take_fallbacks,
    evaluate_exit_policy,
)
from libs.runtime.feature_engine import build_feature_row
from libs.runtime.intraday_monitor_signals import (
    evaluate_intraday_entry_signal,
    resolve_intraday_entry_policy,
)
from libs.runtime.monitor_memory_bias import (
    apply_monitor_memory_bias_to_exit_policy,
    apply_monitor_memory_bias_to_hold_controls,
    apply_monitor_memory_bias_to_entry_policy,
    summarize_monitor_memory_bias,
)
from libs.runtime.monitor_policy import (
    MonitorEntryPolicy,
    build_monitor_entry_policy_contract,
    summarize_monitor_policy_deltas,
)
from libs.runtime.market_hours import MarketHours
from libs.runtime.position_sizing import evaluate_position_size
from libs.runtime.strategy_horizon_feedback import build_exit_vs_strategy_intent
from libs.strategies.contracts import coerce_strategist_output

POST_EXIT_SHADOW_WATCH_MAX_SYMBOLS = 3
POST_EXIT_SHADOW_WATCH_WINDOW_SEC = 90 * 60


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _normalize_status(v: Any) -> str:
    return str(v or "").strip().upper()


def _memory_bias_observation_only(state: Dict[str, Any] | None = None) -> bool:
    if isinstance(state, dict):
        for key in ("memory_bias_observation_only", "commander_memory_bias_observation_only"):
            if state.get(key) not in (None, ""):
                return _is_trueish(state.get(key))
    for name in ("MEMORY_BIAS_OBSERVATION_ONLY", "COMMANDER_MEMORY_BIAS_OBSERVATION_ONLY"):
        raw = str(os.getenv(name, "") or "").strip()
        if raw:
            return _is_trueish(raw)
    return False


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _optional_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _monitor_runtime_dt_kst(
    state: Dict[str, Any],
    *,
    market_hours: MarketHours | None = None,
) -> datetime:
    mh = market_hours or MarketHours()
    tick_ts = _to_int(state.get("tick_ts"))
    if tick_ts > 0:
        return datetime.fromtimestamp(tick_ts, tz=timezone.utc).astimezone(mh.tz)
    for key in ("tick_ts_iso", "ts", "now_iso", "started_at"):
        text = str(state.get(key) or "").strip()
        if not text:
            continue
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=mh.tz)
            return dt.astimezone(mh.tz)
        except Exception:
            continue
    return datetime.now(tz=mh.tz)


def _monitor_runtime_clock_input_present(state: Dict[str, Any]) -> bool:
    if _to_int(state.get("tick_ts")) > 0:
        return True
    return any(str(state.get(key) or "").strip() for key in ("tick_ts_iso", "ts", "now_iso", "started_at"))


def _carry_calendar_context(state: Dict[str, Any]) -> Dict[str, Any]:
    if not _monitor_runtime_clock_input_present(state):
        return {
            "calendar_known": False,
            "date_kst": "",
            "weekday": None,
            "weekday_name": "",
            "weekend_carry": False,
            "holding_gap_days": 1,
            "reason": "runtime_clock_missing",
        }
    dt_kst = _monitor_runtime_dt_kst(state)
    weekday = int(dt_kst.weekday())
    weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekend_carry = weekday == 4
    return {
        "calendar_known": True,
        "date_kst": dt_kst.date().isoformat(),
        "weekday": weekday,
        "weekday_name": weekday_names[weekday] if 0 <= weekday < len(weekday_names) else "",
        "weekend_carry": bool(weekend_carry),
        "holding_gap_days": 3 if weekend_carry else 1,
        "reason": "friday_weekend_gap" if weekend_carry else "regular_overnight",
    }


def _ensure_entry_market_context_clock_fields(
    state: Dict[str, Any],
    *,
    market_hours: MarketHours | None = None,
) -> Dict[str, Any]:
    mh = market_hours or MarketHours()
    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    out = dict(market_context or {})
    existing_minutes = _optional_float(out.get("minutes_to_close"))
    has_reliable_runtime_clock = _monitor_runtime_clock_input_present(state)
    if existing_minutes is not None and not has_reliable_runtime_clock:
        state["market_context"] = out
        return out
    dt_kst = _monitor_runtime_dt_kst(state, market_hours=mh)
    minutes_to_close: float | None = None
    if mh.is_open(dt_kst):
        close_dt = dt_kst.replace(
            hour=mh.close_time.hour,
            minute=mh.close_time.minute,
            second=0,
            microsecond=0,
        )
        minutes_to_close = max(0.0, (close_dt - dt_kst).total_seconds() / 60.0)
    if minutes_to_close is None and existing_minutes is not None:
        state["market_context"] = out
        return out

    previous_source = str(out.get("market_clock_source") or "")
    if existing_minutes is not None and minutes_to_close is not None:
        drift = abs(float(existing_minutes) - float(minutes_to_close))
        if drift <= 1.0:
            out["minutes_to_close"] = float(existing_minutes)
            out.setdefault("market_clock_source", previous_source or "runtime_clock_verified")
            out.setdefault("market_clock_kst", dt_kst.isoformat())
            out["market_clock_verified_minutes_to_close"] = float(minutes_to_close)
            state["market_context"] = out
            return out
        out["market_clock_previous_minutes_to_close"] = float(existing_minutes)
        if previous_source:
            out["market_clock_previous_source"] = previous_source
        out["market_clock_source"] = "runtime_clock_override"
    else:
        out.setdefault("market_clock_source", "runtime_clock")
    out["minutes_to_close"] = minutes_to_close
    out["market_clock_kst"] = dt_kst.isoformat()
    state["market_context"] = out
    return out


def _resolve_monitor_memory_bias_payload(
    *,
    strategy_monitor_policy: Dict[str, Any],
    commander_context: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if (
        isinstance(strategy_monitor_policy.get("monitor_memory_bias"), dict)
        and strategy_monitor_policy.get("monitor_memory_bias")
    ):
        return dict(strategy_monitor_policy.get("monitor_memory_bias") or {})
    if isinstance(commander_context.get("monitor_memory_bias"), dict) and commander_context.get("monitor_memory_bias"):
        return dict(commander_context.get("monitor_memory_bias") or {})
    if isinstance(state.get("monitor_memory_bias"), dict):
        return dict(state.get("monitor_memory_bias") or {})
    return {}


def _resolve_commander_entry_control_for_monitor(
    *,
    commander_context: Dict[str, Any],
    strategy_monitor_policy: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    applied_policy = (
        dict(strategy_monitor_policy.get("applied_policy") or {})
        if isinstance(strategy_monitor_policy.get("applied_policy"), dict)
        else {}
    )
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    scanner_policy = (
        dict(commander_decision.get("scanner_policy") or {})
        if isinstance(commander_decision.get("scanner_policy"), dict)
        else {}
    )
    candidates = [
        commander_context.get("commander_entry_control"),
        commander_context.get("entry_control"),
        strategy_monitor_policy.get("commander_entry_control"),
        strategy_monitor_policy.get("entry_control"),
        applied_policy.get("commander_entry_control"),
        applied_policy.get("entry_control"),
        commander_decision.get("entry_control"),
        scanner_policy.get("entry_control"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    if scanner_policy.get("max_priority_rank") not in (None, ""):
        max_priority_rank = int(_clamp(_to_float(scanner_policy.get("max_priority_rank")), 1, 10))
        return {
            "schema_version": "commander_entry_control.v1",
            "source": "commander_decision.scanner_policy",
            "mode": "scanner_policy_limits",
            "max_priority_rank": int(max_priority_rank),
            "max_runner_ups": int(max(0, max_priority_rank - 1)),
            "allow_dynamic_entry_band": False,
        }
    return {}


def _resolve_entry_candidate_cascade_config(entry_control: Dict[str, Any]) -> Dict[str, Any]:
    raw_rank = entry_control.get("max_priority_rank") if isinstance(entry_control, dict) else None
    raw_runner_ups = entry_control.get("max_runner_ups") if isinstance(entry_control, dict) else None
    if raw_rank not in (None, ""):
        max_priority_rank = int(_clamp(_to_float(raw_rank), 1, 10))
    elif raw_runner_ups not in (None, ""):
        max_priority_rank = int(_clamp(_to_float(raw_runner_ups) + 1, 1, 10))
    else:
        max_priority_rank = 10
    max_runner_ups = int(max(0, max_priority_rank - 1))
    if raw_runner_ups not in (None, ""):
        max_runner_ups = int(_clamp(_to_float(raw_runner_ups), 0, max_runner_ups))
    cascade_enabled = (
        _is_trueish(entry_control.get("cascade_enabled"))
        if isinstance(entry_control, dict) and entry_control.get("cascade_enabled") not in (None, "")
        else max_runner_ups > 0
    )
    if not cascade_enabled:
        max_runner_ups = 0
    return {
        "max_priority_rank": int(max_priority_rank),
        "max_runner_ups": int(max_runner_ups),
        "cascade_enabled": bool(cascade_enabled and max_runner_ups > 0),
        "cascade_allowed_reasons": list((entry_control or {}).get("cascade_allowed_reasons") or []),
        "cascade_blocked_reasons": list((entry_control or {}).get("cascade_blocked_reasons") or []),
        "source": str((entry_control or {}).get("source") or "default"),
        "mode": str((entry_control or {}).get("mode") or "default"),
    }


def _resolve_monitor_skill_runner(state: Dict[str, Any]) -> tuple[Any, str]:
    runner = state.get("skill_runner")
    if runner is not None and hasattr(runner, "run"):
        return runner, "state.skill_runner"

    factory = state.get("skill_runner_factory")
    if callable(factory):
        try:
            try:
                built = factory(state)
            except TypeError:
                built = factory()
            if built is not None and hasattr(built, "run"):
                state["skill_runner"] = built
                return built, "state.skill_runner_factory"
        except Exception:
            return None, "runner_factory_error"

    auto_requested = _is_trueish(state.get("auto_skill_runner")) or _is_trueish(
        os.getenv("M22_AUTO_SKILL_RUNNER", "")
    )
    if not auto_requested:
        runtime_path = str(
            state.get("m13_tick_pipeline")
            or state.get("tick_pipeline")
            or state.get("runtime_path")
            or ""
        ).strip().lower()
        if runtime_path not in {"integrated_chain", "integrated", "chain"}:
            return None, "none"

    try:
        from libs.skills.runner import CompositeSkillRunner

        built = CompositeSkillRunner.from_env()
        state["skill_runner"] = built
        source = "auto.composite_skill_runner" if auto_requested else "integrated_chain_auto.composite_skill_runner"
        return built, source
    except Exception:
        source = "auto_runner_error" if auto_requested else "integrated_chain_auto_runner_error"
        return None, source


def _fresh_monitor_skill_runner() -> tuple[Any, str]:
    try:
        from libs.skills.runner import CompositeSkillRunner

        built = CompositeSkillRunner.from_env()
        return built, "fresh.composite_skill_runner"
    except Exception:
        return None, "fresh_runner_error"


def _run_monitor_minute_skill(*, runner: Any, run_id: str, symbol: str, timeframe_minutes: int) -> Dict[str, Any]:
    raw = runner.run(
        run_id=run_id,
        skill="market.minute_ohlcv",
        args={
            "symbol": symbol,
            "timeframe_minutes": max(1, int(timeframe_minutes or 1)),
            "adjusted_price": "1",
        },
    )
    rec = _monitor_skill_output_to_record(raw)
    return dict(rec) if isinstance(rec, dict) else {}


def _extract_monitor_minute_rows(rec: Dict[str, Any] | None) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    result = rec.get("result") if isinstance(rec, dict) and isinstance(rec.get("result"), dict) else {}
    data = result.get("data") if isinstance(result, dict) else None
    rows = data.get("rows") if isinstance(data, dict) and isinstance(data.get("rows"), list) else []
    normalized_rows = [dict(row) for row in rows if isinstance(row, dict)]
    return dict(result) if isinstance(result, dict) else {}, normalized_rows


def _recover_monitor_minute_rows_from_history(
    state: Dict[str, Any],
    *,
    symbol: str,
    now_epoch: int,
    timeframe_minutes: int,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sym = _norm_symbol(symbol)
    if not sym:
        return [], {}

    history_root = state.get("skill_results_history") if isinstance(state.get("skill_results_history"), dict) else {}
    minute_history = list(history_root.get("market.minute_ohlcv") or [])
    best_rows: List[Dict[str, Any]] = []
    best_meta: Dict[str, Any] = {}
    best_ts = 0
    for row in reversed(minute_history):
        if not isinstance(row, dict):
            continue
        if _norm_symbol(row.get("symbol")) != sym:
            continue
        rec = row.get("record") if isinstance(row.get("record"), dict) else {}
        _result, normalized_rows = _extract_monitor_minute_rows(rec)
        if not normalized_rows:
            continue
        latest_ts = _latest_row_ts(normalized_rows) or 0
        if latest_ts <= 0:
            continue
        stale_reason = _minute_snapshot_stale_reason(
            latest_candle_ts=latest_ts,
            now_epoch=int(now_epoch or 0),
            timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
        )
        age_minutes = _minute_snapshot_age_minutes(latest_candle_ts=latest_ts, now_epoch=int(now_epoch or 0))
        # Allow a recent cache fallback even if it is older than the strict live snapshot window.
        if stale_reason and (age_minutes is None or float(age_minutes) > 15.0):
            continue
        if latest_ts > best_ts:
            best_rows = list(normalized_rows)
            best_ts = latest_ts
            best_meta = {
                "latest_candle_ts": latest_ts,
                "minute_snapshot_age_minutes": age_minutes,
                "minute_snapshot_was_stale": bool(stale_reason),
            }
    return best_rows, best_meta


def _remember_monitor_minute_rows_in_persisted_cache(
    state: Dict[str, Any],
    *,
    symbol: str,
    rows: List[Dict[str, Any]],
    latest_candle_ts: Any,
    timeframe_minutes: int,
    now_epoch: int,
) -> None:
    sym = _norm_symbol(symbol)
    if not sym or not isinstance(rows, list) or not rows:
        return
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    cache_root = (
        dict(persisted.get("recent_minute_ohlcv_by_symbol") or {})
        if isinstance(persisted.get("recent_minute_ohlcv_by_symbol"), dict)
        else {}
    )
    cache_root[sym] = {
        "symbol": sym,
        "rows": [dict(row) for row in rows if isinstance(row, dict)],
        "latest_candle_ts": _latest_row_ts(rows) if latest_candle_ts in (None, "") else latest_candle_ts,
        "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
        "stored_epoch": int(now_epoch or 0),
    }
    if len(cache_root) > 50:
        ordered = sorted(
            cache_root.items(),
            key=lambda item: int(((item[1] or {}).get("stored_epoch") or 0)),
            reverse=True,
        )
        cache_root = {str(k): v for k, v in ordered[:50]}
    persisted["recent_minute_ohlcv_by_symbol"] = cache_root
    state["persisted_state"] = persisted


def _recover_monitor_minute_rows_from_persisted_cache(
    state: Dict[str, Any],
    *,
    symbol: str,
    now_epoch: int,
    timeframe_minutes: int,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sym = _norm_symbol(symbol)
    if not sym:
        return [], {}
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    cache_root = (
        dict(persisted.get("recent_minute_ohlcv_by_symbol") or {})
        if isinstance(persisted.get("recent_minute_ohlcv_by_symbol"), dict)
        else {}
    )
    row = cache_root.get(sym) if isinstance(cache_root.get(sym), dict) else {}
    rows = [dict(item) for item in list(row.get("rows") or []) if isinstance(item, dict)]
    if not rows:
        return [], {}
    latest_ts = _latest_row_ts(rows) or _latest_row_ts(row.get("rows")) or _latest_row_ts(rows)
    stale_reason = _minute_snapshot_stale_reason(
        latest_candle_ts=latest_ts,
        now_epoch=int(now_epoch or 0),
        timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
    )
    age_minutes = _minute_snapshot_age_minutes(latest_candle_ts=latest_ts, now_epoch=int(now_epoch or 0))
    if stale_reason and (age_minutes is None or float(age_minutes) > 15.0):
        return [], {}
    return rows, {
        "latest_candle_ts": latest_ts,
        "minute_snapshot_age_minutes": age_minutes,
        "minute_snapshot_was_stale": bool(stale_reason),
    }


def _monitor_skill_output_to_record(out: Any) -> Dict[str, Any]:
    if isinstance(out, dict) and isinstance(out.get("result"), dict):
        return dict(out)

    def _to_plain(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {k: _to_plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_to_plain(v) for v in value]
        return value

    action = str(getattr(out, "action", "") or "").strip().lower()
    if not action and isinstance(out, dict):
        action = str(out.get("action") or "").strip().lower()

    if action == "ready":
        data = getattr(out, "data", None)
        if data is None and isinstance(out, dict):
            data = out.get("data")
        return {"result": {"action": "ready", "data": _to_plain(data)}}

    meta = getattr(out, "meta", None)
    question = getattr(out, "question", None)
    if isinstance(out, dict):
        meta = out.get("meta", meta)
        question = out.get("question", question)
    rec: Dict[str, Any] = {"result": {"action": action or "error"}}
    if isinstance(meta, dict) and meta:
        rec["result"]["meta"] = dict(meta)
    if question:
        rec["result"]["question"] = str(question)
    return rec


def _latest_row_ts(rows: Any) -> int | None:
    if not isinstance(rows, list) or not rows:
        return None
    last = rows[-1]
    if not isinstance(last, dict):
        return None
    value = last.get("ts")
    try:
        return int(float(value))
    except Exception:
        return None


def _minute_snapshot_age_minutes(*, latest_candle_ts: Any, now_epoch: int) -> float | None:
    try:
        latest = int(float(latest_candle_ts))
    except Exception:
        return None
    if latest <= 0 or now_epoch <= 0:
        return None
    age_sec = max(0, int(now_epoch - latest))
    return round(float(age_sec) / 60.0, 3)


def _minute_snapshot_stale_reason(*, latest_candle_ts: Any, now_epoch: int, timeframe_minutes: int) -> str:
    try:
        latest = int(float(latest_candle_ts))
    except Exception:
        latest = 0
    tf_min = max(1, int(timeframe_minutes or 1))
    if latest <= 0:
        return "missing_latest_candle_ts"
    if now_epoch <= 0:
        return ""
    max_age_sec = max(180, tf_min * 60 * 3)
    age_sec = max(0, int(now_epoch - latest))
    if age_sec > max_age_sec:
        return "stale_snapshot_age_exceeded"
    return ""


def _monitor_policy_adjustment_inputs(frame: Dict[str, Any]) -> Dict[str, str]:
    return {
        "playbook": str(frame.get("playbook") or "").strip(),
        "monitor_guidance": str(frame.get("monitor_guidance") or "").strip(),
        "risk_tone": str(frame.get("risk_tone") or "").strip(),
        "trade_aggressiveness": str(frame.get("trade_aggressiveness") or "").strip(),
    }


def _build_monitor_effective_policy_trace(
    *,
    received_policy: Dict[str, Any],
    effective_policy: Dict[str, Any],
    frame: Dict[str, Any],
    received_policy_source: str,
) -> Dict[str, Any]:
    adjustment_inputs = _monitor_policy_adjustment_inputs(frame)
    deltas = summarize_monitor_policy_deltas(received_policy, effective_policy)
    changed_fields = [str((row or {}).get("field") or "") for row in deltas if str((row or {}).get("field") or "").strip()]
    applied_rules = [str(x or "").strip() for x in list(effective_policy.get("adjustments") or []) if str(x or "").strip()]
    frame_labels = [
        str(adjustment_inputs.get("playbook") or "").strip(),
        str(adjustment_inputs.get("monitor_guidance") or "").strip(),
        str(adjustment_inputs.get("risk_tone") or "").strip(),
        str(adjustment_inputs.get("trade_aggressiveness") or "").strip(),
    ]
    frame_labels = [x for x in frame_labels if x]
    if deltas:
        if frame_labels:
            summary = f"{' + '.join(frame_labels)} adjusted {', '.join(changed_fields[:4])}"
        else:
            summary = f"strategy frame adjusted {', '.join(changed_fields[:4])}"
        reasoning = (
            f"Monitor used an effective policy derived from the commander-confirmed baseline after "
            f"strategy-frame adjustment. Changed fields: {', '.join(changed_fields[:6])}."
        )
        effective_policy_source = "monitor_frame_adjusted"
        effective_policy_source_chain = [
            str(received_policy_source or "monitor_received_policy"),
            "strategy_frame_adjustment",
            "monitor_effective_policy",
        ]
    else:
        summary = "Monitor used the received policy without strategy-frame threshold changes."
        reasoning = "Monitor used the received baseline policy directly because strategy-frame adjustments did not change threshold fields."
        effective_policy_source = "monitor_received_policy"
        effective_policy_source_chain = [
            str(received_policy_source or "monitor_received_policy"),
            "monitor_effective_policy",
        ]
    return {
        "received_policy": dict(received_policy),
        "effective_policy": dict(effective_policy),
        "received_policy_source": str(received_policy_source or ""),
        "effective_policy_source": effective_policy_source,
        "effective_policy_source_chain": [str(x) for x in effective_policy_source_chain if str(x or "").strip()],
        "policy_adjustments": {
            "inputs": adjustment_inputs,
            "applied_rules": applied_rules,
            "changed_fields": changed_fields,
        },
        "policy_adjustment_summary": summary,
        "policy_adjustment_reasoning": reasoning,
        "effective_policy_deltas": deltas,
    }


def _ensure_monitor_minute_ohlcv_for_symbol(
    state: Dict[str, Any],
    *,
    symbol: str,
    timeframe_minutes: int,
    now_epoch: int = 0,
    prefer_fresh_runner: bool = False,
) -> Dict[str, Any]:
    """Hydrate monitor-only minute candles without touching scanner seed OHLCV.

    `ohlcv_by_symbol` remains scanner/feature seed storage. Entry evaluation reads
    only `minute_ohlcv_by_symbol` via `extract_minute_ohlcv_by_symbol(...)`.
    """
    sym = _norm_symbol(symbol)
    if not sym:
        return state

    existing_root = state.get("minute_ohlcv_by_symbol") if isinstance(state.get("minute_ohlcv_by_symbol"), dict) else {}
    existing_rows = existing_root.get(sym) if isinstance(existing_root.get(sym), list) else []
    existing_latest_candle_ts = _latest_row_ts(existing_rows)
    stale_reason = ""
    if existing_rows:
        stale_reason = _minute_snapshot_stale_reason(
            latest_candle_ts=existing_latest_candle_ts,
            now_epoch=int(now_epoch or 0),
            timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
        )
    if existing_rows and not stale_reason:
        _remember_monitor_minute_rows_in_persisted_cache(
            state,
            symbol=sym,
            rows=list(existing_rows),
            latest_candle_ts=existing_latest_candle_ts,
            timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
            now_epoch=int(now_epoch or 0),
        )
        state["monitor_minute_ohlcv_fetch"] = {
            "source": "state.minute_ohlcv_by_symbol",
            "symbol": sym,
            "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
            "row_count": int(len(existing_rows)),
            "latest_candle_ts": existing_latest_candle_ts,
            "minute_snapshot_age_minutes": _minute_snapshot_age_minutes(
                latest_candle_ts=existing_latest_candle_ts,
                now_epoch=int(now_epoch or 0),
            ),
            "minute_snapshot_was_stale": False,
            "minute_refetch_attempted": False,
            "minute_refetch_succeeded": False,
            "minute_refetch_reason": "",
            "minute_refetch_trigger_reason": "",
            "minute_refetch_failure_reason": "",
            "minute_refetch_produced_fresh_snapshot": False,
        }
        return state

    runner, runner_source = _resolve_monitor_skill_runner(state)
    refetch_trigger_reason = "missing_snapshot" if not existing_rows else stale_reason
    if prefer_fresh_runner:
        fresh_runner, fresh_runner_source = _fresh_monitor_skill_runner()
        if fresh_runner is not None and hasattr(fresh_runner, "run"):
            runner, runner_source = fresh_runner, fresh_runner_source
    if runner is None or not hasattr(runner, "run"):
        state["monitor_minute_ohlcv_fetch"] = {
            "source": "state.minute_ohlcv_by_symbol" if existing_rows else "none",
            "symbol": sym,
            "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
            "row_count": int(len(existing_rows)),
            "latest_candle_ts": existing_latest_candle_ts,
            "minute_snapshot_age_minutes": _minute_snapshot_age_minutes(
                latest_candle_ts=existing_latest_candle_ts,
                now_epoch=int(now_epoch or 0),
            ),
            "minute_snapshot_was_stale": bool(stale_reason),
            "minute_refetch_attempted": True,
            "minute_refetch_succeeded": False,
            "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
            "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
            "minute_refetch_failure_reason": "skill_runner_unavailable",
            "minute_refetch_failure_detail": str(runner_source or "none"),
            "minute_refetch_runner_source": str(runner_source or "none"),
            "minute_refetch_produced_fresh_snapshot": False,
        }
        return state

    run_id = str(state.get("run_id") or "monitor-minute-fetch")
    rec = _run_monitor_minute_skill(
        runner=runner,
        run_id=run_id,
        symbol=sym,
        timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
    )
    skill_results = dict(state.get("skill_results") or {}) if isinstance(state.get("skill_results"), dict) else {}
    skill_results["market.minute_ohlcv"] = rec
    skill_results_by_symbol = (
        dict(skill_results.get("market.minute_ohlcv_by_symbol") or {})
        if isinstance(skill_results.get("market.minute_ohlcv_by_symbol"), dict)
        else {}
    )
    skill_results_by_symbol[sym] = rec
    skill_results["market.minute_ohlcv_by_symbol"] = skill_results_by_symbol
    state["skill_results"] = skill_results
    skill_results_history = (
        dict(state.get("skill_results_history") or {})
        if isinstance(state.get("skill_results_history"), dict)
        else {}
    )
    minute_history = list(skill_results_history.get("market.minute_ohlcv") or [])
    minute_history.append(
        {
            "symbol": sym,
            "record": rec,
        }
    )
    skill_results_history["market.minute_ohlcv"] = minute_history[-20:]
    state["skill_results_history"] = skill_results_history

    result, normalized_rows = _extract_monitor_minute_rows(rec)
    primary_failure_reason = ""
    primary_failure_detail = ""
    runner_used_source = str(runner_source or "")
    fresh_runner_used = False
    if str(result.get("action") or "").strip().lower() != "ready" or not normalized_rows:
        primary_action = str(result.get("action") or "").strip().lower()
        if primary_action == "ready" and not normalized_rows:
            primary_failure_reason = "refetch_empty_rows"
            primary_failure_detail = "refetch_empty_rows"
        else:
            primary_failure_reason = str(result.get("action") or "refetch_not_ready")
            primary_failure_detail = str(result.get("question") or result.get("action") or "refetch_not_ready")
        fresh_runner, fresh_runner_source = _fresh_monitor_skill_runner()
        if fresh_runner is not None and hasattr(fresh_runner, "run") and fresh_runner is not runner:
            fresh_rec = _run_monitor_minute_skill(
                runner=fresh_runner,
                run_id=run_id,
                symbol=sym,
                timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
            )
            fresh_result, fresh_rows = _extract_monitor_minute_rows(fresh_rec)
            if str(fresh_result.get("action") or "").strip().lower() == "ready" and fresh_rows:
                rec = fresh_rec
                result = fresh_result
                normalized_rows = fresh_rows
                runner_used_source = str(fresh_runner_source or "fresh.composite_skill_runner")
                fresh_runner_used = True
            else:
                fresh_action = str(fresh_result.get("action") or "").strip().lower()
                if fresh_action == "ready" and not fresh_rows:
                    primary_failure_reason = "refetch_empty_rows"
                    primary_failure_detail = "refetch_empty_rows"
                else:
                    primary_failure_reason = str(fresh_result.get("action") or primary_failure_reason or "refetch_not_ready")
                    primary_failure_detail = str(
                        fresh_result.get("question")
                        or fresh_result.get("action")
                        or primary_failure_detail
                        or "refetch_not_ready"
                    )

    if fresh_runner_used:
        skill_results["market.minute_ohlcv"] = rec
        skill_results_by_symbol[sym] = rec
        skill_results["market.minute_ohlcv_by_symbol"] = skill_results_by_symbol
        state["skill_results"] = skill_results
        minute_history = list(skill_results_history.get("market.minute_ohlcv") or [])
        minute_history.append({"symbol": sym, "record": rec})
        skill_results_history["market.minute_ohlcv"] = minute_history[-20:]
        state["skill_results_history"] = skill_results_history

    if str(result.get("action") or "").strip().lower() != "ready":
        history_rows, history_meta = _recover_monitor_minute_rows_from_history(
            state,
            symbol=sym,
            now_epoch=int(now_epoch or 0),
            timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
        )
        cache_rows: List[Dict[str, Any]] = []
        cache_meta: Dict[str, Any] = {}
        if not history_rows:
            cache_rows, cache_meta = _recover_monitor_minute_rows_from_persisted_cache(
                state,
                symbol=sym,
                now_epoch=int(now_epoch or 0),
                timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
            )
        if history_rows:
            minute_root = dict(existing_root or {})
            minute_root[sym] = list(history_rows)
            state["minute_ohlcv_by_symbol"] = minute_root
            state["monitor_minute_ohlcv_fetch"] = {
                "source": "skill_results_history.minute_ohlcv",
                "symbol": sym,
                "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
                "row_count": int(len(history_rows)),
                "latest_candle_ts": history_meta.get("latest_candle_ts"),
                "minute_snapshot_age_minutes": history_meta.get("minute_snapshot_age_minutes"),
                "minute_snapshot_was_stale": bool(history_meta.get("minute_snapshot_was_stale")),
                "minute_refetch_attempted": True,
                "minute_refetch_succeeded": False,
                "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_failure_reason": primary_failure_reason or str(result.get("action") or "refetch_not_ready"),
                "minute_refetch_failure_detail": primary_failure_detail or str(result.get("question") or result.get("action") or "refetch_not_ready"),
                "minute_refetch_runner_source": runner_used_source,
                "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
                "minute_refetch_produced_fresh_snapshot": False,
                "minute_cache_fallback_used": True,
                "minute_cache_fallback_source": "skill_results_history.minute_ohlcv",
            }
            return state
        if cache_rows:
            minute_root = dict(existing_root or {})
            minute_root[sym] = list(cache_rows)
            state["minute_ohlcv_by_symbol"] = minute_root
            state["monitor_minute_ohlcv_fetch"] = {
                "source": "persisted_state.recent_minute_ohlcv_by_symbol",
                "symbol": sym,
                "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
                "row_count": int(len(cache_rows)),
                "latest_candle_ts": cache_meta.get("latest_candle_ts"),
                "minute_snapshot_age_minutes": cache_meta.get("minute_snapshot_age_minutes"),
                "minute_snapshot_was_stale": bool(cache_meta.get("minute_snapshot_was_stale")),
                "minute_refetch_attempted": True,
                "minute_refetch_succeeded": False,
                "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_failure_reason": primary_failure_reason or str(result.get("action") or "refetch_not_ready"),
                "minute_refetch_failure_detail": primary_failure_detail or str(result.get("question") or result.get("action") or "refetch_not_ready"),
                "minute_refetch_runner_source": runner_used_source,
                "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
                "minute_refetch_produced_fresh_snapshot": False,
                "minute_cache_fallback_used": True,
                "minute_cache_fallback_source": "persisted_state.recent_minute_ohlcv_by_symbol",
            }
            return state
        state["monitor_minute_ohlcv_fetch"] = {
            "source": "state.minute_ohlcv_by_symbol" if existing_rows else "none",
            "symbol": sym,
            "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
            "row_count": int(len(existing_rows)),
            "latest_candle_ts": existing_latest_candle_ts,
            "minute_snapshot_age_minutes": _minute_snapshot_age_minutes(
                latest_candle_ts=existing_latest_candle_ts,
                now_epoch=int(now_epoch or 0),
            ),
            "minute_snapshot_was_stale": bool(stale_reason),
            "minute_refetch_attempted": True,
            "minute_refetch_succeeded": False,
            "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
            "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
            "minute_refetch_failure_reason": primary_failure_reason or str(result.get("action") or "refetch_not_ready"),
            "minute_refetch_failure_detail": primary_failure_detail or str(result.get("question") or result.get("action") or "refetch_not_ready"),
            "minute_refetch_runner_source": runner_used_source,
            "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
            "minute_refetch_produced_fresh_snapshot": False,
            "minute_cache_fallback_used": False,
            "minute_cache_fallback_source": "",
        }
        return state

    if not normalized_rows:
        history_rows, history_meta = _recover_monitor_minute_rows_from_history(
            state,
            symbol=sym,
            now_epoch=int(now_epoch or 0),
            timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
        )
        cache_rows: List[Dict[str, Any]] = []
        cache_meta: Dict[str, Any] = {}
        if not history_rows:
            cache_rows, cache_meta = _recover_monitor_minute_rows_from_persisted_cache(
                state,
                symbol=sym,
                now_epoch=int(now_epoch or 0),
                timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
            )
        if history_rows:
            minute_root = dict(existing_root or {})
            minute_root[sym] = list(history_rows)
            state["minute_ohlcv_by_symbol"] = minute_root
            state["monitor_minute_ohlcv_fetch"] = {
                "source": "skill_results_history.minute_ohlcv",
                "symbol": sym,
                "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
                "row_count": int(len(history_rows)),
                "latest_candle_ts": history_meta.get("latest_candle_ts"),
                "minute_snapshot_age_minutes": history_meta.get("minute_snapshot_age_minutes"),
                "minute_snapshot_was_stale": bool(history_meta.get("minute_snapshot_was_stale")),
                "minute_refetch_attempted": True,
                "minute_refetch_succeeded": False,
                "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_failure_reason": "refetch_empty_rows",
                "minute_refetch_failure_detail": "refetch_empty_rows",
                "minute_refetch_runner_source": runner_used_source,
                "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
                "minute_refetch_produced_fresh_snapshot": False,
                "minute_cache_fallback_used": True,
                "minute_cache_fallback_source": "skill_results_history.minute_ohlcv",
            }
            return state
        if cache_rows:
            minute_root = dict(existing_root or {})
            minute_root[sym] = list(cache_rows)
            state["minute_ohlcv_by_symbol"] = minute_root
            state["monitor_minute_ohlcv_fetch"] = {
                "source": "persisted_state.recent_minute_ohlcv_by_symbol",
                "symbol": sym,
                "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
                "row_count": int(len(cache_rows)),
                "latest_candle_ts": cache_meta.get("latest_candle_ts"),
                "minute_snapshot_age_minutes": cache_meta.get("minute_snapshot_age_minutes"),
                "minute_snapshot_was_stale": bool(cache_meta.get("minute_snapshot_was_stale")),
                "minute_refetch_attempted": True,
                "minute_refetch_succeeded": False,
                "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
                "minute_refetch_failure_reason": "refetch_empty_rows",
                "minute_refetch_failure_detail": "refetch_empty_rows",
                "minute_refetch_runner_source": runner_used_source,
                "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
                "minute_refetch_produced_fresh_snapshot": False,
                "minute_cache_fallback_used": True,
                "minute_cache_fallback_source": "persisted_state.recent_minute_ohlcv_by_symbol",
            }
            return state
        state["monitor_minute_ohlcv_fetch"] = {
            "source": "state.minute_ohlcv_by_symbol" if existing_rows else "none",
            "symbol": sym,
            "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
            "row_count": int(len(existing_rows)),
            "latest_candle_ts": existing_latest_candle_ts,
            "minute_snapshot_age_minutes": _minute_snapshot_age_minutes(
                latest_candle_ts=existing_latest_candle_ts,
                now_epoch=int(now_epoch or 0),
            ),
            "minute_snapshot_was_stale": bool(stale_reason),
            "minute_refetch_attempted": True,
            "minute_refetch_succeeded": False,
            "minute_refetch_reason": refetch_trigger_reason or "missing_snapshot",
            "minute_refetch_trigger_reason": refetch_trigger_reason or "missing_snapshot",
            "minute_refetch_failure_reason": "refetch_empty_rows",
            "minute_refetch_failure_detail": "refetch_empty_rows",
            "minute_refetch_runner_source": runner_used_source,
            "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
            "minute_refetch_produced_fresh_snapshot": False,
            "minute_cache_fallback_used": False,
            "minute_cache_fallback_source": "",
        }
        return state

    minute_root = dict(existing_root or {})
    minute_root[sym] = normalized_rows
    state["minute_ohlcv_by_symbol"] = minute_root
    latest_candle_ts = _latest_row_ts(normalized_rows)
    _remember_monitor_minute_rows_in_persisted_cache(
        state,
        symbol=sym,
        rows=list(normalized_rows),
        latest_candle_ts=latest_candle_ts,
        timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
        now_epoch=int(now_epoch or 0),
    )
    final_stale_reason = _minute_snapshot_stale_reason(
        latest_candle_ts=latest_candle_ts,
        now_epoch=int(now_epoch or 0),
        timeframe_minutes=int(max(1, int(timeframe_minutes or 1))),
    )
    state["monitor_minute_ohlcv_fetch"] = {
        "source": str(runner_source or ""),
        "symbol": sym,
        "timeframe_minutes": int(max(1, int(timeframe_minutes or 1))),
        "row_count": int(len(normalized_rows)),
        "latest_candle_ts": latest_candle_ts,
        "minute_snapshot_age_minutes": _minute_snapshot_age_minutes(
            latest_candle_ts=latest_candle_ts,
            now_epoch=int(now_epoch or 0),
        ),
        "minute_snapshot_was_stale": bool(final_stale_reason),
        "minute_refetch_attempted": True,
        "minute_refetch_succeeded": True,
        "minute_refetch_reason": refetch_trigger_reason,
        "minute_refetch_trigger_reason": refetch_trigger_reason,
        "minute_refetch_failure_reason": "",
        "minute_refetch_failure_detail": "",
        "minute_refetch_runner_source": runner_used_source,
        "minute_refetch_fresh_runner_used": bool(fresh_runner_used),
        "minute_refetch_produced_fresh_snapshot": not bool(final_stale_reason),
        "minute_cache_fallback_used": False,
        "minute_cache_fallback_source": "",
        "previous_latest_candle_ts": existing_latest_candle_ts,
    }
    return state


def _active_post_exit_shadow_watches(state: Dict[str, Any], *, now_epoch: int) -> Dict[str, Dict[str, Any]]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw = persisted.get("post_exit_shadow_watchlist")
    rows = list(raw.values()) if isinstance(raw, dict) else list(raw) if isinstance(raw, list) else []
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _norm_symbol(row.get("symbol"))
        if not symbol:
            continue
        exit_epoch = _to_int(row.get("exit_epoch") or row.get("sold_epoch") or row.get("ts"))
        if exit_epoch <= 0:
            continue
        expires_epoch = _to_int(row.get("expires_epoch")) or int(exit_epoch + POST_EXIT_SHADOW_WATCH_WINDOW_SEC)
        if now_epoch > 0 and expires_epoch > 0 and now_epoch > expires_epoch:
            continue
        normalized = dict(row)
        normalized["symbol"] = symbol
        normalized["exit_epoch"] = int(exit_epoch)
        normalized["expires_epoch"] = int(expires_epoch)
        normalized["observability_only"] = True
        out[symbol] = normalized
    return out


def _refresh_post_exit_shadow_watchlist_minute_rows(state: Dict[str, Any], *, now_epoch: int) -> Dict[str, Any]:
    watches = _active_post_exit_shadow_watches(state, now_epoch=now_epoch)
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    if not watches:
        if isinstance(persisted.get("post_exit_shadow_watchlist"), (dict, list)):
            persisted.pop("post_exit_shadow_watchlist", None)
            state["persisted_state"] = persisted
        state["post_exit_shadow_watchlist_refresh"] = {
            "enabled": True,
            "observability_only": True,
            "watch_count": 0,
            "refreshed_symbols": [],
            "reason": "no_active_watches",
        }
        return state

    refreshed_symbols: list[str] = []
    refresh_rows: list[Dict[str, Any]] = []
    for symbol, watch in sorted(watches.items(), key=lambda item: int((item[1] or {}).get("exit_epoch") or 0), reverse=True):
        if len(refreshed_symbols) >= POST_EXIT_SHADOW_WATCH_MAX_SYMBOLS:
            break
        state = _ensure_monitor_minute_ohlcv_for_symbol(
            state,
            symbol=symbol,
            timeframe_minutes=1,
            now_epoch=int(now_epoch or 0),
            prefer_fresh_runner=False,
        )
        minute_rows_by_symbol, minute_meta = extract_minute_ohlcv_by_symbol(state)
        rows = minute_rows_by_symbol.get(symbol) if isinstance(minute_rows_by_symbol, dict) else []
        latest_ts = _latest_row_ts(rows) if isinstance(rows, list) else None
        fetch_meta = (
            dict(state.get("monitor_minute_ohlcv_fetch") or {})
            if isinstance(state.get("monitor_minute_ohlcv_fetch"), dict)
            else {}
        )
        updated_watch = dict(watch)
        updated_watch["last_refresh_epoch"] = int(now_epoch or 0)
        updated_watch["latest_candle_ts"] = latest_ts
        updated_watch["minute_source"] = str((minute_meta or {}).get("source") or fetch_meta.get("source") or "")
        updated_watch["post_exit_rows_available"] = bool(latest_ts and latest_ts >= _to_int(watch.get("exit_epoch")))
        watches[symbol] = updated_watch
        refreshed_symbols.append(symbol)
        refresh_rows.append(
            {
                "symbol": symbol,
                "latest_candle_ts": latest_ts,
                "row_count": len(rows) if isinstance(rows, list) else 0,
                "minute_refetch_attempted": bool(fetch_meta.get("minute_refetch_attempted")),
                "minute_refetch_succeeded": bool(fetch_meta.get("minute_refetch_succeeded")),
                "minute_refetch_reason": str(fetch_meta.get("minute_refetch_reason") or ""),
                "post_exit_rows_available": bool(updated_watch.get("post_exit_rows_available")),
            }
        )

    persisted["post_exit_shadow_watchlist"] = watches
    state["persisted_state"] = persisted
    state["post_exit_shadow_watchlist_refresh"] = {
        "enabled": True,
        "observability_only": True,
        "watch_count": len(watches),
        "refreshed_symbols": refreshed_symbols,
        "rows": refresh_rows,
        "reason": "refreshed_active_watches" if refreshed_symbols else "no_symbols_refreshed",
    }
    return state


def _resolve_min_hold_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    raw = (
        (((applied_policy.get("monitor") or {}).get("hold") or {}).get("min_hold_seconds"))
        if isinstance((applied_policy.get("monitor") or {}).get("hold"), dict)
        else None
    )
    if raw is None and isinstance(policy, dict):
        raw = (
            (((policy.get("monitor") or {}).get("hold") or {}).get("min_hold_seconds"))
            if isinstance((policy.get("monitor") or {}).get("hold"), dict)
            else None
        )
    if raw is None and isinstance(policy, dict):
        raw = policy.get("min_hold_seconds")
    if raw is None:
        raw = 600
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 600


def _resolve_sell_cooldown_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    raw = (
        (((applied_policy.get("execution") or {}).get("cooldowns") or {}).get("sell_sec"))
        if isinstance((applied_policy.get("execution") or {}).get("cooldowns"), dict)
        else None
    )
    if raw is None and isinstance(policy, dict):
        raw = (
            (((policy.get("execution") or {}).get("cooldowns") or {}).get("sell_sec"))
            if isinstance((policy.get("execution") or {}).get("cooldowns"), dict)
            else None
        )
    if raw is None and isinstance(policy, dict):
        raw = policy.get("sell_cooldown_sec")
    if raw is None and isinstance(policy, dict):
        raw = policy.get("sell_cooldown_seconds")
    if raw in (None, ""):
        raw = 300
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 300


def _resolve_exit_confirm_ticks(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    raw = (
        (((applied_policy.get("monitor") or {}).get("exit") or {}).get("confirm_ticks"))
        if isinstance((applied_policy.get("monitor") or {}).get("exit"), dict)
        else None
    )
    if raw is None and isinstance(policy, dict):
        raw = (
            (((policy.get("monitor") or {}).get("exit") or {}).get("confirm_ticks"))
            if isinstance((policy.get("monitor") or {}).get("exit"), dict)
            else None
        )
    if raw is None and isinstance(policy, dict):
        raw = policy.get("exit_confirm_ticks")
    if raw is None:
        raw = 2
    try:
        return max(1, int(float(raw)))
    except Exception:
        return 2


def _resolve_use_exit_policy(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_exit = (
        (((applied_policy.get("monitor") or {}).get("exit") or {}).get("enabled"))
        if isinstance((applied_policy.get("monitor") or {}).get("exit"), dict)
        else None
    )
    if applied_exit is not None:
        return _is_trueish(applied_exit)
    if state.get("use_exit_policy") is not None:
        return _is_trueish(state.get("use_exit_policy"))
    if isinstance(policy, dict) and policy.get("use_exit_policy") is not None:
        return _is_trueish(policy.get("use_exit_policy"))
    raw_env = str(os.getenv("USE_EXIT_POLICY", "") or "").strip()
    if raw_env:
        return _is_trueish(raw_env)
    return True


def _resolve_post_exit_cooldown_sec(state: Dict[str, Any], policy: Dict[str, Any], monitor_policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    raw = (
        (((applied_policy.get("execution") or {}).get("cooldowns") or {}).get("post_exit_sec"))
        if isinstance((applied_policy.get("execution") or {}).get("cooldowns"), dict)
        else None
    )
    if raw in (None, ""):
        raw = state.get("post_exit_cooldown_sec")
    if raw in (None, "") and isinstance(monitor_policy, dict):
        raw = monitor_policy.get("post_exit_cooldown_sec")
    if raw in (None, "") and isinstance(policy, dict):
        raw = (
            (((policy.get("execution") or {}).get("cooldowns") or {}).get("post_exit_sec"))
            if isinstance((policy.get("execution") or {}).get("cooldowns"), dict)
            else None
        )
    if raw in (None, "") and isinstance(policy, dict):
        raw = policy.get("post_exit_cooldown_sec")
    if raw in (None, ""):
        raw = 180
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 180


def _resolve_max_positions(state: Dict[str, Any], policy: Dict[str, Any] | None = None) -> int:
    for value in (
        ((state.get("risk_context") or {}).get("max_positions") if isinstance(state.get("risk_context"), dict) else None),
        ((state.get("risk") or {}).get("max_positions") if isinstance(state.get("risk"), dict) else None),
        ((policy or {}).get("risk_max_positions") if isinstance(policy, dict) else None),
        os.getenv("RISK_MAX_POSITIONS"),
    ):
        try:
            if value not in (None, ""):
                return max(1, int(float(value)))
        except Exception:
            continue
    return 1


def _pending_order_symbols_from_account_orders(state: Dict[str, Any], *, side: str = "") -> set[str]:
    try:
        rows, _meta = extract_account_orders_rows(state)
    except Exception:
        return set()
    side_filter = str(side or "").strip().upper()
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not account_order_is_pending(row):
            continue
        if side_filter and account_order_side(row) != side_filter:
            continue
        symbol = _norm_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
        if not symbol:
            continue
        out.add(symbol)
    return out


def _pending_buy_symbols_from_account_orders(state: Dict[str, Any]) -> set[str]:
    return _pending_order_symbols_from_account_orders(state, side="BUY")


def _features_pending_order_count(features: Dict[str, Any]) -> int:
    if not isinstance(features, dict):
        return 0
    if not bool(features.get("skill_open_orders_pending_only")):
        return 0
    return max(0, _to_int(features.get("skill_open_orders")))


def _resolve_block_buy_when_open_position(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
) -> bool:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_entry = (applied_policy.get("monitor") or {}).get("entry") if isinstance((applied_policy.get("monitor") or {}), dict) else {}
    if isinstance(applied_entry, dict) and applied_entry.get("block_buy_when_open_position") is not None:
        return _is_trueish(applied_entry.get("block_buy_when_open_position"))
    if state.get("monitor_block_buy_when_open_position") is not None:
        return _is_trueish(state.get("monitor_block_buy_when_open_position"))
    if isinstance(monitor_policy, dict) and monitor_policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(monitor_policy.get("block_buy_when_open_position"))
    if isinstance(policy, dict) and policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(policy.get("block_buy_when_open_position"))
    raw_env = str(os.getenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "") or "").strip()
    if raw_env:
        return _is_trueish(raw_env)
    return True


def _resolve_entry_closeout_window_guard(
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    exit_policy = _resolve_exit_policy_config(state, policy)
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_entry = (
        ((applied_policy.get("monitor") or {}).get("entry") or {})
        if isinstance((applied_policy.get("monitor") or {}).get("entry"), dict)
        else {}
    )
    policy_entry = (
        ((policy.get("monitor") or {}).get("entry") or {})
        if isinstance((policy.get("monitor") or {}).get("entry"), dict)
        else {}
    )
    market_ctx = _ensure_entry_market_context_clock_fields(state)
    minutes_to_close = _optional_float(market_ctx.get("minutes_to_close"))
    use_eod_flat = bool(exit_policy.get("use_eod_flat"))
    cutoff_min = int(_to_float(exit_policy.get("eod_flat_cutoff_min") or 10))
    buy_cutoff_raw = (
        applied_entry.get("buy_closeout_cutoff_min")
        if applied_entry.get("buy_closeout_cutoff_min") not in (None, "")
        else policy_entry.get("buy_closeout_cutoff_min")
    )
    buy_cutoff_min = int(_optional_float(buy_cutoff_raw) or max(15.0, float(cutoff_min)))
    if buy_cutoff_min <= 0:
        buy_cutoff_min = max(15, int(cutoff_min))
    buy_cutoff_min = max(int(cutoff_min), int(buy_cutoff_min))
    active = bool(
        use_eod_flat
        and minutes_to_close is not None
        and minutes_to_close >= 0.0
        and minutes_to_close <= float(buy_cutoff_min)
    )
    return {
        "active": active,
        "minutes_to_close": minutes_to_close,
        "cutoff_min": int(cutoff_min),
        "buy_cutoff_min": int(buy_cutoff_min),
        "use_eod_flat": bool(use_eod_flat),
        "reason": "buy_blocked_closeout_window" if active else "",
    }


def _first_mapping(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _config_float(config: Dict[str, Any], key: str, env_key: str, default: float) -> float:
    if isinstance(config, dict) and config.get(key) not in (None, ""):
        return _to_float(config.get(key))
    raw = str(os.getenv(env_key, "") or "").strip()
    if raw:
        return _to_float(raw, default)
    return float(default)


def _config_bool(config: Dict[str, Any], key: str, env_key: str, default: bool) -> bool:
    if isinstance(config, dict) and config.get(key) not in (None, ""):
        return _is_trueish(config.get(key))
    raw = str(os.getenv(env_key, "") or "").strip()
    if raw:
        return _is_trueish(raw)
    return bool(default)


def _resolve_entry_cost_filter_config(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    strategy_monitor_policy: Dict[str, Any],
    entry_policy_input: Dict[str, Any],
    commander_entry_control: Dict[str, Any],
) -> Dict[str, Any]:
    policy_monitor = policy.get("monitor_policy") if isinstance(policy.get("monitor_policy"), dict) else {}
    config = _first_mapping(
        state.get("entry_cost_filter"),
        state.get("cost_filter"),
        commander_entry_control.get("cost_filter") if isinstance(commander_entry_control, dict) else {},
        entry_policy_input.get("cost_filter") if isinstance(entry_policy_input, dict) else {},
        strategy_monitor_policy.get("entry_cost_filter") if isinstance(strategy_monitor_policy, dict) else {},
        monitor_policy.get("entry_cost_filter") if isinstance(monitor_policy, dict) else {},
        policy_monitor.get("entry_cost_filter") if isinstance(policy_monitor, dict) else {},
        policy.get("entry_cost_filter") if isinstance(policy, dict) else {},
    )
    return {
        "schema_version": "entry_cost_filter.v1",
        "enabled": _config_bool(config, "enabled", "MONITOR_ENTRY_COST_FILTER_ENABLED", True),
        "buy_fee_rate": _config_float(config, "buy_fee_rate", "MONITOR_ENTRY_BUY_FEE_RATE", 0.00015),
        "sell_fee_rate": _config_float(config, "sell_fee_rate", "MONITOR_ENTRY_SELL_FEE_RATE", 0.00015),
        "sell_tax_rate": _config_float(config, "sell_tax_rate", "MONITOR_ENTRY_SELL_TAX_RATE", 0.0018),
        "min_buy_fee": _config_float(config, "min_buy_fee", "MONITOR_ENTRY_MIN_BUY_FEE", 0.0),
        "min_sell_fee": _config_float(config, "min_sell_fee", "MONITOR_ENTRY_MIN_SELL_FEE", 0.0),
        "max_cost_drag_pct": _config_float(config, "max_cost_drag_pct", "MONITOR_ENTRY_MAX_COST_DRAG_PCT", 0.006),
        "round_trip_cost_floor_pct": _config_float(
            config,
            "round_trip_cost_floor_pct",
            "MONITOR_ENTRY_ROUND_TRIP_COST_FLOOR_PCT",
            0.009,
        ),
        "min_net_profit_buffer_pct": _config_float(
            config,
            "min_net_profit_buffer_pct",
            "MONITOR_ENTRY_MIN_NET_PROFIT_BUFFER_PCT",
            0.003,
        ),
        "min_cost_adjusted_edge_pct": _config_float(
            config,
            "min_cost_adjusted_edge_pct",
            "MONITOR_ENTRY_MIN_COST_ADJUSTED_EDGE_PCT",
            0.001,
        ),
        "edge_scale_pct": _config_float(config, "edge_scale_pct", "MONITOR_ENTRY_EDGE_SCALE_PCT", 0.035),
        "quality_proxy_max_edge_pct": _config_float(
            config,
            "quality_proxy_max_edge_pct",
            "MONITOR_ENTRY_QUALITY_PROXY_MAX_EDGE_PCT",
            0.012,
        ),
        "require_directional_edge_evidence": _config_bool(
            config,
            "require_directional_edge_evidence",
            "MONITOR_ENTRY_REQUIRE_DIRECTIONAL_EDGE_EVIDENCE",
            True,
        ),
        "allow_volatility_proxy_edge": _config_bool(
            config,
            "allow_volatility_proxy_edge",
            "MONITOR_ENTRY_ALLOW_VOLATILITY_PROXY_EDGE",
            False,
        ),
        "allow_quality_proxy_edge": _config_bool(
            config,
            "allow_quality_proxy_edge",
            "MONITOR_ENTRY_ALLOW_QUALITY_PROXY_EDGE",
            False,
        ),
        "allow_triggered_signal_proxy_edge": _config_bool(
            config,
            "allow_triggered_signal_proxy_edge",
            "MONITOR_ENTRY_ALLOW_TRIGGERED_SIGNAL_PROXY_EDGE",
            True,
        ),
        "triggered_proxy_confidence_tolerance": _config_float(
            config,
            "triggered_proxy_confidence_tolerance",
            "MONITOR_ENTRY_TRIGGERED_PROXY_CONFIDENCE_TOLERANCE",
            0.0,
        ),
        "proxy_edge_haircut": _config_float(
            config,
            "proxy_edge_haircut",
            "MONITOR_ENTRY_PROXY_EDGE_HAIRCUT",
            0.35,
        ),
        "min_proxy_quality_score": _config_float(
            config,
            "min_proxy_quality_score",
            "MONITOR_ENTRY_MIN_PROXY_QUALITY_SCORE",
            0.80,
        ),
        "min_estimated_gross_edge_pct": _config_float(
            config,
            "min_estimated_gross_edge_pct",
            "MONITOR_ENTRY_MIN_ESTIMATED_GROSS_EDGE_PCT",
            0.0,
        ),
    }


def _evaluate_entry_cost_filter(
    *,
    entry_info: Dict[str, Any],
    selected: Dict[str, Any],
    qty: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    enabled = bool(config.get("enabled"))
    metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
    scores = entry_info.get("condition_scores") if isinstance(entry_info.get("condition_scores"), dict) else {}
    price = _to_float(selected.get("price") or metrics.get("current_price") or metrics.get("price"))
    quantity = max(0, int(qty))
    notional = float(price * quantity) if price > 0.0 and quantity > 0 else 0.0
    raw_quality = scores.get("entry_quality_score")
    if raw_quality in (None, ""):
        raw_quality = metrics.get("entry_quality_score")
    quality_available = raw_quality not in (None, "")
    quality_score = _clamp(_to_float(raw_quality), 0.0, 1.0) if quality_available else 0.0

    buy_fee = max(float(notional) * _to_float(config.get("buy_fee_rate")), _to_float(config.get("min_buy_fee"))) if notional > 0.0 else 0.0
    sell_fee = max(float(notional) * _to_float(config.get("sell_fee_rate")), _to_float(config.get("min_sell_fee"))) if notional > 0.0 else 0.0
    sell_tax = float(notional) * _to_float(config.get("sell_tax_rate")) if notional > 0.0 else 0.0
    total_cost = float(buy_fee + sell_fee + sell_tax)
    cost_drag_pct = float(total_cost / notional) if notional > 0.0 else None
    round_trip_cost_floor_pct = _to_float(config.get("round_trip_cost_floor_pct"))
    effective_cost_drag_pct = (
        max(float(cost_drag_pct), float(round_trip_cost_floor_pct))
        if cost_drag_pct is not None
        else float(round_trip_cost_floor_pct)
        if round_trip_cost_floor_pct > 0.0
        else None
    )

    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}

    def _as_ratio(v: Any) -> float:
        x = _to_float(v)
        if x <= 0.0:
            return 0.0
        if x > 1.0:
            x = x / 100.0
        return float(x)

    def _ratio_from_price(v: Any) -> float:
        target = _to_float(v)
        if price <= 0.0 or target <= price:
            return 0.0
        return float((target / price) - 1.0)

    directional_candidates: list[tuple[str, float]] = []
    proxy_candidates: list[tuple[str, float]] = []
    directional_ratio_keys = (
        "expected_gross_edge_pct",
        "expected_move_pct",
        "target_move_pct",
        "target_profit_pct",
        "take_profit_pct",
    )
    proxy_ratio_keys = (
        "recent_realized_move_pct",
        "recent_range_pct",
        "intraday_range_pct",
    )
    directional_price_keys = (
        "target_price",
        "resistance_price",
        "target_resistance_price",
        "upper_resistance_price",
    )
    for source_name, source in (("selected", selected), ("metrics", metrics), ("features", features)):
        if not isinstance(source, dict):
            continue
        for key in directional_ratio_keys:
            ratio = _as_ratio(source.get(key))
            if ratio > 0.0:
                directional_candidates.append((f"{source_name}.{key}", ratio))
        for key in directional_price_keys:
            ratio = _ratio_from_price(source.get(key))
            if ratio > 0.0:
                directional_candidates.append((f"{source_name}.{key}", ratio))
        for key in proxy_ratio_keys:
            ratio = _as_ratio(source.get(key))
            if ratio > 0.0:
                proxy_candidates.append((f"{source_name}.{key}", ratio))

    atr = _to_float(features.get("engine_atr14") or features.get("atr14") or metrics.get("atr14"))
    if atr > 0.0 and price > 0.0:
        proxy_candidates.append(("features.atr14_ratio", float(atr / price)))
    volatility_ratio = _as_ratio(features.get("engine_volatility20") or features.get("volatility20"))
    if volatility_ratio > 0.0:
        proxy_candidates.append(("features.volatility20", volatility_ratio))

    quality_proxy_raw = (
        max(0.0, quality_score - 0.50) * _to_float(config.get("edge_scale_pct"))
        if quality_available
        else 0.0
    )
    quality_proxy_cap = _to_float(config.get("quality_proxy_max_edge_pct"))
    quality_proxy_edge_pct = (
        min(float(quality_proxy_raw), float(quality_proxy_cap))
        if quality_proxy_cap > 0.0
        else float(quality_proxy_raw)
    )
    quality_modifier = float(0.50 + (0.50 * quality_score)) if quality_available else 0.0
    min_estimated_gross_edge_pct = _to_float(config.get("min_estimated_gross_edge_pct"))
    require_directional_edge_evidence = bool(config.get("require_directional_edge_evidence"))
    allow_volatility_proxy_edge = bool(config.get("allow_volatility_proxy_edge"))
    allow_quality_proxy_edge = bool(config.get("allow_quality_proxy_edge"))
    allow_triggered_signal_proxy_edge = bool(config.get("allow_triggered_signal_proxy_edge"))
    proxy_edge_haircut = _clamp(_to_float(config.get("proxy_edge_haircut")), 0.0, 1.0)
    min_proxy_quality_score = _clamp(_to_float(config.get("min_proxy_quality_score")), 0.0, 1.0)
    confidence_score = _to_float(scores.get("confidence_score") if scores.get("confidence_score") not in (None, "") else metrics.get("confidence_score"))
    confidence_threshold = _to_float(
        scores.get("confidence_threshold")
        if scores.get("confidence_threshold") not in (None, "")
        else metrics.get("confidence_threshold")
    )
    confidence_tolerance = max(0.0, _to_float(config.get("triggered_proxy_confidence_tolerance")))
    estimated_gross_edge_source = ""
    edge_evidence_type = ""
    directional_candidates = [(name, value) for name, value in directional_candidates if value > 0.0]
    proxy_candidates = [(name, value) for name, value in proxy_candidates if value > 0.0]
    proxy_quality_ok = bool((not quality_available) or quality_score >= min_proxy_quality_score)
    confidence_gate_ok = bool(
        confidence_threshold <= 0.0
        or (
            confidence_score > 0.0
            and confidence_score + confidence_tolerance >= confidence_threshold
        )
    )
    triggered_signal_proxy_allowed = bool(
        allow_triggered_signal_proxy_edge
        and bool(entry_info.get("triggered"))
        and confidence_gate_ok
        and proxy_candidates
        and proxy_quality_ok
    )
    effective_allow_volatility_proxy_edge = bool(allow_volatility_proxy_edge or triggered_signal_proxy_allowed)
    effective_require_directional_edge_evidence = bool(
        require_directional_edge_evidence and not triggered_signal_proxy_allowed
    )
    if directional_candidates and quality_available:
        candidate_name, candidate_value = min(directional_candidates, key=lambda row: float(row[1]))
        estimated_gross_edge_pct = max(
            float(min_estimated_gross_edge_pct),
            float(candidate_value) * float(quality_modifier),
        )
        estimated_gross_edge_source = f"{candidate_name}*quality_modifier"
        edge_evidence_type = "directional"
    elif directional_candidates:
        candidate_name, candidate_value = min(directional_candidates, key=lambda row: float(row[1]))
        estimated_gross_edge_pct = max(float(min_estimated_gross_edge_pct), float(candidate_value))
        estimated_gross_edge_source = str(candidate_name)
        edge_evidence_type = "directional"
    elif effective_allow_volatility_proxy_edge and proxy_candidates and proxy_quality_ok:
        candidate_name, candidate_value = min(proxy_candidates, key=lambda row: float(row[1]))
        proxy_modifier = float(proxy_edge_haircut)
        if quality_available:
            proxy_modifier *= float(quality_modifier)
        estimated_gross_edge_pct = max(
            float(min_estimated_gross_edge_pct),
            float(candidate_value) * proxy_modifier,
        )
        estimated_gross_edge_source = f"{candidate_name}*proxy_haircut"
        if quality_available:
            estimated_gross_edge_source = f"{estimated_gross_edge_source}*quality_modifier"
        edge_evidence_type = "proxy"
    elif allow_quality_proxy_edge and quality_available and proxy_quality_ok:
        estimated_gross_edge_pct = max(float(min_estimated_gross_edge_pct), float(quality_proxy_edge_pct))
        estimated_gross_edge_source = (
            "quality_proxy_capped"
            if quality_proxy_edge_pct < quality_proxy_raw
            else "quality_proxy"
        )
        edge_evidence_type = "quality_proxy"
    else:
        estimated_gross_edge_pct = None

    cost_adjusted_edge_pct = (
        float(estimated_gross_edge_pct - float(effective_cost_drag_pct))
        if estimated_gross_edge_pct is not None and effective_cost_drag_pct is not None
        else None
    )
    required_gross_edge_pct = (
        float(effective_cost_drag_pct) + _to_float(config.get("min_net_profit_buffer_pct"))
        if effective_cost_drag_pct is not None
        else None
    )
    fail_reasons = []
    if enabled:
        if notional <= 0.0:
            fail_reasons.append("cost_filter_price_or_qty_missing")
        if cost_drag_pct is not None and cost_drag_pct > _to_float(config.get("max_cost_drag_pct")):
            fail_reasons.append("cost_drag_too_high")
        if effective_require_directional_edge_evidence and edge_evidence_type != "directional":
            fail_reasons.append("directional_edge_evidence_missing")
        if estimated_gross_edge_pct is None:
            fail_reasons.append("estimated_gross_edge_missing")
        if (
            estimated_gross_edge_pct is not None
            and required_gross_edge_pct is not None
            and estimated_gross_edge_pct < required_gross_edge_pct
        ):
            fail_reasons.append("estimated_gross_edge_below_cost_floor")
        if cost_adjusted_edge_pct is not None and cost_adjusted_edge_pct < _to_float(config.get("min_cost_adjusted_edge_pct")):
            fail_reasons.append("cost_adjusted_edge_below_min")

    passed = (not enabled) or not fail_reasons
    return {
        "schema_version": "entry_cost_filter_result.v1",
        "enabled": bool(enabled),
        "passed": bool(passed),
        "cost_adjusted_edge_ok": bool(passed),
        "fail_reasons": fail_reasons,
        "price": price if price > 0.0 else None,
        "qty": int(quantity),
        "notional": round(notional, 4),
        "buy_fee_est": round(buy_fee, 4),
        "sell_fee_est": round(sell_fee, 4),
        "sell_tax_est": round(sell_tax, 4),
        "round_trip_cost_est": round(total_cost, 4),
        "cost_drag_pct": round(float(cost_drag_pct), 6) if cost_drag_pct is not None else None,
        "round_trip_cost_floor_pct": round(float(round_trip_cost_floor_pct), 6),
        "effective_cost_drag_pct": (
            round(float(effective_cost_drag_pct), 6) if effective_cost_drag_pct is not None else None
        ),
        "cost_floor_applied": bool(
            cost_drag_pct is not None
            and effective_cost_drag_pct is not None
            and effective_cost_drag_pct > cost_drag_pct
        ),
        "min_net_profit_buffer_pct": float(config.get("min_net_profit_buffer_pct") or 0.0),
        "required_gross_edge_pct": (
            round(float(required_gross_edge_pct), 6) if required_gross_edge_pct is not None else None
        ),
        "entry_quality_available": bool(quality_available),
        "entry_quality_score": round(float(quality_score), 4),
        "quality_modifier": round(float(quality_modifier), 6),
        "quality_proxy_edge_pct": round(float(quality_proxy_edge_pct), 6),
        "directional_edge_required": bool(require_directional_edge_evidence),
        "effective_directional_edge_required": bool(effective_require_directional_edge_evidence),
        "directional_edge_available": bool(directional_candidates),
        "proxy_edge_available": bool(proxy_candidates),
        "proxy_edge_allowed": bool(allow_volatility_proxy_edge),
        "effective_proxy_edge_allowed": bool(effective_allow_volatility_proxy_edge),
        "quality_proxy_edge_allowed": bool(allow_quality_proxy_edge),
        "triggered_signal_proxy_edge_allowed": bool(triggered_signal_proxy_allowed),
        "allow_triggered_signal_proxy_edge": bool(allow_triggered_signal_proxy_edge),
        "confidence_score": round(float(confidence_score), 4) if confidence_score > 0.0 else None,
        "confidence_threshold": round(float(confidence_threshold), 4) if confidence_threshold > 0.0 else None,
        "triggered_proxy_confidence_tolerance": round(float(confidence_tolerance), 6),
        "proxy_quality_ok": bool(proxy_quality_ok),
        "proxy_edge_haircut": round(float(proxy_edge_haircut), 6),
        "min_proxy_quality_score": round(float(min_proxy_quality_score), 6),
        "edge_evidence_type": str(edge_evidence_type),
        "estimated_gross_edge_pct": round(float(estimated_gross_edge_pct), 6) if estimated_gross_edge_pct is not None else None,
        "estimated_gross_edge_source": str(estimated_gross_edge_source),
        "directional_edge_candidates": [
            {"source": str(name), "pct": round(float(value), 6)}
            for name, value in directional_candidates[:8]
        ],
        "proxy_edge_candidates": [
            {"source": str(name), "pct": round(float(value), 6)}
            for name, value in proxy_candidates[:8]
        ],
        "expected_move_candidates": [
            {"source": str(name), "pct": round(float(value), 6), "evidence_type": "directional"}
            for name, value in directional_candidates[:8]
        ]
        + [
            {"source": str(name), "pct": round(float(value), 6), "evidence_type": "proxy"}
            for name, value in proxy_candidates[:8]
        ],
        "cost_adjusted_edge_pct": round(float(cost_adjusted_edge_pct), 6) if cost_adjusted_edge_pct is not None else None,
        "max_cost_drag_pct": float(config.get("max_cost_drag_pct") or 0.0),
        "min_cost_adjusted_edge_pct": float(config.get("min_cost_adjusted_edge_pct") or 0.0),
    }


def _resolve_exit_policy_config(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    cfg = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else {}
    out = dict(cfg or {})
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_exit_cfg = (
        (((applied_policy.get("monitor") or {}).get("exit")) or {})
        if isinstance(((applied_policy.get("monitor") or {}).get("exit")), dict)
        else {}
    )
    if isinstance(applied_policy.get("exit_policy"), dict):
        out.update(dict(applied_policy.get("exit_policy") or {}))
    applied_exit_policy_overrides = (
        dict(applied_exit_cfg.get("policy_overrides") or {})
        if isinstance(applied_exit_cfg.get("policy_overrides"), dict)
        else {}
    )
    if applied_exit_policy_overrides:
        out.update(applied_exit_policy_overrides)

    # Backward-compatible flat policy aliases.
    alias_map = {
        "hard_stop_pct": "hard_stop_pct",
        "stop_loss_pct": "stop_loss_pct",
        "take_profit_pct": "take_profit_pct",
        "partial_take_profit_pct": "partial_take_profit_pct",
        "partial_take_profit_fraction": "partial_take_profit_fraction",
        "profit_ladder_levels_pct": "profit_ladder_levels_pct",
        "profit_ladder_fraction": "profit_ladder_fraction",
        "risk_reward_take_profit_r": "risk_reward_take_profit_r",
        "risk_reward_take_profit_rungs": "risk_reward_take_profit_rungs",
        "risk_reward_take_profit_fraction": "risk_reward_take_profit_fraction",
        "risk_reward_take_profit_min_pct": "risk_reward_take_profit_min_pct",
        "vwap_extension_take_profit_pct": "vwap_extension_take_profit_pct",
        "vwap_extension_take_profit_min_pct": "vwap_extension_take_profit_min_pct",
        "resistance_take_profit_near_pct": "resistance_take_profit_near_pct",
        "resistance_take_profit_min_pct": "resistance_take_profit_min_pct",
        "profit_time_stop_sec": "profit_time_stop_sec",
        "profit_time_stop_min_pct": "profit_time_stop_min_pct",
        "profit_time_stop_peak_giveback_pct": "profit_time_stop_peak_giveback_pct",
        "volume_exhaustion_take_profit_min_pct": "volume_exhaustion_take_profit_min_pct",
        "volume_exhaustion_volume_ratio_max": "volume_exhaustion_volume_ratio_max",
        "volume_exhaustion_strength_max": "volume_exhaustion_strength_max",
        "opening_gap_profit_take_min_pct": "opening_gap_profit_take_min_pct",
        "opening_gap_profit_take_window_sec": "opening_gap_profit_take_window_sec",
        "opening_gap_profit_take_fraction": "opening_gap_profit_take_fraction",
        "cost_aware_profit_floor_enabled": "cost_aware_profit_floor_enabled",
        "round_trip_cost_floor_pct": "round_trip_cost_floor_pct",
        "min_net_profit_buffer_pct": "min_net_profit_buffer_pct",
        "cost_aware_profit_floor_pct": "cost_aware_profit_floor_pct",
        "cost_aware_profit_floor_use_expected_exit": "cost_aware_profit_floor_use_expected_exit",
        "sell_slippage_buffer_pct": "sell_slippage_buffer_pct",
        "min_expected_net_profit_pct": "min_expected_net_profit_pct",
        "max_hold_sec": "max_hold_sec",
        "time_stop_sec": "time_stop_sec",
        "trailing_stop_pct": "trailing_stop_pct",
        "vol_expansion_ratio": "vol_expansion_ratio",
        "news_shock_threshold": "news_shock_threshold",
        "peak_drawdown_exit_pct": "peak_drawdown_exit_pct",
        "profit_protection_activation_pct": "profit_protection_activation_pct",
        "peak_drawdown_mode": "peak_drawdown_mode",
        "confirm_required_for_peak_drawdown": "confirm_required_for_peak_drawdown",
        "vwap_breakdown_pct": "vwap_breakdown_pct",
        "vwap_break_requires_profit": "vwap_break_requires_profit",
        "intraday_low_break_pct": "intraday_low_break_pct",
        "trend_strength_floor": "trend_strength_floor",
        "use_eod_flat": "use_eod_flat",
        "eod_flat_cutoff_min": "eod_flat_cutoff_min",
        "emergency_halt": "emergency_halt",
    }
    for src_key, dst_key in alias_map.items():
        if out.get(dst_key) in (None, "") and policy.get(src_key) not in (None, ""):
            out[dst_key] = policy.get(src_key)

    mh_raw = str(os.getenv("EXIT_POLICY_MAX_HOLD_SEC", "") or "").strip()
    trail_raw = str(os.getenv("EXIT_POLICY_TRAILING_STOP_PCT", "") or "").strip()
    vol_exp_raw = str(os.getenv("EXIT_POLICY_VOL_EXPANSION_RATIO", "") or "").strip()
    news_shock_raw = str(os.getenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "") or "").strip()
    peak_drawdown_raw = str(os.getenv("EXIT_POLICY_PEAK_DRAWDOWN_EXIT_PCT", "") or "").strip()
    profit_protection_activation_raw = str(os.getenv("EXIT_POLICY_PROFIT_PROTECTION_ACTIVATION_PCT", "") or "").strip()
    peak_drawdown_mode_raw = str(os.getenv("EXIT_POLICY_PEAK_DRAWDOWN_MODE", "") or "").strip()
    vwap_breakdown_raw = str(os.getenv("EXIT_POLICY_VWAP_BREAKDOWN_PCT", "") or "").strip()
    intraday_low_break_raw = str(os.getenv("EXIT_POLICY_INTRADAY_LOW_BREAK_PCT", "") or "").strip()
    trend_strength_floor_raw = str(os.getenv("EXIT_POLICY_TREND_STRENGTH_FLOOR", "") or "").strip()
    eod_flat_enabled = (
        ((((applied_policy.get("monitor") or {}).get("exit") or {}).get("eod_flat") or {}).get("enabled"))
        if isinstance((((applied_policy.get("monitor") or {}).get("exit") or {}).get("eod_flat")), dict)
        else None
    )
    if eod_flat_enabled is None and isinstance(policy.get("monitor"), dict):
        eod_flat_enabled = (
            ((((policy.get("monitor") or {}).get("exit") or {}).get("eod_flat") or {}).get("enabled"))
            if isinstance((((policy.get("monitor") or {}).get("exit") or {}).get("eod_flat")), dict)
            else None
        )
    eod_flat_raw = str(os.getenv("EXIT_POLICY_USE_EOD_FLAT", "") or "").strip()
    eod_cutoff_value = (
        ((((applied_policy.get("monitor") or {}).get("exit") or {}).get("eod_flat") or {}).get("cutoff_min"))
        if isinstance((((applied_policy.get("monitor") or {}).get("exit") or {}).get("eod_flat")), dict)
        else None
    )
    if eod_cutoff_value is None and isinstance(policy.get("monitor"), dict):
        eod_cutoff_value = (
            ((((policy.get("monitor") or {}).get("exit") or {}).get("eod_flat") or {}).get("cutoff_min"))
            if isinstance((((policy.get("monitor") or {}).get("exit") or {}).get("eod_flat")), dict)
            else None
        )
    emergency_raw = str(os.getenv("EXIT_POLICY_EMERGENCY_HALT", "") or "").strip()

    out = apply_env_stop_take_fallbacks(out)
    if mh_raw:
        base = _to_float(out.get("max_hold_sec"))
        x = _to_float(mh_raw)
        out["max_hold_sec"] = int(x if x > 0.0 else base)
    if trail_raw:
        base = _to_float(out.get("trailing_stop_pct"))
        x = _to_float(trail_raw)
        out["trailing_stop_pct"] = float(x if x > 0.0 else base)
    if vol_exp_raw:
        base = _to_float(out.get("vol_expansion_ratio"))
        x = _to_float(vol_exp_raw)
        out["vol_expansion_ratio"] = float(x if x > 0.0 else base)
    if news_shock_raw:
        base = _to_float(out.get("news_shock_threshold"))
        x = _to_float(news_shock_raw)
        out["news_shock_threshold"] = float(x if x > 0.0 else base)
    if peak_drawdown_raw:
        base = _to_float(out.get("peak_drawdown_exit_pct"))
        x = _to_float(peak_drawdown_raw)
        out["peak_drawdown_exit_pct"] = float(x if x > 0.0 else base)
    if profit_protection_activation_raw:
        base = _to_float(out.get("profit_protection_activation_pct"))
        x = _to_float(profit_protection_activation_raw)
        out["profit_protection_activation_pct"] = float(x if x > 0.0 else base)
    if peak_drawdown_mode_raw:
        out["peak_drawdown_mode"] = str(peak_drawdown_mode_raw or "").strip().lower()
    if vwap_breakdown_raw:
        base = _to_float(out.get("vwap_breakdown_pct"))
        x = _to_float(vwap_breakdown_raw)
        out["vwap_breakdown_pct"] = float(x if x > 0.0 else base)
    if intraday_low_break_raw:
        base = _to_float(out.get("intraday_low_break_pct"))
        x = _to_float(intraday_low_break_raw)
        out["intraday_low_break_pct"] = float(x if x > 0.0 else base)
    if trend_strength_floor_raw:
        out["trend_strength_floor"] = _to_float(trend_strength_floor_raw, _to_float(out.get("trend_strength_floor")))
    if eod_flat_enabled is not None:
        out["use_eod_flat"] = _is_trueish(eod_flat_enabled)
    elif eod_flat_raw:
        out["use_eod_flat"] = _is_trueish(eod_flat_raw)
    elif out.get("use_eod_flat") in (None, ""):
        out["use_eod_flat"] = True
    if eod_cutoff_value is not None:
        base = _to_float(out.get("eod_flat_cutoff_min"))
        if base <= 0.0:
            base = 10.0
        x = _to_float(eod_cutoff_value)
        out["eod_flat_cutoff_min"] = int(x if x > 0.0 else base)
    if emergency_raw:
        out["emergency_halt"] = _is_trueish(emergency_raw)
    if out.get("profit_protection_activation_pct") in (None, ""):
        out["profit_protection_activation_pct"] = 0.008
    if out.get("peak_drawdown_mode") in (None, ""):
        out["peak_drawdown_mode"] = "profit_protection"
    profit_defaults = {
        "cost_aware_profit_floor_enabled": True,
        "round_trip_cost_floor_pct": 0.009,
        "min_net_profit_buffer_pct": 0.003,
        "cost_aware_profit_floor_pct": 0.012,
        "partial_take_profit_pct": 0.012,
        "partial_take_profit_fraction": 0.50,
        "profit_ladder_levels_pct": [0.012, 0.016, 0.020],
        "profit_ladder_fraction": 0.34,
        "risk_reward_take_profit_r": 1.0,
        "risk_reward_take_profit_rungs": [1.0, 1.5, 2.0],
        "risk_reward_take_profit_fraction": 0.34,
        "risk_reward_take_profit_min_pct": 0.012,
        "vwap_extension_take_profit_pct": 0.030,
        "vwap_extension_take_profit_min_pct": 0.012,
        "resistance_take_profit_near_pct": 0.003,
        "resistance_take_profit_min_pct": 0.012,
        "profit_time_stop_sec": 900,
        "profit_time_stop_min_pct": 0.012,
        "profit_time_stop_peak_giveback_pct": 0.003,
        "volume_exhaustion_take_profit_min_pct": 0.012,
        "volume_exhaustion_volume_ratio_max": 0.80,
        "volume_exhaustion_strength_max": 0.75,
        "opening_gap_profit_take_min_pct": 0.012,
        "opening_gap_profit_take_window_sec": 1200,
        "opening_gap_profit_take_fraction": 1.0,
    }
    for key, value in profit_defaults.items():
        if out.get(key) in (None, ""):
            out[key] = value
    out.setdefault("policy_source", str(out.get("effective_policy_source") or "monitor_exit_policy_effective"))
    out.setdefault("effective_policy_source", str(out.get("policy_source") or "monitor_exit_policy_effective"))
    return out


def _extract_monitor_strategy_frame(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output_raw = state.get("strategist_output")
    strategist_output = (
        coerce_strategist_output(strategist_output_raw)
        if isinstance(strategist_output_raw, dict)
        else {}
    )
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    if not _has_strategy_policy_content(strategy_policy) and isinstance(state.get("strategy_policy"), dict):
        strategy_policy = dict(state.get("strategy_policy") or {})
    market_policy = (
        dict(strategy_policy.get("market_policy") or {})
        if isinstance(strategy_policy.get("market_policy"), dict)
        else {}
    )
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    commander_context = (
        dict(strategy_policy.get("commander_context") or {})
        if isinstance(strategy_policy.get("commander_context"), dict)
        else {}
    )
    strategist_plan = (
        dict(strategy_policy.get("strategist_plan") or {})
        if isinstance(strategy_policy.get("strategist_plan"), dict)
        else {}
    )
    policy_provenance = (
        dict(strategy_policy.get("provenance") or {})
        if isinstance(strategy_policy.get("provenance"), dict)
        else {}
    )
    commander_horizon_policy = {}
    for candidate in (
        state.get("commander_horizon_policy"),
        strategy_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("horizon_policy"),
        commander_context.get("commander_horizon_policy"),
        strategist_output.get("commander_horizon_policy"),
    ):
        if isinstance(candidate, dict) and candidate:
            commander_horizon_policy = dict(candidate)
            break
    return {
        "playbook": str(
            state.get("playbook")
            or market_policy.get("playbook")
            or strategist_plan.get("selected_playbook")
            or strategist_output.get("playbook")
            or ""
        ).strip().lower(),
        "monitor_guidance": str(
            state.get("monitor_guidance")
            or market_policy.get("monitor_guidance")
            or strategist_output.get("monitor_guidance")
            or ""
        ).strip().lower(),
        "risk_tone": str(
            state.get("risk_tone")
            or market_policy.get("risk_tone")
            or strategist_output.get("risk_tone")
            or ""
        ).strip().lower(),
        "trade_aggressiveness": str(
            state.get("trade_aggressiveness")
            or market_policy.get("trade_aggressiveness")
            or strategist_output.get("trade_aggressiveness")
            or ""
        ).strip().lower(),
        "commander_context": commander_context,
        "commander_horizon_policy": commander_horizon_policy,
        "strategy_horizon": str(commander_horizon_policy.get("strategy_horizon") or strategy_monitor_policy.get("strategy_horizon") or strategist_output.get("strategy_horizon") or "").strip(),
        "source_strategy_horizon": str(commander_horizon_policy.get("source_strategy_horizon") or "").strip(),
        "strategist_plan": strategist_plan,
        "policy_provenance": policy_provenance,
    }


def _build_monitor_policy_trace(
    *,
    commander_context: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    strategist_plan: Dict[str, Any],
    policy_provenance: Dict[str, Any],
    entry_info: Dict[str, Any],
    exit_info: Dict[str, Any],
    current_reason: str,
) -> Dict[str, Any]:
    consumed_fields: List[str] = []
    for key in (
        "monitor_mission",
        "flow_instruction",
        "command_intent",
        "risk_mode",
        "no_trade_reason_code",
        "llm_policy",
        "source_priority",
        "entry_control",
        "commander_entry_control",
    ):
        value = commander_context.get(key)
        if value not in (None, "", [], {}):
            consumed_fields.append(key)
    commander_context_consumed = bool(consumed_fields)

    strategy_fields: List[str] = []
    for key in ("selected_playbook", "entry_plan", "exit_plan", "symbol_constraints", "strategy_summary"):
        value = strategist_plan.get(key)
        if value not in (None, "", [], {}):
            strategy_fields.append(key)

    flow_instruction = str(commander_context.get("flow_instruction") or "").strip()
    no_trade_reason_code = str(commander_context.get("no_trade_reason_code") or "").strip()
    monitor_mission = str(commander_context.get("monitor_mission") or "").strip()
    entry_plan = dict(strategist_plan.get("entry_plan") or {})
    exit_plan = dict(strategist_plan.get("exit_plan") or {})

    def _policy_meta_value(key: str, default: Any = "") -> Any:
        commander_value = commander_context.get(key)
        if commander_value not in (None, "", [], {}):
            return commander_value
        monitor_value = monitor_policy.get(key)
        if monitor_value not in (None, "", [], {}):
            return monitor_value
        return default

    entry_blockers = list(
        dict.fromkeys(
            [
                no_trade_reason_code,
                str(entry_info.get("guard_reason") or "").strip(),
                str(entry_info.get("reason") or "").strip(),
                *[str(x or "").strip() for x in list(entry_info.get("failed_checks") or []) if str(x or "").strip()],
            ]
        )
    )
    entry_blockers = [item for item in entry_blockers if item][:8]

    summary_parts: List[str] = []
    if monitor_mission:
        summary_parts.append(f"mission={monitor_mission}")
    if flow_instruction:
        summary_parts.append(f"flow={flow_instruction}")
    if str(strategist_plan.get("selected_playbook") or "").strip():
        summary_parts.append(f"playbook={str(strategist_plan.get('selected_playbook') or '').strip()}")
    if current_reason:
        summary_parts.append(f"reason={current_reason}")

    return {
        "commander_context_consumed": commander_context_consumed,
        "consumed_fields": consumed_fields + strategy_fields,
        "flow_instruction_applied": bool(flow_instruction),
        "no_trade_reason_applied": bool(no_trade_reason_code),
        "shadow_used": bool(
            commander_context.get("shadow_used")
            if commander_context.get("shadow_used") is not None
            else policy_provenance.get("shadow_used")
        ),
        "strategist_fallback_used": bool(
            commander_context.get("strategist_fallback_used")
            if commander_context.get("strategist_fallback_used") is not None
            else policy_provenance.get("strategist_fallback_used")
        ),
        "policy_ref": {
            "monitor_mission": monitor_mission,
            "flow_instruction": flow_instruction,
            "command_intent": str(commander_context.get("command_intent") or ""),
            "risk_mode": str(commander_context.get("risk_mode") or ""),
            "no_trade_reason_code": no_trade_reason_code,
            "llm_policy": str(commander_context.get("llm_policy") or ""),
            "source_priority": list(commander_context.get("source_priority") or []),
            "entry_control": dict(commander_context.get("entry_control") or {})
            if isinstance(commander_context.get("entry_control"), dict)
            else {},
            "applied_policy": dict(commander_context.get("applied_policy") or {})
            if isinstance(commander_context.get("applied_policy"), dict)
            else dict(monitor_policy.get("applied_policy") or {})
            if isinstance(monitor_policy.get("applied_policy"), dict)
            else {},
            "policy_source": str(_policy_meta_value("policy_source", "")),
            "policy_validation_status": str(_policy_meta_value("policy_validation_status", "")),
            "policy_fallback_used": bool(_policy_meta_value("policy_fallback_used", False)),
            "policy_fallback_reason": str(_policy_meta_value("policy_fallback_reason", "")),
            "policy_partial_normalized": bool(_policy_meta_value("policy_partial_normalized", False)),
            "policy_default_filled_fields": list(_policy_meta_value("policy_default_filled_fields", [])),
            "policy_validation_missing_fields": list(_policy_meta_value("policy_validation_missing_fields", [])),
            "policy_validation_invalid_fields": list(_policy_meta_value("policy_validation_invalid_fields", [])),
            "override_reason": str(_policy_meta_value("override_reason", "")),
            "applied_policy_source_chain": list(_policy_meta_value("applied_policy_source_chain", [])),
            "selected_playbook": str(strategist_plan.get("selected_playbook") or ""),
            "entry_plan": entry_plan,
            "exit_plan": exit_plan,
            "symbol_constraints": dict(strategist_plan.get("symbol_constraints") or {}),
            "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
        },
        "entry_check_summary": " | ".join(summary_parts) if summary_parts else str(current_reason or entry_info.get("reason") or ""),
        "entry_blockers": entry_blockers,
        "timing_assessment": {
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_reason": str(entry_info.get("reason") or ""),
            "entry_plan": entry_plan,
            "monitor_mission": monitor_mission,
            "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
        },
        "exit_trigger_basis": {
            "exit_reason": str(exit_info.get("reason") or ""),
            "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
            "final_exit_thresholds": dict(exit_info.get("final_exit_thresholds") or {}),
            "exit_threshold_source": str(exit_info.get("exit_threshold_source") or ""),
            "hold_block_reason": str(exit_info.get("hold_block_reason") or ""),
            "max_runup_pct": exit_info.get("max_runup_pct"),
            "peak_drawdown_from_peak": exit_info.get("peak_drawdown_from_peak"),
            "peak_drawdown_armed": bool(exit_info.get("peak_drawdown_armed")),
            "peak_drawdown_mode": str(exit_info.get("peak_drawdown_mode") or ""),
            "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
            "peak_drawdown_source": str(exit_info.get("peak_drawdown_source") or ""),
            "exit_trigger_metric_name": str(exit_info.get("exit_trigger_metric_name") or ""),
            "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
            "exit_trigger_metric_source": str(exit_info.get("exit_trigger_metric_source") or ""),
            "gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
            "technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
            "stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
            "stop_pnl_ratio_source": str(exit_info.get("stop_pnl_ratio_source") or ""),
            "hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
            "hard_stop_pnl_ratio_source": str(exit_info.get("hard_stop_pnl_ratio_source") or ""),
            "cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
            "cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
            "cost_drag_pressure_reason": str(exit_info.get("cost_drag_pressure_reason") or ""),
            "stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
            "stop_loss_cost_drag_blocked_reason": str(exit_info.get("stop_loss_cost_drag_blocked_reason") or ""),
            "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
            "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
            "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
            "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
            "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
            "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
            "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
            "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
            "protective_exit_hard_invalidation_reason": str(
                exit_info.get("protective_exit_hard_invalidation_reason") or ""
            ),
            "exit_plan": exit_plan,
            "monitor_mission": monitor_mission,
        },
    }


def _resolve_monitor_entry_scoring_config(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    monitor_policy = applied_policy.get("monitor") if isinstance(applied_policy.get("monitor"), dict) else {}
    entry_policy = monitor_policy.get("entry") if isinstance(monitor_policy.get("entry"), dict) else {}
    scoring_policy = entry_policy.get("scoring") if isinstance(entry_policy.get("scoring"), dict) else {}
    if isinstance(scoring_policy, dict) and scoring_policy:
        out = dict(scoring_policy)
        if out.get("entry_threshold") in (None, "") and out.get("threshold") not in (None, ""):
            out["entry_threshold"] = out.get("threshold")
        out.setdefault("policy_source", str(scoring_policy.get("policy_source") or "commander_applied_policy"))
        return out
    state_scoring = state.get("monitor_entry_scoring")
    if isinstance(state_scoring, dict) and state_scoring:
        out = dict(state_scoring)
        out.setdefault("policy_source", str(state_scoring.get("policy_source") or "state_fallback"))
        return out
    policy_scoring = policy.get("monitor_entry_scoring") if isinstance(policy.get("monitor_entry_scoring"), dict) else {}
    if isinstance(policy_scoring, dict) and policy_scoring:
        out = dict(policy_scoring)
        if out.get("entry_threshold") in (None, "") and out.get("threshold") not in (None, ""):
            out["entry_threshold"] = out.get("threshold")
        out.setdefault("policy_source", str(policy_scoring.get("policy_source") or "policy_fallback"))
        return out
    return {}


def _has_strategy_policy_content(strategy_policy: Any) -> bool:
    if not isinstance(strategy_policy, dict):
        return False
    for key in (
        "market_policy",
        "scanner_policy",
        "monitor_policy",
        "decision_policy",
        "commander_context",
        "strategist_plan",
        "provenance",
    ):
        value = strategy_policy.get(key)
        if isinstance(value, dict) and value:
            return True
    return False


def _apply_monitor_strategy_frame(
    *,
    min_hold_sec: int,
    sell_cooldown_sec: int,
    confirm_ticks: int,
    frame: Dict[str, str],
) -> Dict[str, Any]:
    min_hold = max(0, int(min_hold_sec))
    cooldown = max(0, int(sell_cooldown_sec))
    confirm = max(1, int(confirm_ticks))
    adjustments: list[str] = []

    playbook = str(frame.get("playbook") or "").strip().lower()
    mode = str(frame.get("monitor_guidance") or "").strip().lower()
    horizon_policy = (
        dict(frame.get("commander_horizon_policy") or {})
        if isinstance(frame.get("commander_horizon_policy"), dict)
        else {}
    )
    behavior_translation = (
        dict(horizon_policy.get("behavior_translation") or {})
        if isinstance(horizon_policy.get("behavior_translation"), dict)
        else {}
    )
    strategy_horizon = str(
        horizon_policy.get("strategy_horizon")
        or frame.get("strategy_horizon")
        or behavior_translation.get("strategy_horizon")
        or ""
    ).strip().lower()
    if not mode:
        if playbook == "breakout":
            mode = "hold_through_noise"
            adjustments.append("playbook:breakout->monitor_guidance")
        elif playbook == "defensive":
            mode = "defensive_exit"
            adjustments.append("playbook:defensive->monitor_guidance")
        elif playbook in ("pullback", "reversal"):
            mode = "quick_take_profit"
            adjustments.append(f"playbook:{playbook}->monitor_guidance")

    if mode == "hold_through_noise":
        min_hold += 300
        confirm += 1
        cooldown += 60
        adjustments.append("monitor_guidance:hold_through_noise")
    elif mode == "defensive_exit":
        min_hold = max(0, min_hold - 120)
        confirm = max(1, confirm - 1)
        adjustments.append("monitor_guidance:defensive_exit")
    elif mode == "quick_take_profit":
        min_hold = max(0, min_hold - 300)
        confirm = 1
        cooldown = max(60, min(cooldown, 180))
        adjustments.append("monitor_guidance:quick_take_profit")

    tone = str(frame.get("risk_tone") or "").strip().lower()
    if tone == "conservative":
        min_hold += 120
        confirm += 1
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        min_hold = max(0, min_hold - 60)
        confirm = max(1, confirm - 1)
        adjustments.append("risk_tone:aggressive")

    aggr = str(frame.get("trade_aggressiveness") or "").strip().lower()
    if aggr == "low":
        confirm = max(confirm, 3)
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        confirm = max(1, confirm - 1)
        adjustments.append("trade_aggressiveness:high")

    if bool(behavior_translation.get("applied")) or strategy_horizon:
        if strategy_horizon == "scalp":
            min_hold = max(0, min(min_hold, 180))
            confirm = 1
            cooldown = max(30, min(cooldown, 120))
            adjustments.append("strategy_horizon:scalp_hold_controls")
        elif strategy_horizon == "intraday":
            confirm = max(1, min(confirm, 3))
            adjustments.append("strategy_horizon:intraday_hold_controls")
        elif strategy_horizon in {"overnight_probe", "1_2day_swing"}:
            min_hold += 600 if strategy_horizon == "overnight_probe" else 900
            confirm = max(confirm, 2)
            cooldown += 120
            adjustments.append(f"strategy_horizon:{strategy_horizon}_hold_controls")

    return {
        "min_hold_sec": max(0, int(min_hold)),
        "sell_cooldown_sec": max(0, int(cooldown)),
        "confirm_ticks": max(1, min(6, int(confirm))),
        "playbook": playbook,
        "monitor_guidance": mode,
        "risk_tone": tone,
        "trade_aggressiveness": aggr,
        "strategy_horizon": strategy_horizon,
        "source_strategy_horizon": str(horizon_policy.get("source_strategy_horizon") or frame.get("source_strategy_horizon") or ""),
        "horizon_behavior_translation": dict(behavior_translation),
        "adjustments": list(adjustments),
    }


def _harmonize_exit_policy_with_monitor_guards(
    *,
    exit_policy_base: Dict[str, Any],
    min_hold_sec: int,
) -> Dict[str, Any]:
    """Raise time-based exits that conflict with min-hold.

    Without this, `max_hold_sec < min_hold_sec` makes the runtime exit on the
    first post-min-hold tick. That is coherent in code but incoherent in policy.
    """
    out = dict(exit_policy_base or {})
    adjustments: list[str] = []
    min_hold = max(0, int(min_hold_sec or 0))
    if min_hold <= 0:
        return {"policy": out, "adjustments": adjustments}

    max_hold = _to_int(out.get("max_hold_sec"))
    if max_hold > 0 and max_hold < min_hold:
        out["max_hold_sec"] = int(min_hold)
        adjustments.append(f"max_hold_sec_raised_to_min_hold:{max_hold}->{min_hold}")

    time_stop = _to_int(out.get("time_stop_sec"))
    if time_stop > 0 and time_stop < min_hold:
        out["time_stop_sec"] = int(min_hold)
        adjustments.append(f"time_stop_sec_raised_to_min_hold:{time_stop}->{min_hold}")

    return {"policy": out, "adjustments": adjustments}


def _apply_exit_policy_strategy_frame(
    *,
    state: Dict[str, Any],
    exit_policy_base: Dict[str, Any],
    selected: Dict[str, Any] | None,
    position: Dict[str, Any] | None,
    frame: Dict[str, str],
) -> Dict[str, Any]:
    out = dict(exit_policy_base or {})
    adjustments: list[str] = []

    strategist_output_raw = state.get("strategist_output")
    strategist_output = (
        coerce_strategist_output(strategist_output_raw)
        if isinstance(strategist_output_raw, dict)
        else {}
    )
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    strategist_exit_policy = {}
    if isinstance(strategy_monitor_policy.get("adaptive_exit"), dict):
        strategist_exit_policy.update(dict(strategy_monitor_policy.get("adaptive_exit") or {}))
    elif isinstance(strategy_monitor_policy.get("exit_policy"), dict):
        strategist_exit_policy.update(dict(strategy_monitor_policy.get("exit_policy") or {}))
    if isinstance(strategist_output.get("exit_policy"), dict):
        strategist_exit_policy.update(dict(strategist_output.get("exit_policy") or {}))
    if isinstance(state.get("strategist_exit_policy"), dict):
        strategist_exit_policy.update(dict(state.get("strategist_exit_policy") or {}))
    if strategist_exit_policy:
        for key in (
            "hard_stop_pct",
            "stop_loss_pct",
            "take_profit_pct",
            "partial_take_profit_pct",
            "partial_take_profit_fraction",
            "profit_ladder_levels_pct",
            "profit_ladder_fraction",
            "risk_reward_take_profit_r",
            "risk_reward_take_profit_rungs",
            "risk_reward_take_profit_fraction",
            "risk_reward_take_profit_min_pct",
            "vwap_extension_take_profit_pct",
            "vwap_extension_take_profit_min_pct",
            "resistance_take_profit_near_pct",
            "resistance_take_profit_min_pct",
            "profit_time_stop_sec",
            "profit_time_stop_min_pct",
            "profit_time_stop_peak_giveback_pct",
            "volume_exhaustion_take_profit_min_pct",
            "volume_exhaustion_volume_ratio_max",
            "volume_exhaustion_strength_max",
            "opening_gap_profit_take_min_pct",
            "opening_gap_profit_take_window_sec",
            "opening_gap_profit_take_fraction",
            "cost_aware_profit_floor_enabled",
            "round_trip_cost_floor_pct",
            "min_net_profit_buffer_pct",
            "cost_aware_profit_floor_pct",
            "max_hold_sec",
            "time_stop_sec",
            "trailing_stop_pct",
            "vol_expansion_ratio",
            "news_shock_threshold",
            "peak_drawdown_exit_pct",
            "profit_protection_activation_pct",
            "peak_drawdown_mode",
            "confirm_required_for_peak_drawdown",
            "vwap_breakdown_pct",
            "intraday_low_break_pct",
            "trend_strength_floor",
            "use_eod_flat",
            "eod_flat_cutoff_min",
            "emergency_halt",
        ):
            if strategist_exit_policy.get(key) not in (None, ""):
                out[key] = strategist_exit_policy.get(key)
        adjustments.append("strategist_exit_policy_override")

    commander_horizon_policy = {}
    for candidate in (
        state.get("commander_horizon_policy"),
        strategy_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("commander_horizon_policy"),
        strategy_monitor_policy.get("horizon_policy"),
        frame.get("commander_horizon_policy") if isinstance(frame, dict) else {},
    ):
        if isinstance(candidate, dict) and candidate:
            commander_horizon_policy = dict(candidate)
            break
    behavior_translation = (
        dict(commander_horizon_policy.get("behavior_translation") or {})
        if isinstance(commander_horizon_policy.get("behavior_translation"), dict)
        else {}
    )
    if not behavior_translation and isinstance(frame, dict) and isinstance(frame.get("horizon_behavior_translation"), dict):
        behavior_translation = dict(frame.get("horizon_behavior_translation") or {})

    raw_playbook = str(
        state.get("playbook")
        or ((strategist_output_raw or {}).get("playbook") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()
    raw_guidance = str(
        state.get("monitor_guidance")
        or ((strategist_output_raw or {}).get("monitor_guidance") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()
    raw_tone = str(
        state.get("risk_tone")
        or ((strategist_output_raw or {}).get("risk_tone") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()
    raw_aggr = str(
        state.get("trade_aggressiveness")
        or ((strategist_output_raw or {}).get("trade_aggressiveness") if isinstance(strategist_output_raw, dict) else "")
        or ""
    ).strip().lower()

    playbook = raw_playbook
    guidance = raw_guidance or str(frame.get("monitor_guidance") or "").strip().lower()
    tone = raw_tone or str(frame.get("risk_tone") or "").strip().lower()
    aggr = raw_aggr or str(frame.get("trade_aggressiveness") or "").strip().lower()

    if not strategist_exit_policy and not commander_horizon_policy and not any((raw_playbook, raw_guidance, raw_tone, raw_aggr)):
        return {"policy": out, "adjustments": adjustments}

    features = selected.get("features") if isinstance(selected, dict) and isinstance(selected.get("features"), dict) else {}
    price = _resolve_price(
        state,
        str((selected or {}).get("symbol") or ""),
        selected,
        position=position if isinstance(position, dict) else None,
    )
    if price is None or _to_float(price) <= 0.0:
        price = _position_mark_price(position)
    price_num = _to_float(price)
    atr14 = _to_float((features or {}).get("engine_atr14"))
    volatility20 = _to_float((features or {}).get("engine_volatility20"))
    trend_strength = _to_float((features or {}).get("engine_trend_strength"))
    vwap_distance = _to_float((features or {}).get("engine_vwap_distance"))
    hard_risk_rails = (
        dict(strategy_monitor_policy.get("hard_risk_rails") or {})
        if isinstance(strategy_monitor_policy.get("hard_risk_rails"), dict)
        else {}
    )

    stop_loss_pct = _to_float(out.get("stop_loss_pct"))
    if stop_loss_pct <= 0.0:
        stop_loss_pct = 0.03
    hard_stop_pct = _to_float(out.get("hard_stop_pct"))
    if hard_stop_pct <= 0.0:
        hard_stop_pct = _to_float(hard_risk_rails.get("hard_stop_pct"))
    take_profit_pct = _to_float(out.get("take_profit_pct"))
    if take_profit_pct <= 0.0:
        take_profit_pct = 0.05
    trailing_stop_pct = _to_float(out.get("trailing_stop_pct"))
    vol_expansion_ratio = _to_float(out.get("vol_expansion_ratio"))
    risk_reward_take_profit_r = _to_float(out.get("risk_reward_take_profit_r"))
    vwap_extension_take_profit_min_pct = _to_float(out.get("vwap_extension_take_profit_min_pct"))
    profit_time_stop_sec = _to_int(out.get("profit_time_stop_sec"))
    max_hold_sec = _to_int(out.get("max_hold_sec"))

    strategy_horizon = str(
        commander_horizon_policy.get("strategy_horizon")
        or frame.get("strategy_horizon")
        or behavior_translation.get("strategy_horizon")
        or ""
    ).strip().lower()
    expected_window = (
        dict(commander_horizon_policy.get("expected_hold_window") or {})
        if isinstance(commander_horizon_policy.get("expected_hold_window"), dict)
        else {}
    )
    if bool(behavior_translation.get("applied")) or strategy_horizon:
        if strategy_horizon == "scalp":
            take_profit_pct *= 0.88
            trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.85)
            if risk_reward_take_profit_r > 0.0:
                risk_reward_take_profit_r = min(risk_reward_take_profit_r, 0.85)
            profit_time_stop_sec = 300 if profit_time_stop_sec <= 0 else min(profit_time_stop_sec, 300)
            max_hold_sec = 900 if max_hold_sec <= 0 else min(max_hold_sec, 900)
            adjustments.append("strategy_horizon:scalp_exit_policy")
        elif strategy_horizon == "intraday":
            if profit_time_stop_sec <= 0:
                profit_time_stop_sec = 900
            window_max = _to_int(expected_window.get("max_sec"))
            if window_max > 0:
                max_hold_sec = window_max if max_hold_sec <= 0 else min(max_hold_sec, window_max)
            adjustments.append("strategy_horizon:intraday_exit_policy")
        elif strategy_horizon in {"overnight_probe", "1_2day_swing"}:
            take_profit_pct *= 1.10 if strategy_horizon == "overnight_probe" else 1.18
            trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
            window_max = _to_int(expected_window.get("max_sec"))
            if window_max > 0:
                max_hold_sec = max(max_hold_sec, window_max)
            out["allow_overnight_from_strategy_horizon"] = bool(behavior_translation.get("overnight_allowed"))
            adjustments.append(f"strategy_horizon:{strategy_horizon}_exit_policy")

    if playbook == "breakout":
        take_profit_pct *= 1.10
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.90)
        adjustments.append("playbook:breakout_exit")
    elif playbook == "pullback":
        stop_loss_pct *= 1.05
        take_profit_pct *= 1.08
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.75)
        adjustments.append("playbook:pullback_exit")
    elif playbook == "reversal":
        stop_loss_pct *= 0.92
        take_profit_pct *= 0.95
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        adjustments.append("playbook:reversal_exit")
    elif playbook == "defensive":
        stop_loss_pct *= 0.90
        take_profit_pct *= 0.90
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.65)
        adjustments.append("playbook:defensive_exit")

    if guidance == "hold_through_noise":
        stop_loss_pct *= 1.05
        take_profit_pct *= 1.05
        adjustments.append("monitor_guidance:hold_through_noise_exit")
    elif guidance == "quick_take_profit":
        take_profit_pct *= 0.90
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.80)
        if risk_reward_take_profit_r > 0.0:
            risk_reward_take_profit_r = min(risk_reward_take_profit_r, 0.85)
        if vwap_extension_take_profit_min_pct > 0.0:
            vwap_extension_take_profit_min_pct = min(vwap_extension_take_profit_min_pct, 0.004)
        if profit_time_stop_sec > 0:
            profit_time_stop_sec = min(profit_time_stop_sec, 600)
        adjustments.append("monitor_guidance:quick_take_profit_exit")
    elif guidance == "defensive_exit":
        stop_loss_pct *= 0.95
        take_profit_pct *= 0.92
        adjustments.append("monitor_guidance:defensive_exit_exit")

    if tone == "conservative":
        stop_loss_pct *= 0.92
        take_profit_pct *= 0.96
        adjustments.append("risk_tone:conservative_exit")
    elif tone == "aggressive":
        stop_loss_pct *= 1.08
        take_profit_pct *= 1.05
        adjustments.append("risk_tone:aggressive_exit")

    if aggr == "low":
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        adjustments.append("trade_aggressiveness:low_exit")
    elif aggr == "high":
        take_profit_pct *= 1.05
        adjustments.append("trade_aggressiveness:high_exit")

    if atr14 > 0.0 and price_num > 0.0:
        atr_ratio = float(atr14 / price_num)
        atr_mult = 1.2
        if playbook == "breakout":
            atr_mult = 1.4
        elif playbook == "pullback":
            atr_mult = 1.8
        elif playbook == "reversal":
            atr_mult = 1.3
        atr_stop = _clamp(atr_ratio * atr_mult, 0.005, 0.08)
        if atr_stop > stop_loss_pct:
            stop_loss_pct = atr_stop
            adjustments.append(f"atr_stop_floor:{atr_stop:.4f}")

    if volatility20 > 0.0:
        vol_stop = _clamp(volatility20 * (1.15 if tone == "aggressive" else 0.95), 0.005, 0.08)
        if vol_stop > stop_loss_pct:
            stop_loss_pct = vol_stop
            adjustments.append(f"volatility_stop_floor:{vol_stop:.4f}")
        if vol_expansion_ratio <= 0.0:
            vol_expansion_ratio = 1.8 if playbook in ("defensive", "pullback") else 2.2
            adjustments.append("vol_expansion_ratio:auto")

    if vwap_distance > 0.02 and guidance == "quick_take_profit":
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.90)
        adjustments.append("vwap_distance:extended_profit_lock")

    if trend_strength > 0.5 and playbook in ("breakout", "pullback"):
        take_profit_pct = max(take_profit_pct, stop_loss_pct * 1.6)
        adjustments.append("trend_strength:extend_take_profit")

    stop_loss_pct = _clamp(stop_loss_pct, 0.003, 0.10)
    if hard_stop_pct > 0.0:
        hard_stop_pct = _clamp(hard_stop_pct, 0.003, 0.10)
    if take_profit_pct <= 0.0:
        take_profit_pct = max(0.005, stop_loss_pct * 1.05)
    take_profit_pct = _clamp(take_profit_pct, 0.005, 0.25)
    trailing_stop_pct = _clamp(max(trailing_stop_pct, stop_loss_pct * 0.50 if trailing_stop_pct > 0.0 else 0.0), 0.0, 0.15)
    vol_expansion_ratio = _clamp(vol_expansion_ratio, 0.0, 5.0)
    max_stop_pct_cap = _to_float(hard_risk_rails.get("max_stop_pct_cap"))
    if max_stop_pct_cap > 0.0 and stop_loss_pct > max_stop_pct_cap:
        stop_loss_pct = max_stop_pct_cap
        adjustments.append(f"strategy_policy:max_stop_pct_cap:{max_stop_pct_cap:.4f}")
    if hard_stop_pct > 0.0:
        adjustments.append(f"strategy_policy:hard_stop_pct:{hard_stop_pct:.4f}")

    out["hard_stop_pct"] = float(hard_stop_pct)
    out["stop_loss_pct"] = float(stop_loss_pct)
    out["take_profit_pct"] = float(take_profit_pct)
    out["trailing_stop_pct"] = float(trailing_stop_pct)
    out["vol_expansion_ratio"] = float(vol_expansion_ratio)
    if risk_reward_take_profit_r > 0.0:
        out["risk_reward_take_profit_r"] = float(_clamp(risk_reward_take_profit_r, 0.0, 3.0))
    if vwap_extension_take_profit_min_pct > 0.0:
        out["vwap_extension_take_profit_min_pct"] = float(_clamp(vwap_extension_take_profit_min_pct, 0.001, 0.05))
    if profit_time_stop_sec > 0:
        out["profit_time_stop_sec"] = int(profit_time_stop_sec)
    if max_hold_sec > 0:
        out["max_hold_sec"] = int(max_hold_sec)
    if strategy_horizon:
        out["strategy_horizon"] = strategy_horizon
        out["source_strategy_horizon"] = str(commander_horizon_policy.get("source_strategy_horizon") or frame.get("source_strategy_horizon") or "")
        out["horizon_behavior_translation_applied"] = bool(behavior_translation.get("applied"))
        out["horizon_exit_policy_bias"] = str(behavior_translation.get("exit_policy_bias") or "")
    return {"policy": out, "adjustments": adjustments}


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    tick_ts = state.get("tick_ts")
    try:
        if tick_ts is not None:
            return int(float(tick_ts))
    except Exception:
        pass
    return int(time.time())


def _norm_symbol(v: Any) -> str:
    return normalize_symbol(v)


def _clear_symbol_confirm_keys(confirm_map: Dict[str, Any], symbol: str) -> None:
    prefix = f"{_norm_symbol(symbol)}:"
    for key in list(confirm_map.keys()):
        if str(key).startswith(prefix):
            confirm_map.pop(key, None)


def _is_emergency_exit_reason(reason: str) -> bool:
    r = str(reason or "").strip().lower()
    return r in ("emergency_halt", "news_shock")


def _is_hard_exit_reason(reason: str) -> bool:
    r = str(reason or "").strip().lower()
    return r in (
        "emergency_halt",
        "news_shock",
        "eod_flat",
        "hard_stop",
        "stop_loss",
        "intraday_low_break",
        "trend_breakdown",
        "vwap_breakdown",
        "volatility_expansion",
        "trailing_stop",
    )


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _emit_monitor_event(
    state: Dict[str, Any],
    *,
    name: str,
    payload: Dict[str, Any],
    level: str = "info",
    symbol: str = "",
) -> None:
    try:
        logger = _make_event_logger(state)
        from libs.core.event_logger import log_state_event

        log_state_event(
            logger,
            state,
            stage="monitor",
            event=name,
            event_name=f"monitor.{name}",
            payload=dict(payload or {}),
            level=level,
            agent="monitor",
            symbol=str(symbol or ""),
        )
    except Exception:
        return


def _log_monitor_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "monitor-node")
        logger.log(run_id=run_id, stage="monitor", event="summary", payload=dict(payload))
    except Exception:
        return


def _friendly_exit_axis(reason: Any) -> str:
    text = str(reason or "").strip().replace("_", " ")
    if not text:
        return "No trigger"
    return " ".join(part.capitalize() for part in text.split())


def _monitor_watch_axes(thresholds: Dict[str, Any]) -> list[str]:
    if not isinstance(thresholds, dict):
        return []
    out: list[str] = []
    if _to_float(thresholds.get("hard_stop_pct")) > 0.0:
        out.append("Hard stop")
    if _to_float(thresholds.get("stop_loss_pct")) > 0.0:
        out.append("Adaptive stop")
    if _to_float(thresholds.get("take_profit_pct")) > 0.0:
        out.append("Take profit")
    if _is_trueish(thresholds.get("cost_aware_profit_floor_enabled")) and _to_float(
        thresholds.get("cost_aware_profit_floor_pct")
    ) > 0.0:
        out.append("Cost-aware profit floor")
    if _to_float(thresholds.get("partial_take_profit_pct")) > 0.0:
        out.append("Partial take profit")
    if isinstance(thresholds.get("profit_ladder_levels_pct"), list) and thresholds.get("profit_ladder_levels_pct"):
        out.append("Profit ladder")
    if _to_float(thresholds.get("risk_reward_take_profit_r")) > 0.0:
        out.append("Risk/reward take profit")
    elif isinstance(thresholds.get("risk_reward_take_profit_rungs"), list) and thresholds.get("risk_reward_take_profit_rungs"):
        out.append("Risk/reward take profit")
    if _to_float(thresholds.get("vwap_extension_take_profit_pct")) > 0.0:
        out.append("VWAP extension take profit")
    if _to_float(thresholds.get("resistance_take_profit_near_pct")) > 0.0:
        out.append("Resistance take profit")
    if _to_float(thresholds.get("volume_exhaustion_take_profit_min_pct")) > 0.0:
        out.append("Volume exhaustion take profit")
    if _to_float(thresholds.get("opening_gap_profit_take_min_pct")) > 0.0:
        out.append("Opening gap profit take")
    if _to_float(thresholds.get("profit_time_stop_sec")) > 0.0:
        out.append("Time-decay profit exit")
    if _to_float(thresholds.get("trailing_stop_pct")) > 0.0:
        out.append("Trailing stop")
    if _to_float(thresholds.get("peak_drawdown_exit_pct")) > 0.0:
        out.append("Peak drawdown")
    if _to_float(thresholds.get("vwap_breakdown_pct")) > 0.0:
        out.append("VWAP breakdown")
    if _to_float(thresholds.get("intraday_low_break_pct")) > 0.0:
        out.append("Intraday low break")
    if _to_float(thresholds.get("trend_strength_floor")) != 0.0:
        out.append("Trend breakdown")
    if _to_float(thresholds.get("vol_expansion_ratio")) > 0.0:
        out.append("Volatility expansion")
    if _to_float(thresholds.get("news_shock_threshold")) > 0.0:
        out.append("News shock")
    if bool(thresholds.get("use_eod_flat")):
        out.append("EOD flat")
    return out


def _monitor_posture_for_cycle(
    *,
    open_position_count: int,
    intents: list[dict],
    exit_info: Dict[str, Any],
    buy_blocked_open_position: bool,
    buy_blocked_post_exit_cooldown: bool,
) -> str:
    if any(str((intent or {}).get("side") or "").strip().upper() == "SELL" for intent in list(intents or [])):
        return "SELL"
    if any(str((intent or {}).get("side") or "").strip().upper() == "BUY" for intent in list(intents or [])):
        return "BUY"
    if bool(exit_info.get("triggered")):
        return "SELL"
    if open_position_count > 0:
        return "HOLD"
    if buy_blocked_open_position or buy_blocked_post_exit_cooldown:
        return "WAIT"
    return "WAIT"


def _load_previous_monitor_state(state: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw = persisted.get("monitor_last_state_by_symbol") if isinstance(persisted.get("monitor_last_state_by_symbol"), dict) else {}
    row = raw.get(_norm_symbol(symbol)) if isinstance(raw, dict) else {}
    return dict(row) if isinstance(row, dict) else {}


def _build_monitor_entry_state_snapshot(entry_info: Dict[str, Any]) -> Dict[str, Any]:
    metrics = dict(entry_info.get("metrics") or {}) if isinstance(entry_info.get("metrics"), dict) else {}
    scores = dict(entry_info.get("condition_scores") or {}) if isinstance(entry_info.get("condition_scores"), dict) else {}
    margins = dict(entry_info.get("threshold_margins") or {}) if isinstance(entry_info.get("threshold_margins"), dict) else {}
    breakout_margins = dict(margins.get("breakout_gap_pct") or {}) if isinstance(margins.get("breakout_gap_pct"), dict) else {}
    return {
        "extended_from_vwap_pct": _optional_float(metrics.get("extended_from_vwap_pct")),
        "volume_ratio": _optional_float(metrics.get("volume_ratio")),
        "breakout_gap_pct": _optional_float(breakout_margins.get("actual")),
        "reclaim_gate_ok": bool(metrics.get("reclaim_gate_ok")),
        "volume_ok": bool(metrics.get("volume_ok")),
        "breakout_ok": bool(metrics.get("breakout_ok")),
        "extension_ok": bool(metrics.get("extension_ok")),
        "breakout_path_ok": bool(metrics.get("breakout_path_ok")),
        "pullback_volume_path_ok": bool(metrics.get("pullback_volume_path_ok")),
        "confidence_gate_ok": bool(scores.get("confidence_gate_ok")),
        "triggered": bool(entry_info.get("triggered")),
        "current_blocking_axis": str(entry_info.get("primary_failure_axis") or ""),
        "transition_readiness_score": _optional_float(entry_info.get("transition_readiness_score")),
    }


def _build_monitor_entry_transition_trace(previous_monitor_state: Dict[str, Any], entry_info: Dict[str, Any]) -> Dict[str, Any]:
    previous_entry = (
        dict(previous_monitor_state.get("entry_state") or {})
        if isinstance(previous_monitor_state.get("entry_state"), dict)
        else {}
    )
    thresholds = dict(entry_info.get("thresholds") or {}) if isinstance(entry_info.get("thresholds"), dict) else {}
    current_volume_ratio = _optional_float((entry_info.get("metrics") or {}).get("volume_ratio"))
    current_extended_from_vwap = _optional_float((entry_info.get("metrics") or {}).get("extended_from_vwap_pct"))
    current_breakout_gap = _optional_float((((entry_info.get("threshold_margins") or {}).get("breakout_gap_pct") or {}).get("actual")))
    previous_volume_ratio = _optional_float(previous_entry.get("volume_ratio"))
    previous_extended_from_vwap = _optional_float(previous_entry.get("extended_from_vwap_pct"))
    previous_breakout_gap = _optional_float(previous_entry.get("breakout_gap_pct"))
    volume_ratio_improvement = (
        current_volume_ratio - previous_volume_ratio
        if current_volume_ratio is not None and previous_volume_ratio is not None
        else None
    )
    extended_from_vwap_improvement = (
        current_extended_from_vwap - previous_extended_from_vwap
        if current_extended_from_vwap is not None and previous_extended_from_vwap is not None
        else None
    )
    breakout_gap_improvement = (
        current_breakout_gap - previous_breakout_gap
        if current_breakout_gap is not None and previous_breakout_gap is not None
        else None
    )
    current_ready = bool(entry_info.get("triggered"))
    previous_ready = bool(previous_entry.get("triggered"))
    volume_ratio_min = _optional_float(thresholds.get("volume_ratio_min"))
    volume_recovery_recent = False
    if (
        current_volume_ratio is not None
        and previous_volume_ratio is not None
        and volume_ratio_min is not None
        and volume_ratio_min > 0.0
    ):
        volume_recovery_recent = bool(
            current_volume_ratio > previous_volume_ratio
            and max(current_volume_ratio, previous_volume_ratio) >= (0.75 * volume_ratio_min)
        )
    improving_axes = []
    if extended_from_vwap_improvement is not None and extended_from_vwap_improvement > 0.0:
        improving_axes.append("reclaim")
    if volume_ratio_improvement is not None and volume_ratio_improvement > 0.0:
        improving_axes.append("volume")
    if breakout_gap_improvement is not None and breakout_gap_improvement > 0.0:
        improving_axes.append("breakout")
    last_blocking_axis = str(entry_info.get("primary_failure_axis") or "").strip()
    previous_blocking_axis = str(previous_entry.get("current_blocking_axis") or "").strip()
    if current_ready and not previous_ready and previous_blocking_axis:
        last_blocking_axis = previous_blocking_axis
    elif not last_blocking_axis:
        last_blocking_axis = previous_blocking_axis
    transition_trace = {
        "reclaim_distance_to_ready": entry_info.get("reclaim_distance_to_ready"),
        "vwap_reclaim_progress": entry_info.get("vwap_reclaim_progress"),
        "rebound_progress": entry_info.get("rebound_progress"),
        "volume_distance_to_ready": entry_info.get("volume_distance_to_ready"),
        "breakout_distance_to_ready": entry_info.get("breakout_distance_to_ready"),
        "transition_readiness_score": entry_info.get("transition_readiness_score"),
        "last_blocking_axis": last_blocking_axis,
        "became_ready_this_cycle": bool(current_ready and not previous_ready),
        "extended_from_vwap_improvement": extended_from_vwap_improvement,
        "volume_ratio_improvement": volume_ratio_improvement,
        "breakout_gap_improvement": breakout_gap_improvement,
        "transition_happening_now": bool(
            improving_axes and (current_ready or len(improving_axes) >= 2 or volume_recovery_recent)
        ),
        "volume_recovery_slope": volume_ratio_improvement,
        "volume_recovery_recent": volume_recovery_recent,
    }
    return transition_trace


def _save_current_monitor_state(
    state: Dict[str, Any],
    symbol: str,
    *,
    posture: str,
    reason: str,
    active_exit_axis: str,
    entry_state: Dict[str, Any] | None = None,
) -> None:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = persisted.get("monitor_last_state_by_symbol") if isinstance(persisted.get("monitor_last_state_by_symbol"), dict) else {}
    row = {
        "posture": str(posture or ""),
        "reason": str(reason or ""),
        "active_exit_axis": str(active_exit_axis or ""),
        "updated_at_epoch": int(_resolve_now_epoch(state)),
    }
    if isinstance(entry_state, dict) and entry_state:
        row["entry_state"] = dict(entry_state)
    rows[_norm_symbol(symbol)] = row
    persisted["monitor_last_state_by_symbol"] = rows
    state["persisted_state"] = persisted


def _resolve_cash(state: Dict[str, Any]) -> float:
    risk_context = state.get("risk_context")
    if isinstance(risk_context, dict):
        c = _to_float(risk_context.get("capital_available_for_sizing"))
        if c > 0.0:
            return c
    snapshot = state.get("portfolio_snapshot")
    if isinstance(snapshot, dict):
        c = _to_float(snapshot.get("cash"))
        if c > 0.0:
            return c
    snaps = state.get("snapshots")
    if isinstance(snaps, dict):
        port = snaps.get("portfolio")
        if isinstance(port, dict):
            c = _to_float(port.get("cash"))
            if c > 0.0:
                return c
    return 0.0


def _portfolio_exposure(state: Dict[str, Any], price_fallback: float = 0.0) -> float:
    cash = _resolve_cash(state)
    pos_map = _position_by_symbol(state)
    invested = 0.0
    for row in pos_map.values():
        qty = max(0, _to_int(row.get("qty")))
        if qty <= 0:
            continue
        px = _to_float(row.get("price"))
        if px <= 0.0:
            px = _to_float(row.get("avg_price"))
        if px <= 0.0:
            px = price_fallback
        if px <= 0.0:
            continue
        invested += float(qty) * float(px)
    denom = cash + invested
    if denom <= 0.0:
        return 0.0
    return float(invested / denom)


def _build_sizing_risk_context(state: Dict[str, Any], selected: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    rc = dict(state.get("risk_context") or {}) if isinstance(state.get("risk_context"), dict) else {}
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    if not _has_strategy_policy_content(strategy_policy) and isinstance(state.get("strategy_policy"), dict):
        strategy_policy = dict(state.get("strategy_policy") or {})
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    monitor_policy = state.get("monitor_policy") if isinstance(state.get("monitor_policy"), dict) else {}
    if isinstance(strategy_monitor_policy.get("position_guards"), dict):
        monitor_policy = {**dict(strategy_monitor_policy.get("position_guards") or {}), **monitor_policy}
    if isinstance(strategist_output.get("monitor_policy"), dict):
        monitor_policy = {**dict(strategist_output.get("monitor_policy") or {}), **monitor_policy}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    regime = str(features.get("engine_regime") or selected.get("regime") or policy.get("regime") or "").strip().lower()
    vol20 = _to_float(features.get("engine_volatility20"))
    vol_pct = _to_float(policy.get("volatility_percentile"))
    if vol_pct <= 0.0 and vol20 > 0.0:
        vol_pct = min(max(vol20 / 0.05, 0.0), 1.0)

    price = _resolve_price(
        state,
        symbol,
        selected,
    ) or 0.0
    exposure = _portfolio_exposure(state, price_fallback=float(price))
    corr_bucket = str(policy.get("correlation_bucket") or "medium").strip().lower()
    daily_pnl_ratio = _to_float(rc.get("daily_pnl_ratio"))
    daily_loss_limit = abs(_to_float(policy.get("risk_daily_loss_limit")))
    if daily_loss_limit <= 0.0:
        daily_loss_limit = 0.02
    daily_loss_state = daily_pnl_ratio <= -daily_loss_limit if daily_loss_limit > 0 else False
    degrade_mode = bool(state.get("degrade_mode"))
    rs = state.get("resilience_state") if isinstance(state.get("resilience_state"), dict) else {}
    if str(rs.get("mode") or "").strip().lower() == "degrade":
        degrade_mode = True

    rc.update(
        {
            "regime": regime or None,
            "volatility_percentile": float(vol_pct),
            "portfolio_exposure": float(exposure),
            "correlation_bucket": corr_bucket,
            "daily_loss_state": bool(daily_loss_state),
            "degrade_mode": bool(degrade_mode),
        }
    )
    return rc


def _resolve_position_sizing_config(
    state: Dict[str, Any],
    *,
    policy: Dict[str, Any],
    strategy_policy: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    def _merge(candidate: Any, out: Dict[str, Any]) -> None:
        if isinstance(candidate, dict):
            out.update(dict(candidate))

    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_monitor = applied_policy.get("monitor") if isinstance(applied_policy.get("monitor"), dict) else {}
    applied_entry = applied_monitor.get("entry") if isinstance(applied_monitor.get("entry"), dict) else {}
    strategy_entry = strategy_policy.get("entry_policy") if isinstance(strategy_policy.get("entry_policy"), dict) else {}

    sizing_policy: Dict[str, Any] = {}
    _merge(applied_entry.get("position_sizing"), sizing_policy)
    _merge(applied_policy.get("position_sizing"), sizing_policy)
    _merge(strategy_entry.get("position_sizing"), sizing_policy)
    _merge(policy.get("position_sizing"), sizing_policy)
    _merge(state.get("position_sizing"), sizing_policy)

    for key in (
        "risk_per_trade_ratio",
        "stop_loss_pct",
        "use_structure_stop_loss",
        "use_structure_stop_loss_for_sizing",
        "min_structure_stop_loss_pct",
        "invalidation_price",
        "stop_price",
        "structural_stop_price",
        "position_notional_ratio",
        "max_position_qty",
        "max_order_qty",
        "max_position_notional",
        "max_order_notional",
        "min_position_qty",
        "lot_size",
    ):
        if key in policy and policy.get(key) not in (None, ""):
            sizing_policy[key] = policy.get(key)

    explicit_enabled = None
    if state.get("use_position_sizing") is not None:
        explicit_enabled = _is_trueish(state.get("use_position_sizing"))
    elif policy.get("use_position_sizing") is not None:
        explicit_enabled = _is_trueish(policy.get("use_position_sizing"))

    enabled = bool(explicit_enabled) if explicit_enabled is not None else _is_trueish(sizing_policy.get("enabled"))
    return bool(enabled), sizing_policy


def _is_falseish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("0", "false", "no", "n", "off")


def _entry_context_float(
    selected: Dict[str, Any],
    entry_info: Dict[str, Any],
    key: str,
) -> tuple[float, str]:
    metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    candidates = [
        (metrics.get(key), f"entry.metrics.{key}"),
        (selected.get(key), f"selected.{key}"),
        (features.get(key), f"selected.features.{key}"),
    ]
    if key == "prior_bar_low":
        candidates.append((selected.get("_monitor_prior_bar_low"), "selected._monitor_prior_bar_low"))
    for raw, source in candidates:
        value = _to_float(raw)
        if value > 0.0:
            return float(value), source
    return 0.0, ""


def _derive_position_sizing_stop_context(
    *,
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any],
    entry_info: Dict[str, Any],
    price: float | None,
    sizing_policy: Dict[str, Any],
) -> Dict[str, Any]:
    px = _to_float(price)
    out: Dict[str, Any] = {
        "applied": False,
        "reason": "unavailable",
        "stop_loss_pct": None,
        "invalidation_price": None,
        "stop_loss_source": "",
        "raw_stop_loss_pct": None,
        "min_structure_stop_loss_pct": None,
        "candidates": [],
    }
    if px <= 0.0:
        out["reason"] = "price_unavailable"
        return out
    if _is_falseish(sizing_policy.get("use_structure_stop_loss_for_sizing")) or _is_falseish(
        sizing_policy.get("use_structure_stop_loss")
    ):
        out["reason"] = "disabled_by_policy"
        return out

    candidates: list[Dict[str, Any]] = []

    def add_candidate(name: str, raw: Any, source: str, *, explicit: bool = False) -> None:
        anchor = _to_float(raw)
        if anchor <= 0.0 or anchor >= px:
            return
        pct = (px - anchor) / px
        if pct <= 0.0:
            return
        candidates.append(
            {
                "name": str(name),
                "price": float(anchor),
                "stop_loss_pct": float(pct),
                "source": str(source),
                "explicit": bool(explicit),
            }
        )

    for key in ("invalidation_price", "stop_price", "structural_stop_price"):
        add_candidate(key, sizing_policy.get(key), f"position_sizing.{key}", explicit=True)
        add_candidate(key, selected.get(key), f"selected.{key}", explicit=True)
    explicit_candidates = [row for row in candidates if bool(row.get("explicit"))]
    if explicit_candidates:
        chosen = max(explicit_candidates, key=lambda row: float(row.get("price") or 0.0))
    else:
        metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
        text_bits = [
            str(entry_info.get("pattern") or ""),
            str(entry_info.get("reason") or ""),
            str(entry_info.get("entry_condition_path") or ""),
            " ".join(str(x or "") for x in list(entry_info.get("signal_chain") or [])),
            " ".join(str(x or "") for x in list(entry_info.get("entry_condition_paths_passed") or [])),
        ]
        entry_text = " ".join(text_bits).lower()
        vwap, vwap_source = _entry_context_float(selected, entry_info, "vwap")
        thresholds = entry_info.get("thresholds") if isinstance(entry_info.get("thresholds"), dict) else {}
        reclaim_tolerance_pct = max(0.0, _to_float(thresholds.get("reclaim_tolerance_pct")))
        if vwap > 0.0:
            add_candidate("vwap_floor", vwap * (1.0 - reclaim_tolerance_pct), f"{vwap_source}.reclaim_tolerance")
        for key in ("breakout_level", "recent_high", "prior_bar_high", "prior_bar_low", "current_low"):
            value, source = _entry_context_float(selected, entry_info, key)
            if value > 0.0:
                add_candidate(key, value, source)

        has_breakout = "breakout" in entry_text
        has_vwap = "vwap" in entry_text or bool(metrics.get("vwap_structure_ok"))
        has_pullback = "pullback" in entry_text or "rebound" in entry_text
        preferred_names: set[str] = set()
        if has_breakout:
            preferred_names.update({"breakout_level", "recent_high", "vwap_floor", "prior_bar_low"})
        if has_vwap:
            preferred_names.update({"vwap_floor", "prior_bar_low", "current_low"})
        if has_pullback:
            preferred_names.update({"prior_bar_low", "current_low", "vwap_floor"})
        scoped = [row for row in candidates if str(row.get("name") or "") in preferred_names] if preferred_names else []
        chosen_pool = scoped or candidates
        if not chosen_pool:
            out["reason"] = "no_structure_anchor_below_price"
            return out
        chosen = max(chosen_pool, key=lambda row: float(row.get("price") or 0.0))

    raw_stop_loss_pct = float(chosen.get("stop_loss_pct") or 0.0)
    if raw_stop_loss_pct <= 0.0:
        out["reason"] = "invalid_structure_stop_loss_pct"
        return out
    min_stop_loss_pct = max(0.0, _to_float(sizing_policy.get("min_structure_stop_loss_pct")))
    if min_stop_loss_pct <= 0.0:
        min_stop_loss_pct = 0.008
    stop_loss_pct = max(raw_stop_loss_pct, min_stop_loss_pct)
    invalidation_price = float(px * (1.0 - stop_loss_pct)) if stop_loss_pct > raw_stop_loss_pct else float(chosen["price"])
    stop_loss_source = str(chosen.get("source") or chosen.get("name") or "structure")
    if stop_loss_pct > raw_stop_loss_pct:
        stop_loss_source = f"{stop_loss_source}:min_structure_stop_floor"

    out.update(
        {
            "applied": True,
            "reason": "structure_stop_loss_derived",
            "stop_loss_pct": float(stop_loss_pct),
            "invalidation_price": float(invalidation_price),
            "stop_loss_source": stop_loss_source,
            "raw_stop_loss_pct": float(raw_stop_loss_pct),
            "min_structure_stop_loss_pct": float(min_stop_loss_pct),
            "candidates": candidates[:8],
        }
    )
    return out


def _position_by_symbol(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    snapshot = state.get("portfolio_snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("positions"), list):
        for row in snapshot.get("positions") or []:
            if not isinstance(row, dict):
                continue
            sym = _norm_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
            if not sym:
                continue
            normalized_row = dict(row)
            normalized_row["symbol"] = sym
            out[sym] = normalized_row
        return out

    snaps = state.get("snapshots")
    if isinstance(snaps, dict):
        port = snaps.get("portfolio")
        if isinstance(port, dict) and isinstance(port.get("positions"), list):
            for row in port.get("positions") or []:
                if not isinstance(row, dict):
                    continue
                sym = _norm_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
                if not sym:
                    continue
                normalized_row = dict(row)
                normalized_row["symbol"] = sym
                out[sym] = normalized_row
    return out


def _position_hold_seconds(state: Dict[str, Any], symbol: str, position: Dict[str, Any]) -> int:
    for key in ("hold_sec", "position_age_seconds"):
        hold_sec = _to_int(position.get(key))
        if hold_sec > 0:
            return int(hold_sec)

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    now_epoch = _resolve_now_epoch(state)
    entry_epoch = _to_int(
        position.get("position_entry_epoch")
        if position.get("position_entry_epoch") not in (None, "")
        else position.get("entry_epoch")
    )
    entry_map = (
        persisted.get("position_entry_epoch_by_symbol")
        if isinstance(persisted.get("position_entry_epoch_by_symbol"), dict)
        else {}
    )
    if entry_epoch <= 0:
        entry_epoch = _to_int(entry_map.get(_norm_symbol(symbol)))
    if entry_epoch > 0 and now_epoch > 0:
        return max(0, int(now_epoch - entry_epoch))

    last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
    last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
    last_trade_symbol = _norm_symbol(persisted.get("last_trade_symbol"))
    if (
        last_trade_side == "BUY"
        and last_trade_epoch > 0
        and (not last_trade_symbol or last_trade_symbol == _norm_symbol(symbol))
    ):
        return max(0, int(now_epoch - last_trade_epoch))
    if last_trade_side == "BUY" and last_trade_epoch > 0:
        legacy_age = max(0, int(now_epoch - last_trade_epoch))
        if legacy_age >= 12 * 3600:
            return int(legacy_age)
    return 0


def _apply_position_entry_risk_to_exit_policy(
    state: Dict[str, Any],
    symbol: str,
    exit_policy_map: Dict[str, Any],
) -> Dict[str, Any]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    risk_map = (
        persisted.get("position_entry_risk_by_symbol")
        if isinstance(persisted.get("position_entry_risk_by_symbol"), dict)
        else {}
    )
    entry_risk = risk_map.get(_norm_symbol(symbol)) if isinstance(risk_map, dict) else {}
    if not isinstance(entry_risk, dict):
        return exit_policy_map
    entry_stop = _to_float(entry_risk.get("stop_loss_pct"))
    if entry_stop <= 0.0:
        return exit_policy_map

    out = dict(exit_policy_map or {})
    current_stop = _to_float(out.get("stop_loss_pct"))
    if current_stop <= 0.0 or entry_stop < current_stop:
        out["stop_loss_pct"] = float(entry_stop)
        out["position_entry_risk_applied"] = True
    else:
        out["position_entry_risk_applied"] = False
    out["position_entry_stop_loss_pct"] = float(entry_stop)
    out["position_entry_stop_loss_source"] = str(entry_risk.get("stop_loss_source") or entry_risk.get("source") or "")
    if entry_risk.get("invalidation_price") not in (None, ""):
        out["position_entry_invalidation_price"] = entry_risk.get("invalidation_price")
    if entry_risk.get("raw_structure_stop_loss_pct") not in (None, ""):
        out["position_entry_raw_structure_stop_loss_pct"] = entry_risk.get("raw_structure_stop_loss_pct")
    if entry_risk.get("min_structure_stop_loss_pct") not in (None, ""):
        out["position_entry_min_structure_stop_loss_pct"] = entry_risk.get("min_structure_stop_loss_pct")
    return out


def _preview_exit_decision_for_symbol(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
) -> Dict[str, Any]:
    qty = max(0, _to_int(position.get("qty")))
    avg_price = _to_float(position.get("avg_price"))
    selected_for_exit = _monitor_selected_snapshot_for_symbol(
        state,
        symbol,
        selected if isinstance(selected, dict) else None,
        position=position,
    )
    price, price_source = _resolve_price_with_source(
        state,
        symbol,
        selected_for_exit,
        position=position,
    )
    if price is None or _to_float(price) <= 0.0:
        pos_mark, pos_mark_source = _position_mark_price_with_source(position)
        if pos_mark is not None and pos_mark > 0.0:
            price = float(pos_mark)
            price_source = str(pos_mark_source or "position_mark")
    if _to_float(price) > 0.0 and avg_price > 0.0:
        peak_price = _update_position_peak_price(
            state,
            symbol,
            avg_price=avg_price,
            observed_price=_to_float(price),
        )
    else:
        peak_price = 0.0

    features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
    feature_source = str(selected_for_exit.get("_monitor_feature_source") or "none")
    hold_sec = _position_hold_seconds(state, symbol, position)
    if hold_sec <= 0:
        hold_sec = _to_int(state.get("position_hold_sec"))

    exit_policy_map = dict(exit_policy_base or {})
    quotes, _quote_meta = extract_market_quotes(state)
    quote = quotes.get(_norm_symbol(symbol)) if isinstance(quotes.get(_norm_symbol(symbol)), dict) else {}
    if quote:
        for source_key, policy_key in (
            ("best_bid", "expected_exit_best_bid"),
            ("bid", "expected_exit_best_bid"),
            ("bid_price", "expected_exit_best_bid"),
            ("best_ask", "expected_exit_best_ask"),
            ("ask", "expected_exit_best_ask"),
            ("ask_price", "expected_exit_best_ask"),
            ("spread_bps", "expected_exit_spread_bps"),
        ):
            value = quote.get(source_key)
            if value not in (None, "") and _to_float(value) > 0.0:
                exit_policy_map.setdefault(policy_key, value)
    if position.get("peak_price") is not None:
        exit_policy_map.setdefault("peak_price", position.get("peak_price"))
    elif position.get("high_water_mark") is not None:
        exit_policy_map.setdefault("peak_price", position.get("high_water_mark"))
    elif peak_price > 0.0:
        exit_policy_map.setdefault("peak_price", peak_price)
    else:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        peak_map = persisted.get("position_peak_price") if isinstance(persisted.get("position_peak_price"), dict) else {}
        if peak_map.get(symbol) is not None:
            exit_policy_map.setdefault("peak_price", peak_map.get(symbol))
    if features.get("engine_volatility20") is not None:
        exit_policy_map.setdefault("current_volatility", features.get("engine_volatility20"))
    if features.get("engine_vwap_distance") is not None:
        exit_policy_map.setdefault("vwap_distance", features.get("engine_vwap_distance"))
    if features.get("engine_trend_strength") is not None:
        exit_policy_map.setdefault("trend_strength", features.get("engine_trend_strength"))
    for signal_key in (
        "volume_ratio",
        "execution_strength",
        "trade_strength",
        "previous_close",
        "open_gap_pct",
        "prev_close_distance_pct",
        "opening_gap_chase_observed",
        "minutes_since_session_open",
    ):
        value = selected_for_exit.get(signal_key)
        if value in (None, ""):
            value = features.get(signal_key)
        if value in (None, ""):
            entry_info = state.get("monitor_entry") if isinstance(state.get("monitor_entry"), dict) else {}
            entry_metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
            value = entry_metrics.get(signal_key)
        if value not in (None, ""):
            exit_policy_map.setdefault(signal_key, value)
    for resistance_key in (
        "resistance_price",
        "target_resistance_price",
        "upper_resistance_price",
        "day_high",
        "intraday_high",
        "recent_high",
        "breakout_level",
        "prior_bar_high",
    ):
        value = selected_for_exit.get(resistance_key)
        if value in (None, ""):
            value = features.get(resistance_key)
        if value not in (None, "") and _to_float(value) > 0.0:
            exit_policy_map.setdefault(resistance_key, value)
    prior_bar_low = _to_float(selected_for_exit.get("_monitor_prior_bar_low"))
    if prior_bar_low > 0.0:
        exit_policy_map.setdefault("prior_bar_low", prior_bar_low)
    if state.get("policy") and isinstance(state.get("policy"), dict):
        policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
        if policy.get("exit_policy_baseline_volatility") is not None:
            exit_policy_map.setdefault("baseline_volatility", policy.get("exit_policy_baseline_volatility"))
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    partial_taken_map = (
        persisted.get("partial_take_profit_taken_by_symbol")
        if isinstance(persisted.get("partial_take_profit_taken_by_symbol"), dict)
        else {}
    )
    if partial_taken_map.get(symbol) not in (None, ""):
        exit_policy_map.setdefault("partial_take_profit_taken", True)
    ladder_taken_map = (
        persisted.get("profit_ladder_taken_levels_by_symbol")
        if isinstance(persisted.get("profit_ladder_taken_levels_by_symbol"), dict)
        else {}
    )
    if isinstance(ladder_taken_map.get(symbol), list):
        exit_policy_map.setdefault("profit_ladder_taken_levels", list(ladder_taken_map.get(symbol) or []))
    rr_taken_map = (
        persisted.get("risk_reward_take_profit_taken_rungs_by_symbol")
        if isinstance(persisted.get("risk_reward_take_profit_taken_rungs_by_symbol"), dict)
        else {}
    )
    if isinstance(rr_taken_map.get(symbol), list):
        exit_policy_map.setdefault("risk_reward_take_profit_taken_rungs", list(rr_taken_map.get(symbol) or []))
    if state.get("emergency_halt") is not None:
        exit_policy_map.setdefault("emergency_halt", state.get("emergency_halt"))
    mctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    if mctx.get("minutes_to_close") is not None:
        exit_policy_map.setdefault("minutes_to_close", mctx.get("minutes_to_close"))
    exit_policy_map = _apply_position_entry_risk_to_exit_policy(state, symbol, exit_policy_map)
    exit_policy_map = apply_account_pnl_crosscheck_context(
        exit_policy_map,
        position=position,
    )

    decision = evaluate_exit_policy(
        price=price,
        avg_price=avg_price if avg_price > 0.0 else None,
        qty=qty,
        hold_sec=hold_sec if hold_sec > 0 else None,
        policy=exit_policy_map,
    )
    resolved_peak_price = _to_float(exit_policy_map.get("peak_price"))
    if resolved_peak_price <= 0.0:
        resolved_peak_price = float(peak_price)
    decision["_qty"] = int(qty)
    decision["_price"] = float(price) if price is not None and _to_float(price) > 0.0 else None
    decision["_avg_price"] = float(avg_price) if avg_price > 0.0 else None
    decision["_peak_price"] = float(resolved_peak_price) if resolved_peak_price > 0.0 else None
    decision["_hold_sec"] = int(hold_sec) if hold_sec > 0 else None
    decision["_pnl_ratio"] = _to_float(decision.get("pnl_ratio"))
    decision["_price_source"] = str(price_source or "unavailable")
    decision["_feature_source"] = str(feature_source or "none")
    decision["position_entry_risk_applied"] = bool(exit_policy_map.get("position_entry_risk_applied"))
    decision["position_entry_stop_loss_pct"] = exit_policy_map.get("position_entry_stop_loss_pct")
    decision["position_entry_stop_loss_source"] = str(exit_policy_map.get("position_entry_stop_loss_source") or "")
    decision["position_entry_invalidation_price"] = exit_policy_map.get("position_entry_invalidation_price")
    return decision


def _update_position_peak_price(
    state: Dict[str, Any],
    symbol: str,
    *,
    avg_price: float,
    observed_price: float,
) -> float:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    peak_map = persisted.get("position_peak_price") if isinstance(persisted.get("position_peak_price"), dict) else {}
    sym = _norm_symbol(symbol)
    cur_peak = _to_float(peak_map.get(sym))
    next_peak = max(cur_peak, _to_float(avg_price), _to_float(observed_price))
    if sym and next_peak > 0.0:
        peak_map[sym] = float(next_peak)
        persisted["position_peak_price"] = peak_map
        state["persisted_state"] = persisted
    return float(next_peak)


def _ensure_position_peak_price_map(
    state: Dict[str, Any],
    pos_map: Dict[str, Dict[str, Any]],
) -> Dict[str, float]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_peak_map = persisted.get("position_peak_price") if isinstance(persisted.get("position_peak_price"), dict) else {}
    next_peak_map: Dict[str, float] = {}
    for sym, row in pos_map.items():
        if max(0, _to_int((row or {}).get("qty"))) <= 0:
            continue
        key = _norm_symbol(sym)
        if not key:
            continue
        peak = _to_float(raw_peak_map.get(key))
        avg_price = _to_float((row or {}).get("avg_price"))
        position_peak = _to_float((row or {}).get("peak_price"))
        high_water_mark = _to_float((row or {}).get("high_water_mark"))
        next_peak = max(peak, avg_price, position_peak, high_water_mark)
        if next_peak > 0.0:
            next_peak_map[key] = float(next_peak)
    if next_peak_map:
        persisted["position_peak_price"] = next_peak_map
    else:
        persisted.pop("position_peak_price", None)
    state["persisted_state"] = persisted
    return next_peak_map


def _exit_reason_priority(reason: str) -> int:
    r = str(reason or "").strip().lower()
    order = {
        "emergency_halt": 100,
        "news_shock": 95,
        "eod_flat": 90,
        "time_stop": 80,
        "max_hold": 75,
        "hard_stop": 72,
        "stop_loss": 70,
        "intraday_low_break": 69,
        "trend_breakdown": 68,
        "peak_drawdown": 67,
        "vwap_breakdown": 66,
        "volatility_expansion": 65,
        "trailing_stop": 60,
        "volume_exhaustion_take_profit": 59,
        "opening_gap_profit_take": 59,
        "vwap_extension_take_profit": 58,
        "resistance_take_profit": 57,
        "risk_reward_take_profit": 56,
        "profit_ladder": 55,
        "partial_take_profit": 55,
        "time_decay_profit_exit": 55,
        "take_profit": 50,
        "hold": 10,
        "price_unavailable": 5,
        "no_position": 0,
    }
    return int(order.get(r, 1))


def _is_soft_profit_exit_reason(reason: Any) -> bool:
    return str(reason or "").strip().lower() in {
        "take_profit",
        "partial_take_profit",
        "profit_ladder",
        "risk_reward_take_profit",
        "vwap_extension_take_profit",
        "resistance_take_profit",
        "volume_exhaustion_take_profit",
        "opening_gap_profit_take",
        "time_decay_profit_exit",
    }


def _persist_overnight_decision(
    state: Dict[str, Any],
    *,
    symbol: str,
    decision: Dict[str, Any] | None = None,
    clear: bool = False,
) -> None:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = (
        persisted.get("overnight_decision_by_symbol")
        if isinstance(persisted.get("overnight_decision_by_symbol"), dict)
        else {}
    )
    key = _norm_symbol(symbol)
    if not key:
        return
    if clear:
        rows.pop(key, None)
    elif isinstance(decision, dict) and decision:
        rows[key] = dict(decision)
    if rows:
        persisted["overnight_decision_by_symbol"] = rows
    else:
        persisted.pop("overnight_decision_by_symbol", None)
    state["persisted_state"] = persisted


def _evaluate_overnight_carry_decision(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
    primary_decision: Dict[str, Any],
    frame: Dict[str, Any],
    hold_sec: int,
) -> Dict[str, Any]:
    thresholds = primary_decision.get("thresholds") if isinstance(primary_decision.get("thresholds"), dict) else {}
    minutes_to_close = _optional_float(primary_decision.get("minutes_to_close"))
    if minutes_to_close is None:
        minutes_to_close = _optional_float(exit_policy_base.get("minutes_to_close"))
    cutoff_min = int(_to_float(thresholds.get("eod_flat_cutoff_min") or exit_policy_base.get("eod_flat_cutoff_min") or 10))
    use_eod_flat = bool(exit_policy_base.get("use_eod_flat"))
    qty = max(0, _to_int(position.get("qty")))
    calendar_context = _carry_calendar_context(state)
    weekend_carry = bool(calendar_context.get("weekend_carry"))
    allow_weekend_carry = (
        _is_trueish(exit_policy_base.get("allow_weekend_carry"))
        or _is_trueish(frame.get("allow_weekend_carry"))
        or _is_trueish(state.get("allow_weekend_carry"))
    )
    out: Dict[str, Any] = {
        "evaluated": False,
        "approved": False,
        "action": "not_applicable",
        "reason": "",
        "anomaly": False,
        "anomaly_reason": "",
        "minutes_to_close": minutes_to_close,
        "cutoff_min": int(cutoff_min),
        "positive_signals": [],
        "blockers": [],
        "non_eod_reason": "",
        "non_eod_triggered": False,
        "pnl_ratio": None,
        "trend_strength": None,
        "vwap_distance": None,
        "peak_drawdown": None,
        "playbook": str(frame.get("playbook") or ""),
        "monitor_guidance": str(frame.get("monitor_guidance") or ""),
        "risk_tone": str(frame.get("risk_tone") or ""),
        "carry_calendar": dict(calendar_context),
        "weekend_carry": bool(weekend_carry),
        "allow_weekend_carry": bool(allow_weekend_carry),
        "holding_gap_days": int(calendar_context.get("holding_gap_days") or 1),
    }
    if qty <= 0 or (not use_eod_flat) or minutes_to_close is None or minutes_to_close < 0.0 or minutes_to_close > float(cutoff_min):
        if qty > 0 and bool(use_eod_flat) and minutes_to_close is None:
            out["anomaly"] = True
            out["anomaly_reason"] = "minutes_to_close_missing"
        return out

    out["evaluated"] = True
    out["action"] = "flatten_before_close"

    no_eod_policy = dict(exit_policy_base or {})
    no_eod_policy["use_eod_flat"] = False
    no_eod_policy["minutes_to_close"] = float(minutes_to_close)
    no_eod_policy = apply_account_pnl_crosscheck_context(
        no_eod_policy,
        position=position,
    )
    risk_decision = evaluate_exit_policy(
        price=primary_decision.get("_price"),
        avg_price=primary_decision.get("_avg_price"),
        qty=qty,
        hold_sec=hold_sec if hold_sec > 0 else None,
        policy=no_eod_policy,
    )
    out["non_eod_reason"] = str(risk_decision.get("reason") or "")
    out["non_eod_triggered"] = bool(risk_decision.get("triggered"))

    pnl_ratio = _optional_float(risk_decision.get("pnl_ratio"))
    trend_strength = _optional_float(((selected or {}).get("features") or {}).get("engine_trend_strength"))
    vwap_distance = _optional_float(((selected or {}).get("features") or {}).get("engine_vwap_distance"))
    peak_drawdown = _optional_float(risk_decision.get("peak_drawdown"))
    out["pnl_ratio"] = pnl_ratio
    out["trend_strength"] = trend_strength
    out["vwap_distance"] = vwap_distance
    out["peak_drawdown"] = peak_drawdown

    blockers: list[str] = []
    positives: list[str] = []
    if bool(risk_decision.get("triggered")):
        risk_reason = str(risk_decision.get("reason") or "unknown")
        if _is_soft_profit_exit_reason(risk_reason):
            positives.append(f"soft_profit_exit_available:{risk_reason}")
            out["non_eod_triggered"] = False
        else:
            blockers.append(f"underlying_exit_signal:{risk_reason}")
    if str(frame.get("monitor_guidance") or "").strip().lower() == "defensive_exit":
        blockers.append("monitor_guidance:defensive_exit")
    if str(frame.get("playbook") or "").strip().lower() == "defensive":
        blockers.append("playbook:defensive")
    if str(frame.get("risk_tone") or "").strip().lower() == "conservative":
        blockers.append("risk_tone:conservative")

    if pnl_ratio is None:
        blockers.append("pnl:unavailable")
    elif pnl_ratio < -0.003:
        blockers.append(f"pnl_below_carry_floor:{pnl_ratio:.4f}")
    else:
        positives.append(f"pnl_ok:{pnl_ratio:.4f}")

    if trend_strength is not None:
        if trend_strength < 0.05:
            blockers.append(f"trend_strength_weak:{trend_strength:.4f}")
        else:
            positives.append(f"trend_strength_ok:{trend_strength:.4f}")

    if vwap_distance is not None:
        if vwap_distance < -0.003:
            blockers.append(f"vwap_below_floor:{vwap_distance:.4f}")
        else:
            positives.append(f"vwap_ok:{vwap_distance:.4f}")

    if peak_drawdown is not None:
        if peak_drawdown < -0.012:
            blockers.append(f"peak_drawdown_too_deep:{peak_drawdown:.4f}")
        else:
            positives.append(f"peak_drawdown_ok:{peak_drawdown:.4f}")

    if weekend_carry:
        if not allow_weekend_carry:
            blockers.append("weekend_carry_not_allowed:friday")
        else:
            weekend_pnl_floor = _optional_float(exit_policy_base.get("weekend_carry_min_pnl_ratio"))
            if weekend_pnl_floor is None:
                weekend_pnl_floor = _optional_float(frame.get("weekend_carry_min_pnl_ratio"))
            if weekend_pnl_floor is None:
                weekend_pnl_floor = 0.005
            weekend_trend_floor = _optional_float(exit_policy_base.get("weekend_carry_min_trend_strength"))
            if weekend_trend_floor is None:
                weekend_trend_floor = _optional_float(frame.get("weekend_carry_min_trend_strength"))
            if weekend_trend_floor is None:
                weekend_trend_floor = 0.15
            if pnl_ratio is None or pnl_ratio < float(weekend_pnl_floor):
                blockers.append(f"weekend_pnl_buffer_insufficient:{(pnl_ratio if pnl_ratio is not None else 0.0):.4f}")
            else:
                positives.append(f"weekend_pnl_buffer_ok:{pnl_ratio:.4f}")
            if trend_strength is None or trend_strength < float(weekend_trend_floor):
                blockers.append(
                    f"weekend_trend_buffer_insufficient:{(trend_strength if trend_strength is not None else 0.0):.4f}"
                )
            else:
                positives.append(f"weekend_trend_buffer_ok:{trend_strength:.4f}")
            if vwap_distance is None or vwap_distance < 0.0:
                blockers.append(
                    f"weekend_vwap_buffer_insufficient:{(vwap_distance if vwap_distance is not None else 0.0):.4f}"
                )
            else:
                positives.append(f"weekend_vwap_buffer_ok:{vwap_distance:.4f}")

    playbook = str(frame.get("playbook") or "").strip().lower()
    if playbook in ("breakout", "pullback"):
        positives.append(f"playbook:{playbook}")
    guidance = str(frame.get("monitor_guidance") or "").strip().lower()
    if guidance in ("hold_through_noise", "trend_follow"):
        positives.append(f"monitor_guidance:{guidance}")

    out["positive_signals"] = list(positives)
    out["blockers"] = list(blockers)
    if not blockers and len(positives) >= 2:
        out["approved"] = True
        out["action"] = "carry_overnight"
        out["reason"] = "carry_overnight_approved"
    else:
        out["approved"] = False
        out["action"] = "flatten_before_close"
        out["reason"] = str(blockers[0] if blockers else "carry_conditions_not_met")
    return out


def _persist_eod_carry_decisions_for_open_positions(
    *,
    state: Dict[str, Any],
    pos_map: Dict[str, Dict[str, Any]],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
    frame: Dict[str, Any],
    now_epoch: int,
) -> Dict[str, Any]:
    rows: list[Dict[str, Any]] = []
    selected_symbol = _norm_symbol((selected or {}).get("symbol")) if isinstance(selected, dict) else ""
    for sym, pos in sorted(pos_map.items()):
        symbol = _norm_symbol(sym)
        if not symbol or max(0, _to_int((pos or {}).get("qty"))) <= 0:
            continue
        selected_for_symbol = selected if selected_symbol == symbol else {"symbol": symbol}
        decision = _preview_exit_decision_for_symbol(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_symbol,
            exit_policy_base=exit_policy_base,
        )
        hold_sec = _to_int(decision.get("_hold_sec"))
        if hold_sec <= 0:
            hold_sec = _position_hold_seconds(state, symbol, pos)
        eod_carry = _evaluate_overnight_carry_decision(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_symbol,
            exit_policy_base=exit_policy_base,
            primary_decision=decision,
            frame=frame,
            hold_sec=hold_sec,
        )
        if not bool(eod_carry.get("evaluated")):
            continue
        payload = {
            "approved": bool(eod_carry.get("approved")),
            "action": str(eod_carry.get("action") or ""),
            "reason": str(eod_carry.get("reason") or ""),
            "minutes_to_close": eod_carry.get("minutes_to_close"),
            "cutoff_min": eod_carry.get("cutoff_min"),
            "positive_signals": list(eod_carry.get("positive_signals") or []),
            "blockers": list(eod_carry.get("blockers") or []),
            "carry_calendar": dict(eod_carry.get("carry_calendar") or {}),
            "weekend_carry": bool(eod_carry.get("weekend_carry")),
            "allow_weekend_carry": bool(eod_carry.get("allow_weekend_carry")),
            "holding_gap_days": eod_carry.get("holding_gap_days"),
            "decided_at_epoch": int(now_epoch),
            "symbol": str(symbol or ""),
        }
        _persist_overnight_decision(state, symbol=symbol, decision=payload)
        rows.append(payload)
    return {
        "evaluated_count": len(rows),
        "symbols": [str(row.get("symbol") or "") for row in rows],
        "decisions": rows,
    }


def _select_exit_symbol(
    selected_symbol: str,
    pos_map: Dict[str, Dict[str, Any]],
    *,
    state: Dict[str, Any] | None = None,
    selected: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    exit_policy_base: Dict[str, Any] | None = None,
) -> str:
    sel = _norm_symbol(selected_symbol)
    if state is None and sel and max(0, _to_int((pos_map.get(sel) or {}).get("qty"))) > 0:
        return sel

    held_symbols = [
        _norm_symbol(sym)
        for sym, row in pos_map.items()
        if max(0, _to_int((row or {}).get("qty"))) > 0
    ]
    held_symbols = [s for s in held_symbols if s]
    if not held_symbols:
        return sel

    if state is None:
        # Backward-compatible fallback.
        best_symbol = ""
        best_qty = 0
        for sym, row in pos_map.items():
            qty = max(0, _to_int((row or {}).get("qty")))
            if qty > best_qty:
                best_qty = qty
                best_symbol = _norm_symbol(sym)
        return best_symbol or sel

    base = exit_policy_base if isinstance(exit_policy_base, dict) else {}
    selected_raw = selected if isinstance(selected, dict) else {}
    selected_raw_symbol = _norm_symbol(selected_raw.get("symbol"))
    best_symbol = held_symbols[0]
    best_rank = (-1, -1, -1.0, -1, -1)
    for sym in held_symbols:
        pos = dict(pos_map.get(sym) or {})
        selected_for_exit = selected_raw if selected_raw_symbol == sym else {"symbol": sym}
        decision = _preview_exit_decision_for_symbol(
            state=state,
            symbol=sym,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=base,
        )
        triggered = 1 if bool(decision.get("triggered")) else 0
        reason_priority = _exit_reason_priority(str(decision.get("reason") or ""))
        pnl_mag = abs(_to_float(decision.get("_pnl_ratio")))
        selected_bonus = 1 if sym == sel else 0
        qty = max(0, _to_int(decision.get("_qty")))
        rank = (triggered, reason_priority, pnl_mag, selected_bonus, qty)
        if rank > best_rank:
            best_rank = rank
            best_symbol = sym
    if best_symbol:
        return best_symbol
    return sel


def _resolve_price(
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None = None,
) -> float | None:
    price, _source = _resolve_price_with_source(state, symbol, selected, position=position)
    return price


def _resolve_price_with_source(
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None = None,
) -> tuple[float | None, str]:
    sym = _norm_symbol(symbol)
    if not sym:
        return None, "no_symbol"

    quotes, _meta = extract_market_quotes(state)
    q = quotes.get(sym)
    if isinstance(q, dict):
        for k in ("price", "cur"):
            if q.get(k) is not None:
                p = _to_float(q.get(k))
                if p > 0.0:
                    return p, f"market.quote.{k}"

    if isinstance(position, dict):
        pos_live_price, pos_live_source = _position_live_price_with_source(position)
        if pos_live_price is not None and pos_live_price > 0.0:
            return pos_live_price, pos_live_source

    selected_symbol = _norm_symbol((selected or {}).get("symbol")) if isinstance(selected, dict) else ""
    selected_matches = bool(selected_symbol and selected_symbol == sym)
    if isinstance(selected, dict) and selected_matches:
        direct = selected.get("price")
        if direct is not None:
            p = _to_float(direct)
            if p > 0.0:
                source_hint = str(selected.get("_monitor_price_source") or "").strip()
                return p, (source_hint or "selected.price")
        features = selected.get("features")
        if isinstance(features, dict):
            x = features.get("skill_quote_price")
            if x is not None:
                p = _to_float(x)
                if p > 0.0:
                    source_hint = str(selected.get("_monitor_price_source") or "").strip()
                    return p, (source_hint or "selected.features.skill_quote_price")

    mkt = state.get("market_snapshot")
    if isinstance(mkt, dict):
        ms = _norm_symbol(mkt.get("symbol"))
        px = mkt.get("price")
        if ms == sym and px is not None:
            p = _to_float(px)
            if p > 0.0:
                return p, "market_snapshot"

    minute_rows_by_symbol, minute_meta = extract_minute_ohlcv_by_symbol(state)
    minute_rows = minute_rows_by_symbol.get(sym) if isinstance(minute_rows_by_symbol, dict) else None
    if isinstance(minute_rows, list) and minute_rows:
        latest = minute_rows[-1] if isinstance(minute_rows[-1], dict) else {}
        close_px = _to_float(latest.get("close"))
        if close_px > 0.0:
            source = str((minute_meta or {}).get("source") or "minute_ohlcv_by_symbol").strip() or "minute_ohlcv_by_symbol"
            return close_px, f"{source}.close"
    return None, "unavailable"


def _feature_alias_map(feature_row: Dict[str, Any], *, quote: Dict[str, Any] | None = None) -> Dict[str, Any]:
    row = dict(feature_row or {})
    q = dict(quote or {})
    out = {
        "engine_rsi14": row.get("engine_rsi14", row.get("rsi14")),
        "engine_ma20_gap": row.get("engine_ma20_gap", row.get("ma20_gap")),
        "engine_ma60": row.get("engine_ma60", row.get("ma60")),
        "engine_ma120": row.get("engine_ma120", row.get("ma120")),
        "engine_adx14": row.get("engine_adx14", row.get("adx14")),
        "engine_trend_strength": row.get("engine_trend_strength", row.get("trend_strength")),
        "engine_atr14": row.get("engine_atr14", row.get("atr14")),
        "engine_volume_spike20": row.get("engine_volume_spike20", row.get("volume_spike20")),
        "engine_volatility20": row.get("engine_volatility20", row.get("volatility20")),
        "engine_realized_volatility": row.get("engine_realized_volatility", row.get("realized_volatility")),
        "engine_vwap_distance": row.get("engine_vwap_distance", row.get("vwap_distance")),
        "engine_rolling_drawdown20": row.get("engine_rolling_drawdown20", row.get("rolling_drawdown20")),
        "engine_cross_section_rank": row.get("engine_cross_section_rank", row.get("cross_section_rank")),
        "engine_regime": row.get("engine_regime", row.get("regime")),
        "engine_signal_score": row.get("engine_signal_score", row.get("signal_score")),
        "volume_ratio": row.get("volume_ratio", row.get("engine_volume_ratio")),
        "execution_strength": row.get("execution_strength", row.get("trade_strength")),
        "trade_strength": row.get("trade_strength"),
        "previous_close": row.get("previous_close"),
        "open_gap_pct": row.get("open_gap_pct"),
        "prev_close_distance_pct": row.get("prev_close_distance_pct"),
        "opening_gap_chase_observed": row.get("opening_gap_chase_observed"),
        "minutes_since_session_open": row.get("minutes_since_session_open"),
        "recent_high": row.get("recent_high"),
        "breakout_level": row.get("breakout_level"),
        "prior_bar_high": row.get("prior_bar_high"),
        "day_high": row.get("day_high", row.get("high_price")),
        "intraday_high": row.get("intraday_high"),
        "resistance_price": row.get("resistance_price"),
        "target_resistance_price": row.get("target_resistance_price"),
        "upper_resistance_price": row.get("upper_resistance_price"),
    }
    if q:
        quote_price = q.get("price")
        if quote_price is None:
            quote_price = q.get("cur")
        out["skill_quote_price"] = quote_price
        out["intraday_change_pct"] = q.get("change_pct")
        out["quote_volume"] = q.get("volume")
        out["quote_trading_value"] = q.get("value")
    return out


def _feature_context_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    market_ctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    out: Dict[str, Any] = {}
    if market_ctx.get("global_sentiment") is not None:
        out["global_sentiment"] = market_ctx.get("global_sentiment")
    if market_ctx.get("market_breadth") is not None:
        out["market_breadth"] = market_ctx.get("market_breadth")
    if market_ctx.get("index_trend") is not None:
        out["index_trend"] = market_ctx.get("index_trend")
    if market_ctx.get("realized_volatility") is not None:
        out["realized_volatility"] = market_ctx.get("realized_volatility")
    if not out:
        gs = state.get("global_sentiment")
        if isinstance(gs, dict) and gs.get("score") is not None:
            out["global_sentiment"] = gs.get("score")
    return out


def _feature_row_for_symbol(state: Dict[str, Any], symbol: str) -> tuple[Dict[str, Any], str]:
    sym = _norm_symbol(symbol)
    if not sym:
        return {}, "none"

    feature_engine = state.get("feature_engine") if isinstance(state.get("feature_engine"), dict) else {}
    by_symbol = feature_engine.get("by_symbol") if isinstance(feature_engine.get("by_symbol"), dict) else {}
    direct = by_symbol.get(sym)
    if isinstance(direct, dict) and direct:
        return dict(direct), "feature_engine.by_symbol"

    ohlcv_by_symbol = state.get("ohlcv_by_symbol") if isinstance(state.get("ohlcv_by_symbol"), dict) else {}
    rows = ohlcv_by_symbol.get(sym)
    if isinstance(rows, list) and rows:
        try:
            return build_feature_row(rows, **_feature_context_from_state(state)), "ohlcv_by_symbol"
        except Exception:
            return {}, "ohlcv_build_failed"

    return {}, "none"


def _prior_bar_low_for_symbol(state: Dict[str, Any], symbol: str) -> float | None:
    sym = _norm_symbol(symbol)
    if not sym:
        return None
    ohlcv_by_symbol = state.get("ohlcv_by_symbol") if isinstance(state.get("ohlcv_by_symbol"), dict) else {}
    rows = ohlcv_by_symbol.get(sym)
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    prior = rows[-2] if isinstance(rows[-2], dict) else {}
    low = _to_float(prior.get("low"))
    if low > 0.0:
        return float(low)
    return None


def _monitor_selected_snapshot_for_symbol(
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    sym = _norm_symbol(symbol)
    selected_symbol = _norm_symbol((selected or {}).get("symbol")) if isinstance(selected, dict) else ""
    selected_matches = bool(selected_symbol and selected_symbol == sym)
    base = dict(selected or {}) if selected_matches else {}
    base["symbol"] = sym

    quotes, _meta = extract_market_quotes(state)
    quote = quotes.get(sym) if isinstance(quotes.get(sym), dict) else {}

    price, price_source = _resolve_price_with_source(state, sym, selected, position=position)
    if price is not None and _to_float(price) > 0.0:
        base["price"] = float(price)

    features = base.get("features") if isinstance(base.get("features"), dict) else {}
    feature_source = "selected.features" if features else "none"
    if not features:
        feature_row, feature_source = _feature_row_for_symbol(state, sym)
        if feature_row:
            features = _feature_alias_map(feature_row, quote=quote)
    elif quote:
        enriched = dict(features)
        quote_alias = _feature_alias_map({}, quote=quote)
        for key, value in quote_alias.items():
            if value in (None, ""):
                continue
            if key in {"skill_quote_price", "intraday_change_pct", "quote_volume", "quote_trading_value"}:
                enriched[key] = value
            elif enriched.get(key) in (None, ""):
                enriched[key] = value
        features = enriched

    if features:
        base["features"] = dict(features)
    base["_monitor_price_source"] = str(price_source)
    base["_monitor_feature_source"] = str(feature_source)
    prior_bar_low = _prior_bar_low_for_symbol(state, sym)
    if prior_bar_low is not None and prior_bar_low > 0.0:
        base["_monitor_prior_bar_low"] = float(prior_bar_low)
    return base


def _position_mark_price(position: Dict[str, Any] | None) -> float | None:
    price, _source = _position_mark_price_with_source(position)
    return price


def _position_live_price_with_source(position: Dict[str, Any] | None) -> tuple[float | None, str]:
    if not isinstance(position, dict):
        return None, "no_position"
    for key in ("price", "cur_price", "last_price", "current_price"):
        p = _to_float(position.get(key))
        if p > 0.0:
            return p, f"position.{key}"
    return None, "position_live_price_unavailable"


def _position_mark_price_with_source(position: Dict[str, Any] | None) -> tuple[float | None, str]:
    direct_price, direct_source = _position_live_price_with_source(position)
    if direct_price is not None and direct_price > 0.0:
        return direct_price, direct_source
    if not isinstance(position, dict):
        return None, "no_position"
    qty = max(0, _to_int(position.get("qty")))
    avg_price = _to_float(position.get("avg_price"))
    unrealized = _to_float(position.get("unrealized_pnl"))
    if qty > 0 and avg_price > 0.0:
        mark = avg_price + (unrealized / float(qty))
        if mark > 0.0:
            return mark, "position.avg_plus_unrealized"
    return None, "position_mark_unavailable"


def _derive_order_lifecycle(order_status: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(order_status, dict):
        return None

    status = _normalize_status(order_status.get("status"))
    filled_qty = max(0, _to_int(order_status.get("filled_qty")))
    order_qty = max(0, _to_int(order_status.get("order_qty")))

    if order_qty > 0:
        progress = min(1.0, float(filled_qty) / float(order_qty))
    else:
        progress = 0.0

    cancelled_keys = ("CANCEL", "CANCELED", "CANCELLED")
    rejected_keys = ("REJECT", "DENY", "BLOCK")
    filled_keys = ("FILLED", "DONE")
    partial_keys = ("PARTIAL", "WORKING_PARTIAL")

    stage = "working"
    terminal = False

    if any(k in status for k in cancelled_keys):
        stage = "cancelled"
        terminal = True
    elif any(k in status for k in rejected_keys):
        stage = "rejected"
        terminal = True
    elif (order_qty > 0 and filled_qty >= order_qty) or any(k in status for k in filled_keys):
        stage = "filled"
        terminal = True
        progress = 1.0
    elif (filled_qty > 0 and order_qty > 0 and filled_qty < order_qty) or any(k in status for k in partial_keys):
        stage = "partial_fill"
        terminal = False
    elif not status:
        stage = "unknown"
        terminal = False

    return {
        "ord_no": order_status.get("ord_no"),
        "symbol": order_status.get("symbol"),
        "status_raw": order_status.get("status"),
        "stage": stage,
        "terminal": terminal,
        "filled_qty": filled_qty,
        "order_qty": order_qty,
        "progress": float(progress),
    }


def _evaluate_monitor_entry_candidate(
    *,
    state: Dict[str, Any],
    selected: Dict[str, Any],
    plan: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    strategy_monitor_policy: Dict[str, Any],
    strategy_frame: Dict[str, Any],
    commander_context: Dict[str, Any],
    entry_policy_contract: Dict[str, Any],
    entry_policy_input: Dict[str, Any],
    entry_policy_origin: str,
    all_pos_map: Dict[str, Any],
    open_position_count: int,
    block_buy_open_position: bool,
    post_exit_cooldown_sec: int,
    entry_cooldown_map: Dict[str, Any],
    now_epoch_for_entry: int,
    prefer_fresh_minute_runner: bool = False,
) -> Dict[str, Any]:
    symbol = _norm_symbol(selected.get("symbol"))
    qty = 1
    max_positions = _resolve_max_positions(state, policy)
    held_symbols = {
        _norm_symbol(sym)
        for sym, row in all_pos_map.items()
        if _norm_symbol(sym) and max(0, _to_int((row or {}).get("qty"))) > 0
    }
    pending_buy_symbols = _pending_buy_symbols_from_account_orders(state)
    selected_already_held = bool(symbol and symbol in held_symbols)
    selected_features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    selected_pending_buy = bool(
        symbol
        and (
            symbol in pending_buy_symbols
            or _features_pending_order_count(selected_features) > 0
        )
    )
    strategist_output_for_sizing = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategy_policy_for_sizing = (
        dict(strategist_output_for_sizing.get("strategy_policy") or {})
        if isinstance(strategist_output_for_sizing.get("strategy_policy"), dict)
        else dict(state.get("strategy_policy") or {})
        if isinstance(state.get("strategy_policy"), dict)
        else {}
    )
    use_position_sizing, position_sizing_policy = _resolve_position_sizing_config(
        state,
        policy=policy,
        strategy_policy=strategy_policy_for_sizing,
    )
    sizing_info: Dict[str, Any] = {
        "enabled": bool(use_position_sizing),
        "evaluated": False,
        "qty": 1 if not use_position_sizing else 0,
        "reason": "pending" if use_position_sizing else "disabled",
        "price": None,
        "cash": None,
        "inputs": {},
        "stop_context": {},
    }

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
    last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
    closeout_window_guard = _resolve_entry_closeout_window_guard(state, policy)
    buy_blocked_post_exit_cooldown = False
    post_exit_cooldown_remaining_sec = 0
    if (
        open_position_count <= 0
        and post_exit_cooldown_sec > 0
        and last_trade_side == "SELL"
        and last_trade_epoch > 0
    ):
        elapsed = max(0, int(now_epoch_for_entry - last_trade_epoch))
        remaining = max(0, int(post_exit_cooldown_sec - elapsed))
        if remaining > 0:
            buy_blocked_post_exit_cooldown = True
            post_exit_cooldown_remaining_sec = remaining

    monitor_memory_bias = _resolve_monitor_memory_bias_payload(
        strategy_monitor_policy=strategy_monitor_policy,
        commander_context=commander_context,
        state=state,
    )
    monitor_memory_bias_summary = summarize_monitor_memory_bias(monitor_memory_bias)
    entry_received_policy = MonitorEntryPolicy.from_mapping(entry_policy_input or monitor_policy).to_dict()
    commander_entry_control = (
        dict(commander_context.get("commander_entry_control") or commander_context.get("entry_control") or {})
        if isinstance(commander_context, dict)
        else {}
    )
    if commander_entry_control:
        entry_policy_input = dict(entry_policy_input or monitor_policy or {})
        entry_policy_input["commander_entry_control"] = dict(commander_entry_control)
        entry_policy_input["entry_control"] = dict(commander_entry_control)
    monitor_memory_bias_result = apply_monitor_memory_bias_to_entry_policy(
        entry_policy=entry_policy_input or monitor_policy,
        monitor_memory_bias=monitor_memory_bias,
    )
    monitor_memory_bias_observation_only = _memory_bias_observation_only(state)
    monitor_memory_bias_observed_entry_result = dict(monitor_memory_bias_result)
    if monitor_memory_bias_observation_only:
        monitor_memory_bias_result = {
            "policy": MonitorEntryPolicy.from_mapping(entry_policy_input or monitor_policy).to_dict(),
            "applied": False,
            "deltas": [],
            "observation_only": True,
            "observed_deltas": list(monitor_memory_bias_observed_entry_result.get("deltas") or []),
        }
    entry_policy_input = dict(monitor_memory_bias_result.get("policy") or {})
    if commander_entry_control:
        entry_policy_input["commander_entry_control"] = dict(commander_entry_control)
        entry_policy_input["entry_control"] = dict(commander_entry_control)
    entry_policy = resolve_intraday_entry_policy(entry_policy_input or monitor_policy, frame=strategy_frame)
    state = _ensure_monitor_minute_ohlcv_for_symbol(
        state,
        symbol=symbol,
        timeframe_minutes=int(entry_policy.timeframe_minutes or 1),
        now_epoch=now_epoch_for_entry,
        prefer_fresh_runner=prefer_fresh_minute_runner,
    )
    entry_rows = []
    minute_ohlcv_by_symbol, minute_ohlcv_meta = extract_minute_ohlcv_by_symbol(state)
    entry_row_source = str((minute_ohlcv_meta or {}).get("source") or "")
    minute_fetch_meta = (
        dict(state.get("monitor_minute_ohlcv_fetch") or {})
        if isinstance(state.get("monitor_minute_ohlcv_fetch"), dict)
        else {}
    )
    entry_scoring_policy = _resolve_monitor_entry_scoring_config(state, policy)
    if symbol and isinstance(minute_ohlcv_by_symbol.get(symbol), list):
        entry_rows = list(minute_ohlcv_by_symbol.get(symbol) or [])
    entry_info = evaluate_intraday_entry_signal(
        entry_rows,
        current_price=selected.get("price") if isinstance(selected, dict) else None,
        features=selected.get("features") if isinstance(selected, dict) and isinstance(selected.get("features"), dict) else {},
        policy=entry_policy,
        scoring=entry_scoring_policy,
        frame=strategy_frame,
        policy_contract=entry_policy_contract,
    )
    entry_info["closeout_window_guard"] = dict(closeout_window_guard)
    entry_info["minutes_to_close"] = closeout_window_guard.get("minutes_to_close")
    entry_info["eod_flat_cutoff_min"] = int(closeout_window_guard.get("cutoff_min") or 0)
    entry_info["buy_closeout_cutoff_min"] = int(closeout_window_guard.get("buy_cutoff_min") or 0)
    entry_info["closeout_window_active"] = bool(closeout_window_guard.get("active"))
    entry_info["symbol"] = symbol
    entry_info["selected_symbol"] = symbol
    entry_info["max_positions"] = int(max_positions)
    entry_info["multi_position_capacity_remaining"] = max(0, int(max_positions) - int(open_position_count))
    entry_info["held_symbols"] = sorted(held_symbols)
    entry_info["pending_buy_symbols"] = sorted(pending_buy_symbols)
    entry_info["selected_symbol_already_held"] = bool(selected_already_held)
    entry_info["selected_symbol_pending_buy"] = bool(selected_pending_buy)
    if commander_entry_control:
        entry_info["commander_entry_control"] = dict(commander_entry_control)
    entry_info["applied_policy"] = dict(entry_info.get("applied_policy") or entry_info.get("thresholds") or entry_policy.to_dict())
    entry_applied_policy = dict(entry_info.get("applied_policy") or {})
    effective_policy_trace = _build_monitor_effective_policy_trace(
        received_policy=entry_received_policy,
        effective_policy=entry_applied_policy,
        frame=strategy_frame,
        received_policy_source=entry_policy_origin,
    )
    if bool(monitor_memory_bias_result.get("applied")):
        source_chain = list(effective_policy_trace.get("effective_policy_source_chain") or [])
        effective_policy_trace["effective_policy_source_chain"] = (
            [source_chain[0], "commander_memory_bias", *source_chain[1:]]
            if source_chain
            else ["commander_memory_bias", "monitor_effective_policy"]
        )
        effective_policy_trace["effective_policy_source"] = "monitor_memory_bias_adjusted"
        policy_adjustment_summary = str(effective_policy_trace.get("policy_adjustment_summary") or "").strip()
        effective_policy_trace["policy_adjustment_summary"] = (
            f"{policy_adjustment_summary} | memory_bias=commander"
            if policy_adjustment_summary
            else "commander memory bias adjusted entry policy"
        )
        policy_adjustment_reasoning = str(effective_policy_trace.get("policy_adjustment_reasoning") or "").strip()
        prefix = "Commander-approved memory bias adjusted the entry baseline before strategy-frame normalization."
        effective_policy_trace["policy_adjustment_reasoning"] = (
            f"{prefix} {policy_adjustment_reasoning}".strip()
        )
    entry_info["received_policy"] = dict(effective_policy_trace.get("received_policy") or {})
    entry_info["received_policy_source"] = str(effective_policy_trace.get("received_policy_source") or "")
    entry_info["policy_contract"] = dict(entry_policy_contract)
    entry_info["effective_policy"] = dict(effective_policy_trace.get("effective_policy") or {})
    entry_info["effective_policy_source"] = str(effective_policy_trace.get("effective_policy_source") or "")
    entry_info["effective_policy_source_chain"] = list(effective_policy_trace.get("effective_policy_source_chain") or [])
    entry_info["policy_adjustments"] = dict(effective_policy_trace.get("policy_adjustments") or {})
    entry_info["policy_adjustment_summary"] = str(effective_policy_trace.get("policy_adjustment_summary") or "")
    entry_info["policy_adjustment_reasoning"] = str(effective_policy_trace.get("policy_adjustment_reasoning") or "")
    entry_info["effective_policy_deltas"] = list(effective_policy_trace.get("effective_policy_deltas") or [])
    entry_info["monitor_memory_bias_applied"] = bool(monitor_memory_bias_result.get("applied"))
    entry_info["monitor_memory_bias_observation_only"] = bool(monitor_memory_bias_observation_only)
    entry_info["monitor_memory_bias"] = dict(monitor_memory_bias)
    entry_info["monitor_memory_bias_summary"] = dict(monitor_memory_bias_summary)
    entry_info["monitor_memory_bias_deltas"] = list(monitor_memory_bias_result.get("deltas") or [])
    entry_info["monitor_memory_bias_observed_deltas"] = list(
        monitor_memory_bias_observed_entry_result.get("deltas") or []
    )
    entry_memory_application_trace = build_monitor_commander_memory_application_trace(
        monitor_memory_bias=monitor_memory_bias,
        entry_result=monitor_memory_bias_result,
        hold_result={"applied": False, "deltas": []},
        exit_result={"applied": False, "deltas": []},
        monitor_memory_bias_summary=monitor_memory_bias_summary,
        effective_policy_source=str(effective_policy_trace.get("effective_policy_source") or ""),
        effective_policy_source_chain=list(effective_policy_trace.get("effective_policy_source_chain") or []),
    )
    entry_info["commander_memory_application_trace"] = dict(entry_memory_application_trace)
    entry_info["monitor_memory_application_trace"] = dict(entry_memory_application_trace)
    entry_metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
    entry_metrics["minute_source_present"] = bool(entry_rows)
    entry_metrics["minute_source_used"] = entry_row_source or ""
    latest_candle_ts = None
    if entry_rows and isinstance(entry_rows[-1], dict):
        latest_candle_ts = entry_rows[-1].get("ts")
    entry_metrics["latest_candle_ts"] = latest_candle_ts
    entry_metrics["minute_snapshot_age_minutes"] = minute_fetch_meta.get("minute_snapshot_age_minutes")
    entry_metrics["minute_snapshot_was_stale"] = bool(minute_fetch_meta.get("minute_snapshot_was_stale"))
    entry_metrics["minute_refetch_attempted"] = bool(minute_fetch_meta.get("minute_refetch_attempted"))
    entry_metrics["minute_refetch_succeeded"] = bool(minute_fetch_meta.get("minute_refetch_succeeded"))
    entry_metrics["minute_refetch_reason"] = str(minute_fetch_meta.get("minute_refetch_reason") or "")
    entry_metrics["minute_refetch_trigger_reason"] = str(minute_fetch_meta.get("minute_refetch_trigger_reason") or "")
    entry_metrics["minute_refetch_failure_reason"] = str(minute_fetch_meta.get("minute_refetch_failure_reason") or "")
    entry_metrics["minute_refetch_failure_detail"] = str(minute_fetch_meta.get("minute_refetch_failure_detail") or "")
    entry_metrics["minute_refetch_runner_source"] = str(minute_fetch_meta.get("minute_refetch_runner_source") or "")
    entry_metrics["minute_refetch_produced_fresh_snapshot"] = bool(
        minute_fetch_meta.get("minute_refetch_produced_fresh_snapshot")
    )
    entry_metrics["minute_cache_fallback_used"] = bool(minute_fetch_meta.get("minute_cache_fallback_used"))
    entry_metrics["minute_cache_fallback_source"] = str(minute_fetch_meta.get("minute_cache_fallback_source") or "")
    entry_info["metrics"] = entry_metrics
    entry_info["minute_source_meta"] = dict(minute_ohlcv_meta or {})
    entry_info["minute_fetch_meta"] = minute_fetch_meta
    if use_position_sizing:
        px = _resolve_price(state, symbol, selected)
        cash = _resolve_cash(state)
        sizing_risk_context = _build_sizing_risk_context(state, selected, symbol)
        effective_sizing_policy = dict(position_sizing_policy if position_sizing_policy else policy)
        stop_context = _derive_position_sizing_stop_context(
            state=state,
            symbol=symbol,
            selected=selected,
            entry_info=entry_info,
            price=px,
            sizing_policy=effective_sizing_policy,
        )
        if bool(stop_context.get("applied")):
            effective_sizing_policy["stop_loss_pct"] = stop_context.get("stop_loss_pct")
            effective_sizing_policy["stop_loss_source"] = stop_context.get("stop_loss_source")
            effective_sizing_policy["invalidation_price"] = stop_context.get("invalidation_price")
            effective_sizing_policy["raw_structure_stop_loss_pct"] = stop_context.get("raw_stop_loss_pct")
            effective_sizing_policy["min_structure_stop_loss_pct"] = stop_context.get("min_structure_stop_loss_pct")
        sz = evaluate_position_size(
            price=px,
            cash=cash if cash > 0.0 else None,
            policy=effective_sizing_policy,
            risk_context=sizing_risk_context,
        )
        qty = max(0, _to_int(sz.get("qty")))
        sizing_info = {
            "enabled": True,
            "evaluated": bool(sz.get("evaluated")),
            "qty": int(qty),
            "reason": str(sz.get("reason") or ""),
            "price": sz.get("price"),
            "cash": sz.get("cash"),
            "inputs": sz.get("inputs") if isinstance(sz.get("inputs"), dict) else {},
            "stop_context": dict(stop_context),
        }
    entry_cost_filter_config = _resolve_entry_cost_filter_config(
        state=state,
        policy=policy,
        monitor_policy=monitor_policy,
        strategy_monitor_policy=strategy_monitor_policy,
        entry_policy_input=entry_policy_input,
        commander_entry_control=commander_entry_control,
    )
    entry_cost_filter = _evaluate_entry_cost_filter(
        entry_info=entry_info,
        selected=selected,
        qty=int(qty),
        config=entry_cost_filter_config,
    )
    entry_info["entry_cost_filter"] = dict(entry_cost_filter)
    entry_info["cost_adjusted_edge_ok"] = bool(entry_cost_filter.get("cost_adjusted_edge_ok"))
    entry_info["cost_adjusted_edge_pct"] = entry_cost_filter.get("cost_adjusted_edge_pct")
    entry_info["cost_drag_pct"] = entry_cost_filter.get("cost_drag_pct")
    entry_info["entry_lane"] = "strict"
    entry_info["scoring_mode"] = str(entry_info.get("scoring_mode") or "disabled")
    entry_intent_cooldown_sec = max(0, _to_int((entry_info.get("thresholds") or {}).get("intent_cooldown_sec")))
    cooldown_until = max(0, _to_int(entry_cooldown_map.get(symbol)))
    if cooldown_until > 0 and cooldown_until <= now_epoch_for_entry:
        entry_cooldown_map.pop(symbol, None)
        cooldown_until = 0
    if max(0, _to_int((all_pos_map.get(symbol) or {}).get("qty"))) > 0:
        entry_cooldown_map.pop(symbol, None)
        cooldown_until = 0
    entry_info["intent_cooldown_sec"] = int(entry_intent_cooldown_sec)
    entry_info["intent_cooldown_until"] = int(cooldown_until) if cooldown_until > 0 else None

    entry_guard_blocked = False
    entry_guard_reason = ""
    buy_blocked_open_position = False
    buy_blocked_closeout_window = False
    buy_blocked_same_symbol = False
    buy_blocked_pending_buy = False
    max_positions_reached = bool(open_position_count >= max_positions)
    if selected_already_held:
        entry_guard_blocked = True
        entry_guard_reason = "same_symbol_position_open"
        buy_blocked_open_position = True
        buy_blocked_same_symbol = True
    elif selected_pending_buy:
        entry_guard_blocked = True
        entry_guard_reason = "same_symbol_pending_buy"
        buy_blocked_pending_buy = True
    elif max_positions_reached:
        entry_guard_blocked = True
        entry_guard_reason = "max_positions_reached"
        buy_blocked_open_position = True
    elif bool(closeout_window_guard.get("active")):
        entry_guard_blocked = True
        entry_guard_reason = "buy_blocked_closeout_window"
        buy_blocked_closeout_window = True
    elif buy_blocked_post_exit_cooldown:
        entry_guard_blocked = True
        entry_guard_reason = "post_exit_cooldown"
    elif entry_intent_cooldown_sec > 0 and cooldown_until > now_epoch_for_entry:
        entry_guard_blocked = True
        entry_guard_reason = f"entry_guard_cooldown:{max(0, cooldown_until - now_epoch_for_entry)}s_remaining"
    elif bool(entry_info.get("triggered")) and not bool(entry_cost_filter.get("passed")):
        entry_guard_blocked = True
        entry_guard_reason = "cost_adjusted_edge_not_ready"
        failed_checks = list(entry_info.get("failed_checks") or [])
        if "cost_adjusted_edge_ok" not in failed_checks:
            failed_checks.append("cost_adjusted_edge_ok")
        entry_info["failed_checks"] = failed_checks
        entry_info["primary_failure_axis"] = "cost_adjusted_edge"

    entry_info["guard_blocked"] = bool(entry_guard_blocked)
    entry_info["guard_reason"] = str(entry_guard_reason)
    entry_info["buy_blocked_same_symbol"] = bool(buy_blocked_same_symbol)
    entry_info["buy_blocked_pending_buy"] = bool(buy_blocked_pending_buy)
    entry_info["max_positions_reached"] = bool(max_positions_reached)
    entry_info["legacy_fallback_used"] = False
    entry_info["decision"] = "WAIT"
    entry_info["cascade_candidate"] = str(plan.get("cascade_candidate") or "")

    if symbol and qty > 0 and not entry_guard_blocked and bool(entry_info.get("triggered")):
        entry_info["intent_submitted"] = True
        if entry_intent_cooldown_sec > 0:
            entry_cooldown_map[symbol] = int(now_epoch_for_entry + entry_intent_cooldown_sec)
            entry_info["intent_cooldown_until"] = int(now_epoch_for_entry + entry_intent_cooldown_sec)
        entry_info["decision"] = "BUY"
    else:
        entry_info["intent_submitted"] = False

    return {
        "state": state,
        "selected": selected,
        "symbol": symbol,
        "qty": int(qty),
        "sizing_info": sizing_info,
        "entry_info": entry_info,
        "entry_guard_blocked": bool(entry_guard_blocked),
        "entry_guard_reason": str(entry_guard_reason),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
        "buy_blocked_same_symbol": bool(buy_blocked_same_symbol),
        "buy_blocked_pending_buy": bool(buy_blocked_pending_buy),
        "max_positions_reached": bool(max_positions_reached),
        "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
        "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
        "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
        "entry_received_policy": entry_received_policy,
        "entry_applied_policy": entry_applied_policy,
        "effective_policy_trace": effective_policy_trace,
        "entry_cooldown_map": entry_cooldown_map,
        "entry_signal_detected": bool(entry_info.get("triggered")),
    }


def monitor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Monitor.

    Responsibility:
      - emit at most one intent from selected candidate
      - attach optional order status/lifecycle observation from skill DTOs
      - keep stock-selection and execution out of monitor scope
    """
    run_id = str(state.get("run_id") or "").strip() or "monitor-unknown"
    selected = state.get("selected")
    plan = state.get("plan") or {}
    if isinstance(selected, dict) and selected.get("symbol"):
        selected = _monitor_selected_snapshot_for_symbol(state, str(selected.get("symbol") or ""), selected)

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    monitor_policy: Dict[str, Any] = {}
    if isinstance(policy.get("monitor_policy"), dict):
        monitor_policy.update(dict(policy.get("monitor_policy") or {}))
    if isinstance(strategy_monitor_policy.get("position_guards"), dict):
        monitor_policy.update(dict(strategy_monitor_policy.get("position_guards") or {}))
    if isinstance(strategist_output.get("monitor_policy"), dict):
        monitor_policy.update(dict(strategist_output.get("monitor_policy") or {}))
    if isinstance(state.get("monitor_policy"), dict):
        monitor_policy.update(dict(state.get("monitor_policy") or {}))
    all_pos_map = _position_by_symbol(state)
    _ensure_position_peak_price_map(state, all_pos_map)
    open_position_count = sum(1 for row in all_pos_map.values() if max(0, _to_int((row or {}).get("qty"))) > 0)
    max_positions = _resolve_max_positions(state, policy)
    held_symbols_for_entry = {
        _norm_symbol(sym)
        for sym, row in all_pos_map.items()
        if _norm_symbol(sym) and max(0, _to_int((row or {}).get("qty"))) > 0
    }
    pending_buy_symbols_for_entry = _pending_buy_symbols_from_account_orders(state)
    block_buy_open_position = _resolve_block_buy_when_open_position(state, policy, monitor_policy)
    post_exit_cooldown_sec = _resolve_post_exit_cooldown_sec(state, policy, monitor_policy)
    strategy_frame = _extract_monitor_strategy_frame(state)
    commander_context = (
        dict(strategy_frame.get("commander_context") or {})
        if isinstance(strategy_frame.get("commander_context"), dict)
        else {}
    )
    commander_entry_control = _resolve_commander_entry_control_for_monitor(
        commander_context=commander_context,
        strategy_monitor_policy=strategy_monitor_policy,
        state=state,
    )
    if commander_entry_control:
        commander_context["entry_control"] = dict(commander_entry_control)
        commander_context["commander_entry_control"] = dict(commander_entry_control)
        strategy_frame["commander_context"] = commander_context
    monitor_memory_bias = _resolve_monitor_memory_bias_payload(
        strategy_monitor_policy=strategy_monitor_policy,
        commander_context=commander_context,
        state=state,
    )
    monitor_memory_bias_summary = summarize_monitor_memory_bias(monitor_memory_bias)
    monitor_memory_bias_observation_only = _memory_bias_observation_only(state)
    strategist_plan = (
        dict(strategy_frame.get("strategist_plan") or {})
        if isinstance(strategy_frame.get("strategist_plan"), dict)
        else {}
    )
    policy_provenance = (
        dict(strategy_frame.get("policy_provenance") or {})
        if isinstance(strategy_frame.get("policy_provenance"), dict)
        else {}
    )
    commander_applied_policy = {}
    if isinstance(strategy_monitor_policy.get("applied_policy"), dict) and strategy_monitor_policy.get("applied_policy"):
        commander_applied_policy = dict(strategy_monitor_policy.get("applied_policy") or {})
    elif isinstance(commander_context.get("applied_policy"), dict) and commander_context.get("applied_policy"):
        commander_applied_policy = dict(commander_context.get("applied_policy") or {})
    elif isinstance(state.get("commander_applied_policy"), dict) and state.get("commander_applied_policy"):
        commander_applied_policy = dict(state.get("commander_applied_policy") or {})
    elif isinstance((state.get("commander_decision") or {}).get("applied_policy"), dict):
        commander_applied_policy = dict((state.get("commander_decision") or {}).get("applied_policy") or {})

    entry_policy_contract = build_monitor_entry_policy_contract(
        commander_applied_policy=commander_applied_policy,
        strategist_monitor_entry_policy=(
            dict(strategist_output.get("monitor_entry_policy") or {})
            if isinstance(strategist_output.get("monitor_entry_policy"), dict)
            else {}
        ),
        state_monitor_entry_policy=(
            dict(state.get("monitor_entry_policy") or {})
            if isinstance(state.get("monitor_entry_policy"), dict)
            else {}
        ),
        strategy_monitor_entry_policy=(
            dict(strategy_monitor_policy.get("entry_policy") or {})
            if isinstance(strategy_monitor_policy.get("entry_policy"), dict)
            else {}
        ),
    )
    entry_policy_input: Dict[str, Any] = dict(entry_policy_contract.get("selected_policy") or {})
    if commander_entry_control:
        entry_policy_input["commander_entry_control"] = dict(commander_entry_control)
        entry_policy_input["entry_control"] = dict(commander_entry_control)
    entry_policy_origin = str(entry_policy_contract.get("selected_source") or "monitor_policy")
    buy_blocked_open_position = False
    buy_blocked_same_symbol = False
    buy_blocked_pending_buy = False
    max_positions_reached = bool(open_position_count >= max_positions)
    buy_blocked_post_exit_cooldown = False
    buy_blocked_closeout_window = False
    post_exit_cooldown_remaining_sec = 0
    entry_info: Dict[str, Any] = {
        "enabled": True,
        "evaluated": False,
        "triggered": False,
        "reason": "",
        "pattern": "",
        "signal_chain": [],
        "metrics": {},
        "thresholds": {},
        "guard_blocked": False,
        "guard_reason": "",
        "intent_cooldown_sec": 0,
        "intent_cooldown_until": None,
        "intent_submitted": False,
        "legacy_fallback_used": False,
    }
    entry_signal_detected = False
    entry_guard_blocked = False
    entry_guard_reason = ""
    entry_applied_policy: Dict[str, Any] = {}
    entry_received_policy: Dict[str, Any] = {}
    effective_policy_trace: Dict[str, Any] = {}
    hold_bias_result: Dict[str, Any] = {"controls": {}, "applied": False, "deltas": []}
    exit_bias_result: Dict[str, Any] = {"policy": {}, "applied": False, "deltas": []}
    entry_symbol = _norm_symbol(selected.get("symbol")) if isinstance(selected, dict) and selected.get("symbol") else ""
    entry_cooldown_map = state.get("_monitor_entry_cooldown_until")
    if not isinstance(entry_cooldown_map, dict):
        entry_cooldown_map = {}
    now_epoch_for_entry = _resolve_now_epoch(state)
    state = _refresh_post_exit_shadow_watchlist_minute_rows(
        state,
        now_epoch=now_epoch_for_entry,
    )
    try:
        record_raw_input(
            run_id=run_id,
            agent="monitor",
            stage="entry_exit_decision",
            raw_input={
                "selected_symbol": (
                    str(selected.get("symbol") or "")
                    if isinstance(selected, dict)
                    else ""
                ),
                "selected_snapshot": (
                    {
                        "symbol": str(selected.get("symbol") or ""),
                        "score": selected.get("score"),
                        "risk_score": selected.get("risk_score"),
                        "confidence": selected.get("confidence"),
                        "price_source": str(selected.get("_monitor_price_source") or ""),
                        "feature_source": str(selected.get("_monitor_feature_source") or ""),
                    }
                    if isinstance(selected, dict)
                    else {}
                ),
                "open_position_count": int(open_position_count),
                "positions": {
                    str(k): {"qty": _to_int((v or {}).get("qty")), "avg_price": (v or {}).get("avg_price")}
                    for k, v in list(all_pos_map.items())[:20]
                },
                "monitor_policy": dict(monitor_policy),
                "strategist_guidance": {
                    "playbook": str(strategist_output.get("playbook") or ""),
                    "monitor_guidance": str(strategist_output.get("monitor_guidance") or ""),
                    "risk_tone": str(strategist_output.get("risk_tone") or ""),
                    "trade_aggressiveness": str(strategist_output.get("trade_aggressiveness") or ""),
                },
                "commander_context": {
                    "monitor_mission": str(commander_context.get("monitor_mission") or ""),
                    "flow_instruction": str(commander_context.get("flow_instruction") or ""),
                    "command_intent": str(commander_context.get("command_intent") or ""),
                    "risk_mode": str(commander_context.get("risk_mode") or ""),
                    "no_trade_reason_code": str(commander_context.get("no_trade_reason_code") or ""),
                    "llm_policy": str(commander_context.get("llm_policy") or ""),
                    "source_priority": list(commander_context.get("source_priority") or []),
                    "entry_control": dict(commander_entry_control),
                },
                "strategist_plan": {
                    "selected_playbook": str(strategist_plan.get("selected_playbook") or ""),
                    "entry_plan": dict(strategist_plan.get("entry_plan") or {}),
                    "exit_plan": dict(strategist_plan.get("exit_plan") or {}),
                    "symbol_constraints": dict(strategist_plan.get("symbol_constraints") or {}),
                    "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
                },
            },
            decision_link={"stage": "monitor_input_snapshot"},
        )
    except Exception:
        pass

    intents = []
    sizing_info: Dict[str, Any] = {
        "enabled": False,
        "evaluated": False,
        "qty": 1,
        "reason": "disabled",
        "price": None,
        "cash": None,
        "inputs": {},
    }
    scanner_selected_snapshot = dict(selected) if isinstance(selected, dict) else {}
    entry_cascade_config = _resolve_entry_candidate_cascade_config(commander_entry_control)
    entry_cascade_max_rank = int(entry_cascade_config.get("max_priority_rank") if entry_cascade_config.get("max_priority_rank") not in (None, "") else 10)
    entry_cascade_max_runner_ups = int(entry_cascade_config.get("max_runner_ups") if entry_cascade_config.get("max_runner_ups") not in (None, "") else 9)
    entry_candidate_cascade: Dict[str, Any] = {
        "attempted": False,
        "eligible": False,
        "reason": "",
        "top_pick_symbol": "",
        "max_priority_rank": int(entry_cascade_max_rank),
        "max_runner_ups": int(entry_cascade_max_runner_ups),
        "cascade_enabled": bool(entry_cascade_config.get("cascade_enabled", True)),
        "cascade_allowed_reasons": list(entry_cascade_config.get("cascade_allowed_reasons") or []),
        "cascade_blocked_reasons": list(entry_cascade_config.get("cascade_blocked_reasons") or []),
        "control_source": str(entry_cascade_config.get("source") or "default"),
        "control_mode": str(entry_cascade_config.get("mode") or "default"),
        "runner_up_symbols": [],
        "skipped": [],
        "fallback_used": False,
        "fallback_to_symbol": "",
        "fallback_trace": [],
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "excluded_symbols": sorted(held_symbols_for_entry | pending_buy_symbols_for_entry),
    }
    if isinstance(selected, dict) and selected.get("symbol"):
        top_pick_result = _evaluate_monitor_entry_candidate(
            state=state,
            selected=dict(selected),
            plan=plan,
            policy=policy,
            monitor_policy=monitor_policy,
            strategy_monitor_policy=strategy_monitor_policy,
            strategy_frame=strategy_frame,
            commander_context=commander_context,
            entry_policy_contract=entry_policy_contract,
            entry_policy_input=entry_policy_input,
            entry_policy_origin=entry_policy_origin,
            all_pos_map=all_pos_map,
            open_position_count=open_position_count,
            block_buy_open_position=block_buy_open_position,
            post_exit_cooldown_sec=post_exit_cooldown_sec,
            entry_cooldown_map=entry_cooldown_map,
            now_epoch_for_entry=now_epoch_for_entry,
            prefer_fresh_minute_runner=False,
        )
        state = top_pick_result.get("state") if isinstance(top_pick_result.get("state"), dict) else state
        selected = dict(top_pick_result.get("selected") or selected)
        sizing_info = dict(top_pick_result.get("sizing_info") or sizing_info)
        entry_info = dict(top_pick_result.get("entry_info") or entry_info)
        entry_guard_blocked = bool(top_pick_result.get("entry_guard_blocked"))
        entry_guard_reason = str(top_pick_result.get("entry_guard_reason") or "")
        buy_blocked_open_position = bool(top_pick_result.get("buy_blocked_open_position"))
        buy_blocked_same_symbol = bool(top_pick_result.get("buy_blocked_same_symbol"))
        buy_blocked_pending_buy = bool(top_pick_result.get("buy_blocked_pending_buy"))
        max_positions_reached = bool(top_pick_result.get("max_positions_reached"))
        buy_blocked_post_exit_cooldown = bool(top_pick_result.get("buy_blocked_post_exit_cooldown"))
        buy_blocked_closeout_window = bool(top_pick_result.get("buy_blocked_closeout_window"))
        post_exit_cooldown_remaining_sec = int(top_pick_result.get("post_exit_cooldown_remaining_sec") or 0)
        entry_received_policy = dict(top_pick_result.get("entry_received_policy") or {})
        entry_applied_policy = dict(top_pick_result.get("entry_applied_policy") or {})
        effective_policy_trace = dict(top_pick_result.get("effective_policy_trace") or {})
        entry_cooldown_map = dict(top_pick_result.get("entry_cooldown_map") or entry_cooldown_map)
        entry_signal_detected = bool(top_pick_result.get("entry_signal_detected"))
        symbol = str(top_pick_result.get("symbol") or "")
        qty = int(top_pick_result.get("qty") or 0)
        entry_candidate_cascade["top_pick_symbol"] = symbol
        entry_candidate_cascade["top_pick_triggered"] = bool(entry_info.get("triggered"))
        entry_candidate_cascade["top_pick_reason"] = str(entry_info.get("reason") or "")
        entry_candidate_cascade["top_pick_guard_blocked"] = bool(entry_guard_blocked)

        cascade_plan = build_entry_candidate_cascade_plan(
            selected_symbol=symbol,
            ranked_candidates=[row for row in list(state.get("ranked_candidates") or []) if isinstance(row, dict)],
            scanner_output=state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {},
            open_position_count=open_position_count,
            max_positions=max_positions,
            entry_guard_blocked=entry_guard_blocked,
            entry_guard_reason=entry_guard_reason,
            entry_triggered=bool(entry_info.get("triggered")),
            entry_reason=str(entry_info.get("reason") or ""),
            max_runner_ups=int(entry_cascade_max_runner_ups),
            cascade_enabled=bool(entry_cascade_config.get("cascade_enabled", True)),
            cascade_allowed_reasons=list(entry_cascade_config.get("cascade_allowed_reasons") or []),
            cascade_blocked_reasons=list(entry_cascade_config.get("cascade_blocked_reasons") or []),
            excluded_symbols=sorted(held_symbols_for_entry | pending_buy_symbols_for_entry),
        )
        entry_candidate_cascade.update(dict(cascade_plan))
        fallback_trace = list(entry_candidate_cascade.get("fallback_trace") or [])
        if bool(cascade_plan.get("attempted")):
            for runner_row in list(cascade_plan.get("runner_rows") or []):
                if not isinstance(runner_row, dict):
                    continue
                runner_symbol = _norm_symbol(runner_row.get("symbol"))
                if not runner_symbol:
                    continue
                runner_selected = _monitor_selected_snapshot_for_symbol(state, runner_symbol, dict(runner_row))
                runner_result = _evaluate_monitor_entry_candidate(
                    state=state,
                    selected=runner_selected,
                    plan=plan,
                    policy=policy,
                    monitor_policy=monitor_policy,
                    strategy_monitor_policy=strategy_monitor_policy,
                    strategy_frame=strategy_frame,
                    commander_context=commander_context,
                    entry_policy_contract=entry_policy_contract,
                    entry_policy_input=entry_policy_input,
                    entry_policy_origin=entry_policy_origin,
                    all_pos_map=all_pos_map,
                    open_position_count=open_position_count,
                    block_buy_open_position=block_buy_open_position,
                    post_exit_cooldown_sec=post_exit_cooldown_sec,
                    entry_cooldown_map=entry_cooldown_map,
                    now_epoch_for_entry=now_epoch_for_entry,
                    prefer_fresh_minute_runner=True,
                )
                state = runner_result.get("state") if isinstance(runner_result.get("state"), dict) else state
                entry_cooldown_map = dict(runner_result.get("entry_cooldown_map") or entry_cooldown_map)
                runner_entry = dict(runner_result.get("entry_info") or {})
                runner_metrics = (
                    dict(runner_entry.get("metrics") or {})
                    if isinstance(runner_entry.get("metrics"), dict)
                    else {}
                )
                runner_scores = (
                    dict(runner_entry.get("condition_scores") or {})
                    if isinstance(runner_entry.get("condition_scores"), dict)
                    else {}
                )
                fallback_trace.append(
                    {
                        "symbol": runner_symbol,
                        "rank": runner_row.get("rank") or runner_row.get("priority_rank"),
                        "score_total": runner_row.get("score_total") or runner_row.get("score"),
                        "triggered": bool(runner_entry.get("triggered")),
                        "reason": str(runner_entry.get("reason") or ""),
                        "primary_failure_axis": str(runner_entry.get("primary_failure_axis") or ""),
                        "transition_readiness_score": runner_entry.get("transition_readiness_score")
                        or runner_metrics.get("transition_readiness_score")
                        or runner_scores.get("transition_readiness_score"),
                        "vwap_distance": runner_metrics.get("vwap_distance"),
                        "max_extended_from_vwap_pct": (
                            (runner_entry.get("thresholds") or {}).get("max_extended_from_vwap_pct")
                            if isinstance(runner_entry.get("thresholds"), dict)
                            else None
                        ),
                        "volume_ratio": runner_metrics.get("volume_ratio"),
                        "breakout_ok": runner_metrics.get("breakout_ok"),
                        "pullback_ok": runner_metrics.get("pullback_ok"),
                        "extension_ok": runner_metrics.get("extension_ok"),
                        "confidence_score": runner_scores.get("confidence_score")
                        or runner_metrics.get("confidence_score"),
                        "confidence_threshold": runner_scores.get("confidence_threshold")
                        or runner_metrics.get("confidence_threshold"),
                        "minute_source_present": runner_metrics.get("minute_source_present"),
                        "minute_refetch_succeeded": runner_metrics.get("minute_refetch_succeeded"),
                        "minute_cache_fallback_used": runner_metrics.get("minute_cache_fallback_used"),
                        "guard_blocked": bool(runner_result.get("entry_guard_blocked")),
                    }
                )
                if not bool(runner_entry.get("intent_submitted")):
                    continue
                entry_candidate_cascade["fallback_used"] = True
                entry_candidate_cascade["fallback_to_symbol"] = runner_symbol
                entry_candidate_cascade["fallback_to_rank"] = runner_row.get("rank") or runner_row.get("priority_rank")
                entry_candidate_cascade["fallback_from_symbol"] = symbol
                selected = dict(runner_result.get("selected") or runner_selected)
                sizing_info = dict(runner_result.get("sizing_info") or sizing_info)
                entry_info = runner_entry
                entry_guard_blocked = bool(runner_result.get("entry_guard_blocked"))
                entry_guard_reason = str(runner_result.get("entry_guard_reason") or "")
                buy_blocked_open_position = bool(runner_result.get("buy_blocked_open_position"))
                buy_blocked_same_symbol = bool(runner_result.get("buy_blocked_same_symbol"))
                buy_blocked_pending_buy = bool(runner_result.get("buy_blocked_pending_buy"))
                max_positions_reached = bool(runner_result.get("max_positions_reached"))
                buy_blocked_post_exit_cooldown = bool(runner_result.get("buy_blocked_post_exit_cooldown"))
                buy_blocked_closeout_window = bool(runner_result.get("buy_blocked_closeout_window"))
                post_exit_cooldown_remaining_sec = int(runner_result.get("post_exit_cooldown_remaining_sec") or 0)
                entry_received_policy = dict(runner_result.get("entry_received_policy") or {})
                entry_applied_policy = dict(runner_result.get("entry_applied_policy") or {})
                effective_policy_trace = dict(runner_result.get("effective_policy_trace") or {})
                entry_signal_detected = bool(runner_result.get("entry_signal_detected"))
                symbol = str(runner_result.get("symbol") or runner_symbol)
                qty = int(runner_result.get("qty") or 0)
                entry_info["fallback_from_symbol"] = entry_candidate_cascade.get("fallback_from_symbol")
                entry_info["fallback_to_symbol"] = runner_symbol
                break
        entry_candidate_cascade["fallback_trace"] = fallback_trace
        entry_candidate_cascade["final_selected_symbol"] = symbol
        entry_candidate_cascade["final_selected_rank"] = (
            entry_candidate_cascade.get("fallback_to_rank")
            or selected.get("rank")
            or selected.get("priority_rank")
            or selected.get("scanner_rank")
        )

        if symbol and qty > 0 and not entry_guard_blocked and bool(entry_info.get("intent_submitted")):
            entry_metrics_for_order = (
                dict(entry_info.get("metrics") or {})
                if isinstance(entry_info.get("metrics"), dict)
                else {}
            )
            entry_cost_filter_for_order = (
                dict(entry_info.get("entry_cost_filter") or {})
                if isinstance(entry_info.get("entry_cost_filter"), dict)
                else {}
            )
            order_price_source = ""
            order_price = 0.0
            for source_name, candidate in (
                ("entry_cost_filter.price", entry_cost_filter_for_order.get("price")),
                ("selected.price", selected.get("price")),
                ("entry.metrics.current_price", entry_metrics_for_order.get("current_price")),
                ("entry.metrics.price", entry_metrics_for_order.get("price")),
                ("sizing.price", sizing_info.get("price")),
            ):
                candidate_price = _to_float(candidate)
                if candidate_price > 0.0:
                    order_price = float(candidate_price)
                    order_price_source = source_name
                    break
            intent = {
                "symbol": symbol,
                "side": "BUY",
                "qty": int(qty),
                "price": order_price if order_price > 0.0 else None,
                "thesis": str(plan.get("thesis") or ""),
                "meta": {
                    "score": selected.get("score"),
                    "risk_score": selected.get("risk_score"),
                    "confidence": selected.get("confidence"),
                    "price": order_price if order_price > 0.0 else None,
                    "current_price": order_price if order_price > 0.0 else None,
                    "price_source": order_price_source,
                    "order_price_source": order_price_source,
                    "entry_signal_source": "monitor_intraday_entry",
                    "entry_pattern": str(entry_info.get("pattern") or ""),
                    "entry_reason": str(entry_info.get("reason") or ""),
                    "entry_signal_chain": list(entry_info.get("signal_chain") or []),
                    "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
                    "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
                    "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
                    "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
                    "entry_metrics": dict(entry_info.get("metrics") or {}),
                    "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
                    "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
                    "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
                    "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
                    "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
                    "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
                    "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
                    "entry_lane": str(entry_info.get("entry_lane") or "strict"),
                    "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
                    "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
                    "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
                    "cost_drag_pct": entry_info.get("cost_drag_pct"),
                    "entry_scoring": {
                        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
                        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
                        "total_score": entry_info.get("total_score"),
                        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
                        "entry_threshold": entry_info.get("entry_threshold"),
                        "score_passed": bool(entry_info.get("score_passed")),
                        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
                        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
                        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
                    },
                    "entry_candidate_cascade": dict(entry_candidate_cascade),
                },
            }
            if bool(sizing_info.get("enabled")):
                intent["meta"]["sizing"] = {
                    "reason": str(sizing_info.get("reason") or ""),
                    "price": sizing_info.get("price"),
                    "cash": sizing_info.get("cash"),
                    "inputs": sizing_info.get("inputs"),
                }
            if post_exit_cooldown_sec > 0:
                intent["meta"]["post_exit_cooldown_sec"] = int(post_exit_cooldown_sec)
            if int(entry_info.get("intent_cooldown_sec") or 0) > 0:
                intent["meta"]["entry_intent_cooldown_sec"] = int(entry_info.get("intent_cooldown_sec") or 0)
            intents = [intent]
        else:
            intents = []
    if bool(intents) and open_position_count >= max_positions:
        intents = []
        buy_blocked_open_position = True
        entry_info["guard_blocked"] = True
        entry_info["guard_reason"] = "max_positions_reached"
        entry_info["max_positions_reached"] = True
        entry_info["decision"] = "WAIT"
    state["_monitor_entry_cooldown_until"] = entry_cooldown_map
    if isinstance(selected, dict) and selected.get("symbol"):
        state["selected"] = dict(selected)
    if isinstance(scanner_selected_snapshot, dict) and scanner_selected_snapshot:
        state["scanner_selected_snapshot"] = dict(scanner_selected_snapshot)
    state["monitor_entry_cascade"] = dict(entry_candidate_cascade)

    # Optional M29-2 exit policy (default disabled for backward compatibility).
    use_exit_policy = _resolve_use_exit_policy(state, policy)
    exit_policy_base = _resolve_exit_policy_config(state, policy)
    exit_info: Dict[str, Any] = {
        "enabled": bool(use_exit_policy),
        "evaluated": False,
        "triggered": False,
        "reason": "",
        "symbol": None,
        "qty": 0,
        "pnl_ratio": None,
        "price": None,
        "avg_price": None,
        "position_age_seconds": None,
        "exit_signal_detected": False,
        "exit_confirm_count": 0,
        "min_hold_blocked": False,
        "sell_cooldown_blocked": False,
        "sell_cooldown_until": None,
        "pending_exit_lock_active": False,
        "pending_exit_lock_until": None,
        "monitor_reason": "hold",
        "emergency_exit": False,
    }
    hold_bias_result: Dict[str, Any] = {"applied": False, "deltas": []}
    exit_bias_result: Dict[str, Any] = {"applied": False, "deltas": []}
    selected_snapshot = dict(selected) if isinstance(selected, dict) else {}
    selected_symbol = _norm_symbol(selected_snapshot.get("symbol"))
    has_open_position_for_exit = any(
        max(0, _to_int((row or {}).get("qty"))) > 0
        for row in list(all_pos_map.values())
    )
    if use_exit_policy and (selected_symbol or has_open_position_for_exit):
        pos_map = all_pos_map
        min_hold_sec = _resolve_min_hold_sec(state, monitor_policy)
        sell_cooldown_sec = _resolve_sell_cooldown_sec(state, monitor_policy)
        confirm_ticks = _resolve_exit_confirm_ticks(state, monitor_policy)
        frame_applied = _apply_monitor_strategy_frame(
            min_hold_sec=min_hold_sec,
            sell_cooldown_sec=sell_cooldown_sec,
            confirm_ticks=confirm_ticks,
            frame=strategy_frame,
        )
        min_hold_sec = int(frame_applied.get("min_hold_sec") or min_hold_sec)
        sell_cooldown_sec = int(frame_applied.get("sell_cooldown_sec") or sell_cooldown_sec)
        confirm_ticks = int(frame_applied.get("confirm_ticks") or confirm_ticks)
        hold_bias_result = apply_monitor_memory_bias_to_hold_controls(
            min_hold_sec=min_hold_sec,
            sell_cooldown_sec=sell_cooldown_sec,
            confirm_ticks=confirm_ticks,
            monitor_memory_bias=monitor_memory_bias,
        )
        hold_bias_observed_result = dict(hold_bias_result)
        if monitor_memory_bias_observation_only:
            hold_bias_result = {
                "controls": {
                    "min_hold_sec": int(min_hold_sec),
                    "sell_cooldown_sec": int(sell_cooldown_sec),
                    "confirm_ticks": int(confirm_ticks),
                },
                "applied": False,
                "deltas": [],
                "observation_only": True,
                "observed_deltas": list(hold_bias_observed_result.get("deltas") or []),
            }
        hold_controls = dict(hold_bias_result.get("controls") or {})
        min_hold_sec = int(hold_controls.get("min_hold_sec") or min_hold_sec)
        sell_cooldown_sec = int(hold_controls.get("sell_cooldown_sec") or sell_cooldown_sec)
        confirm_ticks = int(hold_controls.get("confirm_ticks") or confirm_ticks)
        exit_policy_harmonized = _harmonize_exit_policy_with_monitor_guards(
            exit_policy_base=exit_policy_base,
            min_hold_sec=min_hold_sec,
        )
        effective_exit_policy_base = dict(exit_policy_harmonized.get("policy") or {})
        effective_exit_policy_base["policy_source"] = str(
            effective_exit_policy_base.get("policy_source")
            or effective_exit_policy_base.get("effective_policy_source")
            or "monitor_effective_exit_policy"
        )
        effective_exit_policy_base["effective_policy_source"] = str(
            effective_exit_policy_base.get("effective_policy_source")
            or effective_exit_policy_base.get("policy_source")
            or "monitor_effective_exit_policy"
        )
        exit_policy_guard_adjustments = list(exit_policy_harmonized.get("adjustments") or [])
        exit_policy_strategy = _apply_exit_policy_strategy_frame(
            state=state,
            exit_policy_base=effective_exit_policy_base,
            selected=selected_snapshot,
            position=pos_map.get(selected_symbol, {}) if selected_symbol else {},
            frame=frame_applied,
        )
        effective_exit_policy_base = dict(exit_policy_strategy.get("policy") or effective_exit_policy_base)
        effective_exit_policy_base["policy_source"] = str(
            effective_exit_policy_base.get("policy_source")
            or effective_exit_policy_base.get("effective_policy_source")
            or "monitor_effective_exit_policy"
        )
        effective_exit_policy_base["effective_policy_source"] = str(
            effective_exit_policy_base.get("effective_policy_source")
            or effective_exit_policy_base.get("policy_source")
            or "monitor_effective_exit_policy"
        )
        exit_policy_guard_adjustments.extend(list(exit_policy_strategy.get("adjustments") or []))
        exit_bias_result = apply_monitor_memory_bias_to_exit_policy(
            exit_policy=effective_exit_policy_base,
            monitor_memory_bias=monitor_memory_bias,
        )
        exit_bias_observed_result = dict(exit_bias_result)
        if monitor_memory_bias_observation_only:
            exit_bias_result = {
                "policy": dict(effective_exit_policy_base),
                "applied": False,
                "deltas": [],
                "observation_only": True,
                "observed_deltas": list(exit_bias_observed_result.get("deltas") or []),
            }
        effective_exit_policy_base = dict(exit_bias_result.get("policy") or effective_exit_policy_base)
        if bool(hold_bias_result.get("applied")):
            for row in list(hold_bias_result.get("deltas") or [])[:6]:
                exit_policy_guard_adjustments.append(
                    f"commander_memory_bias_hold:{str((row or {}).get('field') or '')}:{(row or {}).get('from')}->{(row or {}).get('to')}"
                )
        if bool(exit_bias_result.get("applied")):
            for row in list(exit_bias_result.get("deltas") or [])[:6]:
                exit_policy_guard_adjustments.append(
                    f"commander_memory_bias_exit:{str((row or {}).get('field') or '')}:{(row or {}).get('from')}->{(row or {}).get('to')}"
                )
        now_epoch = _resolve_now_epoch(state)
        eod_carry_sweep = _persist_eod_carry_decisions_for_open_positions(
            state=state,
            pos_map=pos_map,
            selected=selected_snapshot,
            exit_policy_base=effective_exit_policy_base,
            frame=frame_applied,
            now_epoch=now_epoch,
        )
        symbol = _select_exit_symbol(
            selected_symbol,
            pos_map,
            state=state,
            selected=selected_snapshot,
            policy=policy,
            exit_policy_base=effective_exit_policy_base,
        )
        selected_for_exit: Dict[str, Any] = dict(selected_snapshot)
        if symbol and symbol != selected_symbol:
            selected_for_exit = {"symbol": symbol}
        features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
        pending_order_symbols_for_exit = _pending_order_symbols_from_account_orders(state)
        selected_pending_order_for_exit = bool(
            symbol
            and (
                _norm_symbol(symbol) in pending_order_symbols_for_exit
                or _features_pending_order_count(features) > 0
            )
        )
        pos = pos_map.get(symbol, {})
        qty = max(0, _to_int(pos.get("qty")))
        entry_intent_symbol = _norm_symbol((intents[0] or {}).get("symbol")) if intents else ""
        # Suppress fresh BUY only when it targets the same symbol as an existing position.
        if qty > 0 and entry_intent_symbol and entry_intent_symbol == _norm_symbol(symbol):
            intents = []
        decision = _preview_exit_decision_for_symbol(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=effective_exit_policy_base,
        )
        avg_price = _to_float(decision.get("_avg_price"))
        price = decision.get("_price")
        hold_sec = _to_int(decision.get("_hold_sec"))
        if hold_sec <= 0:
            hold_sec = _position_hold_seconds(state, symbol, pos)
        eod_carry = _evaluate_overnight_carry_decision(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=effective_exit_policy_base,
            primary_decision=decision,
            frame=frame_applied,
            hold_sec=hold_sec,
        )
        if bool(eod_carry.get("approved")):
            decision["triggered"] = False
            decision["reason"] = "carry_overnight_approved"
        if qty > 0 and bool(eod_carry.get("evaluated")):
            _persist_overnight_decision(
                state,
                symbol=symbol,
                decision={
                    "approved": bool(eod_carry.get("approved")),
                    "action": str(eod_carry.get("action") or ""),
                    "reason": str(eod_carry.get("reason") or ""),
                    "minutes_to_close": eod_carry.get("minutes_to_close"),
                    "cutoff_min": eod_carry.get("cutoff_min"),
                    "positive_signals": list(eod_carry.get("positive_signals") or []),
                    "blockers": list(eod_carry.get("blockers") or []),
                    "carry_calendar": dict(eod_carry.get("carry_calendar") or {}),
                    "weekend_carry": bool(eod_carry.get("weekend_carry")),
                    "allow_weekend_carry": bool(eod_carry.get("allow_weekend_carry")),
                    "holding_gap_days": eod_carry.get("holding_gap_days"),
                    "decided_at_epoch": int(now_epoch),
                    "symbol": str(symbol or ""),
                },
            )
        elif qty <= 0:
            _persist_overnight_decision(state, symbol=symbol, clear=True)
        confirm_map = state.get("_monitor_exit_confirm")
        if not isinstance(confirm_map, dict):
            confirm_map = {}
        cooldown_map = state.get("_monitor_sell_cooldown_until")
        if not isinstance(cooldown_map, dict):
            cooldown_map = {}
        pending_exit_lock = state.get("_monitor_pending_exit_lock")
        if not isinstance(pending_exit_lock, dict):
            pending_exit_lock = {}
        prev_qty_map = state.get("_monitor_prev_position_qty")
        if not isinstance(prev_qty_map, dict):
            prev_qty_map = {}

        prev_qty = max(0, _to_int(prev_qty_map.get(symbol)))
        if prev_qty > 0 and qty <= 0 and sell_cooldown_sec > 0:
            cooldown_map[symbol] = int(now_epoch + sell_cooldown_sec)
        prev_qty_map[symbol] = int(qty)

        cooldown_until = max(0, _to_int(cooldown_map.get(symbol)))
        if cooldown_until > 0 and cooldown_until <= now_epoch:
            cooldown_map.pop(symbol, None)
            cooldown_until = 0

        lock_until = max(0, _to_int(pending_exit_lock.get(symbol)))
        if lock_until > 0 and lock_until <= now_epoch:
            pending_exit_lock.pop(symbol, None)
            lock_until = 0

        confirm_key = f"{symbol}:{str(decision.get('reason') or '').strip()}"
        confirm_count = 0
        sell_guard_blocked = False
        sell_guard_reason = ""
        hold_block_reason = str(decision.get("hold_block_reason") or "")
        monitor_reason = "hold"
        min_hold_blocked = False
        sell_cooldown_blocked = False
        exit_signal_detected = bool(decision.get("triggered"))
        emergency_exit = _is_emergency_exit_reason(str(decision.get("reason") or ""))
        hard_exit = _is_hard_exit_reason(str(decision.get("reason") or ""))
        decision_reason = str(decision.get("reason") or "").strip()
        decision_thresholds = (
            decision.get("thresholds")
            if isinstance(decision.get("thresholds"), dict)
            else {}
        )
        effective_confirm_ticks = max(1, int(confirm_ticks))
        peak_drawdown_confirm_ticks = 0
        if decision_reason == "peak_drawdown":
            peak_drawdown_confirm_ticks = max(
                1,
                _to_int(decision_thresholds.get("confirm_required_for_peak_drawdown") or 2),
            )
            if bool(decision.get("peak_drawdown_profit_protection_urgent")):
                peak_drawdown_confirm_ticks = 1
            effective_confirm_ticks = max(effective_confirm_ticks, peak_drawdown_confirm_ticks)

        if exit_signal_detected:
            if qty <= 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_no_position"
                monitor_reason = "no_position"
            elif _is_trueish(state.get("execution_pending")):
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_execution_pending"
                monitor_reason = "pending_exit_lock"
            elif selected_pending_order_for_exit:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_open_order_pending"
                monitor_reason = "pending_exit_lock"
            elif lock_until > now_epoch:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_pending_exit_lock"
                monitor_reason = "pending_exit_lock"
                hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            elif not emergency_exit and not hard_exit and min_hold_sec > 0 and hold_sec > 0 and hold_sec < min_hold_sec:
                sell_guard_blocked = True
                min_hold_blocked = True
                sell_guard_reason = f"sell_guard_min_hold:{hold_sec}s<{min_hold_sec}s"
                monitor_reason = "min_hold_active"
                hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            elif not emergency_exit and not hard_exit and sell_cooldown_sec > 0 and cooldown_until > now_epoch:
                sell_guard_blocked = True
                sell_cooldown_blocked = True
                sell_guard_reason = f"sell_guard_cooldown:{max(0, cooldown_until - now_epoch)}s_remaining"
                monitor_reason = "cooldown_active"
                hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            elif not emergency_exit and not hard_exit and effective_confirm_ticks > 1:
                confirm_count = _to_int(confirm_map.get(confirm_key)) + 1
                confirm_map[confirm_key] = int(confirm_count)
                if confirm_count < int(effective_confirm_ticks):
                    sell_guard_blocked = True
                    sell_guard_reason = f"exit_confirmation_pending:{confirm_count}/{effective_confirm_ticks}"
                    monitor_reason = "exit_signal_pending_confirmation"
                    hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            if not sell_guard_blocked and not monitor_reason:
                monitor_reason = "confirmed_exit_signal"
        else:
            _clear_symbol_confirm_keys(confirm_map, symbol)
            if bool(eod_carry.get("approved")) and qty > 0:
                monitor_reason = "eod_carry_approved"
            elif qty <= 0 and bool(entry_info.get("guard_blocked")):
                monitor_reason = str(entry_info.get("guard_reason") or "entry_guard_blocked")
            elif qty <= 0 and str(entry_info.get("reason") or "").strip():
                monitor_reason = str(entry_info.get("reason") or "entry_wait")
            elif qty <= 0 and bool(entry_info.get("triggered")) and bool(entry_info.get("intent_submitted")):
                monitor_reason = str(entry_info.get("reason") or "entry_signal_confirmed")
            else:
                monitor_reason = "hold" if qty > 0 else "no_position"

        if not sell_guard_blocked and exit_signal_detected:
            if not emergency_exit and not hard_exit and confirm_count <= 0:
                confirm_count = max(1, int(effective_confirm_ticks))
            _clear_symbol_confirm_keys(confirm_map, symbol)
            lock_sec = max(30, int(sell_cooldown_sec))
            pending_exit_lock[symbol] = int(now_epoch + lock_sec)
            lock_until = int(now_epoch + lock_sec)
            if sell_cooldown_sec > 0:
                cooldown_until = int(now_epoch + sell_cooldown_sec)
                cooldown_map[symbol] = int(cooldown_until)
            if emergency_exit:
                monitor_reason = "emergency_exit_signal"
            elif monitor_reason not in ("confirmed_exit_signal", "emergency_exit_signal"):
                monitor_reason = "confirmed_exit_signal"

        if qty <= 0:
            pending_exit_lock.pop(symbol, None)
            lock_until = 0

        state["_monitor_exit_confirm"] = confirm_map
        state["_monitor_sell_cooldown_until"] = cooldown_map
        state["_monitor_pending_exit_lock"] = pending_exit_lock
        state["_monitor_prev_position_qty"] = prev_qty_map

        exit_info = {
            "enabled": True,
            "evaluated": bool(decision.get("evaluated")),
            "triggered": bool(exit_signal_detected) and not bool(sell_guard_blocked),
            "reason": (
                str(sell_guard_reason)
                if str(sell_guard_reason).strip()
                else str(decision.get("reason") or "")
            ),
            "symbol": symbol,
            "selected_symbol": selected_symbol,
            "exit_symbol_fallback": bool(symbol and symbol != selected_symbol),
            "qty": int(qty),
            "pnl_ratio": decision.get("pnl_ratio"),
            "raw_pnl_ratio": decision.get("raw_pnl_ratio"),
            "gross_pnl_ratio": decision.get("gross_pnl_ratio"),
            "technical_pnl_ratio": decision.get("technical_pnl_ratio"),
            "effective_pnl_ratio": decision.get("effective_pnl_ratio"),
            "stop_pnl_ratio": decision.get("stop_pnl_ratio"),
            "stop_pnl_ratio_source": str(decision.get("stop_pnl_ratio_source") or ""),
            "hard_stop_pnl_ratio": decision.get("hard_stop_pnl_ratio"),
            "hard_stop_pnl_ratio_source": str(decision.get("hard_stop_pnl_ratio_source") or ""),
            "cost_drag_pressure": bool(decision.get("cost_drag_pressure")),
            "cost_drag_pressure_pct": decision.get("cost_drag_pressure_pct"),
            "cost_drag_pressure_reason": str(decision.get("cost_drag_pressure_reason") or ""),
            "stop_loss_cost_drag_blocked": bool(decision.get("stop_loss_cost_drag_blocked")),
            "stop_loss_cost_drag_blocked_reason": str(decision.get("stop_loss_cost_drag_blocked_reason") or ""),
            "price": price,
            "raw_price": decision.get("raw_price"),
            "technical_price": decision.get("technical_price"),
            "technical_price_source": str(decision.get("technical_price_source") or ""),
            "effective_price": decision.get("effective_price"),
            "avg_price": avg_price if avg_price > 0.0 else None,
            "peak_price": decision.get("_peak_price"),
            "account_current_price": decision.get("account_current_price"),
            "account_current_price_source": str(decision.get("account_current_price_source") or ""),
            "account_mark_price": decision.get("account_mark_price"),
            "account_mark_price_source": str(decision.get("account_mark_price_source") or ""),
            "account_unrealized_pnl": decision.get("account_unrealized_pnl"),
            "account_pnl_ratio": decision.get("account_pnl_ratio"),
            "account_pnl_ratio_source": str(decision.get("account_pnl_ratio_source") or ""),
            "pnl_crosscheck_applied": bool(decision.get("pnl_crosscheck_applied")),
            "pnl_crosscheck_reason": str(decision.get("pnl_crosscheck_reason") or ""),
            "pnl_crosscheck_gap": decision.get("pnl_crosscheck_gap"),
            "price_crosscheck_gap": decision.get("price_crosscheck_gap"),
            "price_anomaly_flag": bool(decision.get("price_anomaly_flag")),
            "price_anomaly_reason": str(decision.get("price_anomaly_reason") or ""),
            "pnl_fallback_applied": bool(decision.get("pnl_fallback_applied")),
            "fallback_price_source": str(decision.get("fallback_price_source") or ""),
            "thresholds": decision.get("thresholds") if isinstance(decision.get("thresholds"), dict) else {},
            "final_exit_thresholds": (
                dict(decision.get("final_exit_thresholds") or {})
                if isinstance(decision.get("final_exit_thresholds"), dict)
                else dict(decision.get("thresholds") or {})
            ),
            "exit_threshold_source": str(decision.get("exit_threshold_source") or ""),
            "cost_aware_profit_floor_enabled": bool(decision.get("cost_aware_profit_floor_enabled")),
            "round_trip_cost_floor_pct": decision_thresholds.get("round_trip_cost_floor_pct"),
            "min_net_profit_buffer_pct": decision_thresholds.get("min_net_profit_buffer_pct"),
            "cost_aware_profit_floor_pct": decision.get("cost_aware_profit_floor_pct"),
            "cost_aware_profit_floor_met": bool(decision.get("cost_aware_profit_floor_met")),
            "cost_aware_profit_floor_gap_pct": decision.get("cost_aware_profit_floor_gap_pct"),
            "cost_aware_profit_floor_blocked": bool(decision.get("cost_aware_profit_floor_blocked")),
            "expected_exit_price": decision.get("expected_exit_price"),
            "expected_exit_price_source": str(decision.get("expected_exit_price_source") or ""),
            "expected_exit_price_fallback_used": bool(decision.get("expected_exit_price_fallback_used")),
            "expected_exit_slippage_buffer_pct": decision.get("expected_exit_slippage_buffer_pct"),
            "expected_exit_pnl_ratio": decision.get("expected_exit_pnl_ratio"),
            "expected_exit_net_pnl_ratio": decision.get("expected_exit_net_pnl_ratio"),
            "expected_exit_profit_floor_met": bool(decision.get("expected_exit_profit_floor_met")),
            "expected_exit_profit_floor_gap_pct": decision.get("expected_exit_profit_floor_gap_pct"),
            "expected_exit_profit_floor_blocked": bool(decision.get("expected_exit_profit_floor_blocked")),
            "expected_exit_profit_floor_blocked_reason": str(
                decision.get("expected_exit_profit_floor_blocked_reason") or ""
            ),
            "protective_exit_floor_blocked": bool(decision.get("protective_exit_floor_blocked")),
            "protective_exit_floor_blocked_reason": str(decision.get("protective_exit_floor_blocked_reason") or ""),
            "protective_exit_hard_invalidation": bool(decision.get("protective_exit_hard_invalidation")),
            "protective_exit_hard_invalidation_reason": str(
                decision.get("protective_exit_hard_invalidation_reason") or ""
            ),
            "max_runup_pct": decision.get("max_runup_pct"),
            "peak_drawdown_from_peak": decision.get("peak_drawdown_from_peak"),
            "peak_drawdown_armed": bool(decision.get("peak_drawdown_armed")),
            "peak_drawdown_mode": str(decision.get("peak_drawdown_mode") or ""),
            "peak_drawdown_profit_protection_urgent": bool(decision.get("peak_drawdown_profit_protection_urgent")),
            "peak_drawdown_profit_protection_reason": str(decision.get("peak_drawdown_profit_protection_reason") or ""),
            "final_peak_drawdown_ratio": decision.get("final_peak_drawdown_ratio"),
            "peak_drawdown_source": str(decision.get("peak_drawdown_source") or ""),
            "exit_trigger_metric_name": str(decision.get("exit_trigger_metric_name") or ""),
            "exit_trigger_metric_value": decision.get("exit_trigger_metric_value"),
            "exit_trigger_metric_source": str(decision.get("exit_trigger_metric_source") or ""),
            "risk_reward_take_profit_target_pct": decision.get("risk_reward_take_profit_target_pct"),
            "risk_reward_take_profit_rung": decision.get("risk_reward_take_profit_rung"),
            "resistance_price": decision.get("resistance_price"),
            "resistance_price_source": str(decision.get("resistance_price_source") or ""),
            "resistance_distance_pct": decision.get("resistance_distance_pct"),
            "profit_time_stop_peak_giveback_pct": decision.get("profit_time_stop_peak_giveback_pct"),
            "partial_exit": bool(decision.get("partial_exit")),
            "exit_qty": decision.get("exit_qty"),
            "exit_qty_fraction": decision.get("exit_qty_fraction"),
            "partial_take_profit_taken": bool(decision.get("partial_take_profit_taken")),
            "profit_ladder_level_pct": decision.get("profit_ladder_level_pct"),
            "profit_ladder_level_index": decision.get("profit_ladder_level_index"),
            "volume_ratio": decision.get("volume_ratio"),
            "execution_strength": decision.get("execution_strength"),
            "trade_strength": decision.get("trade_strength"),
            "opening_gap_chase_observed": bool(decision.get("opening_gap_chase_observed")),
            "open_gap_pct": decision.get("open_gap_pct"),
            "prev_close_distance_pct": decision.get("prev_close_distance_pct"),
            "position_entry_risk_applied": bool(decision.get("position_entry_risk_applied")),
            "position_entry_stop_loss_pct": decision.get("position_entry_stop_loss_pct"),
            "position_entry_stop_loss_source": str(decision.get("position_entry_stop_loss_source") or ""),
            "position_entry_invalidation_price": decision.get("position_entry_invalidation_price"),
            "effective_exit_policy": dict(effective_exit_policy_base),
            "hold_sec": hold_sec if hold_sec > 0 else None,
            "trailing_drawdown": decision.get("trailing_drawdown"),
            "peak_drawdown": decision.get("peak_drawdown"),
            "vwap_distance": decision.get("vwap_distance"),
            "volatility_ratio": decision.get("volatility_ratio"),
            "volatility_regime": str(features.get("engine_regime") or ""),
            "price_source": str(decision.get("_price_source") or ""),
            "effective_price_source": str(decision.get("effective_price_source") or ""),
            "price_source_policy": "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized; effective_exit_price prefers the most conservative sane cross-check price and falls back when account-derived mark is anomalous",
            "feature_source": str(decision.get("_feature_source") or ""),
            "minutes_to_close": decision.get("minutes_to_close"),
            "min_hold_sec": int(min_hold_sec),
            "sell_cooldown_sec": int(sell_cooldown_sec),
            "exit_confirm_ticks": int(effective_confirm_ticks),
            "exit_confirm_count": int(confirm_count),
            "peak_drawdown_confirm_ticks": int(peak_drawdown_confirm_ticks),
            "sell_guard_blocked": bool(sell_guard_blocked),
            "sell_guard_reason": str(sell_guard_reason),
            "position_age_seconds": hold_sec if hold_sec > 0 else None,
            "exit_signal_detected": bool(exit_signal_detected),
            "min_hold_blocked": bool(min_hold_blocked),
            "sell_cooldown_blocked": bool(sell_cooldown_blocked),
            "hold_block_reason": str(hold_block_reason),
            "sell_cooldown_until": (int(cooldown_until) if cooldown_until > 0 else None),
            "pending_exit_lock_active": bool(lock_until > now_epoch),
            "pending_exit_lock_until": (int(lock_until) if lock_until > 0 else None),
            "monitor_reason": str(monitor_reason or ""),
            "emergency_exit": bool(emergency_exit),
            "hard_exit": bool(hard_exit),
            "playbook": str(frame_applied.get("playbook") or ""),
            "monitor_guidance": str(frame_applied.get("monitor_guidance") or ""),
            "risk_tone": str(frame_applied.get("risk_tone") or ""),
            "trade_aggressiveness": str(frame_applied.get("trade_aggressiveness") or ""),
            "strategy_horizon": str(frame_applied.get("strategy_horizon") or ""),
            "source_strategy_horizon": str(frame_applied.get("source_strategy_horizon") or ""),
            "horizon_behavior_translation": dict(frame_applied.get("horizon_behavior_translation") or {}),
            "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
            "exit_policy_guard_adjustments": list(exit_policy_guard_adjustments),
            "monitor_memory_bias_observation_only": bool(monitor_memory_bias_observation_only),
            "monitor_memory_bias_hold_applied": bool(hold_bias_result.get("applied")),
            "monitor_memory_bias_hold_deltas": list(hold_bias_result.get("deltas") or []),
            "monitor_memory_bias_hold_observed_deltas": list(hold_bias_observed_result.get("deltas") or []),
            "monitor_memory_bias_exit_applied": bool(exit_bias_result.get("applied")),
            "monitor_memory_bias_exit_deltas": list(exit_bias_result.get("deltas") or []),
            "monitor_memory_bias_exit_observed_deltas": list(exit_bias_observed_result.get("deltas") or []),
            "active_exit_axis": _friendly_exit_axis(str(decision.get("reason") or monitor_reason or "hold")),
            "watch_axes": _monitor_watch_axes(decision.get("thresholds") if isinstance(decision.get("thresholds"), dict) else {}),
            "eod_carry_evaluated": bool(eod_carry.get("evaluated")),
            "eod_carry_approved": bool(eod_carry.get("approved")),
            "eod_carry_action": str(eod_carry.get("action") or ""),
            "eod_carry_reason": str(eod_carry.get("reason") or ""),
            "eod_carry_positive_signals": list(eod_carry.get("positive_signals") or []),
            "eod_carry_blockers": list(eod_carry.get("blockers") or []),
            "eod_carry_weekend": bool(eod_carry.get("weekend_carry")),
            "eod_carry_allow_weekend": bool(eod_carry.get("allow_weekend_carry")),
            "eod_carry_holding_gap_days": eod_carry.get("holding_gap_days"),
            "eod_carry_calendar": dict(eod_carry.get("carry_calendar") or {}),
            "eod_carry_non_eod_reason": str(eod_carry.get("non_eod_reason") or ""),
            "eod_carry_non_eod_triggered": bool(eod_carry.get("non_eod_triggered")),
            "eod_carry_anomaly": bool(eod_carry.get("anomaly")),
            "eod_carry_anomaly_reason": str(eod_carry.get("anomaly_reason") or ""),
            "eod_carry_sweep_evaluated_count": int(eod_carry_sweep.get("evaluated_count") or 0),
            "eod_carry_sweep_symbols": list(eod_carry_sweep.get("symbols") or []),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_reason": str(entry_info.get("reason") or ""),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_signal_chain": list(entry_info.get("signal_chain") or []),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
            "entry_passed_checks": list(entry_info.get("passed_checks") or []),
            "entry_failed_checks": list(entry_info.get("failed_checks") or []),
            "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
            "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
            "entry_hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
            "entry_hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
            "entry_total_score": entry_info.get("total_score"),
            "entry_score_breakdown": dict(entry_info.get("score_breakdown") or {}),
            "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
            "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
            "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
            "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
            "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
            "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
            "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
            "entry_score_threshold": entry_info.get("entry_threshold"),
            "entry_score_passed": bool(entry_info.get("score_passed")),
            "entry_scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
            "entry_legacy_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
            "entry_scoring_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            "entry_intent_submitted": bool(entry_info.get("intent_submitted")),
            "entry_legacy_fallback_used": bool(entry_info.get("legacy_fallback_used")),
            "entry_intent_cooldown_sec": int(entry_info.get("intent_cooldown_sec") or 0),
            "entry_intent_cooldown_until": entry_info.get("intent_cooldown_until"),
        }
        sell_would_submit = bool(exit_signal_detected) and not bool(sell_guard_blocked) and qty > 0
        exit_vs_strategy_intent = build_exit_vs_strategy_intent(
            state=state,
            exit_info=exit_info,
            sell_submitted=sell_would_submit,
        )
        exit_info["exit_vs_strategy_intent"] = dict(exit_vs_strategy_intent)
        if bool(exit_signal_detected) and not bool(sell_guard_blocked) and qty > 0:
            exit_order_qty = max(1, min(int(qty), _to_int(decision.get("exit_qty") or qty)))
            exit_info["exit_qty"] = int(exit_order_qty)
            intents = [
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": int(exit_order_qty),
                    "thesis": str(plan.get("thesis") or ""),
                    "meta": {
                        "exit_reason": str(decision.get("reason") or ""),
                        "exit_qty": int(exit_order_qty),
                        "position_qty": int(qty),
                        "partial_exit": bool(decision.get("partial_exit")),
                        "exit_qty_fraction": decision.get("exit_qty_fraction"),
                        "profit_ladder_level_pct": decision.get("profit_ladder_level_pct"),
                        "profit_ladder_level_index": decision.get("profit_ladder_level_index"),
                        "risk_reward_take_profit_rung": decision.get("risk_reward_take_profit_rung"),
                        "pnl_ratio": decision.get("pnl_ratio"),
                        "raw_pnl_ratio": decision.get("raw_pnl_ratio"),
                        "gross_pnl_ratio": decision.get("gross_pnl_ratio"),
                        "technical_pnl_ratio": decision.get("technical_pnl_ratio"),
                        "effective_pnl_ratio": decision.get("effective_pnl_ratio"),
                        "stop_pnl_ratio": decision.get("stop_pnl_ratio"),
                        "stop_pnl_ratio_source": str(decision.get("stop_pnl_ratio_source") or ""),
                        "hard_stop_pnl_ratio": decision.get("hard_stop_pnl_ratio"),
                        "hard_stop_pnl_ratio_source": str(decision.get("hard_stop_pnl_ratio_source") or ""),
                        "cost_drag_pressure": bool(decision.get("cost_drag_pressure")),
                        "cost_drag_pressure_pct": decision.get("cost_drag_pressure_pct"),
                        "cost_drag_pressure_reason": str(decision.get("cost_drag_pressure_reason") or ""),
                        "stop_loss_cost_drag_blocked": bool(decision.get("stop_loss_cost_drag_blocked")),
                        "stop_loss_cost_drag_blocked_reason": str(decision.get("stop_loss_cost_drag_blocked_reason") or ""),
                        "avg_price": avg_price if avg_price > 0.0 else None,
                        "price": price,
                        "technical_price": decision.get("technical_price"),
                        "technical_price_source": str(decision.get("technical_price_source") or ""),
                        "effective_price": decision.get("effective_price"),
                        "account_current_price": decision.get("account_current_price"),
                        "account_mark_price": decision.get("account_mark_price"),
                        "account_unrealized_pnl": decision.get("account_unrealized_pnl"),
                        "account_pnl_ratio_source": str(decision.get("account_pnl_ratio_source") or ""),
                        "pnl_crosscheck_applied": bool(decision.get("pnl_crosscheck_applied")),
                        "pnl_crosscheck_reason": str(decision.get("pnl_crosscheck_reason") or ""),
                        "source": "monitor_exit_policy",
                        "reason": str(decision.get("reason") or ""),
                        "signal_source": "monitor_exit_policy",
                        "position_age_sec": hold_sec if hold_sec > 0 else None,
                        "position_age_seconds": hold_sec if hold_sec > 0 else None,
                        "monitor_reason": str(monitor_reason or ""),
                        "exit_signal_detected": bool(exit_signal_detected),
                        "exit_confirm_count": int(confirm_count),
                        "min_hold_blocked": bool(min_hold_blocked),
                        "sell_cooldown_blocked": bool(sell_cooldown_blocked),
                        "emergency_exit": bool(emergency_exit),
                        "playbook": str(frame_applied.get("playbook") or ""),
                        "monitor_guidance": str(frame_applied.get("monitor_guidance") or ""),
                        "risk_tone": str(frame_applied.get("risk_tone") or ""),
                        "trade_aggressiveness": str(frame_applied.get("trade_aggressiveness") or ""),
                        "strategy_horizon": str(frame_applied.get("strategy_horizon") or ""),
                        "source_strategy_horizon": str(frame_applied.get("source_strategy_horizon") or ""),
                        "horizon_behavior_translation": dict(frame_applied.get("horizon_behavior_translation") or {}),
                        "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
                        "exit_policy_guard_adjustments": list(exit_policy_guard_adjustments),
                        "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
                    },
                }
            ]

    commander_memory_application_trace = build_monitor_commander_memory_application_trace(
        monitor_memory_bias=monitor_memory_bias,
        entry_result={
            "applied": bool(entry_info.get("monitor_memory_bias_applied")),
            "deltas": list(entry_info.get("monitor_memory_bias_deltas") or []),
        },
        hold_result=hold_bias_result,
        exit_result=exit_bias_result,
        monitor_memory_bias_summary=monitor_memory_bias_summary,
        effective_policy_source=str(entry_info.get("effective_policy_source") or ""),
        effective_policy_source_chain=list(entry_info.get("effective_policy_source_chain") or []),
    )
    entry_info["commander_memory_application_trace"] = dict(commander_memory_application_trace)
    entry_info["monitor_memory_application_trace"] = dict(commander_memory_application_trace)
    exit_info["commander_memory_application_trace"] = dict(commander_memory_application_trace)
    exit_info["monitor_memory_application_trace"] = dict(commander_memory_application_trace)

    order_status, order_status_meta = extract_order_status(state)
    order_lifecycle = _derive_order_lifecycle(order_status)
    fallback_reasons = list(order_status_meta.get("errors") or [])

    state["intents"] = intents
    state["monitor"] = {
        "skill_contract_version": SKILL_CONTRACT_VERSION,
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "order_status_loaded": bool(order_status),
        "order_status": order_status,
        "order_status_present": bool(order_status_meta.get("present")),
        "order_status_fallback": bool(fallback_reasons),
        "order_status_fallback_reasons": fallback_reasons,
        "order_status_error_count": len(fallback_reasons),
        "order_lifecycle_loaded": bool(order_lifecycle),
        "order_lifecycle": order_lifecycle,
        "exit_policy_enabled": bool(exit_info.get("enabled")),
        "exit_evaluated": bool(exit_info.get("evaluated")),
        "exit_triggered": bool(exit_info.get("triggered")),
        "exit_reason": str(exit_info.get("reason") or ""),
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "exit_pnl_ratio": exit_info.get("pnl_ratio"),
        "exit_raw_pnl_ratio": exit_info.get("raw_pnl_ratio"),
        "exit_gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
        "exit_technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
        "exit_effective_pnl_ratio": exit_info.get("effective_pnl_ratio"),
        "exit_stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
        "exit_stop_pnl_ratio_source": str(exit_info.get("stop_pnl_ratio_source") or ""),
        "exit_hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
        "exit_hard_stop_pnl_ratio_source": str(exit_info.get("hard_stop_pnl_ratio_source") or ""),
        "exit_cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
        "exit_cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
        "exit_cost_drag_pressure_reason": str(exit_info.get("cost_drag_pressure_reason") or ""),
        "exit_stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
        "exit_stop_loss_cost_drag_blocked_reason": str(exit_info.get("stop_loss_cost_drag_blocked_reason") or ""),
        "exit_symbol": exit_info.get("symbol"),
        "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
        "exit_qty": int(exit_info.get("exit_qty") or exit_info.get("qty") or 0),
        "exit_raw_price": exit_info.get("raw_price"),
        "exit_technical_price": exit_info.get("technical_price"),
        "exit_technical_price_source": str(exit_info.get("technical_price_source") or ""),
        "exit_effective_price": exit_info.get("effective_price"),
        "exit_effective_price_source": str(exit_info.get("effective_price_source") or ""),
        "exit_account_current_price": exit_info.get("account_current_price"),
        "exit_account_mark_price": exit_info.get("account_mark_price"),
        "exit_account_unrealized_pnl": exit_info.get("account_unrealized_pnl"),
        "exit_account_pnl_ratio": exit_info.get("account_pnl_ratio"),
        "exit_account_pnl_ratio_source": str(exit_info.get("account_pnl_ratio_source") or ""),
        "exit_pnl_crosscheck_applied": bool(exit_info.get("pnl_crosscheck_applied")),
        "exit_pnl_crosscheck_reason": str(exit_info.get("pnl_crosscheck_reason") or ""),
        "exit_pnl_crosscheck_gap": exit_info.get("pnl_crosscheck_gap"),
        "exit_position_age_seconds": exit_info.get("position_age_seconds"),
        "exit_min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
        "exit_sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
        "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
        "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "exit_min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
        "exit_sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
        "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
        "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
        "round_trip_cost_floor_pct": exit_info.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": exit_info.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
        "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
        "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
        "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
        "exit_expected_exit_price": exit_info.get("expected_exit_price"),
        "exit_expected_exit_price_source": str(exit_info.get("expected_exit_price_source") or ""),
        "exit_expected_exit_price_fallback_used": bool(exit_info.get("expected_exit_price_fallback_used")),
        "exit_expected_exit_slippage_buffer_pct": exit_info.get("expected_exit_slippage_buffer_pct"),
        "exit_expected_exit_pnl_ratio": exit_info.get("expected_exit_pnl_ratio"),
        "exit_expected_exit_net_pnl_ratio": exit_info.get("expected_exit_net_pnl_ratio"),
        "exit_expected_exit_profit_floor_met": bool(exit_info.get("expected_exit_profit_floor_met")),
        "exit_expected_exit_profit_floor_gap_pct": exit_info.get("expected_exit_profit_floor_gap_pct"),
        "exit_expected_exit_profit_floor_blocked": bool(exit_info.get("expected_exit_profit_floor_blocked")),
        "exit_expected_exit_profit_floor_blocked_reason": str(
            exit_info.get("expected_exit_profit_floor_blocked_reason") or ""
        ),
        "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
        "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
        "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
        "protective_exit_hard_invalidation_reason": str(
            exit_info.get("protective_exit_hard_invalidation_reason") or ""
        ),
        "eod_carry_evaluated": bool(exit_info.get("eod_carry_evaluated")),
        "eod_carry_approved": bool(exit_info.get("eod_carry_approved")),
        "eod_carry_action": str(exit_info.get("eod_carry_action") or ""),
        "eod_carry_reason": str(exit_info.get("eod_carry_reason") or ""),
        "position_sizing_enabled": bool(sizing_info.get("enabled")),
        "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
        "position_sizing_qty": int(sizing_info.get("qty") or 0),
        "position_sizing_reason": str(sizing_info.get("reason") or ""),
        "position_sizing_stop_loss_pct": (sizing_info.get("inputs") or {}).get("stop_loss_pct")
        if isinstance(sizing_info.get("inputs"), dict)
        else None,
        "position_sizing_stop_loss_source": str(
            ((sizing_info.get("inputs") or {}).get("stop_loss_source") if isinstance(sizing_info.get("inputs"), dict) else "")
            or ""
        ),
        "position_sizing_invalidation_price": (sizing_info.get("inputs") or {}).get("invalidation_price")
        if isinstance(sizing_info.get("inputs"), dict)
        else None,
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "multi_position_capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "block_buy_when_open_position": bool(block_buy_open_position),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
        "buy_blocked_same_symbol": bool(buy_blocked_same_symbol),
        "buy_blocked_pending_buy": bool(buy_blocked_pending_buy),
        "max_positions_reached": bool(max_positions_reached),
        "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
        "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
        "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
        "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
        "minutes_to_close": entry_info.get("minutes_to_close"),
        "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
        "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
        "closeout_window_active": bool(entry_info.get("closeout_window_active")),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_reason": str(entry_info.get("reason") or ""),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_signal_chain": list(entry_info.get("signal_chain") or []),
        "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
        "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
        "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
        "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
        "entry_metrics": dict(entry_info.get("metrics") or {}),
        "entry_received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "entry_received_policy_source": str(entry_info.get("received_policy_source") or entry_policy_origin or ""),
        "entry_policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "entry_applied_policy": dict(entry_applied_policy),
        "entry_effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "entry_effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "entry_effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "commander_entry_control": dict(entry_info.get("commander_entry_control") or {}),
        "entry_policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "entry_policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "entry_effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "monitor_memory_bias_applied": bool(entry_info.get("monitor_memory_bias_applied")),
        "monitor_memory_bias_observation_only": bool(entry_info.get("monitor_memory_bias_observation_only")),
        "monitor_memory_bias": dict(entry_info.get("monitor_memory_bias") or {}),
        "monitor_memory_bias_summary": dict(entry_info.get("monitor_memory_bias_summary") or {}),
        "monitor_memory_bias_deltas": list(entry_info.get("monitor_memory_bias_deltas") or []),
        "monitor_memory_bias_observed_deltas": list(entry_info.get("monitor_memory_bias_observed_deltas") or []),
        "monitor_memory_bias_hold_applied": bool(exit_info.get("monitor_memory_bias_hold_applied")),
        "monitor_memory_bias_hold_deltas": list(exit_info.get("monitor_memory_bias_hold_deltas") or []),
        "monitor_memory_bias_exit_applied": bool(exit_info.get("monitor_memory_bias_exit_applied")),
        "monitor_memory_bias_exit_deltas": list(exit_info.get("monitor_memory_bias_exit_deltas") or []),
        "commander_memory_application_trace": dict(commander_memory_application_trace),
        "monitor_memory_application_trace": dict(commander_memory_application_trace),
        "entry_thresholds": dict(entry_info.get("thresholds") or {}),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "entry_hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "entry_hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "entry_total_score": entry_info.get("total_score"),
        "entry_score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "entry_score_threshold": entry_info.get("entry_threshold"),
        "entry_score_passed": bool(entry_info.get("score_passed")),
        "entry_scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "entry_legacy_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "entry_scoring_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
        "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        "entry_intent_submitted": bool(entry_info.get("intent_submitted")),
        "entry_legacy_fallback_used": bool(entry_info.get("legacy_fallback_used")),
        "entry_intent_cooldown_sec": int(entry_info.get("intent_cooldown_sec") or 0),
        "entry_intent_cooldown_until": entry_info.get("intent_cooldown_until"),
        "entry_candidate_cascade": dict(entry_candidate_cascade),
    }
    if bool(exit_info.get("enabled")) and bool(exit_info.get("exit_signal_detected")):
        monitor_entry_exit_reason = str(exit_info.get("reason") or "")
    elif bool(buy_blocked_post_exit_cooldown):
        monitor_entry_exit_reason = "post_exit_cooldown"
    elif bool(buy_blocked_closeout_window):
        monitor_entry_exit_reason = "buy_blocked_closeout_window"
    elif bool(buy_blocked_pending_buy):
        monitor_entry_exit_reason = "same_symbol_pending_buy"
    elif bool(buy_blocked_same_symbol):
        monitor_entry_exit_reason = "same_symbol_position_open"
    elif bool(max_positions_reached and buy_blocked_open_position):
        monitor_entry_exit_reason = "max_positions_reached"
    elif bool(buy_blocked_open_position):
        monitor_entry_exit_reason = "buy_blocked_open_position"
    elif bool(entry_info.get("guard_blocked")):
        monitor_entry_exit_reason = str(entry_info.get("guard_reason") or "")
    else:
        monitor_entry_exit_reason = str(entry_info.get("reason") or "entry_wait")
    state["monitor_output"] = {
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "intent_side": (str(intents[0].get("side")) if intents else "NOOP"),
        "intent_qty": (int(intents[0].get("qty") or 0) if intents else 0),
        "entry_exit_reason": monitor_entry_exit_reason,
        "entry_candidate_cascade": dict(entry_candidate_cascade),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
    }
    state["monitor_entry"] = dict(entry_info)
    state["monitor_exit"] = exit_info
    state["monitor_sizing"] = sizing_info
    monitor_symbol = str(exit_info.get("symbol") or (selected.get("symbol") if isinstance(selected, dict) else "") or "")
    current_posture = _monitor_posture_for_cycle(
        open_position_count=open_position_count,
        intents=intents,
        exit_info=exit_info,
        buy_blocked_open_position=buy_blocked_open_position,
        buy_blocked_post_exit_cooldown=buy_blocked_post_exit_cooldown,
    )
    current_reason = str(exit_info.get("monitor_reason") or exit_info.get("reason") or (state.get("monitor_output") or {}).get("entry_exit_reason") or "").strip()
    previous_monitor_state = _load_previous_monitor_state(state, monitor_symbol) if monitor_symbol else {}
    previous_posture = str(previous_monitor_state.get("posture") or "").strip()
    previous_reason = str(previous_monitor_state.get("reason") or "").strip()
    entry_transition_trace = _build_monitor_entry_transition_trace(previous_monitor_state, entry_info)
    entry_info.update(dict(entry_transition_trace))
    entry_info["entry_transition_trace"] = dict(entry_transition_trace)
    state_changed = bool(previous_posture != current_posture or previous_reason != current_reason)
    if monitor_symbol:
        _save_current_monitor_state(
            state,
            monitor_symbol,
            posture=current_posture,
            reason=current_reason,
            active_exit_axis=str(exit_info.get("active_exit_axis") or ""),
            entry_state=_build_monitor_entry_state_snapshot(entry_info),
        )
    if isinstance(state.get("monitor"), dict):
        state["monitor"]["entry_transition_trace"] = dict(entry_transition_trace)
        state["monitor"]["entry_became_ready_this_cycle"] = bool(entry_transition_trace.get("became_ready_this_cycle"))
        state["monitor"]["entry_last_blocking_axis"] = str(entry_transition_trace.get("last_blocking_axis") or "")
        state["monitor"]["entry_transition_readiness_score"] = entry_transition_trace.get("transition_readiness_score")
    if isinstance(state.get("monitor_output"), dict):
        state["monitor_output"]["entry_transition_trace"] = dict(entry_transition_trace)
        state["monitor_output"]["entry_became_ready_this_cycle"] = bool(entry_transition_trace.get("became_ready_this_cycle"))
        state["monitor_output"]["entry_last_blocking_axis"] = str(entry_transition_trace.get("last_blocking_axis") or "")
        state["monitor_output"]["entry_transition_readiness_score"] = entry_transition_trace.get("transition_readiness_score")

    thresholds = dict(exit_info.get("thresholds") or {}) if isinstance(exit_info.get("thresholds"), dict) else {}
    entry_metrics = dict(entry_info.get("metrics") or {}) if isinstance(entry_info.get("metrics"), dict) else {}
    entry_thresholds = dict(entry_info.get("thresholds") or {}) if isinstance(entry_info.get("thresholds"), dict) else {}
    entry_applied_policy = (
        dict(entry_info.get("applied_policy") or {})
        if isinstance(entry_info.get("applied_policy"), dict)
        else dict(entry_applied_policy or entry_thresholds)
    )
    monitor_policy_trace = _build_monitor_policy_trace(
        commander_context=commander_context,
        monitor_policy=strategy_monitor_policy,
        strategist_plan=strategist_plan,
        policy_provenance=policy_provenance,
        entry_info=entry_info,
        exit_info=exit_info,
        current_reason=current_reason,
    )
    policy_ref = dict(monitor_policy_trace.get("policy_ref") or {})
    policy_ref["received_policy"] = dict(entry_info.get("received_policy") or entry_received_policy or {})
    policy_ref["received_policy_source"] = str(entry_info.get("received_policy_source") or entry_policy_origin or "")
    policy_ref["effective_policy"] = dict(entry_info.get("effective_policy") or entry_applied_policy or {})
    policy_ref["effective_policy_source"] = str(entry_info.get("effective_policy_source") or "")
    policy_ref["effective_policy_source_chain"] = list(entry_info.get("effective_policy_source_chain") or [])
    policy_ref["policy_adjustments"] = dict(entry_info.get("policy_adjustments") or {})
    policy_ref["policy_adjustment_summary"] = str(entry_info.get("policy_adjustment_summary") or "")
    policy_ref["policy_adjustment_reasoning"] = str(entry_info.get("policy_adjustment_reasoning") or "")
    policy_ref["effective_policy_deltas"] = list(entry_info.get("effective_policy_deltas") or [])
    policy_ref["monitor_memory_bias_applied"] = bool(entry_info.get("monitor_memory_bias_applied"))
    policy_ref["monitor_memory_bias_observation_only"] = bool(entry_info.get("monitor_memory_bias_observation_only"))
    policy_ref["monitor_memory_bias"] = dict(entry_info.get("monitor_memory_bias") or {})
    policy_ref["monitor_memory_bias_summary"] = dict(entry_info.get("monitor_memory_bias_summary") or {})
    policy_ref["monitor_memory_bias_deltas"] = list(entry_info.get("monitor_memory_bias_deltas") or [])
    policy_ref["monitor_memory_bias_observed_deltas"] = list(entry_info.get("monitor_memory_bias_observed_deltas") or [])
    policy_ref["monitor_memory_bias_hold_applied"] = bool(exit_info.get("monitor_memory_bias_hold_applied"))
    policy_ref["monitor_memory_bias_hold_deltas"] = list(exit_info.get("monitor_memory_bias_hold_deltas") or [])
    policy_ref["monitor_memory_bias_exit_applied"] = bool(exit_info.get("monitor_memory_bias_exit_applied"))
    policy_ref["monitor_memory_bias_exit_deltas"] = list(exit_info.get("monitor_memory_bias_exit_deltas") or [])
    policy_ref["commander_memory_application_trace"] = dict(commander_memory_application_trace)
    policy_ref["monitor_memory_application_trace"] = dict(commander_memory_application_trace)
    monitor_policy_trace["policy_ref"] = policy_ref
    pnl_ratio = _to_float(exit_info.get("pnl_ratio")) if exit_info.get("pnl_ratio") not in (None, "") else None
    threshold_snapshot = {
        "current_price": exit_info.get("price"),
        "avg_price": exit_info.get("avg_price"),
        "peak_price": exit_info.get("peak_price"),
        "pnl_pct": pnl_ratio,
        "drawdown_pct": exit_info.get("peak_drawdown"),
        "stop_loss_pct": thresholds.get("stop_loss_pct"),
        "effective_stop_loss_pct": thresholds.get("effective_stop_loss_pct"),
        "take_profit_pct": thresholds.get("take_profit_pct"),
        "trailing_stop_pct": thresholds.get("trailing_stop_pct"),
        "final_exit_thresholds": dict(exit_info.get("final_exit_thresholds") or {}),
        "exit_threshold_source": str(exit_info.get("exit_threshold_source") or ""),
        "hold_block_reason": str(exit_info.get("hold_block_reason") or ""),
        "max_runup_pct": exit_info.get("max_runup_pct"),
        "peak_drawdown_from_peak": exit_info.get("peak_drawdown_from_peak"),
        "peak_drawdown_armed": bool(exit_info.get("peak_drawdown_armed")),
        "peak_drawdown_mode": str(exit_info.get("peak_drawdown_mode") or ""),
        "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
        "peak_drawdown_source": str(exit_info.get("peak_drawdown_source") or ""),
        "exit_trigger_metric_name": str(exit_info.get("exit_trigger_metric_name") or ""),
        "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
        "exit_trigger_metric_source": str(exit_info.get("exit_trigger_metric_source") or ""),
        "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
        "round_trip_cost_floor_pct": exit_info.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": exit_info.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
        "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
        "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
        "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
        "expected_exit_price": exit_info.get("expected_exit_price"),
        "expected_exit_price_source": str(exit_info.get("expected_exit_price_source") or ""),
        "expected_exit_price_fallback_used": bool(exit_info.get("expected_exit_price_fallback_used")),
        "expected_exit_slippage_buffer_pct": exit_info.get("expected_exit_slippage_buffer_pct"),
        "expected_exit_pnl_ratio": exit_info.get("expected_exit_pnl_ratio"),
        "expected_exit_net_pnl_ratio": exit_info.get("expected_exit_net_pnl_ratio"),
        "expected_exit_profit_floor_met": bool(exit_info.get("expected_exit_profit_floor_met")),
        "expected_exit_profit_floor_gap_pct": exit_info.get("expected_exit_profit_floor_gap_pct"),
        "expected_exit_profit_floor_blocked": bool(exit_info.get("expected_exit_profit_floor_blocked")),
        "expected_exit_profit_floor_blocked_reason": str(
            exit_info.get("expected_exit_profit_floor_blocked_reason") or ""
        ),
        "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
        "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
        "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
        "protective_exit_hard_invalidation_reason": str(
            exit_info.get("protective_exit_hard_invalidation_reason") or ""
        ),
        "vwap_distance_pct": exit_info.get("vwap_distance"),
        "volatility_regime": str(exit_info.get("volatility_regime") or ""),
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "watch_axes": list(exit_info.get("watch_axes") or []),
        "exit_confirm_required": int(exit_info.get("exit_confirm_ticks") or 0),
        "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "price_anomaly_flag": bool(exit_info.get("price_anomaly_flag")),
        "price_anomaly_reason": str(exit_info.get("price_anomaly_reason") or ""),
        "pnl_fallback_applied": bool(exit_info.get("pnl_fallback_applied")),
        "fallback_price_source": str(exit_info.get("fallback_price_source") or ""),
        "entry_timeframe_minutes": entry_metrics.get("timeframe_minutes"),
        "entry_minute_source_present": entry_metrics.get("minute_source_present"),
        "entry_minute_source_used": entry_metrics.get("minute_source_used"),
        "entry_latest_candle_ts": entry_metrics.get("latest_candle_ts"),
        "entry_minute_snapshot_age_minutes": entry_metrics.get("minute_snapshot_age_minutes"),
        "entry_minute_snapshot_was_stale": entry_metrics.get("minute_snapshot_was_stale"),
        "entry_minute_refetch_attempted": entry_metrics.get("minute_refetch_attempted"),
        "entry_minute_refetch_succeeded": entry_metrics.get("minute_refetch_succeeded"),
        "entry_minute_refetch_reason": entry_metrics.get("minute_refetch_reason"),
        "entry_minute_refetch_trigger_reason": entry_metrics.get("minute_refetch_trigger_reason"),
        "entry_minute_refetch_failure_reason": entry_metrics.get("minute_refetch_failure_reason"),
        "entry_minute_refetch_produced_fresh_snapshot": entry_metrics.get("minute_refetch_produced_fresh_snapshot"),
        "entry_inferred_spacing_minutes": entry_metrics.get("inferred_spacing_minutes"),
        "entry_series_class": entry_metrics.get("series_class"),
        "entry_recent_high": entry_metrics.get("recent_high"),
        "entry_breakout_level": entry_metrics.get("breakout_level"),
        "entry_vwap": entry_metrics.get("vwap"),
        "entry_volume_ratio": entry_metrics.get("volume_ratio"),
        "entry_extended_from_vwap_pct": entry_metrics.get("extended_from_vwap_pct"),
        "entry_pullback_depth_pct": entry_metrics.get("pullback_depth_pct"),
        "entry_previous_close": entry_metrics.get("previous_close"),
        "entry_session_open": entry_metrics.get("session_open"),
        "entry_open_gap_pct": entry_metrics.get("open_gap_pct"),
        "entry_prev_close_distance_pct": entry_metrics.get("prev_close_distance_pct"),
        "entry_minutes_since_session_open": entry_metrics.get("minutes_since_session_open"),
        "entry_opening_gap_chase_observed": bool(entry_metrics.get("opening_gap_chase_observed")),
        "entry_opening_gap_context_observation_only": bool(entry_metrics.get("opening_gap_context_observation_only")),
        "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "received_policy_source": str(entry_info.get("received_policy_source") or entry_policy_origin or ""),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "policy_adjustment_reasoning": str(entry_info.get("policy_adjustment_reasoning") or ""),
        "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "applied_policy": dict(entry_applied_policy),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "entry_volume_ratio_min": entry_thresholds.get("volume_ratio_min"),
        "entry_max_extended_from_vwap_pct": entry_thresholds.get("max_extended_from_vwap_pct"),
        "entry_min_extended_from_vwap_pct": entry_thresholds.get("min_extended_from_vwap_pct"),
        "entry_pullback_min_pct": entry_thresholds.get("pullback_min_pct"),
        "entry_pullback_max_pct": entry_thresholds.get("pullback_max_pct"),
        "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
        "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
        "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
        "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "entry_hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "entry_hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "entry_total_score": entry_info.get("total_score"),
        "entry_score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_score_threshold": entry_info.get("entry_threshold"),
        "entry_score_passed": bool(entry_info.get("score_passed")),
        "entry_scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "entry_legacy_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "entry_scoring_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
    }
    state["monitor_posture"] = current_posture
    state["monitor_threshold_snapshot"] = dict(threshold_snapshot)
    if isinstance(state.get("monitor"), dict):
        state["monitor"]["threshold_snapshot"] = dict(threshold_snapshot)
        state["monitor"]["exit_stop_loss_pct"] = threshold_snapshot.get("stop_loss_pct")
        state["monitor"]["exit_effective_stop_loss_pct"] = threshold_snapshot.get("effective_stop_loss_pct")
        state["monitor"]["position_entry_risk_applied"] = bool(exit_info.get("position_entry_risk_applied"))
        state["monitor"]["position_entry_stop_loss_pct"] = exit_info.get("position_entry_stop_loss_pct")
        state["monitor"]["position_entry_stop_loss_source"] = str(exit_info.get("position_entry_stop_loss_source") or "")
        state["monitor"]["position_entry_invalidation_price"] = exit_info.get("position_entry_invalidation_price")
    state["monitor_state_transition"] = {
        "previous_posture": previous_posture,
        "current_posture": current_posture,
        "previous_reason": previous_reason,
        "current_reason": current_reason,
        "state_changed": bool(state_changed),
        "trigger_delta": {
            "previous_active_exit_axis": str(previous_monitor_state.get("active_exit_axis") or ""),
            "current_active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
            "exit_triggered": bool(exit_info.get("triggered")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
            "became_ready_this_cycle": bool(entry_transition_trace.get("became_ready_this_cycle")),
            "last_blocking_axis": str(entry_transition_trace.get("last_blocking_axis") or ""),
            "transition_readiness_score": entry_transition_trace.get("transition_readiness_score"),
        },
    }
    _emit_monitor_event(
        state,
        name="threshold_snapshot",
        payload=threshold_snapshot,
        symbol=monitor_symbol,
    )
    _emit_monitor_event(
        state,
        name="state_transition",
        payload={
            "previous_posture": previous_posture,
            "current_posture": current_posture,
            "previous_reason": previous_reason,
            "current_reason": current_reason,
            "state_changed": bool(state_changed),
            "trigger_delta": {
                "previous_active_exit_axis": str(previous_monitor_state.get("active_exit_axis") or ""),
                "current_active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
                "exit_triggered": bool(exit_info.get("triggered")),
                "entry_triggered": bool(entry_info.get("triggered")),
                "entry_pattern": str(entry_info.get("pattern") or ""),
                "became_ready_this_cycle": bool(entry_transition_trace.get("became_ready_this_cycle")),
                "last_blocking_axis": str(entry_transition_trace.get("last_blocking_axis") or ""),
                "transition_readiness_score": entry_transition_trace.get("transition_readiness_score"),
            },
        },
        symbol=monitor_symbol,
    )
    buy_submitted = any(str((intent or {}).get("side") or "").strip().upper() == "BUY" for intent in list(intents or []))
    buy_skipped_reason = ""
    if not bool(buy_submitted):
        buy_skipped_reason = str(entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait").strip()
    entry_event_metrics = dict(entry_info.get("metrics") or {}) if isinstance(entry_info.get("metrics"), dict) else {}
    if "price" not in entry_event_metrics:
        entry_event_metrics["price"] = entry_event_metrics.get("current_price")
    if "vwap_distance" not in entry_event_metrics:
        entry_event_metrics["vwap_distance"] = entry_event_metrics.get("extended_from_vwap_pct")
    if "pullback_pct" not in entry_event_metrics:
        entry_event_metrics["pullback_pct"] = entry_event_metrics.get("pullback_depth_pct")
    final_entry_decision = "BUY" if bool(buy_submitted) else "WAIT"
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    monitor_no_trade_surface = build_monitor_no_trade_surface(
        entry_info,
        final_decision=final_entry_decision,
        buy_submitted=bool(buy_submitted),
        guard_blocked=bool(entry_info.get("guard_blocked")),
        guard_reason=entry_info.get("guard_reason"),
        commander_no_trade_reason_code=commander_decision.get("no_trade_reason_code"),
    )
    scanner_monitor_handoff = build_scanner_monitor_handoff_surface(
        selected=scanner_selected_snapshot if isinstance(scanner_selected_snapshot, dict) else {},
        ranked_candidates=[row for row in list(state.get("ranked_candidates") or []) if isinstance(row, dict)],
        scanner_output=state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {},
        final_decision=final_entry_decision,
        no_trade_surface=monitor_no_trade_surface,
        entry_info=entry_info,
    )
    scanner_monitor_handoff["monitor_selected_symbol"] = str((selected or {}).get("symbol") or "")
    scanner_monitor_handoff["entry_candidate_cascade"] = dict(entry_candidate_cascade)
    state["monitor_no_trade_surface"] = dict(monitor_no_trade_surface)
    state["scanner_monitor_handoff"] = dict(scanner_monitor_handoff)
    entry_blocker_surface = build_entry_blocker_surface(
        entry_info,
        final_decision=final_entry_decision,
        no_trade_surface=monitor_no_trade_surface,
        entry_blockers=list(monitor_policy_trace.get("entry_blockers") or []),
        buy_blocked_open_position=bool(buy_blocked_open_position),
        buy_blocked_closeout_window=bool(buy_blocked_closeout_window),
        buy_blocked_post_exit_cooldown=bool(buy_blocked_post_exit_cooldown),
        post_exit_cooldown_remaining_sec=post_exit_cooldown_remaining_sec,
        open_position_count=open_position_count,
        minutes_to_close=entry_info.get("minutes_to_close"),
        eod_flat_cutoff_min=entry_info.get("eod_flat_cutoff_min"),
    )
    state["monitor_entry_blocker_surface"] = dict(entry_blocker_surface)
    scanner_selected_symbol = str(
        scanner_monitor_handoff.get("scanner_selected_symbol")
        or (scanner_selected_snapshot.get("symbol") if isinstance(scanner_selected_snapshot, dict) else "")
        or ""
    ).strip()
    entry_candidate_symbol = str(
        entry_info.get("selected_symbol")
        or entry_info.get("symbol")
        or ((selected or {}).get("symbol") if isinstance(selected, dict) else "")
        or ""
    ).strip()
    entry_final_symbol = str(
        entry_candidate_cascade.get("final_selected_symbol")
        or ((selected or {}).get("symbol") if isinstance(selected, dict) else "")
        or entry_candidate_symbol
        or ""
    ).strip()
    position_focus_symbol = str(exit_info.get("symbol") or "").strip()
    monitor_output_symbol = str(monitor_symbol or position_focus_symbol or entry_final_symbol or "").strip()
    entry_cost_filter_snapshot = (
        dict(entry_info.get("entry_cost_filter") or {})
        if isinstance(entry_info.get("entry_cost_filter"), dict)
        else {}
    )
    if position_focus_symbol and entry_final_symbol and position_focus_symbol != entry_final_symbol:
        monitor_focus_mode = "entry_candidate_and_position_focus"
    elif position_focus_symbol:
        monitor_focus_mode = "position_focus"
    elif entry_final_symbol:
        monitor_focus_mode = "entry_candidate_focus"
    else:
        monitor_focus_mode = "no_symbol_focus"
    monitor_focus_context = {
        "schema_version": "monitor.focus_context.v1",
        "focus_mode": monitor_focus_mode,
        "scanner_selected_symbol": scanner_selected_symbol,
        "entry_candidate_symbol": entry_candidate_symbol,
        "entry_final_symbol": entry_final_symbol,
        "position_focus_symbol": position_focus_symbol,
        "monitor_output_symbol": monitor_output_symbol,
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "held_symbols": sorted(held_symbols_for_entry),
        "pending_buy_symbols": sorted(pending_buy_symbols_for_entry),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_decision": final_entry_decision,
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_intent_submitted": bool(buy_submitted),
        "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
        "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        "entry_reason": str(entry_info.get("reason") or ""),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "entry_cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "entry_cost_drag_pct": entry_info.get("cost_drag_pct"),
        "entry_cost_filter": dict(entry_cost_filter_snapshot),
        "exit_evaluated": bool(exit_info.get("evaluated")),
        "exit_triggered": bool(exit_info.get("triggered")),
        "exit_reason": str(exit_info.get("reason") or ""),
        "exit_monitor_reason": str(exit_info.get("monitor_reason") or ""),
        "exit_active_axis": str(exit_info.get("active_exit_axis") or ""),
    }
    state["monitor_focus_context"] = dict(monitor_focus_context)
    if isinstance(state.get("monitor"), dict):
        state["monitor"]["monitor_focus_context"] = dict(monitor_focus_context)
        state["monitor"]["entry_candidate_symbol"] = entry_candidate_symbol
        state["monitor"]["entry_final_symbol"] = entry_final_symbol
        state["monitor"]["position_focus_symbol"] = position_focus_symbol
        state["monitor"]["monitor_focus_mode"] = monitor_focus_mode
    if isinstance(state.get("monitor_output"), dict):
        state["monitor_output"]["entry_blocker_surface"] = dict(entry_blocker_surface)
        state["monitor_output"]["monitor_focus_context"] = dict(monitor_focus_context)
        state["monitor_output"]["scanner_selected_symbol"] = scanner_selected_symbol
        state["monitor_output"]["entry_candidate_symbol"] = entry_candidate_symbol
        state["monitor_output"]["entry_final_symbol"] = entry_final_symbol
        state["monitor_output"]["position_focus_symbol"] = position_focus_symbol
        state["monitor_output"]["monitor_output_symbol"] = monitor_output_symbol
        state["monitor_output"]["monitor_focus_mode"] = monitor_focus_mode
        state["monitor_output"]["entry_candidate_decision"] = final_entry_decision
        state["monitor_output"]["entry_candidate_reason"] = str(
            entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait"
        )
        state["monitor_output"]["entry_candidate_primary_failure_axis"] = str(
            entry_info.get("primary_failure_axis") or ""
        )
        state["monitor_output"]["entry_candidate_cost_adjusted_edge_ok"] = bool(
            entry_info.get("cost_adjusted_edge_ok")
        )
        state["monitor_output"]["entry_candidate_cost_adjusted_edge_pct"] = entry_info.get("cost_adjusted_edge_pct")
        state["monitor_output"]["entry_candidate_cost_drag_pct"] = entry_info.get("cost_drag_pct")
        state["monitor_output"]["entry_candidate_cost_filter"] = dict(entry_cost_filter_snapshot)
    _emit_monitor_event(
        state,
        name="entry_blocker_surface",
        payload=entry_blocker_surface,
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    entry_decision_detail = {
        "decision": final_entry_decision,
        "reason": str(entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait"),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_reason": str(entry_info.get("reason") or ""),
        "signal_chain": list(entry_info.get("signal_chain") or []),
        "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
        "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
        "condition_scores": dict(entry_info.get("condition_scores") or {}),
        "grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
        "guard_blocked": bool(entry_info.get("guard_blocked")),
        "guard_reason": str(entry_info.get("guard_reason") or ""),
        "buy_submitted": bool(buy_submitted),
        "buy_skipped_reason": buy_skipped_reason,
        "previous_close": entry_event_metrics.get("previous_close"),
        "session_open": entry_event_metrics.get("session_open"),
        "open_gap_pct": entry_event_metrics.get("open_gap_pct"),
        "prev_close_distance_pct": entry_event_metrics.get("prev_close_distance_pct"),
        "minutes_since_session_open": entry_event_metrics.get("minutes_since_session_open"),
        "opening_gap_chase_observed": bool(entry_event_metrics.get("opening_gap_chase_observed")),
        "opening_gap_context_observation_only": bool(entry_event_metrics.get("opening_gap_context_observation_only")),
        "metrics": entry_event_metrics,
        "applied_policy": dict(entry_applied_policy),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "thresholds": dict(entry_info.get("thresholds") or {}),
        "passed_checks": list(entry_info.get("passed_checks") or []),
        "failed_checks": list(entry_info.get("failed_checks") or []),
        "primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "total_score": entry_info.get("total_score"),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "monitor_memory_bias_observation_only": bool(entry_info.get("monitor_memory_bias_observation_only")),
        "monitor_memory_bias_observed_deltas": list(entry_info.get("monitor_memory_bias_observed_deltas") or []),
        "minute_source_meta": dict(entry_info.get("minute_source_meta") or {}),
        "minute_fetch_meta": dict(entry_info.get("minute_fetch_meta") or {}),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "entry_candidate_cascade": dict(entry_candidate_cascade),
        "entry_blocker_surface": dict(entry_blocker_surface),
        "monitor_focus_context": dict(monitor_focus_context),
        "scanner_selected_symbol": scanner_selected_symbol,
        "entry_candidate_symbol": entry_candidate_symbol,
        "entry_final_symbol": entry_final_symbol,
        "position_focus_symbol": position_focus_symbol,
        "monitor_output_symbol": monitor_output_symbol,
        "monitor_focus_mode": monitor_focus_mode,
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "entry_check_summary": str(monitor_policy_trace.get("entry_check_summary") or ""),
        "entry_blockers": list(monitor_policy_trace.get("entry_blockers") or []),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "flow_instruction_applied": bool(monitor_policy_trace.get("flow_instruction_applied")),
        "no_trade_reason_applied": bool(monitor_policy_trace.get("no_trade_reason_applied")),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    state["monitor_entry_decision_detail"] = dict(entry_decision_detail)
    _emit_monitor_event(
        state,
        name="entry_decision_detail",
        payload=entry_decision_detail,
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    scoring_event_payload = {
        "run_id": str(state.get("run_id") or ""),
        "symbol": str(monitor_symbol or entry_symbol or ""),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "minute_source_meta": dict(entry_info.get("minute_source_meta") or {}),
        "minute_fetch_meta": dict(entry_info.get("minute_fetch_meta") or {}),
        "total_score": entry_info.get("total_score"),
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "final_decision": final_entry_decision,
        "primary_reason_code": str(entry_info.get("reason") or ""),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "entry_blocker_surface": dict(entry_blocker_surface),
    }
    if not bool(entry_info.get("hard_filter_passed")):
        _emit_monitor_event(
            state,
            name="hard_filter_failed",
            payload=dict(scoring_event_payload),
            level="info",
            symbol=monitor_symbol or entry_symbol,
        )
    _emit_monitor_event(
        state,
        name="score_computed",
        payload=dict(scoring_event_payload),
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    _emit_monitor_event(
        state,
        name="entry_decision",
        payload=dict(scoring_event_payload),
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    sell_submitted = any(str((intent or {}).get("side") or "").strip().upper() == "SELL" for intent in list(intents or []))
    sell_skipped_reason = ""
    if bool(exit_info.get("exit_signal_detected")) and not bool(sell_submitted):
        sell_skipped_reason = str(exit_info.get("sell_guard_reason") or exit_info.get("reason") or "sell_not_submitted").strip()
    exit_decision_detail = {
        "exit_triggered": bool(exit_info.get("triggered")),
        "triggered_rule": str(exit_info.get("reason") or ""),
        "pnl_ratio": exit_info.get("pnl_ratio"),
        "raw_pnl_ratio": exit_info.get("raw_pnl_ratio"),
        "gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
        "technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
        "effective_pnl_ratio": exit_info.get("effective_pnl_ratio"),
        "stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
        "stop_pnl_ratio_source": str(exit_info.get("stop_pnl_ratio_source") or ""),
        "hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
        "hard_stop_pnl_ratio_source": str(exit_info.get("hard_stop_pnl_ratio_source") or ""),
        "cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
        "cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
        "cost_drag_pressure_reason": str(exit_info.get("cost_drag_pressure_reason") or ""),
        "stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
        "stop_loss_cost_drag_blocked_reason": str(exit_info.get("stop_loss_cost_drag_blocked_reason") or ""),
        "price": exit_info.get("price"),
        "technical_price": exit_info.get("technical_price"),
        "technical_price_source": str(exit_info.get("technical_price_source") or ""),
        "effective_price": exit_info.get("effective_price"),
        "account_mark_price": exit_info.get("account_mark_price"),
        "account_mark_price_source": str(exit_info.get("account_mark_price_source") or ""),
        "account_unrealized_pnl": exit_info.get("account_unrealized_pnl"),
        "account_pnl_ratio_source": str(exit_info.get("account_pnl_ratio_source") or ""),
        "pnl_crosscheck_applied": bool(exit_info.get("pnl_crosscheck_applied")),
        "pnl_crosscheck_reason": str(exit_info.get("pnl_crosscheck_reason") or ""),
        "pnl_crosscheck_gap": exit_info.get("pnl_crosscheck_gap"),
        "price_anomaly_flag": bool(exit_info.get("price_anomaly_flag")),
        "price_anomaly_reason": str(exit_info.get("price_anomaly_reason") or ""),
        "pnl_fallback_applied": bool(exit_info.get("pnl_fallback_applied")),
        "fallback_price_source": str(exit_info.get("fallback_price_source") or ""),
        "confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "confirm_required": int(exit_info.get("exit_confirm_ticks") or 0),
        "guard_blocked": bool(exit_info.get("sell_guard_blocked")),
        "guard_reason": str(exit_info.get("sell_guard_reason") or ""),
        "hold_block_reason": str(exit_info.get("hold_block_reason") or ""),
        "final_exit_thresholds": dict(exit_info.get("final_exit_thresholds") or {}),
        "exit_threshold_source": str(exit_info.get("exit_threshold_source") or ""),
        "max_runup_pct": exit_info.get("max_runup_pct"),
        "peak_drawdown_from_peak": exit_info.get("peak_drawdown_from_peak"),
        "peak_drawdown_armed": bool(exit_info.get("peak_drawdown_armed")),
        "peak_drawdown_mode": str(exit_info.get("peak_drawdown_mode") or ""),
        "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
        "peak_drawdown_source": str(exit_info.get("peak_drawdown_source") or ""),
        "exit_trigger_metric_name": str(exit_info.get("exit_trigger_metric_name") or ""),
        "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
        "exit_trigger_metric_source": str(exit_info.get("exit_trigger_metric_source") or ""),
        "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
        "round_trip_cost_floor_pct": exit_info.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": exit_info.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
        "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
        "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
        "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
        "expected_exit_price": exit_info.get("expected_exit_price"),
        "expected_exit_price_source": str(exit_info.get("expected_exit_price_source") or ""),
        "expected_exit_price_fallback_used": bool(exit_info.get("expected_exit_price_fallback_used")),
        "expected_exit_slippage_buffer_pct": exit_info.get("expected_exit_slippage_buffer_pct"),
        "expected_exit_pnl_ratio": exit_info.get("expected_exit_pnl_ratio"),
        "expected_exit_net_pnl_ratio": exit_info.get("expected_exit_net_pnl_ratio"),
        "expected_exit_profit_floor_met": bool(exit_info.get("expected_exit_profit_floor_met")),
        "expected_exit_profit_floor_gap_pct": exit_info.get("expected_exit_profit_floor_gap_pct"),
        "expected_exit_profit_floor_blocked": bool(exit_info.get("expected_exit_profit_floor_blocked")),
        "expected_exit_profit_floor_blocked_reason": str(
            exit_info.get("expected_exit_profit_floor_blocked_reason") or ""
        ),
        "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
        "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
        "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
        "protective_exit_hard_invalidation_reason": str(
            exit_info.get("protective_exit_hard_invalidation_reason") or ""
        ),
        "risk_reward_take_profit_target_pct": exit_info.get("risk_reward_take_profit_target_pct"),
        "risk_reward_take_profit_rung": exit_info.get("risk_reward_take_profit_rung"),
        "resistance_price": exit_info.get("resistance_price"),
        "resistance_price_source": str(exit_info.get("resistance_price_source") or ""),
        "resistance_distance_pct": exit_info.get("resistance_distance_pct"),
        "profit_time_stop_peak_giveback_pct": exit_info.get("profit_time_stop_peak_giveback_pct"),
        "partial_exit": bool(exit_info.get("partial_exit")),
        "exit_qty": exit_info.get("exit_qty"),
        "exit_qty_fraction": exit_info.get("exit_qty_fraction"),
        "profit_ladder_level_pct": exit_info.get("profit_ladder_level_pct"),
        "profit_ladder_level_index": exit_info.get("profit_ladder_level_index"),
        "volume_ratio": exit_info.get("volume_ratio"),
        "execution_strength": exit_info.get("execution_strength"),
        "trade_strength": exit_info.get("trade_strength"),
        "opening_gap_chase_observed": bool(exit_info.get("opening_gap_chase_observed")),
        "open_gap_pct": exit_info.get("open_gap_pct"),
        "prev_close_distance_pct": exit_info.get("prev_close_distance_pct"),
        "position_entry_risk_applied": bool(exit_info.get("position_entry_risk_applied")),
        "position_entry_stop_loss_pct": exit_info.get("position_entry_stop_loss_pct"),
        "position_entry_stop_loss_source": str(exit_info.get("position_entry_stop_loss_source") or ""),
        "position_entry_invalidation_price": exit_info.get("position_entry_invalidation_price"),
        "sell_submitted": bool(sell_submitted),
        "sell_skipped_reason": sell_skipped_reason,
        "final_reason": current_reason,
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "exit_trigger_basis": dict(monitor_policy_trace.get("exit_trigger_basis") or {}),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    state["monitor_exit_decision_detail"] = dict(exit_decision_detail)
    _emit_monitor_event(
        state,
        name="exit_decision_detail",
        payload=exit_decision_detail,
        level="warning" if bool(exit_info.get("triggered")) else "info",
        symbol=monitor_symbol,
    )
    triggered_rules = []
    if bool(exit_info.get("triggered")) and str(exit_info.get("reason") or "").strip():
        triggered_rules.append(str(exit_info.get("reason") or "").strip())
    if bool(entry_info.get("triggered")) and str(entry_info.get("pattern") or "").strip():
        triggered_rules.append(f"entry:{str(entry_info.get('pattern') or '').strip()}")
    blocked_rules = []
    if bool(entry_info.get("guard_blocked")) and str(entry_info.get("guard_reason") or "").strip():
        blocked_rules.append(str(entry_info.get("guard_reason") or "").strip())
    if bool(exit_info.get("sell_guard_blocked")) and str(exit_info.get("sell_guard_reason") or "").strip():
        blocked_rules.append(str(exit_info.get("sell_guard_reason") or "").strip())
    blocked_rules.extend([str(x or "").strip() for x in list(entry_info.get("failed_checks") or []) if str(x or "").strip()])
    reason_chain = [
        str(exit_info.get("monitor_reason") or "").strip(),
        str(exit_info.get("reason") or "").strip(),
        str(entry_info.get("reason") or "").strip(),
        str((state.get("monitor_output") or {}).get("entry_exit_reason") or "").strip(),
    ]
    reason_chain = [x for x in reason_chain if x]
    if isinstance(state.get("monitor_output"), dict):
        state["monitor_output"]["policy_ref"] = dict(monitor_policy_trace.get("policy_ref") or {})
        state["monitor_output"]["entry_check_summary"] = str(monitor_policy_trace.get("entry_check_summary") or "")
        state["monitor_output"]["entry_blockers"] = list(monitor_policy_trace.get("entry_blockers") or [])
        state["monitor_output"]["timing_assessment"] = dict(monitor_policy_trace.get("timing_assessment") or {})
        state["monitor_output"]["exit_trigger_basis"] = dict(monitor_policy_trace.get("exit_trigger_basis") or {})
        state["monitor_output"]["exit_vs_strategy_intent"] = dict(exit_info.get("exit_vs_strategy_intent") or {})
        state["monitor_output"]["final_exit_thresholds"] = dict(exit_info.get("final_exit_thresholds") or {})
        state["monitor_output"]["exit_threshold_source"] = str(exit_info.get("exit_threshold_source") or "")
        state["monitor_output"]["hold_block_reason"] = str(exit_info.get("hold_block_reason") or "")
        state["monitor_output"]["max_runup_pct"] = exit_info.get("max_runup_pct")
        state["monitor_output"]["peak_drawdown_from_peak"] = exit_info.get("peak_drawdown_from_peak")
        state["monitor_output"]["peak_drawdown_armed"] = bool(exit_info.get("peak_drawdown_armed"))
        state["monitor_output"]["peak_drawdown_mode"] = str(exit_info.get("peak_drawdown_mode") or "")
        state["monitor_output"]["final_peak_drawdown_ratio"] = exit_info.get("final_peak_drawdown_ratio")
        state["monitor_output"]["peak_drawdown_source"] = str(exit_info.get("peak_drawdown_source") or "")
        state["monitor_output"]["exit_trigger_metric_name"] = str(exit_info.get("exit_trigger_metric_name") or "")
        state["monitor_output"]["exit_trigger_metric_value"] = exit_info.get("exit_trigger_metric_value")
        state["monitor_output"]["exit_trigger_metric_source"] = str(exit_info.get("exit_trigger_metric_source") or "")
        state["monitor_output"]["exit_gross_pnl_ratio"] = exit_info.get("gross_pnl_ratio")
        state["monitor_output"]["exit_technical_pnl_ratio"] = exit_info.get("technical_pnl_ratio")
        state["monitor_output"]["exit_stop_pnl_ratio"] = exit_info.get("stop_pnl_ratio")
        state["monitor_output"]["exit_stop_pnl_ratio_source"] = str(exit_info.get("stop_pnl_ratio_source") or "")
        state["monitor_output"]["exit_hard_stop_pnl_ratio"] = exit_info.get("hard_stop_pnl_ratio")
        state["monitor_output"]["exit_hard_stop_pnl_ratio_source"] = str(
            exit_info.get("hard_stop_pnl_ratio_source") or ""
        )
        state["monitor_output"]["exit_cost_drag_pressure"] = bool(exit_info.get("cost_drag_pressure"))
        state["monitor_output"]["exit_cost_drag_pressure_pct"] = exit_info.get("cost_drag_pressure_pct")
        state["monitor_output"]["exit_cost_drag_pressure_reason"] = str(exit_info.get("cost_drag_pressure_reason") or "")
        state["monitor_output"]["exit_stop_loss_cost_drag_blocked"] = bool(
            exit_info.get("stop_loss_cost_drag_blocked")
        )
        state["monitor_output"]["exit_stop_loss_cost_drag_blocked_reason"] = str(
            exit_info.get("stop_loss_cost_drag_blocked_reason") or ""
        )
        state["monitor_output"]["risk_reward_take_profit_target_pct"] = exit_info.get("risk_reward_take_profit_target_pct")
        state["monitor_output"]["risk_reward_take_profit_rung"] = exit_info.get("risk_reward_take_profit_rung")
        state["monitor_output"]["resistance_price"] = exit_info.get("resistance_price")
        state["monitor_output"]["resistance_price_source"] = str(exit_info.get("resistance_price_source") or "")
        state["monitor_output"]["resistance_distance_pct"] = exit_info.get("resistance_distance_pct")
        state["monitor_output"]["profit_time_stop_peak_giveback_pct"] = exit_info.get("profit_time_stop_peak_giveback_pct")
        state["monitor_output"]["partial_exit"] = bool(exit_info.get("partial_exit"))
        state["monitor_output"]["exit_qty"] = exit_info.get("exit_qty")
        state["monitor_output"]["exit_qty_fraction"] = exit_info.get("exit_qty_fraction")
        state["monitor_output"]["profit_ladder_level_pct"] = exit_info.get("profit_ladder_level_pct")
        state["monitor_output"]["profit_ladder_level_index"] = exit_info.get("profit_ladder_level_index")
        state["monitor_output"]["volume_ratio"] = exit_info.get("volume_ratio")
        state["monitor_output"]["execution_strength"] = exit_info.get("execution_strength")
        state["monitor_output"]["trade_strength"] = exit_info.get("trade_strength")
        state["monitor_output"]["opening_gap_chase_observed"] = bool(exit_info.get("opening_gap_chase_observed"))
        state["monitor_output"]["open_gap_pct"] = exit_info.get("open_gap_pct")
        state["monitor_output"]["prev_close_distance_pct"] = exit_info.get("prev_close_distance_pct")
        state["monitor_output"]["position_entry_risk_applied"] = bool(exit_info.get("position_entry_risk_applied"))
        state["monitor_output"]["position_entry_stop_loss_pct"] = exit_info.get("position_entry_stop_loss_pct")
        state["monitor_output"]["position_entry_stop_loss_source"] = str(exit_info.get("position_entry_stop_loss_source") or "")
        state["monitor_output"]["position_entry_invalidation_price"] = exit_info.get("position_entry_invalidation_price")
        state["monitor_output"]["received_policy"] = dict(entry_info.get("received_policy") or entry_received_policy or {})
        state["monitor_output"]["received_policy_source"] = str(entry_info.get("received_policy_source") or entry_policy_origin or "")
        state["monitor_output"]["policy_contract"] = dict(entry_info.get("policy_contract") or entry_policy_contract or {})
        state["monitor_output"]["effective_policy"] = dict(entry_info.get("effective_policy") or entry_applied_policy)
        state["monitor_output"]["effective_policy_source"] = str(entry_info.get("effective_policy_source") or "")
        state["monitor_output"]["effective_policy_source_chain"] = list(entry_info.get("effective_policy_source_chain") or [])
        state["monitor_output"]["policy_adjustments"] = dict(entry_info.get("policy_adjustments") or {})
        state["monitor_output"]["policy_adjustment_summary"] = str(entry_info.get("policy_adjustment_summary") or "")
        state["monitor_output"]["policy_adjustment_reasoning"] = str(entry_info.get("policy_adjustment_reasoning") or "")
        state["monitor_output"]["effective_policy_deltas"] = list(entry_info.get("effective_policy_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_applied"] = bool(entry_info.get("monitor_memory_bias_applied"))
        state["monitor_output"]["monitor_memory_bias_observation_only"] = bool(entry_info.get("monitor_memory_bias_observation_only"))
        state["monitor_output"]["monitor_memory_bias"] = dict(entry_info.get("monitor_memory_bias") or {})
        state["monitor_output"]["monitor_memory_bias_summary"] = dict(entry_info.get("monitor_memory_bias_summary") or {})
        state["monitor_output"]["monitor_memory_bias_deltas"] = list(entry_info.get("monitor_memory_bias_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_observed_deltas"] = list(entry_info.get("monitor_memory_bias_observed_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_hold_applied"] = bool(exit_info.get("monitor_memory_bias_hold_applied"))
        state["monitor_output"]["monitor_memory_bias_hold_deltas"] = list(exit_info.get("monitor_memory_bias_hold_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_exit_applied"] = bool(exit_info.get("monitor_memory_bias_exit_applied"))
        state["monitor_output"]["monitor_memory_bias_exit_deltas"] = list(exit_info.get("monitor_memory_bias_exit_deltas") or [])
        state["monitor_output"]["commander_memory_application_trace"] = dict(commander_memory_application_trace)
        state["monitor_output"]["monitor_memory_application_trace"] = dict(commander_memory_application_trace)
        state["monitor_output"]["applied_policy"] = dict(entry_applied_policy)
        state["monitor_output"]["policy_source"] = str((monitor_policy_trace.get("policy_ref") or {}).get("policy_source") or "")
        state["monitor_output"]["policy_validation_status"] = str((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_status") or "")
        state["monitor_output"]["policy_fallback_used"] = bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_used"))
        state["monitor_output"]["policy_fallback_reason"] = str((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_reason") or "")
        state["monitor_output"]["policy_partial_normalized"] = bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_partial_normalized"))
        state["monitor_output"]["policy_default_filled_fields"] = list((monitor_policy_trace.get("policy_ref") or {}).get("policy_default_filled_fields") or [])
        state["monitor_output"]["policy_validation_missing_fields"] = list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_missing_fields") or [])
        state["monitor_output"]["policy_validation_invalid_fields"] = list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_invalid_fields") or [])
        state["monitor_output"]["override_reason"] = str((monitor_policy_trace.get("policy_ref") or {}).get("override_reason") or "")
        state["monitor_output"]["applied_policy_source_chain"] = list((monitor_policy_trace.get("policy_ref") or {}).get("applied_policy_source_chain") or [])
        state["monitor_output"]["commander_context_consumed"] = bool(monitor_policy_trace.get("commander_context_consumed"))
        state["monitor_output"]["consumed_fields"] = list(monitor_policy_trace.get("consumed_fields") or [])
        state["monitor_output"]["shadow_used"] = bool(monitor_policy_trace.get("shadow_used"))
        state["monitor_output"]["strategist_fallback_used"] = bool(monitor_policy_trace.get("strategist_fallback_used"))
        state["monitor_output"]["hard_filter_passed"] = bool(entry_info.get("hard_filter_passed"))
        state["monitor_output"]["hard_filter_fail_reasons"] = list(entry_info.get("hard_filter_fail_reasons") or [])
        state["monitor_output"]["total_score"] = entry_info.get("total_score")
        state["monitor_output"]["score_breakdown"] = dict(entry_info.get("score_breakdown") or {})
        state["monitor_output"]["policy_interpretation"] = dict(entry_info.get("policy_interpretation") or {})
        state["monitor_output"]["signal_evidence"] = dict(entry_info.get("signal_evidence") or {})
        state["monitor_output"]["chart_structure_features"] = dict(entry_info.get("chart_structure_features") or {})
        state["monitor_output"]["policy_interpreter_trace"] = dict(entry_info.get("policy_interpreter_trace") or {})
        state["monitor_output"]["policy_alignment_summary"] = dict(entry_info.get("policy_alignment_summary") or {})
        state["monitor_output"]["policy_aware_gating"] = dict(entry_info.get("policy_aware_gating") or {})
        state["monitor_output"]["chart_structure_decision_hint"] = dict(entry_info.get("chart_structure_decision_hint") or {})
        state["monitor_output"]["no_trade_surface"] = dict(monitor_no_trade_surface)
        state["monitor_output"]["scanner_monitor_handoff"] = dict(scanner_monitor_handoff)
        state["monitor_output"]["entry_threshold"] = entry_info.get("entry_threshold")
        state["monitor_output"]["score_passed"] = bool(entry_info.get("score_passed"))
        state["monitor_output"]["scoring_mode"] = str(entry_info.get("scoring_mode") or "disabled")
        state["monitor_output"]["legacy_entry_decision"] = str(entry_info.get("legacy_entry_decision") or "WAIT")
        state["monitor_output"]["scoring_entry_decision"] = str(entry_info.get("scoring_entry_decision") or "WAIT")
    state["monitor_evaluation"] = {
        "triggered_rules": list(triggered_rules),
        "blocked_rules": list(dict.fromkeys(blocked_rules))[:8],
        "posture": current_posture,
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "total_score": entry_info.get("total_score"),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "entry_check_summary": str(monitor_policy_trace.get("entry_check_summary") or ""),
        "entry_blockers": list(monitor_policy_trace.get("entry_blockers") or []),
        "timing_assessment": dict(monitor_policy_trace.get("timing_assessment") or {}),
        "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "flow_instruction_applied": bool(monitor_policy_trace.get("flow_instruction_applied")),
        "no_trade_reason_applied": bool(monitor_policy_trace.get("no_trade_reason_applied")),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    state["monitor_action_decision"] = {
        "decision": str((state.get("monitor_output") or {}).get("intent_side") or "NOOP"),
        "action_reason_human": str((state.get("monitor_output") or {}).get("entry_exit_reason") or current_reason),
        "decision_reason_chain": list(reason_chain),
        "confidence": float(_to_float(entry_info.get("confidence"))),
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "triggered_rules": list(triggered_rules),
        "blocked_rules": list(dict.fromkeys(blocked_rules))[:8],
        "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "policy_adjustment_reasoning": str(entry_info.get("policy_adjustment_reasoning") or ""),
        "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "applied_policy": dict(entry_applied_policy),
        "policy_source": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_source") or ""),
        "policy_validation_status": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_status") or ""),
        "policy_fallback_used": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_used")),
        "policy_fallback_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_reason") or ""),
        "policy_partial_normalized": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_partial_normalized")),
        "policy_default_filled_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_default_filled_fields") or []),
        "policy_validation_missing_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_missing_fields") or []),
        "policy_validation_invalid_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_invalid_fields") or []),
        "override_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("override_reason") or ""),
        "applied_policy_source_chain": list((monitor_policy_trace.get("policy_ref") or {}).get("applied_policy_source_chain") or []),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "entry_check_summary": str(monitor_policy_trace.get("entry_check_summary") or ""),
        "entry_blockers": list(monitor_policy_trace.get("entry_blockers") or []),
        "exit_trigger_basis": dict(monitor_policy_trace.get("exit_trigger_basis") or {}),
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "total_score": entry_info.get("total_score"),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    _emit_monitor_event(
        state,
        name="cycle_summary",
        payload={
            "selected_symbol": str((selected.get("symbol") if isinstance(selected, dict) else "") or ""),
            "monitor_symbol": monitor_symbol,
            "posture": current_posture,
            "monitor_reason": current_reason,
            "open_position_count": int(open_position_count),
            "has_intent": bool(intents),
            "intent_side": str((state.get("monitor_output") or {}).get("intent_side") or "NOOP"),
            "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
            "price_source": str(exit_info.get("price_source") or ""),
            "feature_source": str(exit_info.get("feature_source") or ""),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "buy_blocked_open_position": bool(buy_blocked_open_position),
            "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
            "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
            "minutes_to_close": entry_info.get("minutes_to_close"),
            "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
            "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
            "closeout_window_active": bool(entry_info.get("closeout_window_active")),
            "entry_blocker_surface": dict(entry_blocker_surface),
        },
        symbol=monitor_symbol,
    )
    _log_monitor_summary(
        state,
        {
            "has_intent": bool(intents),
            "intent_count": len(intents),
            "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
            "order_status_fallback": bool(fallback_reasons),
            "exit_policy_enabled": bool(exit_info.get("enabled")),
            "exit_evaluated": bool(exit_info.get("evaluated")),
            "exit_triggered": bool(exit_info.get("triggered")),
            "exit_reason": str(exit_info.get("reason") or ""),
            "monitor_reason": str(exit_info.get("monitor_reason") or ""),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "peak_drawdown": exit_info.get("peak_drawdown"),
            "peak_price": exit_info.get("peak_price"),
            "vwap_distance": exit_info.get("vwap_distance"),
            "price_source": str(exit_info.get("price_source") or ""),
            "feature_source": str(exit_info.get("feature_source") or ""),
            "min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
            "sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
            "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
            "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
            "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
            "sell_guard_reason": str(exit_info.get("sell_guard_reason") or ""),
            "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
            "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
            "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
            "position_sizing_enabled": bool(sizing_info.get("enabled")),
            "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
            "position_sizing_qty": int(sizing_info.get("qty") or 0),
            "position_sizing_reason": str(sizing_info.get("reason") or ""),
            "position_sizing_stop_loss_pct": (sizing_info.get("inputs") or {}).get("stop_loss_pct")
            if isinstance(sizing_info.get("inputs"), dict)
            else None,
            "position_sizing_stop_loss_source": str(
                ((sizing_info.get("inputs") or {}).get("stop_loss_source") if isinstance(sizing_info.get("inputs"), dict) else "")
                or ""
            ),
            "position_sizing_invalidation_price": (sizing_info.get("inputs") or {}).get("invalidation_price")
            if isinstance(sizing_info.get("inputs"), dict)
            else None,
            "open_position_count": int(open_position_count),
            "block_buy_when_open_position": bool(block_buy_open_position),
            "buy_blocked_open_position": bool(buy_blocked_open_position),
            "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
            "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
            "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
            "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
            "minutes_to_close": entry_info.get("minutes_to_close"),
            "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
            "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
            "closeout_window_active": bool(entry_info.get("closeout_window_active")),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_reason": str(entry_info.get("reason") or ""),
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
            "entry_lane": str(entry_info.get("entry_lane") or "strict"),
            "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
            "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
            "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
            "cost_drag_pct": entry_info.get("cost_drag_pct"),
            "decision_outcome": str(monitor_no_trade_surface.get("decision_outcome") or final_entry_decision),
            "pre_intent_decision": str(monitor_no_trade_surface.get("pre_intent_decision") or ""),
            "no_trade_stage": str(monitor_no_trade_surface.get("no_trade_stage") or ""),
            "no_trade_reason_code": str(monitor_no_trade_surface.get("no_trade_reason_code") or ""),
            "no_trade_reason_summary": str(monitor_no_trade_surface.get("no_trade_reason_summary") or ""),
            "dominant_blocker": str(monitor_no_trade_surface.get("dominant_blocker") or ""),
            "blocker_family": str(monitor_no_trade_surface.get("blocker_family") or ""),
            "blocker_metrics": dict(monitor_no_trade_surface.get("blocker_metrics") or {}),
            "distance_to_ready": dict(monitor_no_trade_surface.get("distance_to_ready") or {}),
            "near_ready_flag": bool(monitor_no_trade_surface.get("near_ready_flag")),
            "required_checks_failed": list(monitor_no_trade_surface.get("required_checks_failed") or []),
            "preferred_checks_failed": list(monitor_no_trade_surface.get("preferred_checks_failed") or []),
            "relaxable_checks_failed": list(monitor_no_trade_surface.get("relaxable_checks_failed") or []),
            "evidence_snapshot": dict(monitor_no_trade_surface.get("evidence_snapshot") or {}),
            "scanner_monitor_handoff": dict(scanner_monitor_handoff),
            "entry_blocker_surface": dict(entry_blocker_surface),
        },
    )
    append_decision_trace(
        state,
        agent="monitor",
        event="entry_exit_decision",
        payload={
            "selected_symbol": str((selected.get("symbol") if isinstance(selected, dict) else "") or ""),
            "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
            "exit_reason": str(exit_info.get("reason") or ""),
            "thresholds": dict(exit_info.get("thresholds") or {}),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "peak_drawdown": exit_info.get("peak_drawdown"),
            "peak_price": exit_info.get("peak_price"),
            "vwap_distance": exit_info.get("vwap_distance"),
            "price_source": str(exit_info.get("price_source") or ""),
            "price_source_policy": str(exit_info.get("price_source_policy") or ""),
            "feature_source": str(exit_info.get("feature_source") or ""),
            "min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
            "sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
            "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
            "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
            "monitor_reason": str(exit_info.get("monitor_reason") or ""),
            "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
            "strategy_horizon": str(exit_info.get("strategy_horizon") or ""),
            "source_strategy_horizon": str(exit_info.get("source_strategy_horizon") or ""),
            "horizon_behavior_translation": dict(exit_info.get("horizon_behavior_translation") or {}),
            "strategy_frame_adjustments": list(exit_info.get("strategy_frame_adjustments") or []),
            "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_signal_chain": list(entry_info.get("signal_chain") or []),
            "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
            "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
            "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
            "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
            "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
            "received_policy_source": str(entry_info.get("received_policy_source") or entry_policy_origin or ""),
            "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
            "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
            "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
            "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
            "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
            "policy_adjustment_reasoning": str(entry_info.get("policy_adjustment_reasoning") or ""),
            "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
            "applied_policy": dict(entry_applied_policy),
            "policy_source": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_source") or ""),
            "policy_validation_status": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_status") or ""),
            "policy_fallback_used": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_used")),
            "policy_fallback_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_reason") or ""),
            "policy_partial_normalized": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_partial_normalized")),
            "policy_default_filled_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_default_filled_fields") or []),
            "policy_validation_missing_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_missing_fields") or []),
            "policy_validation_invalid_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_invalid_fields") or []),
            "override_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("override_reason") or ""),
            "applied_policy_source_chain": list((monitor_policy_trace.get("policy_ref") or {}).get("applied_policy_source_chain") or []),
            "entry_passed_checks": list(entry_info.get("passed_checks") or []),
            "entry_failed_checks": list(entry_info.get("failed_checks") or []),
            "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
            "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
            "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        },
    )
    try:
        record_decision_bridge(
            run_id=run_id,
            agent="monitor",
            stage="decision_bridge",
            raw_input={
                "selected_symbol": (
                    str(selected.get("symbol") or "")
                    if isinstance(selected, dict)
                    else ""
                ),
                "monitor_policy": dict(monitor_policy),
                "intents_preview": [
                    {
                        "symbol": str(x.get("symbol") or ""),
                        "side": str(x.get("side") or ""),
                        "qty": _to_int(x.get("qty")),
                    }
                    for x in list(intents)[:3]
                    if isinstance(x, dict)
                ],
            },
            parsed_output={
                "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
                "exit_reason": str(exit_info.get("reason") or ""),
                "monitor_reason": str(exit_info.get("monitor_reason") or ""),
                "position_age_seconds": exit_info.get("position_age_seconds"),
                "peak_drawdown": exit_info.get("peak_drawdown"),
                "peak_price": exit_info.get("peak_price"),
                "vwap_distance": exit_info.get("vwap_distance"),
                "price_source": str(exit_info.get("price_source") or ""),
                "feature_source": str(exit_info.get("feature_source") or ""),
                "exit_signal_detected": bool(exit_info.get("exit_signal_detected")),
                "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
                "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
                "sell_guard_reason": str(exit_info.get("sell_guard_reason") or ""),
                "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
                "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
                "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
                "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
                "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
                "minutes_to_close": entry_info.get("minutes_to_close"),
                "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
                "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
                "closeout_window_active": bool(entry_info.get("closeout_window_active")),
                "entry_evaluated": bool(entry_info.get("evaluated")),
                "entry_triggered": bool(entry_info.get("triggered")),
                "entry_pattern": str(entry_info.get("pattern") or ""),
                "entry_reason": str(entry_info.get("reason") or ""),
                "entry_signal_chain": list(entry_info.get("signal_chain") or []),
                "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
                "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
                "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
                "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
                "entry_metrics": dict(entry_info.get("metrics") or {}),
                "entry_thresholds": dict(entry_info.get("thresholds") or {}),
                "entry_passed_checks": list(entry_info.get("passed_checks") or []),
                "entry_failed_checks": list(entry_info.get("failed_checks") or []),
                "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
                "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
                "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
                "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
                "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            },
            decision_link={
                "decision_chain": {
                    "theme": str((state.get("themes") or [""])[0] if isinstance(state.get("themes"), list) and state.get("themes") else ""),
                    "scanner_selected": state.get("top_stock") or (
                        str(selected.get("symbol") or "") if isinstance(selected, dict) else ""
                    ),
                    "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
                    "exit_reason": str(exit_info.get("reason") or ""),
                }
            },
        )
    except Exception:
        pass
    try:
        write_monitor_artifact(state)
    except Exception:
        pass
    return state
