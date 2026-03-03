from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_live_session_summary import main as live_summary_main


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_live_summary_aggregates_window_metrics(tmp_path: Path, capsys) -> None:
    events = tmp_path / "events_live.jsonl"
    report_dir = tmp_path / "reports"
    now_epoch = 10_000

    rows = [
        # in-window strategist llm
        {
            "run_id": "r1",
            "ts": _iso(now_epoch - 100),
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": True, "intent_action": "BUY", "latency_ms": 1000},
        },
        {
            "run_id": "r2",
            "ts": _iso(now_epoch - 90),
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": False, "intent_action": "NOOP", "intent_reason": "strategist_error", "error_type": "ValueError"},
        },
        # in-window decisions
        {
            "run_id": "r1",
            "ts": _iso(now_epoch - 80),
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "BUY"}}, "trace": {"strategy": "OpenAIStrategist", "raw_intent": {}}},
        },
        {
            "run_id": "r3",
            "ts": _iso(now_epoch - 70),
            "stage": "decision",
            "event": "trace",
            "payload": {
                "decision_packet": {"intent": {"action": "SELL"}},
                "trace": {"strategy": "ExitPolicyStrategist", "raw_intent": {}},
            },
        },
        {
            "run_id": "r4",
            "ts": _iso(now_epoch - 60),
            "stage": "decision",
            "event": "trace",
            "payload": {
                "decision_packet": {"intent": {"action": "NOOP", "reason": "post_exit_cooldown"}},
                "trace": {"strategy": "CooldownStrategist", "raw_intent": {"reason": "post_exit_cooldown"}},
            },
        },
        # in-window verdicts
        {
            "run_id": "r4",
            "ts": _iso(now_epoch - 50),
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": False, "reason": "noop_intent_skipped"},
        },
        {
            "run_id": "r5",
            "ts": _iso(now_epoch - 40),
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": False, "reason": "insufficient_mock_cash"},
        },
        {
            "run_id": "r3",
            "ts": _iso(now_epoch - 30),
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": True},
        },
        # in-window executions
        {
            "run_id": "r3",
            "ts": _iso(now_epoch - 20),
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {"order": {"action": "SELL", "qty": 1, "price": 70000, "rationale": "exit_policy:take_profit"}},
        },
        {
            "run_id": "r1",
            "ts": _iso(now_epoch - 10),
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {"order": {"action": "BUY", "qty": 1, "price": 60000, "rationale": ""}},
        },
        # out-of-window row (must be excluded)
        {
            "run_id": "old",
            "ts": _iso(now_epoch - 4000),
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "BUY"}}, "trace": {"strategy": "OpenAIStrategist"}},
        },
    ]
    _write_jsonl(events, rows)

    rc = live_summary_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(report_dir),
            "--lookback-min",
            "30",
            "--now-epoch",
            str(now_epoch),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["events"]["window_total"] == 10
    assert obj["strategist_llm"]["total"] == 2
    assert obj["strategist_llm"]["error_total"] == 1
    assert abs(float(obj["strategist_llm"]["error_rate"]) - 0.5) < 1e-9
    assert obj["decision"]["action_counts"]["BUY"] == 1
    assert obj["decision"]["action_counts"]["SELL"] == 1
    assert obj["decision"]["action_counts"]["NOOP"] == 1
    assert obj["execution"]["blocked_total"] == 2
    assert obj["execution"]["executed_action_counts"]["SELL"] == 1
    assert obj["controls"]["cooldown_noop_total"] == 1
    assert obj["controls"]["exit_policy_sell_total"] == 1
    assert obj["controls"]["insufficient_mock_cash_block_total"] == 1

    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_live_summary_returns_2_when_log_path_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    rc = live_summary_main(["--event-log-path", str(missing), "--report-dir", str(tmp_path / "reports"), "--json"])
    assert rc == 2

