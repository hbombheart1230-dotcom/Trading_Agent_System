from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.llm_artifacts import symbol_artifact_paths
from libs.reporting.symbol_trade_report import build_symbol_trade_summary
from libs.reporting.symbol_trade_report import build_symbol_memory_payload
from libs.reporting.symbol_trade_report import generate_symbol_trade_report


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_symbol_artifact_paths_use_canonical_symbol_root(tmp_path: Path) -> None:
    paths = symbol_artifact_paths(tmp_path / "reports", "005930")
    assert paths["root_dir"] == tmp_path / "reports" / "symbols" / "005930"
    assert paths["symbol_trade_report_json"] == tmp_path / "reports" / "symbols" / "005930" / "symbol_trade_report.json"
    assert paths["symbol_memory_json"] == tmp_path / "reports" / "symbols" / "005930" / "symbol_memory.json"
    assert paths["trade_history_json"] == tmp_path / "reports" / "symbols" / "005930" / "trade_history.json"


def test_generate_symbol_trade_report_uses_truth_artifacts_not_trade_markdown(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(
        events_path,
        [
            {
                "run_id": "run-1",
                "ts": "2026-03-20T00:01:00+00:00",
                "stage": "strategist",
                "event": "decision_frame",
                "payload": {"payload": {"playbook": "pullback"}},
            },
            {
                "run_id": "run-1",
                "ts": "2026-03-20T00:02:00+00:00",
                "stage": "monitor",
                "event": "entry_decision_detail",
                "payload": {"payload": {"symbol": "005930", "decision": "WAIT", "reason": "volume_confirmation_missing"}},
            },
            {
                "run_id": "run-2",
                "ts": "2026-03-20T00:03:00+00:00",
                "stage": "monitor",
                "event": "entry_decision_detail",
                "payload": {"payload": {"symbol": "005930", "decision": "BUY", "reason": "pullback_reclaim_above_vwap_with_rebound_confirmation"}},
            },
        ],
    )
    lifecycle = {
        "trade_id": "TRD_20260320_005930_01",
        "symbol": "005930",
        "day": "2026-03-20",
        "status": "closed",
        "entry": {
            "run_id": "run-2",
            "ts": "2026-03-20T00:03:10+00:00",
            "price": 70000.0,
            "strategist_context": {"playbook": "pullback"},
        },
        "exit": {
            "run_id": "run-3",
            "ts": "2026-03-20T00:13:10+00:00",
            "price": 71400.0,
        },
        "summary": {
            "entry_reason_human": "분봉 눌림 이후 VWAP 재회복이 확인되었습니다.",
            "exit_reason_human": "목표 수익 실현 기준에 도달해 청산했습니다.",
            "lifecycle_summary_human": "눌림 후 재상승 구간을 활용한 거래였습니다.",
            "operator_conclusion_human": "유효한 pullback 진입 사례로 기록할 수 있습니다.",
        },
    }
    _write_json(
        reports_root / "trades" / "2026-03-20" / "TRD_20260320_005930_01" / "lifecycle" / "trade_lifecycle.json",
        lifecycle,
    )

    out = generate_symbol_trade_report(events_path, reports_root, "005930")

    report_json = Path(str(out["report_json_path"]))
    assert report_json.exists()
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["summary"]["trade_count"] == 1
    assert payload["summary"]["completed_trade_count"] == 1
    assert payload["summary"]["win_count"] == 1
    assert payload["summary"]["recent_playbooks"] == ["pullback"]
    assert payload["summary"]["recent_wait_reasons"] == ["volume_confirmation_missing"]
    assert payload["summary"]["wait_reason_distribution"] == {"volume_confirmation_missing": 1}
    assert payload["summary"]["recent_entry_reasons"] == ["pullback_reclaim_above_vwap_with_rebound_confirmation"]
    assert payload["history_index"][0]["trade_id"] == "TRD_20260320_005930_01"
    assert payload["history_index"][0]["last_action"] == "SELL"
    assert payload["history_index"][0]["last_status"] == "closed"
    latest_snapshot = json.loads((reports_root / "symbols" / "005930" / "latest_snapshot.json").read_text(encoding="utf-8"))
    symbol_memory = json.loads((reports_root / "symbols" / "005930" / "symbol_memory.json").read_text(encoding="utf-8"))
    assert latest_snapshot["last_trade_id"] == "TRD_20260320_005930_01"
    assert latest_snapshot["last_trade_date"] == "2026-03-20"
    assert latest_snapshot["last_action"] == "SELL"
    assert latest_snapshot["last_status"] == "closed"
    assert symbol_memory["schema_version"] == "symbol_memory.v1"
    assert symbol_memory["trade_stats"]["trade_count"] == 1
    assert symbol_memory["latest_snapshot"]["last_trade_date"] == "2026-03-20"
    assert symbol_memory["playbook_stats"]["pullback"]["count"] == 1
    assert symbol_memory["bias_recommendation"]["prefer_playbook"] == "pullback"
    assert latest_snapshot["report_path"].endswith("reports\\ai_trade_report.json") or latest_snapshot["report_path"].endswith("reports/ai_trade_report.json")


def test_symbol_trade_report_handles_no_history_symbol(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])

    payload = build_symbol_trade_summary(events_path, reports_root, "000660")
    assert payload["summary"]["trade_count"] == 0
    assert payload["history_index"] == []
    assert payload["pattern_insights"]["risk_notes"]


