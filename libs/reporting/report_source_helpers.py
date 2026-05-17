from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from libs.reporting.chart_structure_decision_hint_summary import (
    build_chart_structure_decision_hint_executive_summary,
    build_chart_structure_decision_hint_summary,
)
from libs.reporting.policy_surface_summary import (
    build_policy_surface_quality_executive_summary,
    build_policy_surface_quality_summary,
)
from libs.reporting.phase_runtime_health import build_phase_5_2_5_3_runtime_health


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def to_epoch(ts: Any) -> int:
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except Exception:
        pass
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def utc_day(ts: Any) -> str:
    epoch = to_epoch(ts)
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def epoch_to_iso(epoch: Any) -> str:
    try:
        n = int(float(epoch))
    except Exception:
        return ""
    if n <= 0:
        return ""
    return datetime.fromtimestamp(n, tz=timezone.utc).isoformat(timespec="seconds")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj

    return _gen()


def build_policy_surface_quality_snapshot(events_path: Path, reports_root: Path, day: str) -> Dict[str, Any]:
    try:
        runtime_health = build_phase_5_2_5_3_runtime_health(
            reports_root=reports_root,
            event_log_path=events_path,
            day=day,
            limit=500,
        )
    except FileNotFoundError:
        summary = build_policy_surface_quality_summary([])
        chart_summary = build_chart_structure_decision_hint_summary([])
        return {
            "summary": summary,
            "executive_summary": build_policy_surface_quality_executive_summary(summary),
            "chart_structure_summary": chart_summary,
            "chart_structure_executive_summary": build_chart_structure_decision_hint_executive_summary(chart_summary),
            "source": {
                "run_count": 0,
                "date": day,
                "source": "daily_monitor_artifacts",
                "notes": ["no_canonical_monitor_runs_found"],
            },
        }
    except Exception:
        summary = build_policy_surface_quality_summary([])
        chart_summary = build_chart_structure_decision_hint_summary([])
        return {
            "summary": summary,
            "executive_summary": build_policy_surface_quality_executive_summary(summary),
            "chart_structure_summary": chart_summary,
            "chart_structure_executive_summary": build_chart_structure_decision_hint_executive_summary(chart_summary),
            "source": {
                "run_count": 0,
                "date": day,
                "source": "daily_monitor_artifacts",
                "notes": ["policy_surface_quality_summary_unavailable"],
            },
        }

    summary = runtime_health.get("policy_surface_quality_summary")
    if not isinstance(summary, dict):
        summary = build_policy_surface_quality_summary([])
    chart_summary = runtime_health.get("chart_structure_decision_hint_summary")
    if not isinstance(chart_summary, dict):
        chart_summary = build_chart_structure_decision_hint_summary([])
    return {
        "summary": dict(summary),
        "executive_summary": build_policy_surface_quality_executive_summary(summary),
        "chart_structure_summary": dict(chart_summary),
        "chart_structure_executive_summary": build_chart_structure_decision_hint_executive_summary(chart_summary),
        "source": {
            "run_count": int(runtime_health.get("run_count") or 0),
            "date": day,
            "source": "daily_monitor_artifacts",
            "health_schema_version": str(runtime_health.get("schema_version") or ""),
        },
    }


def _commander_route_from_payload(payload: Dict[str, Any], *, artifact_path: str = "") -> Dict[str, Any]:
    route_obs = payload.get("route_observability") if isinstance(payload.get("route_observability"), dict) else {}
    commander_decision = payload.get("commander_decision") if isinstance(payload.get("commander_decision"), dict) else {}
    route_selected = str(
        payload.get("route_selected")
        or payload.get("selected_route")
        or route_obs.get("route_selected")
        or commander_decision.get("route_selected")
        or ""
    ).strip()
    return {
        "route_selected": route_selected,
        "strategy_generation_mode": str(
            payload.get("strategy_generation_mode")
            or route_obs.get("strategy_generation_mode")
            or commander_decision.get("strategy_generation_mode")
            or ""
        ).strip(),
        "strategist_call_decision": str(
            payload.get("strategist_call_decision")
            or route_obs.get("strategist_call_decision")
            or commander_decision.get("strategist_call_decision")
            or ""
        ).strip(),
        "strategist_fallback_used": bool(
            payload.get("strategist_fallback_used")
            if payload.get("strategist_fallback_used") is not None
            else route_obs.get("fallback_used")
            if route_obs.get("fallback_used") is not None
            else commander_decision.get("strategist_fallback_used")
        ),
        "route_source": "canonical_commander" if artifact_path else "",
        "artifact_path": artifact_path,
    }


