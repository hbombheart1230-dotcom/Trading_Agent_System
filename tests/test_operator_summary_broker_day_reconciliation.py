import json
from pathlib import Path

from libs.reporting.operator_period_summary import _enrich_rows_with_truth_surface, _is_closed_trade, _metric_return_pct


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
