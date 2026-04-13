from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.profitability_recovery_day1 import (
    audit_profitability_recovery_day,
    build_daily_profitability_scorecard,
    read_trade_diagnostic_row,
)
import scripts.check_profitability_recovery_day1 as check_day1
import scripts.daily_profitability_scorecard as day1_scorecard


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _trade_dir(root: Path, day: str, trade_id: str) -> Path:
    trade_dir = root / "trades" / day / trade_id
    (trade_dir / "reports").mkdir(parents=True, exist_ok=True)
    return trade_dir


def _bundle_payload(*, trade_id: str, day: str, status: str = "closed", story_type: str = "live_trade", linkage: dict | None = None, hold_events_count: int = 2, execution_details: dict | None = None, return_pct: float = -0.01) -> dict:
    return {
        "schema_version": "lifecycle_bundle.v1",
        "day": day,
        "trade_id": trade_id,
        "symbol": "000660",
        "trade_lifecycle_status": status,
        "story_type": story_type,
        "entry": {"action": "BUY"},
        "exit": {"action": "SELL"} if status == "closed" else {},
        "trade_outcome": {"return_pct": return_pct},
        "hold_duration": "00:05:00",
        "hold_duration_sec": 300,
        "holding_phase_summary": "Held across monitor updates.",
        "hold_events_count": hold_events_count,
        "monitor_context_snapshots": [{"run_id": "r1"}] if hold_events_count else [],
        "hold_signal_transitions": [{"summary": "changed"}] if hold_events_count else [],
        "pre_exit_context_summary": {"available": status == "closed"},
        "same_day_reporter_linkage": linkage if linkage is not None else {"status": "linked_day_fallback", "linkage_reason": "same-day reporter attached"},
        "execution_details": execution_details
        if execution_details is not None
        else {
            "order_status": "filled",
            "order_id": "A1",
            "execution_mode": "mock",
            "broker_env": "mock",
            "filled_qty": 1,
            "avg_price": 70000.0,
        },
    }


def _generation_state_payload(status: str = "ok") -> dict:
    return {
        "components": {
            "ai_trade_report": {
                "status": status,
            }
        }
    }


