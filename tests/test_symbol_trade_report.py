from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.llm_artifacts import symbol_artifact_paths
from libs.reporting.symbol_trade_report import build_symbol_trade_summary
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


def test_symbol_trade_report_handles_no_history_symbol(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    events_path = tmp_path / "data" / "logs" / "events.jsonl"
    _write_jsonl(events_path, [])

    payload = build_symbol_trade_summary(events_path, reports_root, "000660")
    assert payload["summary"]["trade_count"] == 0
    assert payload["history_index"] == []
    assert payload["pattern_insights"]["risk_notes"]
