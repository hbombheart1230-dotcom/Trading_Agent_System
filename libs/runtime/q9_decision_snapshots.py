from __future__ import annotations

import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from libs.core.path_isolation import isolate_canonical_path_for_pytest


SCHEMA_VERSION = "q9_decision_windows.v1"
KST = ZoneInfo("Asia/Seoul")
_WRITE_LOCK = threading.Lock()


@contextmanager
def _cross_process_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        except ImportError:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        handle.seek(0)
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except ImportError:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)][:limit]


def _compact_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _compact_scalar_mapping(value: Any, *, limit: int = 24) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key)[:80]: _compact_scalar(raw)
        for key, raw in list(value.items())[:limit]
        if isinstance(raw, (str, int, float, bool)) or raw is None
    }


def _compact_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    wanted = (
        "rank",
        "symbol",
        "name",
        "score",
        "score_total",
        "total_score",
        "pre_adjust_score_total",
        "confidence",
        "risk_score",
        "theme",
        "theme_name",
        "quant_tactic_id",
        "tactical_subtype",
        "primary_failure_axis",
        "reason",
        "would_enter",
        "guard_blocked",
        "cost_floor_state",
        "entry_quant_cost_floor_state",
        "q9_selected",
        "q9_decision_role",
    )
    out = {key: _compact_scalar(row.get(key)) for key in wanted if key in row}
    if "symbol" not in out and row.get("ticker"):
        out["symbol"] = _compact_scalar(row.get("ticker"))
    sources = row.get("sources")
    if isinstance(sources, list):
        out["sources"] = [str(value)[:80] for value in sources[:8] if str(value)]
    source_scores = _compact_scalar_mapping(row.get("source_scores"), limit=12)
    if source_scores:
        out["source_scores"] = source_scores
    for key in (
        "score_breakdown",
        "scanner_chart_fit",
        "scanner_macro_chart_fit",
        "quant_factors",
        "cost_filter",
    ):
        compact = _compact_scalar_mapping(row.get(key))
        if compact:
            out[key] = compact
    feature_snapshot = _mapping(row.get("compact_feature_snapshot"))
    if feature_snapshot:
        out["compact_feature_snapshot"] = {
            key: _compact_scalar(feature_snapshot.get(key))
            for key in (
                "skill_quote_price",
                "engine_close_last",
                "quote_best_bid",
                "quote_best_ask",
                "intraday_change_pct",
            )
            if feature_snapshot.get(key) not in (None, "")
        }
    return out


