# libs/event_logger.py
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def new_run_id() -> str:
    """Create a unique run id for a single cycle/run."""
    return uuid.uuid4().hex


def _utc_iso() -> str:
    """UTC ISO timestamp (no microseconds)"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_kst_iso(iso_ts: str) -> str:
    """
    Convert an ISO timestamp to KST (+09:00) ISO format.

    If timezone info is missing, treat it as UTC.
    """
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    kst = timezone(timedelta(hours=9))
    return dt.astimezone(kst).replace(microsecond=0).isoformat()


def resolve_event_log_path(default: str = "./data/logs/events.jsonl") -> Path:
    """Resolve the effective event-log path.

    Runtime defaults to the canonical operator log. During pytest, when no
    explicit EVENT_LOG_PATH is provided, route writes to a separate test log so
    local test runs do not pollute live operator artifacts.
    """
    raw = str(os.getenv("EVENT_LOG_PATH", "") or "").strip()
    if raw:
        return Path(raw)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return Path("./data/logs/dev/testing/pytest_events.jsonl")
    return Path(default)


def _is_canonical_operator_event_log_path(path: Path) -> bool:
    try:
        candidate = Path(path)
        canonical_relative = Path("data") / "logs" / "events.jsonl"
        if not candidate.is_absolute():
            return candidate == canonical_relative or candidate == Path(".") / canonical_relative
        return candidate.resolve() == (Path.cwd() / canonical_relative).resolve()
    except Exception:
        return False


def _event_log_max_bytes() -> int:
    raw = str(os.getenv("EVENT_LOG_MAX_BYTES", "") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 1_000_000_000
    return max(10_000_000, value)


def _event_log_payload_max_bytes() -> int:
    raw = str(os.getenv("EVENT_LOG_PAYLOAD_MAX_BYTES", "") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 10_000
    return max(3_000, value)


def _event_log_compact_top_items() -> int:
    raw = str(os.getenv("EVENT_LOG_COMPACT_TOP_ITEMS", "") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 5
    return max(1, min(20, value))


def _event_log_compaction_enabled() -> bool:
    raw = str(os.getenv("EVENT_LOG_COMPACT_HEAVY_PAYLOADS", "1") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _rotate_large_event_log(path: Path) -> None:
    try:
        if not _is_canonical_operator_event_log_path(path):
            return
        if not path.exists() or path.stat().st_size < _event_log_max_bytes():
            return
        archive_dir = path.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = archive_dir / f"{path.stem}_{stamp}_{os.getpid()}{path.suffix}"
        path.replace(target)
    except Exception:
        # Logging must never stop trading/runtime flow. Rotation is best-effort.
        return


def _payload_size_bytes(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return 0


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            out[str(key)] = _sanitize_payload(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize_payload(item) for item in value]
    return str(value)


_COMPACT_ROW_KEYS = (
    "rank",
    "symbol",
    "name",
    "score",
    "score_total",
    "pre_adjust_score_total",
    "post_adjust_score_total",
    "scanner_intrinsic_control_score_total",
    "confidence",
    "risk_score",
    "entry_compatibility_score",
    "scanner_chart_fit_score",
    "scanner_macro_chart_fit_score",
    "tactical_strategy",
    "tactical_subtype",
    "playbook",
    "candidate_source",
    "dominant_block_reason",
    "expected_monitor_block_reason",
    "why",
)


def _compact_candidate_row(row: Any) -> Any:
    if not isinstance(row, dict):
        return _compact_value(row, depth=1)
    out: Dict[str, Any] = {}
    for key in _COMPACT_ROW_KEYS:
        value = row.get(key)
        if value not in (None, "", [], {}):
            out[key] = _compact_value(value, depth=1)
    for key in ("sources", "source_scores", "score_breakdown", "tactic_suitability", "compatibility_components"):
        value = row.get(key)
        if value not in (None, "", [], {}):
            out[key] = _compact_value(value, depth=1)
    return out


def _compact_rows(rows: Any, *, limit: int) -> list[Any]:
    if not isinstance(rows, list):
        return []
    return [_compact_candidate_row(row) for row in rows[:limit]]


def _symbol_list(rows: Any, *, limit: int) -> list[str]:
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows[:limit]:
        if isinstance(row, dict) and str(row.get("symbol") or "").strip():
            out.append(str(row.get("symbol") or "").strip())
    return out


def _compact_value(value: Any, *, depth: int = 2) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return value if len(value) <= 800 else value[:800] + "...[truncated]"
    if isinstance(value, dict):
        if depth <= 0:
            return {"_type": "dict", "_keys": [str(key) for key in list(value.keys())[:20]]}
        out: Dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            out[str(key)] = _compact_value(item, depth=depth - 1)
        if len(value) > 40:
            out["_truncated_key_count"] = len(value) - 40
        return out
    if isinstance(value, (list, tuple)):
        limit = _event_log_compact_top_items()
        out = [_compact_value(item, depth=depth - 1) for item in list(value)[:limit]]
        if len(value) > limit:
            out.append({"_truncated_item_count": len(value) - limit})
        return out
    return str(value)


def _copy_known_fields(payload: Dict[str, Any], keys: tuple[str, ...]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            out[key] = _compact_value(value, depth=2)
    return out


def _compact_candidate_ranking_table(payload: Dict[str, Any]) -> Dict[str, Any]:
    limit = _event_log_compact_top_items()
    out = _copy_known_fields(
        payload,
        (
            "tie_break_rule",
            "reconstructed_pre_adjust_evidence_class",
            "reconstructed_pre_adjust_limitation",
            "scanner_intrinsic_control_source",
            "scanner_intrinsic_control_evidence_class",
            "scanner_intrinsic_control_limitation",
        ),
    )
    for key in (
        "rows",
        "post_strategist_top10",
        "reconstructed_pre_adjust_top10",
        "scanner_intrinsic_control_top10",
        "scanner_intrinsic_control_top20",
    ):
        rows = payload.get(key)
        if isinstance(rows, list):
            out[f"{key}_count"] = len(rows)
            out[f"{key}_symbols"] = _symbol_list(rows, limit=20)
            out[key] = _compact_rows(rows, limit=limit)

    snapshot = payload.get("pre_strategist_full_universe_snapshot")
    if isinstance(snapshot, dict):
        source_top20 = snapshot.get("source_universe_top20")
        intrinsic_top20 = snapshot.get("intrinsic_ranked_top20")
        out["pre_strategist_full_universe_snapshot"] = {
            "schema_version": snapshot.get("schema_version"),
            "behavior_effect": snapshot.get("behavior_effect"),
            "source": snapshot.get("source"),
            "scope": snapshot.get("scope"),
            "candidate_count": snapshot.get("candidate_count"),
            "source_universe_top20_symbols": _symbol_list(source_top20, limit=20),
            "intrinsic_ranked_top20_symbols": _symbol_list(intrinsic_top20, limit=20),
            "source_universe_top20": _compact_rows(source_top20, limit=limit),
            "intrinsic_ranked_top20": _compact_rows(intrinsic_top20, limit=limit),
            "limitation": snapshot.get("limitation"),
        }
    return out


def _compact_event_payload(stage: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    original_bytes = _payload_size_bytes(payload)
    max_bytes = _event_log_payload_max_bytes()
    if not _event_log_compaction_enabled() or original_bytes <= max_bytes:
        return payload

    stage_event = f"{stage}.{event}"
    if stage_event == "scanner.candidate_ranking_table":
        compacted = _compact_candidate_ranking_table(payload)
    elif stage_event == "scanner.selection_output":
        compacted = _copy_known_fields(
            payload,
            (
                "selected_symbol",
                "scanner_selected_symbol",
                "selected_rank",
                "scanner_rank",
                "selected_score_total",
                "scanner_score_total",
                "margin_vs_second",
                "playbook",
                "policy_source",
                "entry_compatibility_score",
                "dominant_block_reason",
                "expected_monitor_block_reason",
                "selection_summary",
                "selection_reason_with_bias",
                "why_selected",
                "runner_ups_lost",
                "tie_break_rule",
                "final_decision_basis",
            ),
        )
    elif stage_event == "scanner.summary":
        compacted = _copy_known_fields(
            payload,
            (
                "candidate_source",
                "candidate_pool_before_filter",
                "candidate_pool_after_filter",
                "total_candidates_before_filter",
                "total_candidates_after_filter",
                "top_stock",
                "top_score",
                "scanner_selected_symbol",
                "scanner_rank",
                "scanner_score_total",
                "scanner_score_breakdown",
                "scanner_top_candidates",
                "top_ranked_symbols",
                "strategist_playbook",
                "condition_search_status",
                "condition_search_source",
                "condition_search_reason",
                "scan_aggressiveness",
                "scanner_bias_applied",
                "scanner_memory_bias_applied",
                "market_representative_guard_applied",
                "blocker_family_concentration_applied",
                "selection_vetoed",
                "selection_veto_reason",
            ),
        )
    elif stage_event.startswith("monitor."):
        compacted = _copy_known_fields(
            payload,
            (
                "run_id",
                "symbol",
                "decision",
                "action",
                "reason",
                "final_decision",
                "primary_reason_code",
                "hard_filter_passed",
                "hard_filter_fail_reasons",
                "total_score",
                "entry_threshold",
                "score_passed",
                "scoring_mode",
                "legacy_entry_decision",
                "scoring_entry_decision",
                "entry_decision",
                "entry_reason",
                "exit_decision",
                "exit_reason",
                "entry_triggered",
                "entry_evaluated",
                "entry_pattern",
                "entry_quality_score",
                "entry_quality_tier",
                "score_breakdown",
                "policy_alignment_summary",
                "policy_aware_gating",
                "chart_structure_decision_hint",
                "no_trade_surface",
                "scanner_monitor_handoff",
                "entry_blocker_surface",
                "entry_threshold_margins",
                "entry_thresholds",
                "exit_thresholds",
                "watch_axes",
                "applied_policy",
                "effective_policy",
                "current_price",
                "vwap",
                "volume_ratio",
                "entry_volume_ratio",
                "entry_pullback_depth_pct",
                "entry_minutes_since_session_open",
                "entry_latest_candle_ts",
                "entry_minute_refetch_attempted",
                "entry_minute_refetch_succeeded",
                "entry_minute_refetch_failure_reason",
            ),
        )
    elif stage_event.startswith("commander.") or stage_event.startswith("commander_router."):
        compacted = _copy_known_fields(
            payload,
            (
                "mode",
                "phase",
                "symbol",
                "selected_symbol",
                "decision",
                "reason",
                "route",
                "route_reason",
                "open_position_count",
                "max_positions",
                "position_symbols",
                "q9",
                "q10",
                "q11",
                "q12",
                "applied_policy",
                "effective_policy",
                "commander_decision",
            ),
        )
    elif stage_event.startswith("decision_trace."):
        compacted = _copy_known_fields(
            payload,
            (
                "agent",
                "symbol",
                "decision",
                "reason",
                "selected_symbol",
                "final_decision",
                "primary_reason_code",
                "payload",
            ),
        )
    elif stage_event.startswith("strategist."):
        compacted = _copy_known_fields(
            payload,
            (
                "scenario",
                "market_regime",
                "market_regime_rail",
                "risk_level",
                "selected_strategy",
                "selected_playbook",
                "priority_symbols",
                "avoid_symbols",
                "news_quality",
                "global_sentiment",
                "recommendations",
                "decision",
                "reason",
            ),
        )
    else:
        compacted = _compact_value(payload, depth=2)
        if not isinstance(compacted, dict):
            compacted = {"value": compacted}

    compacted["_event_log_compacted"] = True
    compacted["_event_log_original_bytes"] = original_bytes
    compacted["_event_log_original_keys"] = [str(key) for key in list(payload.keys())[:80]]
    if _payload_size_bytes(compacted) > max_bytes:
        compacted = {
            "_event_log_compacted": True,
            "_event_log_original_bytes": original_bytes,
            "_event_log_original_keys": [str(key) for key in list(payload.keys())[:80]],
            "_event_log_compaction_fallback": "generic_depth_1",
            "summary": _compact_value(compacted, depth=1),
        }
    return compacted


def build_event_envelope(
    *,
    run_id: str,
    stage: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    ts: Optional[str] = None,
    event_name: str = "",
    level: str = "info",
    trade_id: str = "",
    session_id: str = "",
    cycle_id: str = "",
    agent: str = "",
    phase: str = "",
    symbol: str = "",
) -> Dict[str, Any]:
    ts_utc = ts or _utc_iso()
    stage_text = str(stage or "").strip()
    event_text = str(event or "").strip()
    compact_payload = _compact_event_payload(stage_text, event_text, payload or {})
    safe_payload = _sanitize_payload(compact_payload)
    event_name_text = str(event_name or "").strip() or ".".join(part for part in (stage_text, event_text) if part)
    agent_text = str(agent or "").strip() or stage_text
    phase_text = str(phase or "").strip()
    symbol_text = str(symbol or "").strip()
    trade_id_text = str(trade_id or "").strip()
    session_id_text = str(session_id or "").strip()
    cycle_id_text = str(cycle_id or "").strip()
    return {
        "run_id": run_id,
        "ts": ts_utc,
        "ts_kst": _to_kst_iso(ts_utc),
        "stage": stage_text,
        "event": event_text,
        "event_name": event_name_text,
        "level": str(level or "info").strip().lower() or "info",
        "trade_id": trade_id_text,
        "session_id": session_id_text,
        "cycle_id": cycle_id_text,
        "agent": agent_text,
        "phase": phase_text,
        "symbol": symbol_text,
        "payload": safe_payload,
    }


def log_state_event(
    logger: "EventLogger",
    state: Dict[str, Any],
    *,
    stage: str,
    event: str,
    event_name: str,
    payload: Optional[Dict[str, Any]] = None,
    level: str = "info",
    agent: str = "",
    phase: str = "",
    symbol: str = "",
    trade_id: str = "",
    session_id: str = "",
    cycle_id: str = "",
    ts: Optional[str] = None,
) -> Dict[str, Any]:
    runtime_plan = state.get("runtime_plan") if isinstance(state.get("runtime_plan"), dict) else {}
    return logger.log(
        run_id=str(state.get("run_id") or "").strip() or "unknown-run",
        stage=stage,
        event=event,
        event_name=event_name,
        level=level,
        trade_id=str(trade_id or state.get("trade_id") or "").strip(),
        session_id=str(session_id or state.get("session_id") or runtime_plan.get("session_id") or "").strip(),
        cycle_id=str(cycle_id or state.get("cycle_id") or "").strip(),
        agent=str(agent or stage or "").strip(),
        phase=str(phase or state.get("phase") or runtime_plan.get("phase") or "").strip(),
        symbol=str(symbol or state.get("symbol") or "").strip(),
        payload=payload or {},
        ts=ts,
    )


@dataclass
class EventLogger:
    """
    Append-only JSONL event logger.

    - One event per line (JSONL)
    - Minimal schema enforced
    - Creates parent dirs automatically
    """
    log_path: Path

    def __post_init__(self) -> None:
        self.log_path = Path(self.log_path)
        if (
            os.getenv("PYTEST_CURRENT_TEST")
            and not str(os.getenv("EVENT_LOG_PATH", "") or "").strip()
            and _is_canonical_operator_event_log_path(self.log_path)
        ):
            self.log_path = resolve_event_log_path()

    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
        event_name: str = "",
        level: str = "info",
        trade_id: str = "",
        session_id: str = "",
        cycle_id: str = "",
        agent: str = "",
        phase: str = "",
        symbol: str = "",
    ) -> Dict[str, Any]:
        """
        Append one event to JSONL.

        Schema:
        {
          "run_id": "...",
          "ts": "2026-02-07T01:23:45+00:00",
          "ts_kst": "2026-02-07T10:23:45+09:00",
          "stage": "strategist_plan",
          "event": "decision",
          "payload": {...}
        }
        """
        if not run_id or not isinstance(run_id, str):
            raise ValueError("run_id must be a non-empty string")
        if not stage or not isinstance(stage, str):
            raise ValueError("stage must be a non-empty string")
        if not event or not isinstance(event, str):
            raise ValueError("event must be a non-empty string")

        rec = build_event_envelope(
            run_id=run_id,
            stage=stage,
            event=event,
            payload=payload,
            ts=ts,
            event_name=event_name,
            level=level,
            trade_id=trade_id,
            session_id=session_id,
            cycle_id=cycle_id,
            agent=agent,
            phase=phase,
            symbol=symbol,
        )

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_large_event_log(self.log_path)

        # Append atomically-ish (single write) for most OSes
        line = json.dumps(rec, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

        return rec

    def read_all(self) -> list[Dict[str, Any]]:
        """Convenience reader for local debugging/tests."""
        if not self.log_path.exists():
            return []
        out: list[Dict[str, Any]] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out
