from __future__ import annotations

"""Canonical Scanner node for integrated runtime.

Role boundary:
- builds/reduces/ranks candidate pool (Kiwoom-first, strategist-guided)
- selects final Top-1 candidate for monitor stage within strategist frame
- does not create execution calls
"""

import os
import time
from collections import Counter
from functools import partial
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    account_order_is_pending,
    extract_account_orders_rows,
    extract_market_quotes,
    extract_minute_ohlcv_by_symbol,
    norm_symbol,
)
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input
from libs.runtime.asset_universe_policy import apply_asset_universe_filter
from libs.runtime.canonical_artifacts import write_scanner_artifact
from libs.runtime.commander_memory_application_trace import build_scanner_commander_memory_application_trace
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.etf_deviation import extract_etf_deviation_signal
from libs.runtime.scanner_bias import normalize_scanner_bias_context, summarize_scanner_bias_context
from libs.runtime.scanner_memory_bias import (
    compute_scanner_memory_bias_adjustment,
    summarize_scanner_memory_bias,
)
from libs.runtime.scanner.candidate_selection import (
    build_kiwoom_candidates as _build_kiwoom_candidates_base,
    extract_strategist_candidates as _extract_strategist_candidates,
    normalize_scanner_source_policy as _normalize_scanner_source_policy,
    resolve_block_static_fallback as _resolve_block_static_fallback,
    resolve_candidate_limit as _resolve_candidate_limit,
    resolve_candidate_source as _resolve_candidate_source,
    resolve_condition_limit as _resolve_condition_limit,
    resolve_enable_theme_filter as _resolve_enable_theme_filter,
    resolve_include_change_rate as _resolve_include_change_rate,
    resolve_scan_aggressiveness as _resolve_scan_aggressiveness,
    resolve_scanner_candidates as _resolve_scanner_candidates_base,
    resolve_strict_kiwoom_only as _resolve_strict_kiwoom_only,
    resolve_top_candidate_pool as _resolve_top_candidate_pool,
)
from libs.runtime.scanner.theme_filter import (
    apply_avoid_theme_filter as _apply_avoid_theme_filter,
    apply_theme_filter as _apply_theme_filter,
    candidate_theme_match as _candidate_theme_match,
    extract_avoid_themes as _extract_avoid_themes,
    extract_selected_themes as _extract_selected_themes,
    extract_theme_symbol_index as _extract_theme_symbol_index,
    extract_themes as _extract_themes,
)
from libs.runtime.scanner.market_representative_guard import (
    apply_market_representative_guard as _apply_market_representative_guard,
    default_market_representative_guard_policy as _default_market_representative_guard_policy,
    market_representative_confirmation_sources as _market_representative_confirmation_sources,
    market_representative_top_value_dominance as _market_representative_top_value_dominance,
    resolve_market_representative_guard_policy as _resolve_market_representative_guard_policy,
)
from libs.runtime.scanner.practical_filters import (
    candidate_quote_metrics as _candidate_quote_metrics,
    filter_mock_broker_restricted_candidates as _filter_mock_broker_restricted_candidates,
    reduce_candidates_by_practical_filters as _reduce_candidates_by_practical_filters,
    resolve_exclude_halted as _resolve_exclude_halted,
    resolve_min_trading_value as _resolve_min_trading_value,
    resolve_min_volume as _resolve_min_volume,
)
from libs.runtime.scanner.output_snapshots import (
    compact_feature_snapshot as _compact_feature_snapshot,
    compact_selected_snapshot as _compact_selected_snapshot,
    feature_coverage_summary as _feature_coverage_summary,
    ranking_table_rows as _ranking_table_rows,
)
from libs.runtime.scanner.output_payloads import (
    build_candidate_ranking_table_payload as _build_candidate_ranking_table_payload,
    build_candidate_selection_reason_payload as _build_candidate_selection_reason_payload,
)
from libs.runtime.quant.suitability import score_candidate_tactic_suitability
from libs.runtime.intraday_monitor_signals import evaluate_intraday_entry_signal, resolve_intraday_entry_policy
from libs.runtime.feature_engine import build_feature_map
from libs.runtime.scanner_feature_hydration import hydrate_scanner_feature_map
from libs.runtime.scanner_policy import resolve_scanner_runtime_policy
from libs.strategies.contracts import coerce_strategist_output
from libs.reporting.symbol_read_model import build_symbol_read_model


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _norm_symbol(v: Any) -> str:
    return norm_symbol(v)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


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


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _resolve_scanner_repeat_guard_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    raw_policy = policy.get("scanner_repeat_guard") if isinstance(policy.get("scanner_repeat_guard"), dict) else {}
    lookback_sec = _to_int(
        raw_policy.get("lookback_sec", os.getenv("SCANNER_REPEAT_LOOKBACK_SEC", "1800")),
        1800,
    )
    per_hit_penalty = _to_float(
        raw_policy.get("per_hit_penalty", os.getenv("SCANNER_REPEAT_SYMBOL_PENALTY", "0.06"))
    )
    recent_trade_penalty = _to_float(
        raw_policy.get("recent_trade_penalty", os.getenv("SCANNER_RECENT_TRADE_SYMBOL_PENALTY", "0.10"))
    )
    trade_lookback_sec = _to_int(
        raw_policy.get("trade_lookback_sec", os.getenv("SCANNER_RECENT_TRADE_LOOKBACK_SEC", "5400")),
        5400,
    )
    max_penalty = _to_float(
        raw_policy.get("max_penalty", os.getenv("SCANNER_REPEAT_SYMBOL_MAX_PENALTY", "0.40"))
    )
    streak_threshold = _to_int(
        raw_policy.get("streak_threshold", os.getenv("SCANNER_REPEAT_STREAK_THRESHOLD", "3")),
        3,
    )
    streak_penalty = _to_float(
        raw_policy.get("streak_penalty", os.getenv("SCANNER_REPEAT_STREAK_PENALTY", "0.12"))
    )
    history_limit = _to_int(
        raw_policy.get("history_limit", os.getenv("SCANNER_REPEAT_HISTORY_LIMIT", "40")),
        40,
    )
    blocker_lookback_sec = _to_int(
        raw_policy.get("blocker_lookback_sec", os.getenv("SCANNER_REPEAT_BLOCK_LOOKBACK_SEC", "900")),
        900,
    )
    blocker_per_hit_penalty = _to_float(
        raw_policy.get("blocker_per_hit_penalty", os.getenv("SCANNER_REPEAT_BLOCK_PENALTY", "0.08"))
    )
    blocker_max_penalty = _to_float(
        raw_policy.get("blocker_max_penalty", os.getenv("SCANNER_REPEAT_BLOCK_MAX_PENALTY", "0.18"))
    )
    return {
        "lookback_sec": max(0, int(lookback_sec)),
        "per_hit_penalty": max(0.0, float(per_hit_penalty)),
        "recent_trade_penalty": max(0.0, float(recent_trade_penalty)),
        "trade_lookback_sec": max(0, int(trade_lookback_sec)),
        "max_penalty": max(0.0, float(max_penalty)),
        "streak_threshold": max(2, int(streak_threshold)),
        "streak_penalty": max(0.0, float(streak_penalty)),
        "history_limit": max(5, int(history_limit)),
        "blocker_lookback_sec": max(0, int(blocker_lookback_sec)),
        "blocker_per_hit_penalty": max(0.0, float(blocker_per_hit_penalty)),
        "blocker_max_penalty": max(0.0, float(blocker_max_penalty)),
    }


def _resolve_reports_root(state: Dict[str, Any]) -> Path:
    raw = str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports"
    return Path(raw)


def _load_symbol_priors(state: Dict[str, Any], candidates: List[Any]) -> Dict[str, Dict[str, Any]]:
    reports_root = _resolve_reports_root(state)
    trades_root = reports_root / "trades"
    out: Dict[str, Dict[str, Any]] = {}
    if not trades_root.exists():
        return out
    for item in list(candidates or [])[:40]:
        symbol = _norm_symbol(item.get("symbol")) if isinstance(item, dict) else _norm_symbol(item)
        if not symbol or symbol in out:
            continue
        try:
            model = build_symbol_read_model(str(trades_root), symbol, persisted_only=True)
        except Exception:
            model = {}
        if isinstance(model, dict) and model:
            out[symbol] = model
    return out


def _compute_symbol_prior_adjustment(
    *,
    symbol_model: Dict[str, Any],
    playbook: str,
    current_day: str = "",
) -> Dict[str, Any]:
    if not isinstance(symbol_model, dict) or not symbol_model:
        return {
            "adjustment": 0.0,
            "risk_delta": 0.0,
            "confidence_delta": 0.0,
            "reasons": [],
            "summary": {},
        }

    adjustment = 0.0
    risk_delta = 0.0
    confidence_delta = 0.0
    reasons: List[str] = []
    playbook_norm = str(playbook or "").strip().lower()

    if str(symbol_model.get("data_quality", {}).get("data_source") or "").strip() == "symbol_memory":
        reasons.append("symbol_memory")

    avg_pnl_pct = _to_float(symbol_model.get("avg_pnl_pct"))
    win_rate = _to_float(symbol_model.get("win_rate"))
    loss_count = _to_int(symbol_model.get("loss_count"), 0)
    closed_trade_count = _to_int(symbol_model.get("closed_trade_count"), 0)
    last_trade_date = str(symbol_model.get("last_trade_date") or "").strip()
    dominant_playbook = str(symbol_model.get("dominant_playbook") or "").strip().lower()
    dominant_blocker = str(symbol_model.get("dominant_monitor_blocker") or "").strip()
    repeated_failures = list(symbol_model.get("repeated_failure_pattern") or [])
    same_day_model = bool(str(current_day or "").strip() and last_trade_date == str(current_day or "").strip())

    if avg_pnl_pct < 0:
        adjustment -= 0.08
        risk_delta += 0.08
        confidence_delta -= 0.06
        reasons.append(f"negative_avg_pnl_pct:{avg_pnl_pct:.2f}")
    elif avg_pnl_pct > 0:
        adjustment += 0.04
        confidence_delta += 0.03
        reasons.append(f"positive_avg_pnl_pct:{avg_pnl_pct:.2f}")

    if win_rate > 0.0 and win_rate < 0.4:
        adjustment -= 0.05
        risk_delta += 0.05
        confidence_delta -= 0.04
        reasons.append(f"low_win_rate:{win_rate:.2f}")
    elif win_rate >= 0.6:
        adjustment += 0.03
        confidence_delta += 0.02
        reasons.append(f"strong_win_rate:{win_rate:.2f}")

    if playbook_norm and dominant_playbook and dominant_playbook != "unknown":
        if playbook_norm == dominant_playbook:
            adjustment += 0.03
            reasons.append(f"playbook_fit:{dominant_playbook}")
        else:
            adjustment -= 0.04
            risk_delta += 0.03
            reasons.append(f"playbook_mismatch:{dominant_playbook}")

    if dominant_blocker and dominant_blocker.lower() != "unknown":
        risk_delta += 0.03
        reasons.append(f"dominant_blocker:{dominant_blocker}")

    if repeated_failures:
        first = repeated_failures[0] if isinstance(repeated_failures[0], dict) else {}
        failure_type = str(first.get("type") or "").strip()
        failure_value = str(first.get("value") or "").strip()
        if failure_value:
            reasons.append(f"repeated_failure:{failure_type}:{failure_value}")

    if same_day_model and closed_trade_count >= 2 and (loss_count >= 2 or avg_pnl_pct < -0.10):
        adjustment -= 0.25
        risk_delta += 0.18
        confidence_delta -= 0.12
        reasons.append(f"same_day_repeat_loss:{loss_count}/{closed_trade_count}")
    if same_day_model and closed_trade_count >= 3 and (loss_count >= 3 or avg_pnl_pct < -0.15):
        adjustment -= 0.20
        risk_delta += 0.12
        confidence_delta -= 0.08
        reasons.append("same_day_trade_lockout_bias")

    adjustment = _clamp(adjustment, -0.60, 0.10)
    risk_delta = _clamp(risk_delta, 0.0, 0.35)
    confidence_delta = _clamp(confidence_delta, -0.30, 0.05)
    return {
        "adjustment": float(adjustment),
        "risk_delta": float(risk_delta),
        "confidence_delta": float(confidence_delta),
        "reasons": reasons[:6],
        "summary": {
            "dominant_playbook": str(symbol_model.get("dominant_playbook") or ""),
            "dominant_monitor_blocker": str(symbol_model.get("dominant_monitor_blocker") or ""),
            "avg_pnl_pct": float(avg_pnl_pct),
            "win_rate": float(win_rate),
            "last_trade_date": str(last_trade_date),
            "same_day_model": bool(same_day_model),
            "closed_trade_count": int(closed_trade_count),
            "loss_count": int(loss_count),
        },
    }


def _scanner_recent_selection_history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = persisted.get("recent_scanner_selected")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = _norm_symbol(row.get("symbol"))
        epoch = _to_int(row.get("epoch"), 0)
        if sym and epoch > 0:
            out.append({"symbol": sym, "epoch": epoch})
    return out