def _event_route_rows(day_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_run: Dict[str, Dict[str, Any]] = {}
    sorted_rows = sorted(day_rows, key=lambda row: int(row.get("_epoch") or 0))
    for row in sorted_rows:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        current = by_run.setdefault(
            run_id,
            {
                "route_selected": "",
                "strategy_generation_mode": "",
                "strategist_call_decision": "",
                "strategist_fallback_used": False,
                "route_source": "event_fallback",
                "artifact_path": "",
            },
        )
        if stage == "commander_router" and event in {"route_selected", "end", "route"}:
            merged = _commander_route_from_payload(payload)
            for key in ("route_selected", "strategy_generation_mode", "strategist_call_decision"):
                if merged.get(key):
                    current[key] = merged[key]
            if merged.get("strategist_fallback_used"):
                current["strategist_fallback_used"] = True
        if stage == "strategist" and event == "policy_resolution":
            mode = str(payload.get("strategy_generation_mode") or "").strip()
            if mode:
                current["strategy_generation_mode"] = mode
            if bool(payload.get("fallback_used")):
                current["strategist_fallback_used"] = True
    return by_run


def build_commander_route_summary(
    *,
    reports_root: Path,
    day: str,
    day_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    canonical_dir = reports_root / "canonical" / day
    canonical_by_run: Dict[str, Dict[str, Any]] = {}
    if canonical_dir.exists():
        for run_dir in sorted(canonical_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            commander = read_json(run_dir / "commander.json")
            if not commander:
                continue
            row = _commander_route_from_payload(commander, artifact_path=str(run_dir / "commander.json"))
            if row.get("route_selected"):
                canonical_by_run[str(run_dir.name)] = row

    event_rows = day_rows or []
    event_by_run = _event_route_rows(event_rows)

    all_run_ids = set(canonical_by_run) | set(event_by_run)
    for row in event_rows:
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            all_run_ids.add(run_id)

    by_run: Dict[str, Dict[str, Any]] = {}
    route_selected_total: Counter[str] = Counter()
    strategy_generation_mode_total: Counter[str] = Counter()
    strategist_fallback_total = 0
    source_breakdown: Counter[str] = Counter()
    missing_count = 0

    for run_id in sorted(all_run_ids):
        selected = canonical_by_run.get(run_id)
        if not selected:
            selected = event_by_run.get(run_id)
        if not selected or not str(selected.get("route_selected") or "").strip():
            missing_count += 1
            continue
        by_run[run_id] = dict(selected)
        route_selected_total[str(selected.get("route_selected"))] += 1
        mode = str(selected.get("strategy_generation_mode") or "").strip()
        if mode:
            strategy_generation_mode_total[mode] += 1
        if bool(selected.get("strategist_fallback_used")):
            strategist_fallback_total += 1
        source_breakdown[str(selected.get("route_source") or "unknown")] += 1

    return {
        "route_source": "canonical_commander_preferred",
        "route_source_run_count": int(len(by_run)),
        "route_source_missing_count": int(missing_count),
        "route_selected_total": dict(route_selected_total),
        "strategy_generation_mode_total": dict(strategy_generation_mode_total),
        "strategist_fallback_total": int(strategist_fallback_total),
        "route_source_breakdown": dict(source_breakdown),
        "by_run": by_run,
    }
