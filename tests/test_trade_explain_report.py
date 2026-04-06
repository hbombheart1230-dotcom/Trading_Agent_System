from __future__ import annotations

import json
from pathlib import Path

from scripts.run_trade_explain_report import main as trade_explain_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_trade_explain_report_builds_sell_pair_with_hold_and_pnl(tmp_path: Path, capsys) -> None:
    day = "2026-03-10"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "trade_explain"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "scanner",
                "event": "summary",
                "payload": {"candidate_source": "kiwoom_market_data", "top_stock": "005930", "top_score": 0.81},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {
                        "intent": {"action": "BUY", "symbol": "005930", "qty": 2, "reason": "strategy_v1_entry"},
                        "why": {
                            "technical": {"signal_score": 0.7, "rsi14": 58.0, "ma20_gap": 0.02, "volatility20": 0.03},
                            "news": {
                                "symbol_sentiment_score": 0.3,
                                "global_sentiment_score": 0.1,
                                "symbol_sentiment_status": "ok",
                                "global_sentiment_status": "ok",
                            },
                        },
                    },
                    "trace": {"strategy": "RegimeMomentumV1", "rationale": "strategy_v1_entry: composite=0.42 regime=trend"},
                },
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r_buy",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "BUY", "symbol": "005930", "qty": 2, "price": 100, "order_type": "market"},
                    "payload": {"broker_code": "0", "broker_message": "buy_ok"},
                },
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:00+00:00",
                "stage": "scanner",
                "event": "summary",
                "payload": {"candidate_source": "kiwoom_market_data", "top_stock": "005930", "top_score": 0.66},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:01+00:00",
                "stage": "monitor",
                "event": "summary",
                "payload": {"exit_reason": "take_profit", "monitor_reason": "confirmed_exit_signal"},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:02+00:00",
                "stage": "decision",
                "event": "trace",
                "payload": {
                    "decision_packet": {"intent": {"action": "SELL", "symbol": "005930", "qty": 2, "reason": "exit_policy_take_profit"}},
                    "trace": {"strategy": "ExitPolicyStrategist", "rationale": "exit_policy:take_profit"},
                },
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:03+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r_sell",
                "ts": f"{day}T00:05:04+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "SELL", "symbol": "005930", "qty": 2, "price": 110, "order_type": "market"},
                    "payload": {"broker_code": "0", "broker_message": "sell_ok"},
                },
            },
        ],
    )

    rc = trade_explain_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--day",
            day,
            "--max-executions",
            "20",
            "--max-sell-pairs",
            "20",
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["day"] == day
    exe = obj["execution_summary"]
    assert int(exe["executions_total"]) == 2
    assert int(exe["sell_pairs_total"]) == 1

    pair = (obj.get("sell_pairs") or [])[0]
    assert pair["symbol"] == "005930"
    assert int(pair["matched_qty"]) == 2
    assert int(pair["hold_duration_sec_avg"]) == 301
    assert float(pair["estimated_realized_pnl"]) == 20.0
    assert pair["strategy"] == "ExitPolicyStrategist"
    assert pair["monitor_reason"] == "confirmed_exit_signal"

    md_path = Path(obj["report_md_path"])
    assert md_path.exists()
    md_body = md_path.read_text(encoding="utf-8")
    assert "Sell Pair Analysis (FIFO, Latest)" in md_body
    assert "estimated_realized_pnl" in md_body


def test_trade_explain_report_uses_latest_day_when_day_not_given(tmp_path: Path, capsys) -> None:
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "trade_explain"
    _write_jsonl(
        events,
        [
            {
                "run_id": "d1",
                "ts": "2026-03-09T00:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 100}},
            },
            {
                "run_id": "d2",
                "ts": "2026-03-10T00:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1, "price": 200}},
            },
        ],
    )

    rc = trade_explain_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(out_dir),
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["day"] == "2026-03-10"
    assert int(obj["execution_summary"]["executions_total"]) == 1
    assert "000660:BUY" in (obj["execution_summary"]["symbol_side_counts"] or {})


def test_trade_explain_report_filters_malformed_live_like_symbols(tmp_path: Path, capsys) -> None:
    day = "2026-03-16"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "trade_explain"
    _write_jsonl(
        events,
        [
            {
                "run_id": "bad1",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "A0082N0", "qty": 1, "price": 100}},
            },
            {
                "run_id": "good1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 200}},
            },
        ],
    )

    rc = trade_explain_main(
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
    assert int(obj["execution_summary"]["executions_total"]) == 1
    assert "005930:BUY" in (obj["execution_summary"]["symbol_side_counts"] or {})
    assert "A0082N0:BUY" not in (obj["execution_summary"]["symbol_side_counts"] or {})


def test_trade_explain_report_adds_no_trade_summary(tmp_path: Path, capsys) -> None:
    day = "2026-04-06"
    events = tmp_path / "events.jsonl"
    out_dir = tmp_path / "trade_explain"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:00+00:00",
                "stage": "strategist",
                "event": "policy_resolution",
                "payload": {"strategy_generation_mode": "fallback", "fallback_used": True},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "commander_router",
                "event": "route_selected",
                "payload": {"route_selected": "monitor_only"},
            },
            {
                "run_id": "r1",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "monitor",
                "event": "entry_decision_detail",
                "payload": {
                    "no_trade_surface": {
                        "no_trade_stage": "pre_intent_wait",
                        "dominant_blocker": "below_vwap_reclaim_not_ready",
                        "near_ready_flag": True,
                    },
                    "scanner_monitor_handoff": {"scanner_vs_monitor_alignment": "partial_mismatch"},
                },
            },
        ],
    )

    rc = trade_explain_main(
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
    assert obj["no_trade_summary"]["no_trade_runs_total"] == 1
    assert obj["no_trade_summary"]["near_ready_runs_total"] == 1
    assert obj["no_trade_summary"]["strategist_fallback_total"] == 1
    assert obj["no_trade_summary"]["route_selected_total"]["monitor_only"] == 1
    assert obj["no_trade_summary"]["scanner_monitor_mismatch_total"] == 1
    assert obj["no_trade_summary"]["dominant_blocker_topN"][0]["reason"] == "below_vwap_reclaim_not_ready"
    md_body = Path(obj["report_md_path"]).read_text(encoding="utf-8")
    assert "## No-Trade Summary" in md_body
    assert "no_trade_runs_total" in md_body