def test_profitability_recovery_day1_audit_counts_regressions_and_scorecard(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-13"

    trade_ok = _trade_dir(reports_root, day, "TRD_OK")
    _write_json(trade_ok / "lifecycle_bundle.json", _bundle_payload(trade_id="TRD_OK", day=day))
    _write_json(trade_ok / "reports" / "report_generation_state.json", _generation_state_payload("ok"))
    _write_json(trade_ok / "reports" / "ai_trade_report_llm_response.json", {"status": "ok"})

    trade_bad = _trade_dir(reports_root, day, "TRD_BAD")
    _write_json(
        trade_bad / "lifecycle_bundle.json",
        _bundle_payload(
            trade_id="TRD_BAD",
            day=day,
            story_type="decision_only",
            linkage={},
            hold_events_count=0,
            execution_details={
                "order_status": None,
                "order_id": None,
                "execution_mode": None,
                "broker_env": None,
                "filled_qty": None,
                "avg_price": None,
            },
        ),
    )
    _write_json(trade_bad / "reports" / "report_generation_state.json", _generation_state_payload("skipped"))

    audit = audit_profitability_recovery_day(reports_root, day)
    assert audit["trade_count"] == 2
    assert audit["closed_trade_report_generation_regression_count"] == 1
    assert audit["closed_trade_decision_only_misclassification_count"] == 1
    assert audit["holding_evidence_thin_count"] == 1
    assert audit["same_day_linkage_missing_count"] == 1
    assert audit["execution_fields_missing_count"] == 6

    scorecard = build_daily_profitability_scorecard(reports_root, day)
    assert scorecard["total_trades"] == 2
    assert scorecard["closed_trades"] == 2
    assert scorecard["loss_trades"] == 2
    assert scorecard["top_recurring_diagnostic_weakness"] in {
        "closed_trade_report_generation_regression",
        "closed_trade_decision_only_misclassification",
        "holding_evidence_thin",
        "same_day_linkage_missing",
        "execution_fields_missing",
    }


def test_profitability_recovery_day1_accepts_explicit_missing_linkage_reason(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-13"
    trade_dir = _trade_dir(reports_root, day, "TRD_EXPLICIT")
    _write_json(
        trade_dir / "lifecycle_bundle.json",
        _bundle_payload(
            trade_id="TRD_EXPLICIT",
            day=day,
            linkage={"status": "missing", "linkage_reason": "same-day reporter analysis not available yet"},
        ),
    )
    _write_json(trade_dir / "reports" / "report_generation_state.json", _generation_state_payload("ok"))
    _write_json(trade_dir / "reports" / "ai_trade_report_llm_response.json", {"status": "ok"})

    row = read_trade_diagnostic_row(trade_dir)
    assert row["same_day_linkage_missing"] is False


def test_profitability_recovery_day1_uses_backward_compatible_fallbacks(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-13"
    trade_dir = _trade_dir(reports_root, day, "TRD_FALLBACK")
    reporter_dir = reports_root / "dev" / "analysis" / "reporter_analysis"
    _write_json(reporter_dir / f"reporter_analysis_{day}.json", {"status": "ok"})
    _write_json(
        trade_dir / "lifecycle_bundle.json",
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": day,
            "trade_id": "TRD_FALLBACK",
            "symbol": "000660",
            "trade_lifecycle_status": "closed",
            "story_type": "simulation",
            "entry": {"action": "BUY"},
            "exit": {"action": "SELL"},
            "trade_outcome": {"return_pct": -0.01, "holding_time": "3.0m"},
            "execution": {"action": "SELL", "qty": 1, "price": 70100.0, "ord_no": "A77"},
            "story_contract": {"execution_mode_label": "simulation (mock broker)"},
            "ai_report_diagnostics": {"ai_trade_report_status": "ok"},
            "artifacts": {
                "reporter_analysis_json": str(reporter_dir / f"reporter_analysis_{day}.json"),
            },
        },
    )
    _write_json(
        trade_dir / "hold.json",
        {
            "summary": "Held across one monitor update.",
            "hold_duration_sec": 180,
            "holding_events": [
                {
                    "run_id": "hold-1",
                    "monitor_context": {"monitor_reason": "hold_position"},
                }
            ],
        },
    )
    _write_json(trade_dir / "reports" / "ai_trade_report_llm_response.json", {"status": "ok"})

    row = read_trade_diagnostic_row(trade_dir)
    assert row["closed_trade_report_generation_regression"] is False
    assert row["same_day_linkage_missing"] is False
    assert row["hold_events_count"] == 1
    assert row["holding_evidence_thin"] is False
    assert row["hold_duration"] == "3.0m"
    assert row["execution_missing_fields_count"] == 0


def test_profitability_recovery_day1_scripts_emit_expected_summary(tmp_path: Path, capsys) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-13"
    trade_dir = _trade_dir(reports_root, day, "TRD_OK")
    _write_json(trade_dir / "lifecycle_bundle.json", _bundle_payload(trade_id="TRD_OK", day=day))
    _write_json(trade_dir / "reports" / "report_generation_state.json", _generation_state_payload("ok"))
    _write_json(trade_dir / "reports" / "ai_trade_report_llm_response.json", {"status": "ok"})

    assert check_day1.main(["--date", day, "--reports-root", str(reports_root)]) == 0
    check_output = capsys.readouterr().out
    assert "closed trade report generation regression" in check_output.lower()

    assert day1_scorecard.main(["--date", day, "--reports-root", str(reports_root)]) == 0
    scorecard_output = capsys.readouterr().out
    assert "daily profitability scorecard" in scorecard_output.lower()
