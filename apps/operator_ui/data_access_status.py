from __future__ import annotations

from typing import Any, Dict


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _trim_text(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def story_type_label(story_type: Any) -> str:
    raw = str(story_type or "").strip().lower()
    mapping = {
        "live_trade": "Live trade report",
        "simulation": "Simulation trade report",
        "failed_execution": "Failed execution report",
        "decision_only": "Decision-only summary",
    }
    return mapping.get(raw, "Unknown report type")


def story_type_badge_class(story_type: Any) -> str:
    raw = str(story_type or "").strip().lower()
    if raw == "live_trade":
        return "status-badge status-badge--ok"
    if raw == "failed_execution":
        return "status-badge status-badge--critical"
    if raw in {"simulation", "decision_only"}:
        return "status-badge status-badge--warn"
    return "status-badge"


def normalize_report_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"available", "skipped", "pending", "failed"}:
        return raw
    return ""


def report_status_label(status: Any) -> str:
    raw = normalize_report_status(status)
    if raw == "available":
        return "AI Report Available"
    if raw == "pending":
        return "AI Report Pending"
    if raw == "failed":
        return "AI Report Failed"
    if raw == "skipped":
        return "AI Report Skipped"
    return "AI Report"


def report_status_badge_class(status: Any) -> str:
    raw = normalize_report_status(status)
    if raw == "available":
        return "status-badge status-badge--ok"
    if raw in {"pending", "skipped"}:
        return "status-badge status-badge--warn"
    if raw == "failed":
        return "status-badge status-badge--critical"
    return "status-badge"


def report_reason_human(code: Any) -> str:
    raw = str(code or "").strip().lower()
    mapping = {
        "no_executed_lifecycle": "No executed trade lifecycle was created for this run.",
        "decision_only_run": "This run was decision-only, so a full AI trade report was not generated.",
        "hold_only_run": "This run only updated hold/monitor state, so a full AI trade report was not generated.",
        "execution_failed": "Execution did not complete successfully, so a full AI trade report was skipped.",
        "missing_story_input": "Trade story input was not created, so report generation could not continue.",
        "llm_generation_failed": "Trade story input existed, but AI report generation failed.",
        "artifact_write_failed": "AI report generation ran, but writing report artifacts failed.",
        "missing_report_linkage": "A linked AI trade report could not be found for this run.",
        "report_not_requested": "AI trade report generation was not requested for this run.",
        "still_open_lifecycle": "This trade lifecycle is still open, so the full AI report is pending.",
        "awaiting_exit_for_full_report": "This trade is still open. The full AI report is generated after exit or closure.",
    }
    return mapping.get(raw, "AI trade report status is not fully classified yet.")


def report_next_step(code: Any) -> str:
    raw = str(code or "").strip().lower()
    mapping = {
        "no_executed_lifecycle": "Keep using the Operator Brief. A full report is generated only for executed trade lifecycles.",
        "decision_only_run": "Continue with the Operator Brief. Generate AI reports only after executed lifecycle events.",
        "hold_only_run": "Continue monitoring. Generate the full AI report after an executed entry or exit lifecycle is formed.",
        "execution_failed": "Review execution failure details and rerun after execution stabilizes.",
        "missing_story_input": "Inspect story input generation first, then retry report generation.",
        "llm_generation_failed": "Check OpenRouter and model connectivity, then retry report generation.",
        "artifact_write_failed": "Check filesystem write path and permissions, then retry.",
        "missing_report_linkage": "Regenerate lifecycle or report linkage for this run and retry.",
        "report_not_requested": "Enable AI trade report generation policy, then rerun.",
        "still_open_lifecycle": "Generate the full AI report after lifecycle exit or closure.",
        "awaiting_exit_for_full_report": "Generate the final AI report after exit or closure.",
    }
    return mapping.get(raw, "Review diagnostics and proceed with the Operator Brief in the meantime.")


