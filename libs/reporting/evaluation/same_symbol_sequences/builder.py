from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _epoch(value: Any) -> int:
    try:
        return int(datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return 0


def _q9_windows(reports_root: Path, day: str) -> dict[str, dict[str, Any]]:
    payload = _read(reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json")
    return {
        str(row.get("decision_id") or ""): dict(row)
        for row in payload.get("windows") or []
        if isinstance(row, Mapping) and row.get("decision_id")
    }


def _candidate_evidence(window: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    universe = window.get("scanner_pre_strategist_universe")
    universe = universe if isinstance(universe, Mapping) else {}
    candidate = next((row for row in universe.get("intrinsic_ranked_top20") or [] if isinstance(row, Mapping) and str(row.get("symbol") or "") == symbol), {})
    breakdown = candidate.get("score_breakdown") if isinstance(candidate, Mapping) else {}
    breakdown = breakdown if isinstance(breakdown, Mapping) else {}
    compact = candidate.get("compact_feature_snapshot") if isinstance(candidate, Mapping) else {}
    compact = compact if isinstance(compact, Mapping) else {}
    volume = float(breakdown.get("volume_surge") or 0.0) > 0.0
    vwap = compact.get("above_vwap") is True or float(breakdown.get("vwap_alignment") or 0.0) > 0.0
    breakout = float(breakdown.get("momentum") or 0.0) > 0.0 and float(breakdown.get("intraday_strength") or 0.0) > 0.0
    return {
        "available": bool(candidate),
        "rank": candidate.get("rank") if isinstance(candidate, Mapping) else None,
        "score_total": candidate.get("score_total") if isinstance(candidate, Mapping) else None,
        "fresh_volume_confirmation": volume,
        "fresh_vwap_confirmation": vwap,
        "fresh_breakout_confirmation": breakout,
        "fresh_evidence_count": sum((volume, vwap, breakout)),
    }


def load_day_trades(reports_root: Path, day: str) -> list[dict[str, Any]]:
    rows = []
    root = reports_root / "evaluation" / "trades" / day
    for path in sorted(root.glob("*/trade_read_model.json")) if root.exists() else []:
        model = _read(path)
        entry = model.get("entry") if isinstance(model.get("entry"), Mapping) else {}
        exit_data = model.get("exit") if isinstance(model.get("exit"), Mapping) else {}
        outcome = model.get("outcome") if isinstance(model.get("outcome"), Mapping) else {}
        selection = model.get("selection") if isinstance(model.get("selection"), Mapping) else {}
        rows.append({
            "trade_id": str(model.get("trade_id") or path.parent.name),
            "day": day,
            "symbol": str(model.get("symbol") or ""),
            "status": str(model.get("status") or ""),
            "entry_timestamp": entry.get("timestamp"),
            "entry_price": _number(entry.get("price")),
            "entry_quantity": entry.get("quantity"),
            "entry_reason": entry.get("reason"),
            "exit_timestamp": exit_data.get("timestamp"),
            "exit_price": _number(exit_data.get("price")),
            "exit_quantity": exit_data.get("quantity"),
            "exit_reason": exit_data.get("reason"),
            "broker_authoritative": bool(exit_data.get("broker_authoritative")),
            "net_return_pct": _number(outcome.get("net_return_pct")),
            "realized_pnl": _number(outcome.get("realized_pnl")),
            "holding_seconds": _number(outcome.get("holding_seconds")),
            "q9_decision_id": str(selection.get("q9_decision_id") or ""),
            "strategy_horizon": (model.get("horizon_contract") or {}).get("strategy_horizon") if isinstance(model.get("horizon_contract"), Mapping) else "",
            "integrity": dict(model.get("integrity") or {}),
            "source_path": str(path),
        })
    return rows


def build_day_sequences(*, reports_root: Path, day: str) -> list[dict[str, Any]]:
    windows = _q9_windows(reports_root, day)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in load_day_trades(reports_root, day):
        if row.get("symbol"):
            grouped[str(row["symbol"])].append(row)
    result = []
    for symbol, trades in sorted(grouped.items()):
        ordered = sorted(trades, key=lambda row: str(row.get("entry_timestamp") or ""))
        running = peak = 0.0
        enriched = []
        prior = None
        first_profit = None
        prior_full_loss_seen = False
        for ordinal, trade in enumerate(ordered, 1):
            value = _number(trade.get("net_return_pct"))
            before = running
            if value is not None:
                running += value
                peak = max(peak, running)
                if first_profit is None and value > 0:
                    first_profit = value
            decision_id = str(trade.get("q9_decision_id") or "")
            evidence = _candidate_evidence(windows.get(decision_id) or {}, symbol)
            seconds_since_prior_exit = None
            if prior:
                start = _epoch(trade.get("entry_timestamp"))
                end = _epoch(prior.get("exit_timestamp"))
                seconds_since_prior_exit = start - end if start and end else None
            clean_provenance = bool(
                ordinal > 1 and prior and prior.get("q9_decision_id") and decision_id
                and prior.get("exit_timestamp") and trade.get("entry_timestamp")
                and prior.get("net_return_pct") is not None and value is not None
            )
            current_policy_would_have_blocked = bool(ordinal > 1 and prior_full_loss_seen)
            enriched_row = {
                **trade,
                "trade_ordinal": ordinal,
                "prior_trade_id": prior.get("trade_id") if prior else None,
                "prior_exit_outcome": (
                    "PROFIT" if prior and float(prior.get("net_return_pct") or 0) > 0
                    else "LOSS" if prior and float(prior.get("net_return_pct") or 0) < 0
                    else "FLAT_OR_UNKNOWN" if prior else "NOT_APPLICABLE"
                ),
                "seconds_since_prior_exit": seconds_since_prior_exit,
                "prior_q9_decision_id": prior.get("q9_decision_id") if prior else None,
                "decision_changed": bool(prior and prior.get("q9_decision_id") != decision_id),
                "point_in_time_fresh_evidence": evidence,
                "new_independent_episode": "UNKNOWN" if ordinal > 1 else "NOT_APPLICABLE",
                "provenance_status": "CLEAN_PARTIAL" if clean_provenance else "INSUFFICIENT_EVIDENCE" if ordinal > 1 else "NOT_APPLICABLE",
                "current_loss_reentry_policy_would_have_blocked": current_policy_would_have_blocked,
                "profit_exit_reentry_policy_relevant": bool(
                    clean_provenance
                    and not current_policy_would_have_blocked
                    and prior
                    and float(prior.get("net_return_pct") or 0.0) > 0.0
                ),
                "cumulative_return_before_pct": round(before, 4),
                "cumulative_return_after_pct": round(running, 4),
                "peak_cumulative_return_pct": round(peak, 4),
                "profit_giveback_pct": round(max(0.0, peak - running), 4),
            }
            enriched.append(enriched_row)
            prior = enriched_row
            if value is not None and value < 0.0:
                prior_full_loss_seen = True
        giveback = max(0.0, peak - running)
        result.append({
            "day_symbol_sequence_id": f"{day}:{symbol}",
            "day": day,
            "symbol": symbol,
            "trade_count": len(enriched),
            "repeat_count": max(0, len(enriched) - 1),
            "first_profitable_exit_pct": first_profit,
            "cumulative_return_pct": round(running, 4),
            "maximum_cumulative_return_pct": round(peak, 4),
            "profit_giveback_pct": round(giveback, 4),
            "profit_giveback_ratio": round(giveback / first_profit, 4) if first_profit and first_profit > 0 else None,
            "clean_profit_exit_reentry_count": sum(
                bool(row.get("profit_exit_reentry_policy_relevant"))
                for row in enriched
            ),
            "trades": enriched,
        })
    return result


__all__ = ["build_day_sequences", "load_day_trades"]
