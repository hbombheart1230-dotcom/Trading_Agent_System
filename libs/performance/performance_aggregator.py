from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _iter_lifecycle_bundle_paths(reports_root: Path, *, day: str = "") -> Iterable[Path]:
    root = Path(reports_root)
    trades_root = root / "trades"
    target_day = str(day or "").strip()
    if target_day:
        day_root = trades_root / target_day
        if not day_root.exists():
            return []
        return sorted(day_root.glob("*/lifecycle_bundle.json"))
    if not trades_root.exists():
        return []
    return sorted(trades_root.glob("*/*/lifecycle_bundle.json"))


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


def _trade_row(bundle: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trade_id": str(bundle.get("trade_id") or ""),
        "day": str(bundle.get("day") or ""),
        "symbol": _extract_symbol(bundle),
        "playbook": _extract_playbook(bundle),
        "market_regime": _extract_market_regime(bundle),
        "return": _extract_return_value(bundle),
        "pnl": _extract_pnl_value(bundle),
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
        out[name] = {
            "trade_count": int(len(group_rows)),
            "win_count": int(wins),
            "loss_count": int(losses),
            "win_rate": round(float(wins) / float(len(group_rows)), 6) if group_rows else 0.0,
            "avg_return": round(sum(values) / len(values), 6) if values else 0.0,
            "profit_factor": _compute_profit_factor(values),
            "max_drawdown": _compute_max_drawdown(values),
        }
    return out


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
        "win_rate": round(float(wins) / float(len(rows)), 6) if rows else 0.0,
        "avg_return": round(sum(values) / len(values), 6) if values else 0.0,
        "avg_win": round(sum(positive_values) / len(positive_values), 6) if positive_values else 0.0,
        "avg_loss": round(sum(negative_values) / len(negative_values), 6) if negative_values else 0.0,
        "profit_factor": _compute_profit_factor(values),
        "max_drawdown": _compute_max_drawdown(values),
        "per_symbol_stats": _aggregate_group(rows, "symbol"),
        "per_playbook_stats": _aggregate_group(rows, "playbook"),
        "per_market_regime_stats": _aggregate_group(rows, "market_regime"),
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
                "return": row.get("return"),
                "pnl": row.get("pnl"),
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

