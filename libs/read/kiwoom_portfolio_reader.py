from __future__ import annotations

from typing import Any, Dict, List

from libs.core.symbols import normalize_symbol
from libs.core.settings import Settings
from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.kiwoom.kiwoom_account_client import KiwoomAccountClient
from libs.read.snapshot_models import PortfolioSnapshot, PositionSnapshot


def _num(x: Any) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if s.startswith("+"):
        s = s[1:]
    try:
        return float(s)
    except Exception:
        import re
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


def _first_present(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _extract_cash(payload: Dict[str, Any]) -> float:
    for root in (payload, payload.get("output") or {}, payload.get("output1") or {}, payload.get("result") or {}):
        if isinstance(root, dict):
            v = _first_present(
                root,
                [
                    "cash",
                    "dnca_tot_amt",
                    "prvs_rcdl_excc_amt",
                    "tot_evlu_amt",
                    "tot_evlt_amt",
                    "dbst_bal",
                    "day_stk_asst",
                    "prsm_dpst_aset_amt",
                ],
            )
            if v is not None:
                return _num(v)
        if isinstance(root, list) and root:
            v = _first_present(root[0], ["cash", "dnca_tot_amt", "prvs_rcdl_excc_amt"])
            if v is not None:
                return _num(v)
    return 0.0


def _normalize_symbol(symbol: Any) -> str:
    return normalize_symbol(symbol, allow_test_symbols=False)


def _extract_positions(payload: Dict[str, Any]) -> List[PositionSnapshot]:
    candidates: List[Any] = []
    for k in [
        "positions",
        "acnt_evlt_remn_indv_tot",
        "day_bal_rt",
        "output2",
        "output",
        "output1",
        "data",
        "items",
    ]:
        v = payload.get(k)
        if isinstance(v, list):
            candidates = v
            break

    pos: List[PositionSnapshot] = []
    for it in candidates or []:
        if not isinstance(it, dict):
            continue
        symbol = _normalize_symbol(_first_present(it, ["symbol", "stk_cd", "pdno", "code"]))
        if not symbol:
            continue
        qty = int(_num(_first_present(it, ["qty", "hldg_qty", "qty_avlb", "ord_psbl_qty"]) or 0))
        if qty <= 0:
            qty = int(_num(_first_present(it, ["rmnd_qty"]) or 0))
        avg_price = _num(_first_present(it, ["avg_price", "pchs_avg_pric", "avg_pric", "buy_avg", "pur_pric"]) or 0)
        if avg_price <= 0.0:
            avg_price = _num(_first_present(it, ["buy_uv"]) or 0)
        upnl = _num(_first_present(it, ["unrealized_pnl", "evlu_pfls_amt", "pnl", "prft"]) or 0)
        if upnl == 0.0:
            upnl = _num(_first_present(it, ["evltv_prft"]) or 0)
        current_price = _num(
            _first_present(
                it,
                [
                    "current_price",
                    "cur_price",
                    "cur_prc",
                    "stck_prpr",
                    "prpr",
                    "now_pric",
                    "last_price",
                    "price",
                    "cur",
                ],
            )
            or 0
        )
        if current_price <= 0.0 and qty > 0 and avg_price > 0.0 and upnl != 0.0:
            current_price = avg_price + (upnl / float(qty))
        pos.append(
            PositionSnapshot(
                symbol=symbol,
                qty=qty,
                avg_price=avg_price,
                unrealized_pnl=upnl,
                current_price=(current_price if current_price > 0.0 else None),
            )
        )
    return pos


class KiwoomPortfolioReader:
    """Real portfolio reader (mock host when KIWOOM_MODE=mock)."""

    def __init__(self, account: KiwoomAccountClient):
        self.account = account

    @classmethod
    def from_env(cls) -> "KiwoomPortfolioReader":
        s = Settings.from_env()
        base = s.kiwoom_base_url_mock if s.kiwoom_mode == "mock" else s.kiwoom_base_url_real
        http = HttpClient(
            base_url=base,
            timeout_sec=int(s.kiwoom_http_timeout_sec),
            retry_max=int(s.kiwoom_retry_max),
        )
        token = KiwoomTokenClient(s, http)
        account = KiwoomAccountClient(s, http, token)
        return cls(account)

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        # AccountBalanceResult type differs by project version; use duck-typing.
        res = self.account.get_account_balance(dry_run=False)  # type: ignore
        if not bool(getattr(res, "ok", False)):
            code = getattr(res, "status_code", None)
            message = getattr(res, "error_message", None) or "account_balance_api_failed"
            raise RuntimeError(f"account_balance_api_failed(status={code}, message={message})")
        payload = getattr(res, "payload", None) or {}
        cash = _extract_cash(payload)
        positions = _extract_positions(payload)
        return PortfolioSnapshot(cash=cash, positions=positions)
