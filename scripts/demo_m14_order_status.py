"""M14 demo: Order status / fills lookup (MOCK) with pretty output.

Notes:
- kt00007 works well for matching an order number (ord_no).
- kt00009 is sensitive to required params; for MOCK it requires `mrkt_tp`.
- Kiwoom enforces per-API rate limits; this script avoids rapid multi-tries by default.

Examples:
  python scripts/demo_m14_order_status.py --ord-no 0027817 --symbol 005930 --ord-dt 20260212
  python scripts/demo_m14_order_status.py --ord-no 0027817 --symbol 005930 --ord-dt 20260212 --qry-tp 4
  python scripts/demo_m14_order_status.py --ord-no 0027817 --symbol 005930 --ord-dt 20260212 --qry-tp 3
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    import scripts.build_api_catalog as bac
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    bac.main()
    return catalog_path


def _require_api(catalog: ApiCatalog, api_id: str, title: str) -> str:
    if catalog.has(api_id):
        return api_id
    for spec in catalog.list_specs():
        if (spec.title or "").strip() == title:
            return spec.api_id
    raise ApiNotFoundError(f"Missing API: {api_id} / {title}")


def _call(executor, catalog: ApiCatalog, api_id: str, body: Dict[str, Any]):
    spec = catalog.get(api_id)
    req = {
        "api_id": api_id,
        "method": spec.method or "POST",
        "path": spec.path,
        "headers": {},
        "query": {},
        "body": body,
    }
    return executor.execute(req)


def _norm_int(s: Any) -> Optional[int]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    if not isinstance(s, str):
        return None
    t = s.strip().replace(",", "").lstrip("+")
    if t == "":
        return None
    try:
        return int(t)
    except Exception:
        try:
            return int(float(t))
        except Exception:
            return None


def _norm_code(code: str) -> str:
    if not code:
        return code
    return code[1:] if code.startswith("A") and len(code) >= 2 else code


def _pick(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    v = payload.get(key)
    return v if isinstance(v, list) else []


def _pretty_rows(rows: List[Dict[str, Any]]) -> str:
    cols = [
        ("ord_no", "주문번호"),
        ("stk_cd", "종목"),
        ("io_tp_nm", "구분"),
        ("trde_tp", "매매"),
        ("ord_qty", "주문수량"),
        ("ord_uv", "주문가"),
        ("cntr_qty", "체결수량"),
        ("cntr_uv", "체결가"),
        ("acpt_tp", "상태"),
        ("ord_tm", "주문시각"),
    ]

    normed = []
    for r in rows:
        nr = dict(r)
        nr["stk_cd"] = _norm_code(str(nr.get("stk_cd", "")))
        for k in ("ord_qty", "ord_uv", "cntr_qty", "cntr_uv", "ord_remnq", "cnfm_qty"):
            iv = _norm_int(nr.get(k))
            if iv is not None:
                nr[k] = str(iv)
        normed.append(nr)

    widths = []
    for k, label in cols:
        maxlen = len(label)
        for r in normed:
            maxlen = max(maxlen, len(str(r.get(k, ""))))
        widths.append(maxlen)

    lines = []
    header = " | ".join(label.ljust(w) for (_, label), w in zip(cols, widths))
    sep = "-+-".join("-" * w for w in widths)
    lines.append(header)
    lines.append(sep)
    for r in normed:
        line = " | ".join(str(r.get(k, "")).ljust(w) for (k, _), w in zip(cols, widths))
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ord-no", required=True, help="order number (e.g., 0027817)")
    p.add_argument("--symbol", default=None, help="optional stock code to narrow results (e.g., 005930)")
    p.add_argument("--side", choices=["all", "sell", "buy"], default="all")
    p.add_argument("--market", default="KRX", help="dmst_stex_tp (KRX/NXT/SOR). mock supports KRX")
    p.add_argument("--mrkt-tp", default="0", help="kt00009 required: mrkt_tp (0=전체, 1=KOSPI, 2=KOSDAQ etc.)")
    p.add_argument("--ord-dt", default="", help="order date YYYYMMDD (blank may work, but recommended)")
    p.add_argument("--qry-tp", default="4", help="kt00009 qry_tp: 1주문순 2역순 3미체결 4체결내역만")
    args = p.parse_args()

    _ = Settings.from_env()
    catalog_path = _ensure_catalog()
    print(f"[demo] catalog={catalog_path}")
    catalog = ApiCatalog.load(str(catalog_path))

    from libs.execution.executors import get_executor
    executor = get_executor(catalog=catalog)

    kt00007 = _require_api(catalog, "kt00007", "계좌별주문체결내역상세요청")
    kt00009 = _require_api(catalog, "kt00009", "계좌별주문체결현황요청")

    sell_tp_map = {"all": "0", "sell": "1", "buy": "2"}
    sell_tp = sell_tp_map[args.side]

    # --- kt00007 detail ---
    body_00007 = {
        "qry_tp": "2",
        "stk_bond_tp": "1",
        "sell_tp": sell_tp,
        "stk_cd": args.symbol or "",
        "fr_ord_no": args.ord_no,
        "dmst_stex_tp": args.market,
    }
    res7 = _call(executor, catalog, kt00007, body_00007)
    payload7 = res7.response.payload if res7 and res7.response else {}
    rows7 = _pick(payload7, "acnt_ord_cntr_prps_dtl")
    matched7 = [r for r in rows7 if str(r.get("ord_no", "")).strip() == args.ord_no]

    print("\n[kt00007] matched rows")
    if matched7:
        print(_pretty_rows(matched7))
    else:
        print("(no exact match in returned page; show top 5 rows)")
        print(_pretty_rows(rows7[:5]))

    # --- kt00009 summary (single call to avoid rate limit) ---
    body_00009 = {
        "ord_dt": args.ord_dt,
        "qry_tp": str(args.qry_tp),
        "mrkt_tp": str(args.mrkt_tp),   # REQUIRED (Kiwoom error 1511 if missing)
        "stk_bond_tp": "1",
        "sell_tp": sell_tp,
        "stk_cd": args.symbol or "",
        "fr_ord_no": args.ord_no,
        "dmst_stex_tp": args.market,
    }
    res9 = _call(executor, catalog, kt00009, body_00009)
    payload9 = res9.response.payload if res9 and res9.response else {}
    rows9 = _pick(payload9, "acnt_ord_cntr_prst_array")
    matched9 = [r for r in rows9 if str(r.get("ord_no", "")).strip() == args.ord_no]

    print(f"\n[kt00009] qry_tp={args.qry_tp} mrkt_tp={args.mrkt_tp}")
    if matched9:
        print(_pretty_rows(matched9))
    elif rows9:
        print("(no exact match; show top 5 rows)")
        print(_pretty_rows(rows9[:5]))
    else:
        print(res9)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