def _scanner_recent_block_history(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = persisted.get("recent_monitor_blocks")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = _norm_symbol(row.get("symbol"))
        reason = str(row.get("reason") or "").strip()
        epoch = _to_int(row.get("epoch"), 0)
        if sym and reason and epoch > 0:
            out.append({"symbol": sym, "reason": reason, "epoch": epoch})
    return out


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    for key in ("now_epoch", "ts_epoch", "epoch"):
        value = _to_int(state.get(key), 0)
        if value > 0:
            return value
    return int(time.time())


def _repeat_symbol_penalty(
    state: Dict[str, Any],
    *,
    symbol: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    cfg = _resolve_scanner_repeat_guard_policy(policy)
    now_epoch = _resolve_now_epoch(state)
    history = _scanner_recent_selection_history(state)
    sel = _norm_symbol(symbol)
    repeat_count = 0
    streak_count = 0
    if cfg["lookback_sec"] > 0 and sel:
        cutoff = max(0, now_epoch - cfg["lookback_sec"])
        for row in history:
            if row.get("symbol") == sel and _to_int(row.get("epoch"), 0) >= cutoff:
                repeat_count += 1
        for row in reversed(history):
            if _to_int(row.get("epoch"), 0) < cutoff:
                break
            if row.get("symbol") != sel:
                break
            streak_count += 1

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    last_trade_symbol = _norm_symbol(persisted.get("last_trade_symbol"))
    last_trade_epoch = _to_int(persisted.get("last_trade_epoch"), 0)
    recent_trade_same_symbol = False
    if (
        sel
        and last_trade_symbol == sel
        and last_trade_epoch > 0
        and cfg["trade_lookback_sec"] > 0
        and (now_epoch - last_trade_epoch) <= cfg["trade_lookback_sec"]
    ):
        recent_trade_same_symbol = True

    streak_extra = cfg["streak_penalty"] if streak_count >= cfg["streak_threshold"] else 0.0
    penalty = min(
        cfg["max_penalty"],
        (repeat_count * cfg["per_hit_penalty"])
        + streak_extra
        + (cfg["recent_trade_penalty"] if recent_trade_same_symbol else 0.0),
    )
    return {
        "penalty": float(max(0.0, penalty)),
        "repeat_count": int(repeat_count),
        "streak_count": int(streak_count),
        "recent_trade_same_symbol": bool(recent_trade_same_symbol),
        "now_epoch": int(now_epoch),
        "history_count": int(len(history)),
        "config": cfg,
    }


def _repeat_blocker_cooldown_penalty(
    state: Dict[str, Any],
    *,
    symbol: str,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    cfg = _resolve_scanner_repeat_guard_policy(policy)
    now_epoch = _resolve_now_epoch(state)
    sel = _norm_symbol(symbol)
    if not sel or cfg["blocker_lookback_sec"] <= 0:
        return {
            "penalty": 0.0,
            "reason": "",
            "repeat_count": 0,
            "config": cfg,
        }

    cutoff = max(0, now_epoch - cfg["blocker_lookback_sec"])
    history = _scanner_recent_block_history(state)
    reason_counter: Dict[str, int] = {}
    for row in history:
        if row.get("symbol") != sel:
            continue
        if _to_int(row.get("epoch"), 0) < cutoff:
            continue
        reason = str(row.get("reason") or "").strip()
        if not reason:
            continue
        reason_counter[reason] = int(reason_counter.get(reason, 0)) + 1

    if not reason_counter:
        return {
            "penalty": 0.0,
            "reason": "",
            "repeat_count": 0,
            "config": cfg,
        }

    dominant_reason, repeat_count = max(reason_counter.items(), key=lambda item: item[1])
    weight = 0.0
    if dominant_reason == "too_extended_from_vwap":
        weight = 1.0
    elif dominant_reason in {"volume_insufficient", "volume_confirmation_missing"}:
        weight = 0.5
    elif dominant_reason in {"breakout_not_ready", "below_vwap_reclaim_not_ready", "pullback_below_vwap_reclaim_not_ready"}:
        weight = 0.35

    penalty = min(
        cfg["blocker_max_penalty"],
        float(repeat_count) * cfg["blocker_per_hit_penalty"] * float(weight),
    )
    return {
        "penalty": float(max(0.0, penalty)),
        "reason": str(dominant_reason),
        "repeat_count": int(repeat_count),
        "config": cfg,
    }


def _remember_selected_symbol(state: Dict[str, Any], selected_symbol: str, *, now_epoch: int, policy: Dict[str, Any]) -> None:
    symbol = _norm_symbol(selected_symbol)
    if not symbol:
        return
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    state["persisted_state"] = persisted
    cfg = _resolve_scanner_repeat_guard_policy(policy)
    history = _scanner_recent_selection_history(state)
    history.append({"symbol": symbol, "epoch": int(now_epoch)})
    if cfg["lookback_sec"] > 0:
        cutoff = max(0, int(now_epoch) - int(cfg["lookback_sec"]) * 2)
        history = [row for row in history if _to_int(row.get("epoch"), 0) >= cutoff]
    if len(history) > cfg["history_limit"]:
        history = history[-cfg["history_limit"] :]
    persisted["recent_scanner_selected"] = history


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _emit_scanner_event(
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
            stage="scanner",
            event=name,
            event_name=f"scanner.{name}",
            payload=dict(payload or {}),
            level=level,
            agent="scanner",
            symbol=str(symbol or ""),
        )
    except Exception:
        return


def _candidate_visibility_limit(policy: Dict[str, Any]) -> int:
    entry_control = policy.get("entry_control") if isinstance(policy.get("entry_control"), dict) else {}
    raw = entry_control.get("max_priority_rank") or policy.get("max_priority_rank") or 10
    value = int(_to_float(raw) or 10)
    return int(min(10, max(1, value)))


def _log_scanner_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "scanner-node")
        logger.log(run_id=run_id, stage="scanner", event="summary", payload=dict(payload))
    except Exception:
        return


def _extract_skill_quotes(state: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    return extract_market_quotes(state)


def _extract_account_open_order_counts(state: Dict[str, Any]) -> Tuple[Dict[str, int], int, Dict[str, Any]]:
    rows, meta = extract_account_orders_rows(state)

    out: Dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        if not account_order_is_pending(r):
            continue
        symbol = _norm_symbol(r.get("symbol") or r.get("stk_cd") or r.get("code"))
        if not symbol:
            continue
        out[symbol] = int(out.get(symbol, 0)) + 1
    return out, len(rows), meta


def _is_live_equity_symbol(symbol: str) -> bool:
    sym = _norm_symbol(symbol)
    return bool(sym) and sym.isdigit() and len(sym) == 6


def _enforce_live_equity_symbols(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    for raw in (
        policy.get("enforce_live_equity_symbols") if isinstance(policy, dict) else None,
        state.get("enforce_live_equity_symbols") if isinstance(state, dict) else None,
        os.getenv("SCANNER_ENFORCE_LIVE_EQUITY_SYMBOLS", ""),
    ):
        if raw not in (None, ""):
            return _is_trueish(raw)
    return not bool(os.getenv("PYTEST_CURRENT_TEST"))


def _filter_live_equity_candidates(candidates: List[Any]) -> Tuple[List[Any], Dict[str, Any]]:
    kept: List[Any] = []
    excluded: List[str] = []
    for item in list(candidates or []):
        raw_symbol = item.get("symbol") if isinstance(item, dict) else item
        symbol = _norm_symbol(raw_symbol)
        if not _is_live_equity_symbol(symbol):
            if symbol:
                excluded.append(symbol)
            continue
        if isinstance(item, dict):
            row = dict(item)
            row["symbol"] = symbol
            kept.append(row)
        else:
            kept.append(symbol)
    return kept, {
        "live_equity_symbol_filter_enabled": True,
        "live_equity_symbol_excluded_count": int(len(excluded)),
        "live_equity_symbol_excluded_symbols": excluded[:20],
        "candidate_pool_after_live_equity_symbol_filter": int(len(kept)),
    }


def _should_auto_hydrate_scanner_skills(state: Dict[str, Any], candidates: List[Any]) -> bool:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    explicit = policy.get("enable_scanner_skill_hydration")
    if explicit is not None:
        enabled = _is_trueish(explicit)
    else:
        env_value = os.getenv("SCANNER_AUTO_SKILL_HYDRATION", "")
        if env_value:
            enabled = _is_trueish(env_value)
        else:
            enabled = not bool(os.getenv("PYTEST_CURRENT_TEST"))
    if not enabled:
        return False

    if state.get("skill_runner") is not None or callable(state.get("skill_runner_factory")):
        return True
    if _is_trueish(state.get("auto_skill_runner")) or _is_trueish(os.getenv("M22_AUTO_SKILL_RUNNER", "")):
        return True

    candidate_symbols: List[str] = []
    for item in candidates:
        if isinstance(item, dict):
            sym = _norm_symbol(item.get("symbol"))
        else:
            sym = _norm_symbol(item)
        if sym:
            candidate_symbols.append(sym)
    return any(_is_live_equity_symbol(sym) for sym in candidate_symbols)


def _maybe_hydrate_scanner_skill_results(state: Dict[str, Any], candidates: List[Any]) -> Dict[str, Any]:
    existing_quotes, _quote_meta = _extract_skill_quotes(state)
    existing_order_counts, existing_order_rows, _order_meta = _extract_account_open_order_counts(state)
    if existing_quotes or existing_order_counts or existing_order_rows > 0:
        return state
    if not _should_auto_hydrate_scanner_skills(state, candidates):
        return state

    try:
        from graphs.nodes.hydrate_skill_results_node import hydrate_skill_results_node
    except Exception:
        return state

    injected_auto = False
    previous_auto = state.get("auto_skill_runner")
    had_candidates_key = "candidates" in state
    previous_candidates = state.get("candidates")
    if (
        state.get("skill_runner") is None
        and not callable(state.get("skill_runner_factory"))
        and not _is_trueish(state.get("auto_skill_runner"))
    ):
        state["auto_skill_runner"] = True
        injected_auto = True
    # The hydration node resolves market.quote fan-out from `state["candidates"]`.
    # Scanner often works from a locally built Kiwoom candidate pool, so expose that
    # pool during hydration instead of silently hydrating an empty symbol list.
    state["candidates"] = list(candidates or [])
    try:
        return hydrate_skill_results_node(state)
    except Exception:
        return state
    finally:
        if had_candidates_key:
            state["candidates"] = previous_candidates
        else:
            state.pop("candidates", None)
        if injected_auto:
            if previous_auto is None:
                state.pop("auto_skill_runner", None)
            else:
                state["auto_skill_runner"] = previous_auto


def _get_global_sentiment_score(state: Dict[str, Any]) -> float:
    """Return global sentiment score in [-1, +1].

    Priority:
      1) state['global_sentiment_signal']['score'] (normalized signal)
      2) state['mock_global_sentiment'] (tests)
      3) state['global_sentiment']['score'] (precomputed)
      4) state['policy']['global_sentiment']['score'] (set by strategist)
      5) default 0.0
    """
    gsig = state.get("global_sentiment_signal")
    if isinstance(gsig, dict):
        try:
            return _clamp(float(gsig.get("score") or 0.0), -1.0, 1.0)
        except Exception:
            return 0.0

    if "mock_global_sentiment" in state:
        try:
            return _clamp(float(state.get("mock_global_sentiment") or 0.0), -1.0, 1.0)
        except Exception:
            return 0.0

    gs = state.get("global_sentiment")
    if isinstance(gs, dict) and "score" in gs:
        try:
            return _clamp(float(gs.get("score") or 0.0), -1.0, 1.0)
        except Exception:
            return 0.0
    if isinstance(gs, (int, float, str)):
        try:
            return _clamp(float(gs), -1.0, 1.0)
        except Exception:
            return 0.0

    pol = state.get("policy")
    if isinstance(pol, dict):
        pgs = pol.get("global_sentiment")
        if isinstance(pgs, dict) and "score" in pgs:
            try:
                return _clamp(float(pgs.get("score") or 0.0), -1.0, 1.0)
            except Exception:
                return 0.0
        if isinstance(pgs, (int, float, str)):
            try:
                return _clamp(float(pgs), -1.0, 1.0)
            except Exception:
                return 0.0

    return 0.0


def _get_news_sentiment_map(state: Dict[str, Any]) -> Dict[str, float]:
    """Return per-symbol news sentiment map in [-1, +1].

    Priority:
      1) state['news_sentiment_signal'][symbol]['score']
      2) state['news_sentiment'][symbol]
      3) state['mock_news_sentiment'][symbol]
    """
    raw_sig = state.get("news_sentiment_signal")
    if isinstance(raw_sig, dict):
        out_sig: Dict[str, float] = {}
        for k, v in raw_sig.items():
            if isinstance(v, dict):
                try:
                    out_sig[str(k)] = _clamp(float(v.get("score") or 0.0), -1.0, 1.0)
                except Exception:
                    out_sig[str(k)] = 0.0
        if out_sig:
            return out_sig

    raw = state.get("news_sentiment")
    if not isinstance(raw, dict):
        raw = state.get("mock_news_sentiment") if isinstance(state.get("mock_news_sentiment"), dict) else {}
    out: Dict[str, float] = {}
    for k, v in (raw or {}).items():
        try:
            out[str(k)] = _clamp(float(v), -1.0, 1.0)
        except Exception:
            out[str(k)] = 0.0
    return out


def _get_global_sentiment_signal(state: Dict[str, Any]) -> Dict[str, Any]:
    sig = state.get("global_sentiment_signal")
    if isinstance(sig, dict):
        return dict(sig)
    if "mock_global_sentiment" in state:
        return {"status": "ok", "source": "mock_global_sentiment", "reason": ""}
    gs = state.get("global_sentiment")
    if isinstance(gs, dict) and gs.get("score") is not None:
        return {"status": "fallback", "source": "legacy_global_sentiment", "reason": "signal_missing"}
    return {"status": "fallback", "source": "scanner_node", "reason": "missing_global_signal"}


def _get_news_sentiment_signal_map(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = state.get("news_sentiment_signal")
    if not isinstance(raw, dict):
        raw_scores = state.get("news_sentiment")
        if not isinstance(raw_scores, dict):
            raw_scores = state.get("mock_news_sentiment") if isinstance(state.get("mock_news_sentiment"), dict) else {}
        out_legacy: Dict[str, Dict[str, Any]] = {}
        for k, _v in (raw_scores or {}).items():
            source = "legacy_news_sentiment"
            status = "fallback"
            if isinstance(state.get("mock_news_sentiment"), dict) and str(k) in state.get("mock_news_sentiment", {}):
                source = "mock_news_sentiment"
                status = "ok"
            out_legacy[str(k)] = {"status": status, "source": source, "reason": "signal_missing"}
        return out_legacy
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k)] = dict(v)
    return out


def _get_scanner_weights(policy: Any) -> Dict[str, float]:
    """Scanner weighting policy for M18-4.

    Defaults are conservative (small influence), and should not change behavior
    when sentiments are missing (both default to 0.0).
    """
    pol = policy if isinstance(policy, dict) else {}
    return {
        "weight_news": float(pol.get("weight_news", 0.20)),
        "weight_global": float(pol.get("weight_global", 0.10)),
        "risk_news_penalty": float(pol.get("risk_news_penalty", 0.30)),
        "risk_global_penalty": float(pol.get("risk_global_penalty", 0.20)),
        "confidence_news_boost": float(pol.get("confidence_news_boost", 0.05)),
        "feature_score_weight": float(pol.get("feature_score_weight", 0.0)),
        "feature_risk_penalty": float(pol.get("feature_risk_penalty", 0.0)),
        "high_vol_risk_penalty": float(pol.get("high_vol_risk_penalty", 0.0)),
    }


def _stable_unit_hash(text: str) -> float:
    """Return a deterministic pseudo-random float in [0, 1).

    We avoid Python's built-in hash() because it is salted per-process.
    """
    # A tiny, deterministic rolling hash
    h = 0
    for ch in text:
        h = (h * 131 + ord(ch)) % 10_000
    return (h % 10_000) / 10_000.0


def _extract_feature_engine_map(state: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], str, List[str]]:
    errors: List[str] = []

    # Priority 1: explicit features map injection.
    direct = state.get("scanner_features")
    if isinstance(direct, dict):
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in direct.items():
            if not isinstance(v, dict):
                continue
            sym = _norm_symbol(k)
            if sym:
                out[sym] = dict(v)
        return out, "state.scanner_features", errors

    # Priority 2: precomputed feature engine output.
    fe = state.get("feature_engine")
    if isinstance(fe, dict) and isinstance(fe.get("by_symbol"), dict):
        out2: Dict[str, Dict[str, Any]] = {}
        by_symbol = fe.get("by_symbol") or {}
        for k, v in by_symbol.items():
            if not isinstance(v, dict):
                continue
            sym = _norm_symbol(k)
            if sym:
                out2[sym] = dict(v)
        return out2, "state.feature_engine.by_symbol", errors

    # Priority 3: compute from OHLCV data if available.
    ohlcv = state.get("ohlcv_by_symbol")
    if isinstance(ohlcv, dict):
        try:
            policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
            trend_gap_threshold = float(policy.get("feature_trend_gap_threshold", 0.01))
            high_vol_threshold = float(policy.get("feature_high_vol_threshold", 0.03))
            ctx: Dict[str, Any] = {
                "global_sentiment": _get_global_sentiment_score(state),
            }
            # Optional context hooks (already normalized in state when available).
            if isinstance(state.get("market_context"), dict):
                mc = state.get("market_context") or {}
                if mc.get("market_breadth") is not None:
                    ctx["market_breadth"] = mc.get("market_breadth")
                if mc.get("index_trend") is not None:
                    ctx["index_trend"] = mc.get("index_trend")
                if mc.get("realized_vol") is not None:
                    ctx["realized_vol"] = mc.get("realized_vol")
            built = build_feature_map(
                ohlcv,
                trend_gap_threshold=trend_gap_threshold,
                high_vol_threshold=high_vol_threshold,
                context=ctx,
            )
            return {_norm_symbol(k): v for k, v in built.items() if _norm_symbol(k)}, "state.ohlcv_by_symbol", errors
        except Exception as e:
            errors.append(f"feature_engine:error:{type(e).__name__}")

    return {}, "none", errors


def _normalize_scanner_blocker_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"mixed", "none"}:
        return ""
    if text in {"buy_blocked_open_position", "open_position_blocked"}:
        return "open_position_guard"
    if text.startswith("entry_guard_cooldown") or "cooldown" in text:
        return "cooldown_guard"
    if text in {
        "pullback_not_mature",
        "pullback_mature",
        "pullback_ok",
        "pullback_structure_ok",
        "pullback_volume_path_ok",
        "pullback_below_vwap_reclaim_not_ready",
    } or "pullback" in text:
        return "pullback_timing"
    if "extend" in text or "overextended" in text:
        return "overextension_guard"
    if text in {
        "below_vwap_reclaim_not_ready",
        "vwap_reclaim_ok",
        "reclaim_gate_ok",
        "vwap_hold_ok",
    } or "reclaim" in text or "vwap" in text:
        return "reclaim_readiness"
    if text in {"volume_confirmation_missing", "volume_insufficient", "volume_ok"} or "volume" in text:
        return "volume_confirmation"
    if text in {
        "breakout_not_ready",
        "breakout_ok",
        "breakout_path_ok",
        "wait_for_confirmation",
    } or "breakout" in text or "confirmation" in text:
        return "breakout_confirmation"
    if text in {"rebound_ok"} or "rebound" in text:
        return "rebound_confirmation"
    if text in {"structure_hh_hl", "chart_structure_guard"} or "structure" in text:
        return "structure_confirmation"
    if text in {"confidence_gate_ok"} or "confidence" in text:
        return "confidence_gate"
    if text.startswith("risk_") or text == "risk_blocked":
        return "risk_guard"
    if text == "unknown":
        return "unknown"
    return "other"


def _candidate_blocker_families(row: Mapping[str, Any]) -> List[str]:
    if not isinstance(row, Mapping):
        return []
    out: List[str] = []
    seen = set()
    for raw in (
        row.get("expected_monitor_block_reason"),
        row.get("dominant_block_reason"),
    ):
        family = _normalize_scanner_blocker_family(raw)
        if not family or family in {"unknown", "other"} or family in seen:
            continue
        seen.add(family)
        out.append(family)
    return out


def _resolve_scanner_score_weights(policy: Dict[str, Any]) -> Dict[str, float]:
    def pf(key: str, env_key: str, default: float) -> float:
        raw = policy.get(key)
        if raw in (None, ""):
            raw = os.getenv(env_key, str(default))
        return _to_float(raw)

    return {
        "trading_value": pf("score_weight_trading_value", "SCORE_WEIGHTS_TRADING_VALUE", 0.20),
        "momentum": pf("score_weight_momentum", "SCORE_WEIGHTS_MOMENTUM", 0.22),
        "trend": pf("score_weight_trend", "SCORE_WEIGHTS_TREND", 0.20),
        "volume_surge": pf("score_weight_volume_surge", "SCORE_WEIGHTS_VOLUME_SURGE", 0.14),
        "intraday_strength": pf("score_weight_intraday_strength", "SCORE_WEIGHTS_INTRADAY_STRENGTH", 0.12),
        "theme_boost": pf("score_weight_theme_boost", "SCORE_WEIGHTS_THEME_BOOST", 0.06),
        "sentiment": pf("score_weight_sentiment", "SCORE_WEIGHTS_SENTIMENT", 0.06),
        "volatility_penalty": pf("score_weight_volatility_penalty", "SCORE_WEIGHTS_VOLATILITY_PENALTY", 0.10),
        "gap_penalty": pf("score_weight_gap_penalty", "SCORE_WEIGHTS_GAP_PENALTY", 0.07),
        "open_order_penalty": pf("score_weight_open_order_penalty", "SCORE_WEIGHTS_OPEN_ORDER_PENALTY", 0.04),
    }


def _extract_scanner_guidance(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output_raw = state.get("strategist_output")
    strategist_output = coerce_strategist_output(strategist_output_raw) if isinstance(strategist_output_raw, dict) else {}
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    scanner_policy = (
        dict(strategy_policy.get("scanner_policy") or {})
        if isinstance(strategy_policy.get("scanner_policy"), dict)
        else {}
    )
    monitor_policy = (
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
    scanner_bias_context = {}
    if isinstance(commander_context.get("scanner_bias"), dict):
        scanner_bias_context = dict(commander_context.get("scanner_bias") or {})
    elif isinstance(scanner_policy.get("scanner_bias"), dict):
        scanner_bias_context = dict(scanner_policy.get("scanner_bias") or {})
    elif isinstance(strategist_output.get("scanner_bias_context"), dict):
        scanner_bias_context = dict(strategist_output.get("scanner_bias_context") or {})
    scanner_memory_bias = {}
    if isinstance(commander_context.get("scanner_memory_bias"), dict):
        scanner_memory_bias = dict(commander_context.get("scanner_memory_bias") or {})
    elif isinstance(scanner_policy.get("scanner_memory_bias"), dict):
        scanner_memory_bias = dict(scanner_policy.get("scanner_memory_bias") or {})
    elif isinstance(strategist_output.get("scanner_memory_bias"), dict):
        scanner_memory_bias = dict(strategist_output.get("scanner_memory_bias") or {})
    symbol_constraints = (
        dict(strategist_plan.get("symbol_constraints") or {})
        if isinstance(strategist_plan.get("symbol_constraints"), dict)
        else {}
    )
    raw_bias = strategist_output.get("scanner_bias")
    if isinstance(raw_bias, dict):
        raw_bias = str(raw_bias.get("style") or "")
    base = {
        "themes": list(strategist_output.get("themes") or []),
        "selected_themes": list(strategist_output.get("selected_themes") or []),
        "avoid_themes": list(strategist_output.get("avoid_themes") or []),
        "playbook": str(
            strategist_output.get("playbook")
            or strategist_plan.get("selected_playbook")
            or ""
        ),
        "tactical_strategy": str(strategist_output.get("tactical_strategy") or ""),
        "tactical_subtype": str(strategist_output.get("tactical_subtype") or ""),
        "scanner_priority": list(
            scanner_policy.get("priority_tilts")
            or strategist_output.get("scanner_priority")
            or symbol_constraints.get("scanner_priority")
            or []
        ),
        "scanner_source_policy": dict(
            scanner_policy.get("candidate_sources")
            if isinstance(scanner_policy.get("candidate_sources"), dict)
            else strategist_output.get("scanner_source_policy")
            or {}
        ),
        "scanner_bias": str(raw_bias or "").strip().lower(),
        "scanner_bias_context": dict(scanner_bias_context),
        "scanner_memory_bias": dict(scanner_memory_bias),
        "trade_aggressiveness": strategist_output.get("trade_aggressiveness"),
        "risk_tone": strategist_output.get("risk_tone"),
        "monitor_guidance": strategist_output.get("monitor_guidance"),
        "theme_source": strategist_output.get("theme_source"),
        "theme_source_status": strategist_output.get("theme_source_status"),
        "theme_strength_packet": dict(strategist_output.get("theme_strength_packet") or {})
        if isinstance(strategist_output.get("theme_strength_packet"), dict)
        else {},
        "available_themes": list(strategist_output.get("available_themes") or []),
        "theme_strategy": dict(strategist_output.get("theme_strategy") or {})
        if isinstance(strategist_output.get("theme_strategy"), dict)
        else {},
        "score_weights": dict(scanner_policy.get("score_weights") or {}),
        "filters": dict(scanner_policy.get("filters") or {}),
        "ranking_rules": dict(scanner_policy.get("ranking_rules") or {}),
        "monitor_policy": dict(monitor_policy),
        "commander_context": commander_context,
        "strategist_plan": strategist_plan,
        "policy_provenance": policy_provenance,
    }

    # Backward-compatible override hook; canonical source remains strategist_output.
    guidance = state.get("scanner_guidance")
    if isinstance(guidance, dict):
        out = dict(base)
        for key in (
            "themes",
            "selected_themes",
            "avoid_themes",
            "playbook",
            "tactical_strategy",
            "tactical_subtype",
            "scanner_priority",
            "scanner_source_policy",
            "scanner_bias",
            "scanner_bias_context",
            "scanner_memory_bias",
            "trade_aggressiveness",
            "risk_tone",
            "monitor_guidance",
            "theme_source",
            "theme_source_status",
            "theme_strength_packet",
            "available_themes",
            "theme_strategy",
            "score_weights",
            "filters",
            "ranking_rules",
            "monitor_policy",
            "commander_context",
            "strategist_plan",
            "policy_provenance",
        ):
            if guidance.get(key) not in (None, ""):
                out[key] = guidance.get(key)
        raw_override_bias = out.get("scanner_bias")
        if isinstance(raw_override_bias, dict):
            out["scanner_bias"] = str(raw_override_bias.get("style") or "")
        return out

    return base


_build_kiwoom_candidates = partial(
    _build_kiwoom_candidates_base,
    scanner_guidance_resolver=_extract_scanner_guidance,
)
_resolve_scanner_candidates = partial(
    _resolve_scanner_candidates_base,
    scanner_guidance_resolver=_extract_scanner_guidance,
)

def _build_scanner_policy_trace(
    *,
    commander_context: Dict[str, Any],
    strategist_plan: Dict[str, Any],
    policy_provenance: Dict[str, Any],
    playbook: str,
    scanner_priority: List[str],
    scanner_bias: str,
    scanner_bias_context: Dict[str, Any],
    scanner_memory_bias: Dict[str, Any],
) -> Dict[str, Any]:
    consumed_fields: List[str] = []
    for key in (
        "scanner_mission",
        "allowed_playbooks",
        "banned_playbooks",
        "risk_mode",
        "command_intent",
        "strategist_invocation",
        "no_trade_reason_code",
        "source_priority",
    ):
        value = commander_context.get(key)
        if value not in (None, "", [], {}):
            consumed_fields.append(key)
    commander_context_consumed = bool(consumed_fields)

    strategist_consumed_fields: List[str] = []
    for key in ("selected_playbook", "candidate_hypotheses", "symbol_constraints", "strategy_summary"):
        value = strategist_plan.get(key)
        if value not in (None, "", [], {}):
            strategist_consumed_fields.append(key)

    commander_priority_ref = {
        "scanner_mission": str(commander_context.get("scanner_mission") or ""),
        "allowed_playbooks": list(commander_context.get("allowed_playbooks") or []),
        "banned_playbooks": list(commander_context.get("banned_playbooks") or []),
        "risk_mode": str(commander_context.get("risk_mode") or ""),
        "command_intent": str(commander_context.get("command_intent") or ""),
        "strategist_invocation": str(commander_context.get("strategist_invocation") or ""),
        "no_trade_reason_code": str(commander_context.get("no_trade_reason_code") or ""),
        "source_priority": list(commander_context.get("source_priority") or []),
    }
    strategist_constraints_ref = {
        "selected_playbook": str(strategist_plan.get("selected_playbook") or ""),
        "candidate_hypotheses": list(strategist_plan.get("candidate_hypotheses") or []),
        "symbol_constraints": dict(strategist_plan.get("symbol_constraints") or {}),
        "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
    }
    applied_policy = (
        dict(commander_context.get("applied_policy") or {})
        if isinstance(commander_context.get("applied_policy"), dict)
        else {}
    )
    normalized_scanner_bias_context, _scanner_bias_meta = normalize_scanner_bias_context(
        scanner_bias_context or None,
        bias_source=str(commander_context.get("policy_source") or "strategist"),
    )
    scanner_bias_summary = summarize_scanner_bias_context(normalized_scanner_bias_context)
    scanner_memory_bias_summary = summarize_scanner_memory_bias(scanner_memory_bias)
    policy_source = str(
        commander_context.get("policy_source")
        or policy_provenance.get("applied_policy_source")
        or policy_provenance.get("monitor_entry_policy_source")
        or ""
    )
    monitor_entry_policy_summary = {
        key: applied_policy.get(key)
        for key in (
            "timeframe_minutes",
            "breakout_lookback",
            "volume_lookback",
            "volume_ratio_min",
            "pullback_min_pct",
            "pullback_max_pct",
            "max_extended_from_vwap_pct",
        )
        if key in applied_policy
    }
    ranking_factors = list(dict.fromkeys([str(x).strip() for x in list(scanner_priority or []) if str(x).strip()]))[:8]
    if scanner_bias:
        ranking_factors.append(f"bias:{scanner_bias}")
    if bool(scanner_bias_summary.get("enabled")):
        ranking_factors.append(f"scanner_bias:{scanner_bias_summary.get('summary')}")
    if bool(scanner_memory_bias_summary.get("enabled")):
        ranking_factors.append("memory_bias")
    if playbook:
        ranking_factors.append(f"playbook:{playbook}")
    if str(commander_context.get("scanner_mission") or "").strip():
        ranking_factors.append("commander_mission")
    if str(commander_context.get("risk_mode") or "").strip():
        ranking_factors.append(f"risk_mode:{str(commander_context.get('risk_mode') or '').strip()}")
    ranking_factors = list(dict.fromkeys(ranking_factors))[:10]

    summary_parts: List[str] = []
    if str(commander_context.get("scanner_mission") or "").strip():
        summary_parts.append(f"commander_mission={str(commander_context.get('scanner_mission') or '').strip()}")
    if str(strategist_plan.get("selected_playbook") or playbook).strip():
        summary_parts.append(f"playbook={str(strategist_plan.get('selected_playbook') or playbook).strip()}")
    if str(commander_context.get("risk_mode") or "").strip():
        summary_parts.append(f"risk_mode={str(commander_context.get('risk_mode') or '').strip()}")
    if str(commander_context.get("no_trade_reason_code") or "").strip():
        summary_parts.append(f"no_trade_reason={str(commander_context.get('no_trade_reason_code') or '').strip()}")
    if policy_source:
        summary_parts.append(f"policy_source={policy_source}")
    if bool(scanner_bias_summary.get("enabled")):
        summary_parts.append(f"scanner_bias={str(scanner_bias_summary.get('summary') or '')}")
    if bool(scanner_memory_bias_summary.get("enabled")):
        summary_parts.append("memory_bias=commander")

    return {
        "commander_context_consumed": commander_context_consumed,
        "consumed_fields": consumed_fields,
        "commander_priority_ref": commander_priority_ref,
        "strategist_constraints_ref": strategist_constraints_ref,
        "selection_basis": {
            "commander_context_consumed": commander_context_consumed,
            "strategist_plan_consumed": bool(strategist_consumed_fields),
            "consumed_fields": consumed_fields + strategist_consumed_fields,
            "scanner_bias_context": normalized_scanner_bias_context.to_dict(),
            "scanner_bias_summary": dict(scanner_bias_summary),
            "scanner_memory_bias_summary": dict(scanner_memory_bias_summary),
            "summary": " | ".join(summary_parts) if summary_parts else "base_quantitative_ranking",
        },
        "ranking_factors": ranking_factors,
        "playbook": str(strategist_plan.get("selected_playbook") or playbook or ""),
        "policy_source": policy_source,
        "applied_policy_present": bool(applied_policy),
        "monitor_entry_policy_summary": monitor_entry_policy_summary,
        "scanner_bias_context": normalized_scanner_bias_context.to_dict(),
        "scanner_bias_summary": dict(scanner_bias_summary),
        "scanner_memory_bias": dict(scanner_memory_bias or {}),
        "scanner_memory_bias_summary": dict(scanner_memory_bias_summary),
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
        "policy_provenance_ref": {
            "policy_source": policy_source,
            "applied_policy_present": bool(applied_policy),
            "monitor_entry_policy_summary": monitor_entry_policy_summary,
            "scanner_bias_summary": dict(scanner_bias_summary),
        },
    }


def _normalize_priority_list(values: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    if not isinstance(values, list):
        return out
    for row in values:
        s = str(row or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _apply_scanner_guidance_weights(
    weights: Dict[str, float],
    *,
    playbook: str,
    scanner_bias: str,
    scanner_priority: List[str],
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, float]:
    out = dict(weights or {})
    bias = str(scanner_bias or "").strip().lower()
    priority_set = set(_normalize_priority_list(scanner_priority))
    playbook_norm = str(playbook or "").strip().lower()
    aggr = str(trade_aggressiveness or "").strip().lower()
    tone = str(risk_tone or "").strip().lower()

    if bias == "large_cap":
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.10)
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.12)
    elif bias == "leader":
        out["trend"] = float(out.get("trend", 0.0) * 1.08)
        out["theme_boost"] = float(out.get("theme_boost", 0.0) * 1.08)
    elif bias == "momentum":
        out["momentum"] = float(out.get("momentum", 0.0) * 1.12)
        out["volume_surge"] = float(out.get("volume_surge", 0.0) * 1.08)
    elif bias == "value":
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.10)
        out["momentum"] = float(out.get("momentum", 0.0) * 0.94)

    # Priority-driven mild boosts (additive-safe, scanner remains quantitative).
    if "liquidity" in priority_set:
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.10)
    if "momentum" in priority_set or "breakout" in priority_set:
        out["momentum"] = float(out.get("momentum", 0.0) * 1.12)
    if "trend_strength" in priority_set or "trend" in priority_set:
        out["trend"] = float(out.get("trend", 0.0) * 1.10)
    if "ma_alignment" in priority_set or "moving_average_trend" in priority_set:
        out["trend"] = float(out.get("trend", 0.0) * 1.08)
    if "vwap_reclaim" in priority_set or "vwap_distance" in priority_set:
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 1.08)
    if "cross_section_rank" in priority_set or "relative_strength" in priority_set:
        out["trend"] = float(out.get("trend", 0.0) * 1.06)
        out["theme_boost"] = float(out.get("theme_boost", 0.0) * 1.04)
    if "volume_surge" in priority_set or "volume_confirmation" in priority_set:
        out["volume_surge"] = float(out.get("volume_surge", 0.0) * 1.08)
    if "risk_penalty" in priority_set or "drawdown_control" in priority_set:
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.15)
        out["gap_penalty"] = float(out.get("gap_penalty", 0.0) * 1.15)

    # Playbook guidance remains additive (Scanner still does final quantitative ranking).
    if playbook_norm == "breakout":
        out["momentum"] = float(out.get("momentum", 0.0) * 1.10)
        out["volume_surge"] = float(out.get("volume_surge", 0.0) * 1.06)
    elif playbook_norm == "pullback":
        out["trend"] = float(out.get("trend", 0.0) * 1.08)
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 1.05)
    elif playbook_norm == "reversal":
        out["momentum"] = float(out.get("momentum", 0.0) * 0.92)
        out["gap_penalty"] = float(out.get("gap_penalty", 0.0) * 1.10)
    elif playbook_norm == "defensive":
        out["trading_value"] = float(out.get("trading_value", 0.0) * 1.08)
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.12)

    # Risk tone / aggressiveness final tuning.
    if aggr == "high" and tone in ("aggressive", "normal"):
        out["momentum"] = float(out.get("momentum", 0.0) * 1.05)
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 1.05)
    if aggr == "low" or tone == "conservative":
        out["volatility_penalty"] = float(out.get("volatility_penalty", 0.0) * 1.20)
        out["gap_penalty"] = float(out.get("gap_penalty", 0.0) * 1.20)
        out["intraday_strength"] = float(out.get("intraday_strength", 0.0) * 0.95)
        out["momentum"] = float(out.get("momentum", 0.0) * 0.95)

    return out


