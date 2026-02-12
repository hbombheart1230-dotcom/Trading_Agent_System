"""M14 demo: send a real order to Kiwoom MOCK REST (paper trading) account.

This script is intentionally small and explicit so you can run it by hand
and verify end-to-end:
  - load env (.env)
  - ensure api_catalog.jsonl exists (build from kiwoom_apis.jsonl if needed)
  - call order submit via executor (RealExecutor against KIWOOM_MODE=mock base url)

Usage examples (Git Bash / PowerShell):
  python scripts/demo_m14_mock_order.py --side buy  --symbol 005930 --qty 1 --trade-type 3
  python scripts/demo_m14_mock_order.py --side sell --symbol 005930 --qty 1 --trade-type 0 --price 70000

Notes
- "mock" here means "Kiwoom paper trading REST host" (https://mockapi.kiwoom.com).
- Actual HTTP sending is additionally guarded by EXECUTION_ENABLED.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# --- bootstrap so `python scripts/...` works reliably ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import Settings
from libs.catalog.api_catalog import ApiCatalog, ApiNotFoundError


def _env_path(name: str, default: str) -> Path:
    v = os.getenv(name)
    return Path(v) if v else Path(default)


def _ensure_catalog() -> Path:
    """Ensure ./data/specs/api_catalog.jsonl exists and contains method/path."""
    catalog_path = _env_path("KIWOOM_API_CATALOG_JSONL", "./data/specs/api_catalog.jsonl")
    if catalog_path.exists():
        for line in catalog_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("method") and rec.get("path"):
                    return catalog_path
            except Exception:
                break

    # Build catalog from kiwoom_apis.jsonl
    src = _env_path("KIWOOM_REGISTRY_APIS_JSONL", "./data/specs/kiwoom_apis.jsonl")
    if not src.exists():
        raise SystemExit(f"Missing source api list: {src}")

    import scripts.build_api_catalog as bac

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    bac.main()
    return catalog_path


def _build_order_body(args: argparse.Namespace) -> Dict[str, Any]:
    # Kiwoom order body fields (names follow REST docs)
    return {
        "dmst_stex_tp": args.market,  # e.g., KRX
        "stk_cd": args.symbol,
        "ord_qty": str(args.qty),
        "trde_tp": str(args.trade_type),
        "ord_uv": "" if args.price is None else str(args.price),
        "cond_uv": "" if args.cond_price is None else str(args.cond_price),
    }


def _pick_order_api_id(catalog: ApiCatalog, side: str) -> str:
    """
    Prefer known Kiwoom ids (kt10000/kt10001). Fall back to title search.
    """
    if side == "buy" and catalog.has("kt10000"):
        return "kt10000"
    if side == "sell" and catalog.has("kt10001"):
        return "kt10001"

    # fallback: find by Korean title
    want = "주식 매수주문" if side == "buy" else "주식 매도주문"
    for spec in catalog.list_specs():
        if (spec.title or "").strip() == want:
            return spec.api_id

    raise ApiNotFoundError(f"Order API not found for side={side}. Expected kt10000/kt10001 or title '{want}'.")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--price", type=int, default=None, help="limit price (ord_uv). omit for 시장가")
    p.add_argument("--trade-type", type=int, default=3, help="Kiwoom trde_tp (e.g., 0 보통, 3 시장가)")
    p.add_argument("--cond-price", type=int, default=None, help="cond_uv")
    p.add_argument("--market", default="KRX", help="dmst_stex_tp (KRX/NXT/SOR). mock supports KRX")
    args = p.parse_args()

    # Ensure env is loaded & validated
    _ = Settings.from_env()

    catalog_path = _ensure_catalog()
    print(f"[demo] catalog={catalog_path}")
    catalog = ApiCatalog.load(str(catalog_path))

    api_id = _pick_order_api_id(catalog, args.side)
    spec = catalog.get(api_id)
    body = _build_order_body(args)

    # executor selection is centralized in factory; demo expects real HTTP against KIWOOM_MODE base_url
    from libs.execution.executors import get_executor

    executor = get_executor(catalog=catalog)

    req = {
        "api_id": api_id,
        "method": spec.method or "POST",
        "path": spec.path,  # critical: use catalog path (e.g., /api/dostk/ordr)
        "headers": {},
        "query": {},
        "body": body,
    }

    res = executor.execute(req)  # handles EXECUTION_ENABLED guard internally

    # Print raw response for debugging
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
