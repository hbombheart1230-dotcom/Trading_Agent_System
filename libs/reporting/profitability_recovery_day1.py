from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from libs.reporting.llm_artifacts import iter_trade_dirs as _iter_trade_dirs


REQUIRED_EXECUTION_FIELDS = (
    "order_status",
    "order_id",
    "execution_mode",
    "broker_env",
    "filled_qty",
    "avg_price",
)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def iter_trade_dirs(reports_root: Path, day: str) -> List[Path]:
    day_root = Path(reports_root) / "trades" / str(day)
    if not day_root.exists():
        return []
    return sorted(_iter_trade_dirs(day_root))


def _artifact_path(trade_dir: Path, *candidates: str) -> Path:
    for raw in candidates:
        candidate = trade_dir / raw
        if candidate.exists():
            return candidate
    return trade_dir / candidates[0]


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _is_closed_trade(lifecycle_bundle: Dict[str, Any]) -> bool:
    status = str(
        lifecycle_bundle.get("trade_lifecycle_status")
        or lifecycle_bundle.get("status")
        or ""
    ).strip().lower()
    if status == "closed":
        return True
    exit_obj = lifecycle_bundle.get("exit") if isinstance(lifecycle_bundle.get("exit"), dict) else {}
    exit_action = str(exit_obj.get("action") or "").strip().upper()
    return exit_action == "SELL"


def _linkage_surface_present(linkage: Dict[str, Any]) -> bool:
    if not linkage:
        return False
    status = str(linkage.get("status") or "").strip().lower()
    reason = str(linkage.get("linkage_reason") or "").strip()
    return bool(status) and (status != "missing" or bool(reason))


def _execution_missing_fields(execution_details: Dict[str, Any]) -> List[str]:
    execution_details = execution_details if isinstance(execution_details, dict) else {}
    missing: List[str] = []
    for key in REQUIRED_EXECUTION_FIELDS:
        if key not in execution_details or execution_details.get(key) in (None, "", []):
            missing.append(str(key))
    return missing


