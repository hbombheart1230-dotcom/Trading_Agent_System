from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .performance_aggregator import (
    aggregate_performance_from_reports_root,
    performance_artifact_paths,
    write_performance_summary,
)
from .playbook_stats import calculate_playbook_stats, write_playbook_stats


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _list_unique(values: List[str], *, limit: int = 8) -> List[str]:
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _recent_patterns_from_playbooks(playbooks: Dict[str, Any], *, success: bool) -> List[str]:
    rows: List[tuple[str, float, float, float]] = []
    for name, payload in dict(playbooks or {}).items():
        item = payload if isinstance(payload, dict) else {}
        win_rate = _safe_float(item.get("win_rate"), 0.0)
        avg_return = _safe_float(item.get("avg_return"), 0.0)
        stability = _safe_float(item.get("stability_score"), 0.0)
        rows.append((str(name), win_rate, avg_return, stability))
    if success:
        rows.sort(key=lambda row: (-row[3], -row[2], -row[1], row[0]))
        selected = [name for name, win_rate, avg_return, _ in rows if win_rate >= 0.5 and avg_return >= 0.0]
    else:
        rows.sort(key=lambda row: (row[2], row[1], row[3], row[0]))
        selected = [name for name, win_rate, avg_return, _ in rows if win_rate <= 0.4 or avg_return < 0.0]
    return _list_unique(selected, limit=4)


def build_strategy_memory(
    summary: Dict[str, Any],
    playbook_stats: Dict[str, Any],
) -> Dict[str, Any]:
    summary_obj = dict(summary or {})
    playbooks = (
        playbook_stats.get("playbooks")
        if isinstance(playbook_stats.get("playbooks"), dict)
        else {}
    )
    playbook_rows: List[tuple[str, float, float, float]] = []
    for name, payload in dict(playbooks).items():
        item = payload if isinstance(payload, dict) else {}
        playbook_rows.append(
            (
                str(name),
                _safe_float(item.get("stability_score"), 0.0),
                _safe_float(item.get("avg_return"), 0.0),
                _safe_float(item.get("win_rate"), 0.0),
            )
        )
    playbook_rows.sort(key=lambda row: (-row[1], -row[2], -row[3], row[0]))
    best_playbooks = [row[0] for row in playbook_rows[:3] if row[0] and row[0] != "unknown"]
    worst_playbooks = [row[0] for row in sorted(playbook_rows, key=lambda row: (row[2], row[3], row[1], row[0]))[:3] if row[0] and row[0] != "unknown"]
    playbook_performance_snapshot: Dict[str, Any] = {}
    for name, _stability, _avg_return, _win_rate in playbook_rows[:4]:
        src = playbooks.get(name) if isinstance(playbooks.get(name), dict) else {}
        playbook_performance_snapshot[str(name)] = {
            "usage_count": int(float(src.get("usage_count") or 0)),
            "win_rate": _safe_float(src.get("win_rate"), 0.0),
            "avg_return": _safe_float(src.get("avg_return"), 0.0),
            "stability_score": _safe_float(src.get("stability_score"), 0.0),
        }

    regime_stats = (
        summary_obj.get("per_market_regime_stats")
        if isinstance(summary_obj.get("per_market_regime_stats"), dict)
        else {}
    )
    regime_bias: Dict[str, Any] = {}
    for regime, payload in regime_stats.items():
        item = payload if isinstance(payload, dict) else {}
        regime_bias[str(regime)] = {
            "win_rate": _safe_float(item.get("win_rate"), 0.0),
            "avg_return": _safe_float(item.get("avg_return"), 0.0),
            "trade_count": int(float(item.get("trade_count") or 0)),
        }

    success_patterns = _recent_patterns_from_playbooks(playbooks, success=True)
    failure_patterns = _recent_patterns_from_playbooks(playbooks, success=False)
    market_condition_bias: Dict[str, Any] = {
        "regime_bias": regime_bias,
        "preferred_regimes": [
            name
            for name, payload in sorted(
                regime_bias.items(),
                key=lambda item: (-_safe_float((item[1] or {}).get("avg_return"), 0.0), item[0]),
            )[:2]
            if str(name).strip() and str(name).strip() != "unknown"
        ],
        "avoid_regimes": [
            name
            for name, payload in sorted(
                regime_bias.items(),
                key=lambda item: (_safe_float((item[1] or {}).get("avg_return"), 0.0), item[0]),
            )[:2]
            if str(name).strip() and str(name).strip() != "unknown"
        ],
    }

    return {
        "schema_version": "strategy_memory.v1",
        "generated_at": _utc_now_iso(),
        "best_playbooks": _list_unique(best_playbooks, limit=3),
        "worst_playbooks": _list_unique(worst_playbooks, limit=3),
        "market_condition_bias": market_condition_bias,
        "recent_failures": [f"playbook:{name}" for name in failure_patterns],
        "recent_success_patterns": [f"playbook:{name}" for name in success_patterns],
        "playbook_performance_snapshot": playbook_performance_snapshot,
        "advisory_only": True,
    }


