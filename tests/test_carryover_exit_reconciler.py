from __future__ import annotations

import json
from pathlib import Path

from libs.reporting import carryover_exit_reconciler as reconciler
from libs.reporting.symbol_trade_report import build_daily_trade_index


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _snapshot(day: str, *, sell_qty: int, sell_price: int, pnl: float) -> dict:
    return {
        "day": day,
        "calls": [
            {
                "api_id": "ka10170",
                "payload": {
                    "tdy_trde_diary": [
                        {
                            "stk_cd": "097780",
                            "buy_qty": "0",
                            "sell_qty": str(sell_qty),
                        }
                    ]
                },
            },
            {
                "api_id": "ka10072",
                "payload": {
                    "dt_stk_div_rlzt_pl": [
                        {
                            "stk_cd": "097780",
                            "cntr_qty": str(sell_qty),
                            "buy_uv": "1323.45",
                            "cntr_pric": str(sell_price),
                            "tdy_sel_pl": str(pnl),
                            "tdy_trde_cmsn": "4400",
                            "tdy_trde_tax": "2500",
                        }
                    ]
                },
            },
            {
                "api_id": "ka10076",
                "payload": {
                    "cntr": [
                        {
                            "ord_no": "0003801",
                            "stk_cd": "097780",
                            "io_tp_nm": "-매도",
                            "cntr_qty": str(sell_qty),
                            "cntr_pric": str(sell_price),
                            "ord_tm": "090015",
                        }
                    ]
                },
            },
        ],
    }


def test_reconcile_carryover_exit_closes_prior_trade_and_indexes_exit_day(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reports = tmp_path / "reports"
    trade_dir = reports / "trades" / "2026-06-19" / "1400" / "TRD_20260619_097780_01"
    _write_json(
        trade_dir / "lifecycle_bundle.json",
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": "2026-06-19",
            "trade_id": "TRD_20260619_097780_01",
            "symbol": "097780",
            "trade_lifecycle_status": "open",
            "entry": {
                "ts": "2026-06-19T05:20:55+00:00",
                "action": "BUY",
                "price": 1323.45,
                "qty": 960,
                "order_id": "0125389",
                "reason_human": "entry",
            },
            "exit": {},
            "lifecycle": {
                "entry": {
                    "ts": "2026-06-19T05:20:55+00:00",
                    "action": "BUY",
                    "price": 1323.45,
                    "qty": 960,
                },
                "exit": {},
            },
        },
    )
    _write_json(trade_dir / "_health.json", {"lifecycle_status": "open"})
    current_snapshot = _snapshot("2026-06-22", sell_qty=960, sell_price=1324, pnl=-11026.86)
    _write_json(
        tmp_path / "data" / "logs" / "kiwoom_account_snapshots" / "2026-06-22" / "latest.json",
        current_snapshot,
    )
    monkeypatch.setattr(
        reconciler,
        "_regenerate_deterministic_report",
        lambda *_args, **_kwargs: {"ok": True},
    )

    result = reconciler.reconcile_carryover_exit_reports(
        reports_root=reports,
        day="2026-06-22",
        snapshot=current_snapshot,
    )

    assert result["patched_count"] == 1
    lifecycle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    assert lifecycle["trade_lifecycle_status"] == "closed"
    assert lifecycle["remaining_qty"] == 0
    assert lifecycle["exit"]["carryover_exit"] is True
    assert lifecycle["exit"]["order_id"] == "0003801"
    assert lifecycle["shared_facts"]["pnl"] == -11026.86
    assert lifecycle["carryover_exit"]["entry_day"] == "2026-06-19"
    assert lifecycle["carryover_exit"]["exit_day"] == "2026-06-22"

    trade_index = build_daily_trade_index(reports, "2026-06-22")
    assert len(trade_index) == 1
    assert trade_index[0]["trade_id"] == "TRD_20260619_097780_01"
    assert trade_index[0]["date"] == "2026-06-22"
    assert trade_index[0]["trade_root_path"] == str(trade_dir)
