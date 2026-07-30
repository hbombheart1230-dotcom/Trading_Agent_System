# tests/test_event_logger.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.core.event_logger import EventLogger, new_run_id, resolve_event_log_path


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
    assert obj["ts_kst"] == "2026-02-07T09:00:00+09:00"
    assert obj["stage"] == "strategist_plan"
    assert obj["event"] == "decision"
    assert obj["event_name"] == "strategist_plan.decision"
    assert obj["level"] == "info"
    assert obj["trade_id"] == ""
    assert obj["session_id"] == ""
    assert obj["cycle_id"] == ""
    assert obj["agent"] == "strategist_plan"
    assert obj["phase"] == ""
    assert obj["symbol"] == ""
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

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["ts_kst"] == "2026-02-07T09:00:00+09:00"
    assert second["ts_kst"] == "2026-02-07T09:00:01+09:00"


def test_resolve_event_log_path_uses_pytest_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVENT_LOG_PATH", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_event_logger.py::test_dummy")
    path = resolve_event_log_path()
    assert path.name == "events.jsonl"
    assert "trading_agent_system_pytest" in str(path)


def test_resolve_event_log_path_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom_events.jsonl"
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_event_logger.py::test_dummy")
    monkeypatch.setenv("EVENT_LOG_PATH", str(custom))
    assert resolve_event_log_path() == custom


def test_event_logger_redirects_canonical_operator_log_during_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVENT_LOG_PATH", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_event_logger.py::test_dummy")

    logger = EventLogger(log_path=Path("data/logs/events.jsonl"))

    assert logger.log_path.name == "events.jsonl"
    assert "trading_agent_system_pytest" in str(logger.log_path)


def test_explicit_canonical_env_is_still_isolated_during_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_event_logger.py::test_dummy")
    monkeypatch.setenv("EVENT_LOG_PATH", "data/logs/events.jsonl")

    path = resolve_event_log_path()

    assert path.name == "events.jsonl"
    assert "trading_agent_system_pytest" in str(path)


def test_event_logger_keeps_explicit_tmp_log_during_pytest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("EVENT_LOG_PATH", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_event_logger.py::test_dummy")
    log_path = tmp_path / "data" / "logs" / "events.jsonl"

    logger = EventLogger(log_path=log_path)

    assert logger.log_path == log_path


def test_event_logger_compacts_large_candidate_ranking_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EVENT_LOG_PAYLOAD_MAX_BYTES", "30000")
    monkeypatch.setenv("EVENT_LOG_COMPACT_TOP_ITEMS", "3")
    log_path = tmp_path / "events.jsonl"
    logger = EventLogger(log_path=log_path)
    rows = [
        {
            "rank": index,
            "symbol": f"00{index:04d}",
            "score_total": 1.0 - index / 100.0,
            "confidence": 0.8,
            "risk_score": 0.2,
            "sources": ["theme", "volume", "news"],
            "source_scores": {"theme": 0.9, "volume": 0.8},
            "huge_unused_blob": "x" * 1000,
        }
        for index in range(1, 31)
    ]

    rec = logger.log(
        run_id=new_run_id(),
        stage="scanner",
        event="candidate_ranking_table",
        payload={
            "tie_break_rule": "score_total desc",
            "rows": rows,
            "scanner_intrinsic_control_top20": rows,
            "pre_strategist_full_universe_snapshot": {
                "schema_version": "q9_scanner_pre_strategist_universe.v1",
                "candidate_count": len(rows),
                "source_universe_top20": rows[:20],
                "intrinsic_ranked_top20": rows[:20],
            },
        },
        ts="2026-02-07T00:00:00+00:00",
    )

    payload = rec["payload"]
    assert payload["_event_log_compacted"] is True
    assert payload["rows_count"] == 30
    assert len(payload["rows"]) == 3
    assert payload["rows"][0]["symbol"] == "000001"
    assert "huge_unused_blob" not in payload["rows"][0]
    assert payload["scanner_intrinsic_control_top20_count"] == 30
    assert payload["pre_strategist_full_universe_snapshot"]["candidate_count"] == 30


def test_event_logger_keeps_small_payload_uncompacted(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    logger = EventLogger(log_path=log_path)

    rec = logger.log(
        run_id=new_run_id(),
        stage="monitor",
        event="state_transition",
        payload={"symbol": "005930", "from": "watch", "to": "hold"},
        ts="2026-02-07T00:00:00+00:00",
    )

    assert rec["payload"] == {"symbol": "005930", "from": "watch", "to": "hold"}
