from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.trade_lifecycle_builder import (
    build_trade_lifecycles,
    load_existing_open_lifecycle_candidates,
)


def test_build_trade_lifecycles_closes_buy_sell_in_same_symbol() -> None:
    lifecycles = build_trade_lifecycles(
        day="2026-04-16",
        run_snapshots=[
            {
                "run_id": "run-buy",
                "ts_start": "2026-04-16T01:00:00+00:00",
                "ts_epoch": 1,
                "symbol": "000660",
                "execution_action": "BUY",
                "execution": {"action": "BUY", "qty": 1, "price": 100.0},
                "verdict_allowed": True,
            },
            {
                "run_id": "run-sell",
                "ts_start": "2026-04-16T01:02:00+00:00",
                "ts_epoch": 2,
                "symbol": "000660",
                "execution_action": "SELL",
                "execution": {"action": "SELL", "qty": 1, "price": 101.0},
                "exit_reason": "peak_drawdown",
                "monitor_reason": "confirmed_exit_signal",
                "verdict_allowed": True,
            },
        ],
        run_bundles={
            "run-buy": {},
            "run-sell": {},
        },
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "closed"
    assert lifecycle["entry"]["run_id"] == "run-buy"
    assert lifecycle["exit"]["run_id"] == "run-sell"


def test_build_trade_lifecycles_keeps_partial_sell_open() -> None:
    lifecycles = build_trade_lifecycles(
        day="2026-05-12",
        run_snapshots=[
            {
                "run_id": "run-buy",
                "ts_start": "2026-05-12T01:00:00+00:00",
                "ts_epoch": 1,
                "symbol": "003060",
                "execution_action": "BUY",
                "execution": {"action": "BUY", "qty": 1000, "price": 920.0},
                "verdict_allowed": True,
            },
            {
                "run_id": "run-sell-partial",
                "ts_start": "2026-05-12T01:01:00+00:00",
                "ts_epoch": 2,
                "symbol": "003060",
                "execution_action": "SELL",
                "execution": {"action": "SELL", "qty": 1, "price": 919.0},
                "exit_reason": "vwap_breakdown",
                "monitor_reason": "confirmed_exit_signal",
                "verdict_allowed": True,
            },
        ],
        run_bundles={"run-buy": {}, "run-sell-partial": {}},
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "open"
    assert lifecycle["entry"]["qty"] == 1000
    assert lifecycle.get("exit") == {}
    assert lifecycle["remaining_qty"] == 999
    assert lifecycle["partial_exit_qty"] == 1
    partial_exits = lifecycle["holding"]["partial_exits"]
    assert partial_exits[0]["run_id"] == "run-sell-partial"
    assert partial_exits[0]["qty"] == 1


def test_build_trade_lifecycles_closes_after_cumulative_partial_sells() -> None:
    lifecycles = build_trade_lifecycles(
        day="2026-05-12",
        run_snapshots=[
            {
                "run_id": "run-buy",
                "ts_start": "2026-05-12T01:00:00+00:00",
                "ts_epoch": 1,
                "symbol": "003060",
                "execution_action": "BUY",
                "execution": {"action": "BUY", "qty": 1000, "price": 920.0},
                "verdict_allowed": True,
            },
            {
                "run_id": "run-sell-partial",
                "ts_start": "2026-05-12T01:01:00+00:00",
                "ts_epoch": 2,
                "symbol": "003060",
                "execution_action": "SELL",
                "execution": {"action": "SELL", "qty": 1, "price": 919.0},
                "exit_reason": "vwap_breakdown",
                "monitor_reason": "confirmed_exit_signal",
                "verdict_allowed": True,
            },
            {
                "run_id": "run-sell-final",
                "ts_start": "2026-05-12T01:03:00+00:00",
                "ts_epoch": 3,
                "symbol": "003060",
                "execution_action": "SELL",
                "execution": {"action": "SELL", "qty": 999, "price": 918.0},
                "exit_reason": "stop_loss",
                "monitor_reason": "confirmed_exit_signal",
                "verdict_allowed": True,
            },
        ],
        run_bundles={"run-buy": {}, "run-sell-partial": {}, "run-sell-final": {}},
    )

    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "closed"
    assert lifecycle["entry"]["qty"] == 1000
    assert lifecycle["exit"]["run_id"] == "run-sell-final"
    assert lifecycle["exit"]["qty"] == 999
    assert lifecycle["remaining_qty"] == 0
    assert lifecycle["partial_exit_qty"] == 1
    partial_exits = lifecycle["holding"]["partial_exits"]
    assert partial_exits[0]["run_id"] == "run-sell-partial"
    assert partial_exits[0]["qty"] == 1


def test_load_existing_open_lifecycle_candidates_filters_closed_trade(tmp_path: Path) -> None:
    day = "2026-04-16"
    day_root = tmp_path / "trades" / day
    open_trade_dir = day_root / "TRD_20260416_000660_01"
    closed_trade_dir = day_root / "TRD_20260416_005930_01"
    open_trade_dir.mkdir(parents=True, exist_ok=True)
    closed_trade_dir.mkdir(parents=True, exist_ok=True)

    (open_trade_dir / "lifecycle_bundle.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260416_000660_01",
                "symbol": "000660",
                "status": "open",
                "entry": {"run_id": "run-buy", "ts": "2026-04-16T01:00:00+00:00", "action": "BUY", "qty": 1},
                "exit": {},
                "linked_run_ids": ["run-buy"],
            }
        ),
        encoding="utf-8",
    )
    (closed_trade_dir / "lifecycle_bundle.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260416_005930_01",
                "symbol": "005930",
                "status": "closed",
                "entry": {"run_id": "run-buy-2", "ts": "2026-04-16T01:00:00+00:00", "action": "BUY", "qty": 1},
                "exit": {"run_id": "run-sell-2", "ts": "2026-04-16T01:03:00+00:00", "action": "SELL"},
                "linked_run_ids": ["run-buy-2", "run-sell-2"],
            }
        ),
        encoding="utf-8",
    )

    candidates = load_existing_open_lifecycle_candidates(reports_root=tmp_path, day=day)
    assert "000660" in candidates
    assert "005930" not in candidates
    assert candidates["000660"][0]["trade_id"] == "TRD_20260416_000660_01"
