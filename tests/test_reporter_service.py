from __future__ import annotations

import json
from pathlib import Path

from libs.agent.reporter import Reporter
from libs.agent.reporter_inputs import ReporterInput
from libs.agent.reporter_outputs import ReporterOutput
from libs.reporting.trade_explain import OFFICIAL_TRADE_EXPLAIN_RELATIVE_DIR


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_commander_artifact(reports_root: Path, day: str, run_id: str, payload: dict) -> None:
    commander_path = reports_root / "canonical" / day / run_id / "commander.json"
    commander_path.parent.mkdir(parents=True, exist_ok=True)
    commander_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_reporter_service_smoke_generates_core_reports(tmp_path: Path) -> None:
    day = "2026-04-08"
    events = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {
                        "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "entry_signal"}
                    },
                    "trace": {"strategy": "RuleStrategist", "rationale": "entry_signal"},
                },
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "commander_router",
                "event": "route_selected",
                "payload": {"route_selected": "full_cycle", "strategy_generation_mode": "live_llm"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:03+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 100}},
            },
        ],
    )
    _write_commander_artifact(
        reports_root,
        day,
        "r1",
        {
            "route_selected": "cached_strategist",
            "strategy_generation_mode": "cached",
            "strategist_call_decision": "reuse",
        },
    )

    reporter = Reporter()
    metrics = reporter.generate_metrics_report(event_log_path=events, report_dir=reports_root / "metrics", day=day)
    daily = reporter.generate_daily_report(event_log_path=events, reports_root=reports_root, day=day)
    operator_summary = reporter.generate_operator_summary(event_log_path=events, report_dir=reports_root, day=day)
    trade_explain = reporter.generate_trade_explain(event_log_path=events, reports_root=reports_root, day=day)
    run_cards = reporter.generate_run_cards(event_log_path=events, report_dir=reports_root / "run_cards", day=day, trade_only=False)
    decision_story = reporter.generate_decision_story(event_log_path=events, report_dir=reports_root / "decision_story", day=day, trade_only=False)

    assert isinstance(metrics, ReporterOutput)
    assert isinstance(daily, ReporterOutput)
    assert isinstance(operator_summary, ReporterOutput)
    assert isinstance(trade_explain, ReporterOutput)
    assert isinstance(run_cards, ReporterOutput)
    assert isinstance(decision_story, ReporterOutput)

    generated = {
        "metrics": metrics["payload"],
        "daily": daily["payload"],
        "operator_summary": operator_summary["payload"],
        "trade_explain": trade_explain["payload"],
        "run_cards": run_cards["payload"],
        "decision_story": decision_story["payload"],
    }

    for name, payload in generated.items():
        assert isinstance(payload.get("data_freshness"), dict), name
        assert isinstance(payload.get("route_provenance"), dict), name
        assert payload["route_provenance"]["route_source"] == "canonical_commander_preferred", name

    assert Path(metrics["report_json_path"]).exists()
    assert Path(daily["report_json_path"]).exists()
    assert Path(operator_summary["report_json_path"]).exists()
    assert Path(trade_explain["report_json_path"]).exists()
    assert Path(run_cards["report_md_path"]).exists()
    assert Path(decision_story["report_md_path"]).exists()
    assert Path(trade_explain["report_json_path"]) == reports_root / OFFICIAL_TRADE_EXPLAIN_RELATIVE_DIR / f"trade_explain_{day}.json"
    assert generated["trade_explain"]["output_path_policy"]["path_status"] == "official"


def test_reporter_service_run_dispatch_supports_trade_explain_mode(tmp_path: Path) -> None:
    day = "2026-04-08"
    events = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1, "price": 100}},
            }
        ],
    )

    result = Reporter().run(
        mode="trade_explain",
        event_log_path=events,
        reports_root=reports_root,
        day=day,
    )

    assert isinstance(result, ReporterOutput)
    assert result["mode"] == "trade_explain"
    assert Path(result["report_json_path"]).exists()
    assert result["payload"]["output_path_policy"]["path_status"] == "official"
    assert result["payload"]["data_freshness"]["freshness_status"] == "fresh"


def test_reporter_input_and_output_contract_builders_smoke() -> None:
    reporter_input = ReporterInput(
        day="2026-04-08",
        reports_root=Path("reports"),
        canonical_report_root=Path("reports"),
        source_run_count=12,
        latest_run_id="r1",
        latest_run_ts="2026-04-08T01:00:00+00:00",
        route_summary={"route_selected_total": {"full_cycle": 3}},
        data_freshness={"freshness_status": "fresh"},
        available_surfaces=["json", "markdown"],
        generation_mode="deterministic",
        flags={"mode": "daily_report"},
    )
    reporter_output = ReporterOutput(
        report_type="daily_report",
        output_paths={
            "json": "reports/operator_summary/daily/2026-04-08/daily_report.json",
            "md": "reports/operator_summary/daily/2026-04-08/daily_report.md",
        },
        generated_at="2026-04-08T01:02:00+00:00",
        data_freshness={"freshness_status": "fresh"},
        route_provenance={"route_source": "canonical_commander_preferred"},
        summary_metadata={"day": "2026-04-08", "reporter_input": reporter_input.to_dict()},
        success=True,
        warnings=[],
        payload={"day": "2026-04-08"},
    )

    input_dict = reporter_input.to_dict()
    output_dict = reporter_output.to_dict()

    assert input_dict["day"] == "2026-04-08"
    assert input_dict["source_run_count"] == 12
    assert input_dict["available_surfaces"] == ["json", "markdown"]
    assert output_dict["report_type"] == "daily_report"
    assert output_dict["data_freshness"]["freshness_status"] == "fresh"
    assert output_dict["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert output_dict["summary_metadata"]["reporter_input"]["day"] == "2026-04-08"


def test_reporter_service_daily_operator_trade_explain_return_contracts(tmp_path: Path) -> None:
    day = "2026-04-08"
    events = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 100}},
            }
        ],
    )

    reporter = Reporter()
    daily = reporter.generate_daily_report(event_log_path=events, reports_root=reports_root, day=day)
    operator_summary = reporter.generate_operator_summary(event_log_path=events, report_dir=reports_root, day=day)
    trade_explain = reporter.generate_trade_explain(event_log_path=events, reports_root=reports_root, day=day)

    for result in (daily, operator_summary, trade_explain):
        assert isinstance(result, ReporterOutput)
        assert result.success is True
        assert "reporter_input" in result.summary_metadata
        assert result.summary_metadata["reporter_input"]["day"] == day
        packet = result.strategist_feedback_packet
        assert isinstance(packet, dict)
        assert packet["feedback_mode"] == "deterministic"
        assert "route_analysis" in packet
        assert "recommendation" in packet
