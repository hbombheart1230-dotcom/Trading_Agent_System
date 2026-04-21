from __future__ import annotations

from types import SimpleNamespace

from libs.catalog.api_catalog import ApiCatalog
from libs.read.kiwoom_orderable_cash_reader import KiwoomOrderableCashReader


class _StubExecutor:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def execute(self, req):
        self.requests.append(req)
        payload = self.payloads.pop(0) if self.payloads else {}
        return SimpleNamespace(response=SimpleNamespace(payload=payload))


def test_kiwoom_orderable_cash_reader_reads_deposit_snapshot_from_kt00001():
    catalog = ApiCatalog.from_obj(
        [
            {"api_id": "kt00001", "title": "예수금상세현황요청", "method": "POST", "path": "/api/dostk/acnt"},
        ]
    )
    executor = _StubExecutor(
        [
            {
                "entr": "17534",
                "pymn_alow_amt": "85341",
                "ord_alow_amt": "85341",
                "d1_pymn_alow_amt": "12550",
                "d2_pymn_alow_amt": "12550",
            }
        ]
    )
    reader = KiwoomOrderableCashReader(catalog=catalog, executor=executor)

    out = reader.get_deposit_snapshot()

    assert out["deposit"] == 17534.0
    assert out["withdrawable_cash"] == 85341.0
    assert out["orderable_amount"] == 85341.0
    assert out["d1_withdrawable_cash"] == 12550.0
    assert out["d2_withdrawable_cash"] == 12550.0
    assert out["source"] == "kiwoom.kt00001"


def test_kiwoom_orderable_cash_reader_reads_simulated_order_window_from_kt00010():
    catalog = ApiCatalog.from_obj(
        [
            {"api_id": "kt00010", "title": "주문인출가능금액요청", "method": "POST", "path": "/api/dostk/acnt"},
        ]
    )
    executor = _StubExecutor(
        [
            {
                "entr": "17534",
                "ord_alowa": "85341",
                "wthd_alowa": "85341",
                "cmsn": "120",
                "pur_exct_amt": "267000",
                "d2entra": "12550",
            }
        ]
    )
    reader = KiwoomOrderableCashReader(catalog=catalog, executor=executor)

    out = reader.simulate_orderable_cash(symbol="005930", side="BUY", price=267000, qty=1)

    assert out["deposit"] == 17534.0
    assert out["orderable_cash"] == 85341.0
    assert out["withdrawable_cash"] == 85341.0
    assert out["fee"] == 120
    assert out["buy_settlement_amount"] == 267000.0
    assert out["d2_estimated_deposit"] == 12550.0
    assert out["source"] == "kiwoom.kt00010"
    assert executor.requests[0].body["stk_cd"] == "005930"
    assert executor.requests[0].body["trde_tp"] == "2"
