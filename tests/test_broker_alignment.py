from libs.reporting.broker_alignment import _extract_day_trade_diary_rows


def test_extract_day_trade_diary_rows_surfaces_closed_symbols() -> None:
    snapshot = {
        "calls": [
            {
                "api_id": "ka10170",
                "payload": {
                    "tdy_trde_diary": [
                        {
                            "stk_cd": "A061040",
                            "stk_nm": "Alpha",
                            "buy_qty": "378",
                            "sell_qty": "378",
                            "buy_avg_pric": "7939",
                            "sel_avg_pric": "7915",
                            "cmsn_alm_tax": "26944",
                            "pl_amt": "-36074",
                            "prft_rt": "-1.20",
                        },
                        {
                            "stk_cd": "005930",
                            "buy_qty": "10",
                            "sell_qty": "3",
                        },
                    ]
                },
            }
        ]
    }

    rows = _extract_day_trade_diary_rows(snapshot)

    assert rows[0]["symbol"] == "061040"
    assert rows[0]["closed_by_day_trade_diary"] is True
    assert rows[0]["sell_avg_price"] == 7915.0
    assert rows[0]["pnl_pct"] == -1.20
    assert rows[1]["symbol"] == "005930"
    assert rows[1]["closed_by_day_trade_diary"] is False
