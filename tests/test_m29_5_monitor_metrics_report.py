from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_metrics_report import generate_metrics_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m29_5_monitor_agent_metrics_aggregates(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-21T00:00:00+00:00",
                "run_id": "r1",
                "stage": "monitor",
                "event": "summary",
                "payload": {
                    "has_intent": False,
                    "intent_count": 0,
                    "selected_symbol": "AAA",
                    "exit_policy_enabled": True,
                    "exit_evaluated": True,
                    "exit_triggered": True,
                    "exit_reason": "stop_loss",
                    "position_sizing_enabled": True,
                    "position_sizing_evaluated": True,
                    "position_sizing_qty": 0,
                    "position_sizing_reason": "computed_qty_zero",
                },
            },
            {
                "ts": "2026-02-21T00:00:01+00:00",
                "run_id": "r2",
                "stage": "monitor",
                "event": "summary",
                "payload": {
                    "has_intent": True,
                    "intent_count": 1,
                    "selected_symbol": "AAA",
                    "exit_policy_enabled": True,
                    "exit_evaluated": True,
                    "exit_triggered": False,
                    "exit_reason": "hold",
                    "position_sizing_enabled": True,
                    "position_sizing_evaluated": True,
                    "position_sizing_qty": 5,
                    "position_sizing_reason": "ok",
                },
            },
            {
                "ts": "2026-02-21T00:00:02+00:00",
                "run_id": "r3",
                "stage": "monitor",
                "event": "summary",
                "payload": {
                    "has_intent": True,
                    "intent_count": 1,
                    "selected_symbol": "BBB",
                    "exit_policy_enabled": False,
                    "exit_evaluated": False,
                    "exit_triggered": False,
                    "exit_reason": "",
                    "position_sizing_enabled": False,
                    "position_sizing_evaluated": False,
                    "position_sizing_qty": 1,
                    "position_sizing_reason": "disabled",
                },
            },
        ],
    )

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-21")
    data = json.loads(js.read_text(encoding="utf-8"))

    m = data["monitor_agent"]
    assert m["total"] == 3
    assert m["exit_policy_enabled_total"] == 2
    assert m["exit_evaluated_total"] == 2
    assert m["exit_trigger_total"] == 1
    assert m["exit_reason_total"]["stop_loss"] == 1
    assert m["exit_reason_total"]["hold"] == 1
    assert m["position_sizing_enabled_total"] == 2
    assert m["position_sizing_evaluated_total"] == 2
    assert m["position_sizing_computed_qty_sum"] == 6
    assert m["position_sizing_zero_qty_total"] == 1
    assert m["position_sizing_reason_total"]["computed_qty_zero"] == 1
    assert m["position_sizing_reason_total"]["ok"] == 1
    assert m["position_sizing_reason_total"]["disabled"] == 1


def test_m29_5_monitor_agent_metrics_empty_defaults(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")
    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-21")
    data = json.loads(js.read_text(encoding="utf-8"))

    m = data["monitor_agent"]
    assert m["total"] == 0
    assert m["exit_policy_enabled_total"] == 0
    assert m["exit_evaluated_total"] == 0
    assert m["exit_trigger_total"] == 0
    assert m["exit_reason_total"] == {}
    assert m["position_sizing_enabled_total"] == 0
    assert m["position_sizing_evaluated_total"] == 0
    assert m["position_sizing_computed_qty_sum"] == 0
    assert m["position_sizing_zero_qty_total"] == 0
    assert m["position_sizing_reason_total"] == {}
