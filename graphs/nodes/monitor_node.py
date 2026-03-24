from __future__ import annotations

"""Canonical Monitor node for integrated runtime.

Role boundary:
- monitors selected stock / active position state
- emits entry/exit intents only
- never re-ranks symbol universe and never executes orders
"""

import os
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_market_quotes,
    extract_minute_ohlcv_by_symbol,
    extract_order_status,
)
from libs.core.symbols import normalize_symbol
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input
from libs.runtime.canonical_artifacts import write_monitor_artifact
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.exit_policy import apply_env_stop_take_fallbacks, evaluate_exit_policy
from libs.runtime.feature_engine import build_feature_row
from libs.runtime.intraday_monitor_signals import (
    evaluate_intraday_entry_signal,
    resolve_intraday_entry_policy,
)
from libs.runtime.position_sizing import evaluate_position_size
from libs.strategies.contracts import coerce_strategist_output


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _normalize_status(v: Any) -> str:
    return str(v or "").strip().upper()


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


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
        return None, "none"

    try:
        from libs.skills.runner import CompositeSkillRunner

        built = CompositeSkillRunner.from_env()
        state["skill_runner"] = built
        return built, "auto.composite_skill_runner"
    except Exception:
        return None, "auto_runner_error"


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


def _ensure_monitor_minute_ohlcv_for_symbol(
    state: Dict[str, Any],
    *,
    symbol: str,
    timeframe_minutes: int,
    now_epoch: int = 0,
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
            "minute_refetch_produced_fresh_snapshot": False,
        }
        return state

    run_id = str(state.get("run_id") or "monitor-minute-fetch")
    raw = runner.run(
        run_id=run_id,
        skill="market.minute_ohlcv",
        args={
            "symbol": sym,
            "timeframe_minutes": max(1, int(timeframe_minutes or 1)),
            "adjusted_price": "1",
        },
    )
    rec = _monitor_skill_output_to_record(raw)
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

    result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
    if str(result.get("action") or "").strip().lower() != "ready":
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
            "minute_refetch_failure_reason": str(result.get("action") or "refetch_not_ready"),
            "minute_refetch_produced_fresh_snapshot": False,
        }
        return state

    data = result.get("data") if isinstance(result, dict) else None
    rows = data.get("rows") if isinstance(data, dict) and isinstance(data.get("rows"), list) else []
    normalized_rows = [dict(row) for row in rows if isinstance(row, dict)]
    if not normalized_rows:
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
            "minute_refetch_produced_fresh_snapshot": False,
        }
        return state

    minute_root = dict(existing_root or {})
    minute_root[sym] = normalized_rows
    state["minute_ohlcv_by_symbol"] = minute_root
    latest_candle_ts = _latest_row_ts(normalized_rows)
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
        "minute_refetch_produced_fresh_snapshot": not bool(final_stale_reason),
        "previous_latest_candle_ts": existing_latest_candle_ts,
    }
    return state


def _resolve_min_hold_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("min_hold_seconds") if isinstance(policy, dict) else None
    if raw is None:
        raw = os.getenv("MIN_HOLD_SECONDS", "600")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 600


def _resolve_sell_cooldown_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("sell_cooldown_sec") if isinstance(policy, dict) else None
    if raw is None and isinstance(policy, dict):
        raw = policy.get("sell_cooldown_seconds")
    if raw is None:
        raw = os.getenv("SELL_COOLDOWN", "")
    if raw in (None, ""):
        raw = os.getenv("SELL_COOLDOWN_SEC", "300")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 300