def _bundle_artifacts(lifecycle_bundle: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = lifecycle_bundle.get("artifacts")
    return artifacts if isinstance(artifacts, dict) else {}


def _section_provenance(lifecycle_bundle: Dict[str, Any]) -> Dict[str, Any]:
    section_provenance = lifecycle_bundle.get("section_provenance")
    return section_provenance if isinstance(section_provenance, dict) else {}


def _read_hold_payload(trade_dir: Path) -> Dict[str, Any]:
    return _read_json(trade_dir / "hold.json")


def _resolve_same_day_linkage(lifecycle_bundle: Dict[str, Any], trade_dir: Path) -> Dict[str, Any]:
    linkage = lifecycle_bundle.get("same_day_reporter_linkage")
    if isinstance(linkage, dict) and _linkage_surface_present(linkage):
        return dict(linkage)

    artifacts = _bundle_artifacts(lifecycle_bundle)
    section_provenance = _section_provenance(lifecycle_bundle)
    candidate_paths = [
        artifacts.get("reporter_analysis_json"),
        artifacts.get("reporter_analysis_md"),
        ((section_provenance.get("reporter_status_human") or {}) if isinstance(section_provenance.get("reporter_status_human"), dict) else {}).get("artifact_path"),
    ]
    for raw in candidate_paths:
        if not raw:
            continue
        candidate = Path(str(raw))
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            return {
                "status": "linked_day_fallback",
                "linkage_reason": "same_day_reporter_artifact_present",
                "artifact_path": str(candidate),
            }
    return linkage if isinstance(linkage, dict) else {}


def _resolve_holding_evidence(lifecycle_bundle: Dict[str, Any], trade_dir: Path) -> Dict[str, Any]:
    hold_payload = _read_hold_payload(trade_dir)
    monitor_context_snapshots = [
        dict(row)
        for row in list(lifecycle_bundle.get("monitor_context_snapshots") or [])
        if isinstance(row, dict)
    ]
    if not monitor_context_snapshots:
        monitor_context_snapshots = [
            dict((row.get("monitor_context") or {}))
            for row in list(hold_payload.get("holding_events") or [])
            if isinstance(row, dict) and isinstance(row.get("monitor_context"), dict)
        ]

    if not monitor_context_snapshots:
        exit_ctx = lifecycle_bundle.get("exit", {}) if isinstance(lifecycle_bundle.get("exit"), dict) else {}
        entry_ctx = lifecycle_bundle.get("entry", {}) if isinstance(lifecycle_bundle.get("entry"), dict) else {}
        fallback_monitor = exit_ctx.get("monitor_context") or entry_ctx.get("monitor_context")
        if fallback_monitor and isinstance(fallback_monitor, dict):
            monitor_context_snapshots.append(dict(fallback_monitor))
            if not holding_phase_summary:
                holding_phase_summary = "Hold evidence recovered from execution context."

    hold_events_count = int(lifecycle_bundle.get("hold_events_count") or 0)
    if hold_events_count <= 0:
        hold_events_count = len(list(hold_payload.get("holding_events") or []))
    if hold_events_count <= 0:
        hold_events_count = sum(
            1
            for row in list(lifecycle_bundle.get("timeline") or [])
            if isinstance(row, dict) and str(row.get("event") or "").strip().lower() == "holding"
        )

    holding_phase_summary = str(lifecycle_bundle.get("holding_phase_summary") or "").strip()
    if not holding_phase_summary:
        holding_summary = str(hold_payload.get("summary") or "").strip()
        if holding_summary:
            holding_phase_summary = holding_summary
        elif hold_events_count > 0:
            reasons = []
            for row in list(hold_payload.get("holding_events") or []):
                if not isinstance(row, dict):
                    continue
                reason = str(row.get("monitor_reason") or row.get("exit_reason") or "").strip()
                if reason:
                    reasons.append(reason)
            if reasons:
                deduped = ", ".join(dict.fromkeys(reasons))
                holding_phase_summary = f"Holding observed across {hold_events_count} monitor updates: {deduped}."
            else:
                holding_phase_summary = f"Holding observed across {hold_events_count} monitor updates."

    hold_duration = str(lifecycle_bundle.get("hold_duration") or "").strip()
    if not hold_duration:
        hold_duration = str(
            ((lifecycle_bundle.get("trade_outcome") or {}) if isinstance(lifecycle_bundle.get("trade_outcome"), dict) else {}).get("holding_time")
            or ""
        ).strip()

    hold_duration_sec = lifecycle_bundle.get("hold_duration_sec")
    if hold_duration_sec in (None, ""):
        hold_duration_sec = hold_payload.get("hold_duration_sec")

    return {
        "hold_duration": hold_duration,
        "hold_duration_sec": hold_duration_sec,
        "hold_events_count": hold_events_count,
        "monitor_context_snapshots": monitor_context_snapshots,
        "holding_phase_summary": holding_phase_summary,
    }


def _resolve_execution_details(lifecycle_bundle: Dict[str, Any], trade_dir: Path) -> Dict[str, Any]:
    explicit = lifecycle_bundle.get("execution_details")
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)

    execution = lifecycle_bundle.get("execution")
    execution = execution if isinstance(execution, dict) else {}
    story_contract = lifecycle_bundle.get("story_contract")
    story_contract = story_contract if isinstance(story_contract, dict) else {}
    entry = _read_json(trade_dir / "entry.json")
    exit_payload = _read_json(trade_dir / "exit.json")

    order_id = (
        execution.get("ord_no")
        or ((entry.get("execution_details") or {}) if isinstance(entry.get("execution_details"), dict) else {}).get("order_id")
        or ((exit_payload.get("execution_details") or {}) if isinstance(exit_payload.get("execution_details"), dict) else {}).get("order_id")
        or None
    )

    if order_id in (None, ""):
        for ctx in (lifecycle_bundle.get("exit_execution_details", {}), lifecycle_bundle.get("entry_execution_details", {})):
            if ctx.get("order_id") not in (None, ""):
                order_id = ctx.get("order_id")
                break

    execution_mode_label = str(story_contract.get("execution_mode_label") or "").strip().lower()
    execution_mode = None
    broker_env = None
    if "simulation" in execution_mode_label or "mock" in execution_mode_label:
        execution_mode = "simulation"
        broker_env = "mock"
    elif execution_mode_label:
        execution_mode = execution_mode_label

    filled_qty = execution.get("qty")
    avg_price = (
        execution.get("avg_price")
        or execution.get("price")
        or entry.get("price")
        or exit_payload.get("price")
        or None
    )
    if avg_price in (None, ""):
        for ctx in (lifecycle_bundle.get("exit_execution_details", {}), lifecycle_bundle.get("entry_execution_details", {})):
            if ctx.get("avg_price") not in (None, ""):
                avg_price = ctx.get("avg_price")
                break
    if avg_price in (None, ""):
        avg_price = (
            _safe_float(lifecycle_bundle.get("exit", {}).get("price")) or
            _safe_float(lifecycle_bundle.get("entry", {}).get("price")) or
            _safe_float(lifecycle_bundle.get("monitor_snapshot", {}).get("average_price"))
        )

    order_status = execution.get("status")
    if order_status in (None, "") and str(execution.get("action") or "").strip():
        order_status = "filled"

    return {
        "order_status": order_status if order_status not in ("", []) else None,
        "order_id": order_id if order_id not in ("", []) else None,
        "execution_mode": execution_mode,
        "broker_env": broker_env,
        "filled_qty": filled_qty if filled_qty not in ("", []) else None,
        "avg_price": avg_price if avg_price not in ("", []) else None,
    }


