from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except Exception:
        if default is None:
            return None
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _truth_input_path_from_bundle(bundle: Dict[str, Any]) -> Path:
    raw_bundle_path = str(bundle.get("_bundle_path") or "").strip()
    if raw_bundle_path:
        trade_root = Path(raw_bundle_path).parent
        candidate = trade_root / "reports" / "ai_trade_summary_input.json"
        if candidate.exists():
            return candidate
    return Path()


def extract_truth_outcome_from_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    path = _truth_input_path_from_bundle(bundle)
    if not path:
        return {"available": False}
    payload = _read_json_dict(path)
    truth = payload.get("truth_surface") if isinstance(payload.get("truth_surface"), dict) else {}
    if not truth:
        return {"available": False, "path": str(path)}
    pnl_value = truth.get("pnl")
    pnl = _safe_float(pnl_value, None)
    pnl_pct = _safe_float(truth.get("pnl_pct"), None)
    observed = pnl_pct if pnl is None else None
    return {
        "available": True,
        "path": str(path),
        "pnl": pnl,
        "return": pnl_pct if pnl is not None else None,
        "observed_return": observed,
        "result_label": str(truth.get("result_label") or ""),
        "truth_source": str(truth.get("truth_source") or ""),
    }


def _iter_lifecycle_bundle_paths(reports_root: Path, *, day: str = "") -> Iterable[Path]:
    root = Path(reports_root)
    trades_root = root / "trades"
    target_day = str(day or "").strip()
    if target_day:
        day_root = trades_root / target_day
        if not day_root.exists():
            return []
        return sorted(day_root.rglob("lifecycle_bundle.json"))
    if not trades_root.exists():
        return []
    return sorted(trades_root.rglob("lifecycle_bundle.json"))


