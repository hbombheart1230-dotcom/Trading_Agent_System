from __future__ import annotations

"""Durable UNKNOWN-broker-outcome quarantine (Phase 1 Step 5B).

Extracted from graphs/nodes/execute_from_packet.py (Phase 1 Step 5B Fix 3)
so every live path that can physically submit a broker mutation shares the
*same* durable per-symbol lock state -- not just the canonical
execute_from_packet.py guard chain, but also
libs/skills/runner.py::CompositeSkillRunner (reached via
libs/tools/tool_facade.py::ToolFacade.order_execute and
libs/agent/executor/executor_agent.py::ExecutorAgent), which previously
never checked or wrote this state at all. A symbol quarantined by one path
is now respected by the other, and vice versa.

Behavior is unchanged from the Step 5B Safety Fix 2 design (commit
6b17925) for the existing execute_from_packet.py call sites -- this is an
extraction, not a redesign:

- Fail-closed decisions are based on the per-symbol lock file's
  *existence*, never on successfully parsing its content.
- The lock file is created atomically (O_CREAT|O_EXCL) and never
  auto-deleted by any code path here.
- If durable persistence itself fails (disk full / permission denied),
  the process-wide GLOBAL_MUTATION_HALT activates as a last-resort
  fallback that blocks every mutation regardless of symbol.

New in Fix 3: GLOBAL_MUTATION_HALT is additionally backed by a durable,
atomically-created marker file (same existence-based contract as a
per-symbol lock), so a process restart also fails closed instead of
silently losing the halt the moment the in-memory flag is gone.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from libs.core.path_isolation import isolate_canonical_path_for_pytest


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


_UNKNOWN_QUARANTINE_DEFAULT_DIR = Path("data/state/execution_unknown_quarantine")
_GLOBAL_MUTATION_HALT_MARKER_NAME = "_global_mutation_halt.lock"

# Process-wide, module-level by design (mutated in place, shared by every
# importer of this module -- graphs/nodes/execute_from_packet.py re-exports
# this exact dict object as its own `_GLOBAL_MUTATION_HALT` name for
# backward compatibility with existing test fixtures that reset it).
GLOBAL_MUTATION_HALT: Dict[str, Any] = {"active": False, "reason": "", "since_epoch": 0, "pid": 0}


def quarantine_dir(override_path: Optional[str] = None) -> Path:
    raw = override_path or os.getenv("UNKNOWN_QUARANTINE_GUARD_PATH", "")
    if str(raw or "").strip():
        return Path(str(raw))
    return isolate_canonical_path_for_pytest(
        _UNKNOWN_QUARANTINE_DEFAULT_DIR,
        canonical_path=_UNKNOWN_QUARANTINE_DEFAULT_DIR,
        isolated_name="execution_unknown_quarantine",
    )


def quarantine_lock_path(symbol: str, override_path: Optional[str] = None) -> Path:
    return quarantine_dir(override_path) / f"{symbol}.lock"


def _global_mutation_halt_marker_path(override_path: Optional[str] = None) -> Path:
    return quarantine_dir(override_path) / _GLOBAL_MUTATION_HALT_MARKER_NAME


def write_quarantine_lock_if_absent(lock_path: Path, payload: Dict[str, Any]) -> bool:
    """Atomically create a lock/marker file. Returns True iff it durably
    exists after this call (just created, or already existed from an
    earlier attempt / a prior process incarnation) -- both mean "the block
    is in effect", which is success, not failure. Returns False only when
    the file could not be created and does not already exist -- a genuine
    persistence failure."""
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return True
    except Exception:
        try:
            return lock_path.exists()
        except Exception:
            return False


def activate_global_mutation_halt(reason: str, *, now_epoch: int, override_path: Optional[str] = None) -> None:
    """Activate the process-wide mutation halt and persist a durable marker
    (Phase 1 Step 5B Fix 3, closes HIGH3: the in-memory flag alone does not
    survive a process restart). The marker uses the exact same atomic,
    existence-based, never-auto-deleted contract as a per-symbol quarantine
    lock, so a fresh process that checks global_mutation_halt_active()
    before ever calling this function itself still fails closed if a
    marker from a prior incarnation exists."""
    if not GLOBAL_MUTATION_HALT["active"]:
        GLOBAL_MUTATION_HALT["active"] = True
        GLOBAL_MUTATION_HALT["reason"] = str(reason or "")
        GLOBAL_MUTATION_HALT["since_epoch"] = int(now_epoch)
        GLOBAL_MUTATION_HALT["pid"] = os.getpid()
    try:
        write_quarantine_lock_if_absent(
            _global_mutation_halt_marker_path(override_path),
            {
                "pid": os.getpid(),
                "activated_at_epoch": int(now_epoch),
                "reason": str(reason or ""),
            },
        )
    except Exception:
        # Durable marker write is best-effort on top of the in-memory flag,
        # which is already active for the remaining lifetime of this
        # process regardless.
        pass


def global_mutation_halt_active(override_path: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """Returns (active, details). Checks the in-memory flag first, then the
    durable marker file (Fix 3: covers a fresh process that never itself
    called activate_global_mutation_halt but must still fail closed if a
    marker from a prior incarnation exists). Hydrates the in-memory flag
    when the marker is found so later checks in this same process are
    cheap and consistent."""
    if GLOBAL_MUTATION_HALT["active"]:
        return True, dict(GLOBAL_MUTATION_HALT)
    try:
        marker_path = _global_mutation_halt_marker_path(override_path)
        if not marker_path.exists():
            return False, {}
    except Exception:
        return False, {}

    details: Dict[str, Any] = {"reason": "durable_global_mutation_halt_marker_present", "since_epoch": 0}
    try:
        record = json.loads(marker_path.read_text(encoding="utf-8"))
        if isinstance(record, dict):
            details["reason"] = str(record.get("reason") or details["reason"])
            details["since_epoch"] = _coerce_int(record.get("activated_at_epoch"), 0)
    except Exception:
        # Existence alone is the fail-closed signal, same as a per-symbol
        # lock -- an unreadable/partially-written marker still halts.
        pass
    GLOBAL_MUTATION_HALT["active"] = True
    GLOBAL_MUTATION_HALT["reason"] = str(details.get("reason") or "")
    GLOBAL_MUTATION_HALT["since_epoch"] = _coerce_int(details.get("since_epoch"), 0)
    GLOBAL_MUTATION_HALT["pid"] = os.getpid()
    return True, dict(GLOBAL_MUTATION_HALT)


def evaluate_unknown_quarantine_guard(
    symbol: str, *, override_path: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """(allowed, reason, details) for an already-normalized, non-empty
    symbol. Callers that need "not a mutation action" / "no symbol"
    passthrough semantics keep that check themselves before calling this
    (see graphs/nodes/execute_from_packet.py::_evaluate_unknown_quarantine_guard
    for the existing wrapper)."""
    details: Dict[str, Any] = {}
    halted, halt_details = global_mutation_halt_active(override_path)
    if halted:
        details["global_mutation_halt"] = True
        details["global_mutation_halt_reason"] = str(halt_details.get("reason") or "")
        details["global_mutation_halt_since_epoch"] = _coerce_int(halt_details.get("since_epoch"), 0)
        return False, "global_mutation_halt_active", details

    details["symbol"] = symbol
    lock_path = quarantine_lock_path(symbol, override_path)
    try:
        lock_exists = lock_path.exists()
    except Exception:
        # Cannot even determine whether a quarantine lock exists for this
        # symbol -> cannot safely treat it as "not quarantined".
        details["quarantine_store_unreadable"] = True
        return False, "quarantine_store_unreadable_fail_closed", details

    if not lock_exists:
        return True, "", details

    details["quarantined"] = True
    try:
        record = json.loads(lock_path.read_text(encoding="utf-8"))
        if isinstance(record, dict):
            details.update(
                {
                    "quarantine_pid": record.get("pid"),
                    "quarantined_at_epoch": _coerce_int(record.get("created_at_epoch"), 0),
                    "quarantine_reason": str(record.get("reason") or ""),
                    "quarantine_operation": str(record.get("operation") or ""),
                    "quarantine_run_id": str(record.get("run_id") or ""),
                    "quarantine_exception_type": str(record.get("exception_type") or ""),
                }
            )
    except Exception:
        details["quarantine_lock_unreadable"] = True
    return False, "symbol_quarantined_pending_reconciliation", details


def quarantine_symbol_for_unknown_outcome(
    *,
    symbol: str,
    operation: str,
    now_epoch: int,
    run_id: str = "",
    exception_type: str = "",
    reason: str = "broker_outcome_unknown",
    override_path: Optional[str] = None,
) -> bool:
    """Durably quarantine `symbol`. Returns whether it is now (or already
    was) durably blocked. On a genuine persistence failure (lock file could
    not be created and does not already exist -- or no resolvable symbol at
    all), activates the process-wide global mutation halt so the failure
    can never be silently read as "safe to proceed" for ANY symbol."""
    if not symbol:
        activate_global_mutation_halt(
            "unknown_outcome_missing_symbol", now_epoch=now_epoch, override_path=override_path
        )
        return False
    lock_path = quarantine_lock_path(symbol, override_path)
    payload = {
        "pid": os.getpid(),
        "created_at_epoch": int(now_epoch),
        "symbol": symbol,
        "operation": str(operation or "").strip().upper(),
        "reason": str(reason or "broker_outcome_unknown"),
        "run_id": str(run_id or ""),
        "exception_type": str(exception_type or ""),
    }
    persisted = write_quarantine_lock_if_absent(lock_path, payload)
    if not persisted:
        activate_global_mutation_halt(
            f"quarantine_lock_write_failed:{symbol}", now_epoch=now_epoch, override_path=override_path
        )
    return persisted


__all__ = [
    "GLOBAL_MUTATION_HALT",
    "activate_global_mutation_halt",
    "evaluate_unknown_quarantine_guard",
    "global_mutation_halt_active",
    "quarantine_dir",
    "quarantine_lock_path",
    "quarantine_symbol_for_unknown_outcome",
    "write_quarantine_lock_if_absent",
]
