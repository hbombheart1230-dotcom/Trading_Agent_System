from __future__ import annotations

from types import SimpleNamespace

from libs.catalog.api_catalog import ApiCatalog
from libs.read.kiwoom_order_fill_reader import KiwoomOrderFillReader, normalize_broker_order_rows


class _StubExecutor:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def execute(self, req):
        self.requests.append(req)
        payload = self.payloads.pop(0) if self.payloads else {}
        return SimpleNamespace(response=SimpleNamespace(payload=payload))


def test_normalize_broker_order_rows_extracts_fill_truth_fields():
    rows = normalize_broker_order_rows(
        [
            {
                "ord_no": "001",
                "stk_cd": "A005930",
                "io_tp_nm": "매도",
                "ord_qty": "1",
                "cntr_qty": "1",
                "ord_uv": "70000",
                "cntr_uv": "70100",
                "acpt_tp": "체결",
                "ord_tm": "090101",
                "cntr_tm": "090102",
                "fee_amt": "15",
                "tax_amt": "20",
            }
        ]
    )

    assert len(rows) == 1
    assert rows[0]["ord_no"] == "001"
    assert rows[0]["symbol"] == "005930"
    assert rows[0]["side"] == "SELL"
    assert rows[0]["filled_qty"] == 1
    assert rows[0]["filled_price"] == 70100
    assert rows[0]["fee"] == 15
    assert rows[0]["tax"] == 20


def test_kiwoom_order_fill_reader_get_filled_rows_for_day_uses_kt00009():
    catalog = ApiCatalog.from_obj(
        [
            {"api_id": "kt00009", "title": "계좌별주문체결현황요청", "method": "POST", "path": "/api/dostk/acnt/order-status"},
        ]
    )
    executor = _StubExecutor(
        [
            {
                "acnt_ord_cntr_prst_array": [
                    {
                        "ord_no": "001",
                        "stk_cd": "A005930",
                        "io_tp_nm": "매수",
                        "ord_qty": "2",
                        "cntr_qty": "2",
                        "ord_uv": "70000",
                        "cntr_uv": "70100",
                        "acpt_tp": "체결",
                    }
                ]
            }
        ]
    )
    reader = KiwoomOrderFillReader(catalog=catalog, executor=executor)

    rows = reader.get_filled_rows_for_day(day="2026-04-20")

    assert len(rows) == 1
    assert rows[0]["symbol"] == "005930"
    assert rows[0]["side"] == "BUY"
    assert executor.requests[0].api_id == "kt00009"
    assert executor.requests[0].body["ord_dt"] == "20260420"


def test_kiwoom_order_fill_reader_get_order_status_merges_detail_and_summary_rows():
    catalog = ApiCatalog.from_obj(
        [
            {"api_id": "kt00007", "title": "계좌별주문체결내역상세요청", "method": "POST", "path": "/api/dostk/acnt/order-detail"},
            {"api_id": "kt00009", "title": "계좌별주문체결현황요청", "method": "POST", "path": "/api/dostk/acnt/order-status"},
        ]
    )
    executor = _StubExecutor(
        [
            {
                "acnt_ord_cntr_prps_dtl": [
                    {
                        "ord_no": "001",
                        "stk_cd": "A005930",
                        "acpt_tp": "체결",
                        "ord_qty": "1",
                        "io_tp_nm": "매도",
                    }
                ]
            },
            {
                "acnt_ord_cntr_prst_array": [
                    {
                        "ord_no": "001",
                        "stk_cd": "A005930",
                        "cntr_qty": "1",
                        "cntr_uv": "70200",
                        "ord_uv": "70100",
                    }
                ]
            },
        ]
    )
    reader = KiwoomOrderFillReader(catalog=catalog, executor=executor)

    dto = reader.get_order_status(ord_no="001", symbol="005930", ord_dt="20260420")

    assert dto.ord_no == "001"
    assert dto.symbol == "005930"
    assert dto.status == "체결"
    assert dto.filled_qty == 1
    assert dto.filled_price == 70200
    assert dto.order_qty == 1
    assert dto.order_price == 70100
    assert dto.side == "매도"
