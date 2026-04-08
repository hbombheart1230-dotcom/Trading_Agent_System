from __future__ import annotations

import json
from pathlib import Path

import pytest
import libs.ai.providers.openai_provider as prov
from scripts.query_strategist_llm_events import main as query_main
from scripts.smoke_m20_llm import main as smoke_main


@pytest.fixture(autouse=True)
def _disable_strategy_v1(monkeypatch):
    monkeypatch.setenv("USE_STRATEGY_V1", "false")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m20_4_smoke_show_llm_event_in_openai_mode(monkeypatch, tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")
    monkeypatch.setenv("EVENT_LOG_PATH", str(events))

    def fake_post_json(url, headers, payload, timeout=15.0):  # type: ignore[no-untyped-def]
        return {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "usage": {"prompt_tokens": 90, "completion_tokens": 60, "total_tokens": 150},
            "meta": {"provider": "fake"},
        }

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    rc = smoke_main(
        [
            "--provider",
            "openai",
            "--event-log-path",
            str(events),
            "--show-llm-event",
            "--require-llm-event",
            "--require-openai",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "llm_event=" in out
    assert "\"attempts\":" in out
    assert "\"latency_ms\":" in out
    assert f"\"prompt_version\": \"{prov.DEFAULT_PROMPT_VERSION}\"" in out
    assert f"\"schema_version\": \"{prov.DEFAULT_SCHEMA_VERSION}\"" in out
    assert "\"prompt_tokens\": 90" in out
    assert "\"completion_tokens\": 60" in out
    assert "\"total_tokens\": 150" in out
    assert "\"estimated_cost_usd\": null" in out


def test_m20_4_smoke_require_llm_event_succeeds_with_blocked_llm_event(monkeypatch, tmp_path: Path):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "rule")
    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    rc = smoke_main(["--event-log-path", str(events), "--require-llm-event"])
    assert rc == 0


def test_m20_4_query_script_filters_failures_json(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-14T00:00:00+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "intent_action": "BUY", "attempts": 1},
            },
            {
                "run_id": "r2",
                "ts": "2026-02-14T00:01:00+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": False, "intent_action": "NOOP", "error_type": "TimeoutError"},
            },
            {
                "run_id": "r3",
                "ts": "2026-02-14T00:02:00+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {},
            },
        ],
    )

    rc = query_main(["--path", str(events), "--only-failures", "--json"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    rows = json.loads(out)
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "r2"
    assert rows[0]["payload"]["ok"] is False


def test_m20_4_query_script_missing_path_returns_error(tmp_path: Path):
    missing = tmp_path / "missing.jsonl"
    rc = query_main(["--path", str(missing)])
    assert rc == 2


def test_m20_4_query_script_human_includes_token_and_cost_fields(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-14T00:00:00+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {
                    "ok": True,
                    "intent_action": "BUY",
                    "prompt_tokens": 111,
                    "completion_tokens": 22,
                    "total_tokens": 133,
                    "estimated_cost_usd": 0.00123,
                },
            }
        ],
    )

    rc = query_main(["--path", str(events), "--limit", "1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "prompt_tokens=111" in out
    assert "completion_tokens=22" in out
    assert "total_tokens=133" in out
    assert "estimated_cost_usd=0.00123" in out
