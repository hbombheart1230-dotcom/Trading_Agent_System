"""2026-10-01 closeout durable-completion authority (HOST runtime pivot
follow-up). Additive, standalone primitive -- deliberately separate from
libs/runtime/live_loop_lock.py's own responsibility.

Why this is a SEPARATE primitive from the lock (do not overload the lock
with both meanings): the strict-identity lock
(libs/reporting/closeout_maintenance.py::run_closeout_maintenance_with_lock)
only ever answers "is another owner actively running this right now" --
mutual exclusion DURING an attempt. It says nothing about "did a PRIOR
attempt already finish successfully." A lock is released on both normal
completion and on crash/kill (so a later retry is never permanently
blocked) -- which means a process that crashes immediately after a fully
successful run_closeout_maintenance() call (e.g. killed between the
function returning and this wrapper's own release_live_loop_lock() call)
leaves nothing behind proving the work already happened. A later retry,
from either trigger path, would then have no way to know the entire
17-step battery already ran and succeeded for that day, and would re-run
all of it -- expensive, and able to reinstate the exact "closeout
maintenance ran multiple times, writing the same dated artifact paths"
class of risk the lock itself was introduced to prevent.

This module stores one durable fact per (target_day, action_key): whether
a run_closeout_maintenance() attempt for that identity has ever reached
`ok=True` (every step succeeded). It is consulted BEFORE attempting
maintenance (by run_closeout_maintenance_with_lock, the single entrypoint
both libs/runtime/market_status_closeout.py and
scripts/run_closeout_maintenance.py already call -- see that function's
own module-level comment), and written ONLY after the full maintenance
path completes with ok=True. A failed attempt (ok=False, including one
that raised) writes nothing, so a later retry remains possible -- this is
intentionally a SUCCESS-only marker, never a "someone attempted this"
marker.

Storage: a single JSON file, atomic tmp+replace on write (same pattern as
graphs/nodes/build_execution_readiness.py's own snapshot persistence) --
not SQLite, since this is a single-writer-at-a-time fact (the strict lock
already guarantees that) with no concurrent-write contention to resolve,
and not one-file-per-day, since a single small file is simpler to reason
about and audit directly. A read failure (missing file, malformed JSON)
is treated as "not complete" (fail OPEN) -- unlike the lock's own
fail-closed release semantics, the worst case here is a redundant re-run,
never an unsafe trading action, so availability is preferred over
paranoia.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from libs.core.path_isolation import resolve_runtime_write_path

_DEFAULT_COMPLETION_AUTHORITY_PATH = Path("data/state/closeout_completion_authority.json")


def _resolved_path(path: Optional[Path]) -> Path:
    """Same pattern as scripts/step5d_crash_reconciliation.py's own audit-log
    path resolution: a repo-relative default (or an explicit but still
    repo-relative caller path) is redirected under an isolated root while
    running under pytest, so the test suite can never write into this
    repository's real data/state/ directory; an explicit test-owned path
    (e.g. a pytest tmp_path) passes through unchanged. A no-op outside
    pytest."""
    candidate = Path(path) if path is not None else _DEFAULT_COMPLETION_AUTHORITY_PATH
    return resolve_runtime_write_path(candidate)

# Shared across both trigger paths deliberately: run_closeout_maintenance()
# is one indivisible unit of work regardless of which code/trigger caused
# it to run (market-status regular_close, market-status final_refresh, or
# the scheduled CLI fallback) -- see module docstring. This is distinct
# from libs/runtime/market_status_closeout.py's own, unrelated, unmodified
# per-event action_key dedup (f"{day}:{action_name}" for
# processed_market_status_action_keys), which continues to govern ONLY
# whether a given market-status event is re-dispatched, not whether the
# full closeout battery itself needs to run again.
COMPLETION_ACTION_KEY = "daily_closeout_maintenance"


def _completion_key(day: str, action_key: str) -> str:
    return f"{day}:{action_key}"


def _read_completions(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        completions = raw.get("completions")
        return dict(completions) if isinstance(completions, dict) else {}
    except Exception:
        return {}


def read_closeout_completion(
    day: str,
    action_key: str = COMPLETION_ACTION_KEY,
    *,
    path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Returns the durable SUCCESS record for (day, action_key), or None if
    no such record exists (never attempted, attempted but failed, or
    unreadable/corrupt -- all treated identically as "not complete yet")."""
    resolved_path = _resolved_path(path)
    record = _read_completions(resolved_path).get(_completion_key(day, action_key))
    if not isinstance(record, dict):
        return None
    if str(record.get("completion_status") or "") != "SUCCESS":
        return None
    return record


def write_closeout_completion_success(
    day: str,
    action_key: str = COMPLETION_ACTION_KEY,
    *,
    run_id: str,
    trigger: str,
    owner_pid: Optional[int] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Durably records that run_closeout_maintenance() reached ok=True for
    (day, action_key). Best-effort: a write failure here must never raise
    back into the caller, which has already completed the real work this
    only records evidence of."""
    resolved_path = _resolved_path(path)
    owner_identity = None
    try:
        from libs.runtime.live_loop_lock import _process_start_identity

        owner_identity = _process_start_identity(int(owner_pid if owner_pid is not None else os.getpid()))
    except Exception:
        owner_identity = None

    record = {
        "target_day": day,
        "action_key": action_key,
        "completion_status": "SUCCESS",
        "completed_at_epoch": int(time.time()),
        "run_id": run_id,
        "trigger": trigger,
        "owner_pid": int(owner_pid if owner_pid is not None else os.getpid()),
        "owner_identity": owner_identity,
    }
    try:
        completions = _read_completions(resolved_path)
        completions[_completion_key(day, action_key)] = record
        payload = {
            "schema_version": "closeout_completion_authority.v1",
            "completions": completions,
        }
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = resolved_path.with_suffix(resolved_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(resolved_path)
    except Exception:
        pass
    return record


__all__ = [
    "COMPLETION_ACTION_KEY",
    "read_closeout_completion",
    "write_closeout_completion_success",
]
