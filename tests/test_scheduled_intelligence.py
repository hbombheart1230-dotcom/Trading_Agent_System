from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.scheduled_intelligence import (
    materialize_closeout_intelligence,
    materialize_preopen_intelligence,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_preopen_manifest_and_memory_receipt_use_existing_strategist_artifact(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write(
        reports / "canonical" / "2026-08-26" / "run-session-live-preopen" / "strategist.json",
        {
            "day": "2026-08-27",
            "ts": "2026-08-27T08:50:01+09:00",
            "market_regime": "risk_on",
            "market_sentiment": "positive",
            "final_playbook": "breakout",
            "tactical_strategy": "opening_range_breakout",
            "themes": ["semiconductor"],
            "strategy_thesis": {"risk_tone": "normal", "one_line": "opening strength"},
            "llm_metadata_summary": {"status": "ok", "model": "test/model"},
            "strategy_memory_snapshot": {"day": "2026-08-26", "status": "ok", "artifact_path": "memory.json"},
            "memory_packet_visibility": {
                "strategy_memory": {"present": True, "status": "ok", "resolved_day": "2026-08-26"},
                "memory_packets": {"daily": {"status": "ok", "active": True, "resolved_day": "2026-08-26"}},
            },
        },
    )

    result = materialize_preopen_intelligence(day="2026-08-27", capture_rc=0, session_rc=0, reports_root=reports)
    briefing = json.loads(Path(result["briefing_json_path"]).read_text(encoding="utf-8"))
    receipt = json.loads(Path(result["memory_receipt_path"]).read_text(encoding="utf-8"))

    assert result["status"] == "SUCCESS"
    assert briefing["market_frame"]["tactical_strategy"] == "opening_range_breakout"
    assert receipt["status"] == "DELIVERED_ACTIVE"
    assert receipt["source_day"] == "2026-08-26"


def test_preopen_snapshot_failure_is_partial_without_hiding_strategist_success(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write(
        reports / "canonical" / "2026-08-26" / "run-session-live-preopen" / "strategist.json",
        {"day": "2026-08-27", "status": "ok"},
    )
    result = materialize_preopen_intelligence(day="2026-08-27", capture_rc=2, session_rc=0, reports_root=reports)
    payload = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert result["status"] == "PARTIAL"
    assert "PREOPEN_MARKET_SNAPSHOT_FAILED" in payload["issues"]


def test_closeout_index_reuses_steps_and_records_memory_delivery_pending(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    memory = reports / "performance" / "2026-08-27" / "strategy_memory.json"
    _write(memory, {"day": "2026-08-27", "status": "ok"})
    payload = {
        "ok": True,
        "trigger": "test",
        "steps": {
            "account_snapshot": {"ok": True, "path": "snapshot.json"},
            "broker_closed_trade_reconciliation": {"ok": True},
            "operator_daily_summary_artifact": {"ok": True, "performance_memory_sync": {"ok": True}},
            "operator_visibility_summary": {"ok": True},
            "post_exit_shadow_recap": {"ok": True},
        },
    }
    result = materialize_closeout_intelligence(
        day="2026-08-27", closeout_payload=payload, closeout_paths={}, reports_root=reports,
    )
    index = json.loads(Path(result["index_json_path"]).read_text(encoding="utf-8"))
    assert result["status"] == "SUCCESS"
    assert index["memory"]["status"] == "GENERATED"
    assert index["memory"]["next_session_delivery"] == "PENDING_PREOPEN_RECEIPT"
