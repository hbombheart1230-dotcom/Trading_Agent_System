from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "q9_decision_windows.v1"
KST = ZoneInfo("Asia/Seoul")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)][:limit]


def _day(state: Mapping[str, Any]) -> str:
    for value in (
        state.get("started_at"),
        state.get("ts"),
        state.get("now_iso"),
        state.get("tick_ts"),
    ):
        text = str(value or "").strip()
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc).astimezone(KST).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            pass
    return datetime.now(timezone.utc).astimezone(KST).strftime("%Y-%m-%d")


def _generated_at(state: Mapping[str, Any]) -> str:
    for value in (state.get("ts"), state.get("now_iso"), state.get("tick_ts")):
        text = str(value or "").strip()
        if text:
            try:
                return datetime.fromtimestamp(float(text), tz=timezone.utc).isoformat(timespec="seconds")
            except (TypeError, ValueError, OSError):
                return text
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_q9_decision_id(state: dict[str, Any]) -> str:
    existing = str(state.get("q9_decision_id") or "").strip()
    if existing:
        return existing
    run_id = str(state.get("run_id") or "").strip()
    seed = run_id or _generated_at(state)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", seed).strip("-")[:96] or "runtime"
    decision_id = f"Q9_{_day(state).replace('-', '')}_{safe}"
    state["q9_decision_id"] = decision_id
    return decision_id


def _output_path(state: Mapping[str, Any]) -> Path:
    reports_root = Path(
        str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports") or "reports")
    )
    return reports_root / "operator_summary" / "daily" / _day(state) / "q9_decision_windows.json"


def _read_payload(path: Path, *, day: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("schema_version", SCHEMA_VERSION)
            payload.setdefault("day", day)
            payload.setdefault("windows", [])
            return payload
    except Exception:
        pass
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "observation_only",
        "day": day,
        "windows": [],
    }


def _upsert(state: dict[str, Any], stage_payload: Mapping[str, Any]) -> dict[str, Any]:
    decision_id = ensure_q9_decision_id(state)
    path = _output_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_payload(path, day=_day(state))
    windows = [
        dict(row)
        for row in payload.get("windows") or []
        if isinstance(row, Mapping)
    ]
    target = next(
        (row for row in windows if str(row.get("decision_id") or "") == decision_id),
        None,
    )
    if target is None:
        generated_at = _generated_at(state)
        try:
            generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            generated_dt = None
        target = {
            "schema_version": "q9_decision_window.v1",
            "behavior_effect": "observation_only",
            "decision_id": decision_id,
            "decision_epoch": (
                state.get("now_epoch")
                if state.get("now_epoch") is not None
                else int(generated_dt.timestamp())
                if generated_dt is not None
                else None
            ),
            "generated_at": generated_at,
            "run_id": str(state.get("run_id") or ""),
        }
        windows.append(target)
    target.update(dict(stage_payload))
    target["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload["windows"] = windows
    payload["window_count"] = len(windows)
    payload["updated_at"] = target["updated_at"]
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)
    state["q9_decision_snapshot"] = dict(target)
    state["q9_decision_snapshot_path"] = str(path)
    scanner_output = state.get("scanner_output")
    if isinstance(scanner_output, dict):
        scanner_output["q9_decision_id"] = decision_id
        scanner_output["q9_decision_snapshot"] = dict(target)
        scanner_output["q9_decision_snapshot_path"] = str(path)
    return {"status": "ok", "path": str(path), "decision_id": decision_id}


def capture_scanner_decision_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    scanner = _mapping(state.get("scanner_output"))
    ranking_payload = _mapping(state.get("scanner_candidate_ranking_table"))
    strategist = _mapping(state.get("strategist_output"))
    intrinsic = _rows(
        ranking_payload.get("scanner_intrinsic_control_top10")
        or scanner.get("scanner_intrinsic_control_top10")
    )
    post = _rows(
        ranking_payload.get("post_strategist_top10")
        or scanner.get("ranked_candidates")
        or state.get("ranked_candidates")
    )
    selected = _mapping(state.get("selected"))
    return _upsert(
        state,
        {
            "window_type": "scanner_selection",
            "candidate_pool_id": str(scanner.get("candidate_pool_id") or ensure_q9_decision_id(state)),
            "scanner_control": {
                "scope": "same_candidate_universe_ranking_only",
                "source": "scanner_intrinsic_control_snapshot",
                "evidence_class": "TRUSTED_SHADOW",
                "top10": intrinsic,
                "top1_symbol": str((intrinsic[0] if intrinsic else {}).get("symbol") or ""),
                "universe_control_available": False,
                "limitation": (
                    "Candidate sourcing may already reflect Strategist guidance; this control isolates "
                    "ranking weights within the same candidate universe."
                ),
            },
            "strategist_selection": {
                "strategist_run_id": str(
                    scanner.get("strategist_run_id")
                    or strategist.get("run_id")
                    or strategist.get("strategist_run_id")
                    or state.get("run_id")
                    or ""
                ),
                "scenario": str(
                    strategist.get("scenario")
                    or strategist.get("market_scenario")
                    or strategist.get("market_regime")
                    or ""
                ),
                "playbook": str(
                    strategist.get("final_playbook")
                    or strategist.get("playbook")
                    or scanner.get("strategist_playbook")
                    or ""
                ),
                "post_strategist_top10": post,
                "selected_symbol": str(selected.get("symbol") or scanner.get("top_stock") or ""),
                "evidence_class": "REALIZED_DECISION_SNAPSHOT",
            },
        },
    )


def capture_commander_decision_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    monitor = _mapping(state.get("monitor_output"))
    intents = state.get("intents") if isinstance(state.get("intents"), list) else []
    first_intent = _mapping(intents[0]) if intents else {}
    decision = str(state.get("decision") or "noop").strip().lower()
    selected = _mapping(state.get("selected"))
    symbol = str(
        first_intent.get("symbol")
        or monitor.get("selected_symbol")
        or selected.get("symbol")
        or state.get("top_stock")
        or ""
    )
    existing_snapshot = _mapping(state.get("q9_decision_snapshot"))
    window_type = (
        "scanner_selection"
        if isinstance(existing_snapshot.get("scanner_control"), Mapping)
        else "commander_monitor_only"
    )
    return _upsert(
        state,
        {
            "window_type": window_type,
            "commander_final": {
                "decision_id": ensure_q9_decision_id(state),
                "decision": decision,
                "selected_symbol": symbol if decision == "approve" else "",
                "candidate_symbol": symbol,
                "veto": decision == "reject",
                "no_trade": decision in {"noop", "reject", "retry_scan"},
                "reason": str(state.get("decision_reason") or ""),
                "detail": str(state.get("decision_detail") or ""),
                "monitor_intent": str(
                    monitor.get("intent_side")
                    or first_intent.get("side")
                    or first_intent.get("action")
                    or "NOOP"
                ).upper(),
                "authority_scope": "final_approval_or_veto",
                "evidence_class": "REALIZED_DECISION_SNAPSHOT",
            },
        },
    )