def test_symbol_trade_report_marks_recovered_partial_trade_in_latest_snapshot(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])
    bundle_path = reports_root / "trades" / "2026-03-24" / "TRD_20260324_005930_99" / "lifecycle_bundle.json"
    _write_json(
        bundle_path,
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": "2026-03-24",
            "trade_id": "TRD_20260324_005930_99",
            "symbol": "005930",
            "trade_lifecycle_status": "partial",
            "trade_origin": "recovered_partial",
            "lifecycle_completeness": "partial",
            "evidence_recovery_used": True,
            "lifecycle": {
                "entry": {},
                "hold": [],
                "exit": {"run_id": "run-exit", "ts": "2026-03-24T02:30:00+00:00", "price": 70100.0, "reason_human": "recovered exit"},
            },
            "trade_outcome": {"exit_reason": "recovered exit"},
        },
    )

    out = generate_symbol_trade_report(events_path, reports_root, "005930")
    latest_snapshot = json.loads(Path(str(out["latest_snapshot_path"])).read_text(encoding="utf-8"))
    assert latest_snapshot["last_trade_id"] == "TRD_20260324_005930_99"
    assert latest_snapshot["last_action"] == "SELL"
    assert latest_snapshot["trade_origin"] == "recovered_partial"
    assert latest_snapshot["lifecycle_completeness"] == "partial"
    assert latest_snapshot["evidence_recovery_used"] is True


