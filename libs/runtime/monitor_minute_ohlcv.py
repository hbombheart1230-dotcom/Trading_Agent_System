from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from libs.core.symbols import normalize_symbol


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
    sym = normalize_symbol(symbol)
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
        if normalize_symbol(row.get("symbol")) != sym:
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
    sym = normalize_symbol(symbol)
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
    sym = normalize_symbol(symbol)
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
    sym = normalize_symbol(symbol)
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

