from pathlib import Path
import json
from libs.reporting.llm_artifacts import daily_artifact_paths
from libs.reporting.daily_report import generate_daily_report as compat_generate_daily_report
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


def test_compat_daily_report_delegates_to_canonical_generator(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join([
            json.dumps({"ts": "2026-03-23T06:24:32+00:00", "run_id": "r1", "stage": "strategist", "event": "summary", "payload": {}}),
            json.dumps({"ts": "2026-03-23T06:25:32+00:00", "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}),
        ]) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    md, js = compat_generate_daily_report(events, out_dir, day="2026-03-23")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert md == out_dir / "daily" / "2026-03-23" / "daily_report.md"
    assert data["events"] == 2
    assert data["approvals"] == 1
    assert "stage_counts" in data


def test_generate_daily_report_uses_lifecycle_bundle_for_trade_index(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": "2026-03-23T06:24:32+00:00", "run_id": "r1", "stage": "monitor", "event": "summary", "payload": {"symbol": "005930"}}) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    bundle = out_dir / "trades" / "2026-03-23" / "TRD_20260323_005930_01" / "lifecycle_bundle.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "lifecycle_bundle.v1",
                "day": "2026-03-23",
                "trade_id": "TRD_20260323_005930_01",
                "symbol": "005930",
                "trade_lifecycle_status": "closed",
                "lifecycle": {
                    "entry": {"run_id": "r1", "ts": "2026-03-23T06:20:00+00:00", "price": 100.0, "reason_human": "entry reason"},
                    "exit": {"run_id": "r2", "ts": "2026-03-23T06:30:00+00:00", "price": 103.0, "reason_human": "exit reason"},
                },
                "trade_outcome": {"exit_reason": "exit reason"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _md, js = generate_daily_report(events, out_dir, day="2026-03-23")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["trade_index"]
    assert data["trade_index"][0]["trade_id"] == "TRD_20260323_005930_01"
    assert data["symbols_observed"] == ["005930"]
