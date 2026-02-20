from pathlib import Path
import json

from scripts.generate_metrics_report import generate_metrics_report


def test_generate_metrics_report_aggregates_core_metrics(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": 1700000000,
                        "run_id": "r1",
                        "stage": "decision",
                        "event": "trace",
                        "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000001,
                        "run_id": "r1",
                        "stage": "decision",
                        "event": "trace",
                        "payload": {"decision_packet": {"intent": {"action": "NOOP"}}},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000002,
                        "run_id": "r1",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": True, "reason": "Allowed"},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000003,
                        "run_id": "r2",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": False, "reason": "Symbol blocked"},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000000,
                        "run_id": "r3",
                        "stage": "execute_from_packet",
                        "event": "start",
                        "payload": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000004,
                        "run_id": "r3",
                        "stage": "execute_from_packet",
                        "event": "execution",
                        "payload": {"allowed": True},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000005,
                        "run_id": "r3",
                        "stage": "execute_from_packet",
                        "event": "end",
                        "payload": {"ok": True},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000010,
                        "run_id": "r4",
                        "stage": "execute_from_packet",
                        "event": "start",
                        "payload": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000014,
                        "run_id": "r4",
                        "stage": "execute_from_packet",
                        "event": "error",
                        "payload": {"api_id": "kt10000", "error": "timeout"},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000020,
                        "run_id": "r5",
                        "stage": "strategist_llm",
                        "event": "result",
                        "payload": {
                            "ok": True,
                            "latency_ms": 120,
                            "attempts": 1,
                            "intent_action": "BUY",
                            "prompt_tokens": 100,
                            "completion_tokens": 40,
                            "total_tokens": 140,
                            "estimated_cost_usd": 0.0009,
                            "prompt_version": "pv-1",
                            "schema_version": "intent.v1",
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000021,
                        "run_id": "r6",
                        "stage": "strategist_llm",
                        "event": "result",
                        "payload": {
                            "ok": False,
                            "latency_ms": 350,
                            "attempts": 2,
                            "intent_action": "NOOP",
                            "error_type": "TimeoutError",
                            "prompt_tokens": 150,
                            "completion_tokens": 60,
                            "total_tokens": 210,
                            "estimated_cost_usd": 0.00135,
                            "prompt_version": "pv-1",
                            "schema_version": "intent.v1",
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000022,
                        "run_id": "r7",
                        "stage": "strategist_llm",
                        "event": "result",
                        "payload": {
                            "ok": False,
                            "intent_action": "NOOP",
                            "error_type": "CircuitOpen",
                            "intent_reason": "circuit_open",
                            "circuit_state": "open",
                            "circuit_fail_count": 2,
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000023,
                        "run_id": "r8",
                        "stage": "skill_hydration",
                        "event": "summary",
                        "payload": {
                            "used_runner": True,
                            "runner_source": "state.skill_runner",
                            "attempted": {"market.quote": 3, "account.orders": 1, "order.status": 1},
                            "ready": {"market.quote": 3, "account.orders": 1, "order.status": 1},
                            "errors_total": 0,
                            "errors": [],
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000024,
                        "run_id": "r9",
                        "stage": "skill_hydration",
                        "event": "summary",
                        "payload": {
                            "used_runner": True,
                            "runner_source": "auto.composite_skill_runner",
                            "attempted": {"market.quote": 3, "account.orders": 1, "order.status": 1},
                            "ready": {"market.quote": 0, "account.orders": 0, "order.status": 0},
                            "errors_total": 5,
                            "errors": [
                                "market.quote(005930):error:TimeoutError",
                                "market.quote(000660):error:TimeoutError",
                                "market.quote(035420):error:TimeoutError",
                                "account.orders:ask:account required",
                                "order.status:error:TimeoutError",
                            ],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    md, js = generate_metrics_report(events, out_dir, day="2023-11-14")
    assert md.exists() and js.exists()

    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["schema_version"] == "metrics.v1"
    assert data["intents_created_total"] == 1
    assert data["intents_approved_total"] == 1
    assert data["intents_blocked_total"] == 1
    assert data["intents_executed_total"] == 1
    assert data["intents_blocked_by_reason"]["Symbol blocked"] == 1
    assert data["execution"]["intents_created"] == 1
    assert data["execution"]["intents_approved"] == 1
    assert data["execution"]["intents_blocked"] == 1
    assert data["execution"]["intents_executed"] == 1
    assert data["execution"]["blocked_reason_topN"][0]["reason"] == "Symbol blocked"
    assert data["execution"]["blocked_reason_topN"][0]["count"] == 1
    assert data["execution_latency_seconds"]["count"] == 2.0
    assert abs(float(data["execution_latency_seconds"]["avg"]) - 4.5) < 1e-9
    assert data["api_error_total_by_api_id"]["kt10000"] == 1
    assert data["broker_api"]["api_error_total_by_api_id"]["kt10000"] == 1
    assert data["broker_api"]["api_429_total"] == 0
    assert data["broker_api"]["api_429_rate"] == 0.0
    assert data["strategist_llm"]["total"] == 3
    assert data["strategist_llm"]["ok_total"] == 1
    assert data["strategist_llm"]["fail_total"] == 2
    assert abs(float(data["strategist_llm"]["success_rate"]) - (1.0 / 3.0)) < 1e-9
    assert data["strategist_llm"]["circuit_open_total"] == 1
    assert abs(float(data["strategist_llm"]["circuit_open_rate"]) - (1.0 / 3.0)) < 1e-9
    assert data["strategist_llm"]["circuit_state_total"]["open"] == 1
    assert data["strategist_llm"]["latency_ms"]["count"] == 2.0
    assert abs(float(data["strategist_llm"]["latency_ms"]["avg"]) - 235.0) < 1e-9
    assert data["strategist_llm"]["attempts"]["count"] == 2.0
    assert data["strategist_llm"]["error_type_total"]["TimeoutError"] == 1
    assert data["strategist_llm"]["error_type_total"]["CircuitOpen"] == 1
    assert data["strategist_llm"]["prompt_version_total"]["pv-1"] == 2
    assert data["strategist_llm"]["prompt_version_total"]["unknown"] == 1
    assert data["strategist_llm"]["schema_version_total"]["intent.v1"] == 2
    assert data["strategist_llm"]["schema_version_total"]["unknown"] == 1
    assert data["strategist_llm"]["token_usage"]["prompt_tokens_total"] == 250
    assert data["strategist_llm"]["token_usage"]["completion_tokens_total"] == 100
    assert data["strategist_llm"]["token_usage"]["total_tokens_total"] == 350
    assert abs(float(data["strategist_llm"]["token_usage"]["estimated_cost_usd_total"]) - 0.00225) < 1e-12
    assert data["skill_hydration"]["total"] == 2
    assert data["skill_hydration"]["used_runner_total"] == 2
    assert data["skill_hydration"]["fallback_hint_total"] == 1
    assert abs(float(data["skill_hydration"]["fallback_hint_rate"]) - 0.5) < 1e-12
    assert data["skill_hydration"]["errors_total_sum"] == 5
    assert data["skill_hydration"]["runner_source_total"]["state.skill_runner"] == 1
    assert data["skill_hydration"]["runner_source_total"]["auto.composite_skill_runner"] == 1
    assert data["skill_hydration"]["attempted_total_by_skill"]["market.quote"] == 6
    assert data["skill_hydration"]["ready_total_by_skill"]["market.quote"] == 3
    assert data["skill_hydration"]["errors_total_by_skill"]["market.quote"] == 3
    assert data["skill_hydration"]["errors_total_by_skill"]["account.orders"] == 1
    assert data["skill_hydration"]["errors_total_by_skill"]["order.status"] == 1


def test_generate_metrics_report_supports_iso_ts_and_latest_day(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-13T23:59:59+00:00",
                        "run_id": "old",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": False, "reason": "old-day"},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-14T10:00:00+00:00",
                        "run_id": "new",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": True, "reason": "Allowed"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day=None)
    data = json.loads(js.read_text(encoding="utf-8"))

    assert data["day"] == "2026-02-14"
    assert data["intents_approved_total"] == 1
    assert data["intents_blocked_total"] == 0


def test_generate_metrics_report_empty_has_llm_summary_keys(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-14")
    data = json.loads(js.read_text(encoding="utf-8"))

    assert data["schema_version"] == "metrics.v1"
    assert data["events"] == 0
    assert data["strategist_llm"]["total"] == 0
    assert data["strategist_llm"]["ok_total"] == 0
    assert data["strategist_llm"]["fail_total"] == 0
    assert data["strategist_llm"]["success_rate"] == 0.0
    assert data["strategist_llm"]["circuit_open_total"] == 0
    assert data["strategist_llm"]["circuit_open_rate"] == 0.0
    assert data["strategist_llm"]["circuit_state_total"] == {}
    assert data["strategist_llm"]["prompt_version_total"] == {}
    assert data["strategist_llm"]["schema_version_total"] == {}
    assert data["strategist_llm"]["token_usage"]["prompt_tokens_total"] == 0
    assert data["strategist_llm"]["token_usage"]["completion_tokens_total"] == 0
    assert data["strategist_llm"]["token_usage"]["total_tokens_total"] == 0
    assert data["strategist_llm"]["token_usage"]["estimated_cost_usd_total"] == 0.0
    assert data["skill_hydration"]["total"] == 0
    assert data["skill_hydration"]["used_runner_total"] == 0
    assert data["skill_hydration"]["fallback_hint_total"] == 0
    assert data["skill_hydration"]["fallback_hint_rate"] == 0.0
    assert data["skill_hydration"]["errors_total_sum"] == 0
    assert data["skill_hydration"]["runner_source_total"] == {}
    assert data["skill_hydration"]["attempted_total_by_skill"] == {}
    assert data["skill_hydration"]["ready_total_by_skill"] == {}
    assert data["skill_hydration"]["errors_total_by_skill"] == {}
    assert data["intents_executed_total"] == 0
    assert data["execution"]["intents_created"] == 0
    assert data["execution"]["intents_approved"] == 0
    assert data["execution"]["intents_blocked"] == 0
    assert data["execution"]["intents_executed"] == 0
    assert data["execution"]["blocked_reason_topN"] == []
    assert data["broker_api"]["api_error_total_by_api_id"] == {}
    assert data["broker_api"]["api_429_total"] == 0
    assert data["broker_api"]["api_429_rate"] == 0.0


def test_generate_metrics_report_broker_api_429_rate(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-17T00:00:00+00:00",
                        "run_id": "r1",
                        "stage": "execute_from_packet",
                        "event": "error",
                        "payload": {"api_id": "ORDER_SUBMIT", "status_code": 429, "error": "too many requests"},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-17T00:00:01+00:00",
                        "run_id": "r2",
                        "stage": "execute_from_packet",
                        "event": "error",
                        "payload": {"api_id": "ORDER_SUBMIT", "status_code": 500, "error": "server error"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-17")
    data = json.loads(js.read_text(encoding="utf-8"))

    assert data["broker_api"]["api_error_total_by_api_id"]["ORDER_SUBMIT"] == 2
    assert data["broker_api"]["api_429_total"] == 1
    assert abs(float(data["broker_api"]["api_429_rate"]) - 0.5) < 1e-12


def test_generate_metrics_report_aggregates_portfolio_guard_metrics(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-20T00:00:00+00:00",
                        "run_id": "r1",
                        "stage": "commander_router",
                        "event": "end",
                        "payload": {
                            "status": "ok",
                            "path": "graph_spine",
                            "portfolio_guard": {
                                "applied": True,
                                "approved_total": 2,
                                "blocked_total": 3,
                                "blocked_reason_counts": {
                                    "strategy_budget_exceeded": 2,
                                    "opposite_side_conflict": 1,
                                },
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-20T00:00:10+00:00",
                        "run_id": "r2",
                        "stage": "commander_router",
                        "event": "end",
                        "payload": {
                            "status": "ok",
                            "path": "graph_spine",
                            "portfolio_guard": {
                                "applied": True,
                                "approved_total": 1,
                                "blocked_total": 2,
                                "blocked_reason_counts": {
                                    "strategy_budget_exceeded": 1,
                                    "symbol_notional_cap_exceeded": 1,
                                },
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-20")
    data = json.loads(js.read_text(encoding="utf-8"))

    pg = data["portfolio_guard"]
    assert pg["total"] == 2
    assert pg["applied_total"] == 2
    assert pg["approved_total_sum"] == 3
    assert pg["blocked_total_sum"] == 5
    assert pg["blocked_reason_total"]["strategy_budget_exceeded"] == 3
    assert pg["blocked_reason_total"]["opposite_side_conflict"] == 1
    assert pg["blocked_reason_total"]["symbol_notional_cap_exceeded"] == 1
    assert pg["blocked_reason_topN"][0]["reason"] == "strategy_budget_exceeded"
    assert pg["blocked_reason_topN"][0]["count"] == 3


def test_generate_metrics_report_empty_has_portfolio_guard_keys(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-20")
    data = json.loads(js.read_text(encoding="utf-8"))

    pg = data["portfolio_guard"]
    assert pg["total"] == 0
    assert pg["applied_total"] == 0
    assert pg["approved_total_sum"] == 0
    assert pg["blocked_total_sum"] == 0
    assert pg["blocked_reason_total"] == {}
    assert pg["blocked_reason_topN"] == []
