from __future__ import annotations

from libs.reporting.broker_closed_trade_reconciler import (
    _build_order_pair_truth,
    _find_closed_day_diary_row,
    _merge_day_diary_with_order_pair,
    _order_time_to_utc,
    _pair_same_symbol_round_trips,
    _patch_entry_payload,
    _patch_exit_payload,
    _patch_lifecycle_payload,
    _patch_report_payload,
    _patch_summary_payload,
)


def test_single_round_trip_keeps_exact_day_diary_pnl_with_order_timing() -> None:
    merged = _merge_day_diary_with_order_pair(
        {
            "source": "kiwoom.ka10170",
            "match_mode": "ka10170_symbol_buy_sell_qty_exact",
            "pnl": 37806.0,
            "pnl_pct": 0.0141,
            "fee_tax": 24474,
            "buy_price": 2683.425,
            "sell_price": 2745.705,
        },
        {
            "source": "kiwoom.order_pair_snapshot",
            "pnl": 38576.0,
            "pnl_pct": 0.0144,
            "buy_order_no": "101",
            "sell_order_no": "102",
            "buy_time": "143500",
            "sell_time": "145400",
        },
    )

    assert merged["source"] == "kiwoom.ka10170"
    assert merged["pnl"] == 37806.0
    assert merged["pnl_pct"] == 0.0141
    assert merged["fee_tax"] == 24474
    assert merged["buy_order_no"] == "101"
    assert merged["sell_order_no"] == "102"
    assert merged["match_mode"] == "ka10170_with_order_pair_time"


def test_order_pair_truth_can_match_buy_from_exit_order_when_entry_order_missing() -> None:
    orders = [
        {
            "ord_no": "0090860",
            "io_tp_nm": "+매수",
            "ord_tm": "114724",
            "ord_qty": "1000",
            "cntr_qty": "1000",
            "cntr_pric": "1216",
            "stk_cd": "036420",
        },
        {
            "ord_no": "0092587",
            "io_tp_nm": "-매도",
            "ord_tm": "115405",
            "ord_qty": "1000",
            "cntr_qty": "1000",
            "cntr_pric": "1218",
            "stk_cd": "036420",
        },
    ]

    truth = _build_order_pair_truth(
        symbol="036420",
        entry={"order_id": ""},
        exit_payload={"order_id": "0092587"},
        order_rows=orders,
        fee_rows=[
            {**orders[0], "tdy_trde_cmsn": "4240", "tdy_trde_tax": "0"},
            {**orders[1], "tdy_trde_cmsn": "4170", "tdy_trde_tax": "2420"},
        ],
    )

    assert truth["buy_order_no"] == "0090860"
    assert truth["sell_order_no"] == "0092587"
    assert truth["buy_price"] == 1216.0
    assert truth["sell_price"] == 1218.0
    assert truth["pnl"] == -8830.0
    assert truth["match_mode"] == "entry_order_id_next_same_symbol_qty_sell"


def test_round_trip_pairing_uses_fee_rows_without_crossing_order_times() -> None:
    rows = [
        {"ord_no": "0090860", "io_tp_nm": "+매수", "ord_tm": "114724", "ord_qty": "1000", "cntr_qty": "1000", "stk_cd": "036420"},
        {"ord_no": "0092587", "io_tp_nm": "-매도", "ord_tm": "115405", "ord_qty": "1000", "cntr_qty": "1000", "stk_cd": "036420"},
        {"ord_no": "0095083", "io_tp_nm": "+매수", "ord_tm": "120713", "ord_qty": "1000", "cntr_qty": "1000", "stk_cd": "036420"},
        {"ord_no": "0096421", "io_tp_nm": "-매도", "ord_tm": "121311", "ord_qty": "1000", "cntr_qty": "1000", "stk_cd": "036420"},
    ]

    pairs = _pair_same_symbol_round_trips(rows)

    assert [(p["buy"]["ord_no"], p["sell"]["ord_no"]) for p in pairs] == [
        ("0090860", "0092587"),
        ("0095083", "0096421"),
    ]


def test_day_diary_match_uses_filled_entry_price() -> None:
    row = _find_closed_day_diary_row(
        [{
            "stk_cd": "097780",
            "buy_qty": "1000",
            "sell_qty": "1000",
            "buy_avg_pric": "1390",
        }],
        symbol="097780",
        entry={"qty": 1000, "price": 1399, "filled_price": 1390},
    )

    assert row["stk_cd"] == "097780"


