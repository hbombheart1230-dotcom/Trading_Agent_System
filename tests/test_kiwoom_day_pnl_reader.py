from __future__ import annotations

from types import SimpleNamespace

from libs.catalog.api_catalog import ApiCatalog
from libs.read.kiwoom_day_pnl_reader import KiwoomDayPnlReader


class _StubExecutor:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def execute(self, req):
        self.requests.append(req)
        payload = self.payloads.pop(0) if self.payloads else {}
        return SimpleNamespace(response=SimpleNamespace(payload=payload))


def test_kiwoom_day_pnl_reader_reads_realized_summary_from_ka10074():
    catalog = ApiCatalog.from_obj(
        [
            {"api_id": "ka10074", "title": "일자별실현손익요청", "method": "POST", "path": "/api/dostk/acnt"},
        ]
    )
    executor = _StubExecutor(
        [
            {
                "tot_sell_amt": "474600",
                "rlzt_pl": "179419",
                "trde_cmsn": "940",
                "trde_tax": "852",
            }
        ]
    )
    reader = KiwoomDayPnlReader(catalog=catalog, executor=executor)

    out = reader.get_day_realized_summary(day="2026-04-20")

    assert out["day"] == "20260420"
    assert out["realized_pnl"] == 179419.0
    assert out["gross_sell_amount"] == 474600.0
    assert out["fee"] == 940
    assert out["tax"] == 852
    assert out["source"] == "kiwoom.ka10074"
    assert executor.requests[0].api_id == "ka10074"


def test_kiwoom_day_pnl_reader_reads_detail_rows_from_ka10077():
    catalog = ApiCatalog.from_obj(
        [
            {"api_id": "ka10077", "title": "당일실현손익상세요청", "method": "POST", "path": "/api/dostk/acnt"},
        ]
    )
    executor = _StubExecutor(
        [
            {
                "tdy_rlzt_pl_dtl": [
                    {
                        "stk_cd": "A005930",
                        "stk_nm": "삼성전자",
                        "cntr_qty": "1",
                        "buy_uv": "97602.95",
                        "cntr_pric": "158200",
                        "tdy_sel_pl": "59813.04",
                        "pl_rt": "+61.28",
                        "tdy_trde_cmsn": "500",
                        "tdy_trde_tax": "284",
                    }
                ]
            }
        ]
    )
    reader = KiwoomDayPnlReader(catalog=catalog, executor=executor)

    out = reader.get_day_realized_details(symbol="005930")

    assert len(out["rows"]) == 1
    row = out["rows"][0]
    assert row["symbol"] == "005930"
    assert row["name"] == "삼성전자"
    assert row["filled_qty"] == 1
    assert row["filled_price"] == 158200.0
    assert round(float(row["pnl_ratio"] or 0.0), 4) == 0.6128
    assert row["fee"] == 500
    assert row["tax"] == 284
    assert executor.requests[0].api_id == "ka10077"
    assert executor.requests[0].body["stk_cd"] == "005930"
