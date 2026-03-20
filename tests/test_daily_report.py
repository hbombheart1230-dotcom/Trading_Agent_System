from pathlib import Path
import json
from libs.reporting.llm_artifacts import daily_artifact_paths
from scripts.generate_daily_report import generate_daily_report


def test_daily_artifact_paths_use_single_canonical_root(tmp_path: Path) -> None:
    paths = daily_artifact_paths(tmp_path / "reports", "2026-03-20")
    assert paths["root_dir"] == tmp_path / "reports" / "daily" / "2026-03-20"
    assert paths["daily_report_json"] == tmp_path / "reports" / "daily" / "2026-03-20" / "daily_report.json"
    assert paths["operator_summary_json"] == tmp_path / "reports" / "daily" / "2026-03-20" / "operator_summary.json"


def test_generate_daily_report(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join([
            json.dumps({"ts": 1700000000, "run_id": "r1", "stage": "decision", "event": "trace", "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930"}}}}),
            json.dumps({"ts": 1700000001, "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}),
        ]) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    lifecycle = out_dir / "trades" / "2023-11-14" / "TRD_20231114_005930_01" / "lifecycle" / "trade_lifecycle.json"
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.write_text(
        json.dumps(
            {
                "trade_id": "TRD_20231114_005930_01",
                "symbol": "005930",
                "day": "2023-11-14",
                "status": "closed",
                "entry": {"run_id": "r1", "ts": "2023-11-14T00:00:00+00:00", "price": 100.0, "strategist_context": {"playbook": "pullback"}},
                "exit": {"run_id": "r2", "ts": "2023-11-14T00:05:00+00:00", "price": 103.0},
                "summary": {"entry_reason_human": "눌림목 이후 재상승 진입", "exit_reason_human": "목표 수익 실현"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # 1700000000 is 2023-11-14 in UTC
    md, js = generate_daily_report(events, out_dir, day="2023-11-14")
    assert md.exists() and js.exists()
    assert md == out_dir / "daily" / "2023-11-14" / "daily_report.md"
    assert js == out_dir / "daily" / "2023-11-14" / "daily_report.json"
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["approvals"] == 1
    assert (out_dir / "daily" / "2023-11-14" / "daily_report.json").exists()
    assert (out_dir / "daily" / "2023-11-14" / "daily_report.md").exists()
    assert (out_dir / "daily" / "2023-11-14" / "trade_index.json").exists()
    assert (out_dir / "symbols" / "005930" / "symbol_trade_report.json").exists()
    assert not (out_dir / "daily_2023-11-14.json").exists()
    assert not (out_dir / "daily_2023-11-14.md").exists()
    assert not (out_dir / "daily" / "daily_2023-11-14.json").exists()
    assert not (out_dir / "daily" / "daily_2023-11-14.md").exists()