def _compact_candidates(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [_compact_candidate(row) for row in rows[:limit]]


def _compact_mapping(value: Mapping[str, Any], *, list_limit: int = 20) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in value.items():
        if isinstance(raw, Mapping):
            nested = {
                nested_key: _compact_scalar(nested_value)
                for nested_key, nested_value in raw.items()
                if isinstance(nested_value, (str, int, float, bool)) or nested_value is None
            }
            if nested:
                out[str(key)] = nested
        elif isinstance(raw, list):
            if key in {
                "intrinsic_ranked_top20",
                "top10",
                "top20",
                "post_strategist_top10",
                "ranked_candidates",
                "candidates",
            }:
                out[str(key)] = _compact_candidates(
                    [dict(row) for row in raw if isinstance(row, Mapping)],
                    limit=list_limit,
                )
        elif isinstance(raw, (str, int, float, bool)) or raw is None:
            out[str(key)] = raw
    return out


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
    reports_root = isolate_canonical_path_for_pytest(
        str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports") or "reports")
        ,
        canonical_path="reports",
        isolated_name="reports",
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
    with _WRITE_LOCK, _cross_process_lock(path):
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
        temp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
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
        ranking_payload.get("scanner_intrinsic_control_top20")
        or scanner.get("scanner_intrinsic_control_top20")
        or ranking_payload.get("scanner_intrinsic_control_top10")
        or scanner.get("scanner_intrinsic_control_top10")
        ,
        limit=20,
    )
    post = _rows(
        ranking_payload.get("post_strategist_top10")
        or scanner.get("ranked_candidates")
        or state.get("ranked_candidates")
    )
    selected = _mapping(state.get("selected"))
    pre_strategist_universe = _mapping(
        ranking_payload.get("pre_strategist_full_universe_snapshot")
        or scanner.get("pre_strategist_full_universe_snapshot")
    )
    source_universe = _mapping(state.get("scanner_source_universe_before_strategy_weighting"))
    if source_universe:
        pre_strategist_universe = {
            **pre_strategist_universe,
            "source_universe_before_filters": source_universe,
        }
    compact_pre = _compact_mapping(pre_strategist_universe, list_limit=20)
    compact_pre["intrinsic_ranked_top20"] = (
        _compact_candidates(_rows(pre_strategist_universe.get("intrinsic_ranked_top20"), limit=20), limit=20)
        or _compact_candidates(intrinsic, limit=20)
    )
    return _upsert(
        state,
        {
            "window_type": "scanner_selection",
            "candidate_pool_id": str(scanner.get("candidate_pool_id") or ensure_q9_decision_id(state)),
            "scanner_control": {
                "scope": "same_candidate_universe_ranking_only",
                "source": "scanner_intrinsic_control_snapshot",
                "evidence_class": "TRUSTED_SHADOW",
                "top10": _compact_candidates(intrinsic, limit=10),
                "top20": _compact_candidates(intrinsic, limit=20),
                "top1_symbol": str((intrinsic[0] if intrinsic else {}).get("symbol") or ""),
                "universe_control_available": False,
                "limitation": (
                    "Candidate sourcing may already reflect Strategist guidance; this control isolates "
                    "ranking weights within the same candidate universe."
                ),
            },
            "scanner_pre_strategist_universe": {
                **compact_pre,
                "schema_version": str(
                    pre_strategist_universe.get("schema_version")
                    or "q9_scanner_pre_strategist_universe.v1"
                ),
                "behavior_effect": "evaluation_only",
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
                "post_strategist_top10": _compact_candidates(post, limit=10),
                "selected_symbol": str(selected.get("symbol") or scanner.get("top_stock") or ""),
                "evidence_class": "REALIZED_DECISION_SNAPSHOT",
            },
        },
    )


def capture_commander_decision_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    monitor = _mapping(state.get("monitor_output"))
    monitor_entry = _mapping(state.get("monitor_entry"))
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
    entry_cost_filter = _mapping(
        monitor.get("entry_cost_filter") or monitor_entry.get("entry_cost_filter")
    )
    directional_edge_estimate = _mapping(
        monitor.get("directional_edge_estimate")
        or monitor_entry.get("directional_edge_estimate")
    )
    monitor_intent = str(
        monitor.get("intent_side")
        or first_intent.get("side")
        or first_intent.get("action")
        or "NOOP"
    ).upper()
    monitor_observation = {
        "intent": monitor_intent,
        "reason": str(
            monitor.get("entry_exit_reason")
            or monitor_entry.get("guard_reason")
            or monitor_entry.get("reason")
            or ""
        ),
        "entry_triggered": bool(monitor_entry.get("triggered")),
        "entry_guard_blocked": bool(monitor_entry.get("guard_blocked")),
        "entry_guard_reason": str(monitor_entry.get("guard_reason") or ""),
        "entry_primary_failure_axis": str(
            monitor_entry.get("primary_failure_axis") or ""
        ),
        "entry_lane": str(
            monitor.get("entry_lane") or monitor_entry.get("entry_lane") or ""
        ),
        "cost_floor_state": str(
            _mapping(monitor_entry.get("entry_quant_decision"))
            .get("cost_edge", {})
            .get("cost_floor_state")
            if isinstance(
                _mapping(monitor_entry.get("entry_quant_decision")).get("cost_edge"),
                Mapping,
            )
            else ""
        ),
        "cost_filter_passed": bool(entry_cost_filter.get("passed")),
        "cost_filter_fail_reasons": [
            str(value)
            for value in list(entry_cost_filter.get("fail_reasons") or [])[:12]
        ],
        "directional_edge_estimate": {
            **_compact_scalar_mapping(directional_edge_estimate),
            "failed_requirements": [
                str(value)
                for value in list(
                    directional_edge_estimate.get("failed_requirements") or []
                )[:12]
            ],
        }
        if directional_edge_estimate
        else {},
    }
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
                "monitor_intent": monitor_intent,
                "monitor_reason": str(monitor_observation.get("reason") or ""),
                "monitor_observation": monitor_observation,
                "authority_scope": "final_approval_or_veto",
                "evidence_class": "REALIZED_DECISION_SNAPSHOT",
            },
        },
    )
