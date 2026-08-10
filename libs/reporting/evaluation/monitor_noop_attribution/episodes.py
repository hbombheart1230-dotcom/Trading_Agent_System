from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.evaluation.artifact_inventory import (
    is_regular_session_evaluation_row,
    is_synthetic_evaluation_row,
)

from .contracts import EPISODE_GAP_SECONDS, blocker_family


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _epoch(row: Mapping[str, Any]) -> int:
    try:
        value = int(float(row.get("decision_epoch") or 0))
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    try:
        return int(datetime.fromisoformat(
            str(row.get("generated_at") or "").replace("Z", "+00:00")
        ).timestamp())
    except (TypeError, ValueError):
        return 0


def _candidate_bases(log_root: Path, day: str) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    root = log_root / day
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        if path.name == "latest.json":
            continue
        payload = _read(path)
        decision_id = str(payload.get("q9_decision_id") or "")
        rows = list(payload.get("q9_decision_candidates") or []) + list(
            payload.get("candidates") or []
        )
        for raw in rows:
            if not isinstance(raw, Mapping):
                continue
            symbol = str(raw.get("symbol") or "")
            key = (str(raw.get("q9_decision_id") or decision_id), symbol)
            base = raw.get("shadow_forward_base")
            if not key[0] or not symbol or not isinstance(base, Mapping):
                continue
            if bool(base.get("available")) or float(base.get("baseline_price") or 0) > 0:
                result.setdefault(key, dict(base))
    return result


def load_approved_noop_cycles(
    *, reports_root: Path, log_root: Path, day: str
) -> list[dict[str, Any]]:
    payload = _read(
        reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json"
    )
    bases = _candidate_bases(log_root, day)
    rows: list[dict[str, Any]] = []
    for window in payload.get("windows") or []:
        if not isinstance(window, dict):
            continue
        if is_synthetic_evaluation_row(window) or not is_regular_session_evaluation_row(window):
            continue
        commander = window.get("commander_final")
        commander = commander if isinstance(commander, Mapping) else {}
        if str(commander.get("decision") or "").lower() != "approve":
            continue
        if str(commander.get("monitor_intent") or "").upper() != "NOOP":
            continue
        decision_id = str(window.get("decision_id") or commander.get("decision_id") or "")
        symbol = str(
            commander.get("selected_symbol") or commander.get("candidate_symbol") or ""
        )
        epoch = _epoch(window)
        if not decision_id or not symbol or epoch <= 0:
            continue
        observation = commander.get("monitor_observation")
        observation = observation if isinstance(observation, Mapping) else {}
        rows.append({
            "day": day,
            "decision_id": decision_id,
            "decision_epoch": epoch,
            "generated_at": str(window.get("generated_at") or ""),
            "symbol": symbol,
            "blocker_family": blocker_family(commander),
            "blocker_reason": str(
                commander.get("monitor_reason") or observation.get("reason") or "unknown"
            ),
            "entry_lane": str(observation.get("entry_lane") or ""),
            "cost_floor_state": str(observation.get("cost_floor_state") or ""),
            "shadow_forward_base": dict(bases.get((decision_id, symbol)) or {}),
        })
    return sorted(rows, key=lambda row: int(row["decision_epoch"]))


def collapse_cycles_to_episodes(
    rows: list[Mapping[str, Any]], *, gap_seconds: int = EPISODE_GAP_SECONDS
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    active: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in sorted(rows, key=lambda row: int(row.get("decision_epoch") or 0)):
        row = dict(raw)
        key = (str(row.get("day") or ""), str(row.get("symbol") or ""), str(row.get("blocker_family") or "OTHER"))
        prior = active.get(key)
        epoch = int(row.get("decision_epoch") or 0)
        if prior and epoch - int(prior["last_decision_epoch"]) <= gap_seconds:
            prior["last_decision_epoch"] = epoch
            prior["last_decision_id"] = row.get("decision_id")
            prior["cycle_count"] += 1
            prior["blocker_reasons"] = sorted(
                set(prior["blocker_reasons"]) | {str(row.get("blocker_reason") or "")}
            )
            continue
        episode = {
            **row,
            "episode_id": f"{row.get('day')}:{row.get('symbol')}:{row.get('blocker_family')}:{epoch}",
            "first_decision_epoch": epoch,
            "last_decision_epoch": epoch,
            "first_decision_id": row.get("decision_id"),
            "last_decision_id": row.get("decision_id"),
            "cycle_count": 1,
            "blocker_reasons": [str(row.get("blocker_reason") or "")],
        }
        active[key] = episode
        episodes.append(episode)
    return episodes


__all__ = ["collapse_cycles_to_episodes", "load_approved_noop_cycles"]
