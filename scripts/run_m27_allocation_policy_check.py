from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.portfolio_allocation import allocate_portfolio_budget


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-1 multi-strategy allocation policy check.")
    p.add_argument("--total-notional", type=float, default=1_000_000)
    p.add_argument("--reserve-ratio", type=float, default=0.1)
    p.add_argument("--json", action="store_true")
    return p


def _default_profiles() -> List[Dict[str, Any]]:
    return [
        {"strategy_id": "trend", "enabled": True, "weight": 0.6, "max_notional_ratio": 0.7},
        {"strategy_id": "mean_reversion", "enabled": True, "weight": 0.3, "max_notional_ratio": 0.4},
        {"strategy_id": "event_driven", "enabled": True, "weight": 0.1, "max_notional_ratio": 0.2},
    ]


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    result = allocate_portfolio_budget(
        _default_profiles(),
        total_notional=float(args.total_notional),
        reserve_ratio=float(args.reserve_ratio),
    )

    failures: List[str] = list(result.get("failures") or [])
    allocatable = float(result.get("allocatable_notional") or 0.0)
    allocation_total = float(result.get("allocation_total") or 0.0)
    if allocation_total > allocatable + 1e-8:
        failures.append("allocation_total > allocatable_notional")

    for row in result.get("allocations") or []:
        if not isinstance(row, dict):
            continue
        max_notional = row.get("max_notional")
        if max_notional is None:
            continue
        allocated = float(row.get("allocated_notional") or 0.0)
        if allocated > float(max_notional) + 1e-8:
            failures.append(f"{row.get('strategy_id')} exceeds max_notional")

    ok = len(failures) == 0
    out = {
        "ok": ok,
        "total_notional": float(result.get("total_notional") or 0.0),
        "reserve_ratio": float(result.get("reserve_ratio") or 0.0),
        "allocatable_notional": allocatable,
        "allocation_total": allocation_total,
        "unallocated_notional": float(result.get("unallocated_notional") or 0.0),
        "active_strategy_total": int(result.get("active_strategy_total") or 0),
        "allocations": result.get("allocations") or [],
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} active_strategy_total={out['active_strategy_total']} "
            f"allocatable_notional={out['allocatable_notional']:.6f} "
            f"allocation_total={out['allocation_total']:.6f} "
            f"unallocated_notional={out['unallocated_notional']:.6f} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
