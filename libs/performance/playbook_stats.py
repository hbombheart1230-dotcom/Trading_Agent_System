from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .performance_aggregator import (
    aggregate_performance_from_reports_root,
    load_lifecycle_bundles,
    performance_artifact_paths,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _extract_playbook(bundle: Dict[str, Any]) -> str:
    strategist = bundle.get("strategist_summary") if isinstance(bundle.get("strategist_summary"), dict) else {}
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    strategist_ctx = entry.get("strategist_context") if isinstance(entry.get("strategist_context"), dict) else {}
    return str(strategist.get("playbook") or strategist_ctx.get("playbook") or "unknown").strip().lower() or "unknown"


def _extract_return(bundle: Dict[str, Any]) -> Optional[float]:
    trade_outcome = bundle.get("trade_outcome") if isinstance(bundle.get("trade_outcome"), dict) else {}
    candidates = [
        trade_outcome.get("return_pct"),
        trade_outcome.get("realized_return_pct"),
    ]
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except Exception:
            continue
    pnl = trade_outcome.get("pnl")
    if pnl in (None, ""):
        return None
    try:
        return float(pnl)
    except Exception:
        return None


def _max_drawdown(values: List[float]) -> float:
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


def _stability_score(*, win_rate: float, drawdown: float, avg_return: float, usage_count: int) -> float:
    # Lightweight heuristic, bounded in [0, 1].
    usage_factor = min(1.0, max(0.0, float(usage_count) / 10.0))
    drawdown_penalty = min(1.0, max(0.0, drawdown / 10.0))
    return round(
        max(
            0.0,
            min(
                1.0,
                0.55 * float(win_rate)
                + 0.30 * (0.5 + max(-0.5, min(0.5, avg_return / 10.0)))
                + 0.25 * usage_factor
                - 0.25 * drawdown_penalty,
            ),
        ),
        6,
    )


def calculate_playbook_stats(
    bundles: List[Dict[str, Any]],
    *,
    day: str = "",
    recent_window: int = 5,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for bundle in list(bundles or []):
        if not isinstance(bundle, dict):
            continue
        playbook = _extract_playbook(bundle)
        score = _extract_return(bundle)
        rows.append(
            {
                "day": str(bundle.get("day") or ""),
                "trade_id": str(bundle.get("trade_id") or ""),
                "playbook": playbook,
                "return": score,
            }
        )
    rows.sort(key=lambda row: (str(row.get("day") or ""), str(row.get("trade_id") or "")))
    playbook_rows: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        playbook_rows.setdefault(str(row.get("playbook") or "unknown"), []).append(row)

    out: Dict[str, Any] = {}
    for playbook, grouped in sorted(playbook_rows.items(), key=lambda item: item[0]):
        values = [_safe_float(row.get("return"), 0.0) for row in grouped if row.get("return") not in (None, "")]
        usage_count = len(grouped)
        win_count = sum(1 for value in values if value > 0.0)
        recent_values = values[-max(1, int(recent_window)) :]
        drawdown = _max_drawdown(values)
        avg_return = (sum(values) / len(values)) if values else 0.0
        win_rate = (float(win_count) / float(len(values))) if values else 0.0
        out[playbook] = {
            "usage_count": int(usage_count),
            "win_rate": round(win_rate, 6),
            "avg_return": round(avg_return, 6),
            "recent_performance": [round(v, 6) for v in recent_values],
            "drawdown": float(drawdown),
            "stability_score": _stability_score(
                win_rate=win_rate,
                drawdown=drawdown,
                avg_return=avg_return,
                usage_count=usage_count,
            ),
        }

    target_day = str(day or "").strip()
    if not target_day:
        days = [str(row.get("day") or "").strip() for row in rows if str(row.get("day") or "").strip()]
        target_day = max(days) if days else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "schema_version": "playbook_stats.v1",
        "day": target_day,
        "generated_at": _utc_now_iso(),
        "recent_window": int(max(1, int(recent_window))),
        "playbooks": out,
    }


def write_playbook_stats(
    reports_root: Path,
    *,
    day: str,
    bundles: Optional[List[Dict[str, Any]]] = None,
    recent_window: int = 5,
) -> Dict[str, Any]:
    rows = list(bundles or load_lifecycle_bundles(Path(reports_root), day=day))
    payload = calculate_playbook_stats(rows, day=day, recent_window=recent_window)
    paths = performance_artifact_paths(Path(reports_root), str(payload.get("day") or day))
    paths["root_dir"].mkdir(parents=True, exist_ok=True)
    paths["playbook_stats_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["artifact_path"] = str(paths["playbook_stats_json"])
    return payload


def build_playbook_stats_from_reports_root(
    reports_root: Path,
    *,
    day: str,
    recent_window: int = 5,
) -> Dict[str, Any]:
    _ = aggregate_performance_from_reports_root(Path(reports_root), day=day)
    return write_playbook_stats(Path(reports_root), day=day, recent_window=recent_window)

