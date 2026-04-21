from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from libs.reporting.llm_artifacts import (
    build_compact_input_artifact,
    trade_artifact_paths,
    write_json,
)
from libs.reporting.trade_report_ai import build_ai_trade_report_compact_input
from libs.reporting.trade_report_runtime_generation import (
    apply_ai_trade_report_generation_result,
    apply_runtime_diagnostics_context,
    build_live_generation_state_payload,
    execute_ai_trade_report_generation,
    load_report_generation_state,
    plan_live_trade_report_generation,
    report_generation_state_path,
    write_report_generation_state,
)
from libs.reporting.trade_report_runtime_policy import (
    base_report_diagnostics,
    report_next_step,
    report_reason_human,
    resolve_trade_report_policy,
    seed_diagnostics_for_policy,
)
from libs.reporting.trade_regeneration_truth import rehydrate_lifecycle_bundle_execution_truth
from libs.reporting.trade_story_pipeline import build_trade_story_input_from_bundle, render_bundle_markdown


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _trade_day_from_trade_id(trade_id: str) -> str:
    value = str(trade_id or "").strip()
    match = re.match(r"^TRD_(\d{4})(\d{2})(\d{2})_", value)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bundle_role() -> str:
    return "intraday_trade_report_bundle"


def _script_path(root: Path) -> Path:
    return root / "scripts" / "run_live_execution_bundle_report.py"


def _runner_module_name() -> str:
    return "libs.reporting.live_execution_bundle_runner"


def _brief_cache_dir(root: Path) -> Path:
    return Path(
        os.getenv("OPERATOR_UI_CACHE_PATH", str(root / "data" / "operator_ui" / "brief_cache"))
    )


def _bundle_job_lock_path(root: Path) -> Path:
    return root / "reports" / "runtime" / "intraday_trade_report_bundle.lock"


def _bundle_job_queue_path(root: Path) -> Path:
    return root / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"


