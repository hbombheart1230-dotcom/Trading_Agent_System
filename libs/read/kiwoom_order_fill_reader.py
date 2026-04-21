from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from libs.catalog.api_catalog import ApiCatalog
from libs.core.settings import Settings
from libs.read.kiwoom_broker_truth_common import (
    KiwoomBrokerTruthClient,
    first_present as _first_present,
    normalize_symbol as _normalize_symbol,
    require_api as _require_api,
    to_int as _to_int,
)
from libs.skills.dto import OrderStatusDTO
from libs.skills.dto_extractors import extract_order_status


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue
def _normalize_side(v: Any) -> str:
    raw = str(v or "").strip().upper()
    if raw in {"BUY", "B", "2"}:
        return "BUY"
    if raw in {"SELL", "S", "1"}:
        return "SELL"
    if "BUY" in raw:
        return "BUY"
    if "SELL" in raw:
        return "SELL"
    if "매수" in raw:
        return "BUY"
    if "매도" in raw:
        return "SELL"
    return raw


def _pick(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    rows = payload.get(key)
    return rows if isinstance(rows, list) else []


def normalize_broker_order_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ord_no = str(_first_present(row, ["ord_no", "odno", "ODNO"]) or "").strip()
        symbol = _normalize_symbol(_first_present(row, ["stk_cd", "symbol", "pdno", "code"]))
        out.append(
            {
                "ord_no": ord_no,
                "symbol": symbol,
                "side": _normalize_side(_first_present(row, ["io_tp_nm", "trde_tp", "side"])),
                "order_qty": _to_int(_first_present(row, ["ord_qty", "order_qty"])),
                "filled_qty": _to_int(_first_present(row, ["cntr_qty", "filled_qty"])),
                "remaining_qty": _to_int(_first_present(row, ["ord_remnq", "rmnd_qty", "remaining_qty"])),
                "order_price": _to_int(_first_present(row, ["ord_uv", "order_price"])),
                "filled_price": _to_int(_first_present(row, ["cntr_uv", "filled_price"])),
                "status": str(_first_present(row, ["acpt_tp", "status", "ord_st"]) or "").strip(),
                "order_time": str(_first_present(row, ["ord_tm", "order_time"]) or "").strip(),
                "filled_time": str(_first_present(row, ["cntr_tm", "filled_time"]) or "").strip(),
                "fee": _to_int(
                    _first_present(
                        row,
                        ["fee", "fee_amt", "ord_fee", "cntr_fee", "fee_total", "fee_sum", "cmsn", "comm_fee"],
                    )
                ),
                "tax": _to_int(
                    _first_present(
                        row,
                        ["tax", "tax_amt", "ord_tax", "cntr_tax", "tax_total", "tax_sum"],
                    )
                ),
                "raw": row,
            }
        )
    return out


def load_local_execution_rows(event_log_path: Path, *, day: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in _iter_jsonl(event_log_path):
        ts_kst = str(rec.get("ts_kst") or "")
        if not ts_kst.startswith(day):
            continue
        if rec.get("stage") != "execute_from_packet" or rec.get("event") != "execution":
            continue
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        inner_meta = inner.get("meta") if isinstance(inner.get("meta"), dict) else {}
        broker_ok = bool(inner.get("broker_message")) or bool(inner.get("order_id")) or bool(inner.get("json"))
        if not broker_ok:
            continue
        effective_mode = str(inner.get("effective_mode") or "")
        executor_name = str(inner_meta.get("executor") or "")
        ord_no = str(inner.get("order_id") or "")
        symbol = _normalize_symbol(order.get("symbol") or order.get("stk_cd"))
        if effective_mode == "mock_executor" or executor_name == "mock":
            continue
        if ord_no.startswith("A") and str(inner.get("broker_message") or "").strip().lower() == "accepted":
            continue
        if not ord_no or not symbol:
            continue
        rows.append(
            {
                "run_id": str(rec.get("run_id") or ""),
                "ts_kst": ts_kst,
                "ord_no": ord_no,
                "symbol": symbol,
                "side": _normalize_side(order.get("action")),
                "qty": _to_int(order.get("qty") or order.get("ord_qty")),
                "broker_message": str(inner.get("broker_message") or ""),
                "effective_mode": effective_mode,
            }
        )
    return rows


def reconcile_rows(local_rows: List[Dict[str, Any]], broker_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    local_by_ord = {str(row.get("ord_no") or ""): row for row in local_rows if str(row.get("ord_no") or "")}
    broker_by_ord = {str(row.get("ord_no") or ""): row for row in broker_rows if str(row.get("ord_no") or "")}
    missing_in_local = [row for ord_no, row in broker_by_ord.items() if ord_no not in local_by_ord]
    missing_in_broker = [row for ord_no, row in local_by_ord.items() if ord_no not in broker_by_ord]

    def _count(rows: List[Dict[str, Any]]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for row in rows:
            key = f"{str(row.get('symbol') or '')}:{str(row.get('side') or '')}"
            out[key] = int(out.get(key) or 0) + 1
        return dict(sorted(out.items()))

    return {
        "local_total": len(local_rows),
        "broker_total": len(broker_rows),
        "matched_by_ord_no": len([k for k in local_by_ord.keys() if k in broker_by_ord]),
        "broker_window_limited": bool(
            local_rows
            and broker_rows
            and len(local_rows) > len(broker_rows)
            and len([k for k in local_by_ord.keys() if k in broker_by_ord]) == len(broker_rows)
        ),
        "missing_in_local_total": len(missing_in_local),
        "missing_in_broker_total": len(missing_in_broker),
        "missing_in_local": missing_in_local[:20],
        "missing_in_broker": missing_in_broker[:20],
        "local_counts": _count(local_rows),
        "broker_counts": _count(broker_rows),
    }


class KiwoomOrderFillReader:
    """Broker-side order/fill truth owner for kt00007 + kt00009."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        catalog: Optional[ApiCatalog] = None,
        executor: Any = None,
    ) -> None:
        self.client = KiwoomBrokerTruthClient(settings=settings, catalog=catalog, executor=executor)
        self.s = self.client.s
        self.catalog = self.client.catalog
        self.executor = self.client.executor

    @classmethod
    def from_env(cls) -> "KiwoomOrderFillReader":
        return cls()

    def fetch_order_status_payloads(
        self,
        *,
        ord_no: str,
        symbol: str,
        ord_dt: str,
        qry_tp: str = "4",
        mrkt_tp: str = "0",
        market: str = "KRX",
        side: str = "all",
    ) -> Dict[str, Dict[str, Any]]:
        sell_tp_map = {"all": "0", "sell": "1", "buy": "2"}
        sell_tp = sell_tp_map.get(str(side).strip().lower(), "0")
        kt00007 = _require_api(self.catalog, "kt00007", "계좌별주문체결내역상세요청")
        kt00009 = _require_api(self.catalog, "kt00009", "계좌별주문체결현황요청")
        detail_payload = self.client.call(
            kt00007,
            {
                "qry_tp": "2",
                "stk_bond_tp": "1",
                "sell_tp": sell_tp,
                "stk_cd": symbol or "",
                "fr_ord_no": ord_no,
                "dmst_stex_tp": market,
            },
        )
        summary_payload = self.client.call(
            kt00009,
            {
                "ord_dt": ord_dt,
                "qry_tp": str(qry_tp or "4"),
                "mrkt_tp": str(mrkt_tp or "0"),
                "stk_bond_tp": "1",
                "sell_tp": sell_tp,
                "stk_cd": symbol or "",
                "fr_ord_no": ord_no,
                "dmst_stex_tp": market,
            },
        )
        return {"detail": detail_payload, "summary": summary_payload}

    def get_order_status(
        self,
        *,
        ord_no: str,
        symbol: str,
        ord_dt: str,
        qry_tp: str = "4",
        mrkt_tp: str = "0",
        market: str = "KRX",
        side: str = "all",
    ) -> OrderStatusDTO:
        payloads = self.fetch_order_status_payloads(
            ord_no=ord_no,
            symbol=symbol,
            ord_dt=ord_dt,
            qry_tp=qry_tp,
            mrkt_tp=mrkt_tp,
            market=market,
            side=side,
        )
        return extract_order_status(ord_no, [payloads["detail"], payloads["summary"]])

    def get_filled_rows_for_day(
        self,
        *,
        day: str,
        qry_tp: str = "4",
        mrkt_tp: str = "0",
        market: str = "KRX",
        symbol: str = "",
        side: str = "all",
        stk_bond_tp: str = "1",
        fr_ord_no: str = "",
    ) -> List[Dict[str, Any]]:
        sell_tp_map = {"all": "0", "sell": "1", "buy": "2"}
        sell_tp = sell_tp_map.get(str(side).strip().lower(), "0")
        api_id = _require_api(self.catalog, "kt00009", "계좌별주문체결현황요청")
        payload = self.client.call(
            api_id,
            {
                "ord_dt": day.replace("-", ""),
                "qry_tp": str(qry_tp or "4"),
                "mrkt_tp": str(mrkt_tp or "0"),
                "stk_bond_tp": str(stk_bond_tp or "1"),
                "sell_tp": sell_tp,
                "stk_cd": symbol or "",
                "fr_ord_no": fr_ord_no or "",
                "dmst_stex_tp": market,
            },
        )
        return normalize_broker_order_rows(_pick(payload, "acnt_ord_cntr_prst_array"))

    def get_daily_reconciliation_report(
        self,
        *,
        day: str,
        event_log_path: Path,
    ) -> Dict[str, Any]:
        local_rows = load_local_execution_rows(event_log_path, day=day)
        broker_rows = self.get_filled_rows_for_day(day=day)
        return {
            "day": day,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "event_log_path": str(event_log_path),
            "summary": reconcile_rows(local_rows, broker_rows),
        }
