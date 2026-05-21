from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def defer_full_trade_report_artifacts(diagnostics: Dict[str, Any], generation_mode: str = "") -> bool:
    status = str((diagnostics or {}).get("report_status") or "").strip().lower()
    reason_code = str((diagnostics or {}).get("report_reason_code") or "").strip().lower()
    if str(generation_mode or "").strip().lower() == "pending_no_report":
        return True
    return status == "pending" and reason_code in {
        "awaiting_exit_for_full_report",
        "partial_exit_awaiting_full_close",
        "still_open_lifecycle",
    }


def report_before_full_close_reason(
    *,
    lifecycle_status: str,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    monitor_reason_human: Dict[str, Any],
) -> str:
    """Allow explicit diagnostic reports for recoveries and enriched open snapshots."""

    status = str(lifecycle_status or "").strip().lower()
    lifecycle_obj = lifecycle if isinstance(lifecycle, dict) else {}
    bundle = lifecycle_bundle if isinstance(lifecycle_bundle, dict) else {}
    if status == "partial":
        entry_ctx = lifecycle_obj.get("entry") if isinstance(lifecycle_obj.get("entry"), dict) else {}
        entry_reason = str(entry_ctx.get("reason_human") or "").strip().lower()
        entry_missing = (
            not str(entry_ctx.get("ts") or "").strip()
            or "entry evidence was not captured" in entry_reason
        )
        trade_origin = str(bundle.get("trade_origin") or "").strip().lower()
        missing_sections = {
            str(x or "").strip().lower()
            for x in list(bundle.get("recovery_missing_sections") or [])
            if str(x or "").strip()
        }
        if entry_missing or trade_origin == "recovered_partial" or (
            bool(bundle.get("evidence_recovery_used"))
            and ("entry" in missing_sections or "entry_evidence" in missing_sections)
        ):
            return "recovered_partial_lifecycle"

    if status == "open":
        monitor = monitor_reason_human if isinstance(monitor_reason_human, dict) else {}
        price_source = str(monitor.get("price_source") or "").strip()
        has_runtime_price = price_source.startswith("runtime_state.position.")
        has_position_snapshot = (
            monitor.get("current_price") not in (None, "")
            and monitor.get("average_price") not in (None, "")
        )
        if has_runtime_price and has_position_snapshot:
            return "runtime_state_open_monitor_snapshot"
    return ""


def remove_deferred_trade_report_artifacts(*paths: Path) -> None:
    for path in paths:
        try:
            target = Path(path)
            if target.exists():
                target.unlink()
        except Exception:
            continue


def sanitize_error_message(value: Any, *, max_len: int = 260) -> str:
    text = str(value or "").strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def has_report_text_corruption(report: Any) -> bool:
    if not isinstance(report, dict):
        return False
    section_keys = (
        "market_context",
        "market_context_at_entry",
        "strategist_summary",
        "why_this_symbol_was_chosen",
        "scanner_filters",
    )
    for key in section_keys:
        section = report.get(key)
        if not isinstance(section, dict):
            continue
        texts = [str(section.get("summary") or "")]
        texts.extend([str(item or "") for item in list(section.get("bullets") or [])])
        if any("??" in text for text in texts):
            return True
    return False


def existing_report_conflicts_with_story(report: Any, story_input: Any) -> bool:
    if not isinstance(report, dict) or not isinstance(story_input, dict):
        return False
    expected_status = str(story_input.get("status") or "").strip().lower()
    if not expected_status:
        return False
    shared_facts = report.get("shared_facts") if isinstance(report.get("shared_facts"), dict) else {}
    report_status = str(report.get("status") or shared_facts.get("status") or "").strip().lower()
    if report_status and report_status != expected_status:
        return True

    if expected_status == "closed":
        expected_action = str(story_input.get("action") or "").strip().upper()
        report_action = str(report.get("action") or shared_facts.get("action") or "").strip().upper()
        if expected_action in {"SELL", "EXIT"} and report_action in {"HOLD", "WAIT", "BUY"}:
            return True
        texts = [
            str(((report.get("executive_summary") or {}) if isinstance(report.get("executive_summary"), dict) else {}).get("summary") or ""),
            str(((report.get("final_operator_conclusion") or {}) if isinstance(report.get("final_operator_conclusion"), dict) else {}).get("summary") or ""),
        ]
        if any(" is partial" in text.lower() or "status is partial" in text.lower() for text in texts):
            return True
    return False


def write_legacy_json(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def write_legacy_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return str(path)


def read_json_if_exists(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