def _resolve_exit_confirm_ticks(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("exit_confirm_ticks") if isinstance(policy, dict) else None
    if raw is None:
        raw = os.getenv("MONITOR_EXIT_CONFIRM_TICKS", "2")
    try:
        return max(1, int(float(raw)))
    except Exception:
        return 2


def _resolve_use_exit_policy(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    if state.get("use_exit_policy") is not None:
        return _is_trueish(state.get("use_exit_policy"))
    if isinstance(policy, dict) and policy.get("use_exit_policy") is not None:
        return _is_trueish(policy.get("use_exit_policy"))
    return _is_trueish(os.getenv("USE_EXIT_POLICY", "false"))


def _resolve_post_exit_cooldown_sec(state: Dict[str, Any], policy: Dict[str, Any], monitor_policy: Dict[str, Any]) -> int:
    raw = state.get("post_exit_cooldown_sec")
    if raw in (None, "") and isinstance(monitor_policy, dict):
        raw = monitor_policy.get("post_exit_cooldown_sec")
    if raw in (None, "") and isinstance(policy, dict):
        raw = policy.get("post_exit_cooldown_sec")
    if raw in (None, ""):
        raw = os.getenv("POST_EXIT_COOLDOWN_SEC", "0")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 0


def _resolve_block_buy_when_open_position(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
) -> bool:
    if state.get("monitor_block_buy_when_open_position") is not None:
        return _is_trueish(state.get("monitor_block_buy_when_open_position"))
    if isinstance(monitor_policy, dict) and monitor_policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(monitor_policy.get("block_buy_when_open_position"))
    if isinstance(policy, dict) and policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(policy.get("block_buy_when_open_position"))
    return _is_trueish(os.getenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false"))


def _resolve_exit_policy_config(policy: Dict[str, Any]) -> Dict[str, Any]:
    cfg = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else {}
    out = dict(cfg or {})

    # Backward-compatible flat policy aliases.
    alias_map = {
        "hard_stop_pct": "hard_stop_pct",
        "stop_loss_pct": "stop_loss_pct",
        "take_profit_pct": "take_profit_pct",
        "max_hold_sec": "max_hold_sec",
        "trailing_stop_pct": "trailing_stop_pct",
        "vol_expansion_ratio": "vol_expansion_ratio",
        "news_shock_threshold": "news_shock_threshold",
        "peak_drawdown_exit_pct": "peak_drawdown_exit_pct",
        "vwap_breakdown_pct": "vwap_breakdown_pct",
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
    vwap_breakdown_raw = str(os.getenv("EXIT_POLICY_VWAP_BREAKDOWN_PCT", "") or "").strip()
    intraday_low_break_raw = str(os.getenv("EXIT_POLICY_INTRADAY_LOW_BREAK_PCT", "") or "").strip()
    trend_strength_floor_raw = str(os.getenv("EXIT_POLICY_TREND_STRENGTH_FLOOR", "") or "").strip()
    eod_flat_raw = str(os.getenv("EXIT_POLICY_USE_EOD_FLAT", "") or "").strip()
    eod_cutoff_raw = str(os.getenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "") or "").strip()
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
    if eod_flat_raw:
        out["use_eod_flat"] = _is_trueish(eod_flat_raw)
    if eod_cutoff_raw:
        base = _to_float(out.get("eod_flat_cutoff_min"))
        if base <= 0.0:
            base = 10.0
        x = _to_float(eod_cutoff_raw)
        out["eod_flat_cutoff_min"] = int(x if x > 0.0 else base)
    if emergency_raw:
        out["emergency_halt"] = _is_trueish(emergency_raw)
    return out


def _extract_monitor_strategy_frame(state: Dict[str, Any]) -> Dict[str, str]:
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
    market_policy = (
        dict(strategy_policy.get("market_policy") or {})
        if isinstance(strategy_policy.get("market_policy"), dict)
        else {}
    )
    return {
        "playbook": str(
            state.get("playbook")
            or market_policy.get("playbook")
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
    }


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

    return {
        "min_hold_sec": max(0, int(min_hold)),
        "sell_cooldown_sec": max(0, int(cooldown)),
        "confirm_ticks": max(1, min(6, int(confirm))),
        "playbook": playbook,
        "monitor_guidance": mode,
        "risk_tone": tone,
        "trade_aggressiveness": aggr,
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
            "max_hold_sec",
            "time_stop_sec",
            "trailing_stop_pct",
            "vol_expansion_ratio",
            "news_shock_threshold",
            "peak_drawdown_exit_pct",
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

    if not strategist_exit_policy and not any((raw_playbook, raw_guidance, raw_tone, raw_aggr)):
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
        "peak_drawdown",
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


def _save_current_monitor_state(state: Dict[str, Any], symbol: str, *, posture: str, reason: str, active_exit_axis: str) -> None:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = persisted.get("monitor_last_state_by_symbol") if isinstance(persisted.get("monitor_last_state_by_symbol"), dict) else {}
    rows[_norm_symbol(symbol)] = {
        "posture": str(posture or ""),
        "reason": str(reason or ""),
        "active_exit_axis": str(active_exit_axis or ""),
        "updated_at_epoch": int(_resolve_now_epoch(state)),
    }
    persisted["monitor_last_state_by_symbol"] = rows
    state["persisted_state"] = persisted


def _resolve_cash(state: Dict[str, Any]) -> float:
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
    hold_sec = _to_int(position.get("hold_sec"))
    if hold_sec <= 0:
        hold_sec = _to_int(state.get("position_hold_sec"))
    if hold_sec <= 0:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
        last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
        if last_trade_side == "BUY" and last_trade_epoch > 0:
            now_epoch = _resolve_now_epoch(state)
            hold_sec = max(0, int(now_epoch - last_trade_epoch))

    exit_policy_map = dict(exit_policy_base or {})
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
    prior_bar_low = _to_float(selected_for_exit.get("_monitor_prior_bar_low"))
    if prior_bar_low > 0.0:
        exit_policy_map.setdefault("prior_bar_low", prior_bar_low)
    if state.get("policy") and isinstance(state.get("policy"), dict):
        policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
        if policy.get("exit_policy_baseline_volatility") is not None:
            exit_policy_map.setdefault("baseline_volatility", policy.get("exit_policy_baseline_volatility"))
    if state.get("emergency_halt") is not None:
        exit_policy_map.setdefault("emergency_halt", state.get("emergency_halt"))
    mctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    if mctx.get("minutes_to_close") is not None:
        exit_policy_map.setdefault("minutes_to_close", mctx.get("minutes_to_close"))

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
        "take_profit": 50,
        "hold": 10,
        "price_unavailable": 5,
        "no_position": 0,
    }
    return int(order.get(r, 1))


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
    out: Dict[str, Any] = {
        "evaluated": False,
        "approved": False,
        "action": "not_applicable",
        "reason": "",
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
    }
    if qty <= 0 or (not use_eod_flat) or minutes_to_close is None or minutes_to_close < 0.0 or minutes_to_close > float(cutoff_min):
        return out

    out["evaluated"] = True
    out["action"] = "flatten_before_close"

    no_eod_policy = dict(exit_policy_base or {})
    no_eod_policy["use_eod_flat"] = False
    no_eod_policy["minutes_to_close"] = float(minutes_to_close)
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
        blockers.append(f"underlying_exit_signal:{str(risk_decision.get('reason') or 'unknown')}")
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
    if sel and max(0, _to_int((pos_map.get(sel) or {}).get("qty"))) > 0:
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
    best_rank = (-1, -1, -1.0, -1)
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
        qty = max(0, _to_int(decision.get("_qty")))
        rank = (triggered, reason_priority, pnl_mag, qty)
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
    block_buy_open_position = _resolve_block_buy_when_open_position(state, policy, monitor_policy)
    post_exit_cooldown_sec = _resolve_post_exit_cooldown_sec(state, policy, monitor_policy)
    strategy_frame = _extract_monitor_strategy_frame(state)
    buy_blocked_open_position = False
    buy_blocked_post_exit_cooldown = False
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
    entry_symbol = _norm_symbol(selected.get("symbol")) if isinstance(selected, dict) and selected.get("symbol") else ""
    entry_cooldown_map = state.get("_monitor_entry_cooldown_until")
    if not isinstance(entry_cooldown_map, dict):
        entry_cooldown_map = {}
    now_epoch_for_entry = _resolve_now_epoch(state)
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
    if isinstance(selected, dict) and selected.get("symbol"):
        symbol = _norm_symbol(selected.get("symbol"))
        qty = 1
        use_position_sizing = _is_trueish(state.get("use_position_sizing")) or _is_trueish(policy.get("use_position_sizing"))
        if use_position_sizing:
            px = _resolve_price(state, symbol, selected)
            cash = _resolve_cash(state)
            sizing_risk_context = _build_sizing_risk_context(state, selected, symbol)
            sz = evaluate_position_size(
                price=px,
                cash=cash if cash > 0.0 else None,
                policy=policy.get("position_sizing") if isinstance(policy.get("position_sizing"), dict) else policy,
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
            }
        else:
            sizing_info = {
                "enabled": False,
                "evaluated": False,
                "qty": 1,
                "reason": "disabled",
                "price": None,
                "cash": None,
                "inputs": {},
            }

        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
        last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
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

        entry_policy = resolve_intraday_entry_policy(monitor_policy, frame=strategy_frame)
        state = _ensure_monitor_minute_ohlcv_for_symbol(
            state,
            symbol=symbol,
            timeframe_minutes=int(entry_policy.get("timeframe_minutes") or 1),
            now_epoch=now_epoch_for_entry,
        )
        entry_rows = []
        minute_ohlcv_by_symbol, minute_ohlcv_meta = extract_minute_ohlcv_by_symbol(state)
        entry_row_source = str((minute_ohlcv_meta or {}).get("source") or "")
        minute_fetch_meta = (
            dict(state.get("monitor_minute_ohlcv_fetch") or {})
            if isinstance(state.get("monitor_minute_ohlcv_fetch"), dict)
            else {}
        )
        if symbol and isinstance(minute_ohlcv_by_symbol.get(symbol), list):
            entry_rows = list(minute_ohlcv_by_symbol.get(symbol) or [])
        entry_info = evaluate_intraday_entry_signal(
            entry_rows,
            current_price=selected.get("price") if isinstance(selected, dict) else None,
            features=selected.get("features") if isinstance(selected, dict) and isinstance(selected.get("features"), dict) else {},
            policy=monitor_policy,
            frame=strategy_frame,
        )
        entry_info["symbol"] = symbol
        entry_info["selected_symbol"] = symbol
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
        entry_metrics["minute_refetch_produced_fresh_snapshot"] = bool(
            minute_fetch_meta.get("minute_refetch_produced_fresh_snapshot")
        )
        entry_info["metrics"] = entry_metrics
        entry_info["minute_source_meta"] = dict(minute_ohlcv_meta or {})
        entry_info["minute_fetch_meta"] = minute_fetch_meta
        entry_signal_detected = bool(entry_info.get("triggered"))
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

        if bool(block_buy_open_position) and open_position_count > 0:
            entry_guard_blocked = True
            entry_guard_reason = "buy_blocked_open_position"
            buy_blocked_open_position = True
        elif buy_blocked_post_exit_cooldown:
            entry_guard_blocked = True
            entry_guard_reason = "post_exit_cooldown"
        elif entry_intent_cooldown_sec > 0 and cooldown_until > now_epoch_for_entry:
            entry_guard_blocked = True
            entry_guard_reason = f"entry_guard_cooldown:{max(0, cooldown_until - now_epoch_for_entry)}s_remaining"

        entry_info["guard_blocked"] = bool(entry_guard_blocked)
        entry_info["guard_reason"] = str(entry_guard_reason)
        entry_info["legacy_fallback_used"] = False

        if not symbol:
            intents = []
        elif qty <= 0:
            intents = []
        elif entry_guard_blocked:
            intents = []
        elif not bool(entry_info.get("triggered")):
            intents = []
        else:
            intent = {
                "symbol": symbol,
                "side": "BUY",
                "qty": int(qty),
                "thesis": str(plan.get("thesis") or ""),
                "meta": {
                    "score": selected.get("score"),
                    "risk_score": selected.get("risk_score"),
                    "confidence": selected.get("confidence"),
                    "entry_signal_source": "monitor_intraday_entry",
                    "entry_pattern": str(entry_info.get("pattern") or ""),
                    "entry_reason": str(entry_info.get("reason") or ""),
                    "entry_signal_chain": list(entry_info.get("signal_chain") or []),
                    "entry_metrics": dict(entry_info.get("metrics") or {}),
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
            if entry_intent_cooldown_sec > 0:
                intent["meta"]["entry_intent_cooldown_sec"] = int(entry_intent_cooldown_sec)
            intents = [intent]
            entry_info["intent_submitted"] = True
            if entry_intent_cooldown_sec > 0:
                entry_cooldown_map[symbol] = int(now_epoch_for_entry + entry_intent_cooldown_sec)
                entry_info["intent_cooldown_until"] = int(now_epoch_for_entry + entry_intent_cooldown_sec)
        entry_info["decision"] = "BUY" if bool(entry_info.get("intent_submitted")) else "WAIT"
    if bool(intents) and block_buy_open_position and open_position_count > 0:
        intents = []
        buy_blocked_open_position = True
        entry_info["guard_blocked"] = True
        entry_info["guard_reason"] = "buy_blocked_open_position"
        entry_info["decision"] = "WAIT"
    state["_monitor_entry_cooldown_until"] = entry_cooldown_map

    # Optional M29-2 exit policy (default disabled for backward compatibility).
    use_exit_policy = _resolve_use_exit_policy(state, policy)
    exit_policy_base = _resolve_exit_policy_config(policy)
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
    if use_exit_policy and isinstance(selected, dict) and selected.get("symbol"):
        selected_symbol = _norm_symbol(selected.get("symbol"))
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
        exit_policy_harmonized = _harmonize_exit_policy_with_monitor_guards(
            exit_policy_base=exit_policy_base,
            min_hold_sec=min_hold_sec,
        )
        effective_exit_policy_base = dict(exit_policy_harmonized.get("policy") or {})
        exit_policy_guard_adjustments = list(exit_policy_harmonized.get("adjustments") or [])
        exit_policy_strategy = _apply_exit_policy_strategy_frame(
            state=state,
            exit_policy_base=effective_exit_policy_base,
            selected=selected,
            position=pos_map.get(selected_symbol, {}),
            frame=frame_applied,
        )
        effective_exit_policy_base = dict(exit_policy_strategy.get("policy") or effective_exit_policy_base)
        exit_policy_guard_adjustments.extend(list(exit_policy_strategy.get("adjustments") or []))
        symbol = _select_exit_symbol(
            selected_symbol,
            pos_map,
            state=state,
            selected=selected,
            policy=policy,
            exit_policy_base=effective_exit_policy_base,
        )
        selected_for_exit: Dict[str, Any] = selected
        if symbol and symbol != selected_symbol:
            selected_for_exit = {"symbol": symbol}
        features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
        pos = pos_map.get(symbol, {})
        qty = max(0, _to_int(pos.get("qty")))
        # When a position is already held for monitored symbol, suppress fresh BUY intents.
        if qty > 0:
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
        now_epoch = _resolve_now_epoch(state)
        if hold_sec <= 0:
            persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
            last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
            last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
            if last_trade_side == "BUY" and last_trade_epoch > 0:
                hold_sec = max(0, int(now_epoch - last_trade_epoch))
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
        monitor_reason = "hold"
        min_hold_blocked = False
        sell_cooldown_blocked = False
        exit_signal_detected = bool(decision.get("triggered"))
        emergency_exit = _is_emergency_exit_reason(str(decision.get("reason") or ""))
        hard_exit = _is_hard_exit_reason(str(decision.get("reason") or ""))

        if exit_signal_detected:
            if qty <= 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_no_position"
                monitor_reason = "no_position"
            elif _is_trueish(state.get("execution_pending")):
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_execution_pending"
                monitor_reason = "pending_exit_lock"
            elif int(features.get("skill_open_orders") or 0) > 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_open_order_pending"
                monitor_reason = "pending_exit_lock"
            elif lock_until > now_epoch:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_pending_exit_lock"
                monitor_reason = "pending_exit_lock"
            elif not emergency_exit and not hard_exit and min_hold_sec > 0 and hold_sec > 0 and hold_sec < min_hold_sec:
                sell_guard_blocked = True
                min_hold_blocked = True
                sell_guard_reason = f"sell_guard_min_hold:{hold_sec}s<{min_hold_sec}s"
                monitor_reason = "min_hold_active"
            elif not emergency_exit and not hard_exit and sell_cooldown_sec > 0 and cooldown_until > now_epoch:
                sell_guard_blocked = True
                sell_cooldown_blocked = True
                sell_guard_reason = f"sell_guard_cooldown:{max(0, cooldown_until - now_epoch)}s_remaining"
                monitor_reason = "cooldown_active"
            elif not emergency_exit and not hard_exit and confirm_ticks > 1:
                confirm_count = _to_int(confirm_map.get(confirm_key)) + 1
                confirm_map[confirm_key] = int(confirm_count)
                if confirm_count < int(confirm_ticks):
                    sell_guard_blocked = True
                    sell_guard_reason = f"exit_confirmation_pending:{confirm_count}/{confirm_ticks}"
                    monitor_reason = "exit_signal_pending_confirmation"
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
            "price": price,
            "avg_price": avg_price if avg_price > 0.0 else None,
            "peak_price": decision.get("_peak_price"),
            "thresholds": decision.get("thresholds") if isinstance(decision.get("thresholds"), dict) else {},
            "effective_exit_policy": dict(effective_exit_policy_base),
            "hold_sec": hold_sec if hold_sec > 0 else None,
            "trailing_drawdown": decision.get("trailing_drawdown"),
            "peak_drawdown": decision.get("peak_drawdown"),
            "vwap_distance": decision.get("vwap_distance"),
            "volatility_ratio": decision.get("volatility_ratio"),
            "volatility_regime": str(features.get("engine_regime") or ""),
            "price_source": str(decision.get("_price_source") or ""),
            "price_source_policy": "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized",
            "feature_source": str(decision.get("_feature_source") or ""),
            "minutes_to_close": decision.get("minutes_to_close"),
            "min_hold_sec": int(min_hold_sec),
            "sell_cooldown_sec": int(sell_cooldown_sec),
            "exit_confirm_ticks": int(confirm_ticks),
            "exit_confirm_count": int(confirm_count),
            "sell_guard_blocked": bool(sell_guard_blocked),
            "sell_guard_reason": str(sell_guard_reason),
            "position_age_seconds": hold_sec if hold_sec > 0 else None,
            "exit_signal_detected": bool(exit_signal_detected),
            "min_hold_blocked": bool(min_hold_blocked),
            "sell_cooldown_blocked": bool(sell_cooldown_blocked),
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
            "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
            "exit_policy_guard_adjustments": list(exit_policy_guard_adjustments),
            "active_exit_axis": _friendly_exit_axis(str(decision.get("reason") or monitor_reason or "hold")),
            "watch_axes": _monitor_watch_axes(decision.get("thresholds") if isinstance(decision.get("thresholds"), dict) else {}),
            "eod_carry_evaluated": bool(eod_carry.get("evaluated")),
            "eod_carry_approved": bool(eod_carry.get("approved")),
            "eod_carry_action": str(eod_carry.get("action") or ""),
            "eod_carry_reason": str(eod_carry.get("reason") or ""),
            "eod_carry_positive_signals": list(eod_carry.get("positive_signals") or []),
            "eod_carry_blockers": list(eod_carry.get("blockers") or []),
            "eod_carry_non_eod_reason": str(eod_carry.get("non_eod_reason") or ""),
            "eod_carry_non_eod_triggered": bool(eod_carry.get("non_eod_triggered")),
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
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            "entry_intent_submitted": bool(entry_info.get("intent_submitted")),
            "entry_legacy_fallback_used": bool(entry_info.get("legacy_fallback_used")),
            "entry_intent_cooldown_sec": int(entry_info.get("intent_cooldown_sec") or 0),
            "entry_intent_cooldown_until": entry_info.get("intent_cooldown_until"),
        }
        if bool(exit_signal_detected) and not bool(sell_guard_blocked) and qty > 0:
            intents = [
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": int(qty),
                    "thesis": str(plan.get("thesis") or ""),
                    "meta": {
                        "exit_reason": str(decision.get("reason") or ""),
                        "pnl_ratio": decision.get("pnl_ratio"),
                        "avg_price": avg_price if avg_price > 0.0 else None,
                        "price": price,
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
                        "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
                        "exit_policy_guard_adjustments": list(exit_policy_guard_adjustments),
                    },
                }
            ]

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
        "exit_pnl_ratio": exit_info.get("pnl_ratio"),
        "exit_symbol": exit_info.get("symbol"),
        "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
        "exit_qty": int(exit_info.get("qty") or 0),
        "exit_position_age_seconds": exit_info.get("position_age_seconds"),
        "exit_min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
        "exit_sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
        "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
        "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "exit_min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
        "exit_sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
        "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
        "eod_carry_evaluated": bool(exit_info.get("eod_carry_evaluated")),
        "eod_carry_approved": bool(exit_info.get("eod_carry_approved")),
        "eod_carry_action": str(exit_info.get("eod_carry_action") or ""),
        "eod_carry_reason": str(exit_info.get("eod_carry_reason") or ""),
        "position_sizing_enabled": bool(sizing_info.get("enabled")),
        "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
        "position_sizing_qty": int(sizing_info.get("qty") or 0),
        "position_sizing_reason": str(sizing_info.get("reason") or ""),
        "open_position_count": int(open_position_count),
        "block_buy_when_open_position": bool(block_buy_open_position),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
        "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
        "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
        "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
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
        "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
        "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        "entry_intent_submitted": bool(entry_info.get("intent_submitted")),
        "entry_legacy_fallback_used": bool(entry_info.get("legacy_fallback_used")),
        "entry_intent_cooldown_sec": int(entry_info.get("intent_cooldown_sec") or 0),
        "entry_intent_cooldown_until": entry_info.get("intent_cooldown_until"),
    }
    state["monitor_output"] = {
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "intent_side": (str(intents[0].get("side")) if intents else "NOOP"),
        "intent_qty": (int(intents[0].get("qty") or 0) if intents else 0),
        "entry_exit_reason": (
            str(exit_info.get("reason") or "")
            if bool(exit_info.get("enabled")) and bool(exit_info.get("exit_signal_detected"))
            else (
                "post_exit_cooldown"
                if bool(buy_blocked_post_exit_cooldown)
                else (
                "buy_blocked_open_position"
                if bool(buy_blocked_open_position)
                else (
                    str(entry_info.get("guard_reason") or "")
                    if bool(entry_info.get("guard_blocked"))
                    else (
                        str(entry_info.get("reason") or "entry_wait")
                    )
                )
                )
            )
        ),
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
    state_changed = bool(previous_posture != current_posture or previous_reason != current_reason)
    if monitor_symbol:
        _save_current_monitor_state(
            state,
            monitor_symbol,
            posture=current_posture,
            reason=current_reason,
            active_exit_axis=str(exit_info.get("active_exit_axis") or ""),
        )

    thresholds = dict(exit_info.get("thresholds") or {}) if isinstance(exit_info.get("thresholds"), dict) else {}
    entry_metrics = dict(entry_info.get("metrics") or {}) if isinstance(entry_info.get("metrics"), dict) else {}
    entry_thresholds = dict(entry_info.get("thresholds") or {}) if isinstance(entry_info.get("thresholds"), dict) else {}
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
        "vwap_distance_pct": exit_info.get("vwap_distance"),
        "volatility_regime": str(exit_info.get("volatility_regime") or ""),
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "watch_axes": list(exit_info.get("watch_axes") or []),
        "exit_confirm_required": int(exit_info.get("exit_confirm_ticks") or 0),
        "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
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
        "entry_volume_ratio_min": entry_thresholds.get("volume_ratio_min"),
        "entry_max_extended_from_vwap_pct": entry_thresholds.get("max_extended_from_vwap_pct"),
        "entry_min_extended_from_vwap_pct": entry_thresholds.get("min_extended_from_vwap_pct"),
        "entry_pullback_min_pct": entry_thresholds.get("pullback_min_pct"),
        "entry_pullback_max_pct": entry_thresholds.get("pullback_max_pct"),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
    }
    state["monitor_posture"] = current_posture
    state["monitor_threshold_snapshot"] = dict(threshold_snapshot)
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
    entry_decision_detail = {
        "decision": "BUY" if bool(buy_submitted) else "WAIT",
        "reason": str(entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait"),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_reason": str(entry_info.get("reason") or ""),
        "signal_chain": list(entry_info.get("signal_chain") or []),
        "guard_blocked": bool(entry_info.get("guard_blocked")),
        "guard_reason": str(entry_info.get("guard_reason") or ""),
        "buy_submitted": bool(buy_submitted),
        "buy_skipped_reason": buy_skipped_reason,
        "metrics": entry_event_metrics,
        "thresholds": dict(entry_info.get("thresholds") or {}),
        "passed_checks": list(entry_info.get("passed_checks") or []),
        "failed_checks": list(entry_info.get("failed_checks") or []),
        "primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "threshold_margins": dict(entry_info.get("threshold_margins") or {}),
    }
    state["monitor_entry_decision_detail"] = dict(entry_decision_detail)
    _emit_monitor_event(
        state,
        name="entry_decision_detail",
        payload=entry_decision_detail,
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
        "confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "confirm_required": int(exit_info.get("exit_confirm_ticks") or 0),
        "guard_blocked": bool(exit_info.get("sell_guard_blocked")),
        "guard_reason": str(exit_info.get("sell_guard_reason") or ""),
        "sell_submitted": bool(sell_submitted),
        "sell_skipped_reason": sell_skipped_reason,
        "final_reason": current_reason,
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
    state["monitor_evaluation"] = {
        "triggered_rules": list(triggered_rules),
        "blocked_rules": list(dict.fromkeys(blocked_rules))[:8],
        "posture": current_posture,
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
    }
    state["monitor_action_decision"] = {
        "decision": str((state.get("monitor_output") or {}).get("intent_side") or "NOOP"),
        "action_reason_human": str((state.get("monitor_output") or {}).get("entry_exit_reason") or current_reason),
        "decision_reason_chain": list(reason_chain),
        "confidence": float(_to_float(entry_info.get("confidence"))),
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "triggered_rules": list(triggered_rules),
        "blocked_rules": list(dict.fromkeys(blocked_rules))[:8],
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
            "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
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
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
            "position_sizing_enabled": bool(sizing_info.get("enabled")),
            "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
            "position_sizing_qty": int(sizing_info.get("qty") or 0),
            "position_sizing_reason": str(sizing_info.get("reason") or ""),
            "open_position_count": int(open_position_count),
            "block_buy_when_open_position": bool(block_buy_open_position),
            "buy_blocked_open_position": bool(buy_blocked_open_position),
            "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
            "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
            "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_reason": str(entry_info.get("reason") or ""),
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
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
            "strategy_frame_adjustments": list(exit_info.get("strategy_frame_adjustments") or []),
            "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_signal_chain": list(entry_info.get("signal_chain") or []),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
            "entry_passed_checks": list(entry_info.get("passed_checks") or []),
            "entry_failed_checks": list(entry_info.get("failed_checks") or []),
            "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
            "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
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
                "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
                "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
                "entry_evaluated": bool(entry_info.get("evaluated")),
                "entry_triggered": bool(entry_info.get("triggered")),
                "entry_pattern": str(entry_info.get("pattern") or ""),
                "entry_reason": str(entry_info.get("reason") or ""),
                "entry_signal_chain": list(entry_info.get("signal_chain") or []),
                "entry_metrics": dict(entry_info.get("metrics") or {}),
                "entry_thresholds": dict(entry_info.get("thresholds") or {}),
                "entry_passed_checks": list(entry_info.get("passed_checks") or []),
                "entry_failed_checks": list(entry_info.get("failed_checks") or []),
                "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
                "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
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
