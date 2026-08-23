from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from libs.reporting.quant_shadow_forward_outcomes import (
    attach_forward_outcomes,
    load_minute_rows_from_state,
)

from .metrics import performance_metrics


HORIZONS = ("+5m", "+15m", "+30m", "+60m")
LABELS = (
    "ENTRY_TOO_EARLY",
    "ENTRY_TOO_LATE",
    "ENTRY_APPROPRIATE",
    "INSUFFICIENT_EVIDENCE",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _epoch(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        pass
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _iso(epoch: int) -> str:
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _stage_epoch(payload: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = _epoch(payload.get(key))
        if value > 0:
            return value
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _daily_windows_by_id(reports_root: Path, day: str) -> dict[str, dict[str, Any]]:
    path = reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json"
    payload = _read_json(path)
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("windows") or []:
        if not isinstance(row, dict):
            continue
        decision_id = str(row.get("decision_id") or "").strip()
        if decision_id:
            out[decision_id] = dict(row)
    return out


def _candidate_symbol(candidate: Any) -> str:
    return str(candidate.get("symbol") or "").strip() if isinstance(candidate, Mapping) else ""


def _candidate_rank(candidate: Any) -> int | None:
    value = _num(candidate.get("rank") if isinstance(candidate, Mapping) else None)
    return int(value) if value is not None else None


def _row_at_or_before(rows: Sequence[Mapping[str, Any]], epoch: int) -> Mapping[str, Any] | None:
    prior = [row for row in rows if int(row.get("ts") or 0) <= epoch]
    return prior[-1] if prior else None


def _pre_entry_move_pct(
    *,
    symbol: str,
    decision_epoch: int,
    entry_price: float | None,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> tuple[float | None, dict[str, Any]]:
    if not symbol or decision_epoch <= 0 or entry_price is None or entry_price <= 0:
        return None, {"available": False, "reason": "missing_symbol_time_or_entry_price"}
    rows = list(minute_rows_by_symbol.get(symbol) or [])
    base = _row_at_or_before(rows, decision_epoch)
    if not base:
        return None, {"available": False, "reason": "minute_row_before_decision_unavailable"}
    base_price = _num(base.get("close") or base.get("price"))
    if base_price is None or base_price <= 0:
        return None, {"available": False, "reason": "decision_base_price_unavailable"}
    return round(((entry_price / base_price) - 1.0) * 100.0, 4), {
        "available": True,
        "decision_base_price": base_price,
        "decision_base_ts": base.get("raw_ts") or base.get("ts"),
    }


def _entry_forward(
    *,
    trade_id: str,
    symbol: str,
    entry_epoch: int,
    entry_price: float | None,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    if not symbol or entry_epoch <= 0 or entry_price is None or entry_price <= 0:
        return {"available": False, "reason": "entry_baseline_unavailable", "checkpoints": {}}
    rows = attach_forward_outcomes(
        [{
            "symbol": symbol,
            "trade_id": trade_id,
            "generated_at": _iso(entry_epoch),
            "shadow_forward_base": {
                "available": True,
                "baseline_epoch": entry_epoch,
                "baseline_price": entry_price,
                "source": "actual_entry",
            },
        }],
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    outcome = _mapping((rows[0] if rows else {}).get("shadow_forward_outcome"))
    checkpoints = _mapping(outcome.get("checkpoints"))
    return {
        "available": bool(outcome.get("available")),
        "reason": outcome.get("reason"),
        "observed_checkpoint_count": outcome.get("observed_checkpoint_count"),
        "checkpoints": {
            horizon: dict(checkpoints.get(horizon) or {"status": "pending"})
            for horizon in HORIZONS
        },
    }


def _checkpoint(forward: Mapping[str, Any], horizon: str) -> Mapping[str, Any]:
    return _mapping(_mapping(forward.get("checkpoints")).get(horizon))


def _label(
    *,
    scanner_to_entry_delay_sec: int | None,
    pre_entry_move_pct: float | None,
    forward: Mapping[str, Any],
    strategy_horizon: str = "",
) -> tuple[str, list[str]]:
    cp5 = _checkpoint(forward, "+5m")
    cp15 = _checkpoint(forward, "+15m")
    cp30 = _checkpoint(forward, "+30m")
    ret5 = _num(cp5.get("return_pct"))
    mfe5 = _num(cp5.get("mfe_pct"))
    mae5 = _num(cp5.get("mae_pct"))
    ret15 = _num(cp15.get("return_pct"))
    normalized_horizon = str(strategy_horizon or "").strip().lower()
    if normalized_horizon in {"swing", "overnight", "position", "1-2day", "1_2day"}:
        return "INSUFFICIENT_EVIDENCE", ["strategy_horizon_exceeds_entry_timing_observation_window"]
    if normalized_horizon == "intraday":
        ret30 = _num(cp30.get("return_pct"))
        mfe15 = _num(cp15.get("mfe_pct"))
        mae15 = _num(cp15.get("mae_pct"))
        if ret15 is None or ret30 is None or mfe15 is None or mae15 is None:
            return "INSUFFICIENT_EVIDENCE", ["missing_intraday_forward_quality"]
        reasons: list[str] = []
        if pre_entry_move_pct is not None and pre_entry_move_pct >= 0.35 and ret15 <= 0.0 and ret30 <= 0.0:
            return "ENTRY_TOO_LATE", ["pre_entry_move>=0.35pct_then_intraday_forward_weak"]
        if mae15 <= -0.75 and ret15 < 0.0 and (pre_entry_move_pct is None or pre_entry_move_pct < 0.20):
            return "ENTRY_TOO_EARLY", ["intraday_adverse_move_without_prior_alpha"]
        if ret15 > 0.0 or ret30 > 0.0 or mfe15 >= 0.70:
            return "ENTRY_APPROPRIATE", ["favorable_intraday_forward_response"]
        return "INSUFFICIENT_EVIDENCE", ["intraday_forward_weak_but_not_classifiable"]
    if ret5 is None or mfe5 is None or mae5 is None:
        return "INSUFFICIENT_EVIDENCE", ["missing_5m_forward_quality"]
    reasons: list[str] = []
    if scanner_to_entry_delay_sec is not None and scanner_to_entry_delay_sec >= 180:
        reasons.append("scanner_to_entry_delay>=180s")
    if pre_entry_move_pct is not None and pre_entry_move_pct >= 0.35 and (ret5 <= 0.0 or (ret15 is not None and ret15 <= 0.0)):
        reasons.append("pre_entry_move>=0.35pct_then_forward_weak")
        return "ENTRY_TOO_LATE", reasons
    if mae5 <= -0.55 and ret5 < 0.0 and (pre_entry_move_pct is None or pre_entry_move_pct < 0.20):
        reasons.append("immediate_adverse_move_without_prior_alpha")
        return "ENTRY_TOO_EARLY", reasons
    if ret5 > 0.0 or (ret15 is not None and ret15 > 0.0) or mfe5 >= 0.50:
        reasons.append("favorable_forward_response")
        return "ENTRY_APPROPRIATE", reasons
    reasons.append("forward_weak_but_not_classifiable")
    return "INSUFFICIENT_EVIDENCE", reasons


def build_entry_timing_attribution_report(
    *,
    day: str,
    models: Sequence[Mapping[str, Any]],
    reports_root: Path = Path("reports"),
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    rows_by_symbol = (
        minute_rows_by_symbol
        if minute_rows_by_symbol is not None
        else load_minute_rows_from_state()
    )
    windows = _daily_windows_by_id(Path(reports_root), day)
    rows: list[dict[str, Any]] = []
    excluded_count = 0
    for model in models:
        defects = {
            str(value)
            for value in (_mapping(model.get("integrity")).get("defects") or [])
        }
        if "broker_day_partial_exit_duplicate" in defects or "confirmed_runtime_defect" in defects:
            excluded_count += 1
            continue
        trade_id = str(model.get("trade_id") or "")
        symbol = str(model.get("symbol") or "")
        selection = _mapping(model.get("selection"))
        entry = _mapping(model.get("entry"))
        outcome = _mapping(model.get("outcome"))
        horizon_contract = _mapping(model.get("horizon_contract"))
        strategy_horizon = str(
            horizon_contract.get("strategy_horizon")
            or horizon_contract.get("source_strategy_horizon")
            or ""
        )
        decision_id = str(selection.get("q9_decision_id") or "")
        window = windows.get(decision_id, {})
        decision_epoch = int(_num(window.get("decision_epoch")) or _epoch(window.get("generated_at")))
        entry_epoch = _epoch(entry.get("timestamp"))
        entry_price = _num(entry.get("price"))
        scanner_time = decision_epoch
        strategist_payload = _mapping(window.get("strategist_selection"))
        strategist_time = _stage_epoch(
            strategist_payload,
            "generated_at",
            "confirmed_at",
            "updated_at",
            "timestamp",
        )
        selected_time = _stage_epoch(
            selection,
            "selected_at",
            "selected_candidate_time",
            "timestamp",
        )
        scanner_delay = int(entry_epoch - scanner_time) if entry_epoch > 0 and scanner_time > 0 else None
        strategist_delay = int(entry_epoch - strategist_time) if entry_epoch > 0 and strategist_time > 0 else None
        selected_delay = int(entry_epoch - selected_time) if entry_epoch > 0 and selected_time > 0 else None
        pre_move, pre_move_meta = _pre_entry_move_pct(
            symbol=symbol,
            decision_epoch=decision_epoch,
            entry_price=entry_price,
            minute_rows_by_symbol=rows_by_symbol,
        )
        forward = _entry_forward(
            trade_id=trade_id,
            symbol=symbol,
            entry_epoch=entry_epoch,
            entry_price=entry_price,
            minute_rows_by_symbol=rows_by_symbol,
        )
        label, reasons = _label(
            scanner_to_entry_delay_sec=scanner_delay,
            pre_entry_move_pct=pre_move,
            forward=forward,
            strategy_horizon=strategy_horizon,
        )
        cp5 = _checkpoint(forward, "+5m")
        cp15 = _checkpoint(forward, "+15m")
        cp30 = _checkpoint(forward, "+30m")
        cp60 = _checkpoint(forward, "+60m")
        missing_stage_timestamps = [
            name
            for name, value in (
                ("strategist_confirm_time", strategist_time),
                ("selected_candidate_time", selected_time),
            )
            if value <= 0
        ]
        rows.append({
            "trade_id": trade_id,
            "symbol": symbol,
            "label": label,
            "label_reasons": reasons,
            "scanner_top1_symbol": _candidate_symbol(selection.get("raw_scanner_top1")),
            "post_strategy_top1_symbol": _candidate_symbol(selection.get("scanner_top1")),
            "selected_symbol": str(selection.get("selected_symbol") or ""),
            "selected_rank": selection.get("selected_rank") or _candidate_rank(selection.get("selected_candidate")),
            "strategy_horizon": strategy_horizon or "unknown",
            "stage_timing_status": "COMPLETE" if not missing_stage_timestamps else "PARTIAL",
            "missing_stage_timestamps": missing_stage_timestamps,
            "scanner_top1_time": _iso(scanner_time),
            "post_strategy_top1_time": _iso(strategist_time),
            "strategist_confirm_time": _iso(strategist_time),
            "selected_candidate_time": _iso(selected_time),
            "actual_entry_time": _iso(entry_epoch),
            "scanner_to_entry_delay_sec": scanner_delay,
            "strategist_to_entry_delay_sec": strategist_delay,
            "selected_to_entry_delay_sec": selected_delay,
            "decision_window_to_entry_delay_sec": scanner_delay,
            "pre_entry_move_pct": pre_move,
            "pre_entry_move_meta": pre_move_meta,
            "entry_return_pct": outcome.get("net_return_pct"),
            "entry_forward_quality": {
                "+5m_return_pct": cp5.get("return_pct"),
                "+15m_return_pct": cp15.get("return_pct"),
                "+30m_return_pct": cp30.get("return_pct"),
                "+60m_return_pct": cp60.get("return_pct"),
                "+5m_mfe_pct": cp5.get("mfe_pct"),
                "+15m_mfe_pct": cp15.get("mfe_pct"),
                "+30m_mfe_pct": cp30.get("mfe_pct"),
                "+60m_mfe_pct": cp60.get("mfe_pct"),
                "+5m_mae_pct": cp5.get("mae_pct"),
                "+15m_mae_pct": cp15.get("mae_pct"),
                "+30m_mae_pct": cp30.get("mae_pct"),
                "+60m_mae_pct": cp60.get("mae_pct"),
                "immediate_adverse_move": bool((_num(cp5.get("mae_pct")) or 0.0) <= -0.55),
                "immediate_favorable_move": bool((_num(cp5.get("mfe_pct")) or 0.0) >= 0.50),
                "forward_available": bool(forward.get("available")),
            },
        })

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("label") or "INSUFFICIENT_EVIDENCE")].append(row)
    label_rows: list[dict[str, Any]] = []
    for label in LABELS:
        label_group = groups.get(label, [])
        realized = [_num(row.get("entry_return_pct")) for row in label_group]
        realized_values = [float(value) for value in realized if value is not None]
        mfe_values = [
            _num(_mapping(row.get("entry_forward_quality")).get("+5m_mfe_pct"))
            for row in label_group
        ]
        mae_values = [
            _num(_mapping(row.get("entry_forward_quality")).get("+5m_mae_pct"))
            for row in label_group
        ]
        delays = [_num(row.get("scanner_to_entry_delay_sec")) for row in label_group]
        label_rows.append({
            "label": label,
            "trade_count": len(label_group),
            "performance": performance_metrics(realized_values),
            "avg_scanner_to_entry_delay_sec": (
                round(sum(float(v) for v in delays if v is not None) / len([v for v in delays if v is not None]), 2)
                if any(v is not None for v in delays)
                else None
            ),
            "avg_5m_mfe_pct": (
                round(sum(float(v) for v in mfe_values if v is not None) / len([v for v in mfe_values if v is not None]), 4)
                if any(v is not None for v in mfe_values)
                else None
            ),
            "avg_5m_mae_pct": (
                round(sum(float(v) for v in mae_values if v is not None) / len([v for v in mae_values if v is not None]), 4)
                if any(v is not None for v in mae_values)
                else None
            ),
        })

    return {
        "schema_version": "entry_timing_attribution_report.v1",
        "measurement_contract_version": "q13_stage_timing.v2",
        "evaluation_program_id": "Q13_ENTRY_TIMING_ATTRIBUTION",
        "behavior_effect": "observation_only",
        "day": day,
        "trade_count": len(rows),
        "excluded_trade_count": excluded_count,
        "label_summary": label_rows,
        "rows": rows,
        "limitations": [
            "Scanner time uses the Q9 decision snapshot. Strategist and selected-candidate times remain empty unless an explicit stage timestamp exists.",
            "Labels are attribution hypotheses, not trading behavior.",
            "INSUFFICIENT_EVIDENCE is used when forward minute observations are missing or ambiguous.",
        ],
    }


def _fmt(value: Any, suffix: str = "") -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.4f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def render_entry_timing_attribution_report(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Q13 Entry Timing Attribution - {payload.get('day', '')}",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Trades: {payload.get('trade_count', 0)}",
        "",
        "## Label Summary",
        "",
        "| Label | Trades | Win Rate | Avg Return | Avg Delay Sec | Avg 5m MFE | Avg 5m MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("label_summary") or []:
        if not isinstance(row, Mapping):
            continue
        perf = _mapping(row.get("performance"))
        lines.append(
            f"| {row.get('label')} | {row.get('trade_count')} | "
            f"{_fmt(float(perf.get('win_rate') or 0.0) * 100.0, '%')} | "
            f"{_fmt(perf.get('average_return_pct'), '%')} | "
            f"{_fmt(row.get('avg_scanner_to_entry_delay_sec'))} | "
            f"{_fmt(row.get('avg_5m_mfe_pct'), '%')} | "
            f"{_fmt(row.get('avg_5m_mae_pct'), '%')} |"
        )
    lines.extend([
        "",
        "## Trade Rows",
        "",
        "| Trade | Symbol | Label | Delay Sec | Pre-entry Move | +5m Return | +5m MFE | +5m MAE | Realized | Reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        quality = _mapping(row.get("entry_forward_quality"))
        lines.append(
            f"| {row.get('trade_id')} | {row.get('symbol')} | {row.get('label')} | "
            f"{_fmt(row.get('scanner_to_entry_delay_sec'))} | "
            f"{_fmt(row.get('pre_entry_move_pct'), '%')} | "
            f"{_fmt(quality.get('+5m_return_pct'), '%')} | "
            f"{_fmt(quality.get('+5m_mfe_pct'), '%')} | "
            f"{_fmt(quality.get('+5m_mae_pct'), '%')} | "
            f"{_fmt(row.get('entry_return_pct'), '%')} | "
            f"{', '.join(row.get('label_reasons') or []) or '-'} |"
        )
    lines.extend([
        "",
        "## Limitations",
        "",
    ])
    for item in payload.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "build_entry_timing_attribution_report",
    "render_entry_timing_attribution_report",
]