def test_exit_patch_includes_broker_fill_timestamp_and_order_id() -> None:
    exit_ts = _order_time_to_utc("2026-06-23", "110558")
    patched = _patch_exit_payload(
        {},
        {
            "symbol": "097780",
            "qty": 1000,
            "sell_price": 1358,
            "sell_order_no": "0088888",
            "exit_ts": exit_ts,
            "pnl": -44521,
            "pnl_pct": -0.032,
            "fee_tax": 12310,
            "buy_price": 1390,
            "source": "kiwoom.ka10170",
            "match_mode": "ka10170_with_order_pair_time",
        },
    )

    assert patched["timestamp"] == "2026-06-23T02:05:58+00:00"
    assert patched["order_id"] == "0088888"


def test_entry_patch_replaces_none_price_with_broker_buy_price() -> None:
    patched = _patch_entry_payload(
        {
            "symbol": "006800",
            "price": None,
            "qty": 66,
            "filled_qty": 66,
            "execution_details": {
                "filled_price": None,
                "avg_price": None,
                "broker_day_authoritative": False,
            },
        },
        {
            "symbol": "006800",
            "qty": 66,
            "buy_price": 45317.0,
            "source": "kiwoom.ka10170",
            "match_mode": "ka10170_symbol_buy_sell_qty_exact",
        },
    )

    assert patched["price"] == 45317.0
    assert patched["filled_price"] == 45317.0
    assert patched["avg_price"] == 45317.0
    assert patched["execution_details"]["filled_price"] == 45317.0
    assert patched["execution_details"]["broker_buy_price"] == 45317.0


def test_report_and_summary_patch_fill_symbol_metadata_fallback() -> None:
    truth = {
        "symbol": "006800",
        "qty": 66,
        "buy_price": 45317.0,
        "sell_price": 45294.0,
        "pnl": -28445.0,
        "pnl_pct": -0.0095,
        "pnl_pct_text": "-0.95%",
        "fee_tax": 26895,
        "result_label": "loss",
        "source": "kiwoom.ka10170",
        "match_mode": "ka10170_with_order_pair_time",
    }

    report = _patch_report_payload({"symbol": "006800", "symbol_name": None, "shared_facts": {}}, truth)
    summary = _patch_summary_payload({"trade": {"symbol": "006800", "symbol_name": "", "theme": ""}}, truth)

    assert report["symbol_name"] == "미래에셋증권"
    assert report["shared_facts"]["symbol_name"] == "미래에셋증권"
    assert summary["trade"]["symbol_name"] == "미래에셋증권"
    assert summary["trade"]["themes"] == ["증권", "금융투자", "자산관리"]


def test_lifecycle_patch_closes_nested_lifecycle_and_truth_sources() -> None:
    truth = {
        "symbol": "097780",
        "qty": 1000,
        "sell_price": 1358,
        "sell_order_no": "0088888",
        "exit_ts": "2026-06-23T02:05:58+00:00",
        "pnl": -44521,
        "pnl_pct": -0.032,
        "fee_tax": 12310,
        "buy_price": 1390,
        "source": "kiwoom.ka10170",
        "match_mode": "ka10170_with_order_pair_time",
    }
    patched = _patch_lifecycle_payload(
        {
            "entry": {"symbol": "097780"},
            "lifecycle": {"status": "open", "entry": {"symbol": "097780"}, "exit": {}},
            "shared_facts": {"data_source": {"pnl": "unavailable"}},
        },
        truth,
    )

    assert patched["lifecycle"]["status"] == "closed"
    assert patched["lifecycle"]["exit"]["action"] == "SELL"
    assert patched["entry"]["price"] == 1390
    assert patched["entry_execution_details"]["filled_price"] == 1390
    assert patched["exit_execution_details"]["broker_realized_pnl_pct"] == -0.032
    assert patched["execution_details"]["broker_realized_pnl_pct"] == -0.032
    assert patched["execution_details"]["pnl_truth_source"] == "kiwoom.ka10170"
    assert patched["shared_facts"]["data_source"]["pnl"] == "kiwoom.ka10170"
