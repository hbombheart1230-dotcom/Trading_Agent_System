from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from libs.catalog.api_catalog import ApiCatalog
from libs.core.settings import Settings
from libs.read.kiwoom_broker_truth_common import (
    KiwoomBrokerTruthClient,
    first_present,
    normalize_symbol,
    require_api,
    to_float,
    to_int,
)


def _normalize_ratio(v: Any) -> Optional[float]:
    out = to_float(v)
    if out is None:
        return None
    return out / 100.0 if abs(out) > 1.0 else out


def _detail_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = payload.get("tdy_rlzt_pl_dtl")
    return rows if isinstance(rows, list) else []


class KiwoomDayPnlReader:
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
    def from_env(cls) -> "KiwoomDayPnlReader":
        return cls()

    def get_day_realized_summary(self, *, day: str) -> Dict[str, Any]:
        api_id = require_api(self.catalog, "ka10074", "일자별실현손익요청")
        payload = self.client.call(api_id, {"end_dt": str(day).replace("-", "")})
        rows = payload.get("dt_rlzt_pl")
        row = rows[0] if isinstance(rows, list) and rows else payload
        return {
            "day": str(day).replace("-", ""),
            "realized_pnl": to_float(first_present(row if isinstance(row, dict) else {}, ["tdy_sel_pl", "rlzt_pl"])),
            "gross_sell_amount": to_float(first_present(row if isinstance(row, dict) else {}, ["sell_amt", "tot_sell_amt"])),
            "fee": to_int(first_present(row if isinstance(row, dict) else {}, ["tdy_trde_cmsn", "trde_cmsn"])),
            "tax": to_int(first_present(row if isinstance(row, dict) else {}, ["tdy_trde_tax", "trde_tax"])),
            "source": "kiwoom.ka10074",
            "raw": payload,
        }

    def get_day_realized_details(self, *, symbol: str = "") -> Dict[str, Any]:
        api_id = require_api(self.catalog, "ka10077", "당일실현손익상세요청")
        body = {"stk_cd": symbol} if str(symbol or "").strip() else {}
        payload = self.client.call(api_id, body)
        rows = []
        for row in _detail_rows(payload):
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "symbol": normalize_symbol(first_present(row, ["stk_cd", "symbol"])),
                    "name": str(first_present(row, ["stk_nm", "name"]) or "").strip(),
                    "filled_qty": to_int(first_present(row, ["cntr_qty", "filled_qty"])),
                    "buy_price": to_float(first_present(row, ["buy_uv", "buy_price"])),
                    "filled_price": to_float(first_present(row, ["cntr_pric", "filled_price"])),
                    "realized_pnl": to_float(first_present(row, ["tdy_sel_pl", "realized_pnl"])),
                    "pnl_ratio": _normalize_ratio(first_present(row, ["pl_rt", "pnl_ratio"])),
                    "fee": to_int(first_present(row, ["tdy_trde_cmsn", "fee"])),
                    "tax": to_int(first_present(row, ["tdy_trde_tax", "tax"])),
                }
            )
        return {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "rows": rows,
            "source": "kiwoom.ka10077",
            "raw": payload,
        }

    def get_account_profit_rate_rows(self) -> Dict[str, Any]:
        api_id = require_api(self.catalog, "ka10085", "계좌수익률요청")
        payload = self.client.call(api_id, {})
        rows = payload.get("acnt_prft_rt")
        normalized: List[Dict[str, Any]] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized.append(
                    {
                        "symbol": normalize_symbol(first_present(row, ["stk_cd", "symbol"])),
                        "name": str(first_present(row, ["stk_nm", "name"]) or "").strip(),
                        "current_price": to_float(first_present(row, ["cur_prc", "current_price"])),
                        "buy_price": to_float(first_present(row, ["pur_pric", "buy_price"])),
                        "qty": to_int(first_present(row, ["rmnd_qty", "qty"])),
                        "today_sell_pnl": to_float(first_present(row, ["tdy_sel_pl", "realized_pnl"])),
                        "today_fee": to_int(first_present(row, ["tdy_trde_cmsn", "fee"])),
                        "today_tax": to_int(first_present(row, ["tdy_trde_tax", "tax"])),
                    }
                )
        return {"rows": normalized, "source": "kiwoom.ka10085", "raw": payload}
