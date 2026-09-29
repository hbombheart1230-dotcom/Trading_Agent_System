"""P0-A (real-readiness hardening, 2026-09-17): deterministic, every-tick
open/pending-order reconciliation snapshot.

Mirrors graphs/nodes/build_portfolio_snapshot.py's own pattern exactly
(unconditional read at the same point in the tick, `state["<x>_reader"]`
override hook for tests, an explicit `_health`-style block) -- this is the
"canonical tick flow's authoritative fetch location" the task asked to be
found: wired into libs/runtime/commander/session_context.py's
`build_integrated_chain_session_context`, immediately after
`build_portfolio_snapshot_fn`, i.e. BEFORE strategist/scanner/monitor/
decision/execution ever run, on every tick, unconditionally.

Deliberately does NOT use the generic skill-runner path
(hydrate_skill_results_node / state["skill_runner"]) -- uses
KiwoomOrderFillReader (same broker-truth-client family as
KiwoomPortfolioReader) instead, which resolves its own executor via
get_executor() independent of anything a caller/test injects into
state["skill_runner"]. This is precisely why this fetch does not repeat
the ~29-test regression the earlier, reverted execute_from_packet.py-level
force-hydration attempt caused.

execute_from_packet.py's `_evaluate_open_order_reconciliation_guard` is the
sole consumer -- it treats this snapshot's absence/staleness/error as
UNKNOWN and fails closed (see that function's own docstring).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from libs.read.kiwoom_order_fill_reader import KiwoomOrderFillReader


def build_open_order_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("open_order_reader") is not None:
        reader = state["open_order_reader"]
    else:
        reader = KiwoomOrderFillReader.from_env()

    health: Dict[str, Any] = {
        "reader_ok": True,
        "reader_error": "",
        "source": "reader",
        "fetched_epoch": int(time.time()),
    }
    rows: List[Dict[str, Any]] = []
    try:
        rows = reader.get_open_orders_now()
    except Exception as exc:
        health["reader_ok"] = False
        health["reader_error"] = f"{type(exc).__name__}: {exc}"
        health["source"] = "reader_error"
        rows = []

    state["open_order_snapshot"] = {
        "rows": rows,
        "_health": health,
    }
    return state