def write_strategy_memory(
    reports_root: Path,
    *,
    day: str,
    summary: Optional[Dict[str, Any]] = None,
    playbook_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(reports_root)
    target_day = str(day or "").strip()
    summary_obj = dict(summary) if isinstance(summary, dict) else aggregate_performance_from_reports_root(root, day=target_day)
    playbook_obj = dict(playbook_stats) if isinstance(playbook_stats, dict) else calculate_playbook_stats(
        [],
        day=target_day,
    )
    if not playbook_obj.get("playbooks"):
        playbook_obj = write_playbook_stats(root, day=target_day)
    memory = build_strategy_memory(summary_obj, playbook_obj)
    memory["day"] = str(target_day or summary_obj.get("day") or playbook_obj.get("day") or "")
    paths = performance_artifact_paths(root, memory["day"])
    paths["root_dir"].mkdir(parents=True, exist_ok=True)
    paths["strategy_memory_json"].write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    memory["artifact_path"] = str(paths["strategy_memory_json"])
    return memory


def _resolve_latest_day(performance_root: Path) -> str:
    if not performance_root.exists():
        return ""
    days = [path.name for path in performance_root.iterdir() if path.is_dir()]
    days = [day for day in days if len(day) == 10 and day[4:5] == "-" and day[7:8] == "-"]
    if not days:
        return ""
    return sorted(days)[-1]


def load_strategy_memory_hint(
    *,
    reports_root: Path,
    day: str = "",
    auto_build: bool = False,
) -> Dict[str, Any]:
    root = Path(reports_root)
    performance_root = root / "performance"
    target_day = str(day or "").strip() or _resolve_latest_day(performance_root)
    if not target_day:
        return {
            "schema_version": "strategy_memory.v1",
            "day": "",
            "status": "empty",
            "best_playbooks": [],
            "worst_playbooks": [],
            "market_condition_bias": {},
            "recent_failures": [],
            "recent_success_patterns": [],
            "playbook_performance_snapshot": {},
            "advisory_only": True,
        }
    paths = performance_artifact_paths(root, target_day)
    summary = _read_json_dict(paths["summary_json"])
    playbook = _read_json_dict(paths["playbook_stats_json"])
    memory = _read_json_dict(paths["strategy_memory_json"])
    if not summary and auto_build:
        summary = write_performance_summary(root, day=target_day)
    if not playbook and auto_build:
        playbook = write_playbook_stats(root, day=target_day)
    if not memory:
        if summary or playbook:
            memory = build_strategy_memory(summary, playbook)
            memory["day"] = target_day
        else:
            memory = {
                "schema_version": "strategy_memory.v1",
                "day": target_day,
                "best_playbooks": [],
                "worst_playbooks": [],
                "market_condition_bias": {},
                "recent_failures": [],
                "recent_success_patterns": [],
                "playbook_performance_snapshot": {},
                "advisory_only": True,
            }
    memory["status"] = "ok" if (memory.get("best_playbooks") or memory.get("worst_playbooks")) else "empty"
    memory["day"] = target_day
    memory.setdefault("advisory_only", True)
    return memory
