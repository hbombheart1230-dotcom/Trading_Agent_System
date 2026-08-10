from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.evaluation.cost_basis_comparison import build_evaluation_cost_bases
from libs.reporting.evaluation.metrics import performance_metrics
from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .candle_provider import load_opening_candles
from .contracts import HORIZONS


KST = timezone(timedelta(hours=9))
MINIMUM_FRESH_TRIGGERS = 12
MINIMUM_DAYS = 5
MAXIMUM_CONCENTRATION = 0.25
MAX_FORWARD_DELAY_SEC = 180


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _fresh_triggers(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for watch in payload.get("rows") or []:
        if not isinstance(watch, Mapping):
            continue
        candidates = []
        for redetection in watch.get("redetections") or []:
            if not isinstance(redetection, Mapping):
                continue
            fresh = redetection.get("first_signal_evidence")
            if isinstance(fresh, Mapping):
                candidates.append(dict(fresh))
        if not candidates:
            continue
        fresh = min(candidates, key=lambda row: int(row.get("decision_epoch") or 0))
        rows.append({
            "watch_id": str(watch.get("watch_id") or ""),
            "initial_episode_id": watch.get("initial_episode_id"),
            "initial_day": watch.get("initial_day"),
            "symbol": str(watch.get("symbol") or ""),
            "trigger_day": str(fresh.get("day") or ""),
            "trigger_decision_id": fresh.get("decision_id"),
            "trigger_epoch": int(fresh.get("decision_epoch") or 0),
            "trigger_time_kst": fresh.get("decision_time_kst"),
            "rank": fresh.get("rank"),
            "score_total": fresh.get("score_total"),
            "confidence": fresh.get("confidence"),
            "risk_score": fresh.get("risk_score"),
            "signal_evidence": dict(fresh.get("signal_evidence") or {}),
            "reference_quote_price": fresh.get("reference_price"),
            "behavior_effect": "observation_only",
        })
    return sorted(rows, key=lambda row: (str(row["trigger_day"]), int(row["trigger_epoch"]), str(row["symbol"])))


def _cache_read(root: Path, day: str, symbols: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    result = {}
    for symbol in symbols:
        try:
            payload = json.loads((root / day / f"{symbol}.json").read_text(encoding="utf-8"))
            result[symbol] = [dict(row) for row in payload.get("rows") or [] if isinstance(row, Mapping)]
        except (OSError, ValueError):
            result[symbol] = []
    return result


def _cache_write(root: Path, day: str, candles: Mapping[str, list[Mapping[str, Any]]]) -> None:
    target = root / day
    target.mkdir(parents=True, exist_ok=True)
    for symbol, rows in candles.items():
        if rows:
            (target / f"{symbol}.json").write_text(
                json.dumps({"schema_version": "latent_reactivation_candles.v1", "day": day, "symbol": symbol, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


def _row_epoch(row: Mapping[str, Any]) -> int:
    try:
        return int(row.get("ts") or 0)
    except (TypeError, ValueError):
        return 0


def _observe(row: dict[str, Any], candles: list[Mapping[str, Any]]) -> dict[str, Any]:
    trigger_epoch = int(row.get("trigger_epoch") or 0)
    entry = next((value for value in candles if _row_epoch(value) > trigger_epoch), None)
    if entry is None:
        return {**row, "forward_status": "MISSING_FORWARD_PRICE", "forward_reason": "next_tradable_minute_unavailable"}
    entry_epoch = _row_epoch(entry)
    entry_price = _number(entry.get("open")) or _number(entry.get("close"))
    if entry_price is None or entry_price <= 0:
        return {**row, "forward_status": "MISSING_FORWARD_PRICE", "forward_reason": "reference_entry_price_unavailable"}
    checkpoints: dict[str, Any] = {}
    for horizon in HORIZONS:
        if horizon == "EOD":
            usable = [value for value in candles if _row_epoch(value) >= entry_epoch and datetime.fromtimestamp(_row_epoch(value), KST).time() >= datetime.strptime("15:20", "%H:%M").time()]
            target = usable[-1] if usable else None
            window = [value for value in candles if entry_epoch <= _row_epoch(value) <= _row_epoch(target)] if target else []
        else:
            minutes = int(horizon[1:-1])
            target_epoch = entry_epoch + minutes * 60
            target = next((value for value in candles if _row_epoch(value) >= target_epoch), None)
            if target and _row_epoch(target) - target_epoch > MAX_FORWARD_DELAY_SEC:
                target = None
            window = [value for value in candles if entry_epoch <= _row_epoch(value) <= target_epoch]
        if target is None:
            checkpoints[horizon] = {"status": "pending"}
            continue
        close = _number(target.get("close")) or entry_price
        window = window or [target]
        high = max(_number(value.get("high")) or entry_price for value in window)
        low = min(_number(value.get("low")) or entry_price for value in window)
        checkpoints[horizon] = {
            "status": "observed",
            "gross_return_pct": round((close / entry_price - 1.0) * 100.0, 4),
            "mfe_pct": round((high / entry_price - 1.0) * 100.0, 4),
            "mae_pct": round((low / entry_price - 1.0) * 100.0, 4),
            "exit_price": close,
            "observed_epoch": _row_epoch(target),
        }
    return {
        **row,
        "forward_status": "OBSERVED" if any(value.get("status") == "observed" for value in checkpoints.values()) else "MISSING_FORWARD_PRICE",
        "reference_entry": {"epoch": entry_epoch, "price": entry_price, "source": "next_available_minute_open"},
        "checkpoints": checkpoints,
    }


def _summary(rows: list[Mapping[str, Any]], cost_bases: Mapping[str, Any]) -> dict[str, Any]:
    live_drag = float((cost_bases.get("live_deployment_equity") or {}).get("total_drag_with_slippage_pct") or 0.0)
    mock_drag = float((cost_bases.get("mock_observed") or {}).get("total_drag_with_slippage_pct") or 0.0)
    horizon_rows = {}
    for horizon in HORIZONS:
        gross = [float((row.get("checkpoints") or {}).get(horizon, {}).get("gross_return_pct")) for row in rows if (row.get("checkpoints") or {}).get(horizon, {}).get("status") == "observed"]
        horizon_rows[horizon] = {
            "gross": performance_metrics(gross),
            "live_net": performance_metrics(value - live_drag for value in gross),
            "mock_net": performance_metrics(value - mock_drag for value in gross),
        }
    primary = horizon_rows["+30m"]["live_net"]
    observed = int(primary.get("count") or 0)
    day_counts: dict[str, int] = defaultdict(int)
    symbol_counts: dict[str, int] = defaultdict(int)
    daily_returns: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        point = (row.get("checkpoints") or {}).get("+30m") or {}
        if point.get("status") != "observed":
            continue
        day = str(row.get("trigger_day") or "")
        symbol = str(row.get("symbol") or "")
        value = float(point.get("gross_return_pct")) - live_drag
        day_counts[day] += 1
        symbol_counts[symbol] += 1
        daily_returns[day].append(value)
    positive_day_ratio = sum(sum(values) / len(values) > 0 for values in daily_returns.values()) / len(daily_returns) if daily_returns else 0.0
    largest_day_share = max(day_counts.values(), default=0) / observed if observed else 0.0
    largest_symbol_share = max(symbol_counts.values(), default=0) / observed if observed else 0.0
    gates = {
        "minimum_observed_count": observed >= MINIMUM_FRESH_TRIGGERS,
        "minimum_day_count": len(day_counts) >= MINIMUM_DAYS,
        "positive_expectancy": float(primary.get("average_return_pct") or 0.0) > 0.0,
        "minimum_profit_factor": float(primary.get("profit_factor") or 0.0) >= 1.2,
        "minimum_win_rate": float(primary.get("win_rate") or 0.0) >= 0.5,
        "minimum_positive_day_ratio": positive_day_ratio >= 0.55,
        "maximum_day_concentration": largest_day_share <= MAXIMUM_CONCENTRATION,
        "maximum_symbol_concentration": largest_symbol_share <= MAXIMUM_CONCENTRATION,
    }
    status = "COLLECTING" if observed < MINIMUM_FRESH_TRIGGERS else "ELIGIBLE_FOR_REINJECTION_SHADOW" if all(gates.values()) else "REJECTED"
    return {
        "status": status,
        "fresh_trigger_count": len(rows),
        "observed_30m_count": observed,
        "observed_day_count": len(day_counts),
        "positive_day_ratio": round(positive_day_ratio, 4),
        "largest_day_share": round(largest_day_share, 4),
        "largest_symbol_share": round(largest_symbol_share, 4),
        "decision_at_observed_count": MINIMUM_FRESH_TRIGGERS,
        "gates": gates,
        "horizons": horizon_rows,
    }


def _trigger_day_status(opening_root: Path, day: str) -> str:
    try:
        payload = json.loads(
            (opening_root / day / "opening_rank1_shadow_daily.json").read_text(
                encoding="utf-8"
            )
        )
        return str(payload.get("day_status") or "MISSING")
    except (OSError, ValueError):
        return "MISSING"


def _render(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Latent Reactivation Fresh-Trigger Forward",
        "",
        "- Behavior effect: observation only",
        f"- Status: **{summary.get('status')}**",
        f"- Fresh triggers: {summary.get('fresh_trigger_count', 0)}",
        f"- Excluded by trigger-day integrity: {summary.get('excluded_trigger_count', 0)}",
        f"- Observed +30m: {summary.get('observed_30m_count', 0)} / decision at {summary.get('decision_at_observed_count', 12)}",
        "- Reference entry: next available one-minute candle open",
        "- Original position carry: false",
        "",
        "| Horizon | N | Live win | Live average | Live PF | Mock average |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for horizon, metrics in (summary.get("horizons") or {}).items():
        live = metrics.get("live_net") or {}
        mock = metrics.get("mock_net") or {}
        lines.append(f"| {horizon} | {live.get('count', 0)} | {float(live.get('win_rate') or 0):.1%} | {float(live.get('average_return_pct') or 0):+.4f}% | {float(live.get('profit_factor') or 0):.4f} | {float(mock.get('average_return_pct') or 0):+.4f}% |")
    lines += ["", "This artifact cannot submit an order or reinject a candidate.", ""]
    return "\n".join(lines)


def build_latent_reactivation_forward(
    *, watch_payload: Mapping[str, Any], state_path: Path, output_root: Path,
    allow_fresh_fetch: bool,
) -> dict[str, Any]:
    triggers = _fresh_triggers(watch_payload)
    opening_root = Path(output_root).parent
    excluded = []
    eligible = []
    for row in triggers:
        trigger_status = _trigger_day_status(opening_root, str(row.get("trigger_day") or ""))
        row["trigger_day_integrity_status"] = trigger_status
        if trigger_status != "VALID":
            excluded.append({
                **row,
                "forward_status": "EXCLUDED_TRIGGER_DAY_INTEGRITY",
                "forward_reason": f"opening_day_status:{trigger_status}",
            })
        else:
            eligible.append(row)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        grouped[str(row.get("trigger_day") or "")].append(row)
    cache_root = Path("data/research/opening_rank1_shadow/latent_forward_candles")
    observed = []
    for day, rows in sorted(grouped.items()):
        symbols = tuple(sorted({str(row.get("symbol") or "") for row in rows}))
        candles = _cache_read(cache_root, day, symbols)
        missing = tuple(symbol for symbol in symbols if not candles.get(symbol))
        if missing:
            recovered, _ = load_opening_candles(state_path=state_path, day=day, symbols=missing, allow_fresh_fetch=allow_fresh_fetch)
            candles.update(recovered)
            _cache_write(cache_root, day, recovered)
        observed.extend(_observe(row, candles.get(str(row.get("symbol") or "")) or []) for row in rows)
    cost_bases = build_evaluation_cost_bases(load_broker_cost_profile(None))
    summary = _summary(observed, cost_bases)
    summary["raw_fresh_trigger_count"] = len(triggers)
    summary["excluded_trigger_count"] = len(excluded)
    payload = {
        "schema_version": "latent_reactivation_forward.v1",
        "behavior_effect": "observation_only",
        "through_day": watch_payload.get("through_day"),
        "cost_bases": cost_bases,
        "summary": summary,
        "rows": sorted(observed + excluded, key=lambda row: (str(row.get("trigger_day") or ""), int(row.get("trigger_epoch") or 0))),
        "policy_change_authorized": False,
    }
    json_path = Path(output_root) / "latent_reactivation_forward.json"
    markdown_path = Path(output_root) / "latent_reactivation_forward.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path), "summary": payload["summary"]}


__all__ = ["build_latent_reactivation_forward"]
