import json
from pathlib import Path

from libs.reporting.event_log_reader import iter_jsonl_events


def test_iter_jsonl_events_filters_day_and_reuses_cache(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("EVENT_LOG_DAY_CACHE_DIR", str(cache_dir))
    events.write_text(
        "\n".join(
            [
                json.dumps({"ts": "2026-05-07T23:59:59+00:00", "payload": {"symbol": "OLD"}}),
                json.dumps({"ts": "2026-05-08T00:00:00+00:00", "payload": {"symbol": "AAA"}}),
                json.dumps({"ts": "2026-05-08T06:00:00+00:00", "payload": {"symbol": "BBB"}}),
                json.dumps({"ts": "2026-05-09T00:00:00+00:00", "payload": {"symbol": "NEXT"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    first = list(iter_jsonl_events(events, day="2026-05-08"))
    second = list(iter_jsonl_events(events, day="2026-05-08"))

    assert [row["payload"]["symbol"] for row in first] == ["AAA", "BBB"]
    assert [row["payload"]["symbol"] for row in second] == ["AAA", "BBB"]
    assert list(cache_dir.glob("events_2026-05-08_*.jsonl"))
    assert list(cache_dir.glob("events_2026-05-08_*.meta.json"))


def test_iter_jsonl_events_keeps_numeric_timestamp_rows_correct(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_DAY_CACHE_DIR", str(tmp_path / "cache"))
    events.write_text(
        json.dumps({"ts": 1700000000, "payload": {"symbol": "005930"}}) + "\n",
        encoding="utf-8",
    )

    rows = list(iter_jsonl_events(events, day="2023-11-14"))

    assert len(rows) == 1
    assert rows[0]["payload"]["symbol"] == "005930"


def test_iter_jsonl_events_appends_new_source_rows_to_day_cache(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("EVENT_LOG_DAY_CACHE_DIR", str(cache_dir))
    events.write_text(
        json.dumps({"ts": "2026-05-22T00:00:00+00:00", "payload": {"symbol": "AAA"}}) + "\n",
        encoding="utf-8",
    )

    first = list(iter_jsonl_events(events, day="2026-05-22"))
    with events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": "2026-05-21T23:59:59+00:00", "payload": {"symbol": "OLD"}}) + "\n")
        handle.write(json.dumps({"ts": "2026-05-22T00:01:00+00:00", "payload": {"symbol": "BBB"}}) + "\n")
    second = list(iter_jsonl_events(events, day="2026-05-22"))
    third = list(iter_jsonl_events(events, day="2026-05-22"))

    assert [row["payload"]["symbol"] for row in first] == ["AAA"]
    assert [row["payload"]["symbol"] for row in second] == ["AAA", "BBB"]
    assert [row["payload"]["symbol"] for row in third] == ["AAA", "BBB"]


def test_iter_jsonl_events_filters_timestamp_rows_for_evidence_ledger(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "evidence.jsonl"
    monkeypatch.setenv("EVENT_LOG_DAY_CACHE_DIR", str(tmp_path / "cache"))
    events.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-05-21T23:59:59+00:00", "payload": {"symbol": "OLD"}}),
                json.dumps({"timestamp": "2026-05-22T00:01:00+00:00", "payload": {"symbol": "NEW"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = list(iter_jsonl_events(events, day="2026-05-22"))

    assert [row["payload"]["symbol"] for row in rows] == ["NEW"]
