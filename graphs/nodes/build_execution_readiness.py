"""P1 (execution readiness authority, 2026-09-17): deterministic, every-tick
`ExecutionReadiness` evaluation -- the canonical evidence this runtime uses
to decide whether a NEW physical BUY/SELL order may even be attempted.

Mirrors graphs/nodes/build_portfolio_snapshot.py / build_open_order_
snapshot.py's own pattern: unconditional every-tick read, wired into
libs/runtime/commander/session_context.py's `build_integrated_chain_
session_context`, immediately after `build_open_order_snapshot_fn` (whose
output this node consumes, alongside `build_portfolio_snapshot_fn`'s) --
i.e. BEFORE strategist/scanner/monitor/decision/execution ever run, on
every tick, unconditionally.

graphs/nodes/execute_from_packet.py's `_evaluate_execution_readiness_guard`
is the sole enforcement point -- it only ever CONSUMES
`state["execution_readiness"]["ready"]`; it never recomputes any of this
node's evidence itself. `scripts/docker_healthcheck.py` calls
`libs.execution.execution_readiness.evaluate_execution_readiness` (the same
pure decision function this node calls) against its own, independently
gathered on-disk evidence -- single source of truth for the DECISION RULE,
even though the two callers necessarily gather evidence differently (one
has a live tick's fresh in-memory state, the other is a cold, separate
process).

Explicit recovery-clear semantics (P1 Section 6): a stale-takeover's
`recovery_required` flag (set once, at ownership acquisition, in
libs/runtime/live_loop_runner.py) is cleared here -- and ONLY here -- the
first tick every OTHER readiness input (ownership presence, Step5C
availability, zero orphan claims, portfolio reconciliation, open-order
reconciliation, config validity) is simultaneously healthy. A tick where
even one other input is still bad does NOT clear it, no matter how many
ticks have run -- "one successful tick" is deliberately not the clearing
condition; "this tick's full reconciliation evidence is clean" is.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from libs.core.path_isolation import isolate_canonical_path_for_pytest
from libs.execution.execution_readiness import evaluate_execution_readiness, validate_execution_config

_DEFAULT_OPEN_ORDER_SNAPSHOT_MAX_AGE_SEC = 120
_EXECUTION_READINESS_SNAPSHOT_DEFAULT_PATH = Path("data/state/execution_readiness.json")


def _is_trueish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _portfolio_reconciled(state: Dict[str, Any]) -> bool:
    snap = state.get("portfolio_snapshot")
    health = snap.get("_health") if isinstance(snap, dict) else None
    if not isinstance(health, dict):
        return False
    if not _is_trueish(health.get("reader_ok", False)):
        return False
    mismatch = _is_trueish(health.get("positions_mismatch_detected"))
    reconciled = _is_trueish(health.get("reconciliation_applied"))
    if mismatch and not reconciled:
        return False
    return True


def _open_orders_reconciled(state: Dict[str, Any]) -> bool:
    snap = state.get("open_order_snapshot")
    if not isinstance(snap, dict):
        return False
    health = snap.get("_health")
    health = health if isinstance(health, dict) else {}
    if not _is_trueish(health.get("reader_ok", False)):
        return False
    rows = snap.get("rows")
    if not isinstance(rows, list):
        return False
    fetched_epoch = _coerce_int(health.get("fetched_epoch"), -1)
    if fetched_epoch < 0:
        return False
    max_age = _coerce_int(
        os.getenv("OPEN_ORDER_SNAPSHOT_MAX_AGE_SECONDS"), _DEFAULT_OPEN_ORDER_SNAPSHOT_MAX_AGE_SEC
    )
    if int(time.time()) - fetched_epoch > max_age:
        return False
    return True


def _step5c_orphan_claims(state: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
    """(step5c_available, orphan_claim_count) -- count is None when
    unknown (store unreachable), never a false "0"."""
    try:
        store = state.get("intent_state_store")
        if store is None:
            from libs.supervisor.intent_state_store import SQLiteIntentStateStore

            store = SQLiteIntentStateStore()
        claims = store.list_active_physical_claims(limit=200)
        return True, len(claims)
    except Exception:
        return False, None


def _execution_readiness_snapshot_path(state: Dict[str, Any]) -> Path:
    raw = str(state.get("execution_readiness_snapshot_path") or "").strip()
    if raw:
        return Path(raw)
    return isolate_canonical_path_for_pytest(
        _EXECUTION_READINESS_SNAPSHOT_DEFAULT_PATH,
        canonical_path=_EXECUTION_READINESS_SNAPSHOT_DEFAULT_PATH,
        isolated_name="execution_readiness.json",
    )


def _persist_execution_readiness_snapshot(state: Dict[str, Any], readiness_dict: Dict[str, Any]) -> None:
    """Writes the SAME dict `execute_from_packet.py`'s readiness guard
    just consumed to disk, atomically -- this is what makes
    scripts/docker_healthcheck.py (a separate, cold process with no
    access to this tick's in-memory state) a genuine single-source-of-
    truth READER rather than a second, independent reimplementation of
    these rules. Best-effort: a write failure here must never affect
    execution admission itself (already decided, above this call)."""
    try:
        path = _execution_readiness_snapshot_path(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"execution_readiness": readiness_dict, "computed_at_epoch": int(time.time())}
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def build_execution_readiness(state: Dict[str, Any]) -> Dict[str, Any]:
    ownership = state.get("runtime_ownership")
    ownership = ownership if isinstance(ownership, dict) else None
    ownership_valid = ownership is not None
    runtime_instance_id = ownership.get("instance_id") if ownership else None
    ownership_generation = ownership.get("generation") if ownership else None
    recovery_required = bool(ownership.get("recovery_required")) if ownership else False

    step5c_available, orphan_count = _step5c_orphan_claims(state)
    portfolio_ok = _portfolio_reconciled(state)
    open_orders_ok = _open_orders_reconciled(state)
    config_ok, _config_reasons = validate_execution_config()
    execution_enabled = _is_trueish(os.getenv("EXECUTION_ENABLED", "false"))

    if (
        recovery_required
        and ownership_valid
        and step5c_available
        and orphan_count == 0
        and portfolio_ok
        and open_orders_ok
        and config_ok
    ):
        recovery_required = False
        if ownership is not None:
            ownership["recovery_required"] = False
            ownership["recovery_cleared_at_epoch"] = int(time.time())

    readiness = evaluate_execution_readiness(
        ownership_valid=ownership_valid,
        runtime_instance_id=runtime_instance_id,
        ownership_generation=ownership_generation,
        recovery_required=recovery_required,
        step5c_available=step5c_available,
        orphan_claim_count=orphan_count,
        portfolio_reconciled=portfolio_ok,
        open_orders_reconciled=open_orders_ok,
        config_valid=config_ok,
        execution_enabled=execution_enabled,
    )
    readiness_dict = readiness.to_dict()
    state["execution_readiness"] = readiness_dict
    _persist_execution_readiness_snapshot(state, readiness_dict)
    return state