def _read_lock_payload(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _stable_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_fingerprint(payload: Any) -> str:
    return hashlib.sha256(_stable_json_text(payload).encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _to_epoch(ts: Any) -> Optional[int]:
    text = str(ts or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except Exception:
        return None


def _null_if_empty(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def normalize_trade_id_filters(values: Any) -> List[str]:
    raw_values: List[str] = []
    if isinstance(values, list):
        raw_values = [str(value or "") for value in values]
    elif values not in (None, ""):
        raw_values = [str(values or "")]
    out: List[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in str(raw or "").split(","):
            trade_id = str(part or "").strip()
            if not trade_id or trade_id in seen:
                continue
            out.append(trade_id)
            seen.add(trade_id)
    return out


def build_hold_signal_transitions(monitor_context_snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    previous: Dict[str, Any] | None = None
    keys = ("posture", "monitor_reason", "exit_reason", "active_exit_axis", "exit_triggered")
    for current in list(monitor_context_snapshots or []):
        if not isinstance(current, dict):
            continue
        if previous is None:
            previous = current
            continue
        changes: Dict[str, Dict[str, Any]] = {}
        for key in keys:
            before = previous.get(key)
            after = current.get(key)
            if before != after:
                changes[str(key)] = {"from": before, "to": after}
        if changes:
            change_labels = ", ".join(sorted(changes.keys()))
            out.append(
                {
                    "from_run_id": str(previous.get("run_id") or ""),
                    "to_run_id": str(current.get("run_id") or ""),
                    "ts": str(current.get("ts") or ""),
                    "changes": changes,
                    "summary": f"Hold context changed in {change_labels}.",
                }
            )
        previous = current
    return out


def build_holding_phase_observability(
    lifecycle: Dict[str, Any],
    *,
    monitor_timeline: Dict[str, Any],
) -> Dict[str, Any]:
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    summary_obj = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    hold_events = [
        dict(row)
        for row in list(holding.get("holding_events") or [])
        if isinstance(row, dict)
    ]
    monitor_context_snapshots: List[Dict[str, Any]] = []
    for row in hold_events:
        monitor_context = row.get("monitor_context") if isinstance(row.get("monitor_context"), dict) else {}
        monitor_context_snapshots.append(
            {
                "run_id": str(row.get("run_id") or ""),
                "ts": str(row.get("ts") or ""),
                "posture": str(row.get("posture") or ""),
                "monitor_reason": _null_if_empty(row.get("monitor_reason") or monitor_context.get("monitor_reason")),
                "exit_reason": _null_if_empty(row.get("exit_reason") or monitor_context.get("exit_reason")),
                "active_exit_axis": _null_if_empty(monitor_context.get("active_exit_axis") or monitor_context.get("trigger_type")),
                "exit_triggered": monitor_context.get("exit_triggered") if "exit_triggered" in monitor_context else None,
                "current_drawdown": _null_if_empty(monitor_context.get("current_drawdown")),
                "peak_drawdown": _null_if_empty(monitor_context.get("peak_drawdown")),
                "price_source": _null_if_empty(monitor_context.get("price_source")),
                "summary": str(row.get("summary") or ""),
            }
        )
    hold_signal_transitions = build_hold_signal_transitions(monitor_context_snapshots)
    hold_events_count = int(len(hold_events))
    hold_duration = str(summary_obj.get("holding_duration") or "")
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    entry_ts = _to_epoch(entry.get("ts"))
    exit_ts = _to_epoch(exit_ctx.get("ts"))
    hold_duration_sec = None
    if entry_ts is not None:
        if exit_ts is not None:
            hold_duration_sec = max(0, int(exit_ts - entry_ts))
        elif monitor_context_snapshots:
            latest_hold_ts = _to_epoch(monitor_context_snapshots[-1].get("ts"))
            if latest_hold_ts is not None:
                hold_duration_sec = max(0, int(latest_hold_ts - entry_ts))

    last_hold_snapshot = monitor_context_snapshots[-1] if monitor_context_snapshots else {}
    exit_monitor_context = exit_ctx.get("monitor_context") if isinstance(exit_ctx.get("monitor_context"), dict) else {}
    deterioration_signals: List[str] = []
    if bool(exit_monitor_context.get("exit_triggered")):
        deterioration_signals.append("exit_triggered")
    active_axis = str(exit_monitor_context.get("active_exit_axis") or exit_monitor_context.get("trigger_type") or "").strip()
    if active_axis:
        deterioration_signals.append(f"active_exit_axis:{active_axis}")
    current_drawdown = _safe_float(exit_monitor_context.get("current_drawdown"), None)
    if current_drawdown is not None and current_drawdown < 0:
        deterioration_signals.append("current_drawdown_negative")
    peak_drawdown = _safe_float(exit_monitor_context.get("peak_drawdown"), None)
    if peak_drawdown is not None and peak_drawdown < 0:
        deterioration_signals.append("peak_drawdown_negative")

    pre_exit_context_summary = {
        "available": bool(exit_ctx),
        "last_hold_run_id": str(last_hold_snapshot.get("run_id") or ""),
        "last_hold_ts": str(last_hold_snapshot.get("ts") or ""),
        "last_hold_posture": _null_if_empty(last_hold_snapshot.get("posture")),
        "last_hold_monitor_reason": _null_if_empty(last_hold_snapshot.get("monitor_reason")),
        "last_hold_exit_reason": _null_if_empty(last_hold_snapshot.get("exit_reason")),
        "deterioration_signals": deterioration_signals,
        "summary": (
            f"Pre-exit context captured {hold_events_count} holding updates; last hold posture was "
            f"{str(last_hold_snapshot.get('posture') or 'not_captured')} before exit."
            if exit_ctx
            else "No exit context yet; pre-exit monitor summary is not available."
        ),
    }

    timeline_summary = monitor_timeline if isinstance(monitor_timeline, dict) else {}
    threshold_snapshot_count = len(list(timeline_summary.get("threshold_snapshots") or []))
    state_transition_count = len(list(timeline_summary.get("state_transitions") or []))
    hold_evidence_thin = hold_events_count <= 0 or not monitor_context_snapshots

    if hold_evidence_thin:
        recovered_snapshot = {}
        if exit_monitor_context:
            recovered_snapshot = dict(exit_monitor_context)
            recovered_snapshot["_recovery_source"] = "exit_monitor_context"
            recovered_snapshot["ts"] = str(exit_ctx.get("ts") or "")
            recovered_snapshot["run_id"] = str(exit_ctx.get("run_id") or "")
        elif entry.get("monitor_context"):
            recovered_snapshot = dict(entry.get("monitor_context") or {})
            recovered_snapshot["_recovery_source"] = "entry_monitor_context"
            recovered_snapshot["ts"] = str(entry.get("ts") or "")
            recovered_snapshot["run_id"] = str(entry.get("run_id") or "")

        if recovered_snapshot:
            monitor_context_snapshots.append(
                {
                    "run_id": recovered_snapshot.get("run_id", ""),
                    "ts": recovered_snapshot.get("ts", ""),
                    "posture": recovered_snapshot.get("posture", "HOLD"),
                    "monitor_reason": _null_if_empty(recovered_snapshot.get("monitor_reason")),
                    "exit_reason": _null_if_empty(recovered_snapshot.get("exit_reason")),
                    "active_exit_axis": _null_if_empty(recovered_snapshot.get("active_exit_axis") or recovered_snapshot.get("trigger_type")),
                    "exit_triggered": recovered_snapshot.get("exit_triggered"),
                    "current_drawdown": _null_if_empty(recovered_snapshot.get("current_drawdown")),
                    "peak_drawdown": _null_if_empty(recovered_snapshot.get("peak_drawdown")),
                    "price_source": _null_if_empty(recovered_snapshot.get("price_source")),
                    "summary": "Recovered from nearby execution context",
                    "_recovery_source": recovered_snapshot.get("_recovery_source"),
                }
            )
            hold_evidence_thin = False
            holding_phase_summary = "Hold evidence recovered from execution context due to short hold duration."
            hold_events_count = max(1, hold_events_count)
        else:
            holding_phase_summary = "No explicit holding monitor updates were captured, and no nearby context was available for recovery."
    else:
        holding_phase_summary = (
            f"Held across {hold_events_count} monitor updates over {hold_duration or 'uncaptured duration'}. "
            f"Signal transitions observed: {len(hold_signal_transitions)}. "
            f"Timeline snapshots: thresholds={threshold_snapshot_count}, state_transitions={state_transition_count}."
        )

    return {
        "hold_duration": hold_duration,
        "hold_duration_sec": hold_duration_sec,
        "holding_phase_summary": holding_phase_summary,
        "hold_events_count": hold_events_count,
        "monitor_context_snapshots": monitor_context_snapshots[:20],
        "hold_signal_transitions": hold_signal_transitions[:20],
        "pre_exit_context_summary": pre_exit_context_summary,
        "deterioration_signals": deterioration_signals,
        "hold_evidence_thin": hold_evidence_thin,
    }


def build_same_day_reporter_linkage(
    *,
    reporter_obj: Dict[str, Any],
    reporter_js: Path,
    reporter_md: Path,
    entry_run_id: str,
    exit_run_id: str,
    entry_bundle: Dict[str, Any],
    exit_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    reporter_obj = reporter_obj if isinstance(reporter_obj, dict) else {}
    entry_reporter = entry_bundle.get("reporter") if isinstance(entry_bundle.get("reporter"), dict) else {}
    exit_reporter = exit_bundle.get("reporter") if isinstance(exit_bundle.get("reporter"), dict) else {}
    reporter_day_file_found = bool(
        reporter_js.exists()
        or reporter_md.exists()
        or entry_reporter.get("reporter_analysis_day_file_found")
        or exit_reporter.get("reporter_analysis_day_file_found")
    )
    linked_run_ids: List[str] = []
    if bool(entry_reporter.get("reporter_analysis_found")) and entry_run_id:
        linked_run_ids.append(str(entry_run_id))
    if bool(exit_reporter.get("reporter_analysis_found")) and exit_run_id and exit_run_id not in linked_run_ids:
        linked_run_ids.append(str(exit_run_id))
    run_link_found = bool(linked_run_ids)
    if run_link_found:
        status = "linked_run"
        linkage_source = "run_specific"
        linkage_reason = "A same-day reporter analysis linked directly to this lifecycle run."
    elif reporter_day_file_found:
        status = "linked_day_fallback"
        linkage_source = "day_fallback"
        linkage_reason = "A same-day reporter analysis file was attached as fallback context for this lifecycle."
    else:
        status = "missing"
        linkage_source = "missing"
        linkage_reason = "Same-day reporter analysis is not available for this lifecycle yet."
    return {
        "schema_version": "same_day_reporter_linkage.v1",
        "status": status,
        "linkage_source": linkage_source,
        "linkage_reason": linkage_reason,
        "reporter_analysis_day_file_found": reporter_day_file_found,
        "run_link_found": run_link_found,
        "linked_run_ids": linked_run_ids,
        "reporter_analysis_json_path": str(reporter_js) if reporter_js.exists() else "",
        "reporter_analysis_md_path": str(reporter_md) if reporter_md.exists() else "",
        "reporter_analysis_expected_json_path": str(reporter_js),
        "reporter_analysis_expected_md_path": str(reporter_md),
        "reporter_analysis_json_found": bool(reporter_js.exists()),
        "reporter_analysis_md_found": bool(reporter_md.exists()),
        "reporter_analysis_summary": str(reporter_obj.get("ai_summary") or ""),
        "reporter_analysis_grade": str(reporter_obj.get("ai_run_grade") or "N/A"),
    }


def _load_story_input(trade_dir: Path) -> tuple[Dict[str, Any], str]:
    canonical = trade_dir / "ai_trade_report_input.json"
    normalized_legacy = trade_dir / "ai_trade_report" / "ai_trade_report_input.json"
    legacy = trade_dir / "trade_story_input.json"
    for path in (canonical, normalized_legacy, legacy):
        payload = _read_json(path)
        if payload:
            return payload, str(path)
    return {}, ""


def _story_input_quality_score(story_input: Dict[str, Any]) -> int:
    if not isinstance(story_input, dict) or not story_input:
        return 0

    def _execution_truth_score(details: Any) -> int:
        details_obj = details if isinstance(details, dict) else {}
        local_score = 0
        if str(details_obj.get("order_id") or "").strip():
            local_score += 1
        if details_obj.get("filled_qty") not in (None, ""):
            local_score += 1
        if details_obj.get("filled_price") not in (None, ""):
            local_score += 2
        if str(details_obj.get("broker_truth_source") or "").strip():
            local_score += 2
        if str(details_obj.get("broker_day_truth_source") or "").strip():
            local_score += 2
        if str(details_obj.get("broker_day_match_mode") or "").strip():
            local_score += 1
        if bool(details_obj.get("broker_day_authoritative")):
            local_score += 1
        if details_obj.get("broker_realized_pnl") not in (None, ""):
            local_score += 2
        if details_obj.get("broker_fee") not in (None, "") or details_obj.get("broker_tax") not in (None, ""):
            local_score += 1
        return local_score

    score = 0
    status_lower = str(story_input.get("status") or "").strip().lower()
    trade_symbol = str(story_input.get("symbol") or "").strip()
    if status_lower in {"open", "closed"}:
        score += 2
    if trade_symbol:
        score += 1
    if str(story_input.get("run_id") or "").strip():
        score += 1
    scanner_reason_human = (
        story_input.get("scanner_reason_human")
        if isinstance(story_input.get("scanner_reason_human"), dict)
        else {}
    )
    scanner_trace = (
        story_input.get("scanner_selection_trace")
        if isinstance(story_input.get("scanner_selection_trace"), dict)
        else {}
    )
    selected_symbol = str(
        story_input.get("selected_symbol")
        or scanner_reason_human.get("selected_symbol")
        or scanner_trace.get("selected_symbol")
        or ""
    ).strip()
    if selected_symbol:
        score += 2
    if status_lower == "closed" and trade_symbol and selected_symbol and trade_symbol != selected_symbol:
        score -= 2
    candidate_count = (
        story_input.get("candidate_count")
        if story_input.get("candidate_count") not in (None, "")
        else scanner_reason_human.get("candidate_count")
    )
    if isinstance(candidate_count, (int, float)) and float(candidate_count) > 0:
        score += 1
    if isinstance(scanner_trace.get("ranked_candidates"), list) and len(scanner_trace.get("ranked_candidates") or []) > 0:
        score += 1
    if isinstance(story_input.get("monitor_stop_policy_trace"), dict) and story_input.get("monitor_stop_policy_trace"):
        score += 1
    canonical_monitor = story_input.get("canonical_monitor") if isinstance(story_input.get("canonical_monitor"), dict) else {}
    if canonical_monitor:
        score += 1
    if canonical_monitor.get("current_price") not in (None, ""):
        score += 1
    if canonical_monitor.get("account_pnl_ratio") not in (None, "") or canonical_monitor.get("effective_pnl_ratio") not in (None, ""):
        score += 1
    if str(story_input.get("entry_summary") or "").strip():
        score += 1
    score += _execution_truth_score(story_input.get("execution_details"))
    score += _execution_truth_score(story_input.get("entry_execution_details"))
    score += _execution_truth_score(story_input.get("exit_execution_details"))
    return score


def resolve_story_input_for_regeneration(
    trade_dir: Path,
    trade_paths: Dict[str, Path],
) -> tuple[Dict[str, Any], str, str, int, int]:
    existing_story_input, existing_path = _load_story_input(trade_dir)
    existing_score = _story_input_quality_score(existing_story_input)
    lifecycle_bundle = _read_json(trade_paths["lifecycle_bundle_json"])
    if not lifecycle_bundle:
        return existing_story_input, existing_path, "existing_story_input", existing_score, existing_score

    enriched_lifecycle_bundle = rehydrate_lifecycle_bundle_execution_truth(lifecycle_bundle)
    if _payload_fingerprint(enriched_lifecycle_bundle) != _payload_fingerprint(lifecycle_bundle):
        write_json(trade_paths["lifecycle_bundle_json"], enriched_lifecycle_bundle)
        lifecycle_bundle = enriched_lifecycle_bundle

    rebuilt_story_input = build_trade_story_input_from_bundle(
        lifecycle_bundle,
        existing_story_input=existing_story_input,
    )
    rebuilt_score = _story_input_quality_score(rebuilt_story_input)
    if rebuilt_score >= existing_score and rebuilt_story_input:
        canonical_path = trade_paths["ai_trade_report_input_json"]
        if _payload_fingerprint(rebuilt_story_input) != _payload_fingerprint(existing_story_input):
            write_json(canonical_path, rebuilt_story_input)
        return (
            rebuilt_story_input,
            str(canonical_path),
            "rebuilt_from_lifecycle_bundle",
            existing_score,
            rebuilt_score,
        )
    return existing_story_input, existing_path, "existing_story_input", existing_score, rebuilt_score


def sync_ai_trade_report_generation_state(
    trade_paths: Dict[str, Path],
    *,
    story_input: Dict[str, Any],
    compact_input: Dict[str, Any],
    report: Dict[str, Any],
    llm_artifact: Dict[str, Any],
    llm_response_path: str,
) -> Dict[str, Any]:
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    state_path = report_generation_state_path(trade_paths)
    state_payload = load_report_generation_state(state_path)
    components = state_payload.get("components") if isinstance(state_payload.get("components"), dict) else {}
    generation_status = str(
        generation.get("status")
        or report.get("ai_trade_report_status")
        or report.get("status")
        or llm_artifact.get("status")
        or ""
    ).strip()
    model = str(
        generation.get("model")
        or llm_artifact.get("model")
        or ((llm_artifact.get("model_info") or {}) if isinstance(llm_artifact.get("model_info"), dict) else {}).get("model")
        or ""
    )
    source_inputs = {
        "story_input_sha256": _payload_fingerprint(story_input),
        "compact_input_sha256": _payload_fingerprint(compact_input),
    }
    components["ai_trade_report"] = {
        "fingerprint": _payload_fingerprint(
            {
                "component": "ai_trade_report",
                "trade_id": str(story_input.get("trade_id") or ""),
                "run_id": str(story_input.get("run_id") or ""),
                **source_inputs,
            }
        ),
        "component": "ai_trade_report",
        "status": generation_status,
        "report_status": "available" if trade_paths["ai_trade_report_json"].exists() else "missing",
        "skip_reason": "",
        "trade_id": str(story_input.get("trade_id") or ""),
        "run_id": str(story_input.get("run_id") or ""),
        "updated_at": _utc_now_iso(),
        "model": model,
        "report_json_path": str(trade_paths["ai_trade_report_json"]),
        "report_md_path": str(trade_paths["ai_trade_report_md"]),
        "llm_response_path": str(llm_response_path or ""),
        "source_inputs": source_inputs,
    }
    state_payload["components"] = components
    write_report_generation_state(state_path, state_payload)
    return state_payload


def build_live_bundle_backfill_payload(
    *,
    trade_id: str,
    status: str,
    story_type: str,
    execution_mode_label: str,
    symbol: str,
    entry_run_id: str,
    hold_run_ids: List[str],
    exit_run_id: str,
    linked_run_ids: List[str],
    lifecycle_summary: str,
    lifecycle_bundle_path: Path,
    story_input_path: Path,
    story_compact_input_path: Path,
    trade_report_json_written: str,
    trade_report_md_written: str,
    strategist_llm_response_path: Path,
    ai_trade_report_llm_response_written: str,
    entry_artifact_path: Path,
    hold_artifact_path: Path,
    exit_artifact_path: Path,
    strategist_evidence_path: Path,
    scanner_evidence_path: Path,
    monitor_evidence_path: Path,
    commander_evidence_path: Path,
    trade_provenance_path: Path,
    trade_health_path: Path,
    trade_artifact_links_path: Path,
    trade_root: Path,
    trade_report_summary: str,
    diagnostics: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    diagnostics_obj = dict(diagnostics or {})
    common_row_patch = {
        "trade_id": trade_id,
        "story_id": trade_id,
        "lifecycle_bundle_json_path": str(lifecycle_bundle_path),
        "trade_lifecycle_json_path": "",
        "trade_story_input_path": str(story_input_path),
        "ai_trade_report_input_path": str(story_input_path),
        "ai_trade_report_compact_input_path": str(story_compact_input_path),
        "trade_report_json_path": str(trade_report_json_written or ""),
        "trade_report_md_path": str(trade_report_md_written or ""),
        "ai_trade_report_json_path": str(trade_report_json_written or ""),
        "ai_trade_report_md_path": str(trade_report_md_written or ""),
        "strategist_llm_response_path": str(strategist_llm_response_path),
        "ai_trade_report_llm_response_path": str(ai_trade_report_llm_response_written or ""),
        "entry_json_path": str(entry_artifact_path),
        "hold_json_path": str(hold_artifact_path),
        "exit_json_path": str(exit_artifact_path),
        "strategist_evidence_json_path": str(strategist_evidence_path),
        "scanner_evidence_json_path": str(scanner_evidence_path),
        "monitor_evidence_json_path": str(monitor_evidence_path),
        "monitor_timeline_json_path": str(monitor_evidence_path),
        "commander_evidence_json_path": str(commander_evidence_path),
        "trade_provenance_json_path": str(trade_provenance_path),
        "trade_health_json_path": str(trade_health_path),
        "trade_artifact_links_json_path": str(trade_artifact_links_path),
        "trade_root_path": str(trade_root),
        "trade_report_summary": str(trade_report_summary or ""),
        "report_status": str(diagnostics_obj.get("report_status") or ""),
        "report_reason_code": str(diagnostics_obj.get("report_reason_code") or ""),
        "report_reason_human": str(diagnostics_obj.get("report_reason_human") or ""),
        "report_next_expected_step": str(diagnostics_obj.get("next_expected_step") or ""),
        "report_generation_model": str(diagnostics_obj.get("llm_model_used") or ""),
        "report_generation_attempted": bool(diagnostics_obj.get("generation_attempted")),
        "deterministic_report_status": str(diagnostics_obj.get("deterministic_report_status") or ""),
        "llm_brief_status": str(diagnostics_obj.get("llm_brief_status") or ""),
        "ai_trade_report_status": str(diagnostics_obj.get("ai_trade_report_status") or ""),
    }
    lifecycle_row = {
        "trade_id": trade_id,
        "story_id": trade_id,
        "status": status,
        "story_type": story_type,
        "execution_mode_label": execution_mode_label,
        "symbol": symbol,
        "entry_run_id": entry_run_id,
        "hold_run_ids": list(hold_run_ids or []),
        "exit_run_id": exit_run_id,
        "linked_run_ids": list(linked_run_ids or []),
        "lifecycle_summary": str(lifecycle_summary or ""),
        "report_json_path": str(lifecycle_bundle_path),
        **common_row_patch,
    }
    bundle_artifacts_patch = {
        "lifecycle_bundle_json": str(lifecycle_bundle_path),
        "entry_json": str(entry_artifact_path),
        "hold_json": str(hold_artifact_path),
        "exit_json": str(exit_artifact_path),
        "trade_story_input_json": str(story_input_path),
        "ai_trade_report_input_json": str(story_input_path),
        "ai_trade_report_compact_input_json": str(story_compact_input_path),
        "trade_report_json": str(trade_report_json_written or ""),
        "trade_report_md": str(trade_report_md_written or ""),
        "ai_trade_report_json": str(trade_report_json_written or ""),
        "ai_trade_report_md": str(trade_report_md_written or ""),
        "strategist_llm_response_json": str(strategist_llm_response_path),
        "ai_trade_report_llm_response_json": str(ai_trade_report_llm_response_written or ""),
        "strategist_evidence_json": str(strategist_evidence_path),
        "scanner_evidence_json": str(scanner_evidence_path),
        "monitor_evidence_json": str(monitor_evidence_path),
        "monitor_timeline_json": str(monitor_evidence_path),
        "commander_evidence_json": str(commander_evidence_path),
    }
    return {
        "lifecycle_row": lifecycle_row,
        "run_bundle_row_patch": common_row_patch,
        "bundle_artifacts_patch": bundle_artifacts_patch,
    }


def persist_live_story_input_artifacts(
    *,
    day: str,
    trade_id: str,
    anchor_run_id: str,
    status: str,
    should_attempt_generation: bool,
    trade_story_input: Mapping[str, Any] | None,
    trade_story_compact_input: Mapping[str, Any] | None,
    existing_trade_report_artifact: Mapping[str, Any] | None,
    existing_story_input_artifact: Mapping[str, Any] | None,
    story_input_path: Path,
    story_compact_input_path: Path,
    diagnostics: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    diagnostics_out = dict(diagnostics or {})
    story_input_to_persist = dict(trade_story_input or {})
    existing_report_obj = dict(existing_trade_report_artifact or {})
    existing_story_obj = dict(existing_story_input_artifact or {})
    preserved_closed_story_input = False

    current_status_lower = str(status or "").strip().lower()
    existing_report_status_lower = str(existing_report_obj.get("status") or "").strip().lower()
    existing_story_status_lower = str(existing_story_obj.get("status") or "").strip().lower()

    if (
        current_status_lower == "open"
        and not should_attempt_generation
        and existing_report_status_lower == "closed"
    ):
        if existing_story_status_lower == "closed":
            story_input_to_persist = dict(existing_story_obj)
            preserved_closed_story_input = True
            diagnostics_out["story_input_persist_strategy"] = "preserve_existing_closed_snapshot"
        else:
            repaired_story_input = dict(trade_story_input or {})
            repaired_story_input["status"] = "closed"
            report_action = str(existing_report_obj.get("action") or "").strip().upper()
            report_run_id = str(existing_report_obj.get("run_id") or "").strip()
            if report_action in {"BUY", "SELL", "EXIT", "WAIT", "HOLD"}:
                repaired_story_input["action"] = report_action
            if report_run_id:
                repaired_story_input["run_id"] = report_run_id
            repaired_shared_facts = (
                repaired_story_input.get("shared_facts")
                if isinstance(repaired_story_input.get("shared_facts"), dict)
                else {}
            )
            repaired_shared_facts["status"] = "closed"
            if report_action in {"BUY", "SELL", "EXIT", "WAIT", "HOLD"}:
                repaired_shared_facts["action"] = report_action
                resolved_trade_facts = (
                    repaired_shared_facts.get("resolved_trade_facts")
                    if isinstance(repaired_shared_facts.get("resolved_trade_facts"), dict)
                    else {}
                )
                resolved_trade_facts["status"] = "closed"
                resolved_trade_facts["action"] = report_action
                repaired_shared_facts["resolved_trade_facts"] = resolved_trade_facts
            repaired_story_input["shared_facts"] = repaired_shared_facts
            story_input_to_persist = repaired_story_input
            diagnostics_out["story_input_persist_strategy"] = "repair_closed_snapshot_from_existing_report"
    else:
        diagnostics_out["story_input_persist_strategy"] = "persist_current_runtime_snapshot"

    trade_story_compact_input_to_persist = (
        build_ai_trade_report_compact_input(story_input_to_persist)
        if preserved_closed_story_input
        else dict(trade_story_compact_input or {})
    )

    write_json(story_input_path, story_input_to_persist)
    trade_story_compact_artifact = build_compact_input_artifact(
        component="ai_trade_report",
        run_id=str(anchor_run_id or ""),
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        source_artifact_path=str(story_input_path),
        source_input=story_input_to_persist,
        compact_input=trade_story_compact_input_to_persist,
    )
    write_json(story_compact_input_path, trade_story_compact_artifact)
    return {
        "story_input_to_persist": story_input_to_persist,
        "trade_story_compact_artifact": trade_story_compact_artifact,
        "trade_story_compact_input_to_persist": trade_story_compact_input_to_persist,
        "preserved_closed_story_input": preserved_closed_story_input,
        "diagnostics": diagnostics_out,
    }


def apply_live_bundle_backfill(
    *,
    linked_run_ids: Iterable[str],
    run_bundle_lookup: Mapping[str, Any] | None,
    run_bundles_by_run: Mapping[str, Any] | None,
    backfill_payload: Mapping[str, Any] | None,
    trade_id: str,
    diagnostics: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    row_patch = dict((backfill_payload or {}).get("run_bundle_row_patch") or {})
    bundle_patch = dict((backfill_payload or {}).get("bundle_artifacts_patch") or {})
    diagnostics_obj = dict(diagnostics or {})
    updated_run_ids: List[str] = []
    rewritten_json_paths: List[str] = []
    rewritten_md_paths: List[str] = []

    for rid in [str(x or "").strip() for x in list(linked_run_ids or []) if str(x or "").strip()]:
        row = (run_bundle_lookup or {}).get(rid)
        if isinstance(row, dict):
            row.update(dict(row_patch))
        bundle = (run_bundles_by_run or {}).get(rid)
        if not isinstance(bundle, dict):
            continue
        bundle["trade_id"] = trade_id
        bundle["story_id"] = trade_id
        bundle["ai_report_diagnostics"] = dict(diagnostics_obj)
        bundle.setdefault("artifacts", {})
        bundle["artifacts"].update(dict(bundle_patch))
        report_json_path = Path(str(bundle.get("report_json_path") or ""))
        if report_json_path.exists():
            report_json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            rewritten_json_paths.append(str(report_json_path))
        report_md_path = Path(str(bundle.get("report_md_path") or ""))
        if report_md_path.exists():
            report_md_path.write_text(render_bundle_markdown(bundle), encoding="utf-8")
            rewritten_md_paths.append(str(report_md_path))
        updated_run_ids.append(rid)

    return {
        "updated_run_ids": updated_run_ids,
        "rewritten_json_paths": rewritten_json_paths,
        "rewritten_md_paths": rewritten_md_paths,
    }


def build_live_execution_summary_payload(
    *,
    day: str,
    role: str,
    event_log_path: Path,
    evidence_log_path: Path,
    lifecycle_rows: List[Dict[str, Any]],
    run_bundle_rows: List[Dict[str, Any]],
    lifecycle_story_type_counts: Mapping[str, Any] | None,
    run_story_type_counts: Mapping[str, Any] | None,
    target_ctx: Mapping[str, Any] | None,
    canonical_trades_root: Path,
    trade_js: Path,
    trade_md: Path,
    reporter_js: Path,
    reporter_md: Path,
    operator_summary_json: Path,
    operator_summary_md: Path,
) -> Dict[str, Any]:
    report_status_counts: Dict[str, int] = {}
    for row in list(lifecycle_rows or []):
        key = str((row or {}).get("report_status") or "").strip().lower() or "unknown"
        report_status_counts[key] = int(report_status_counts.get(key, 0) + 1)

    target_ctx = dict(target_ctx or {})
    return {
        "schema_version": "live_execution_bundles.v3",
        "ok": True,
        "ts": _utc_now_iso(),
        "day": str(day or ""),
        "role": str(role or ""),
        "event_log_path": str(event_log_path),
        "evidence_log_path": str(evidence_log_path),
        "bundle_count": len(list(lifecycle_rows or [])),
        "trade_lifecycle_count": len(list(lifecycle_rows or [])),
        "run_bundle_count": len(list(run_bundle_rows or [])),
        "story_type_counts": dict(lifecycle_story_type_counts or {}),
        "report_status_counts": report_status_counts,
        "run_story_type_counts": dict(run_story_type_counts or {}),
        "targeted_mode": bool(target_ctx.get("targeted_mode")),
        "target_run_id": str(target_ctx.get("target_run_id") or ""),
        "target_symbol": str(target_ctx.get("target_symbol") or ""),
        "targeted_execution_run_count": int(target_ctx.get("execution_run_count") or 0),
        "targeted_lifecycle_context_run_count": int(target_ctx.get("lifecycle_context_run_count") or 0),
        "canonical_trades_root": str(canonical_trades_root),
        "bundles": list(lifecycle_rows or []),
        "run_bundles": list(run_bundle_rows or []),
        "day_artifacts": {
            "trade_explain_json": str(trade_js),
            "trade_explain_md": str(trade_md),
            "reporter_analysis_json": str(reporter_js) if reporter_js.exists() else "",
            "reporter_analysis_md": str(reporter_md) if reporter_md.exists() else "",
            "operator_summary_json": str(operator_summary_json) if operator_summary_json.exists() else "",
            "operator_summary_md": str(operator_summary_md) if operator_summary_md.exists() else "",
        },
    }


def _report_diagnostics_from_report(report: Dict[str, Any], llm_artifact: Dict[str, Any]) -> Dict[str, Any]:
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    generation_status = str(generation.get("status") or llm_artifact.get("status") or "").strip().lower()
    model = str(generation.get("model") or llm_artifact.get("model") or ((llm_artifact.get("model_info") or {}).get("model")) or "")
    diagnostics = {
        "report_status": "failed",
        "report_reason_code": "llm_generation_failed",
        "report_reason_human": "AI trade report generation failed.",
        "generation_attempted": True,
        "generation_ts": _utc_now_iso(),
        "story_input_available": True,
        "report_output_available": True,
        "report_artifact_available": True,
        "llm_model_used": model,
        "last_error_message": str(llm_artifact.get("error") or ""),
        "next_expected_step": "Inspect the LLM response artifact and retry generation.",
    }
    if generation_status in {"ok", "repaired"}:
        diagnostics.update(
            {
                "report_status": "available",
                "report_reason_code": "",
                "report_reason_human": "AI trade report was generated successfully.",
                "next_expected_step": "Open the full report for detailed lifecycle analysis.",
                "last_error_message": "",
            }
        )
    elif generation_status in {"partial", "salvaged"}:
        diagnostics.update(
            {
                "report_status": "available",
                "report_reason_code": "llm_generation_salvaged",
                "report_reason_human": "AI trade report was generated with partial recovery.",
                "next_expected_step": "Open the report and review completeness metadata before relying on every section.",
            }
        )
    return diagnostics


def sync_ai_report_diagnostics(
    trade_paths: Dict[str, Path],
    report: Dict[str, Any],
    llm_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    diagnostics = _report_diagnostics_from_report(report, llm_artifact)
    report["ai_report_diagnostics"] = dict(diagnostics)

    for path in (
        trade_paths["lifecycle_bundle_json"],
        trade_paths["ai_trade_report_input_json"],
        trade_paths["trade_health_json"],
    ):
        payload = _read_json(path)
        if not payload:
            continue
        payload["ai_report_diagnostics"] = dict(diagnostics)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return diagnostics


def finalize_ai_report_diagnostics(
    trade_paths: Dict[str, Path],
    report_json_path: Path,
    diagnostics: Dict[str, Any],
) -> None:
    for path in (
        report_json_path,
        trade_paths["lifecycle_bundle_json"],
        trade_paths["ai_trade_report_input_json"],
        trade_paths["trade_health_json"],
    ):
        payload = _read_json(path)
        if not payload:
            continue
        payload["ai_report_diagnostics"] = dict(diagnostics)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_bundle_queue(path: Path) -> List[Dict[str, Any]]:
    try:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        return [dict(row) for row in payload if isinstance(row, dict)]
    except Exception:
        return []


def _write_bundle_queue(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _enqueue_bundle_request(
    root: Path,
    *,
    run_id: str,
    symbol: str,
    reason: str,
) -> Dict[str, Any]:
    queue_path = _bundle_job_queue_path(root)
    rows = _load_bundle_queue(queue_path)
    normalized_run_id = str(run_id or "").strip()
    normalized_symbol = _normalize_symbol(symbol)
    for row in rows:
        if (
            str(row.get("target_run_id") or "").strip() == normalized_run_id
            and _normalize_symbol(row.get("target_symbol")) == normalized_symbol
        ):
            row["last_seen_at"] = _utc_iso()
            row["reason"] = str(reason or row.get("reason") or "")
            _write_bundle_queue(queue_path, rows)
            out = dict(row)
            out["queue_path"] = str(queue_path)
            out["queue_length"] = len(rows)
            out["deduped"] = True
            return out
    entry = {
        "target_run_id": normalized_run_id,
        "target_symbol": normalized_symbol,
        "role": _bundle_role(),
        "reason": str(reason or ""),
        "enqueued_at": _utc_iso(),
        "last_seen_at": _utc_iso(),
    }
    rows.append(entry)
    _write_bundle_queue(queue_path, rows)
    out = dict(entry)
    out["queue_path"] = str(queue_path)
    out["queue_length"] = len(rows)
    out["deduped"] = False
    return out


def _pid_active(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _active_bundle_job(path: Path, *, stale_after_sec: float = 900.0) -> Dict[str, Any]:
    payload = _read_lock_payload(path)
    if not payload:
        return {}
    pid = int(payload.get("pid") or 0)
    touched_at = float(
        payload.get("touched_at_epoch")
        or payload.get("heartbeat_epoch")
        or payload.get("started_at_epoch")
        or 0.0
    )
    age_sec = max(0.0, float(time.time()) - touched_at) if touched_at > 0 else stale_after_sec + 1.0
    active = _pid_active(pid)
    if active and age_sec <= stale_after_sec:
        out = dict(payload)
        out["lock_path"] = str(path)
        out["age_sec"] = age_sec
        return out
    if age_sec > stale_after_sec or not active:
        with contextlib.suppress(Exception):
            path.unlink()
    return {}


def _active_bundle_process(root: Path) -> Dict[str, Any]:
    script_path = str(_script_path(root)).lower()
    runner_module = _runner_module_name().lower()
    current_pid = int(os.getpid())
    try:
        if os.name == "nt":
            probe = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*run_live_execution_bundle_report.py*' -or $_.CommandLine -like '*libs.reporting.live_execution_bundle_runner*') } | "
                "Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Compress"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", probe],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
                check=False,
            )
            raw = str(completed.stdout or "").strip()
            if not raw:
                return {}
            payload = json.loads(raw)
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                pid = int(row.get("ProcessId") or 0)
                cmd = str(row.get("CommandLine") or "").lower()
                if pid <= 0 or pid == current_pid:
                    continue
                if (
                    script_path not in cmd
                    and "run_live_execution_bundle_report.py" not in cmd
                    and runner_module not in cmd
                ):
                    continue
                creation_epoch = _creation_epoch_from_wmi(row.get("CreationDate"))
                return {
                    "pid": pid,
                    "parent_pid": int(row.get("ParentProcessId") or 0),
                    "script": "run_live_execution_bundle_report.py",
                    "entrypoint_module": _runner_module_name() if runner_module in cmd else "",
                    "command_line": str(row.get("CommandLine") or ""),
                    "detection_source": "process_scan",
                    "creation_epoch": creation_epoch,
                    "age_sec": max(0.0, float(time.time()) - creation_epoch) if creation_epoch > 0 else None,
                }
        else:
            completed = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
                check=False,
            )
            for raw in str(completed.stdout or "").splitlines():
                line = str(raw or "").strip()
                if not line:
                    continue
                try:
                    pid_text, cmd = line.split(None, 1)
                except ValueError:
                    continue
                pid = int(pid_text or 0)
                cmd_lower = str(cmd or "").lower()
                if pid <= 0 or pid == current_pid:
                    continue
                if (
                    script_path not in cmd_lower
                    and "run_live_execution_bundle_report.py" not in cmd_lower
                    and runner_module not in cmd_lower
                ):
                    continue
                return {
                    "pid": pid,
                    "parent_pid": int(parent_pid or 0),
                    "script": "run_live_execution_bundle_report.py",
                    "entrypoint_module": _runner_module_name() if runner_module in cmd_lower else "",
                    "command_line": str(cmd or ""),
                    "detection_source": "process_scan",
                }
    except Exception:
        return {}
    return {}


def _creation_epoch_from_wmi(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    match = re.search(r"/Date\((\d+)", raw)
    if match:
        try:
            return float(match.group(1)) / 1000.0
        except Exception:
            return 0.0
    return 0.0


def _stale_process_after_sec() -> float:
    try:
        return max(30.0, float(os.getenv("INTRADAY_TRADE_REPORT_STALE_PROCESS_SEC", "180") or 180.0))
    except Exception:
        return 180.0


def _terminate_process_tree(pid: int) -> bool:
    pid = int(pid or 0)
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
                check=False,
            )
            return int(completed.returncode or 1) == 0
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def _write_bundle_job_lock(
    path: Path,
    *,
    pid: int,
    argv: List[str],
    target_run_id: str = "",
    target_symbol: str = "",
) -> None:
    now_epoch = float(time.time())
    payload = {
        "pid": int(pid or 0),
        "parent_pid": int(os.getpid()),
        "role": _bundle_role(),
        "status": "running",
        "created_at": _utc_iso(),
        "created_at_epoch": now_epoch,
        "started_at": _utc_iso(),
        "started_at_epoch": now_epoch,
        "touched_at": _utc_iso(),
        "touched_at_epoch": now_epoch,
        "script": "run_live_execution_bundle_report.py",
        "entrypoint_module": _runner_module_name(),
        "argv": list(argv or []),
        "target_run_id": str(target_run_id or ""),
        "target_symbol": _normalize_symbol(target_symbol),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _execution_action(state: Dict[str, Any]) -> str:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    return str(order.get("action") or execution.get("action") or "").strip().upper()


def _execution_ok(state: Dict[str, Any]) -> bool:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    return bool(execution.get("ok")) and bool(execution.get("allowed", True))


def _cache_run_ids(summary: Dict[str, Any], current_run_id: str) -> List[str]:
    run_bundles = summary.get("run_bundles") if isinstance(summary.get("run_bundles"), list) else []
    matched_trade_ids = {
        str(row.get("trade_id") or "").strip()
        for row in run_bundles
        if str(row.get("run_id") or "").strip() == current_run_id and str(row.get("trade_id") or "").strip()
    }
    run_ids = {current_run_id}
    for row in run_bundles:
        if not isinstance(row, dict):
            continue
        trade_id = str(row.get("trade_id") or "").strip()
        run_id = str(row.get("run_id") or "").strip()
        if trade_id and trade_id in matched_trade_ids and run_id:
            run_ids.add(run_id)
    return sorted(x for x in run_ids if x)


def _invalidate_brief_cache(root: Path, run_ids: Iterable[str]) -> List[str]:
    cache_dir = _brief_cache_dir(root)
    removed: List[str] = []
    for run_id in run_ids:
        path = cache_dir / f"{run_id}.json"
        if not path.exists():
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except Exception:
            continue
    return removed


def _build_bundle_argv(root: Path, state: Dict[str, Any] | None = None) -> List[str]:
    runtime_state = state if isinstance(state, dict) else {}
    execution = runtime_state.get("execution") if isinstance(runtime_state.get("execution"), dict) else {}
    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    run_id = str(runtime_state.get("run_id") or "").strip()
    symbol = _normalize_symbol(order.get("symbol") or execution.get("symbol") or runtime_state.get("symbol") or "")
    argv = [
        "--env-path",
        str(Path(os.getenv("ENV_PATH", str(root / ".env")))),
        "--event-log-path",
        str(Path(os.getenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl")))),
        "--evidence-log-path",
        str(Path(os.getenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl")))),
        "--report-dir",
        str(root / "reports" / "dev" / "analysis" / "live_execution_bundles"),
        "--reports-root",
        str(root / "reports"),
        "--intents-path",
        str(Path(os.getenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl")))),
        "--role",
        _bundle_role(),
        "--trade-report-ai",
        "--json",
    ]
    if run_id:
        argv.extend(["--target-run-id", run_id])
    if symbol:
        argv.extend(["--target-symbol", symbol])
    return argv


def _make_bundle_event_logger(root: Path):
    try:
        from libs.core.event_logger import EventLogger, resolve_event_log_path
    except Exception:
        return None
    try:
        return EventLogger(log_path=resolve_event_log_path(str(root / "data" / "logs" / "events.jsonl")))
    except Exception:
        return None


def _log_bundle_event(
    root: Path,
    *,
    event: str,
    reason: str = "",
    run_id: str = "",
    trade_id: str = "",
    symbol: str = "",
    payload: Dict[str, Any] | None = None,
) -> None:
    logger = _make_bundle_event_logger(root)
    if logger is None:
        return
    safe_payload = dict(payload or {})
    safe_payload.setdefault("role", _bundle_role())
    if reason:
        safe_payload.setdefault("reason", str(reason))
    safe_payload.setdefault("pid", int(os.getpid()))
    safe_payload.setdefault("parent_pid", int(os.getpid()))
    with contextlib.suppress(Exception):
        logger.log(
            run_id=str(run_id or "runtime-report-bundle"),
            stage="reporting",
            event=event,
            event_name=f"reporting.{event}",
            level="info",
            trade_id=str(trade_id or ""),
            agent="reporting",
            phase="runtime",
            symbol=_normalize_symbol(symbol),
            payload=safe_payload,
        )


def _run_bundle_sync(argv: List[str]) -> tuple[int, str]:
    from libs.reporting.live_execution_bundle_runner import run_live_execution_bundle_inprocess

    return run_live_execution_bundle_inprocess(argv)


def _background_creationflags() -> int:
    flags = 0
    for name in ("CREATE_NO_WINDOW", "DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= int(getattr(subprocess, name, 0) or 0)
    return flags


def _run_bundle_with_timeout(
    root: Path,
    argv: List[str],
    *,
    timeout_sec: float,
    target_run_id: str = "",
    target_symbol: str = "",
) -> tuple[int | None, str, int | None]:
    cmd = [sys.executable, "-m", _runner_module_name(), *argv]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(0.5, float(timeout_sec)),
            check=False,
        )
        return int(completed.returncode), str(completed.stdout or "").strip(), None
    except subprocess.TimeoutExpired:
        lock_path = _bundle_job_lock_path(root)
        env = dict(os.environ)
        env["INTRADAY_TRADE_REPORT_JOB_LOCK_PATH"] = str(lock_path)
        env["INTRADAY_TRADE_REPORT_PARENT_SPAWN"] = "1"
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=_background_creationflags(),
        )
        _write_bundle_job_lock(
            lock_path,
            pid=int(getattr(proc, "pid", 0) or 0),
            argv=cmd,
            target_run_id=target_run_id,
            target_symbol=target_symbol,
        )
        return None, "", int(getattr(proc, "pid", 0) or 0)


def _build_generation_result(*, root: Path, summary: Dict[str, Any], run_id: str, return_code: int) -> Dict[str, Any]:
    cache_run_ids = _cache_run_ids(summary, run_id)
    removed_cache = _invalidate_brief_cache(root, cache_run_ids)
    run_bundles = summary.get("run_bundles") if isinstance(summary.get("run_bundles"), list) else []
    matched = next(
        (row for row in run_bundles if isinstance(row, dict) and str(row.get("run_id") or "").strip() == run_id),
        {},
    )
    brief_artifacts: Dict[str, str] = {}
    trade_id = str((matched or {}).get("trade_id") or "").strip()
    trade_day = _trade_day_from_trade_id(trade_id)
    if trade_id and trade_day:
        trade_paths = trade_artifact_paths(root / "reports", trade_day, trade_id)
        brief_json_path = Path(trade_paths.get("brief_json") or Path())
        brief_md_path = Path(trade_paths.get("brief_md") or Path())
        brief_artifacts = {
            "operator_brief_json_path": str(brief_json_path),
            "operator_brief_md_path": str(brief_md_path),
        }

    return {
        "ok": True,
        "status": "generated",
        "reason": "",
        "return_code": int(return_code),
        "summary": summary,
        "trade_id": trade_id,
        "story_id": str((matched or {}).get("story_id") or ""),
        "report_status": str((matched or {}).get("report_status") or ""),
        "report_path": str((matched or {}).get("trade_report_json_path") or ""),
        "symbol": _normalize_symbol((matched or {}).get("symbol") or ""),
        "cache_invalidated": removed_cache,
        **brief_artifacts,
    }


def generate_intraday_trade_artifacts(state: Dict[str, Any], *, root: Path | None = None) -> Dict[str, Any]:
    if not _is_trueish(os.getenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")):
        return {"ok": False, "status": "disabled", "reason": "intraday_trade_reports_disabled"}

    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    reporter = applied_policy.get("reporter") if isinstance(applied_policy.get("reporter"), dict) else {}
    trade_report = reporter.get("trade_report") if isinstance(reporter.get("trade_report"), dict) else {}
    if trade_report and trade_report.get("enabled") is False:
        return {
            "ok": False,
            "status": "disabled",
            "reason": "reporter.trade_report.enabled is false",
            "policy_source": str(trade_report.get("policy_source") or "commander_applied_policy"),
        }

    if not _execution_ok(state):
        return {"ok": False, "status": "skipped", "reason": "execution_not_successful"}

    action = _execution_action(state)
    if action not in {"BUY", "SELL"}:
        return {"ok": False, "status": "skipped", "reason": "non_trade_action"}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    repo_root = Path(root) if root is not None else _root_dir()
    run_id = str(state.get("run_id") or "").strip()
    argv = _build_bundle_argv(repo_root, state)
    force_sync = root is not None or _is_trueish(state.get("force_sync_intraday_trade_reports"))

    generate_on_open = bool(trade_report.get("generate_on_open", False))
    if action == "BUY" and not generate_on_open and not force_sync:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "trade_report_generate_on_open_disabled",
            "report_status": "pending",
            "symbol": _normalize_symbol(
                ((execution.get("order") or {}) if isinstance(execution.get("order"), dict) else {}).get("symbol")
                or execution.get("symbol")
                or state.get("symbol")
                or ""
            ),
            "target_run_id": str(state.get("run_id") or "").strip(),
            "target_symbol": _normalize_symbol(
                ((execution.get("order") or {}) if isinstance(execution.get("order"), dict) else {}).get("symbol")
                or execution.get("symbol")
                or state.get("symbol")
                or ""
            ),
            "role": _bundle_role(),
            "policy_source": str(trade_report.get("policy_source") or "commander_applied_policy"),
        }

    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    symbol = _normalize_symbol(order.get("symbol") or execution.get("symbol") or state.get("symbol") or "")
    _log_bundle_event(
        repo_root,
        event="report_bundle_spawn_requested",
        run_id=run_id,
        symbol=symbol,
        payload={
            "lock_path": str(_bundle_job_lock_path(repo_root)),
            "target_run_id": run_id,
            "target_symbol": symbol,
            "force_sync": bool(force_sync),
        },
    )
    if not force_sync:
        active_job = _active_bundle_job(_bundle_job_lock_path(repo_root))
        if not active_job:
            active_job = _active_bundle_process(repo_root)
            active_pid = int(active_job.get("pid") or 0) if isinstance(active_job, dict) else 0
            active_age_sec = float(active_job.get("age_sec") or 0.0) if isinstance(active_job, dict) else 0.0
            if active_pid > 0 and active_age_sec >= _stale_process_after_sec():
                terminated = _terminate_process_tree(active_pid)
                _log_bundle_event(
                    repo_root,
                    event="report_bundle_stale_process_terminated",
                    reason="orphan_bundle_process_exceeded_stale_window",
                    run_id=run_id,
                    symbol=symbol,
                    payload={
                        "lock_path": str(_bundle_job_lock_path(repo_root)),
                        "active_pid": active_pid,
                        "active_age_sec": active_age_sec,
                        "terminated": bool(terminated),
                        "target_run_id": run_id,
                        "target_symbol": symbol,
                    },
                )
                if terminated:
                    time.sleep(0.2)
                    active_job = {}
        if active_job:
            _log_bundle_event(
                repo_root,
                event="report_bundle_spawn_skipped_existing_process",
                reason="bundle_busy_no_queue",
                run_id=run_id,
                symbol=symbol,
                payload={
                    "target_run_id": run_id,
                    "target_symbol": symbol,
                    "lock_path": str(active_job.get("lock_path") or _bundle_job_lock_path(repo_root)),
                    "active_pid": int(active_job.get("pid") or 0),
                    "dedupe_source": str(active_job.get("detection_source") or "lock"),
                },
            )
            return {
                "ok": True,
                "status": "skipped",
                "reason": "bundle_busy_no_queue",
                "return_code": None,
                "summary": {},
                "trade_id": "",
                "story_id": "",
                "report_status": "skipped",
                "report_path": "",
                "symbol": symbol,
                "cache_invalidated": [],
                "background_pid": int(active_job.get("pid") or 0),
                "lock_path": str(active_job.get("lock_path") or ""),
                "dedupe_source": str(active_job.get("detection_source") or "lock"),
                "target_run_id": run_id,
                "target_symbol": symbol,
                "role": _bundle_role(),
            }
    if force_sync:
        rc, raw = _run_bundle_sync(argv)
        queued_pid = None
    else:
        rc, raw, queued_pid = _run_bundle_with_timeout(
            repo_root,
            argv,
            timeout_sec=float(os.getenv("INTRADAY_TRADE_REPORT_SYNC_TIMEOUT_SEC", "2.0") or 2.0),
            target_run_id=run_id,
            target_symbol=symbol,
        )

    if queued_pid:
        _log_bundle_event(
            repo_root,
            event="report_bundle_spawned_background",
            run_id=run_id,
            symbol=symbol,
            payload={
                "lock_path": str(_bundle_job_lock_path(repo_root)),
                "background_pid": int(queued_pid),
                "target_run_id": run_id,
                "target_symbol": symbol,
            },
        )
        return {
            "ok": True,
            "status": "queued",
            "reason": "",
            "return_code": None,
            "summary": {},
            "trade_id": "",
            "story_id": "",
            "report_status": "queued",
            "report_path": "",
            "symbol": symbol,
            "cache_invalidated": [],
            "queue_mode": "background_subprocess",
            "background_pid": int(queued_pid),
            "lock_path": str(_bundle_job_lock_path(repo_root)),
            "target_run_id": run_id,
            "target_symbol": symbol,
            "role": _bundle_role(),
        }

    try:
        summary = json.loads(raw) if raw else {}
    except Exception:
        summary = {}

    if rc != 0 or not isinstance(summary, dict):
        return {
            "ok": False,
            "status": "failed",
            "reason": "intraday_bundle_generation_failed",
            "return_code": int(rc),
            "stdout": raw[-1000:],
        }

    result = _build_generation_result(root=repo_root, summary=summary, run_id=run_id, return_code=int(rc))
    result["target_run_id"] = run_id
    result["target_symbol"] = symbol
    result["role"] = _bundle_role()
    return result