def _resolve_ai_trade_report_status(
    lifecycle_bundle: Dict[str, Any],
    ai_component: Dict[str, Any],
    ai_trade_report_llm_exists: bool,
) -> str:
    diagnostics = lifecycle_bundle.get("ai_report_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    for candidate in (
        ai_component.get("status"),
        diagnostics.get("ai_trade_report_status"),
        lifecycle_bundle.get("ai_trade_report_status"),
    ):
        value = str(candidate or "").strip().lower()
        if value:
            return value
    if ai_trade_report_llm_exists:
        return "ok"
    return ""


def _is_closed_trade_report_generation_regression(
    *, closed_trade: bool, ai_trade_report_llm_exists: bool, ai_status: str
) -> bool:
    if not closed_trade:
        return False
    if not ai_trade_report_llm_exists:
        return True
    normalized = str(ai_status or "").strip().lower()
    if not normalized:
        return False
    return normalized in {"failed", "error", "skipped"}


def read_trade_diagnostic_row(trade_dir: Path) -> Dict[str, Any]:
    lifecycle_path = _artifact_path(
        trade_dir,
        "lifecycle_bundle.json",
        "lifecycle/trade_lifecycle.json",
        "trade_lifecycle.json",
    )
    generation_state_path = trade_dir / "reports" / "report_generation_state.json"
    ai_trade_report_llm_path = _artifact_path(
        trade_dir,
        "reports/ai_trade_report_llm_response.json",
        "ai_trade_report/ai_trade_report_llm_response.json",
    )
    lifecycle_bundle = _read_json(lifecycle_path)
    generation_state = _read_json(generation_state_path)
    components = generation_state.get("components") if isinstance(generation_state.get("components"), dict) else {}
    ai_component = components.get("ai_trade_report") if isinstance(components.get("ai_trade_report"), dict) else {}
    ai_trade_report_llm_exists = ai_trade_report_llm_path.exists()
    same_day_linkage = _resolve_same_day_linkage(lifecycle_bundle, trade_dir)
    holding_evidence = _resolve_holding_evidence(lifecycle_bundle, trade_dir)
    holding_phase_summary = str(holding_evidence.get("holding_phase_summary") or "").strip()
    hold_events_count = int(holding_evidence.get("hold_events_count") or 0)
    monitor_context_snapshots = [
        dict(row)
        for row in list(holding_evidence.get("monitor_context_snapshots") or [])
        if isinstance(row, dict)
    ]
    execution_details = _resolve_execution_details(lifecycle_bundle, trade_dir)
    closed_trade = _is_closed_trade(lifecycle_bundle)
    story_type = str(
        lifecycle_bundle.get("story_type")
        or ((lifecycle_bundle.get("story_contract") or {}) if isinstance(lifecycle_bundle.get("story_contract"), dict) else {}).get("story_type")
        or ""
    ).strip().lower()
    ai_status = _resolve_ai_trade_report_status(lifecycle_bundle, ai_component, ai_trade_report_llm_exists)
    return_pct = _safe_float(((lifecycle_bundle.get("trade_outcome") or {}) if isinstance(lifecycle_bundle.get("trade_outcome"), dict) else {}).get("return_pct"))
    same_day_linkage_missing = not _linkage_surface_present(same_day_linkage)
    holding_evidence_thin = bool(
        lifecycle_bundle.get("hold_evidence_thin")
        or hold_events_count <= 0
        or (not monitor_context_snapshots and not holding_phase_summary)
    )
    execution_missing_fields = _execution_missing_fields(execution_details)
    row = {
        "trade_id": str(lifecycle_bundle.get("trade_id") or trade_dir.name),
        "day": str(lifecycle_bundle.get("day") or trade_dir.parent.name),
        "symbol": str(lifecycle_bundle.get("symbol") or ""),
        "story_type": story_type,
        "lifecycle_status": str(lifecycle_bundle.get("trade_lifecycle_status") or lifecycle_bundle.get("status") or ""),
        "closed_trade": closed_trade,
        "loss_trade": bool(return_pct is not None and return_pct < 0),
        "return_pct": return_pct,
        "hold_duration": str(holding_evidence.get("hold_duration") or ""),
        "hold_duration_sec": holding_evidence.get("hold_duration_sec"),
        "holding_evidence_thin": holding_evidence_thin,
        "holding_phase_summary": holding_phase_summary,
        "hold_events_count": hold_events_count,
        "monitor_context_snapshots_count": len(monitor_context_snapshots),
        "same_day_linkage_status": str(same_day_linkage.get("status") or ""),
        "same_day_linkage_reason": str(same_day_linkage.get("linkage_reason") or ""),
        "same_day_linkage_missing": same_day_linkage_missing,
        "execution_fields_missing": execution_missing_fields,
        "execution_missing_fields_count": len(execution_missing_fields),
        "ai_trade_report_llm_response_exists": ai_trade_report_llm_exists,
        "ai_trade_report_status": ai_status,
        "closed_trade_report_generation_regression": _is_closed_trade_report_generation_regression(
            closed_trade=closed_trade,
            ai_trade_report_llm_exists=ai_trade_report_llm_exists,
            ai_status=ai_status,
        ),
        "closed_trade_decision_only_misclassification": bool(closed_trade and story_type == "decision_only"),
        "report_generation_state_path": str(generation_state_path),
        "lifecycle_bundle_path": str(lifecycle_path),
    }
    return row