def portfolio_sync_badge_class(status: Any) -> str:
    raw = str(status or "").strip().lower()
    if raw in {"aligned", "reconciled"}:
        return "status-badge status-badge--ok"
    if raw == "unavailable":
        return "status-badge"
    return "status-badge status-badge--critical"


def portfolio_sync_label(status: Any) -> str:
    raw = str(status or "").strip().lower()
    mapping = {
        "aligned": "Portfolio Sync OK",
        "reconciled": "Portfolio Reconciled",
        "mismatch": "Portfolio Mismatch",
        "reader_error": "Portfolio Reader Error",
        "unavailable": "Sync status unavailable",
    }
    return mapping.get(raw, "Portfolio Sync")


def portfolio_sync_sentence(status: Any) -> str:
    raw = str(status or "").strip().lower()
    mapping = {
        "aligned": "계좌 보유 종목과 로컬 상태가 일치했습니다.",
        "reconciled": "계좌 보유 종목을 기준으로 로컬 상태를 자동 정합했습니다.",
        "mismatch": "계좌 보유 종목과 로컬 상태 불일치가 남아 있습니다. 신규 BUY는 차단됩니다.",
        "reader_error": "계좌 조회에 실패했습니다. 신규 BUY는 차단됩니다.",
        "unavailable": "이 run에는 계좌 동기화 상태가 기록되지 않았습니다.",
    }
    return mapping.get(raw, "계좌 동기화 상태를 확인해 주세요.")


def portfolio_positions_source_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "reader_positions_authoritative": "Reader positions",
        "reader_positions_authoritative_empty": "Reader says no positions",
        "reader_positions": "Reader positions",
        "persisted_mock_positions": "Local fallback positions",
        "reader_positions_empty": "No positions",
    }
    return mapping.get(raw, raw.replace("_", " ") if raw else "")


def portfolio_reconciliation_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "aligned": "Already aligned",
        "reader_aligned": "Already aligned",
        "reconciled_to_reader": "Reconciled to account reader",
        "persisted_fallback": "Using local fallback",
        "empty": "No active positions",
    }
    return mapping.get(raw, raw.replace("_", " ") if raw else "")


def build_portfolio_sync_card(raw: Any) -> Dict[str, Any]:
    guard = raw if isinstance(raw, dict) else {}
    if not guard:
        status = "unavailable"
        return {
            "available": False,
            "status": status,
            "status_label": portfolio_sync_label(status),
            "badge_class": portfolio_sync_badge_class(status),
            "sentence": portfolio_sync_sentence(status),
            "note": "",
            "positions_source": "",
            "positions_source_label": "",
            "reconciliation_status": "",
            "reconciliation_label": "",
            "reader_ok": None,
            "reader_error": "",
            "reader_positions_authoritative": False,
            "positions_mismatch_detected": False,
            "reconciliation_applied": False,
            "reader_positions_count": 0,
            "persisted_positions_count": 0,
        }

    reader_ok = bool(guard.get("reader_ok"))
    mismatch = bool(guard.get("positions_mismatch_detected"))
    reconciled = bool(guard.get("reconciliation_applied"))
    if not reader_ok:
        status = "reader_error"
    elif mismatch and reconciled:
        status = "reconciled"
    elif mismatch:
        status = "mismatch"
    else:
        status = "aligned"

    positions_source = str(guard.get("positions_source") or "")
    reconciliation_status = str(guard.get("reconciliation_status") or "")
    counts_note = f"Reader {_safe_int(guard.get('reader_positions_count'), 0)} / local {_safe_int(guard.get('persisted_positions_count'), 0)}"
    note_bits = [
        bit
        for bit in [
            portfolio_positions_source_label(positions_source),
            portfolio_reconciliation_label(reconciliation_status),
            counts_note,
        ]
        if bit
    ]

    return {
        "available": True,
        "status": status,
        "status_label": portfolio_sync_label(status),
        "badge_class": portfolio_sync_badge_class(status),
        "sentence": portfolio_sync_sentence(status),
        "note": " | ".join(note_bits),
        "positions_source": positions_source,
        "positions_source_label": portfolio_positions_source_label(positions_source),
        "reconciliation_status": reconciliation_status,
        "reconciliation_label": portfolio_reconciliation_label(reconciliation_status),
        "reader_ok": reader_ok,
        "reader_error": str(guard.get("reader_error") or ""),
        "reader_positions_authoritative": bool(guard.get("reader_positions_authoritative")),
        "positions_mismatch_detected": mismatch,
        "reconciliation_applied": reconciled,
        "reader_positions_count": _safe_int(guard.get("reader_positions_count"), 0),
        "persisted_positions_count": _safe_int(guard.get("persisted_positions_count"), 0),
    }