def test_symbol_trade_report_reads_linked_trade_report_and_operator_brief(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])
    trade_root = reports_root / "trades" / "2026-04-02" / "TRD_20260402_000660_01"
    _write_json(
        trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "trade_id": "TRD_20260402_000660_01",
            "symbol": "000660",
            "day": "2026-04-02",
            "status": "closed",
            "entry": {
                "run_id": "run-buy",
                "ts": "2026-04-02T00:10:00+00:00",
                "strategist_context": {"playbook": "defensive"},
            },
            "exit": {
                "run_id": "run-sell",
                "ts": "2026-04-02T00:25:00+00:00",
            },
            "summary": {
                "entry_reason_human": "Scanner selected 000660 as rank #1",
                "exit_reason_human": "SELL was triggered because vwap_breakdown.",
            },
        },
    )
    _write_json(
        trade_root / "reports" / "ai_trade_report.json",
        {
            "executive_summary": {
                "headline": "BUY 000660",
                "summary": "Defensive entry completed and later closed with VWAP breakdown discipline.",
            },
            "market_context_at_entry": {
                "summary": "Market regime was neutral with defensive playbook."
            },
            "entry_decision": {
                "summary": "Pullback reclaim confirmation aligned with defensive entry."
            },
            "final_operator_conclusion": {
                "summary": "The trade stayed disciplined and exited on VWAP loss."
            },
            "strategist_feedback_input": {
                "entry_pattern_type": "pullback",
                "exit_pattern_type": "vwap_breakdown",
                "thesis_invalidation_code": "vwap_loss",
                "improvement_tags": ["insufficient_confirmation"],
                "review_flags": ["needs_human_review"],
            },
            "shared_facts": {
                "pnl_pct": 0.67
            },
        },
    )
    _write_json(
        trade_root / "reports" / "operator_brief.json",
        {
            "headline": "000660 VWAP breakdown exit",
            "executive_summary": "Scanner found the leader, but the trade needed a defensive exit.",
            "risk_summary": "Momentum weakened near VWAP.",
            "next_checkpoints": ["watch VWAP reclaim", "check volume recovery"],
        },
    )

    payload = build_symbol_trade_summary(events_path, reports_root, "000660")

    assert payload["summary"]["recent_trade_headlines"] == ["000660 VWAP breakdown exit"]
    assert payload["summary"]["recent_operator_viewpoints"] == [
        "Scanner found the leader, but the trade needed a defensive exit."
    ]
    assert payload["pattern_insights"]["recent_entry_pattern_types"] == ["pullback"]
    assert payload["pattern_insights"]["recent_exit_pattern_types"] == ["vwap_breakdown"]
    assert payload["pattern_insights"]["recent_improvement_tags"] == ["insufficient_confirmation"]
    assert payload["pattern_insights"]["recent_review_flags"] == ["needs_human_review"]
    assert payload["history_index"][0]["entry_pattern_type"] == "pullback"
    assert payload["history_index"][0]["exit_pattern_type"] == "vwap_breakdown"
    assert payload["history_index"][0]["brief_headline"] == "000660 VWAP breakdown exit"
    assert payload["history_index"][0]["result_pct"] == 0.67


def test_symbol_trade_report_normalizes_ratio_like_result_pct_from_bundle_artifacts(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])
    trade_root = reports_root / "trades" / "2026-04-02" / "TRD_20260402_008350_01"
    _write_json(
        trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "trade_id": "TRD_20260402_008350_01",
            "symbol": "008350",
            "day": "2026-04-02",
            "status": "closed",
            "entry": {
                "run_id": "run-buy",
                "ts": "2026-04-02T00:10:00+00:00",
                "strategist_context": {"playbook": "momentum"},
            },
            "exit": {
                "run_id": "run-sell",
                "ts": "2026-04-02T00:30:00+00:00",
            },
            "summary": {
                "entry_reason_human": "Scanner selected 008350 after breakout move.",
                "exit_reason_human": "SELL was triggered because hard_stop.",
            },
        },
    )
    _write_json(
        trade_root / "lifecycle_bundle.json",
        {
            "trade_id": "TRD_20260402_008350_01",
            "symbol": "008350",
            "day": "2026-04-02",
            "shared_facts": {"pnl_pct": -0.0304},
            "trade_outcome": {"return_pct": -0.0304},
        },
    )

    payload = build_symbol_trade_summary(events_path, reports_root, "008350")

    assert abs(float(payload["history_index"][0]["result_pct"]) - (-3.04)) < 1e-9


