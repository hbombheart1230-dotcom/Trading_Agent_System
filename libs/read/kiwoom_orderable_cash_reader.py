from __future__ import annotations

from typing import Any, Dict, Optional

from libs.catalog.api_catalog import ApiCatalog
from libs.core.settings import Settings
from libs.read.kiwoom_broker_truth_common import KiwoomBrokerTruthClient, first_present, require_api, to_float, to_int


class KiwoomOrderableCashReader:
    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        catalog: Optional[ApiCatalog] = None,
        executor: Any = None,
    ) -> None:
        self.client = KiwoomBrokerTruthClient(settings=settings, catalog=catalog, executor=executor)
        self.catalog = self.client.catalog

    @classmethod
    def from_env(cls) -> "KiwoomOrderableCashReader":
        return cls()

    def get_deposit_snapshot(self) -> Dict[str, Any]:
        api_id = require_api(self.catalog, "kt00001", "예수금상세현황요청")
        payload = self.client.call(api_id, {})
        return {
            "deposit": to_float(first_present(payload, ["entr", "deposit"])),
            "withdrawable_cash": to_float(first_present(payload, ["pymn_alow_amt", "withdrawable_cash"])),
            "orderable_amount": to_float(first_present(payload, ["ord_alow_amt", "orderable_amount"])),
            "d1_withdrawable_cash": to_float(first_present(payload, ["d1_pymn_alow_amt"])),
            "d2_withdrawable_cash": to_float(first_present(payload, ["d2_pymn_alow_amt"])),
            "source": "kiwoom.kt00001",
            "raw": payload,
        }

    def simulate_orderable_cash(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        qty: Optional[int] = None,
        expected_buy_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        api_id = require_api(self.catalog, "kt00010", "주문인출가능금액요청")
        trade_type = "1" if str(side or "").strip().upper() == "SELL" else "2"
        body: Dict[str, Any] = {
            "stk_cd": str(symbol or "").strip(),
            "trde_tp": trade_type,
            "uv": str(int(price)),
        }
        if qty not in (None, 0):
            body["trde_qty"] = str(int(qty))
        if expected_buy_price not in (None, 0, 0.0):
            body["exp_buy_unp"] = str(int(expected_buy_price))
        payload = self.client.call(api_id, body)
        return {
            "deposit": to_float(first_present(payload, ["entr", "deposit"])),
            "orderable_cash": to_float(first_present(payload, ["ord_alowa", "orderable_cash"])),
            "withdrawable_cash": to_float(first_present(payload, ["wthd_alowa", "withdrawable_cash"])),
            "fee": to_int(first_present(payload, ["cmsn", "fee"])),
            "buy_settlement_amount": to_float(first_present(payload, ["pur_exct_amt", "buy_settlement_amount"])),
            "d2_estimated_deposit": to_float(first_present(payload, ["d2entra", "d2_estimated_deposit"])),
            "source": "kiwoom.kt00010",
            "raw": payload,
        }
