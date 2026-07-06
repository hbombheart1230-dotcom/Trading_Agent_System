from __future__ import annotations

from libs.reporting.broker_closed_trade_reconciler import (
    _find_closed_day_diary_row,
    _order_time_to_utc,
    _patch_entry_payload,
    _patch_exit_payload,
    _patch_lifecycle_payload,
    _patch_report_payload,
    _patch_summary_payload,
)


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
    assert patched["shared_facts"]["data_source"]["pnl"] == "kiwoom.ka10170"
