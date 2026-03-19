from __future__ import annotations

import json
from pathlib import Path

from scripts.check_reports_trades_health import audit_reports_trades_health


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_audit_reports_trades_health_flags_partial_and_mismatch(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_root = reports_root / "trades" / "2026-03-18" / "TRD_20260318_000660_01"

    _write_json(
        trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "status": "open",
            "ai_report_diagnostics": {
                "report_status": "failed",
                "report_reason_code": "llm_generation_failed",
            },
        },
    )
    _write_json(
        trade_root / "ai_trade_report" / "ai_trade_report_llm_response.json",
        {
            "status": "salvaged",
            "required_keys_missing": ["timeline", "final_operator_conclusion"],
            "meta": {"parse_error": "JSONDecodeError: truncated"},
        },
    )
    _write_json(
        trade_root / "brief" / "brief_llm_response.json",
        {
            "status": "error",
            "meta": {"reason": "llm_error:The read operation timed out"},
        },
    )
    _write_json(
        trade_root / "brief_llm_response.json",
        {
            "status": "error",
            "meta": {"reason": "llm_error:The read operation timed out"},
        },
    )
    _write_json(
        trade_root / "strategist" / "strategist_llm_response.json",
        {
            "status": "fallback",
            "parse_mode": "none",
            "raw_response_text": "",
            "meta": {
                "synthetic_placeholder": True,
                "reason_code": "no_linked_strategist_llm_evidence",
            },
        },
    )

    out = audit_reports_trades_health(reports_root, day="2026-03-18")

    assert out["trade_dir_count"] == 1
    assert out["llm_status_counts"]["ai_trade_report:salvaged"] == 1
    assert out["llm_status_counts"]["brief:error"] == 1
    assert out["llm_status_counts"]["strategist:synthetic_placeholder"] == 1
    assert out["lifecycle_report_status_counts"]["failed"] == 1
    assert out["duplicate_counts"]["brief_llm_response:identical"] == 1
    assert out["issue_counts"]["llm_partial"] == 1
    assert out["issue_counts"]["llm_error"] == 1
    assert out["issue_counts"].get("llm_fallback", 0) == 0
    assert out["issue_counts"]["diagnostic_status_mismatch"] == 1
    assert out["issue_counts"]["sidecar_missing"] == 3


def test_audit_reports_trades_health_treats_empty_strategist_fallback_as_placeholder(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_root = reports_root / "trades" / "2026-03-19" / "TRD_20260319_005930_01"

    _write_json(
        trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "status": "closed",
            "ai_report_diagnostics": {
                "report_status": "available",
            },
        },
    )
    _write_json(trade_root / "_provenance.json", {})
    _write_json(trade_root / "_health.json", {})
    _write_json(trade_root / "_artifact_links.json", {})
    _write_json(
        trade_root / "strategist" / "strategist_llm_response.json",
        {
            "status": "fallback",
            "parse_mode": "none",
            "model": "",
            "raw_response_text": "",
            "error": "",
            "retry_count": 0,
            "meta": {},
        },
    )

    out = audit_reports_trades_health(reports_root, day="2026-03-19")

    assert out["llm_status_counts"]["strategist:synthetic_placeholder"] == 1
    assert out["issue_counts"].get("llm_fallback", 0) == 0


def test_audit_reports_trades_health_downgrades_recovered_ai_report_to_info(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_root = reports_root / "trades" / "2026-03-19" / "TRD_20260319_000660_05"

    _write_json(
        trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "status": "closed",
            "ai_report_diagnostics": {
                "report_status": "available",
            },
        },
    )
    _write_json(trade_root / "_provenance.json", {})
    _write_json(trade_root / "_health.json", {})
    _write_json(trade_root / "_artifact_links.json", {})
    _write_json(
        trade_root / "ai_trade_report" / "ai_trade_report_llm_response.json",
        {
            "status": "salvaged",
            "required_keys_missing": ["entry_decision", "exit_decision"],
            "meta": {"parse_error": "JSONDecodeError: truncated"},
        },
    )
    _write_json(
        trade_root / "ai_trade_report" / "ai_trade_report.json",
        {
            "executive_summary": {},
            "market_context_at_entry": {},
            "why_this_symbol_was_chosen": {},
            "entry_decision": {},
            "holding_monitoring_story": {},
            "exit_decision": {},
            "execution_quality": {},
            "scanner_filters": {},
            "guard_approval_result": {},
            "reporter_evaluation": {},
            "errors_weaknesses_improvement_points": {},
            "final_operator_conclusion": {},
        },
    )

    out = audit_reports_trades_health(reports_root, day="2026-03-19")

    assert out["llm_status_counts"]["ai_trade_report:salvaged"] == 1
    assert out["issue_counts"]["llm_recovered"] == 1
    assert out["issue_counts"].get("llm_partial", 0) == 0
    assert out["severity_counts"]["info"] == 1
