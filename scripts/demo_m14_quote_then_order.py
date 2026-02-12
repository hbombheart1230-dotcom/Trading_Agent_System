"""M14 demo: Quote -> (optional auto-price) -> Order (MOCK).

Adds:
- Quote call (체결정보요청, ka10003) to get current price and best bid/ask units.
- Auto-price for limit orders using best bid/ask so it stays within tick/limit rules.

Examples:
  # market buy
  python scripts/demo_m14_quote_then_order.py --side buy --symbol 005930 --qty 1 --trade-type 3

  # limit sell with auto price (uses best ask)
  python scripts/demo_m14_quote_then_order.py --side sell --symbol 005930 --qty 1 --trade-type 0 --auto-price

  # limit buy with explicit price
  python scripts/demo_m14_quote_then_order.py --side buy --symbol 005930 --qty 1 --trade-type 0 --price 70000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import Settings
from libs.catalog.api_catalog import ApiCatalog, ApiNotFoundError


def _env_path(name: str, default: str) -> Path:
    v = os.getenv(name)
    return Path(v) if v else Path(default)


def _ensure_catalog() -> Path:
    catalog_path = _env_path("KIWOOM_API_CATALOG_JSONL", "./data/specs/api_catalog.jsonl")
    if catalog_path.exists():
        return catalog_path

    src = _env_path("KIWOOM_REGISTRY_APIS_JSONL", "./data/specs/kiwoom_apis.jsonl")
    if not src.exists():
        raise SystemExit(f"Missing source api list: {src}")

    import scripts.build_api_catalog as bac
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    bac.main()
    return catalog_path


def _pick_api_id_by_title(catalog: ApiCatalog, title_exact: str) -> str:
    for spec in catalog.list_specs():
        if (spec.title or "").strip() == title_exact:
            return spec.api_id
    raise ApiNotFoundError(f"API not found by title: {title_exact}")


def _pick_quote_api_id(catalog: ApiCatalog) -> str:
    # Prefer the well-known Kiwoom ID
    if catalog.has("ka10003"):
        return "ka10003"
    # Fallback by title
    return _pick_api_id_by_title(catalog, "체결정보요청")


def _pick_order_api_id(catalog: ApiCatalog, side: str) -> str:
    if side == "buy" and catalog.has("kt10000"):
        return "kt10000"
    if side == "sell" and catalog.has("kt10001"):
        return "kt10001"

    want = "주식 매수주문" if side == "buy" else "주식 매도주문"
    return _pick_api_id_by_title(catalog, want)


def _parse_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        # Kiwoom sometimes uses "+53500" style
        s = s.lstrip("+")
        if s == "":
            return None
        try:
            return int(float(s))
        except Exception:
            return None
    return None


def _fetch_quote(executor, catalog: ApiCatalog, symbol: str) -> Dict[str, Any]:
    api_id = _pick_quote_api_id(catalog)
    spec = catalog.get(api_id)
    req = {
        "api_id": api_id,
        "method": spec.method or "POST",
        "path": spec.path,
        "headers": {},
        "query": {},
        # examples in kiwoom_apis.jsonl show stk_cd is used for ka10003
        "body": {"stk_cd": symbol},
    }
    res = executor.execute(req)
    payload = res.response.payload if res and res.response else {}
    return {"api_id": api_id, "spec": spec, "result": res, "payload": payload}


def _extract_best_prices(quote_payload: Dict[str, Any]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Returns (cur_prc, best_ask, best_bid) if available.
    ka10003 example returns list 'cntr_infr' with keys:
      cur_prc, pri_sel_bid_unit (best ask), pri_buy_bid_unit (best bid)
    """
    items = None
    for k in ("cntr_infr", "items", "data", "result"):
        if isinstance(quote_payload.get(k), list):
            items = quote_payload.get(k)
            break
    if not items:
        return (None, None, None)

    first = items[0] or {}
    cur = _parse_int(first.get("cur_prc"))
    best_ask = _parse_int(first.get("pri_sel_bid_unit"))
    best_bid = _parse_int(first.get("pri_buy_bid_unit"))
    return (cur, best_ask, best_bid)


def _build_order_body(args: argparse.Namespace, *, price: Optional[int]) -> Dict[str, Any]:
    return {
        "dmst_stex_tp": args.market,  # KRX
        "stk_cd": args.symbol,
        "ord_qty": str(args.qty),
        "trde_tp": str(args.trade_type),
        "ord_uv": "" if price is None else str(price),
        "cond_uv": "" if args.cond_price is None else str(args.cond_price),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--price", type=int, default=None, help="limit price (ord_uv). omit for 시장가")
    p.add_argument("--auto-price", action="store_true", help="for limit orders, set price from best bid/ask")
    p.add_argument("--trade-type", type=int, default=3, help="0=보통(지정가), 3=시장가 (Kiwoom trde_tp)")
    p.add_argument("--cond-price", type=int, default=None, help="cond_uv")
    p.add_argument("--market", default="KRX", help="dmst_stex_tp (KRX/NXT/SOR). mock supports KRX")
    args = p.parse_args()

    _ = Settings.from_env()
    catalog_path = _ensure_catalog()
    print(f"[demo] catalog={catalog_path}")
    catalog = ApiCatalog.load(str(catalog_path))

    from libs.execution.executors import get_executor
    executor = get_executor(catalog=catalog)

    # Quote
    q = _fetch_quote(executor, catalog, args.symbol)
    q_payload = q["payload"] or {}
    cur, best_ask, best_bid = _extract_best_prices(q_payload)
    print(f"[quote] cur={cur} best_ask={best_ask} best_bid={best_bid}")

    # Decide order price
    price = args.price
    is_limit = str(args.trade_type) == "0"
    if args.auto_price and is_limit:
        if args.side == "buy":
            price = best_bid or cur or price
        else:
            price = best_ask or cur or price

    # If still no price for limit, fail fast
    if is_limit and price is None:
        raise SystemExit("Limit order requires --price or --auto-price (with quote fields available).")

    # Order
    order_api_id = _pick_order_api_id(catalog, args.side)
    spec = catalog.get(order_api_id)
    body = _build_order_body(args, price=price)

    req = {
        "api_id": order_api_id,
        "method": spec.method or "POST",
        "path": spec.path,
        "headers": {},
        "query": {},
        "body": body,
    }
    res = executor.execute(req)
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
