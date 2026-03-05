from __future__ import annotations

import json
from pathlib import Path

from scripts.query_trade_reason_chain import main as reason_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_query_trade_reason_chain_extracts_buy_and_sell_with_reason(tmp_path: Path, capsys) -> None:
    events = tmp_path / "events.jsonl"
    rows = [
        {
            "run_id": "r-buy",
            "ts": "2026-03-05T01:00:00+00:00",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {
                "provider": "openai",
                "model": "minimax/minimax-m2.5",
                "ok": True,
                "intent_action": "BUY",
                "intent_reason": "",
                "intent_rationale": "llm-breakout",
                "latency_ms": 1234,
            },
        },
        {
            "run_id": "r-buy",
            "ts": "2026-03-05T01:00:01+00:00",
            "stage": "decision",
            "event": "trace",
            "payload": {
                "decision_packet": {"intent": {"action": "BUY", "reason": ""}},
                "trace": {"strategy": "OpenAIStrategist", "rationale": "breakout"},
            },
        },
        {
            "run_id": "r-buy",
            "ts": "2026-03-05T01:00:02+00:00",
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": True},
        },
        {
            "run_id": "r-buy",
            "ts": "2026-03-05T01:00:03+00:00",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "reason": "Allowed",
                "order": {"action": "BUY", "symbol": "005930", "qty": 3, "price": 70000, "order_type": "market"},
                "payload": {"broker_code": "0", "order_id": "A1", "broker_message": "ok"},
            },
        },
        {
            "run_id": "r-sell",
            "ts": "2026-03-05T01:02:01+00:00",
            "stage": "decision",
            "event": "trace",
            "payload": {
                "decision_packet": {"intent": {"action": "SELL", "reason": ""}},
                "trace": {"strategy": "ExitPolicyStrategist", "rationale": "exit_policy:max_hold"},
            },
        },
        {
            "run_id": "r-sell",
            "ts": "2026-03-05T01:02:02+00:00",
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": True},
        },
        {
            "run_id": "r-sell",
            "ts": "2026-03-05T01:02:03+00:00",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "reason": "Allowed",
                "order": {"action": "SELL", "symbol": "005930", "qty": 3, "price": 70200, "order_type": "market"},
                "payload": {"broker_code": "0", "order_id": "B1", "broker_message": "ok"},
            },
        },
    ]
    _write_jsonl(events, rows)

    rc = reason_main(["--path", str(events), "--json", "--limit", "10"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert isinstance(obj, list)
    assert len(obj) == 2

    buy = obj[0]
    sell = obj[1]

    assert buy["action"] == "BUY"
    assert buy["decision_strategy"] == "OpenAIStrategist"
    assert buy["decision_rationale"] == "breakout"
    assert buy["llm_intent_rationale"] == "llm-breakout"
    assert buy["llm_model"] == "minimax/minimax-m2.5"
    assert buy["broker_code"] == "0"
    assert buy["order_id"] == "A1"

    assert sell["action"] == "SELL"
    assert sell["decision_strategy"] == "ExitPolicyStrategist"
    assert sell["decision_rationale"] == "exit_policy:max_hold"
    assert sell["llm_model"] == ""
    assert sell["broker_code"] == "0"
    assert sell["order_id"] == "B1"


def test_query_trade_reason_chain_only_broker_success_filter(tmp_path: Path, capsys) -> None:
    events = tmp_path / "events.jsonl"
    rows = [
        {
            "run_id": "r-fail",
            "ts": "2026-03-05T01:03:00+00:00",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "BUY"}}, "trace": {"strategy": "OpenAIStrategist"}},
        },
        {
            "run_id": "r-fail",
            "ts": "2026-03-05T01:03:01+00:00",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "reason": "Allowed",
                "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_type": "market"},
                "payload": {"broker_code": "20", "broker_message": "rejected"},
            },
        },
    ]
    _write_jsonl(events, rows)

    rc = reason_main(["--path", str(events), "--json", "--only-broker-success"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj == []


def test_query_trade_reason_chain_falls_back_to_llm_rationale(tmp_path: Path, capsys) -> None:
    events = tmp_path / "events.jsonl"
    rows = [
        {
            "run_id": "r-fallback",
            "ts": "2026-03-05T01:00:00+00:00",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {
                "provider": "openai",
                "model": "minimax/minimax-m2.5",
                "ok": True,
                "intent_action": "BUY",
                "intent_reason": "",
                "intent_rationale": "llm-fallback-reason",
            },
        },
        {
            "run_id": "r-fallback",
            "ts": "2026-03-05T01:00:01+00:00",
            "stage": "decision",
            "event": "trace",
            "payload": {
                "decision_packet": {"intent": {"action": "BUY", "reason": "", "rationale": ""}},
                "trace": {"strategy": "OpenAIStrategist", "rationale": ""},
            },
        },
        {
            "run_id": "r-fallback",
            "ts": "2026-03-05T01:00:03+00:00",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "reason": "Allowed",
                "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_type": "market"},
                "payload": {"broker_code": "0", "order_id": "X1", "broker_message": "ok"},
            },
        },
    ]
    _write_jsonl(events, rows)

    rc = reason_main(["--path", str(events), "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert len(obj) == 1
    assert obj[0]["decision_rationale"] == "llm-fallback-reason"
    assert obj[0]["llm_intent_rationale"] == "llm-fallback-reason"
