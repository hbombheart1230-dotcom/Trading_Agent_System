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