def _scanner_bias_total_cap(bias_strength: str) -> float:
    return 0.04 if str(bias_strength or "").strip().lower() == "medium" else 0.02


def _compute_structured_scanner_bias(
    *,
    symbol: str,
    feature_row: Dict[str, Any],
    metrics: Dict[str, Any],
    bias_context: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_context, _meta = normalize_scanner_bias_context(bias_context or None)
    context = normalized_context.to_dict()
    summary = summarize_scanner_bias_context(context)
    if not bool(summary.get("enabled")):
        return {
            "bias_adjustment": 0.0,
            "bias_adjustments": [],
            "bias_summary": dict(summary),
            "bias_signals": {},
        }

    vwap_distance = _to_float(feature_row.get("vwap_distance"))
    volume_spike20 = _to_float(feature_row.get("volume_spike20"))
    intraday_change_pct = _to_float(metrics.get("change_pct"))
    signals = {
        "vwap_distance": float(vwap_distance),
        "volume_spike20": float(volume_spike20),
        "intraday_change_pct": float(intraday_change_pct),
    }
    adjustments: List[Dict[str, Any]] = []
    bias_delta = 0.0
    strength = str(context.get("bias_strength") or "low").strip().lower()
    cap = _scanner_bias_total_cap(strength)
    step = 0.005 if strength == "medium" else 0.003

    if bool(context.get("prefer_shallow_pullback_candidates")) and -0.015 <= vwap_distance <= 0.03:
        bias_delta += step
        adjustments.append({"rule": "prefer_shallow_pullback_candidates", "delta": float(step), "reason": "shallow pullback preference applied"})

    if bool(context.get("penalize_overextended")) and vwap_distance >= 0.08:
        delta = -(step * 1.5)
        bias_delta += delta
        adjustments.append({"rule": "penalize_overextended", "delta": float(delta), "reason": "overextended penalty applied"})

    if bool(context.get("prefer_reclaim_candidates")) and -0.01 <= vwap_distance <= 0.02:
        bias_delta += step
        adjustments.append({"rule": "prefer_reclaim_candidates", "delta": float(step), "reason": "reclaim preference applied"})

    if bool(context.get("prefer_volume_confirmation")) and volume_spike20 >= 1.2:
        bias_delta += step
        adjustments.append({"rule": "prefer_volume_confirmation", "delta": float(step), "reason": "volume confirmation bias applied"})

    bias_delta = _clamp(bias_delta, -cap, cap)
    if adjustments and abs(bias_delta) < 1e-9:
        adjustments = []

    return {
        "bias_adjustment": float(bias_delta),
        "bias_adjustments": adjustments[:4],
        "bias_summary": dict(summary),
        "bias_signals": signals,
        "symbol": str(symbol or ""),
    }


def _summarize_quote_metric_coverage(
    candidates: List[Any],
    *,
    skill_quotes: Dict[str, Dict[str, Any]],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    live_equity_candidates = 0
    quote_rows_present = 0
    quote_rows_with_price = 0
    quote_rows_with_activity = 0
    zero_quote_metric_symbols: List[str] = []

    for item in list(candidates or []):
        symbol = _norm_symbol(item.get("symbol") if isinstance(item, dict) else item)
        if not _is_live_equity_symbol(symbol):
            continue
        live_equity_candidates += 1
        quote = skill_quotes.get(symbol) if isinstance(skill_quotes.get(symbol), dict) else {}
        if quote:
            quote_rows_present += 1
            if _to_float(quote.get("price") or quote.get("cur")) > 0.0:
                quote_rows_with_price += 1
        metrics = _candidate_quote_metrics(symbol, skill_quotes=skill_quotes, state=state)
        if (
            _to_float(metrics.get("volume")) > 0.0
            or _to_float(metrics.get("trading_value")) > 0.0
            or abs(_to_float(metrics.get("change_pct"))) > 1e-9
        ):
            quote_rows_with_activity += 1
        else:
            zero_quote_metric_symbols.append(symbol)

    return {
        "live_equity_candidates": int(live_equity_candidates),
        "quote_rows_present": int(quote_rows_present),
        "quote_rows_with_price": int(quote_rows_with_price),
        "quote_rows_with_activity": int(quote_rows_with_activity),
        "zero_quote_metric_symbols": list(zero_quote_metric_symbols)[:10],
    }


def _should_refresh_scanner_features(
    *,
    state: Dict[str, Any],
    candidates: List[Any],
    quote_metric_coverage: Dict[str, Any],
) -> Tuple[bool, str]:
    live_equity_candidates = _to_int(quote_metric_coverage.get("live_equity_candidates"), 0)
    if live_equity_candidates <= 0:
        return False, ""
    if _to_int(quote_metric_coverage.get("quote_rows_with_activity"), 0) > 0:
        return False, ""

    fe_root = state.get("feature_engine") if isinstance(state.get("feature_engine"), dict) else {}
    fe_by_symbol = fe_root.get("by_symbol") if isinstance(fe_root.get("by_symbol"), dict) else {}
    if not isinstance(fe_by_symbol, dict) or not fe_by_symbol:
        return False, ""

    stale_symbols: List[str] = []
    for item in list(candidates or []):
        symbol = _norm_symbol(item.get("symbol") if isinstance(item, dict) else item)
        if not _is_live_equity_symbol(symbol):
            continue
        value = fe_by_symbol.get(symbol)
        if isinstance(value, dict) and value:
            stale_symbols.append(symbol)
    if not stale_symbols:
        return False, ""
    return True, "quote_metrics_missing_rebuild_feature_engine"


def _build_scanner_monitor_policy_input(
    *,
    state: Dict[str, Any],
    commander_context: Dict[str, Any],
    monitor_policy: Dict[str, Any],
) -> Dict[str, Any]:
    if isinstance(commander_context.get("applied_policy"), dict):
        return dict(commander_context.get("applied_policy") or {})
    if isinstance(state.get("commander_applied_policy"), dict):
        return dict(state.get("commander_applied_policy") or {})
    if isinstance(monitor_policy.get("entry_policy"), dict):
        return dict(monitor_policy.get("entry_policy") or {})
    if isinstance(state.get("monitor_entry_policy"), dict):
        return dict(state.get("monitor_entry_policy") or {})
    return {}


def _build_scanner_monitor_frame(
    *,
    playbook: str,
    monitor_guidance: str,
    risk_tone: str,
    trade_aggressiveness: str,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if str(playbook or "").strip():
        out["playbook"] = str(playbook).strip().lower()
    if str(monitor_guidance or "").strip():
        out["monitor_guidance"] = str(monitor_guidance).strip().lower()
    if str(risk_tone or "").strip():
        out["risk_tone"] = str(risk_tone).strip().lower()
    if str(trade_aggressiveness or "").strip():
        out["trade_aggressiveness"] = str(trade_aggressiveness).strip().lower()
    return out


def _calc_reclaim_proximity(*, actual: float | None, minimum: float | None) -> float:
    if actual is None:
        return 0.5
    actual_num = float(actual)
    minimum_num = float(minimum if minimum is not None else -0.02)
    if actual_num >= minimum_num:
        return 1.0
    band = max(0.05, abs(minimum_num) * 3.0)
    return _clamp(1.0 - abs(actual_num - minimum_num) / band, 0.0, 1.0)


def _calc_breakout_proximity(*, actual: float | None, minimum: float | None) -> float:
    if actual is None:
        return 0.5
    actual_num = float(actual)
    minimum_num = float(minimum if minimum is not None else 0.0)
    if actual_num >= minimum_num:
        return 1.0
    band = 0.02
    return _clamp(1.0 - abs(actual_num - minimum_num) / band, 0.0, 1.0)


def _scanner_chart_fit_from_entry_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    chart_features = (
        dict(result.get("chart_structure_features") or {})
        if isinstance(result.get("chart_structure_features"), Mapping)
        else {}
    )
    context = (
        dict(chart_features.get("human_chart_context") or {})
        if isinstance(chart_features.get("human_chart_context"), Mapping)
        else {}
    )
    if not bool(context.get("available")):
        return {
            "available": False,
            "chart_context_score": 0.5,
            "exit_risk_score": 0.0,
            "late_entry_risk": "",
            "soft_penalty": 0.0,
            "components": {},
        }
    late_entry_risk = str(context.get("late_entry_risk") or "").strip().lower()
    late_penalty = {"high": 0.10, "medium": 0.05, "low": 0.02}.get(late_entry_risk, 0.0)
    exit_risk_score = _clamp(_to_float(context.get("exit_risk_score")), 0.0, 1.0)
    risk_penalty = 0.05 if exit_risk_score >= 0.55 else 0.0
    return {
        "available": True,
        "chart_context_score": _clamp(_to_float(context.get("entry_chart_score"), 0.5), 0.0, 1.0),
        "exit_risk_score": float(exit_risk_score),
        "late_entry_risk": late_entry_risk,
        "soft_penalty": float(late_penalty + risk_penalty),
        "components": {
            "vwap_reclaim_persistence": context.get("vwap_reclaim_persistence"),
            "ma_bullish_persistence": context.get("ma_bullish_persistence"),
            "volume_expansion_persistence": context.get("volume_expansion_persistence"),
            "late_entry_risk": late_entry_risk,
            "swing_low_above_vwap": bool(context.get("swing_low_above_vwap")),
            "box_breakout_retest_hold": bool(context.get("box_breakout_retest_hold")),
            "exit_risk_score": float(exit_risk_score),
        },
    }


def _scanner_macro_focus(
    *,
    playbook: str = "",
    scanner_priority: List[Any] | None = None,
    risk_tone: str = "",
    trade_aggressiveness: str = "",
) -> Dict[str, float]:
    focus = {
        "trend_alignment": 1.0,
        "relative_strength": 1.0,
        "adx_trend": 1.0,
        "volume_accumulation": 1.0,
        "breakout_base": 1.0,
        "risk_balance": 1.0,
    }
    playbook_text = str(playbook or "").strip().lower()
    if playbook_text == "breakout":
        focus["breakout_base"] += 0.25
        focus["volume_accumulation"] += 0.15
        focus["relative_strength"] += 0.10
    elif playbook_text in {"pullback", "reversal"}:
        focus["trend_alignment"] += 0.15
        focus["risk_balance"] += 0.15
        focus["breakout_base"] -= 0.10
    elif playbook_text == "defensive":
        focus["risk_balance"] += 0.25
        focus["trend_alignment"] += 0.10

    for item in list(scanner_priority or []):
        text = str(item or "").strip().lower()
        if text in {"trend", "trend_strength", "ma_alignment", "ma20", "ma60", "ma120"}:
            focus["trend_alignment"] += 0.10
        elif text in {"relative_strength", "cross_section_rank", "leader", "leaders"}:
            focus["relative_strength"] += 0.10
        elif text in {"adx", "adx14"}:
            focus["adx_trend"] += 0.10
        elif text in {"volume", "volume_surge", "volume_spike", "turnover"}:
            focus["volume_accumulation"] += 0.10
        elif text in {"breakout", "breakout_base", "vwap_reclaim", "momentum"}:
            focus["breakout_base"] += 0.10
        elif text in {"low_risk", "risk", "volatility", "gap"}:
            focus["risk_balance"] += 0.10

    risk_text = str(risk_tone or "").strip().lower()
    if risk_text == "conservative":
        focus["risk_balance"] += 0.20
    elif risk_text == "aggressive":
        focus["breakout_base"] += 0.10
        focus["volume_accumulation"] += 0.10

    aggression_text = str(trade_aggressiveness or "").strip().lower()
    if aggression_text == "high":
        focus["relative_strength"] += 0.10
        focus["breakout_base"] += 0.10
    elif aggression_text == "low":
        focus["risk_balance"] += 0.15
        focus["trend_alignment"] += 0.05

    return {key: _clamp(float(value), 0.50, 1.50) for key, value in focus.items()}


def _compute_scanner_macro_chart_fit(
    *,
    feature_row: Mapping[str, Any],
    ma_alignment_component: float,
    trend_component: float,
    adx_component: float,
    momentum_component: float,
    volume_surge_component: float,
    vwap_alignment_component: float,
    cross_section_rank_component: float,
    volatility_penalty: float,
    gap_penalty: float,
    playbook: str = "",
    scanner_priority: List[Any] | None = None,
    risk_tone: str = "",
    trade_aggressiveness: str = "",
    bias_cap: float = 0.06,
) -> Dict[str, Any]:
    coverage_keys = (
        "return20",
        "ma20_gap",
        "ma60_gap",
        "ma120_gap",
        "trend_strength",
        "adx14",
        "volume_spike20",
        "cross_section_rank",
        "rolling_drawdown20",
        "volatility20",
        "gap_pct",
    )
    coverage = sum(1 for key in coverage_keys if feature_row.get(key) not in (None, ""))
    focus = _scanner_macro_focus(
        playbook=playbook,
        scanner_priority=scanner_priority,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
    )
    if coverage < 3:
        return {
            "scanner_macro_chart_fit_score": 0.5,
            "scanner_macro_chart_fit_bias": 0.0,
            "scanner_macro_chart_fit_authority": "soft_rank_bias_only_insufficient_feature_coverage",
            "scanner_macro_chart_fit_components": {
                "feature_coverage_count": int(coverage),
                "focus": dict(focus),
            },
            "scanner_macro_chart_fit_focus": dict(focus),
        }
    return20 = _to_float(feature_row.get("return20"))
    ma20_gap = _to_float(feature_row.get("ma20_gap"))
    rolling_drawdown20 = abs(_to_float(feature_row.get("rolling_drawdown20")))
    relative_strength = feature_row.get("sector_relative_strength")
    if relative_strength in (None, ""):
        relative_strength = feature_row.get("relative_strength20")
    relative_strength_component = max(
        cross_section_rank_component,
        max(0.0, _signed01(_to_float(relative_strength), 0.08)),
        max(0.0, _signed01(return20, 0.10)),
    )
    trend_alignment_score = _clamp(
        (0.48 * ma_alignment_component) + (0.32 * trend_component) + (0.20 * adx_component),
        0.0,
        1.0,
    )
    adx_trend_score = _clamp((0.65 * adx_component) + (0.35 * trend_component), 0.0, 1.0)
    volume_accumulation_score = _clamp(volume_surge_component, 0.0, 1.0)
    breakout_base_score = _clamp(
        (0.45 * momentum_component)
        + (0.25 * trend_component)
        + (0.20 * vwap_alignment_component)
        + (0.10 * max(0.0, _signed01(ma20_gap, 0.03))),
        0.0,
        1.0,
    )
    drawdown_penalty = _norm01(rolling_drawdown20, 0.08, 0.25)
    overextension_risk = max(
        _norm01(max(0.0, ma20_gap), 0.06, 0.15),
        _clamp(volatility_penalty, 0.0, 1.0),
        _clamp(gap_penalty, 0.0, 1.0),
    )
    risk_balance_score = _clamp(
        1.0
        - (
            (0.40 * _clamp(volatility_penalty, 0.0, 1.0))
            + (0.35 * _clamp(gap_penalty, 0.0, 1.0))
            + (0.25 * drawdown_penalty)
        ),
        0.0,
        1.0,
    )
    components = {
        "trend_alignment_score": float(trend_alignment_score),
        "relative_strength_score": float(_clamp(relative_strength_component, 0.0, 1.0)),
        "adx_trend_score": float(adx_trend_score),
        "volume_accumulation_score": float(volume_accumulation_score),
        "breakout_base_score": float(breakout_base_score),
        "risk_balance_score": float(risk_balance_score),
        "overextension_risk": float(_clamp(overextension_risk, 0.0, 1.0)),
        "rolling_drawdown20": float(rolling_drawdown20),
        "focus": dict(focus),
    }
    weights = {
        "trend_alignment_score": 0.24 * focus["trend_alignment"],
        "relative_strength_score": 0.18 * focus["relative_strength"],
        "adx_trend_score": 0.12 * focus["adx_trend"],
        "volume_accumulation_score": 0.16 * focus["volume_accumulation"],
        "breakout_base_score": 0.18 * focus["breakout_base"],
        "risk_balance_score": 0.12 * focus["risk_balance"],
    }
    weight_total = sum(float(v) for v in weights.values()) or 1.0
    score = _clamp(
        sum(float(components[key]) * weight for key, weight in weights.items()) / weight_total,
        0.0,
        1.0,
    )
    bias_limit = max(0.0, float(bias_cap))
    bias = _clamp((score - 0.50) * 0.12, -bias_limit, bias_limit)
    return {
        "scanner_macro_chart_fit_score": float(score),
        "scanner_macro_chart_fit_bias": float(bias),
        "scanner_macro_chart_fit_authority": "soft_rank_bias_only",
        "scanner_macro_chart_fit_components": components,
        "scanner_macro_chart_fit_focus": dict(focus),
    }


def _compute_entry_compatibility_signal(
    *,
    symbol: str,
    feature_row: Dict[str, Any],
    metrics: Dict[str, Any],
    candidate_rows: List[Dict[str, Any]],
    current_price: Any,
    policy: Any,
    bias_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if policy in (None, {}, ""):
        return {
            "entry_compatibility_score": 0.5,
            "compatibility_bias": 0.0,
            "dominant_block_reason": "mixed",
            "dominant_block_reason_ratio": 0.0,
            "bias_scale": 0.10,
            "soft_penalty": 0.0,
            "compatibility_score_pre_penalty": 0.5,
            "compatibility_score_post_penalty": 0.5,
            "compatibility_components": {
                "vwap_proximity_score": 0.5,
                "volume_readiness_score": 0.5,
                "breakout_readiness_score": 0.5,
                "reclaim_proximity": 0.5,
            },
            "scanner_chart_fit_score": 0.5,
            "scanner_chart_fit_authority": "disabled_no_policy",
            "scanner_chart_fit_components": {},
            "scanner_chart_fit_penalty": 0.0,
            "expected_monitor_block_reason": "",
            "compatibility_source": "disabled",
            "triggered_path": "",
            "paths_passed": [],
            "vwap_distance_abs": None,
            "is_below_vwap": False,
            "reclaim_proximity": 0.5,
            "volume_ratio": None,
            "breakout_gap_pct": None,
        }
    result = evaluate_intraday_entry_signal(
        candidate_rows,
        current_price=current_price,
        features=feature_row,
        policy=policy,
        frame=None,
    )
    thresholds = dict(result.get("threshold_margins") or {})
    condition_scores = dict(result.get("condition_scores") or {})
    metrics_map = dict(result.get("metrics") or {})

    vwap_distance = metrics_map.get("extended_from_vwap_pct")
    if vwap_distance in (None, ""):
        vwap_distance = metrics_map.get("vwap_distance")
    volume_ratio = metrics_map.get("volume_ratio")
    breakout_gap_threshold = thresholds.get("breakout_gap_pct") if isinstance(thresholds.get("breakout_gap_pct"), dict) else {}
    extended_threshold = thresholds.get("extended_from_vwap_pct") if isinstance(thresholds.get("extended_from_vwap_pct"), dict) else {}
    volume_threshold = thresholds.get("volume_ratio") if isinstance(thresholds.get("volume_ratio"), dict) else {}
    breakout_gap_pct = breakout_gap_threshold.get("actual")
    min_extended = extended_threshold.get("min")
    max_extended = extended_threshold.get("max")
    volume_min = volume_threshold.get("min")
    below_vwap = bool(vwap_distance is not None and _to_float(vwap_distance) < 0.0)

    source = "minute_eval"
    if not bool(result.get("evaluated")):
        source = "feature_heuristic"
        vwap_distance = feature_row.get("vwap_distance")
        volume_ratio = feature_row.get("volume_ratio")
        if volume_ratio in (None, ""):
            volume_ratio = feature_row.get("volume_spike20")
        breakout_gap_pct = None
        min_extended = policy.get("min_extended_from_vwap_pct") if hasattr(policy, "get") else None
        max_extended = policy.get("max_extended_from_vwap_pct") if hasattr(policy, "get") else None
        volume_min = policy.get("volume_ratio_min") if hasattr(policy, "get") else None
        below_vwap = bool(vwap_distance is not None and _to_float(vwap_distance) < 0.0)
    elif max_extended in (None, "") and hasattr(policy, "get"):
        max_extended = policy.get("max_extended_from_vwap_pct")

    vwap_distance_num = float(_to_float(vwap_distance)) if vwap_distance not in (None, "") else None
    vwap_distance_abs = abs(vwap_distance_num) if vwap_distance_num is not None else None
    max_extended_num = float(_to_float(max_extended)) if max_extended not in (None, "") else None
    reclaim_proximity = _calc_reclaim_proximity(
        actual=vwap_distance_num,
        minimum=float(min_extended) if min_extended not in (None, "") else None,
    )
    vwap_proximity_score = (
        _clamp(1.0 - abs(min(0.0, float(vwap_distance_num))) / 0.10, 0.0, 1.0)
        if vwap_distance_num is not None
        else 0.5
    )
    overextension_score = 1.0
    if vwap_distance_num is not None and max_extended_num is not None and max_extended_num > 0.0:
        overextension_score = _clamp(
            1.0 - max(0.0, vwap_distance_num - max_extended_num) / max(0.02, max_extended_num),
            0.0,
            1.0,
        )
        vwap_proximity_score = min(vwap_proximity_score, overextension_score)
    volume_readiness_score = 0.5
    if volume_ratio not in (None, ""):
        volume_floor = max(_to_float(volume_min), 1e-6)
        volume_readiness_score = _clamp(_to_float(volume_ratio) / volume_floor, 0.0, 1.0)
    breakout_readiness_score = 0.5
    if breakout_gap_pct not in (None, ""):
        breakout_readiness_score = _clamp(1.0 - abs(min(0.0, _to_float(breakout_gap_pct))) / 0.03, 0.0, 1.0)

    base_compatibility_score = _clamp(
        (0.45 * vwap_proximity_score)
        + (0.35 * volume_readiness_score)
        + (0.20 * breakout_readiness_score),
        0.0,
        1.0,
    )
    chart_fit = _scanner_chart_fit_from_entry_result(result)
    scanner_chart_fit_score = float(base_compatibility_score)
    if bool(chart_fit.get("available")):
        chart_context_score = _clamp(_to_float(chart_fit.get("chart_context_score"), 0.5), 0.0, 1.0)
        scanner_chart_fit_score = _clamp(
            (0.75 * base_compatibility_score)
            + (0.25 * chart_context_score)
            - _to_float(chart_fit.get("soft_penalty")),
            0.0,
            1.0,
        )
    entry_compatibility_score = scanner_chart_fit_score
    compatibility_score_pre_penalty = float(entry_compatibility_score)
    soft_penalty = 0.0
    volume_ratio_num = _to_float(volume_ratio) if volume_ratio not in (None, "") else None
    volume_min_num = max(_to_float(volume_min), 1e-6) if volume_min not in (None, "") else None
    if volume_ratio_num is not None:
        if volume_ratio_num <= 0.0:
            soft_penalty += 0.08
        if volume_min_num is not None and volume_ratio_num < (0.33 * volume_min_num):
            soft_penalty += 0.05
    if vwap_distance_num is not None and vwap_distance_num < -0.07:
        soft_penalty += 0.03
    if (
        vwap_distance_num is not None
        and max_extended_num is not None
        and max_extended_num > 0.0
        and vwap_distance_num > max_extended_num
    ):
        soft_penalty += min(0.12, 0.04 + (vwap_distance_num - max_extended_num))
    if str(result.get("reason") or "").strip() == "too_extended_from_vwap":
        soft_penalty += 0.04
    compatibility_score_post_penalty = max(0.0, compatibility_score_pre_penalty - soft_penalty)
    if str(result.get("reason") or "").strip() == "too_extended_from_vwap":
        compatibility_score_post_penalty = min(compatibility_score_post_penalty, 0.35)
    dominant_block_reason = str((bias_context or {}).get("dominant_block_reason") or "mixed")
    dominant_block_reason_ratio = float(_to_float((bias_context or {}).get("dominant_block_reason_ratio")))
    bias_scale = float(_to_float((bias_context or {}).get("bias_scale") or 0.10))
    compatibility_bias = bias_scale * (compatibility_score_post_penalty - 0.5)
    expected_monitor_block_reason = ""
    if not bool(result.get("triggered")):
        expected_monitor_block_reason = str(result.get("reason") or "").strip()
    elif below_vwap:
        expected_monitor_block_reason = "below_vwap_reclaim_not_ready"

    return {
        "entry_compatibility_score": float(compatibility_score_post_penalty),
        "compatibility_bias": float(compatibility_bias),
        "dominant_block_reason": dominant_block_reason,
        "dominant_block_reason_ratio": float(dominant_block_reason_ratio),
        "bias_scale": float(bias_scale),
        "soft_penalty": float(soft_penalty),
        "compatibility_score_pre_penalty": float(compatibility_score_pre_penalty),
        "compatibility_score_post_penalty": float(compatibility_score_post_penalty),
        "compatibility_components": {
            "vwap_proximity_score": float(vwap_proximity_score),
            "volume_readiness_score": float(volume_readiness_score),
            "breakout_readiness_score": float(breakout_readiness_score),
            "reclaim_proximity": float(reclaim_proximity),
            "base_compatibility_score": float(base_compatibility_score),
            "scanner_chart_fit_score": float(scanner_chart_fit_score),
            "scanner_chart_fit_available": bool(chart_fit.get("available")),
        },
        "scanner_chart_fit_score": float(scanner_chart_fit_score),
        "scanner_chart_fit_authority": "soft_rank_bias_only",
        "scanner_chart_fit_components": dict(chart_fit.get("components") or {}),
        "scanner_chart_fit_penalty": float(_to_float(chart_fit.get("soft_penalty"))),
        "expected_monitor_block_reason": expected_monitor_block_reason,
        "compatibility_source": source,
        "triggered_path": str(result.get("entry_condition_path") or ""),
        "paths_passed": list(result.get("entry_condition_paths_passed") or []),
        "vwap_distance_abs": float(vwap_distance_abs) if vwap_distance_abs is not None else None,
        "is_below_vwap": bool(below_vwap),
        "reclaim_proximity": float(reclaim_proximity),
        "volume_ratio": float(_to_float(volume_ratio)) if volume_ratio not in (None, "") else None,
        "breakout_gap_pct": float(_to_float(breakout_gap_pct)) if breakout_gap_pct not in (None, "") else None,
    }


def _resolve_canonical_day(state: Dict[str, Any]) -> str:
    for key in ("day", "trade_day", "session_day"):
        value = str(state.get(key) or "").strip()
        if value:
            return value
    now_epoch = _resolve_now_epoch(state)
    return datetime.fromtimestamp(now_epoch).strftime("%Y-%m-%d")


_ENTRY_COMPATIBILITY_BLOCK_REASONS = {
    "too_extended_from_vwap",
    "breakout_not_ready",
    "volume_insufficient",
    "volume_confirmation_missing",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
    "pullback_not_mature",
    "minute_candle_missing",
    "human_chart_sanity_guard_blocked",
}


def _extract_monitor_entry_block_reason(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    cascade = payload.get("entry_candidate_cascade") if isinstance(payload.get("entry_candidate_cascade"), dict) else {}
    candidates = [
        cascade.get("reason"),
        cascade.get("top_pick_reason"),
        payload.get("entry_reason"),
        payload.get("entry_exit_reason"),
        payload.get("primary_reason_code"),
    ]
    for value in candidates:
        reason = str(value or "").strip()
        if reason in _ENTRY_COMPATIBILITY_BLOCK_REASONS:
            return reason
    return ""


def _resolve_compatibility_bias_context(state: Dict[str, Any], *, limit: int = 20) -> Dict[str, Any]:
    root = Path.cwd() / "reports" / "canonical" / _resolve_canonical_day(state)
    if not root.exists():
        return {
            "dominant_block_reason": "mixed",
            "dominant_block_reason_ratio": 0.0,
            "bias_scale": 0.10,
            "sample_size": 0,
        }

    monitor_paths = sorted(
        [
            p / "monitor.json"
            for p in root.iterdir()
            if p.is_dir()
            and len(str(p.name)) == 32
            and all(ch in "0123456789abcdefABCDEF" for ch in str(p.name))
            and (p / "monitor.json").exists()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(1, int(limit))]
    reasons: List[str] = []
    for path in monitor_paths:
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reason = _extract_monitor_entry_block_reason(payload)
        if reason:
            reasons.append(reason)

    if not reasons:
        return {
            "dominant_block_reason": "mixed",
            "dominant_block_reason_ratio": 0.0,
            "bias_scale": 0.10,
            "sample_size": 0,
        }

    counter = Counter(reasons)
    top_reason, top_count = counter.most_common(1)[0]
    top_ratio = float(top_count) / float(len(reasons))
    dominant_block_reason = top_reason if top_ratio >= 0.40 else "mixed"
    if dominant_block_reason in {"volume_confirmation_missing", "volume_insufficient"}:
        bias_scale = 0.18 if top_ratio >= 0.60 else 0.15
    elif dominant_block_reason in {"below_vwap_reclaim_not_ready", "pullback_below_vwap_reclaim_not_ready"}:
        bias_scale = 0.16 if top_ratio >= 0.45 else 0.12
    elif dominant_block_reason in {"pullback_not_mature", "breakout_not_ready"}:
        bias_scale = 0.14 if top_ratio >= 0.45 else 0.11
    else:
        bias_scale = 0.10
    return {
        "dominant_block_reason": str(dominant_block_reason),
        "dominant_block_reason_ratio": float(top_ratio if dominant_block_reason != "mixed" else 0.0),
        "bias_scale": float(bias_scale),
        "sample_size": int(len(reasons)),
    }


def _norm01(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return _clamp((float(x) - float(lo)) / (float(hi) - float(lo)), 0.0, 1.0)


def _signed01(x: float, scale: float = 1.0) -> float:
    s = max(1e-9, float(scale))
    return _clamp(float(x) / s, -1.0, 1.0)


def _merge_mock_compatibility_override(
    base: Dict[str, Any],
    *,
    override: Any,
) -> Dict[str, Any]:
    if not isinstance(override, Mapping):
        return dict(base or {})
    merged = dict(base or {})
    for key in (
        "entry_compatibility_score",
        "compatibility_bias",
        "dominant_block_reason_ratio",
        "bias_scale",
        "soft_penalty",
        "compatibility_score_pre_penalty",
        "compatibility_score_post_penalty",
        "vwap_distance_abs",
        "reclaim_proximity",
        "volume_ratio",
        "breakout_gap_pct",
    ):
        if override.get(key) not in (None, ""):
            merged[key] = float(_to_float(override.get(key)))
    for key in (
        "expected_monitor_block_reason",
        "dominant_block_reason",
        "compatibility_source",
        "triggered_path",
    ):
        if override.get(key) not in (None, ""):
            merged[key] = str(override.get(key) or "")
    if override.get("is_below_vwap") is not None:
        merged["is_below_vwap"] = bool(override.get("is_below_vwap"))
    if isinstance(override.get("paths_passed"), list):
        merged["paths_passed"] = list(override.get("paths_passed") or [])
    if isinstance(override.get("compatibility_components"), Mapping):
        merged["compatibility_components"] = dict(override.get("compatibility_components") or {})
    return merged


def _apply_blocker_family_concentration_overlay(
    rows: List[Dict[str, Any]],
    *,
    scan_aggressiveness: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    meta = {
        "applied": False,
        "family": "",
        "penalty": 0.0,
        "candidate_count": 0,
        "top3_symbols_before": [],
        "top3_symbols_after": [],
        "alternative_symbols": [],
        "selection_vetoed": False,
        "selection_veto_reason": "",
    }
    ranked_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    if len(ranked_rows) < 3:
        return ranked_rows, meta

    top3_rows = ranked_rows[:3]
    top3_family_sets = [set(_candidate_blocker_families(row)) for row in top3_rows]
    if any(not family_set for family_set in top3_family_sets):
        return ranked_rows, meta

    common_families = set.intersection(*top3_family_sets) if top3_family_sets else set()
    common_families = {family for family in common_families if family}
    if not common_families:
        return ranked_rows, meta

    family_counter: Counter[str] = Counter()
    for row in ranked_rows:
        for family in _candidate_blocker_families(row):
            family_counter[family] += 1
    concentrated_family = sorted(common_families, key=lambda family: (-family_counter.get(family, 0), family))[0]

    affected_rows = [row for row in ranked_rows if concentrated_family in _candidate_blocker_families(row)]
    alternative_rows = [row for row in ranked_rows if concentrated_family not in _candidate_blocker_families(row)]
    meta.update(
        {
            "applied": True,
            "family": str(concentrated_family),
            "candidate_count": int(len(affected_rows)),
            "top3_symbols_before": [str((row or {}).get("symbol") or "") for row in top3_rows],
            "alternative_symbols": [str((row or {}).get("symbol") or "") for row in alternative_rows[:5]],
        }
    )
    if not alternative_rows:
        meta["selection_vetoed"] = True
        meta["selection_veto_reason"] = "blocker_family_concentration_no_alternative"
        meta["top3_symbols_after"] = list(meta.get("top3_symbols_before") or [])
        return ranked_rows, meta

    third_score = float(_to_float(top3_rows[2].get("score_total") or top3_rows[2].get("score")))
    best_alternative_score = max(
        float(_to_float((row or {}).get("score_total") or (row or {}).get("score")))
        for row in alternative_rows
    )
    base_penalty = 0.04 + min(0.02, max(0.0, float(scan_aggressiveness)))
    required_penalty = max(0.0, third_score - best_alternative_score + 0.001)
    penalty = min(0.15, max(base_penalty, required_penalty))

    adjusted_rows: List[Dict[str, Any]] = []
    for row in ranked_rows:
        row_copy = dict(row)
        families = _candidate_blocker_families(row_copy)
        if concentrated_family in families:
            score_before = float(_to_float(row_copy.get("score_total") or row_copy.get("score")))
            score_after = score_before - penalty
            row_copy["score_total"] = float(score_after)
            row_copy["score"] = float(score_after)
            row_copy["blocker_family_concentration_penalty_applied"] = float(penalty)
            row_copy["blocker_family_concentration_family"] = str(concentrated_family)
        adjusted_rows.append(row_copy)

    adjusted_rows.sort(
        key=lambda r: (
            float(r.get("score_total") or 0.0),
            float(r.get("confidence") or 0.0),
            -float(r.get("risk_score") or 0.0),
        ),
        reverse=True,
    )
    post_top3_rows = adjusted_rows[:3]
    meta["penalty"] = float(penalty)
    meta["top3_symbols_after"] = [str((row or {}).get("symbol") or "") for row in post_top3_rows]
    if len(post_top3_rows) >= 3 and all(
        concentrated_family in _candidate_blocker_families(row) for row in post_top3_rows
    ):
        meta["selection_vetoed"] = True
        meta["selection_veto_reason"] = "blocker_family_concentration_unresolved"
    return adjusted_rows, meta


def scanner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Scanner (Data + feature extraction).

    M17-3 contract (additive):
      - Builds candidate pool from Kiwoom market data (default)
      - Applies strategist theme hints when mapping data exists
      - Falls back to strategist candidates when Kiwoom pool is empty
      - Computes per-candidate features/risk/confidence
      - Selects exactly 1 candidate into state['selected'] (or None)

    Writes:
      - state['scan_results'] : list[dict]
      - state['selected'] : dict | None
      - state['risk'] : dict (risk_score/confidence for selected)

    Test hooks:
      - state['mock_scan_results'] : {symbol: {score, risk_score, confidence, features?}}
        If present, Scanner will use these values instead of generating.
    """
    # M18-4: sentiment-aware scoring (offline-friendly)
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    candidates, pool_meta = _resolve_scanner_candidates(state, policy)
    if _enforce_live_equity_symbols(state, policy):
        candidates, live_symbol_meta = _filter_live_equity_candidates(list(candidates or []))
        pool_meta = dict(pool_meta)
        pool_meta.update(dict(live_symbol_meta))
    run_id = str(state.get("run_id") or "").strip() or "scanner-unknown"

    mock: Optional[Mapping[str, Any]] = state.get("mock_scan_results")  # for tests
    mock_by_sym: Dict[str, Any] = {}
    if isinstance(mock, Mapping):
        for k, v in mock.items():
            mock_by_sym[_norm_symbol(k)] = v

    w = _get_scanner_weights(policy)
    practical_w = _resolve_scanner_score_weights(policy)
    intrinsic_control_w = dict(practical_w)
    scanner_guidance = _extract_scanner_guidance(state)
    playbook = str(scanner_guidance.get("playbook") or "").strip().lower()
    scanner_bias = str(scanner_guidance.get("scanner_bias") or "").strip().lower()
    scanner_bias_context = (
        dict(scanner_guidance.get("scanner_bias_context") or {})
        if isinstance(scanner_guidance.get("scanner_bias_context"), dict)
        else {}
    )
    scanner_memory_bias = (
        dict(scanner_guidance.get("scanner_memory_bias") or {})
        if isinstance(scanner_guidance.get("scanner_memory_bias"), dict)
        else {}
    )
    scanner_priority = _normalize_priority_list(scanner_guidance.get("scanner_priority"))
    trade_aggressiveness = str(scanner_guidance.get("trade_aggressiveness") or "").strip().lower()
    risk_tone = str(scanner_guidance.get("risk_tone") or "").strip().lower()
    monitor_guidance = str(scanner_guidance.get("monitor_guidance") or "").strip().lower()
    strategy_monitor_policy = (
        dict(scanner_guidance.get("monitor_policy") or {})
        if isinstance(scanner_guidance.get("monitor_policy"), dict)
        else {}
    )
    commander_context = (
        dict(scanner_guidance.get("commander_context") or {})
        if isinstance(scanner_guidance.get("commander_context"), dict)
        else {}
    )
    strategist_plan = (
        dict(scanner_guidance.get("strategist_plan") or {})
        if isinstance(scanner_guidance.get("strategist_plan"), dict)
        else {}
    )
    policy_provenance = (
        dict(scanner_guidance.get("policy_provenance") or {})
        if isinstance(scanner_guidance.get("policy_provenance"), dict)
        else {}
    )
    scanner_policy_trace = _build_scanner_policy_trace(
        commander_context=commander_context,
        strategist_plan=strategist_plan,
        policy_provenance=policy_provenance,
        playbook=playbook,
        scanner_priority=scanner_priority,
        scanner_bias=scanner_bias,
        scanner_bias_context=scanner_bias_context,
        scanner_memory_bias=scanner_memory_bias,
    )
    if isinstance(scanner_guidance.get("score_weights"), dict):
        for key, value in dict(scanner_guidance.get("score_weights") or {}).items():
            if key in practical_w and value not in (None, ""):
                practical_w[key] = _to_float(value)
    practical_w = _apply_scanner_guidance_weights(
        practical_w,
        playbook=playbook,
        scanner_bias=scanner_bias,
        scanner_priority=scanner_priority,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    state = _maybe_hydrate_scanner_skill_results(state, list(candidates))
    skill_quotes, quote_meta = _extract_skill_quotes(state)
    skill_order_counts, skill_order_rows, order_meta = _extract_account_open_order_counts(state)
    quote_metric_coverage = _summarize_quote_metric_coverage(list(candidates), skill_quotes=skill_quotes, state=state)
    refresh_existing_features, feature_refresh_reason = _should_refresh_scanner_features(
        state=state,
        candidates=list(candidates),
        quote_metric_coverage=quote_metric_coverage,
    )
    feature_map, feature_source, feature_errors = hydrate_scanner_feature_map(
        state=state,
        candidates=list(candidates),
        skill_quotes=skill_quotes,
        policy=policy,
        refresh_existing=refresh_existing_features,
    )
    if not feature_map:
        feature_map, feature_source, feature_errors = _extract_feature_engine_map(state)
    minute_rows_by_symbol, minute_rows_meta = extract_minute_ohlcv_by_symbol(state)
    ohlcv_by_symbol = state.get("ohlcv_by_symbol") if isinstance(state.get("ohlcv_by_symbol"), dict) else {}
    compatibility_bias_context = _resolve_compatibility_bias_context(state)
    compatibility_policy_input = _build_scanner_monitor_policy_input(
        state=state,
        commander_context=commander_context,
        monitor_policy=strategy_monitor_policy,
    )
    compatibility_frame = _build_scanner_monitor_frame(
        playbook=playbook,
        monitor_guidance=monitor_guidance,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
    )
    compatibility_policy = (
        resolve_intraday_entry_policy(compatibility_policy_input or None, frame=compatibility_frame or None)
        if compatibility_policy_input
        else None
    )
    state["scanner_quote_diagnostic"] = {
        **dict(quote_metric_coverage),
        "feature_refresh_forced": bool(refresh_existing_features),
        "feature_refresh_reason": str(feature_refresh_reason or ""),
        "feature_source": str(feature_source or ""),
        "minute_rows_source": str(minute_rows_meta.get("source") or "") if isinstance(minute_rows_meta, dict) else "",
    }
    gs = _get_global_sentiment_score(state)
    gs_signal = _get_global_sentiment_signal(state)
    news_by_sym = _get_news_sentiment_map(state)
    news_signal_by_sym = _get_news_sentiment_signal_map(state)
    try:
        raw_candidates = []
        for item in list(candidates)[:50]:
            if isinstance(item, dict):
                raw_candidates.append(
                    {
                        "symbol": _norm_symbol(item.get("symbol")),
                        "why": str(item.get("why") or ""),
                        "sources": list(item.get("sources") or [])[:5],
                        "rank_score": _to_float(item.get("rank_score") or 0.0),
                    }
                )
            else:
                raw_candidates.append({"symbol": _norm_symbol(item), "why": "raw_candidate"})
        record_raw_input(
            run_id=run_id,
            agent="scanner",
            stage="symbol_selection",
            raw_input={
                "candidate_pool_before_filter": int(len(candidates)),
                "candidates": raw_candidates,
                "candidate_source": str(pool_meta.get("candidate_source") or ""),
                "strategist_guidance": {
                    "themes": list(scanner_guidance.get("themes") or []),
                    "selected_themes": list(scanner_guidance.get("selected_themes") or []),
                    "avoid_themes": list(scanner_guidance.get("avoid_themes") or []),
                    "playbook": playbook,
                    "scanner_bias": scanner_bias,
                    "scanner_bias_context": dict(scanner_policy_trace.get("scanner_bias_context") or {}),
                    "scanner_priority": list(scanner_priority),
                    "scanner_source_policy": dict(scanner_guidance.get("scanner_source_policy") or {}),
                    "trade_aggressiveness": trade_aggressiveness,
                    "risk_tone": risk_tone,
                    "theme_source": str(scanner_guidance.get("theme_source") or ""),
                    "theme_source_status": str(scanner_guidance.get("theme_source_status") or ""),
                    "available_themes": list(scanner_guidance.get("available_themes") or [])[:8],
                    "theme_strategy": dict(scanner_guidance.get("theme_strategy") or {})
                    if isinstance(scanner_guidance.get("theme_strategy"), dict)
                    else {},
                    "theme_strength_packet_summary": {
                        "source": str((scanner_guidance.get("theme_strength_packet") or {}).get("source") or "")
                        if isinstance(scanner_guidance.get("theme_strength_packet"), dict)
                        else "",
                        "status": str((scanner_guidance.get("theme_strength_packet") or {}).get("status") or "")
                        if isinstance(scanner_guidance.get("theme_strength_packet"), dict)
                        else "",
                        "top_themes": list((scanner_guidance.get("theme_strength_packet") or {}).get("top_themes") or [])[:5]
                        if isinstance(scanner_guidance.get("theme_strength_packet"), dict)
                        else [],
                    },
                },
                "commander_context": scanner_policy_trace.get("commander_priority_ref"),
                "strategist_plan": scanner_policy_trace.get("strategist_constraints_ref"),
                "global_sentiment_score": float(gs),
                "feature_source": str(feature_source),
                "feature_symbol_count": int(len(feature_map)),
                "feature_errors": list(feature_errors),
                "quote_metric_coverage": dict(quote_metric_coverage),
                "feature_refresh_forced": bool(refresh_existing_features),
                "feature_refresh_reason": str(feature_refresh_reason or ""),
            },
            decision_link={"stage": "scanner_candidate_retrieval"},
        )
    except Exception:
        pass

    asset_filtered_candidates, asset_policy_meta = apply_asset_universe_filter(
        candidates,
        state=state,
        policy=policy,
        market_quotes=skill_quotes,
        allow_remote_lookup=True,
    )
    if int(asset_policy_meta.get("asset_policy_excluded_count") or 0) > 0:
        if not asset_filtered_candidates and not str((pool_meta or {}).get("fallback_reason") or "").strip():
            pool_meta = dict(pool_meta)
            pool_meta["fallback_reason"] = "asset_policy_filtered_all_candidates"
        _emit_scanner_event(
            state,
            name="asset_policy_exclusions",
            payload={
                "asset_universe_policy": str(asset_policy_meta.get("asset_universe_policy") or ""),
                "asset_universe_policy_source": str(asset_policy_meta.get("asset_universe_policy_source") or ""),
                "excluded_candidate_count": int(asset_policy_meta.get("asset_policy_excluded_count") or 0),
                "excluded_symbols": list(asset_policy_meta.get("asset_policy_excluded_symbols") or []),
                "exclusions": list(asset_policy_meta.get("asset_policy_exclusions") or []),
                "asset_detection_stats": dict(asset_policy_meta.get("asset_detection_stats") or {}),
                "unknown_asset_candidate_count": int(asset_policy_meta.get("unknown_asset_candidate_count") or 0),
                "total_candidates_before_filter": int(asset_policy_meta.get("total_candidates_before_filter") or 0),
                "total_candidates_after_filter": int(asset_policy_meta.get("total_candidates_after_filter") or 0),
            },
        )
    candidates = list(asset_filtered_candidates)
    pool_meta = dict(pool_meta)
    pool_meta.update(dict(asset_policy_meta))

    restricted_filtered_candidates, restricted_meta = _filter_mock_broker_restricted_candidates(
        candidates,
        state=state,
    )
    candidates = list(restricted_filtered_candidates)
    pool_meta.update(dict(restricted_meta))
    if int(restricted_meta.get("mock_broker_restricted_excluded_count") or 0) > 0:
        _emit_scanner_event(
            state,
            name="mock_broker_restricted_symbol_exclusions",
            payload={
                "excluded_candidate_count": int(restricted_meta.get("mock_broker_restricted_excluded_count") or 0),
                "excluded_symbols": list(restricted_meta.get("mock_broker_restricted_excluded_symbols") or []),
                "exclusions": list(restricted_meta.get("mock_broker_restricted_exclusions") or []),
                "candidate_pool_after_filter": int(restricted_meta.get("candidate_pool_after_mock_broker_restricted_filter") or 0),
            },
        )

    # Practical pool reduction before scoring.
    reduced_candidates, reduction_meta = _reduce_candidates_by_practical_filters(
        candidates,
        state=state,
        policy=policy,
        skill_quotes=skill_quotes,
    )
    candidates = list(reduced_candidates)
    pool_meta.update(dict(reduction_meta))
    state["scanner_candidate_pool"] = dict(pool_meta)
    practical_enabled = str(pool_meta.get("candidate_source") or "").strip().lower() == "kiwoom_market_data"
    if policy.get("enable_practical_scoring") is not None:
        practical_enabled = _is_trueish(policy.get("enable_practical_scoring"))
    practical_scale = 1.0 if practical_enabled else 0.0

    scan_results: List[Dict[str, Any]] = []
    symbol_priors = _load_symbol_priors(state, candidates)

    for item in candidates:
        candidate_meta: Dict[str, Any] = {}
        if isinstance(item, dict):
            symbol = _norm_symbol(item.get("symbol"))
            candidate_meta = dict(item)
        else:
            symbol = _norm_symbol(item)

        if not symbol:
            continue

        if symbol in mock_by_sym:
            row = dict(mock_by_sym[symbol])
            row.setdefault("symbol", symbol)
        else:
            base = _stable_unit_hash(symbol)
            # Simple deterministic defaults (placeholder)
            score = 1.0 - base  # higher is better
            risk_score = base  # higher is riskier
            confidence = max(0.0, min(1.0, 0.9 - base * 0.4))
            row = {
                "symbol": symbol,
                "score": float(score),
                "risk_score": float(risk_score),
                "confidence": float(confidence),
                "features": {
                    "unit_hash": float(base),
                },
            }

        # ---- Practical scoring model (additive, deterministic) ----
        base_score = _to_float(row.get("score") or 0.0)
        base_risk = _to_float(row.get("risk_score") or 0.35)
        base_conf = _to_float(row.get("confidence") or 0.55)
        row["raw_score"] = float(base_score)
        row["base_score"] = float(base_score)
        candidate_rank_score = _clamp(_to_float(candidate_meta.get("rank_score") or 0.0), -1.0, 1.0)
        candidate_universe_score = _clamp(_to_float(candidate_meta.get("universe_score") or 0.0), 0.0, 10.0)
        source_scores = dict(candidate_meta.get("source_scores") or {})

        news_s = _to_float(news_by_sym.get(symbol, news_by_sym.get(_norm_symbol(symbol), 0.0)))
        news_sig = (
            news_signal_by_sym.get(symbol)
            if isinstance(news_signal_by_sym.get(symbol), dict)
            else news_signal_by_sym.get(_norm_symbol(symbol), {})
        )
        metrics = _candidate_quote_metrics(symbol, skill_quotes=skill_quotes, state=state)
        quote = skill_quotes.get(_norm_symbol(symbol), {}) if isinstance(skill_quotes.get(_norm_symbol(symbol)), dict) else {}
        quote_price = quote.get("price")
        if quote_price is None:
            quote_price = quote.get("cur")
        quote_price_num = _to_float(quote_price) if quote_price is not None else None
        deviation_signal = extract_etf_deviation_signal(
            symbol=symbol,
            candidate={**dict(candidate_meta), **dict(row if isinstance(row, dict) else {})},
            features=feature_map.get(_norm_symbol(symbol), {}) if isinstance(feature_map.get(_norm_symbol(symbol)), dict) else {},
            quote=quote,
            state=state,
            asset_class_detected=(
                candidate_meta.get("asset_class_detected")
                or (row.get("asset_class_detected") if isinstance(row, dict) else "")
            ),
        )
        etf_deviation_tradeable = bool(
            deviation_signal.get("is_etf_family")
            or deviation_signal.get("available")
        )
        etf_deviation_entry_score = (
            float(deviation_signal.get("entry_discount_score") or 0.0)
            if etf_deviation_tradeable
            else 0.0
        )
        etf_deviation_premium_score = (
            float(deviation_signal.get("exit_premium_score") or 0.0)
            if etf_deviation_tradeable
            else 0.0
        )
        etf_deviation_bias = float((0.08 * etf_deviation_entry_score) - (0.08 * etf_deviation_premium_score))
        open_orders = int(skill_order_counts.get(_norm_symbol(symbol), 0))
        order_penalty = min(open_orders, 3)

        feature_row = feature_map.get(_norm_symbol(symbol), {})
        if not isinstance(feature_row, dict):
            feature_row = {}
        feature_signal = _clamp(_to_float(feature_row.get("signal_score") or 0.0), -1.0, 1.0)
        feature_regime = str(feature_row.get("regime") or "").strip().lower()
        return20 = _to_float(feature_row.get("return20"))
        ma20_gap = _to_float(feature_row.get("ma20_gap"))
        ma60_gap = _to_float(feature_row.get("ma60_gap"))
        ma120_gap = _to_float(feature_row.get("ma120_gap"))
        trend_strength = _to_float(feature_row.get("trend_strength"))
        adx14 = _to_float(feature_row.get("adx14"))
        volume_spike20 = _to_float(feature_row.get("volume_spike20"))
        volatility20 = _to_float(feature_row.get("volatility20"))
        vwap_distance = _to_float(feature_row.get("vwap_distance"))
        cross_section_rank = _to_float(feature_row.get("cross_section_rank"))
        gap_pct = abs(_to_float(feature_row.get("gap_pct")))

        trading_value_component = _norm01(_to_float(source_scores.get("top_value")), 0.0, 2.0)
        momentum_raw = (0.65 * _signed01(return20, 0.10)) + (0.35 * _signed01(ma20_gap, 0.03))
        momentum_component = max(0.0, momentum_raw)
        ma_alignment_component = max(
            0.0,
            (
                0.45 * _signed01(ma20_gap, 0.03)
                + 0.35 * _signed01(ma60_gap, 0.05)
                + 0.20 * _signed01(ma120_gap, 0.08)
            ),
        )
        adx_component = _norm01(adx14, 15.0, 35.0)
        trend_raw = trend_strength if trend_strength != 0.0 else feature_signal
        trend_component = max(
            0.0,
            (
                0.45 * max(0.0, _signed01(trend_raw, 1.0))
                + 0.35 * ma_alignment_component
                + 0.20 * adx_component
            ),
        )
        volume_surge_component = _norm01(volume_spike20, 1.0, 3.0)
        vwap_alignment_component = max(0.0, _signed01(vwap_distance, 0.02))
        intraday_strength_component = max(
            0.0,
            (
                0.70 * max(0.0, _signed01(_to_float(metrics.get("change_pct")), 5.0))
                + 0.30 * vwap_alignment_component
            ),
        )
        cross_section_rank_component = _norm01(cross_section_rank, 0.0, 1.0)

        theme_matched_symbols = set(_norm_symbol(x) for x in list(pool_meta.get("theme_matched_symbols") or []))
        avoid_theme_symbols = set(_norm_symbol(x) for x in list(pool_meta.get("avoid_matched_symbols") or []))
        theme_boost_component = 1.0 if (symbol in theme_matched_symbols and len(theme_matched_symbols) > 0) else 0.0
        sentiment_component = max(0.0, (0.7 * news_s) + (0.3 * gs))

        volatility_penalty = _norm01(volatility20, 0.03, 0.08)
        gap_penalty = _norm01(gap_pct, 0.03, 0.10)
        open_order_penalty = _norm01(float(order_penalty), 0.0, 3.0)
        avoid_theme_penalty = 1.0 if (symbol in avoid_theme_symbols and len(avoid_theme_symbols) > 0) else 0.0

        repeat_penalty_meta = _repeat_symbol_penalty(state, symbol=symbol, policy=policy)
        repeat_symbol_penalty = _to_float(repeat_penalty_meta.get("penalty"))
        blocker_penalty_meta = _repeat_blocker_cooldown_penalty(state, symbol=symbol, policy=policy)
        repeat_blocker_penalty = _to_float(blocker_penalty_meta.get("penalty"))

        positive_score = (
            practical_w["trading_value"] * trading_value_component
            + practical_w["momentum"] * momentum_component
            + practical_w["trend"] * trend_component
            + practical_w["volume_surge"] * volume_surge_component
            + practical_w["intraday_strength"] * intraday_strength_component
            + practical_w["theme_boost"] * theme_boost_component
            + practical_w["sentiment"] * sentiment_component
            + (0.06 * max(0.0, candidate_rank_score))
            + (0.02 * _norm01(candidate_universe_score, 0.0, 10.0))
            + (0.05 * cross_section_rank_component)
        ) * practical_scale
        risk_penalty_score = (
            practical_w["volatility_penalty"] * volatility_penalty
            + practical_w["gap_penalty"] * gap_penalty
            + practical_w["open_order_penalty"] * open_order_penalty
            + (0.20 * avoid_theme_penalty)
        ) * practical_scale

        # Keep backward compatibility with previous additive sentiment/risk knobs.
        legacy_adjust = (
            w["weight_news"] * news_s
            + w["weight_global"] * gs
            + w["feature_score_weight"] * feature_signal
            - (0.03 * open_order_penalty)
        )
        rank_bonus = 0.01 * max(0.0, candidate_rank_score)
        intrinsic_control_positive = (
            intrinsic_control_w["trading_value"] * trading_value_component
            + intrinsic_control_w["momentum"] * momentum_component
            + intrinsic_control_w["trend"] * trend_component
            + intrinsic_control_w["volume_surge"] * volume_surge_component
            + intrinsic_control_w["intraday_strength"] * intraday_strength_component
            + intrinsic_control_w["sentiment"] * sentiment_component
            + (0.06 * max(0.0, candidate_rank_score))
            + (0.02 * _norm01(candidate_universe_score, 0.0, 10.0))
            + (0.05 * cross_section_rank_component)
        ) * practical_scale
        intrinsic_control_risk = (
            intrinsic_control_w["volatility_penalty"] * volatility_penalty
            + intrinsic_control_w["gap_penalty"] * gap_penalty
            + intrinsic_control_w["open_order_penalty"] * open_order_penalty
        ) * practical_scale
        bias_result = _compute_structured_scanner_bias(
            symbol=symbol,
            feature_row=feature_row,
            metrics=metrics,
            bias_context=scanner_bias_context,
        )
        scanner_bias_adjustment = float(bias_result.get("bias_adjustment") or 0.0)
        memory_bias_result = compute_scanner_memory_bias_adjustment(
            symbol=symbol,
            candidate_sources=list(candidate_meta.get("sources") or []),
            memory_bias=scanner_memory_bias,
        )
        scanner_memory_bias_observed_adjustment = float(memory_bias_result.get("bias_adjustment") or 0.0)
        scanner_memory_bias_observation_only = _memory_bias_observation_only(state)
        scanner_memory_bias_adjustment = 0.0 if scanner_memory_bias_observation_only else scanner_memory_bias_observed_adjustment
        candidate_rows = []
        raw_minute_rows = minute_rows_by_symbol.get(_norm_symbol(symbol)) if isinstance(minute_rows_by_symbol, dict) else None
        if isinstance(raw_minute_rows, list) and raw_minute_rows:
            candidate_rows = list(raw_minute_rows)
        else:
            raw_ohlcv_rows = ohlcv_by_symbol.get(_norm_symbol(symbol)) if isinstance(ohlcv_by_symbol.get(_norm_symbol(symbol)), list) else []
            if raw_ohlcv_rows:
                candidate_rows = list(raw_ohlcv_rows)
        compatibility_result = _compute_entry_compatibility_signal(
            symbol=symbol,
            feature_row=feature_row,
            metrics=metrics,
            candidate_rows=candidate_rows,
            current_price=quote_price_num or feature_row.get("close_last"),
            policy=compatibility_policy,
            bias_context=compatibility_bias_context,
        )
        mock_row = mock_by_sym.get(symbol) if isinstance(mock_by_sym.get(symbol), Mapping) else {}
        mock_compatibility_override = mock_row.get("compatibility_override") if isinstance(mock_row.get("compatibility_override"), Mapping) else {}
        if not mock_compatibility_override and isinstance(mock_row, Mapping):
            top_level_override = {
                key: mock_row.get(key)
                for key in (
                    "entry_compatibility_score",
                    "compatibility_bias",
                    "expected_monitor_block_reason",
                    "dominant_block_reason",
                    "dominant_block_reason_ratio",
                    "bias_scale",
                    "soft_penalty",
                    "compatibility_score_pre_penalty",
                    "compatibility_score_post_penalty",
                )
                if mock_row.get(key) not in (None, "")
            }
            if top_level_override:
                mock_compatibility_override = top_level_override
        compatibility_result = _merge_mock_compatibility_override(
            compatibility_result,
            override=mock_compatibility_override,
        )
        compatibility_bias = float(compatibility_result.get("compatibility_bias") or 0.0)
        macro_chart_fit = _compute_scanner_macro_chart_fit(
            feature_row=feature_row,
            ma_alignment_component=ma_alignment_component,
            trend_component=trend_component,
            adx_component=adx_component,
            momentum_component=momentum_component,
            volume_surge_component=volume_surge_component,
            vwap_alignment_component=vwap_alignment_component,
            cross_section_rank_component=cross_section_rank_component,
            volatility_penalty=volatility_penalty,
            gap_penalty=gap_penalty,
            playbook=playbook,
            scanner_priority=scanner_priority,
            risk_tone=risk_tone,
            trade_aggressiveness=trade_aggressiveness,
        )
        scanner_macro_chart_fit_bias = float(
            macro_chart_fit.get("scanner_macro_chart_fit_bias") or 0.0
        )
        symbol_prior_result = _compute_symbol_prior_adjustment(
            symbol_model=dict(symbol_priors.get(symbol) or {}),
            playbook=playbook,
            current_day=_resolve_canonical_day(state),
        )
        symbol_prior_adjustment = float(symbol_prior_result.get("adjustment") or 0.0)
        scanner_intrinsic_control_score_total = (
            base_score
            + intrinsic_control_positive
            + legacy_adjust
            - intrinsic_control_risk
            + rank_bonus
            - repeat_symbol_penalty
            - repeat_blocker_penalty
            + scanner_memory_bias_adjustment
            + symbol_prior_adjustment
            + etf_deviation_bias
        )
        pre_adjust_score_total = (
            base_score
            + positive_score
            + legacy_adjust
            - risk_penalty_score
            + rank_bonus
            - repeat_symbol_penalty
            - repeat_blocker_penalty
            + scanner_bias_adjustment
            + scanner_memory_bias_adjustment
            + symbol_prior_adjustment
            + etf_deviation_bias
        )
        score_total = pre_adjust_score_total + compatibility_bias + scanner_macro_chart_fit_bias

        neg_news = max(-news_s, 0.0)
        neg_global = max(-gs, 0.0)
        feature_risk = w["feature_risk_penalty"] * max(-feature_signal, 0.0)
        if feature_regime == "high_volatility":
            feature_risk += w["high_vol_risk_penalty"]
        adj_risk = (
            base_risk
            + w["risk_news_penalty"] * neg_news
            + w["risk_global_penalty"] * neg_global
            + feature_risk
            + (0.35 * volatility_penalty * practical_scale)
            + (0.25 * gap_penalty * practical_scale)
            + (0.10 * open_order_penalty)
        )
        if etf_deviation_tradeable and etf_deviation_premium_score > 0.0:
            adj_risk += 0.05 * etf_deviation_premium_score
        if etf_deviation_tradeable and etf_deviation_entry_score > 0.0:
            adj_risk -= 0.03 * etf_deviation_entry_score
        adj_conf = _clamp(
            base_conf
            + w["confidence_news_boost"] * max(news_s, 0.0)
            + 0.15 * (positive_score - risk_penalty_score)
            - 0.08 * open_order_penalty,
            0.0,
            1.0,
        )
        if etf_deviation_tradeable and etf_deviation_entry_score > 0.0:
            adj_conf = _clamp(adj_conf + (0.05 * etf_deviation_entry_score), 0.0, 1.0)
        if etf_deviation_tradeable and etf_deviation_premium_score > 0.0:
            adj_conf = _clamp(adj_conf - (0.04 * etf_deviation_premium_score), 0.0, 1.0)
        if repeat_symbol_penalty > 0.0:
            adj_conf = _clamp(adj_conf - (0.40 * repeat_symbol_penalty), 0.0, 1.0)
            adj_risk = _clamp(adj_risk + (0.25 * repeat_symbol_penalty), 0.0, 1.0)
        if repeat_blocker_penalty > 0.0:
            adj_conf = _clamp(adj_conf - (0.35 * repeat_blocker_penalty), 0.0, 1.0)
            adj_risk = _clamp(adj_risk + (0.20 * repeat_blocker_penalty), 0.0, 1.0)
        adj_conf = _clamp(adj_conf + float(symbol_prior_result.get("confidence_delta") or 0.0), 0.0, 1.0)
        adj_risk = _clamp(adj_risk + float(symbol_prior_result.get("risk_delta") or 0.0), 0.0, 1.0)

        score_breakdown = {
            "trading_value": float(practical_w["trading_value"] * trading_value_component),
            "momentum": float(practical_w["momentum"] * momentum_component),
            "trend": float(practical_w["trend"] * trend_component),
            "ma_alignment": float(practical_w["trend"] * 0.35 * ma_alignment_component),
            "adx_trend": float(practical_w["trend"] * 0.20 * adx_component),
            "volume_surge": float(practical_w["volume_surge"] * volume_surge_component),
            "intraday_strength": float(practical_w["intraday_strength"] * intraday_strength_component),
            "vwap_alignment": float(practical_w["intraday_strength"] * 0.30 * vwap_alignment_component),
            "theme_boost": float(practical_w["theme_boost"] * theme_boost_component),
            "sentiment": float(practical_w["sentiment"] * sentiment_component),
            "cross_section_rank": float(0.05 * cross_section_rank_component * practical_scale),
            "avoid_theme_penalty": float(-0.20 * avoid_theme_penalty * practical_scale),
            "repeat_symbol_penalty": float(-repeat_symbol_penalty),
            "repeat_blocker_penalty": float(-repeat_blocker_penalty),
            "scanner_bias": float(scanner_bias_adjustment),
            "scanner_memory_bias": float(scanner_memory_bias_adjustment),
            "scanner_memory_bias_observed": float(scanner_memory_bias_observed_adjustment),
            "symbol_prior": float(symbol_prior_adjustment),
            "etf_deviation_bias": float(etf_deviation_bias),
            "entry_compatibility_bias": float(compatibility_bias),
            "scanner_macro_chart_fit_bias": float(scanner_macro_chart_fit_bias),
            "risk_penalty": float(-risk_penalty_score),
            "rank_bonus": float(rank_bonus),
        }

        row["score"] = float(score_total)
        row["score_total"] = float(score_total)
        row["score_breakdown"] = dict(score_breakdown)
        row["bias_adjustment"] = float(scanner_bias_adjustment)
        row["bias_adjustments"] = list(bias_result.get("bias_adjustments") or [])
        row["bias_summary"] = dict(bias_result.get("bias_summary") or {})
        row["memory_bias_adjustment"] = float(scanner_memory_bias_adjustment)
        row["memory_bias_observed_adjustment"] = float(scanner_memory_bias_observed_adjustment)
        row["memory_bias_observation_only"] = bool(scanner_memory_bias_observation_only)
        row["memory_bias_source_delta"] = float(memory_bias_result.get("source_delta") or 0.0)
        row["memory_bias_symbol_delta"] = float(memory_bias_result.get("symbol_delta") or 0.0)
        row["memory_bias_adjustments"] = list(memory_bias_result.get("adjustments") or [])
        row["memory_bias_summary"] = dict(memory_bias_result.get("summary") or {})
        row["symbol_prior_adjustment"] = float(symbol_prior_adjustment)
        row["symbol_prior_reasons"] = list(symbol_prior_result.get("reasons") or [])
        row["symbol_prior_summary"] = dict(symbol_prior_result.get("summary") or {})
        row["etf_deviation_pct"] = deviation_signal.get("etf_deviation_pct")
        row["etf_deviation_source"] = str(deviation_signal.get("etf_deviation_source") or "")
        row["etf_deviation_available"] = bool(deviation_signal.get("available"))
        row["etf_deviation_entry_score"] = float(etf_deviation_entry_score)
        row["etf_deviation_premium_score"] = float(etf_deviation_premium_score)
        row["etf_deviation_bias"] = float(etf_deviation_bias)
        row["entry_compatibility_score"] = float(compatibility_result.get("entry_compatibility_score") or 0.0)
        row["compatibility_bias"] = float(compatibility_bias)
        row["compatibility_components"] = dict(compatibility_result.get("compatibility_components") or {})
        row["scanner_chart_fit_score"] = float(_to_float(compatibility_result.get("scanner_chart_fit_score")))
        row["scanner_chart_fit_authority"] = str(compatibility_result.get("scanner_chart_fit_authority") or "")
        row["scanner_chart_fit_components"] = dict(compatibility_result.get("scanner_chart_fit_components") or {})
        row["scanner_chart_fit_penalty"] = float(_to_float(compatibility_result.get("scanner_chart_fit_penalty")))
        row["scanner_macro_chart_fit_score"] = float(
            _to_float(macro_chart_fit.get("scanner_macro_chart_fit_score"), 0.5)
        )
        row["scanner_macro_chart_fit_bias"] = float(scanner_macro_chart_fit_bias)
        row["scanner_macro_chart_fit_authority"] = str(
            macro_chart_fit.get("scanner_macro_chart_fit_authority") or ""
        )
        row["scanner_macro_chart_fit_components"] = dict(
            macro_chart_fit.get("scanner_macro_chart_fit_components") or {}
        )
        row["scanner_macro_chart_fit_focus"] = dict(
            macro_chart_fit.get("scanner_macro_chart_fit_focus") or {}
        )
        row["expected_monitor_block_reason"] = str(compatibility_result.get("expected_monitor_block_reason") or "")
        row["dominant_block_reason"] = str(compatibility_result.get("dominant_block_reason") or "")
        row["dominant_block_reason_ratio"] = float(_to_float(compatibility_result.get("dominant_block_reason_ratio")))
        row["bias_scale"] = float(_to_float(compatibility_result.get("bias_scale")))
        row["soft_penalty"] = float(_to_float(compatibility_result.get("soft_penalty")))
        row["compatibility_score_pre_penalty"] = float(_to_float(compatibility_result.get("compatibility_score_pre_penalty")))
        row["compatibility_score_post_penalty"] = float(_to_float(compatibility_result.get("compatibility_score_post_penalty")))
        row["compatibility_trace"] = dict(compatibility_result)
        row["pre_adjust_score_total"] = float(pre_adjust_score_total)
        row["post_adjust_score_total"] = float(score_total)
        row["scanner_intrinsic_control_score_total"] = float(
            scanner_intrinsic_control_score_total
        )
        row["risk_score"] = float(_clamp(adj_risk, 0.0, 1.0))
        row["confidence"] = float(adj_conf)
        row["why"] = str(candidate_meta.get("why") or row.get("why") or "")
        row["asset_class_detected"] = str(candidate_meta.get("asset_class_detected") or "")
        row["detection_source"] = str(candidate_meta.get("detection_source") or "")
        row["detection_field"] = str(candidate_meta.get("detection_field") or "")
        row["excluded_by_asset_policy"] = bool(candidate_meta.get("excluded_by_asset_policy"))
        row["exclusion_reason"] = str(candidate_meta.get("exclusion_reason") or "")
        row["candidate"] = {
            "source_why": str(candidate_meta.get("why") or ""),
            "sources": list(candidate_meta.get("sources") or []),
            "rank_score": float(candidate_rank_score),
            "universe_score": float(candidate_universe_score),
            "source_scores": dict(candidate_meta.get("source_scores") or {}),
            "source_count": int(candidate_meta.get("source_count") or len(list(candidate_meta.get("sources") or []))),
            "asset_class_detected": str(candidate_meta.get("asset_class_detected") or ""),
            "detection_source": str(candidate_meta.get("detection_source") or ""),
            "detection_field": str(candidate_meta.get("detection_field") or ""),
            "excluded_by_asset_policy": bool(candidate_meta.get("excluded_by_asset_policy")),
            "exclusion_reason": str(candidate_meta.get("exclusion_reason") or ""),
        }
        row.setdefault("features", {})
        if isinstance(row.get("features"), dict):
            row["features"].update(
                {
                    "skill_quote_price": quote_price_num,
                    "skill_open_orders": open_orders,
                    "skill_open_orders_pending_only": True,
                    "quote_best_bid": _to_float(metrics.get("best_bid")),
                    "quote_best_ask": _to_float(metrics.get("best_ask")),
                    "quote_spread_bps": metrics.get("spread_bps"),
                    "etf_deviation_pct": deviation_signal.get("etf_deviation_pct"),
                    "etf_deviation_source": str(deviation_signal.get("etf_deviation_source") or ""),
                    "etf_deviation_available": bool(deviation_signal.get("available")),
                    "etf_deviation_entry_score": float(etf_deviation_entry_score),
                    "etf_deviation_premium_score": float(etf_deviation_premium_score),
                    "asset_class_detected": str(
                        deviation_signal.get("asset_class_detected")
                        or candidate_meta.get("asset_class_detected")
                        or ""
                    ),
                    "engine_rsi14": feature_row.get("rsi14"),
                    "engine_ma20_gap": feature_row.get("ma20_gap"),
                    "engine_ma60": feature_row.get("ma60"),
                    "engine_ma120": feature_row.get("ma120"),
                    "engine_adx14": feature_row.get("adx14"),
                    "engine_trend_strength": feature_row.get("trend_strength"),
                    "engine_atr14": feature_row.get("atr14"),
                    "engine_volume_spike20": feature_row.get("volume_spike20"),
                    "engine_volatility20": feature_row.get("volatility20"),
                    "engine_realized_volatility": feature_row.get("realized_volatility"),
                    "engine_vwap_distance": feature_row.get("vwap_distance"),
                    "engine_rolling_drawdown20": feature_row.get("rolling_drawdown20"),
                    "engine_sector_relative_strength": feature_row.get("sector_relative_strength"),
                    "engine_cross_section_rank": feature_row.get("cross_section_rank"),
                    "engine_regime": feature_row.get("regime"),
                    "engine_signal_score": feature_signal,
                    "intraday_change_pct": _to_float(metrics.get("change_pct")),
                    "quote_trading_value": _to_float(metrics.get("trading_value")),
                    "quote_volume": _to_float(metrics.get("volume")),
                    "entry_compatibility_score": compatibility_result.get("entry_compatibility_score"),
                    "compatibility_bias": compatibility_result.get("compatibility_bias"),
                    "compatibility_components": dict(compatibility_result.get("compatibility_components") or {}),
                    "scanner_chart_fit_score": compatibility_result.get("scanner_chart_fit_score"),
                    "scanner_chart_fit_authority": compatibility_result.get("scanner_chart_fit_authority"),
                    "scanner_chart_fit_components": dict(compatibility_result.get("scanner_chart_fit_components") or {}),
                    "scanner_macro_chart_fit_score": macro_chart_fit.get("scanner_macro_chart_fit_score"),
                    "scanner_macro_chart_fit_bias": scanner_macro_chart_fit_bias,
                    "scanner_macro_chart_fit_authority": macro_chart_fit.get("scanner_macro_chart_fit_authority"),
                    "scanner_macro_chart_fit_components": dict(
                        macro_chart_fit.get("scanner_macro_chart_fit_components") or {}
                    ),
                    "compatibility_source": compatibility_result.get("compatibility_source"),
                    "compat_vwap_distance_abs": compatibility_result.get("vwap_distance_abs"),
                    "compat_is_below_vwap": compatibility_result.get("is_below_vwap"),
                    "compat_reclaim_proximity": compatibility_result.get("reclaim_proximity"),
                    "compat_volume_ratio": compatibility_result.get("volume_ratio"),
                    "compat_breakout_gap_pct": compatibility_result.get("breakout_gap_pct"),
                }
            )
        row.setdefault("components", {})
        if isinstance(row.get("components"), dict):
            row["components"].update(
                {
                    "base_score": base_score,
                    "base_risk": base_risk,
                    "base_confidence": base_conf,
                    "news_sentiment": news_s,
                    "global_sentiment": gs,
                    "weight_news": w["weight_news"],
                    "weight_global": w["weight_global"],
                    "risk_news_penalty": w["risk_news_penalty"],
                    "risk_global_penalty": w["risk_global_penalty"],
                    "feature_signal": feature_signal,
                    "feature_regime": feature_regime,
                    "feature_score_weight": w["feature_score_weight"],
                    "feature_risk_penalty": w["feature_risk_penalty"],
                    "high_vol_risk_penalty": w["high_vol_risk_penalty"],
                    "practical_positive_score": float(positive_score),
                    "practical_risk_penalty_score": float(risk_penalty_score),
                    "skill_open_orders": open_orders,
                    "candidate_rank_score": candidate_rank_score,
                    "candidate_universe_score": candidate_universe_score,
                    "trading_value_component": trading_value_component,
                    "momentum_component": momentum_component,
                    "trend_component": trend_component,
                    "ma_alignment_component": ma_alignment_component,
                    "adx_component": adx_component,
                    "volume_surge_component": volume_surge_component,
                    "intraday_strength_component": intraday_strength_component,
                    "vwap_alignment_component": vwap_alignment_component,
                    "cross_section_rank_component": cross_section_rank_component,
                    "theme_boost_component": theme_boost_component,
                    "sentiment_component": sentiment_component,
                    "volatility_penalty_component": volatility_penalty,
                    "gap_penalty_component": gap_penalty,
                    "open_order_penalty_component": open_order_penalty,
                    "avoid_theme_penalty_component": avoid_theme_penalty,
                    "repeat_symbol_penalty_component": repeat_symbol_penalty,
                    "repeat_blocker_penalty_component": repeat_blocker_penalty,
                    "scanner_bias_adjustment": float(scanner_bias_adjustment),
                    "scanner_memory_bias_adjustment": float(scanner_memory_bias_adjustment),
                    "scanner_memory_bias_source_delta": float(memory_bias_result.get("source_delta") or 0.0),
                    "scanner_memory_bias_symbol_delta": float(memory_bias_result.get("symbol_delta") or 0.0),
                    "scanner_memory_bias_adjustments": list(memory_bias_result.get("adjustments") or []),
                    "entry_compatibility_score": compatibility_result.get("entry_compatibility_score"),
                    "entry_compatibility_bias": compatibility_result.get("compatibility_bias"),
                    "compatibility_components": dict(compatibility_result.get("compatibility_components") or {}),
                    "scanner_chart_fit_score": compatibility_result.get("scanner_chart_fit_score"),
                    "scanner_chart_fit_authority": compatibility_result.get("scanner_chart_fit_authority"),
                    "scanner_chart_fit_components": dict(compatibility_result.get("scanner_chart_fit_components") or {}),
                    "scanner_chart_fit_penalty": compatibility_result.get("scanner_chart_fit_penalty"),
                    "scanner_macro_chart_fit_score": macro_chart_fit.get("scanner_macro_chart_fit_score"),
                    "scanner_macro_chart_fit_bias": scanner_macro_chart_fit_bias,
                    "scanner_macro_chart_fit_authority": macro_chart_fit.get("scanner_macro_chart_fit_authority"),
                    "scanner_macro_chart_fit_components": dict(
                        macro_chart_fit.get("scanner_macro_chart_fit_components") or {}
                    ),
                    "scanner_macro_chart_fit_focus": dict(
                        macro_chart_fit.get("scanner_macro_chart_fit_focus") or {}
                    ),
                    "expected_monitor_block_reason": compatibility_result.get("expected_monitor_block_reason"),
                    "dominant_block_reason": compatibility_result.get("dominant_block_reason"),
                    "dominant_block_reason_ratio": compatibility_result.get("dominant_block_reason_ratio"),
                    "bias_scale": compatibility_result.get("bias_scale"),
                    "soft_penalty": compatibility_result.get("soft_penalty"),
                    "compatibility_score_pre_penalty": compatibility_result.get("compatibility_score_pre_penalty"),
                    "compatibility_score_post_penalty": compatibility_result.get("compatibility_score_post_penalty"),
                    "compatibility_source": compatibility_result.get("compatibility_source"),
                    "pre_adjust_score_total": float(pre_adjust_score_total),
                    "post_adjust_score_total": float(score_total),
                    "scanner_bias_signals": dict(bias_result.get("bias_signals") or {}),
                    "recent_selection_repeat_count": int(repeat_penalty_meta.get("repeat_count") or 0),
                    "recent_selection_streak_count": int(repeat_penalty_meta.get("streak_count") or 0),
                    "recent_trade_same_symbol": bool(repeat_penalty_meta.get("recent_trade_same_symbol")),
                    "recent_blocker_repeat_count": int(blocker_penalty_meta.get("repeat_count") or 0),
                    "recent_blocker_reason": str(blocker_penalty_meta.get("reason") or ""),
                    "news_sentiment_status": str(news_sig.get("status") or "fallback"),
                    "news_sentiment_source": str(news_sig.get("source") or ""),
                    "news_sentiment_reason": str(news_sig.get("reason") or ""),
                    "global_sentiment_status": str(gs_signal.get("status") or "fallback"),
                    "global_sentiment_source": str(gs_signal.get("source") or ""),
                    "global_sentiment_reason": str(gs_signal.get("reason") or ""),
                }
            )

        tactic_id = str(scanner_guidance.get("tactical_strategy") or "")
        row["tactical_strategy"] = tactic_id
        row["tactical_subtype"] = str(scanner_guidance.get("tactical_subtype") or "")
        row["playbook"] = playbook
        row["tactic_suitability"] = score_candidate_tactic_suitability(
            row,
            tactic_id=tactic_id,
            playbook=playbook,
        )

        scan_results.append(row)

    # Sort by score desc, then confidence desc, then risk asc
    scan_results_sorted = sorted(
        scan_results,
        key=lambda r: (
            float(r.get("score") or 0.0),
            float(r.get("confidence") or 0.0),
            -float(r.get("risk_score") or 0.0),
        ),
        reverse=True,
    )

    # ---- [NEW: Commander Policy Overlay] ----
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    commander_scanner_policy = commander_decision.get("scanner_policy") if isinstance(commander_decision.get("scanner_policy"), dict) else {}
    if not commander_scanner_policy:
        applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
        applied_scanner_policy = applied_policy.get("scanner") if isinstance(applied_policy.get("scanner"), dict) else {}
        if applied_scanner_policy:
            commander_scanner_policy = dict(applied_scanner_policy)
    if not isinstance(commander_scanner_policy.get("market_representative_guard"), dict):
        source_type = str(((commander_scanner_policy.get("source") or {}).get("type") if isinstance(commander_scanner_policy.get("source"), dict) else "") or "").strip().lower()
        if source_type in ("", "kiwoom", "hybrid", "auto"):
            commander_scanner_policy = dict(commander_scanner_policy)
            commander_scanner_policy["market_representative_guard"] = _default_market_representative_guard_policy()
    enforce_blocker_family_veto = _is_trueish(
        commander_scanner_policy.get(
            "enforce_blocker_family_selection_veto",
            os.getenv("SCANNER_ENFORCE_BLOCKER_FAMILY_SELECTION_VETO", "false"),
        )
    )
    
    avoid_recent_symbol = _is_trueish(commander_scanner_policy.get("avoid_recent_symbol", False))
    recent_symbol_penalty = _to_float(commander_scanner_policy.get("recent_symbol_penalty", 0.0))
    diversification_bias = _to_float(commander_scanner_policy.get("diversification_bias", 0.0))
    entry_bias_cap = _to_float(commander_scanner_policy.get("entry_bias_cap", 0.0))
    allow_same_symbol_reentry = _is_trueish(commander_scanner_policy.get("allow_same_symbol_reentry", True))
    reentry_score_gap_threshold = _to_float(commander_scanner_policy.get("reentry_score_gap_threshold", 0.0))

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    last_trade_symbol = _norm_symbol(persisted.get("last_trade_symbol", ""))
    positions = state.get("portfolio_snapshot", {}).get("positions", [])
    if isinstance(positions, dict):
        open_position_count = sum(1 for v in positions.values() if isinstance(v, dict) and _to_float(v.get("qty")) > 0)
    elif isinstance(positions, list):
        open_position_count = sum(1 for v in positions if isinstance(v, dict) and _to_float(v.get("qty")) > 0)
    else:
        open_position_count = 0
    is_flat = open_position_count == 0

    ranking_before_policy = [{"symbol": r.get("symbol"), "score_total": r.get("score_total")} for r in scan_results_sorted]
    
    reentry_penalty_applied = False
    reentry_penalty_value = 0.0
    diversification_applied = False
    diversification_bonus_value = 0.0
    score_adjustment_trace = []
    market_representative_guard_meta = {
        "enabled": False,
        "applied": False,
        "policy": {},
        "symbol": "",
        "penalty": 0.0,
        "score_gap": 0.0,
        "top_value_dominance": False,
        "confirmation_sources": [],
        "before_top": [],
        "after_top": [],
        "skipped_reason": "",
        "reason": "",
    }

    if entry_bias_cap > 0.0:
        for r in scan_results_sorted:
            raw_bias = _to_float(r.get("compatibility_bias", 0.0))
            if raw_bias > entry_bias_cap:
                diff = raw_bias - entry_bias_cap
                r["compatibility_bias"] = entry_bias_cap
                r["score_total"] = _to_float(r.get("score_total", 0.0)) - diff
                r["score"] = r["score_total"]
                r["entry_bias_cap_applied"] = True
                r["raw_entry_compatibility_bias"] = raw_bias
                r["effective_entry_compatibility_bias"] = entry_bias_cap
                score_adjustment_trace.append(f"entry_bias_cap applied to {r.get('symbol')}: {raw_bias:.3f} -> {entry_bias_cap:.3f}")
        scan_results_sorted.sort(key=lambda r: (float(r.get("score_total") or 0.0), float(r.get("confidence") or 0.0), -float(r.get("risk_score") or 0.0)), reverse=True)

    if len(scan_results_sorted) > 0:
        top1 = scan_results_sorted[0]
        top1_sym = _norm_symbol(top1.get("symbol"))
        top1_score = _to_float(top1.get("score_total"))
        
        if len(scan_results_sorted) > 1:
            top2 = scan_results_sorted[1]
            top2_score = _to_float(top2.get("score_total"))
            score_gap = top1_score - top2_score
            
            if avoid_recent_symbol and is_flat and last_trade_symbol == top1_sym and allow_same_symbol_reentry:
                if score_gap <= reentry_score_gap_threshold:
                    top1["score_total"] = top1_score - recent_symbol_penalty
                    top1["score"] = top1["score_total"]
                    reentry_penalty_applied = True
                    reentry_penalty_value = recent_symbol_penalty
                    score_adjustment_trace.append(f"reentry_dampener applied to {top1_sym}: -{recent_symbol_penalty:.3f} (gap {score_gap:.3f} <= {reentry_score_gap_threshold:.3f})")
            elif diversification_bias > 0.0 and score_gap <= reentry_score_gap_threshold:
                if top2.get("symbol") != last_trade_symbol:
                    top2["score_total"] = top2_score + diversification_bias
                    top2["score"] = top2["score_total"]
                    diversification_applied = True
                    diversification_bonus_value = diversification_bias
                    score_adjustment_trace.append(f"diversification_bonus applied to {top2.get('symbol')}: +{diversification_bias:.3f}")

        scan_results_sorted.sort(key=lambda r: (float(r.get("score_total") or 0.0), float(r.get("confidence") or 0.0), -float(r.get("risk_score") or 0.0)), reverse=True)

    scan_results_sorted, market_representative_guard_meta = _apply_market_representative_guard(
        scan_results_sorted,
        raw_policy=commander_scanner_policy.get("market_representative_guard"),
    )
    if bool(market_representative_guard_meta.get("applied")):
        score_adjustment_trace.append(
            "market_representative_guard "
            f"{str(market_representative_guard_meta.get('symbol') or '')} "
            f"-{float(_to_float(market_representative_guard_meta.get('penalty'))):.3f}"
        )

    blocker_family_overlay_meta = {
        "applied": False,
        "family": "",
        "penalty": 0.0,
        "candidate_count": 0,
        "top3_symbols_before": [],
        "top3_symbols_after": [],
        "alternative_symbols": [],
        "selection_vetoed": False,
        "selection_veto_reason": "",
    }
    scan_results_sorted, blocker_family_overlay_meta = _apply_blocker_family_concentration_overlay(
        scan_results_sorted,
        scan_aggressiveness=float(_to_float(pool_meta.get("scan_aggressiveness"))),
    )
    if bool(blocker_family_overlay_meta.get("applied")):
        score_adjustment_trace.append(
            "blocker_family_concentration "
            f"{str(blocker_family_overlay_meta.get('family') or '')} "
            f"-{float(_to_float(blocker_family_overlay_meta.get('penalty'))):.3f}"
        )
    if bool(blocker_family_overlay_meta.get("selection_vetoed")):
        score_adjustment_trace.append(
            f"selection_veto:{str(blocker_family_overlay_meta.get('selection_veto_reason') or '')}"
        )
        if not enforce_blocker_family_veto:
            score_adjustment_trace.append("selection_veto_observed_not_enforced")

    ranking_after_policy = [{"symbol": r.get("symbol"), "score_total": r.get("score_total")} for r in scan_results_sorted]

    selected = scan_results_sorted[0] if scan_results_sorted else None
    selection_veto_enforced = bool(blocker_family_overlay_meta.get("selection_vetoed")) and bool(enforce_blocker_family_veto)
    if selection_veto_enforced:
        selected = None
    now_epoch = _resolve_now_epoch(state)
    if isinstance(selected, dict):
        _remember_selected_symbol(state, str(selected.get("symbol") or ""), now_epoch=now_epoch, policy=policy)
    state["scan_results"] = scan_results_sorted
    state["ranked_candidates"] = [
        {
            "symbol": str(r.get("symbol") or ""),
            "asset_class_detected": str(r.get("asset_class_detected") or ""),
            "detection_source": str(r.get("detection_source") or ""),
            "detection_field": str(r.get("detection_field") or ""),
            "score_total": float(r.get("score_total") if r.get("score_total") is not None else _to_float(r.get("score"))),
            "score_breakdown": dict(r.get("score_breakdown") or {}),
            "risk_score": float(_to_float(r.get("risk_score"))),
            "confidence": float(_to_float(r.get("confidence"))),
            "bias_adjustment": float(_to_float(r.get("bias_adjustment"))),
            "bias_adjustments": list(r.get("bias_adjustments") or []),
            "bias_summary": dict(r.get("bias_summary") or {}),
            "entry_compatibility_score": float(_to_float(r.get("entry_compatibility_score"))),
            "compatibility_bias": float(_to_float(r.get("compatibility_bias"))),
            "compatibility_components": dict(r.get("compatibility_components") or {}),
            "scanner_chart_fit_score": float(_to_float(r.get("scanner_chart_fit_score"))),
            "scanner_chart_fit_authority": str(r.get("scanner_chart_fit_authority") or ""),
            "scanner_chart_fit_components": dict(r.get("scanner_chart_fit_components") or {}),
            "scanner_macro_chart_fit_score": float(_to_float(r.get("scanner_macro_chart_fit_score"), 0.5)),
            "scanner_macro_chart_fit_bias": float(_to_float(r.get("scanner_macro_chart_fit_bias"))),
            "scanner_macro_chart_fit_authority": str(r.get("scanner_macro_chart_fit_authority") or ""),
            "scanner_macro_chart_fit_components": dict(r.get("scanner_macro_chart_fit_components") or {}),
            "expected_monitor_block_reason": str(r.get("expected_monitor_block_reason") or ""),
            "dominant_block_reason": str(r.get("dominant_block_reason") or ""),
            "dominant_block_reason_ratio": float(_to_float(r.get("dominant_block_reason_ratio"))),
            "blocker_families": list(_candidate_blocker_families(r)),
            "bias_scale": float(_to_float(r.get("bias_scale"))),
            "soft_penalty": float(_to_float(r.get("soft_penalty"))),
            "compatibility_score_pre_penalty": float(_to_float(r.get("compatibility_score_pre_penalty"))),
            "compatibility_score_post_penalty": float(_to_float(r.get("compatibility_score_post_penalty"))),
            "compatibility_trace": dict(r.get("compatibility_trace") or {}),
            "pre_adjust_score_total": float(_to_float(r.get("pre_adjust_score_total"))),
            "post_adjust_score_total": float(_to_float(r.get("post_adjust_score_total") or r.get("score_total") or r.get("score"))),
            "scanner_intrinsic_control_score_total": float(
                _to_float(r.get("scanner_intrinsic_control_score_total"))
            ),
            "market_representative_guard_applied": bool(r.get("market_representative_guard_applied")),
            "market_representative_guard_penalty": float(_to_float(r.get("market_representative_guard_penalty"))),
            "market_representative_guard_reason": str(r.get("market_representative_guard_reason") or ""),
            "market_representative_confirmation_sources": list(r.get("market_representative_confirmation_sources") or []),
        }
        for r in scan_results_sorted
        if isinstance(r, dict)
    ]
    candidate_visibility_limit = _candidate_visibility_limit(commander_scanner_policy)
    visible_ranked_candidates = list(state.get("ranked_candidates") or [])[:candidate_visibility_limit]
    state["selected"] = selected
    state["top_stock"] = str(selected.get("symbol") or "") if isinstance(selected, dict) else ""
    top_score = (
        float(selected.get("score_total"))
        if isinstance(selected, dict) and selected.get("score_total") is not None
        else (
            float(selected.get("score"))
            if isinstance(selected, dict) and selected.get("score") is not None
            else None
        )
    )
    state["scanner_output"] = {
        "top_stock": state["top_stock"] or None,
        "primary_watch_symbol": state["top_stock"] or None,
        "score": (
            float(selected.get("raw_score"))
            if isinstance(selected, dict) and selected.get("raw_score") is not None
            else float(selected.get("score"))
            if isinstance(selected, dict) and selected.get("score") is not None
            else None
        ),
        "top_score": top_score,
        "risk_score": (
            float(selected.get("risk_score"))
            if isinstance(selected, dict) and selected.get("risk_score") is not None
            else None
        ),
        "confidence": (
            float(selected.get("confidence"))
            if isinstance(selected, dict) and selected.get("confidence") is not None
            else None
        ),
        "candidate_count": int(len(scan_results_sorted)),
        "candidate_pool_size": int(len(scan_results_sorted)),
        "ranked_candidates": visible_ranked_candidates,
        "watch_candidates": visible_ranked_candidates,
        "candidate_source": str(pool_meta.get("candidate_source") or ""),
        "scanner_candidate_source": str(pool_meta.get("scanner_candidate_source") or ""),
        "scanner_policy_source": str(pool_meta.get("scanner_policy_source") or ""),
        "scanner_fallback_mode": str(pool_meta.get("scanner_fallback_mode") or ""),
        "scanner_strict_mode": bool(pool_meta.get("scanner_strict_mode")),
        "fallback_reason": str(pool_meta.get("fallback_reason") or ""),
        "blocked_static_fallback": bool(pool_meta.get("blocked_static_fallback")),
        "strict_kiwoom_only": bool(pool_meta.get("strict_kiwoom_only")),
        "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
        "avoid_filter_applied": bool(pool_meta.get("avoid_filter_applied")),
        "avoid_filter_reason": str(pool_meta.get("avoid_filter_reason") or ""),
        "avoid_filter_fallback_used": bool(pool_meta.get("avoid_filter_fallback_used")),
        "backfill_used": bool(pool_meta.get("backfill_used")),
        "backfill_count": int(pool_meta.get("backfill_count") or 0),
        "backfill_skipped_reason": str(pool_meta.get("backfill_skipped_reason") or ""),
        "scan_aggressiveness": float(_to_float(pool_meta.get("scan_aggressiveness"))),
        "strict_mode_relaxed_by_scan_aggressiveness": bool(pool_meta.get("strict_mode_relaxed_by_scan_aggressiveness")),
        "candidate_limit_base": int(pool_meta.get("candidate_limit_base") or 0),
        "candidate_limit_effective": int(pool_meta.get("candidate_limit_effective") or 0),
        "aggressive_source_expansion_used": bool(pool_meta.get("aggressive_source_expansion_used")),
        "aggressive_source_expansion_slots": int(pool_meta.get("aggressive_source_expansion_slots") or 0),
        "aggressive_source_expansion_sources": list(pool_meta.get("aggressive_source_expansion_sources") or []),
        "score_weights": dict(practical_w),
        "source_mix": dict(pool_meta.get("pool_source_mix") or {}),
        "theme_source": str(scanner_guidance.get("theme_source") or ""),
        "theme_source_status": str(scanner_guidance.get("theme_source_status") or ""),
        "selected_themes": list(pool_meta.get("selected_themes") or []),
        "selected_theme_source": str(pool_meta.get("selected_theme_source") or ""),
        "available_themes": list(scanner_guidance.get("available_themes") or [])[:8],
        "theme_strategy": dict(scanner_guidance.get("theme_strategy") or {})
        if isinstance(scanner_guidance.get("theme_strategy"), dict)
        else {},
        "theme_strength_packet": dict(scanner_guidance.get("theme_strength_packet") or {})
        if isinstance(scanner_guidance.get("theme_strength_packet"), dict)
        else {},
        "asset_universe_policy": str(pool_meta.get("asset_universe_policy") or ""),
        "asset_universe_policy_source": str(pool_meta.get("asset_universe_policy_source") or ""),
        "excluded_candidate_count_by_asset_policy": int(pool_meta.get("asset_policy_excluded_count") or 0),
        "excluded_candidates_by_asset_policy": list(pool_meta.get("asset_policy_exclusions") or []),
        "excluded_candidate_count_by_mock_broker_restricted": int(pool_meta.get("mock_broker_restricted_excluded_count") or 0),
        "excluded_candidates_by_mock_broker_restricted": list(pool_meta.get("mock_broker_restricted_exclusions") or []),
        "mock_broker_restricted_filter_applied": bool(pool_meta.get("mock_broker_restricted_filter_applied")),
        "asset_detection_stats": dict(pool_meta.get("asset_detection_stats") or {}),
        "unknown_asset_candidate_count": int(pool_meta.get("unknown_asset_candidate_count") or 0),
        "total_candidates_before_filter": int(pool_meta.get("total_candidates_before_filter") or 0),
        "total_candidates_after_filter": int(pool_meta.get("total_candidates_after_filter") or 0),
        "condition_search_status": str(pool_meta.get("condition_search_status") or ""),
        "condition_search_source": str(pool_meta.get("condition_search_source") or ""),
        "condition_search_reason": str(pool_meta.get("condition_search_reason") or ""),
        "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
        "strategist_scanner_priority": list(scanner_priority),
        "strategist_playbook": playbook or None,
        "strategist_scanner_bias": scanner_bias or None,
        "strategist_avoid_themes": list(pool_meta.get("avoid_themes") or []),
        "strategist_trade_aggressiveness": trade_aggressiveness or None,
        "strategist_risk_tone": risk_tone or None,
        "repeat_guard": _resolve_scanner_repeat_guard_policy(policy),
        "recent_scanner_selected_count": int(len(_scanner_recent_selection_history(state))),
        "commander_context_consumed": bool(scanner_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(scanner_policy_trace.get("consumed_fields") or []),
        "commander_priority_ref": dict(scanner_policy_trace.get("commander_priority_ref") or {}),
        "strategist_constraints_ref": dict(scanner_policy_trace.get("strategist_constraints_ref") or {}),
        "selection_basis": dict(scanner_policy_trace.get("selection_basis") or {}),
        "ranking_factors": list(scanner_policy_trace.get("ranking_factors") or []),
        "playbook": str(scanner_policy_trace.get("playbook") or playbook or ""),
        "policy_source": str(scanner_policy_trace.get("policy_source") or ""),
        "applied_policy_present": bool(scanner_policy_trace.get("applied_policy_present")),
        "monitor_entry_policy_summary": dict(scanner_policy_trace.get("monitor_entry_policy_summary") or {}),
        "entry_compatibility_score": float(_to_float((selected or {}).get("entry_compatibility_score"))) if isinstance(selected, dict) else 0.0,
        "compatibility_bias": float(_to_float((selected or {}).get("compatibility_bias"))) if isinstance(selected, dict) else 0.0,
        "compatibility_components": dict((selected or {}).get("compatibility_components") or {}) if isinstance(selected, dict) else {},
        "scanner_chart_fit_score": float(_to_float((selected or {}).get("scanner_chart_fit_score"))) if isinstance(selected, dict) else 0.0,
        "scanner_chart_fit_authority": str((selected or {}).get("scanner_chart_fit_authority") or "") if isinstance(selected, dict) else "",
        "scanner_chart_fit_components": dict((selected or {}).get("scanner_chart_fit_components") or {}) if isinstance(selected, dict) else {},
        "tactic_suitability": dict((selected or {}).get("tactic_suitability") or {}) if isinstance(selected, dict) else {},
        "scanner_macro_chart_fit_score": float(_to_float((selected or {}).get("scanner_macro_chart_fit_score"), 0.5)) if isinstance(selected, dict) else 0.5,
        "scanner_macro_chart_fit_bias": float(_to_float((selected or {}).get("scanner_macro_chart_fit_bias"))) if isinstance(selected, dict) else 0.0,
        "scanner_macro_chart_fit_authority": str((selected or {}).get("scanner_macro_chart_fit_authority") or "") if isinstance(selected, dict) else "",
        "scanner_macro_chart_fit_components": dict((selected or {}).get("scanner_macro_chart_fit_components") or {}) if isinstance(selected, dict) else {},
        "expected_monitor_block_reason": str((selected or {}).get("expected_monitor_block_reason") or "") if isinstance(selected, dict) else "",
        "dominant_block_reason": str((selected or {}).get("dominant_block_reason") or compatibility_bias_context.get("dominant_block_reason") or "") if isinstance(selected, dict) else str(compatibility_bias_context.get("dominant_block_reason") or ""),
        "dominant_block_reason_ratio": float(_to_float((selected or {}).get("dominant_block_reason_ratio") or compatibility_bias_context.get("dominant_block_reason_ratio"))),
        "bias_scale": float(_to_float((selected or {}).get("bias_scale") or compatibility_bias_context.get("bias_scale"))),
        "soft_penalty": float(_to_float((selected or {}).get("soft_penalty"))) if isinstance(selected, dict) else 0.0,
        "compatibility_score_pre_penalty": float(_to_float((selected or {}).get("compatibility_score_pre_penalty"))) if isinstance(selected, dict) else 0.0,
        "compatibility_score_post_penalty": float(_to_float((selected or {}).get("compatibility_score_post_penalty"))) if isinstance(selected, dict) else 0.0,
        "compatibility_trace": dict((selected or {}).get("compatibility_trace") or {}) if isinstance(selected, dict) else {},
        "pre_adjust_score_total": float(_to_float((selected or {}).get("pre_adjust_score_total"))) if isinstance(selected, dict) else 0.0,
        "post_adjust_score_total": float(_to_float((selected or {}).get("post_adjust_score_total") or (selected or {}).get("score_total") or (selected or {}).get("score"))) if isinstance(selected, dict) else 0.0,
        "quote_data_diagnostic": dict(state.get("scanner_quote_diagnostic") or {}),
        "scanner_bias_applied": False,
        "scanner_bias_summary": dict(scanner_policy_trace.get("scanner_bias_summary") or {}),
        "scanner_memory_bias_applied": False,
        "scanner_memory_bias_summary": dict(scanner_policy_trace.get("scanner_memory_bias_summary") or {}),
        "candidate_bias_adjustments": [],
        "candidate_memory_bias_adjustments": [],
        "candidate_symbol_prior_adjustments": [],
        "selection_reason_with_bias": "",
        "shadow_used": bool(scanner_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(scanner_policy_trace.get("strategist_fallback_used")),
        "policy_provenance": dict(policy_provenance),
        "policy_provenance_ref": dict(scanner_policy_trace.get("policy_provenance_ref") or {}),
        "applied_scanner_policy": dict(commander_scanner_policy),
        "score_adjustment_trace": list(score_adjustment_trace),
        "reentry_penalty_applied": bool(reentry_penalty_applied),
        "reentry_penalty_value": float(reentry_penalty_value),
        "diversification_applied": bool(diversification_applied),
        "diversification_bonus_value": float(diversification_bonus_value),
        "entry_bias_cap_applied": bool((selected or {}).get("entry_bias_cap_applied") if isinstance(selected, dict) else False),
        "market_representative_guard_enabled": bool(market_representative_guard_meta.get("enabled")),
        "market_representative_guard_applied": bool(market_representative_guard_meta.get("applied")),
        "market_representative_guard_policy": dict(market_representative_guard_meta.get("policy") or {}),
        "market_representative_guard_symbol": str(market_representative_guard_meta.get("symbol") or ""),
        "market_representative_guard_penalty": float(_to_float(market_representative_guard_meta.get("penalty"))),
        "market_representative_guard_score_gap": float(_to_float(market_representative_guard_meta.get("score_gap"))),
        "market_representative_guard_reason": str(
            market_representative_guard_meta.get("reason")
            or market_representative_guard_meta.get("skipped_reason")
            or ""
        ),
        "market_representative_guard_top_value_dominance": bool(market_representative_guard_meta.get("top_value_dominance")),
        "market_representative_guard_confirmation_sources": list(market_representative_guard_meta.get("confirmation_sources") or []),
        "market_representative_guard_before_top": list(market_representative_guard_meta.get("before_top") or []),
        "market_representative_guard_after_top": list(market_representative_guard_meta.get("after_top") or []),
        "raw_entry_compatibility_bias": float(
            _to_float((selected or {}).get("raw_entry_compatibility_bias")) if isinstance(selected, dict) else 0.0
        ),
        "effective_entry_compatibility_bias": float(
            _to_float((selected or {}).get("effective_entry_compatibility_bias")) if isinstance(selected, dict) else 0.0
        ),
        "adjusted_score_total": float(_to_float((selected or {}).get("score_total"))) if isinstance(selected, dict) else 0.0,
        "ranking_before_policy": ranking_before_policy,
        "ranking_after_policy": ranking_after_policy,
        "blocker_family_concentration_applied": bool(blocker_family_overlay_meta.get("applied")),
        "blocker_family_concentration_family": str(blocker_family_overlay_meta.get("family") or ""),
        "blocker_family_concentration_penalty": float(_to_float(blocker_family_overlay_meta.get("penalty"))),
        "blocker_family_concentration_candidate_count": int(blocker_family_overlay_meta.get("candidate_count") or 0),
        "blocker_family_concentration_top3_before": list(blocker_family_overlay_meta.get("top3_symbols_before") or []),
        "blocker_family_concentration_top3_after": list(blocker_family_overlay_meta.get("top3_symbols_after") or []),
        "blocker_family_concentration_alternative_symbols": list(blocker_family_overlay_meta.get("alternative_symbols") or []),
        "selection_vetoed": bool(blocker_family_overlay_meta.get("selection_vetoed")),
        "selection_veto_enforced": bool(selection_veto_enforced),
        "selection_veto_reason": str(blocker_family_overlay_meta.get("selection_veto_reason") or ""),
    }

    # Provide a normalized risk snapshot for Decision Node.
    if isinstance(selected, dict):
        state["risk"] = {
            "risk_score": float(selected.get("risk_score") or 0.0),
            "confidence": float(selected.get("confidence") or 0.0),
        }
    else:
        state["risk"] = {"risk_score": 0.0, "confidence": 0.0}
    fallback_reasons: List[str] = list(quote_meta.get("errors") or []) + list(order_meta.get("errors") or [])
    state["scanner_skill"] = {
        "contract_version": SKILL_CONTRACT_VERSION,
        "used": bool(skill_quotes) or bool(skill_order_counts),
        "quote_symbols": len(skill_quotes),
        "account_open_order_symbols": len(skill_order_counts),
        "account_order_rows": int(skill_order_rows),
        "quote_present": bool(quote_meta.get("present")),
        "account_orders_present": bool(order_meta.get("present")),
        "fallback": bool(fallback_reasons),
        "fallback_reasons": fallback_reasons,
        "error_count": len(fallback_reasons),
    }
    state["scanner_feature"] = {
        "used": bool(feature_map),
        "source": feature_source,
        "symbol_count": len(feature_map),
        "refresh_existing": bool(refresh_existing_features),
        "refresh_reason": str(feature_refresh_reason or ""),
        "fallback": bool(feature_errors),
        "fallback_reasons": list(feature_errors),
        "error_count": len(feature_errors),
    }
    ranking_table = _ranking_table_rows(scan_results_sorted, max_rows=candidate_visibility_limit)
    selected_snapshot = _compact_selected_snapshot(selected if isinstance(selected, dict) else None)
    selected_symbol = str((selected or {}).get("symbol") or "") if isinstance(selected, dict) else ""
    selected_rank = 0
    if selected_symbol:
        ranked_symbols = [str((row or {}).get("symbol") or "") for row in list(scan_results_sorted) if isinstance(row, dict)]
        if selected_symbol in ranked_symbols:
            selected_rank = int(ranked_symbols.index(selected_symbol) + 1)
    selected_score_total = float(_to_float((selected or {}).get("score_total") or (selected or {}).get("score"))) if isinstance(selected, dict) else 0.0
    second_score_total = float(_to_float((scan_results_sorted[1] or {}).get("score_total") or (scan_results_sorted[1] or {}).get("score"))) if len(scan_results_sorted) > 1 and isinstance(scan_results_sorted[1], dict) else 0.0
    margin_vs_second = float(selected_score_total - second_score_total) if isinstance(selected, dict) else 0.0
    selected_score_breakdown = dict((selected or {}).get("score_breakdown") or {}) if isinstance(selected, dict) else {}
    critical_positive_factors = [f"{str(k)}:{float(_to_float(v)):.3f}" for k, v in selected_score_breakdown.items() if float(_to_float(v)) > 0][:4]
    critical_negative_factors = [f"{str(k)}:{float(_to_float(v)):.3f}" for k, v in selected_score_breakdown.items() if float(_to_float(v)) < 0][:4]
    selection_summary = str((selected or {}).get("why") or "").strip() if isinstance(selected, dict) else ""
    if bool(blocker_family_overlay_meta.get("selection_vetoed")):
        selection_summary = str(blocker_family_overlay_meta.get("selection_veto_reason") or "blocker_family_concentration_veto")
    scanner_bias_summary = dict(scanner_policy_trace.get("scanner_bias_summary") or {})
    scanner_memory_bias_summary = dict(scanner_policy_trace.get("scanner_memory_bias_summary") or {})
    candidate_bias_adjustments = [
        {
            "symbol": str(row.get("symbol") or ""),
            "bias_adjustment": float(_to_float(row.get("bias_adjustment"))),
            "bias_adjustments": list(row.get("bias_adjustments") or []),
        }
        for row in list(scan_results_sorted)[:candidate_visibility_limit]
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    ]
    candidate_memory_bias_adjustments = [
        {
            "symbol": str(row.get("symbol") or ""),
            "memory_bias_adjustment": float(_to_float(row.get("memory_bias_adjustment"))),
            "memory_bias_observed_adjustment": float(_to_float(row.get("memory_bias_observed_adjustment"))),
            "memory_bias_observation_only": bool(row.get("memory_bias_observation_only")),
            "memory_bias_source_delta": float(_to_float(row.get("memory_bias_source_delta"))),
            "memory_bias_symbol_delta": float(_to_float(row.get("memory_bias_symbol_delta"))),
            "memory_bias_adjustments": list(row.get("memory_bias_adjustments") or []),
            "memory_bias_summary": dict(row.get("memory_bias_summary") or {}),
        }
        for row in list(scan_results_sorted)[:candidate_visibility_limit]
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    ]
    candidate_symbol_prior_adjustments = [
        {
            "symbol": str(row.get("symbol") or ""),
            "symbol_prior_adjustment": float(_to_float(row.get("symbol_prior_adjustment"))),
            "symbol_prior_reasons": list(row.get("symbol_prior_reasons") or []),
            "symbol_prior_summary": dict(row.get("symbol_prior_summary") or {}),
        }
        for row in list(scan_results_sorted)[:candidate_visibility_limit]
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    ]
    scanner_bias_applied = any(abs(float(_to_float(row.get("bias_adjustment")))) > 1e-9 for row in list(scan_results_sorted))
    scanner_memory_bias_applied = any(
        abs(float(_to_float(row.get("memory_bias_adjustment")))) > 1e-9 for row in list(scan_results_sorted)
    )
    selected_memory_bias_result = {
        "bias_adjustment": float(_to_float((selected or {}).get("memory_bias_adjustment"))) if isinstance(selected, dict) else 0.0,
        "observed_bias_adjustment": float(_to_float((selected or {}).get("memory_bias_observed_adjustment"))) if isinstance(selected, dict) else 0.0,
        "observation_only": bool((selected or {}).get("memory_bias_observation_only")) if isinstance(selected, dict) else False,
        "source_delta": float(_to_float((selected or {}).get("memory_bias_source_delta"))) if isinstance(selected, dict) else 0.0,
        "symbol_delta": float(_to_float((selected or {}).get("memory_bias_symbol_delta"))) if isinstance(selected, dict) else 0.0,
        "adjustments": list((selected or {}).get("memory_bias_adjustments") or []) if isinstance(selected, dict) else [],
    }
    commander_memory_application_trace = build_scanner_commander_memory_application_trace(
        scanner_memory_bias=scanner_memory_bias,
        selected_symbol=selected_symbol,
        candidate_sources=(
            list(((selected or {}).get("candidate") or {}).get("sources") or [])
            if isinstance(selected, dict) and isinstance((selected or {}).get("candidate"), dict)
            else []
        ),
        selected_memory_bias_result=selected_memory_bias_result,
        candidate_memory_bias_adjustments=candidate_memory_bias_adjustments,
        scanner_memory_bias_summary=scanner_memory_bias_summary,
        scanner_memory_bias_applied=bool(scanner_memory_bias_applied),
    )
    selection_reason_with_bias = selection_summary
    if scanner_bias_applied:
        bias_text = str(scanner_bias_summary.get("summary") or "scanner_bias").strip() or "scanner_bias"
        selection_reason_with_bias = (
            f"{selection_summary} | bias: {bias_text}" if selection_summary else f"bias applied: {bias_text}"
        )
    if scanner_memory_bias_applied:
        memory_bias_text = "memory_bias=commander"
        selection_reason_with_bias = (
            f"{selection_reason_with_bias} | {memory_bias_text}"
            if selection_reason_with_bias
            else memory_bias_text
        )
    selected_compatibility_bias = float(_to_float((selected or {}).get("compatibility_bias"))) if isinstance(selected, dict) else 0.0
    selected_expected_block = str((selected or {}).get("expected_monitor_block_reason") or "") if isinstance(selected, dict) else ""
    if abs(selected_compatibility_bias) > 1e-9:
        compatibility_text = (
            f"compatibility_bias={selected_compatibility_bias:+.3f}"
            + (f", monitor_risk={selected_expected_block}" if selected_expected_block else "")
        )
        selection_reason_with_bias = (
            f"{selection_reason_with_bias} | {compatibility_text}"
            if selection_reason_with_bias
            else compatibility_text
        )
    if score_adjustment_trace:
        selection_reason_with_bias += f" | overlay: {', '.join(score_adjustment_trace)}"
    if bool(blocker_family_overlay_meta.get("selection_vetoed")):
        veto_text = (
            (
                "selection veto enforced due to blocker family concentration"
                if selection_veto_enforced
                else "selection veto observed but not enforced due to blocker family concentration"
            )
            + (
                f" ({str(blocker_family_overlay_meta.get('family') or '')})"
                if str(blocker_family_overlay_meta.get("family") or "").strip()
                else ""
            )
        )
        selection_reason_with_bias = (
            f"{selection_reason_with_bias} | {veto_text}"
            if selection_reason_with_bias
            else veto_text
        )
    runner_up_reasons: List[Dict[str, Any]] = []
    if len(scan_results_sorted) > 1 and isinstance(selected, dict):
        selected_score = float(_to_float(selected.get("score_total") or selected.get("score")))
        selected_confidence = float(_to_float(selected.get("confidence")))
        selected_risk = float(_to_float(selected.get("risk_score")))
        for row in list(scan_results_sorted[1:3]):
            if not isinstance(row, dict):
                continue
            reasons: List[str] = []
            row_score = float(_to_float(row.get("score_total") or row.get("score")))
            row_conf = float(_to_float(row.get("confidence")))
            row_risk = float(_to_float(row.get("risk_score")))
            if row_score < selected_score:
                reasons.append(f"lower total score ({row_score:.3f} vs {selected_score:.3f})")
            if row_conf < selected_confidence:
                reasons.append(f"lower confidence ({row_conf:.2f} vs {selected_confidence:.2f})")
            if row_risk > selected_risk:
                reasons.append(f"higher risk ({row_risk:.2f} vs {selected_risk:.2f})")
            if not reasons:
                reasons.append("lost on tie-break after score, confidence, and risk comparison")
            runner_up_reasons.append(
                {
                    "symbol": str(row.get("symbol") or ""),
                    "why_lost": reasons,
                }
            )
    state["scanner_ranking_table"] = list(ranking_table)
    state["scanner_runner_up_reasons"] = list(runner_up_reasons)
    state["scanner_selection_reason"] = {
        "selected_symbol": selected_symbol,
        "selected_rank": int(selected_rank),
        "selected_score_total": float(selected_score_total),
        "margin_vs_second": float(margin_vs_second),
        "critical_positive_factors": list(critical_positive_factors),
        "critical_negative_factors": list(critical_negative_factors),
        "selection_summary": selection_summary,
        "commander_context_consumed": bool(scanner_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(scanner_policy_trace.get("consumed_fields") or []),
        "commander_priority_ref": dict(scanner_policy_trace.get("commander_priority_ref") or {}),
        "strategist_constraints_ref": dict(scanner_policy_trace.get("strategist_constraints_ref") or {}),
        "selection_basis": dict(scanner_policy_trace.get("selection_basis") or {}),
        "ranking_factors": list(scanner_policy_trace.get("ranking_factors") or []),
        "playbook": str(scanner_policy_trace.get("playbook") or playbook or ""),
        "policy_source": str(scanner_policy_trace.get("policy_source") or ""),
        "applied_policy_present": bool(scanner_policy_trace.get("applied_policy_present")),
        "monitor_entry_policy_summary": dict(scanner_policy_trace.get("monitor_entry_policy_summary") or {}),
        "entry_compatibility_score": float(_to_float((selected or {}).get("entry_compatibility_score"))) if isinstance(selected, dict) else 0.0,
        "compatibility_bias": float(_to_float((selected or {}).get("compatibility_bias"))) if isinstance(selected, dict) else 0.0,
        "compatibility_components": dict((selected or {}).get("compatibility_components") or {}) if isinstance(selected, dict) else {},
        "scanner_chart_fit_score": float(_to_float((selected or {}).get("scanner_chart_fit_score"))) if isinstance(selected, dict) else 0.0,
        "scanner_chart_fit_authority": str((selected or {}).get("scanner_chart_fit_authority") or "") if isinstance(selected, dict) else "",
        "scanner_chart_fit_components": dict((selected or {}).get("scanner_chart_fit_components") or {}) if isinstance(selected, dict) else {},
        "scanner_macro_chart_fit_score": float(_to_float((selected or {}).get("scanner_macro_chart_fit_score"), 0.5)) if isinstance(selected, dict) else 0.5,
        "scanner_macro_chart_fit_bias": float(_to_float((selected or {}).get("scanner_macro_chart_fit_bias"))) if isinstance(selected, dict) else 0.0,
        "scanner_macro_chart_fit_authority": str((selected or {}).get("scanner_macro_chart_fit_authority") or "") if isinstance(selected, dict) else "",
        "scanner_macro_chart_fit_components": dict((selected or {}).get("scanner_macro_chart_fit_components") or {}) if isinstance(selected, dict) else {},
        "expected_monitor_block_reason": str((selected or {}).get("expected_monitor_block_reason") or "") if isinstance(selected, dict) else "",
        "dominant_block_reason": str((selected or {}).get("dominant_block_reason") or compatibility_bias_context.get("dominant_block_reason") or "") if isinstance(selected, dict) else str(compatibility_bias_context.get("dominant_block_reason") or ""),
        "dominant_block_reason_ratio": float(_to_float((selected or {}).get("dominant_block_reason_ratio") or compatibility_bias_context.get("dominant_block_reason_ratio"))),
        "market_representative_guard_enabled": bool(market_representative_guard_meta.get("enabled")),
        "market_representative_guard_applied": bool(market_representative_guard_meta.get("applied")),
        "market_representative_guard_policy": dict(market_representative_guard_meta.get("policy") or {}),
        "market_representative_guard_symbol": str(market_representative_guard_meta.get("symbol") or ""),
        "market_representative_guard_penalty": float(_to_float(market_representative_guard_meta.get("penalty"))),
        "market_representative_guard_score_gap": float(_to_float(market_representative_guard_meta.get("score_gap"))),
        "market_representative_guard_reason": str(
            market_representative_guard_meta.get("reason")
            or market_representative_guard_meta.get("skipped_reason")
            or ""
        ),
        "market_representative_guard_top_value_dominance": bool(market_representative_guard_meta.get("top_value_dominance")),
        "market_representative_guard_confirmation_sources": list(market_representative_guard_meta.get("confirmation_sources") or []),
        "market_representative_guard_before_top": list(market_representative_guard_meta.get("before_top") or []),
        "market_representative_guard_after_top": list(market_representative_guard_meta.get("after_top") or []),
        "blocker_family_concentration_applied": bool(blocker_family_overlay_meta.get("applied")),
        "blocker_family_concentration_family": str(blocker_family_overlay_meta.get("family") or ""),
        "blocker_family_concentration_penalty": float(_to_float(blocker_family_overlay_meta.get("penalty"))),
        "blocker_family_concentration_top3_before": list(blocker_family_overlay_meta.get("top3_symbols_before") or []),
        "blocker_family_concentration_top3_after": list(blocker_family_overlay_meta.get("top3_symbols_after") or []),
        "blocker_family_concentration_alternative_symbols": list(blocker_family_overlay_meta.get("alternative_symbols") or []),
        "selection_vetoed": bool(blocker_family_overlay_meta.get("selection_vetoed")),
        "selection_veto_enforced": bool(selection_veto_enforced),
        "selection_veto_reason": str(blocker_family_overlay_meta.get("selection_veto_reason") or ""),
        "bias_scale": float(_to_float((selected or {}).get("bias_scale") or compatibility_bias_context.get("bias_scale"))),
        "soft_penalty": float(_to_float((selected or {}).get("soft_penalty"))) if isinstance(selected, dict) else 0.0,
        "compatibility_score_pre_penalty": float(_to_float((selected or {}).get("compatibility_score_pre_penalty"))) if isinstance(selected, dict) else 0.0,
        "compatibility_score_post_penalty": float(_to_float((selected or {}).get("compatibility_score_post_penalty"))) if isinstance(selected, dict) else 0.0,
        "compatibility_trace": dict((selected or {}).get("compatibility_trace") or {}) if isinstance(selected, dict) else {},
        "pre_adjust_score_total": float(_to_float((selected or {}).get("pre_adjust_score_total"))) if isinstance(selected, dict) else 0.0,
        "post_adjust_score_total": float(_to_float((selected or {}).get("post_adjust_score_total") or (selected or {}).get("score_total") or (selected or {}).get("score"))) if isinstance(selected, dict) else 0.0,
        "scanner_bias_applied": bool(scanner_bias_applied),
        "scanner_bias_summary": dict(scanner_bias_summary),
        "scanner_memory_bias_applied": bool(scanner_memory_bias_applied),
        "scanner_memory_bias": dict(scanner_memory_bias),
        "scanner_memory_bias_summary": dict(scanner_memory_bias_summary),
        "commander_memory_application_trace": dict(commander_memory_application_trace),
        "scanner_memory_application_trace": dict(commander_memory_application_trace),
        "candidate_bias_adjustments": list(candidate_bias_adjustments),
        "candidate_memory_bias_adjustments": list(candidate_memory_bias_adjustments),
        "candidate_symbol_prior_adjustments": list(candidate_symbol_prior_adjustments),
        "selection_reason_with_bias": selection_reason_with_bias,
        "shadow_used": bool(scanner_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(scanner_policy_trace.get("strategist_fallback_used")),
        "policy_provenance_ref": dict(scanner_policy_trace.get("policy_provenance_ref") or {}),
        "selected_asset_class_detected": str((selected or {}).get("asset_class_detected") or "") if isinstance(selected, dict) else "",
        "selected_asset_detection_source": str((selected or {}).get("detection_source") or "") if isinstance(selected, dict) else "",
        "selected_asset_detection_field": str((selected or {}).get("detection_field") or "") if isinstance(selected, dict) else "",
    }
    if isinstance(state.get("scanner_output"), dict):
        state["scanner_output"]["selection_summary"] = selection_summary
        state["scanner_output"]["selected_rank"] = int(selected_rank)
        state["scanner_output"]["selected_score_total"] = float(selected_score_total)
        state["scanner_output"]["margin_vs_second"] = float(margin_vs_second)
        state["scanner_output"]["critical_positive_factors"] = list(critical_positive_factors)
        state["scanner_output"]["critical_negative_factors"] = list(critical_negative_factors)
        state["scanner_output"]["rejected_candidates"] = list(runner_up_reasons)
        state["scanner_output"]["scanner_bias_applied"] = bool(scanner_bias_applied)
        state["scanner_output"]["scanner_bias_summary"] = dict(scanner_bias_summary)
        state["scanner_output"]["scanner_memory_bias_applied"] = bool(scanner_memory_bias_applied)
        state["scanner_output"]["scanner_memory_bias"] = dict(scanner_memory_bias)
        state["scanner_output"]["scanner_memory_bias_summary"] = dict(scanner_memory_bias_summary)
        state["scanner_output"]["commander_memory_application_trace"] = dict(commander_memory_application_trace)
        state["scanner_output"]["scanner_memory_application_trace"] = dict(commander_memory_application_trace)
        state["scanner_output"]["candidate_bias_adjustments"] = list(candidate_bias_adjustments)
        state["scanner_output"]["candidate_memory_bias_adjustments"] = list(candidate_memory_bias_adjustments)
        state["scanner_output"]["candidate_symbol_prior_adjustments"] = list(candidate_symbol_prior_adjustments)
        state["scanner_output"]["selection_reason_with_bias"] = selection_reason_with_bias
        state["scanner_output"]["entry_compatibility_score"] = float(_to_float((selected or {}).get("entry_compatibility_score"))) if isinstance(selected, dict) else 0.0
        state["scanner_output"]["compatibility_bias"] = float(_to_float((selected or {}).get("compatibility_bias"))) if isinstance(selected, dict) else 0.0
        state["scanner_output"]["compatibility_components"] = dict((selected or {}).get("compatibility_components") or {}) if isinstance(selected, dict) else {}
        state["scanner_output"]["scanner_chart_fit_score"] = float(_to_float((selected or {}).get("scanner_chart_fit_score"))) if isinstance(selected, dict) else 0.0
        state["scanner_output"]["scanner_chart_fit_authority"] = str((selected or {}).get("scanner_chart_fit_authority") or "") if isinstance(selected, dict) else ""
        state["scanner_output"]["scanner_chart_fit_components"] = dict((selected or {}).get("scanner_chart_fit_components") or {}) if isinstance(selected, dict) else {}
        state["scanner_output"]["scanner_macro_chart_fit_score"] = float(_to_float((selected or {}).get("scanner_macro_chart_fit_score"), 0.5)) if isinstance(selected, dict) else 0.5
        state["scanner_output"]["scanner_macro_chart_fit_bias"] = float(_to_float((selected or {}).get("scanner_macro_chart_fit_bias"))) if isinstance(selected, dict) else 0.0
        state["scanner_output"]["scanner_macro_chart_fit_authority"] = str((selected or {}).get("scanner_macro_chart_fit_authority") or "") if isinstance(selected, dict) else ""
        state["scanner_output"]["scanner_macro_chart_fit_components"] = dict((selected or {}).get("scanner_macro_chart_fit_components") or {}) if isinstance(selected, dict) else {}
        state["scanner_output"]["expected_monitor_block_reason"] = str((selected or {}).get("expected_monitor_block_reason") or "") if isinstance(selected, dict) else ""
        state["scanner_output"]["dominant_block_reason"] = str((selected or {}).get("dominant_block_reason") or compatibility_bias_context.get("dominant_block_reason") or "")
        state["scanner_output"]["dominant_block_reason_ratio"] = float(_to_float((selected or {}).get("dominant_block_reason_ratio") or compatibility_bias_context.get("dominant_block_reason_ratio")))
        state["scanner_output"]["market_representative_guard_enabled"] = bool(market_representative_guard_meta.get("enabled"))
        state["scanner_output"]["market_representative_guard_applied"] = bool(market_representative_guard_meta.get("applied"))
        state["scanner_output"]["market_representative_guard_policy"] = dict(market_representative_guard_meta.get("policy") or {})
        state["scanner_output"]["market_representative_guard_symbol"] = str(market_representative_guard_meta.get("symbol") or "")
        state["scanner_output"]["market_representative_guard_penalty"] = float(_to_float(market_representative_guard_meta.get("penalty")))
        state["scanner_output"]["market_representative_guard_score_gap"] = float(_to_float(market_representative_guard_meta.get("score_gap")))
        state["scanner_output"]["market_representative_guard_reason"] = str(
            market_representative_guard_meta.get("reason")
            or market_representative_guard_meta.get("skipped_reason")
            or ""
        )
        state["scanner_output"]["market_representative_guard_top_value_dominance"] = bool(market_representative_guard_meta.get("top_value_dominance"))
        state["scanner_output"]["market_representative_guard_confirmation_sources"] = list(market_representative_guard_meta.get("confirmation_sources") or [])
        state["scanner_output"]["market_representative_guard_before_top"] = list(market_representative_guard_meta.get("before_top") or [])
        state["scanner_output"]["market_representative_guard_after_top"] = list(market_representative_guard_meta.get("after_top") or [])
        state["scanner_output"]["blocker_family_concentration_applied"] = bool(blocker_family_overlay_meta.get("applied"))
        state["scanner_output"]["blocker_family_concentration_family"] = str(blocker_family_overlay_meta.get("family") or "")
        state["scanner_output"]["blocker_family_concentration_penalty"] = float(_to_float(blocker_family_overlay_meta.get("penalty")))
        state["scanner_output"]["blocker_family_concentration_top3_before"] = list(blocker_family_overlay_meta.get("top3_symbols_before") or [])
        state["scanner_output"]["blocker_family_concentration_top3_after"] = list(blocker_family_overlay_meta.get("top3_symbols_after") or [])
        state["scanner_output"]["blocker_family_concentration_alternative_symbols"] = list(blocker_family_overlay_meta.get("alternative_symbols") or [])
        state["scanner_output"]["selection_vetoed"] = bool(blocker_family_overlay_meta.get("selection_vetoed"))
        state["scanner_output"]["selection_veto_enforced"] = bool(selection_veto_enforced)
        state["scanner_output"]["selection_veto_reason"] = str(blocker_family_overlay_meta.get("selection_veto_reason") or "")
        state["scanner_output"]["bias_scale"] = float(_to_float((selected or {}).get("bias_scale") or compatibility_bias_context.get("bias_scale")))
        state["scanner_output"]["soft_penalty"] = float(_to_float((selected or {}).get("soft_penalty")))
        state["scanner_output"]["compatibility_score_pre_penalty"] = float(_to_float((selected or {}).get("compatibility_score_pre_penalty")))
        state["scanner_output"]["compatibility_score_post_penalty"] = float(_to_float((selected or {}).get("compatibility_score_post_penalty")))
        state["scanner_output"]["compatibility_trace"] = dict((selected or {}).get("compatibility_trace") or {}) if isinstance(selected, dict) else {}
        state["scanner_output"]["pre_adjust_score_total"] = float(_to_float((selected or {}).get("pre_adjust_score_total"))) if isinstance(selected, dict) else 0.0
        state["scanner_output"]["post_adjust_score_total"] = float(_to_float((selected or {}).get("post_adjust_score_total") or (selected or {}).get("score_total") or (selected or {}).get("score"))) if isinstance(selected, dict) else 0.0
        state["scanner_output"]["quote_data_diagnostic"] = dict(state.get("scanner_quote_diagnostic") or {})
        state["scanner_output"]["selected_asset_class_detected"] = str((selected or {}).get("asset_class_detected") or "") if isinstance(selected, dict) else ""
        state["scanner_output"]["selected_asset_detection_source"] = str((selected or {}).get("detection_source") or "") if isinstance(selected, dict) else ""
        state["scanner_output"]["selected_asset_detection_field"] = str((selected or {}).get("detection_field") or "") if isinstance(selected, dict) else ""
    state["scanner_margin_vs_second"] = float(margin_vs_second)
    _emit_scanner_event(
        state,
        name="candidate_pool_snapshot",
        payload={
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "candidate_pool_before_filter": int(pool_meta.get("candidate_pool_before_filter") or 0),
            "candidate_pool_after_filter": int(pool_meta.get("candidate_pool_after_filter") or len(scan_results_sorted)),
            "asset_universe_policy": str(pool_meta.get("asset_universe_policy") or ""),
            "asset_universe_policy_source": str(pool_meta.get("asset_universe_policy_source") or ""),
            "excluded_candidate_count_by_asset_policy": int(pool_meta.get("asset_policy_excluded_count") or 0),
            "excluded_symbols_by_asset_policy": list(pool_meta.get("asset_policy_excluded_symbols") or []),
            "asset_detection_stats": dict(pool_meta.get("asset_detection_stats") or {}),
            "unknown_asset_candidate_count": int(pool_meta.get("unknown_asset_candidate_count") or 0),
            "total_candidates_before_filter": int(pool_meta.get("total_candidates_before_filter") or 0),
            "total_candidates_after_filter": int(pool_meta.get("total_candidates_after_filter") or 0),
            "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
            "avoid_filter_applied": bool(pool_meta.get("avoid_filter_applied")),
            "avoid_filter_reason": str(pool_meta.get("avoid_filter_reason") or ""),
            "avoid_filter_fallback_used": bool(pool_meta.get("avoid_filter_fallback_used")),
            "source_mix": dict(pool_meta.get("pool_source_mix") or {}),
            "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            "candidate_symbols": [str((row or {}).get("symbol") or "") for row in list(scan_results_sorted or [])[:10] if isinstance(row, dict)],
            "fallback_reason": str(pool_meta.get("fallback_reason") or ""),
            "backfill_used": bool(pool_meta.get("backfill_used")),
            "backfill_count": int(pool_meta.get("backfill_count") or 0),
            "scan_aggressiveness": float(_to_float(pool_meta.get("scan_aggressiveness"))),
            "strict_mode_relaxed_by_scan_aggressiveness": bool(pool_meta.get("strict_mode_relaxed_by_scan_aggressiveness")),
            "aggressive_source_expansion_used": bool(pool_meta.get("aggressive_source_expansion_used")),
            "aggressive_source_expansion_sources": list(pool_meta.get("aggressive_source_expansion_sources") or []),
            "market_representative_guard_applied": bool(market_representative_guard_meta.get("applied")),
            "market_representative_guard_symbol": str(market_representative_guard_meta.get("symbol") or ""),
            "market_representative_guard_reason": str(
                market_representative_guard_meta.get("reason")
                or market_representative_guard_meta.get("skipped_reason")
                or ""
            ),
            "blocker_family_concentration_applied": bool(blocker_family_overlay_meta.get("applied")),
            "blocker_family_concentration_family": str(blocker_family_overlay_meta.get("family") or ""),
            "selection_vetoed": bool(blocker_family_overlay_meta.get("selection_vetoed")),
            "selection_veto_enforced": bool(selection_veto_enforced),
            "selection_veto_reason": str(blocker_family_overlay_meta.get("selection_veto_reason") or ""),
        },
    )
    candidate_ranking_table_payload = _build_candidate_ranking_table_payload(ranking_table)
    state["scanner_candidate_ranking_table"] = dict(candidate_ranking_table_payload)
    state["scanner_output"]["scanner_intrinsic_control_top10"] = list(
        candidate_ranking_table_payload.get("scanner_intrinsic_control_top10") or []
    )
    _emit_scanner_event(
        state,
        name="candidate_ranking_table",
        payload=candidate_ranking_table_payload,
        symbol=str((selected or {}).get("symbol") or ""),
    )
    try:
        from libs.runtime.q9_decision_snapshots import capture_scanner_decision_snapshot

        state["q9_scanner_snapshot_result"] = capture_scanner_decision_snapshot(state)
    except Exception as exc:
        state["q9_scanner_snapshot_result"] = {
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
        }
    candidate_selection_reason_payload = _build_candidate_selection_reason_payload(
        selected=selected if isinstance(selected, dict) else None,
        selected_symbol=selected_symbol,
        selected_rank=selected_rank,
        selected_score_total=selected_score_total,
        margin_vs_second=margin_vs_second,
        critical_positive_factors=critical_positive_factors,
        critical_negative_factors=critical_negative_factors,
        selection_summary=selection_summary,
        scanner_policy_trace=scanner_policy_trace,
        playbook=playbook,
        compatibility_bias_context=compatibility_bias_context,
        market_representative_guard_meta=market_representative_guard_meta,
        blocker_family_overlay_meta=blocker_family_overlay_meta,
        selection_veto_enforced=selection_veto_enforced,
        scanner_bias_applied=scanner_bias_applied,
        scanner_memory_bias_applied=scanner_memory_bias_applied,
        scanner_memory_bias=scanner_memory_bias,
        commander_memory_application_trace=commander_memory_application_trace,
        candidate_bias_adjustments=candidate_bias_adjustments,
        candidate_memory_bias_adjustments=candidate_memory_bias_adjustments,
        candidate_symbol_prior_adjustments=candidate_symbol_prior_adjustments,
        selection_reason_with_bias=selection_reason_with_bias,
        runner_up_reasons=runner_up_reasons,
    )
    state["scanner_candidate_selection_reason"] = dict(candidate_selection_reason_payload)
    _emit_scanner_event(
        state,
        name="candidate_selection_reason",
        payload=candidate_selection_reason_payload,
        symbol=str((selected or {}).get("symbol") or ""),
    )
    _emit_scanner_event(
        state,
        name="selection_output",
        payload={
            "selected_symbol": state.get("top_stock") or None,
            "scanner_selected_symbol": selected_symbol,
            "scanner_rank": int(selected_rank),
            "scanner_score_total": float(selected_score_total),
            "scanner_score_breakdown": dict((selected or {}).get("score_breakdown") or {}) if isinstance(selected, dict) else {},
            "scanner_top_candidates": ranking_table[:3],
            "candidate_count": int(len(scan_results_sorted)),
            "selected_asset_class_detected": str((selected or {}).get("asset_class_detected") or "") if isinstance(selected, dict) else "",
            "selected_asset_detection_source": str((selected or {}).get("detection_source") or "") if isinstance(selected, dict) else "",
            "ranking_top_n": ranking_table,
            "selected_candidate": selected_snapshot,
        },
        symbol=str((selected or {}).get("symbol") or ""),
    )

    _log_scanner_summary(
        state,
        {
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "candidate_pool_before_filter": int(pool_meta.get("candidate_pool_before_filter") or 0),
            "candidate_pool_after_filter": int(pool_meta.get("candidate_pool_after_filter") or len(scan_results_sorted)),
            "asset_universe_policy": str(pool_meta.get("asset_universe_policy") or ""),
            "asset_universe_policy_source": str(pool_meta.get("asset_universe_policy_source") or ""),
            "excluded_candidate_count_by_asset_policy": int(pool_meta.get("asset_policy_excluded_count") or 0),
            "asset_detection_stats": dict(pool_meta.get("asset_detection_stats") or {}),
            "unknown_asset_candidate_count": int(pool_meta.get("unknown_asset_candidate_count") or 0),
            "total_candidates_before_filter": int(pool_meta.get("total_candidates_before_filter") or 0),
            "total_candidates_after_filter": int(pool_meta.get("total_candidates_after_filter") or 0),
            "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
            "fallback_reason": str(pool_meta.get("fallback_reason") or ""),
            "blocked_static_fallback": bool(pool_meta.get("blocked_static_fallback")),
            "strict_kiwoom_only": bool(pool_meta.get("strict_kiwoom_only")),
            "backfill_used": bool(pool_meta.get("backfill_used")),
            "backfill_count": int(pool_meta.get("backfill_count") or 0),
            "scan_aggressiveness": float(_to_float(pool_meta.get("scan_aggressiveness"))),
            "strict_mode_relaxed_by_scan_aggressiveness": bool(pool_meta.get("strict_mode_relaxed_by_scan_aggressiveness")),
            "aggressive_source_expansion_used": bool(pool_meta.get("aggressive_source_expansion_used")),
            "aggressive_source_expansion_sources": list(pool_meta.get("aggressive_source_expansion_sources") or []),
            "top_stock": state.get("top_stock"),
            "top_score": top_score,
            "scanner_selected_symbol": selected_symbol,
            "scanner_rank": int(selected_rank),
            "scanner_score_total": float(selected_score_total),
            "scanner_score_breakdown": dict((selected or {}).get("score_breakdown") or {}) if isinstance(selected, dict) else {},
            "scanner_top_candidates": ranking_table[:3],
            "top_ranked_symbols": [str(x.get("symbol") or "") for x in visible_ranked_candidates],
            "strategist_scanner_priority": list(scanner_priority),
            "strategist_scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            "condition_search_status": str(pool_meta.get("condition_search_status") or ""),
            "condition_search_source": str(pool_meta.get("condition_search_source") or ""),
            "condition_search_reason": str(pool_meta.get("condition_search_reason") or ""),
            "strategist_playbook": playbook or "",
            "strategist_scanner_bias": scanner_bias or "",
            "strategist_avoid_themes": list(pool_meta.get("avoid_themes") or []),
            "strategist_trade_aggressiveness": trade_aggressiveness or "",
            "strategist_risk_tone": risk_tone or "",
            "recent_scanner_selected_count": int(len(_scanner_recent_selection_history(state))),
            "scanner_bias_applied": bool(scanner_bias_applied),
            "scanner_bias_summary": dict(scanner_bias_summary),
            "scanner_memory_bias_applied": bool(scanner_memory_bias_applied),
            "scanner_memory_bias_summary": dict(scanner_memory_bias_summary),
            "market_representative_guard_applied": bool(market_representative_guard_meta.get("applied")),
            "market_representative_guard_symbol": str(market_representative_guard_meta.get("symbol") or ""),
            "market_representative_guard_reason": str(
                market_representative_guard_meta.get("reason")
                or market_representative_guard_meta.get("skipped_reason")
                or ""
            ),
            "blocker_family_concentration_applied": bool(blocker_family_overlay_meta.get("applied")),
            "blocker_family_concentration_family": str(blocker_family_overlay_meta.get("family") or ""),
            "selection_vetoed": bool(blocker_family_overlay_meta.get("selection_vetoed")),
            "selection_veto_enforced": bool(selection_veto_enforced),
            "selection_veto_reason": str(blocker_family_overlay_meta.get("selection_veto_reason") or ""),
        },
    )

    top_candidates_summary: List[Dict[str, Any]] = []
    for row in list(state.get("ranked_candidates") or [])[:3]:
        if not isinstance(row, dict):
            continue
        top_candidates_summary.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "score_total": float(_to_float(row.get("score_total"))),
                "risk_score": float(_to_float(row.get("risk_score"))),
            }
        )
    append_decision_trace(
        state,
        agent="scanner",
        event="candidate_selection",
        payload={
            "playbook": playbook or "",
            "scanner_priority": list(scanner_priority),
            "scanner_bias_applied": bool(scanner_bias_applied),
            "scanner_bias_summary": dict(scanner_bias_summary),
            "scanner_memory_bias_applied": bool(scanner_memory_bias_applied),
            "scanner_memory_bias": dict(scanner_memory_bias),
            "scanner_memory_bias_summary": dict(scanner_memory_bias_summary),
            "commander_memory_application_trace": dict(commander_memory_application_trace),
            "scanner_memory_application_trace": dict(commander_memory_application_trace),
            "candidate_bias_adjustments": list(candidate_bias_adjustments),
            "candidate_memory_bias_adjustments": list(candidate_memory_bias_adjustments),
            "selection_reason_with_bias": selection_reason_with_bias,
            "candidate_source": str(pool_meta.get("candidate_source") or ""),
            "asset_universe_policy": str(pool_meta.get("asset_universe_policy") or ""),
            "excluded_candidate_count_by_asset_policy": int(pool_meta.get("asset_policy_excluded_count") or 0),
            "asset_detection_stats": dict(pool_meta.get("asset_detection_stats") or {}),
            "unknown_asset_candidate_count": int(pool_meta.get("unknown_asset_candidate_count") or 0),
            "kiwoom_pool_source_mix": dict(pool_meta.get("pool_source_mix") or {}),
            "condition_search_status": str(pool_meta.get("condition_search_status") or ""),
            "condition_search_source": str(pool_meta.get("condition_search_source") or ""),
            "condition_search_reason": str(pool_meta.get("condition_search_reason") or ""),
            "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
            "candidate_pool_size": int(len(scan_results_sorted)),
            "recent_scanner_selected_count": int(len(_scanner_recent_selection_history(state))),
            "top_candidates": top_candidates_summary,
            "selected_symbol": state.get("top_stock") or None,
            "aggressive_source_expansion_used": bool(pool_meta.get("aggressive_source_expansion_used")),
            "aggressive_source_expansion_sources": list(pool_meta.get("aggressive_source_expansion_sources") or []),
            "market_representative_guard_applied": bool(market_representative_guard_meta.get("applied")),
            "market_representative_guard_symbol": str(market_representative_guard_meta.get("symbol") or ""),
            "market_representative_guard_reason": str(
                market_representative_guard_meta.get("reason")
                or market_representative_guard_meta.get("skipped_reason")
                or ""
            ),
            "blocker_family_concentration_applied": bool(blocker_family_overlay_meta.get("applied")),
            "blocker_family_concentration_family": str(blocker_family_overlay_meta.get("family") or ""),
            "selection_vetoed": bool(blocker_family_overlay_meta.get("selection_vetoed")),
            "selection_veto_enforced": bool(selection_veto_enforced),
            "selection_veto_reason": str(blocker_family_overlay_meta.get("selection_veto_reason") or ""),
            "score_breakdown_summary": (
                dict(selected.get("score_breakdown") or {})
                if isinstance(selected, dict)
                else {}
            ),
            "selected_candidate": _compact_selected_snapshot(selected if isinstance(selected, dict) else None),
        },
    )
    try:
        record_decision_bridge(
            run_id=run_id,
            agent="scanner",
            stage="decision_bridge",
            raw_input={
                "candidate_pool_size": int(len(scan_results_sorted)),
                "candidate_source": str(pool_meta.get("candidate_source") or ""),
                "theme_filter_applied": bool(pool_meta.get("theme_filter_applied")),
                "scanner_source_policy": dict(pool_meta.get("scanner_source_policy") or {}),
                "aggressive_source_expansion_used": bool(pool_meta.get("aggressive_source_expansion_used")),
                "aggressive_source_expansion_sources": list(pool_meta.get("aggressive_source_expansion_sources") or []),
            },
            parsed_output={
                "selected_symbol": state.get("top_stock") or None,
                "top_score": float(_to_float(top_score) if top_score is not None else 0.0),
                "ranked_candidates": visible_ranked_candidates,
                "selected_candidate": _compact_selected_snapshot(selected if isinstance(selected, dict) else None),
            },
            decision_link={
                "decision_chain": {
                    "theme": str((state.get("themes") or [""])[0] if isinstance(state.get("themes"), list) and state.get("themes") else ""),
                    "scanner_selected": state.get("top_stock") or None,
                }
            },
        )
    except Exception:
        pass
    try:
        write_scanner_artifact(state)
    except Exception:
        pass

    return state
