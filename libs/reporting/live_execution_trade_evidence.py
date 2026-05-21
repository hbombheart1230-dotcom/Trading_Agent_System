from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.core.symbols import normalize_symbol
from libs.reporting.live_execution_event_evidence import (
    event_row_name,
    event_row_symbol,
    filter_canonical_events,
    merge_rows_by_identity,
    resolve_strategist_source_run_ids,
)
from libs.reporting.live_execution_report_artifacts import read_json_if_exists
from libs.reporting.live_execution_report_context import to_epoch

MONITOR_TIMELINE_CANONICAL_FIELDS = (
    "entry_minute_snapshot_age_minutes",
    "entry_minute_snapshot_was_stale",
    "entry_minute_refetch_attempted",
    "entry_minute_refetch_succeeded",
    "entry_minute_refetch_reason",
    "entry_minute_refetch_trigger_reason",
    "entry_minute_refetch_failure_reason",
    "entry_latest_candle_ts",
    "entry_inferred_spacing_minutes",
    "entry_series_class",
)


def load_latest_canonical_monitor_artifact(
    *,
    reports_root: Path,
    day: str,
    run_ids: List[str],
) -> Dict[str, Any]:
    canonical_root = reports_root / "canonical" / str(day or "")
    for run_id in reversed([str(x or "").strip() for x in list(run_ids or []) if str(x or "").strip()]):
        monitor_path = canonical_root / run_id / "monitor.json"
        payload = read_json_if_exists(monitor_path)
        if payload:
            return {
                "path": str(monitor_path),
                "payload": payload,
            }
    return {}


