from __future__ import annotations

from libs.runtime.etf_deviation import extract_etf_deviation_signal


def test_common_stock_dstr_rt_is_not_treated_as_etf_deviation() -> None:
    out = extract_etf_deviation_signal(
        symbol="005930",
        state={
            "symbol_metadata": {
                "005930": {
                    "stk_nm": "삼성전자",
                    "dstr_rt": "76.0",
                }
            }
        },
    )

    assert out["available"] is False
    assert out["etf_deviation_pct"] is None
    assert out["exit_premium_score"] == 0.0


def test_etf_dstr_rt_is_kept_when_asset_class_is_etf() -> None:
    out = extract_etf_deviation_signal(
        symbol="069500",
        state={
            "symbol_metadata": {
                "069500": {
                    "stk_nm": "KODEX 200",
                    "asset_class": "etf",
                    "dstr_rt": "-0.80",
                }
            }
        },
    )

    assert out["available"] is True
    assert out["is_etf_family"] is True
    assert out["etf_deviation_pct"] == -0.80
    assert out["entry_discount_score"] > 0.0

