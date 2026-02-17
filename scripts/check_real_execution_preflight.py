from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.real_executor import RealExecutor


def _build_req(symbol: str) -> PreparedRequest:
    sym = str(symbol or "").strip()
    return PreparedRequest(
        api_id="ORDER_SUBMIT",
        method="POST",
        path="/api/dostk/ordr",
        headers={},
        query={},
        body={"stk_cd": sym, "ord_qty": "1"} if sym else {},
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check RealExecutor preflight guards and denial reasons.")
    p.add_argument("--symbol", default="", help="Optional symbol for allowlist validation preflight.")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    ex = RealExecutor()
    req = _build_req(str(args.symbol or ""))
    pf = ex.preflight_check(req)

    out: Dict[str, Any] = {
        "ok": bool(pf.get("ok")),
        "code": str(pf.get("code") or ""),
        "message": str(pf.get("message") or ""),
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok={out['ok']} code={out['code']} message={out['message']}")

    return 0 if out["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
