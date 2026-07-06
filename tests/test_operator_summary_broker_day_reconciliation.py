import json
from pathlib import Path

from libs.reporting.operator_period_summary import (
    _enrich_rows_with_truth_surface,
    _is_closed_trade,
    _is_realized_nonclosed_exit,
    _metric_return_pct,
)


def test_enrich_rows_uses_ka10170_to_close_open_lifecycle_residue(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_dir = reports_root / "trades" / "2026-06-09" / "1000" / "TRD_20260609_001020_01"
    trade_dir.mkdir(parents=True)
    (trade_dir / "lifecycle_bundle.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260609_001020_01",
                "symbol": "001020",
                "trade_lifecycle_status": "open",
                "entry": {"symbol": "001020", "qty": 1000, "price": 2425},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot_dir = tmp_path / "data" / "logs" / "kiwoom_account_snapshots" / "2026-06-09"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-09T07:37:57+00:00",
                "summary": {"api_call_count": 1, "ok_count": 1, "error_count": 0},
                "calls": [
                    {
                        "api_id": "ka10170",
                        "payload": {
                            "tdy_trde_diary": [
                                {
                                    "stk_cd": "001020",
                                    "stk_nm": "페이퍼코리아",
                                    "buy_avg_pric": "2425",
                                    "buy_qty": "1000",
                                    "sel_avg_pric": "2385",
                                    "sell_qty": "1000",
                                    "cmsn_alm_tax": "21571",
                                    "pl_amt": "-61656",
                                    "prft_rt": "-2.54",
                                }
                            ]
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = _enrich_rows_with_truth_surface(
        [
            {
                "trade_id": "TRD_20260609_001020_01",
                "date": "2026-06-09",
                "symbol": "001020",
                "status": "open",
                "last_status": "open",
                "trade_root_path": str(trade_dir),
            }
        ],
        reports_root,
    )

    row = rows[0]
    assert row["status"] == "closed"
    assert row["last_status"] == "closed"
    assert row["last_action"] == "SELL"
    assert row["truth_source"] == "kiwoom.ka10170"
    assert row["broker_day_authoritative"] is True
    assert _is_closed_trade(row) is True
    assert _metric_return_pct(row) == -2.54


def test_closeout_broker_skip_is_not_counted_as_closed_or_realized(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    trade_dir = reports_root / "trades" / "2026-07-03" / "1500" / "TRD_20260703_025440_06"
    trade_dir.mkdir(parents=True)
    (trade_dir / "lifecycle_bundle.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260703_025440_06",
                "symbol": "025440",
                "trade_lifecycle_status": "partial",
                "entry": {"symbol": "025440", "qty": 49, "price": 3280},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    daily = reports_root / "operator_summary" / "daily" / "2026-07-03"
    daily.mkdir(parents=True)
    (daily / "closeout_maintenance.json").write_text(
        json.dumps(
            {
                "steps": {
                    "broker_closed_trade_reconciliation": {
                        "snapshot_path": "data/logs/kiwoom_account_snapshots/2026-07-03/latest.json",
                        "skipped": [
                            {
                                "trade_id": "TRD_20260703_025440_06",
                                "symbol": "025440",
                                "reason": "order_pair_or_day_diary_row_not_found",
                            }
                        ],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = _enrich_rows_with_truth_surface(
        [
            {
                "trade_id": "TRD_20260703_025440_06",
                "date": "2026-07-03",
                "symbol": "025440",
                "status": "partial",
                "last_status": "partial",
                "last_action": "SELL",
                "result_pct": -0.01,
                "trade_root_path": str(trade_dir),
            }
        ],
        reports_root,
    )

    row = rows[0]
    assert row["broker_reconciliation_status"] == "skipped_unresolved"
    assert _is_closed_trade(row) is False
    assert _is_realized_nonclosed_exit(row) is False