def normalize_ai_report_diagnostics(
    raw: Any,
    *,
    report_exists: bool,
    lifecycle_status: Any,
    story_type: Any,
    model_hint: Any = "",
    generation: Any = None,
) -> Dict[str, Any]:
    diag = raw if isinstance(raw, dict) else {}
    generation_obj = generation if isinstance(generation, dict) else {}
    lifecycle = str(lifecycle_status or "").strip().lower()
    story = str(story_type or "").strip().lower()

    status = normalize_report_status(diag.get("report_status"))
    reason_code = str(diag.get("report_reason_code") or "").strip().lower()

    if not status:
        if report_exists:
            status = "available"
            reason_code = reason_code or ""
        elif lifecycle == "open":
            status = "pending"
            reason_code = reason_code or "awaiting_exit_for_full_report"
        elif story == "decision_only":
            status = "skipped"
            reason_code = reason_code or "decision_only_run"
        elif story == "failed_execution":
            status = "skipped"
            reason_code = reason_code or "execution_failed"
        else:
            status = "failed"
            reason_code = reason_code or "missing_report_linkage"

    if status == "available" and not report_exists:
        status = "failed"
        reason_code = "missing_report_linkage"

    reason_human = _trim_text(diag.get("report_reason_human"), max_len=320)
    if not reason_human:
        reason_human = report_reason_human(reason_code)

    next_step = _trim_text(diag.get("next_expected_step"), max_len=320)
    if not next_step:
        next_step = report_next_step(reason_code)

    model_used = (
        _trim_text(diag.get("llm_model_used"), max_len=120)
        or _trim_text(diag.get("llm_model"), max_len=120)
        or _trim_text(generation_obj.get("model"), max_len=120)
        or _trim_text(model_hint, max_len=120)
        or "not_captured"
    )
    provider = _trim_text(diag.get("llm_provider"), max_len=64) or "OpenRouter"

    generation_attempted = bool(diag.get("generation_attempted"))
    if not generation_attempted and str(generation_obj.get("status") or "").strip():
        generation_attempted = True
    generation_ts = _trim_text(diag.get("generation_ts"), max_len=64)
    last_error_message = _trim_text(diag.get("last_error_message"), max_len=260)
    if not last_error_message and status == "failed":
        last_error_message = _trim_text(generation_obj.get("reason"), max_len=260)

    story_input_available = bool(diag.get("story_input_available")) if "story_input_available" in diag else True
    report_output_available = (
        bool(diag.get("report_output_available"))
        if "report_output_available" in diag
        else bool(diag.get("report_artifact_available"))
        if "report_artifact_available" in diag
        else report_exists
    )

    return {
        "report_status": status,
        "report_status_label": report_status_label(status),
        "report_status_badge_class": report_status_badge_class(status),
        "report_reason_code": reason_code,
        "report_reason_human": reason_human,
        "generation_attempted": generation_attempted,
        "generation_ts": generation_ts,
        "story_input_available": story_input_available,
        "report_output_available": report_output_available,
        "report_artifact_available": report_output_available,
        "llm_provider": provider,
        "llm_model_used": model_used,
        "expected_generation_mode": _trim_text(diag.get("expected_generation_mode"), max_len=120) or "per-trade free model report",
        "next_expected_step": next_step,
        "last_error_message": last_error_message,
    }