def load_lifecycle_bundles(reports_root: Path, *, day: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in _iter_lifecycle_bundle_paths(Path(reports_root), day=day):
        obj = _read_json_dict(path)
        if not obj:
            continue
        obj.setdefault("_bundle_path", str(path))
        rows.append(obj)
    return rows


def _extract_return_value(bundle: Dict[str, Any]) -> Optional[float]:
    truth = extract_truth_outcome_from_bundle(bundle)
    if bool(truth.get("available")):
        value = truth.get("return")
        return float(value) if value not in (None, "") else None
    trade_outcome = bundle.get("trade_outcome") if isinstance(bundle.get("trade_outcome"), dict) else {}
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    candidates = [
        trade_outcome.get("return_pct"),
        trade_outcome.get("realized_return_pct"),
        summary.get("return_pct"),
    ]
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _extract_pnl_value(bundle: Dict[str, Any]) -> Optional[float]:
    truth = extract_truth_outcome_from_bundle(bundle)
    if bool(truth.get("available")):
        value = truth.get("pnl")
        return float(value) if value not in (None, "") else None
    trade_outcome = bundle.get("trade_outcome") if isinstance(bundle.get("trade_outcome"), dict) else {}
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    candidates = [
        trade_outcome.get("pnl"),
        trade_outcome.get("realized_pnl"),
        summary.get("realized_pnl"),
        summary.get("pnl"),
    ]
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _extract_playbook(bundle: Dict[str, Any]) -> str:
    strategist = bundle.get("strategist_summary") if isinstance(bundle.get("strategist_summary"), dict) else {}
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    strategist_ctx = entry.get("strategist_context") if isinstance(entry.get("strategist_context"), dict) else {}
    value = (
        strategist.get("playbook")
        or strategist_ctx.get("playbook")
        or ""
    )
    return str(value or "").strip().lower()


def _extract_market_regime(bundle: Dict[str, Any]) -> str:
    strategist = bundle.get("strategist_summary") if isinstance(bundle.get("strategist_summary"), dict) else {}
    value = strategist.get("market_regime") or strategist.get("regime") or ""
    return str(value or "").strip().lower()


def _extract_symbol(bundle: Dict[str, Any]) -> str:
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    value = bundle.get("symbol") or entry.get("symbol") or ""
    return str(value or "").strip().upper()


def _classify_entry_pattern(reason: Any) -> str:
    text = _text(reason).lower()
    if not text:
        return ""
    if "pullback" in text or "rebound" in text:
        return "pullback"
    if "breakout" in text or "recent_high" in text:
        return "breakout"
    if "reversal" in text:
        return "reversal"
    if "reclaim" in text or "vwap" in text:
        return "vwap_reclaim"
    return ""


def _classify_exit_pattern(reason: Any) -> str:
    text = _text(reason).lower()
    if not text:
        return ""
    if "peak_drawdown" in text:
        return "peak_drawdown"
    if "hard_stop" in text:
        return "hard_stop"
    if "take_profit" in text or "profit" in text:
        return "take_profit"
    if "intraday_low_break" in text:
        return "intraday_low_break"
    if "time" in text:
        return "time_exit"
    if "no_position" in text:
        return "no_position"
    return ""


def _extract_entry_reason(bundle: Dict[str, Any]) -> str:
    feedback = _dict(bundle.get("strategist_feedback_input"))
    lifecycle = _dict(bundle.get("lifecycle"))
    entry = _dict(bundle.get("entry")) or _dict(lifecycle.get("entry"))
    return _text(
        feedback.get("entry_reason")
        or bundle.get("entry_reason")
        or entry.get("reason_human")
        or entry.get("summary")
    )


def _extract_exit_reason(bundle: Dict[str, Any]) -> str:
    feedback = _dict(bundle.get("strategist_feedback_input"))
    lifecycle = _dict(bundle.get("lifecycle"))
    exit_row = _dict(bundle.get("exit")) or _dict(lifecycle.get("exit"))
    trade_outcome = _dict(bundle.get("trade_outcome"))
    return _text(
        feedback.get("exit_reason")
        or bundle.get("exit_reason")
        or trade_outcome.get("exit_reason")
        or exit_row.get("reason_human")
        or exit_row.get("summary")
    )


def _extract_entry_pattern_type(bundle: Dict[str, Any]) -> str:
    feedback = _dict(bundle.get("strategist_feedback_input"))
    reason = _extract_entry_reason(bundle)
    return _text(
        feedback.get("entry_pattern_type")
        or bundle.get("entry_pattern_type")
        or _classify_entry_pattern(reason)
    ).lower()


def _extract_exit_pattern_type(bundle: Dict[str, Any]) -> str:
    feedback = _dict(bundle.get("strategist_feedback_input"))
    reason = _extract_exit_reason(bundle)
    return _text(
        feedback.get("exit_pattern_type")
        or bundle.get("exit_pattern_type")
        or _classify_exit_pattern(reason)
    ).lower()


def _trade_row(bundle: Dict[str, Any]) -> Dict[str, Any]:
    truth = extract_truth_outcome_from_bundle(bundle)
    return {
        "trade_id": str(bundle.get("trade_id") or ""),
        "day": str(bundle.get("day") or ""),
        "symbol": _extract_symbol(bundle),
        "playbook": _extract_playbook(bundle),
        "market_regime": _extract_market_regime(bundle),
        "entry_reason": _extract_entry_reason(bundle),
        "exit_reason": _extract_exit_reason(bundle),
        "entry_pattern_type": _extract_entry_pattern_type(bundle),
        "exit_pattern_type": _extract_exit_pattern_type(bundle),
        "return": _extract_return_value(bundle),
        "pnl": _extract_pnl_value(bundle),
        "observed_return": truth.get("observed_return") if bool(truth.get("available")) else None,
        "return_basis": "truth_surface_net" if bool(truth.get("available")) and truth.get("return") not in (None, "") else (
            "truth_surface_observation_only" if bool(truth.get("available")) else "lifecycle"
        ),
        "truth_surface_path": str(truth.get("path") or ""),
        "bundle_path": str(bundle.get("_bundle_path") or ""),
    }


def _is_win(row: Dict[str, Any]) -> Optional[bool]:
    if row.get("return") not in (None, ""):
        return bool(_safe_float(row.get("return"), 0.0) > 0.0)
    if row.get("pnl") not in (None, ""):
        return bool(_safe_float(row.get("pnl"), 0.0) > 0.0)
    return None


def _score_series(rows: List[Dict[str, Any]]) -> List[float]:
    out: List[float] = []
    for row in rows:
        if row.get("return") not in (None, ""):
            out.append(_safe_float(row.get("return"), 0.0))
            continue
        if row.get("pnl") not in (None, ""):
            out.append(_safe_float(row.get("pnl"), 0.0))
    return out


def _compute_profit_factor(values: List[float]) -> float:
    gains = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    if losses <= 0.0:
        return 0.0 if gains <= 0.0 else round(gains, 6)
    return round(gains / losses, 6)


def _compute_max_drawdown(values: List[float]) -> float:
    # Simple approximation from cumulative trade-level return/pnl sequence.
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_dd:
            max_dd = drawdown
    return round(max_dd, 6)


def _aggregate_group(rows: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        name = str(row.get(key) or "").strip()
        if not name:
            name = "unknown"
        buckets.setdefault(name, []).append(row)

    out: Dict[str, Dict[str, Any]] = {}
    for name, group_rows in sorted(buckets.items(), key=lambda item: item[0]):
        values = _score_series(group_rows)
        wins = sum(1 for row in group_rows if _is_win(row) is True)
        losses = sum(1 for row in group_rows if _is_win(row) is False)
        scored_count = int(len(values))
        unavailable_count = max(0, int(len(group_rows)) - scored_count)
        symbols = sorted({str(row.get("symbol") or "").strip().upper() for row in group_rows if str(row.get("symbol") or "").strip()})
        out[name] = {
            "trade_count": int(len(group_rows)),
            "return_sample_count": scored_count,
            "unavailable_return_count": unavailable_count,
            "win_count": int(wins),
            "loss_count": int(losses),
            "win_rate": round(float(wins) / float(scored_count), 6) if scored_count else 0.0,
            "avg_return": round(sum(values) / len(values), 6) if values else 0.0,
            "profit_factor": _compute_profit_factor(values),
            "max_drawdown": _compute_max_drawdown(values),
            "symbols": symbols[:12],
        }
    return out


def _aggregate_entry_exit_combo_stats(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    combo_rows: List[Dict[str, Any]] = []
    for row in rows:
        entry = str(row.get("entry_pattern_type") or "").strip() or "unknown"
        exit_pattern = str(row.get("exit_pattern_type") or "").strip() or "unknown"
        combo = f"{entry} -> {exit_pattern}"
        combo_rows.append({**row, "entry_exit_combo": combo})
    return _aggregate_group(combo_rows, "entry_exit_combo")


def aggregate_performance_from_bundles(
    bundles: List[Dict[str, Any]],
    *,
    day: str = "",
    reports_root: Optional[Path] = None,
) -> Dict[str, Any]:
    rows = [_trade_row(bundle) for bundle in list(bundles or []) if isinstance(bundle, dict)]
    values = _score_series(rows)
    wins = sum(1 for row in rows if _is_win(row) is True)
    losses = sum(1 for row in rows if _is_win(row) is False)
    positive_values = [value for value in values if value > 0]
    negative_values = [value for value in values if value < 0]
    target_day = str(day or "").strip()
    if not target_day:
        days = [str(row.get("day") or "").strip() for row in rows if str(row.get("day") or "").strip()]
        target_day = max(days) if days else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "schema_version": "performance_summary.v1",
        "day": target_day,
        "generated_at": _utc_now_iso(),
        "total_trades": int(len(rows)),
        "return_sample_count": int(len(values)),
        "unavailable_return_count": max(0, int(len(rows)) - int(len(values))),
        "observed_return_sample_count": int(
            sum(1 for row in rows if row.get("return") in (None, "") and row.get("observed_return") not in (None, ""))
        ),
        "win_rate": round(float(wins) / float(len(values)), 6) if values else 0.0,
        "avg_return": round(sum(values) / len(values), 6) if values else 0.0,
        "avg_win": round(sum(positive_values) / len(positive_values), 6) if positive_values else 0.0,
        "avg_loss": round(sum(negative_values) / len(negative_values), 6) if negative_values else 0.0,
        "profit_factor": _compute_profit_factor(values),
        "max_drawdown": _compute_max_drawdown(values),
        "per_symbol_stats": _aggregate_group(rows, "symbol"),
        "per_playbook_stats": _aggregate_group(rows, "playbook"),
        "per_market_regime_stats": _aggregate_group(rows, "market_regime"),
        "per_entry_pattern_stats": _aggregate_group(rows, "entry_pattern_type"),
        "per_exit_pattern_stats": _aggregate_group(rows, "exit_pattern_type"),
        "per_entry_reason_stats": _aggregate_group(rows, "entry_reason"),
        "per_exit_reason_stats": _aggregate_group(rows, "exit_reason"),
        "per_entry_exit_combo_stats": _aggregate_entry_exit_combo_stats(rows),
        "source": {
            "bundle_count": int(len(rows)),
            "reports_root": str(reports_root) if reports_root is not None else "",
        },
        "trade_rows": [
            {
                "trade_id": str(row.get("trade_id") or ""),
                "day": str(row.get("day") or ""),
                "symbol": str(row.get("symbol") or ""),
                "playbook": str(row.get("playbook") or ""),
                "market_regime": str(row.get("market_regime") or ""),
                "entry_pattern_type": str(row.get("entry_pattern_type") or ""),
                "exit_pattern_type": str(row.get("exit_pattern_type") or ""),
                "entry_reason": str(row.get("entry_reason") or ""),
                "exit_reason": str(row.get("exit_reason") or ""),
                "return": row.get("return"),
                "pnl": row.get("pnl"),
                "observed_return": row.get("observed_return"),
                "return_basis": str(row.get("return_basis") or ""),
                "truth_surface_path": str(row.get("truth_surface_path") or ""),
            }
            for row in rows
        ],
    }


def aggregate_performance_from_reports_root(reports_root: Path, *, day: str = "") -> Dict[str, Any]:
    bundles = load_lifecycle_bundles(Path(reports_root), day=day)
    return aggregate_performance_from_bundles(bundles, day=day, reports_root=Path(reports_root))


def performance_artifact_paths(reports_root: Path, day: str) -> Dict[str, Path]:
    root = Path(reports_root) / "performance" / str(day or "").strip()
    return {
        "root_dir": root,
        "summary_json": root / "summary.json",
        "playbook_stats_json": root / "playbook_stats.json",
        "symbol_stats_json": root / "symbol_stats.json",
        "strategy_memory_json": root / "strategy_memory.json",
    }


def write_performance_summary(
    reports_root: Path,
    *,
    day: str,
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = (
        dict(summary)
        if isinstance(summary, dict)
        else aggregate_performance_from_reports_root(Path(reports_root), day=day)
    )
    payload["day"] = str(day or payload.get("day") or "").strip()
    paths = performance_artifact_paths(Path(reports_root), str(payload.get("day") or day))
    paths["root_dir"].mkdir(parents=True, exist_ok=True)
    paths["summary_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    symbol_stats = payload.get("per_symbol_stats") if isinstance(payload.get("per_symbol_stats"), dict) else {}
    paths["symbol_stats_json"].write_text(
        json.dumps(
            {
                "schema_version": "symbol_stats.v1",
                "day": str(payload.get("day") or day),
                "generated_at": _utc_now_iso(),
                "symbol_stats": symbol_stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    payload["artifacts"] = {
        "summary_json": str(paths["summary_json"]),
        "symbol_stats_json": str(paths["symbol_stats_json"]),
    }
    return payload
