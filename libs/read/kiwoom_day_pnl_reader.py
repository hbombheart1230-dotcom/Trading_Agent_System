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


def _normalize_percent(v: Any) -> Optional[float]:
    out = to_float(v)
    if out is None:
        return None
    return out / 100.0


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
            raw_pl_rt = first_present(row, ["pl_rt"])
            rows.append(
                {
                    "symbol": normalize_symbol(first_present(row, ["stk_cd", "symbol"])),
                    "name": str(first_present(row, ["stk_nm", "name"]) or "").strip(),
                    "filled_qty": to_int(first_present(row, ["cntr_qty", "filled_qty"])),
                    "buy_price": to_float(first_present(row, ["buy_uv", "buy_price"])),
                    "filled_price": to_float(first_present(row, ["cntr_pric", "filled_price"])),
                    "realized_pnl": to_float(first_present(row, ["tdy_sel_pl", "realized_pnl"])),
                    "pnl_ratio": (
                        _normalize_percent(raw_pl_rt)
                        if raw_pl_rt not in (None, "")
                        else _normalize_ratio(first_present(row, ["pnl_ratio"]))
                    ),
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

    def get_day_trade_diary(self, *, day: str, symbol: str = "") -> Dict[str, Any]:
        api_id = require_api(self.catalog, "ka10170", "당일매매일지요청")
        payload = self.client.call(
            api_id,
            {
                "base_dt": str(day).replace("-", ""),
                "ottks_tp": "1",
                "ch_crd_tp": "0",
            },
        )
        wanted_symbol = normalize_symbol(symbol) if str(symbol or "").strip() else ""
        rows_raw = payload.get("tdy_trde_diary")
        rows: List[Dict[str, Any]] = []
        if isinstance(rows_raw, list):
            for row in rows_raw:
                if not isinstance(row, dict):
                    continue
                row_symbol = normalize_symbol(first_present(row, ["stk_cd", "symbol"]))
                if wanted_symbol and row_symbol != wanted_symbol:
                    continue
                raw_prft_rt = first_present(row, ["prft_rt", "pnl_ratio"])
                rows.append(
                    {
                        "symbol": row_symbol,
                        "name": str(first_present(row, ["stk_nm", "name"]) or "").strip(),
                        "buy_avg_price": to_float(first_present(row, ["buy_avg_pric", "buy_price"])),
                        "buy_qty": to_int(first_present(row, ["buy_qty"])),
                        "sell_avg_price": to_float(first_present(row, ["sel_avg_pric", "filled_price", "sell_price"])),
                        "sell_qty": to_int(first_present(row, ["sell_qty", "filled_qty"])),
                        "fee_tax": to_int(first_present(row, ["cmsn_alm_tax", "fee_tax"])),
                        "realized_pnl": to_float(first_present(row, ["pl_amt", "realized_pnl"])),
                        "sell_amount": to_float(first_present(row, ["sell_amt"])),
                        "buy_amount": to_float(first_present(row, ["buy_amt"])),
                        "pnl_ratio": _normalize_percent(raw_prft_rt) if raw_prft_rt not in (None, "") else None,
                        "raw": row,
                    }
                )
        return {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "day": str(day).replace("-", ""),
            "total_sell_amount": to_float(first_present(payload, ["tot_sell_amt"])),
            "total_buy_amount": to_float(first_present(payload, ["tot_buy_amt"])),
            "total_fee_tax": to_int(first_present(payload, ["tot_cmsn_tax"])),
            "total_settlement_amount": to_float(first_present(payload, ["tot_exct_amt"])),
            "total_realized_pnl": to_float(first_present(payload, ["tot_pl_amt"])),
            "total_pnl_ratio": _normalize_percent(first_present(payload, ["tot_prft_rt"])),
            "rows": rows,
            "source": "kiwoom.ka10170",
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
