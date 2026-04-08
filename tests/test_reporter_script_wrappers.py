from __future__ import annotations

import json
from pathlib import Path

from libs.agent.reporter_outputs import ReporterOutput
import scripts.generate_daily_report as daily_script
import scripts.generate_metrics_report as metrics_script
from scripts.run_decision_story_report import main as decision_story_main
from scripts.run_operator_daily_summary import main as operator_summary_main
from scripts.run_run_card_report import main as run_card_main
from scripts.run_trade_explain_report import main as trade_explain_main


def _fake_output(mode: str, base_dir: Path, day: str = "2026-04-08") -> ReporterOutput:
    report_dir = base_dir / mode
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / f"{mode}_{day}.md"
    js_path = report_dir / f"{mode}_{day}.json"
    md_path.write_text(f"# {mode}\n", encoding="utf-8")
    js_path.write_text(json.dumps({"day": day, "mode": mode}, ensure_ascii=False), encoding="utf-8")
    return ReporterOutput(
        report_type=mode,
        output_paths={"md": str(md_path), "json": str(js_path)},
        generated_at=f"{day}T00:00:00+00:00",
        data_freshness={"freshness_status": "fresh"},
        route_provenance={"route_source": "canonical_commander_preferred"},
        summary_metadata={"day": day},
        success=True,
        warnings=[],
        payload={
            "day": day,
            "report_md_path": str(md_path),
            "report_json_path": str(js_path),
            "data_freshness": {"freshness_status": "fresh"},
            "route_provenance": {"route_source": "canonical_commander_preferred"},
        },
    )


def test_generate_daily_report_main_delegates_to_reporter(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {}

    def _fake_generate(self, **kwargs):
        called.update(kwargs)
        return _fake_output("daily_report", tmp_path)

    monkeypatch.setenv("EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("REPORT_DAY", "2026-04-08")
    monkeypatch.setattr(daily_script.Reporter, "generate_daily_report", _fake_generate)

    daily_script.main()

    out = capsys.readouterr().out
    assert "Wrote:" in out
    assert str(tmp_path / "events.jsonl") in str(called["event_log_path"])
    assert Path(called["reports_root"]) == tmp_path / "reports"
    assert called["day"] == "2026-04-08"


def test_generate_metrics_report_main_delegates_to_reporter(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {}

    def _fake_generate(self, **kwargs):
        called.update(kwargs)
        return _fake_output("metrics_report", tmp_path)

    monkeypatch.setenv("EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("METRICS_DAY", "2026-04-08")
    monkeypatch.setattr(metrics_script.Reporter, "generate_metrics_report", _fake_generate)

    metrics_script.main()

    out = capsys.readouterr().out
    assert "Wrote:" in out
    assert str(tmp_path / "events.jsonl") in str(called["event_log_path"])
    assert Path(called["report_dir"]) == tmp_path / "reports" / "metrics"
    assert called["day"] == "2026-04-08"


def test_run_trade_explain_script_delegates_to_reporter(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {}

    def _fake_generate(self, **kwargs):
        called.update(kwargs)
        return _fake_output("trade_explain", tmp_path)

    monkeypatch.setattr("scripts.run_trade_explain_report.Reporter.generate_trade_explain", _fake_generate)

    rc = trade_explain_main(
        [
            "--event-log-path",
            str(tmp_path / "events.jsonl"),
            "--report-dir",
            str(tmp_path / "reports" / "dev" / "analysis" / "trade_explain"),
            "--day",
            "2026-04-08",
            "--json",
        ]
    )

    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert called["day"] == "2026-04-08"
    assert obj["route_provenance"]["route_source"] == "canonical_commander_preferred"


def test_run_operator_summary_script_delegates_to_reporter(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {}

    def _fake_generate(self, **kwargs):
        called.update(kwargs)
        return _fake_output("operator_summary", tmp_path)

    monkeypatch.setattr("scripts.run_operator_daily_summary.Reporter.generate_operator_summary", _fake_generate)

    rc = operator_summary_main(
        [
            "--event-log-path",
            str(tmp_path / "events.jsonl"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--day",
            "2026-04-08",
            "--json",
        ]
    )

    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert called["day"] == "2026-04-08"
    assert obj["data_freshness"]["freshness_status"] == "fresh"


def test_run_cards_script_delegates_to_reporter(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {}

    def _fake_generate(self, **kwargs):
        called.update(kwargs)
        return _fake_output("run_cards", tmp_path)

    monkeypatch.setattr("scripts.run_run_card_report.Reporter.generate_run_cards", _fake_generate)

    rc = run_card_main(
        [
            "--event-log-path",
            str(tmp_path / "events.jsonl"),
            "--report-dir",
            str(tmp_path / "run_cards"),
            "--day",
            "2026-04-08",
            "--json",
        ]
    )

    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert called["day"] == "2026-04-08"
    assert obj["route_provenance"]["route_source"] == "canonical_commander_preferred"


def test_decision_story_script_delegates_to_reporter(monkeypatch, tmp_path: Path, capsys) -> None:
    called = {}

    def _fake_generate(self, **kwargs):
        called.update(kwargs)
        return _fake_output("decision_story", tmp_path)

    monkeypatch.setattr("scripts.run_decision_story_report.Reporter.generate_decision_story", _fake_generate)

    rc = decision_story_main(
        [
            "--event-log-path",
            str(tmp_path / "events.jsonl"),
            "--report-dir",
            str(tmp_path / "decision_story"),
            "--day",
            "2026-04-08",
            "--json",
        ]
    )

    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert called["day"] == "2026-04-08"
    assert obj["data_freshness"]["freshness_status"] == "fresh"