def merge_monitor_timeline_with_canonical(
    *,
    monitor_timeline: Dict[str, Any],
    canonical_monitor_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(monitor_timeline or {})
    artifact_path = str(canonical_monitor_artifact.get("path") or "").strip()
    artifact_payload = (
        canonical_monitor_artifact.get("payload")
        if isinstance(canonical_monitor_artifact.get("payload"), dict)
        else {}
    )
    threshold_snapshot = (
        artifact_payload.get("threshold_snapshot")
        if isinstance(artifact_payload.get("threshold_snapshot"), dict)
        else {}
    )
    if not threshold_snapshot:
        return out

    out["canonical_monitor_artifact_path"] = artifact_path
    out["canonical_monitor_run_id"] = str(artifact_payload.get("run_id") or "")
    out["canonical_monitor_freshness_mirrored"] = True
    for field in MONITOR_TIMELINE_CANONICAL_FIELDS:
        value = threshold_snapshot.get(field)
        if value not in (None, ""):
            out[field] = value

    threshold_rows = [dict(row) for row in list(out.get("threshold_snapshots") or []) if isinstance(row, dict)]
    if threshold_rows:
        latest_row = dict(threshold_rows[-1] or {})
        payload = dict(latest_row.get("payload") or {}) if isinstance(latest_row.get("payload"), dict) else {}
        for field in MONITOR_TIMELINE_CANONICAL_FIELDS:
            if payload.get(field) in (None, "") and threshold_snapshot.get(field) not in (None, ""):
                payload[field] = threshold_snapshot.get(field)
        latest_row["payload"] = payload
        threshold_rows[-1] = latest_row
    else:
        threshold_rows.append(
            {
                "ts": str(artifact_payload.get("ts") or artifact_payload.get("generated_at") or ""),
                "event_name": "monitor.threshold_snapshot",
                "level": "info",
                "run_id": str(artifact_payload.get("run_id") or ""),
                "trade_id": str(artifact_payload.get("trade_id") or ""),
                "session_id": str(artifact_payload.get("session_id") or ""),
                "cycle_id": str(artifact_payload.get("cycle_id") or ""),
                "agent": "monitor",
                "phase": str(artifact_payload.get("phase") or ""),
                "symbol": str(artifact_payload.get("symbol") or out.get("symbol") or ""),
                "payload": dict(threshold_snapshot),
                "source": "canonical_monitor_artifact",
                "artifact_path": artifact_path,
            }
        )
    out["threshold_snapshots"] = threshold_rows
    return out


def build_trade_evidence_from_events(
    *,
    event_rows: List[Dict[str, Any]],
    lifecycle: Dict[str, Any],
    reports_root: Optional[Path] = None,
    day: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    run_ids = [str(x or "") for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
    trade_id = str(lifecycle.get("trade_id") or "")
    symbol = str(lifecycle.get("symbol") or "")
    strategist_run_ids, linked_cached_frames = resolve_strategist_source_run_ids(
        event_rows=event_rows,
        lifecycle=lifecycle,
    )

    strategist_events = filter_canonical_events(
        event_rows,
        run_ids=strategist_run_ids,
        agent="strategist",
        event_names=[
            "strategist.market_context_snapshot",
            "strategist.global_sentiment_breakdown",
            "strategist.news_evidence_ranked",
            "strategist.decision_frame",
            "strategist.llm_response_saved",
        ],
    )
    scanner_events = filter_canonical_events(
        event_rows,
        run_ids=run_ids,
        agent="scanner",
        event_names=[
            "scanner.candidate_pool_snapshot",
            "scanner.candidate_ranking_table",
            "scanner.candidate_selection_reason",
            "scanner.selection_output",
        ],
    )
    monitor_events = filter_canonical_events(
        event_rows,
        run_ids=run_ids,
        agent="monitor",
        event_names=[
            "monitor.threshold_snapshot",
            "monitor.state_transition",
            "monitor.entry_decision_detail",
            "monitor.exit_decision_detail",
            "monitor.cycle_summary",
        ],
    )
    entry_ctx = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    entry_epoch = to_epoch(entry_ctx.get("ts")) or 0.0
    exit_epoch = to_epoch(exit_ctx.get("ts")) or 0.0
    if symbol and entry_epoch > 0.0:
        window_start = float(entry_epoch - 120.0)
        window_end = float((exit_epoch if exit_epoch > 0.0 else entry_epoch) + 120.0)
        symbol_monitor_events = [
            row
            for row in list(event_rows or [])
            if event_row_symbol(row) == normalize_symbol(symbol, allow_test_symbols=True)
            and event_row_name(row)
            in {
                "monitor.threshold_snapshot",
                "monitor.state_transition",
                "monitor.entry_decision_detail",
                "monitor.exit_decision_detail",
                "monitor.cycle_summary",
            }
            and window_start <= (to_epoch(row.get("ts")) or 0.0) <= window_end
        ]
        monitor_events = merge_rows_by_identity(monitor_events, symbol_monitor_events)
    monitor_run_ids = [
        str(row.get("run_id") or "").strip()
        for row in monitor_events
        if str(row.get("run_id") or "").strip()
    ]
    monitor_run_ids = sorted(set(list(run_ids) + monitor_run_ids))

    strategist_evidence = {
        "schema_version": "trade_strategist_evidence.v1",
        "trade_id": trade_id,
        "symbol": symbol,
        "run_ids": strategist_run_ids,
        "linked_cached_frame_sources": dict(linked_cached_frames),
        "market_context_snapshots": [row for row in strategist_events if row.get("event_name") == "strategist.market_context_snapshot"],
        "global_sentiment_breakdowns": [row for row in strategist_events if row.get("event_name") == "strategist.global_sentiment_breakdown"],
        "news_evidence_ranked": [row for row in strategist_events if row.get("event_name") == "strategist.news_evidence_ranked"],
        "decision_frames": [row for row in strategist_events if row.get("event_name") == "strategist.decision_frame"],
        "llm_response_saved": [row for row in strategist_events if row.get("event_name") == "strategist.llm_response_saved"],
    }
    scanner_evidence = {
        "schema_version": "trade_scanner_evidence.v1",
        "trade_id": trade_id,
        "symbol": symbol,
        "run_ids": run_ids,
        "candidate_pool_snapshots": [row for row in scanner_events if row.get("event_name") == "scanner.candidate_pool_snapshot"],
        "candidate_ranking_tables": [row for row in scanner_events if row.get("event_name") == "scanner.candidate_ranking_table"],
        "candidate_selection_reasons": [row for row in scanner_events if row.get("event_name") == "scanner.candidate_selection_reason"],
        "selection_outputs": [row for row in scanner_events if row.get("event_name") == "scanner.selection_output"],
    }
    monitor_timeline = {
        "schema_version": "trade_monitor_timeline.v1",
        "trade_id": trade_id,
        "symbol": symbol,
        "run_ids": monitor_run_ids,
        "run_ids_all_from_lifecycle": run_ids,
        "symbol_time_window_applied": bool(symbol and entry_epoch > 0.0),
        "threshold_snapshots": [row for row in monitor_events if row.get("event_name") == "monitor.threshold_snapshot"],
        "state_transitions": [row for row in monitor_events if row.get("event_name") == "monitor.state_transition"],
        "entry_decision_details": [row for row in monitor_events if row.get("event_name") == "monitor.entry_decision_detail"],
        "exit_decision_details": [row for row in monitor_events if row.get("event_name") == "monitor.exit_decision_detail"],
        "cycle_summaries": [row for row in monitor_events if row.get("event_name") == "monitor.cycle_summary"],
    }
    if isinstance(reports_root, Path) and str(day or "").strip():
        monitor_timeline = merge_monitor_timeline_with_canonical(
            monitor_timeline=monitor_timeline,
            canonical_monitor_artifact=load_latest_canonical_monitor_artifact(
                reports_root=reports_root,
                day=str(day or ""),
                run_ids=run_ids,
            ),
        )
    return strategist_evidence, scanner_evidence, monitor_timeline