def iter_trade_diagnostic_rows(reports_root: Path, day: str) -> List[Dict[str, Any]]:
    return [read_trade_diagnostic_row(trade_dir) for trade_dir in iter_trade_dirs(reports_root, day)]


def _top_recurring_weakness(rows: Iterable[Dict[str, Any]]) -> str:
    counter: Counter[str] = Counter()
    for row in rows:
        if bool(row.get("closed_trade_report_generation_regression")):
            counter["closed_trade_report_generation_regression"] += 1
        if bool(row.get("closed_trade_decision_only_misclassification")):
            counter["closed_trade_decision_only_misclassification"] += 1
        if bool(row.get("holding_evidence_thin")):
            counter["holding_evidence_thin"] += 1
        if bool(row.get("same_day_linkage_missing")):
            counter["same_day_linkage_missing"] += 1
        if int(row.get("execution_missing_fields_count") or 0) > 0:
            counter["execution_fields_missing"] += 1
    if not counter:
        return "none"
    return str(counter.most_common(1)[0][0])


def audit_profitability_recovery_day(reports_root: Path, day: str) -> Dict[str, Any]:
    rows = iter_trade_diagnostic_rows(reports_root, day)
    return {
        "schema_version": "profitability_recovery_day1_audit.v1",
        "day": str(day),
        "trade_count": len(rows),
        "closed_trade_count": sum(1 for row in rows if bool(row.get("closed_trade"))),
        "closed_trade_report_generation_regression_count": sum(
            1 for row in rows if bool(row.get("closed_trade_report_generation_regression"))
        ),
        "closed_trade_decision_only_misclassification_count": sum(
            1 for row in rows if bool(row.get("closed_trade_decision_only_misclassification"))
        ),
        "holding_evidence_thin_count": sum(1 for row in rows if bool(row.get("holding_evidence_thin"))),
        "same_day_linkage_missing_count": sum(1 for row in rows if bool(row.get("same_day_linkage_missing"))),
        "execution_fields_missing_count": sum(
            int(row.get("execution_missing_fields_count") or 0) for row in rows
        ),
        "top_recurring_diagnostic_weakness": _top_recurring_weakness(rows),
        "rows": rows,
    }


def build_daily_profitability_scorecard(reports_root: Path, day: str) -> Dict[str, Any]:
    audit = audit_profitability_recovery_day(reports_root, day)
    rows = list(audit.get("rows") or [])
    return {
        "schema_version": "daily_profitability_scorecard.v1",
        "day": str(day),
        "total_trades": int(audit.get("trade_count") or 0),
        "closed_trades": int(audit.get("closed_trade_count") or 0),
        "loss_trades": sum(1 for row in rows if bool(row.get("loss_trade"))),
        "lifecycle_linkage_missing_count": int(audit.get("same_day_linkage_missing_count") or 0),
        "holding_evidence_thin_count": int(audit.get("holding_evidence_thin_count") or 0),
        "execution_fields_missing_count": int(audit.get("execution_fields_missing_count") or 0),
        "closed_trade_report_generation_regression_count": int(
            audit.get("closed_trade_report_generation_regression_count") or 0
        ),
        "closed_trade_decision_only_misclassification_count": int(
            audit.get("closed_trade_decision_only_misclassification_count") or 0
        ),
        "top_recurring_diagnostic_weakness": str(
            audit.get("top_recurring_diagnostic_weakness") or "none"
        ),
        "rows": rows,
    }