def test_symbol_trade_report_prefers_structured_entry_pattern_for_pattern_rows(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])

    winning_trade_root = reports_root / "trades" / "2026-04-02" / "TRD_20260402_000250_01"
    _write_json(
        winning_trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "trade_id": "TRD_20260402_000250_01",
            "symbol": "000250",
            "day": "2026-04-02",
            "status": "closed",
            "entry": {
                "run_id": "run-buy-1",
                "ts": "2026-04-02T00:10:00+00:00",
                "strategist_context": {"playbook": "pullback"},
            },
            "exit": {
                "run_id": "run-sell-1",
                "ts": "2026-04-02T00:30:00+00:00",
            },
            "summary": {
                "entry_reason_human": "legacy entry reason that should not become the final pattern label",
                "exit_reason_human": "SELL was triggered because take_profit.",
            },
        },
    )
    _write_json(
        winning_trade_root / "reports" / "ai_trade_report.json",
        {
            "entry_decision": {"summary": "Breakout confirmation stayed strong."},
            "strategist_feedback_input": {"entry_pattern_type": "breakout"},
            "shared_facts": {"pnl_pct": 1.75},
        },
    )

    losing_trade_root = reports_root / "trades" / "2026-04-02" / "TRD_20260402_000250_02"
    _write_json(
        losing_trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "trade_id": "TRD_20260402_000250_02",
            "symbol": "000250",
            "day": "2026-04-02",
            "status": "closed",
            "entry": {
                "run_id": "run-buy-2",
                "ts": "2026-04-02T01:10:00+00:00",
                "strategist_context": {"playbook": "pullback"},
            },
            "exit": {
                "run_id": "run-sell-2",
                "ts": "2026-04-02T01:30:00+00:00",
            },
            "summary": {
                "entry_reason_human": "another legacy entry reason that should not become the failed pattern label",
                "exit_reason_human": "SELL was triggered because hard_stop.",
            },
        },
    )
    _write_json(
        losing_trade_root / "reports" / "ai_trade_report.json",
        {
            "entry_decision": {"summary": "Pullback reclaim was weak."},
            "strategist_feedback_input": {"entry_pattern_type": "pullback"},
            "shared_facts": {"pnl_pct": -2.1},
        },
    )

    payload = build_symbol_trade_summary(events_path, reports_root, "000250")

    assert payload["pattern_insights"]["successful_entry_patterns"] == ["breakout"]
    assert payload["pattern_insights"]["failed_entry_patterns"] == ["pullback"]


def test_build_symbol_memory_payload_derives_deterministic_bias_fields(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])
    trade_root = reports_root / "trades" / "2026-04-02" / "TRD_20260402_005930_01"
    _write_json(
        trade_root / "lifecycle" / "trade_lifecycle.json",
        {
            "trade_id": "TRD_20260402_005930_01",
            "symbol": "005930",
            "day": "2026-04-02",
            "status": "closed",
            "entry": {
                "run_id": "run-buy",
                "ts": "2026-04-02T00:10:00+00:00",
                "strategist_context": {"playbook": "breakout"},
            },
            "exit": {
                "run_id": "run-sell",
                "ts": "2026-04-02T00:30:00+00:00",
            },
            "summary": {
                "entry_reason_human": "Scanner selected 005930 after breakout move.",
                "exit_reason_human": "SELL was triggered because hard_stop.",
            },
        },
    )
    _write_json(
        trade_root / "reports" / "ai_trade_report.json",
        {
            "strategist_feedback_input": {
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "hard_stop",
            },
            "shared_facts": {"pnl_pct": -1.2},
        },
    )

    payload = build_symbol_trade_summary(events_path, reports_root, "005930")
    memory = build_symbol_memory_payload(payload)

    assert memory["schema_version"] == "symbol_memory.v1"
    assert memory["trade_stats"]["trade_count"] == 1
    assert memory["playbook_stats"]["breakout"]["count"] == 1
    assert memory["pattern_stats"]["failed_entry_patterns"] == ["breakout"]
    assert memory["monitor_patterns"]["dominant_exit_failure_axis"] == "hard_stop"
    assert memory["bias_recommendation"]["avoid_playbook"] == "breakout"
    assert memory["bias_recommendation"]["risk_cap"] == "conservative"
