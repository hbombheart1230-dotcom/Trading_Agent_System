from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from graphs.pipelines.m13_eod_report import run_m13_eod_report
from libs.runtime.market_hours import MarketHours
from scripts.run_decision_story_report import main as decision_story_main
from scripts.run_operator_daily_summary import main as operator_summary_main
from scripts.run_run_card_report import main as run_card_main

KST = timezone(timedelta(hours=9))


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_operator_daily_summary_script_generates_red_status(tmp_path: Path, capsys) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    metrics_dir = tmp_path / "metrics"
    m30_post = tmp_path / "m30_post"
    m30_go = tmp_path / "m30_go"
    m31_dir = tmp_path / "m31"
    out_dir = tmp_path / "operator_summary"

    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1}}, "trace": {"strategy": "RuleStrategist"}},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "MAX_NOTIONAL exceeded"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "error",
                "payload": {"reason": "duplicate_execution"},
            },
            {
                "run_id": "r2",
                "ts": f"{day}T01:10:00+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume"},
            },
        ],
    )

    _write_json(
        metrics_dir / f"metrics_{day}.json",
        {
            "execution": {"intents_created": 6, "intents_blocked": 4},
            "broker_api": {"api_429_rate": 0.10},
            "strategist_llm": {"success_rate": 0.80},
            "commander_resilience": {"total": 1},
        },
    )
    _write_json(
        m30_post / f"m30_post_golive_policy_{day}.json",
        {"escalation_level": "normal", "policy": {"manual_approval_only": False}},
    )
    _write_json(
        m30_go / f"m30_final_golive_signoff_{day}.json",
        {"approved": True, "go_live_decision": "approve_go_live"},
    )
    _write_json(
        m31_dir / f"m31_slo_incident_{day}.json",
        {"ok": True, "failure_total": 0},
    )

    rc = operator_summary_main(
        [
            "--event-log-path",
            str(events),
            "--metrics-report-dir",
            str(metrics_dir),
            "--m30-post-golive-dir",
            str(m30_post),
            "--m30-golive-dir",
            str(m30_go),
            "--m31-slo-incident-dir",
            str(m31_dir),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["executive_summary"]["system_status"] == "RED"
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Executive Summary" in md_body
    assert "System Health Status" in md_body
    assert "Trading Activity Summary" in md_body
    assert "Safety Guard Interventions" in md_body
    assert "Top Issues" in md_body
    assert "Recommended Operator Actions" in md_body


def test_decision_story_report_script_outputs_story_per_run(tmp_path: Path, capsys) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "decision_story"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "intent_action": "BUY", "intent_reason": "momentum_positive"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {
                        "intent": {"action": "BUY", "symbol": "005930", "qty": 3, "reason": "momentum_positive"},
                        "why": {
                            "technical": {"regime": "trend_up", "rsi14": 61},
                            "news": {"symbol_sentiment_score": 0.4},
                            "policy": {"max_risk": 0.7},
                        },
                    },
                    "trace": {"strategy": "RegimeMomentumV1", "rationale": "trend breakout"},
                },
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "MAX_NOTIONAL exceeded"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:03+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume"},
            },
        ],
    )

    rc = decision_story_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["story_total"] == 1
    md_path = Path(obj["report_md_path"])
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "Run r1" in md_body
    assert "execution_status: **BLOCKED**" in md_body
    assert "guard_intervention: MAX_NOTIONAL exceeded" in md_body


def test_run_card_report_script_outputs_cards(tmp_path: Path, capsys) -> None:
    day = "2026-03-06"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "run_cards"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "breakout"}}},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T01:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"broker_code": "0"}},
            },
            {
                "run_id": "r2",
                "ts": f"{day}T01:05:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "000660", "qty": 2, "reason": "signal"}}},
            },
            {
                "run_id": "r2",
                "ts": f"{day}T01:05:01+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "allowlist_blocked"},
            },
        ],
    )

    rc = run_card_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert obj["card_total"] == 2
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "Run: r1" in md_body
    assert "Status: EXECUTED_OK" in md_body
    assert "Run: r2" in md_body
    assert "Status: BLOCKED" in md_body


def test_m13_eod_report_auto_attaches_operator_visibility_bundle(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    day = "2026-02-13"
    epoch = int(datetime(2026, 2, 13, 6, 30, tzinfo=timezone.utc).timestamp())
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": epoch,
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            }
        ],
    )

    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    monkeypatch.setenv("REPORT_DIR", str(reports))

    called = {"n": 0}

    def fake_bundle(*, events_path: Path, report_root: Path, day: str | None = None):
        called["n"] += 1
        assert events_path == events
        assert report_root == reports
        return {"day": day, "operator_summary_md": "ok.md"}

    dt = datetime(2026, 2, 13, 15, 40, tzinfo=KST)
    out = run_m13_eod_report(
        {},
        dt=dt,
        market_hours=MarketHours(),
        generate_operator_reports=fake_bundle,
        grace_minutes=0,
    )

    assert out["eod_skipped"] is False
    assert called["n"] == 1
    assert out["daily_report"]["day"] == day
    assert out["daily_report"]["operator_visibility"]["day"] == day

