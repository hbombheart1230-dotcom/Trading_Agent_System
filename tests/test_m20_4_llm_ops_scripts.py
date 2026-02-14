from __future__ import annotations

import json
from pathlib import Path

import libs.ai.providers.openai_provider as prov
from scripts.query_strategist_llm_events import main as query_main
from scripts.smoke_m20_llm import main as smoke_main


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
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "0")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_VERSION", "pv-smoke")
    monkeypatch.setenv("AI_STRATEGIST_SCHEMA_VERSION", "intent.v1-smoke")
    monkeypatch.setenv("AI_STRATEGIST_PROMPT_COST_PER_1K_USD", "0.003")
    monkeypatch.setenv("AI_STRATEGIST_COMPLETION_COST_PER_1K_USD", "0.015")
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
    assert "\"prompt_version\": \"pv-smoke\"" in out
    assert "\"schema_version\": \"intent.v1-smoke\"" in out
    assert "\"prompt_tokens\": 90" in out
    assert "\"completion_tokens\": 60" in out
    assert "\"total_tokens\": 150" in out
    assert "\"estimated_cost_usd\":" in out


def test_m20_4_smoke_require_llm_event_fails_when_missing(monkeypatch, tmp_path: Path):
    events = tmp_path / "events.jsonl"
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "rule")
    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    rc = smoke_main(["--event-log-path", str(events), "--require-llm-event"])
    assert rc == 3


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
