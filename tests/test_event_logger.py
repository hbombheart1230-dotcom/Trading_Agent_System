# tests/test_event_logger.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.core.event_logger import EventLogger, new_run_id


def test_event_logger_writes_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "data" / "logs" / "events.jsonl"
    logger = EventLogger(log_path=log_path)

    run_id = new_run_id()
    rec = logger.log(
        run_id=run_id,
        stage="strategist_plan",
        event="decision",
        payload={"selected_category_minors": ["순위정보"], "tags": ["거래대금", "급증"]},
        ts="2026-02-07T00:00:00+00:00",  # deterministic for test
    )

    assert log_path.exists()

    # file has exactly 1 line
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    # line is valid json
    obj = json.loads(lines[0])

    # schema fields exist
    assert obj["run_id"] == run_id
    assert obj["ts"] == "2026-02-07T00:00:00+00:00"
    assert obj["stage"] == "strategist_plan"
    assert obj["event"] == "decision"
    assert isinstance(obj["payload"], dict)

    # returned record matches stored record
    assert rec == obj


def test_event_logger_appends_multiple_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    logger = EventLogger(log_path=log_path)

    run_id = new_run_id()
    logger.log(run_id=run_id, stage="node1", event="start", payload={"a": 1}, ts="2026-02-07T00:00:00+00:00")
    logger.log(run_id=run_id, stage="node1", event="end", payload={"b": 2}, ts="2026-02-07T00:00:01+00:00")

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
