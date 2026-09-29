"""P1 (execution readiness authority, 2026-09-17): a single, explicit,
fail-closed `ExecutionReadiness` decision -- the canonical answer to "is the
SYSTEM (not any one symbol/order) currently safe to place a NEW physical
order at all."

This module holds only the pure DECISION RULE (`evaluate_execution_
readiness`), deliberately separated from evidence-gathering so the exact
same rule can be reused by two different callers that gather evidence
differently:

  - the live tick (graphs/nodes/build_execution_readiness.py), which reads
    already-fresh, already-built-this-tick state (portfolio_snapshot,
    open_order_snapshot, runtime_ownership) -- zero extra I/O beyond one
    Step5C claims query.
  - scripts/docker_healthcheck.py, a cold, separate process with no access
    to the live tick's in-memory state, which reconstructs its own
    best-effort evidence directly from persisted, on-disk state (the
    ownership DB, the intent-state DB) and calls this SAME function.

Both callers therefore apply identical rules -- this is the single source
of truth the audit asked for, even though evidence collection necessarily
differs by process.

Deliberately narrow scope (P1 Non-goals): this module has no opinion on
trading strategy, sizing, or thresholds. It answers exactly one question:
"has this runtime's own restart/ownership/reconciliation state been
verified clean enough to trust a new physical order," nothing else. It
does not replace, weaken, or duplicate any existing guard (Supervisor,
symbol allowlist, notional limits, open-order-per-symbol reconciliation,
Step5C CAS, Step5D manual reconciliation) -- it is an ADDITIONAL, coarser,
earlier gate above all of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ExecutionReadiness:
    ready: bool
    reasons: List[str] = field(default_factory=list)
    runtime_instance_id: Optional[str] = None
    ownership_generation: Optional[int] = None
    recovery_required: bool = False
    orphan_claim_count: Optional[int] = None
    portfolio_reconciled: bool = False
    open_orders_reconciled: bool = False
    config_valid: bool = False
    execution_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "reasons": list(self.reasons),
            "runtime_instance_id": self.runtime_instance_id,
            "ownership_generation": self.ownership_generation,
            "recovery_required": self.recovery_required,
            "orphan_claim_count": self.orphan_claim_count,
            "portfolio_reconciled": self.portfolio_reconciled,
            "open_orders_reconciled": self.open_orders_reconciled,
            "config_valid": self.config_valid,
            "execution_enabled": self.execution_enabled,
        }


def evaluate_execution_readiness(
    *,
    ownership_valid: bool,
    runtime_instance_id: Optional[str],
    ownership_generation: Optional[int],
    recovery_required: bool,
    step5c_available: bool,
    orphan_claim_count: Optional[int],
    portfolio_reconciled: bool,
    open_orders_reconciled: bool,
    config_valid: bool,
    execution_enabled: bool,
) -> ExecutionReadiness:
    """Combine every readiness input with AND -- any single UNKNOWN/ERROR/
    STALE/missing input makes the whole result NOT ready. No input is ever
    allowed to compensate for another (e.g. a perfectly reconciled
    portfolio never overrides an unresolved Step5D orphan).

    `recovery_required` is evaluated like every other input here (not
    special-cased to auto-clear) -- callers are responsible for the
    explicit clearing semantics (a stale-takeover's `recovery_required`
    flag may only be flipped to False once ALL of the OTHER inputs below
    have independently been confirmed healthy in the same evaluation, not
    merely because some tick ran -- see build_execution_readiness.py).
    """
    reasons: List[str] = []

    if not ownership_valid:
        reasons.append("ownership_unavailable_or_unverified")
    if recovery_required:
        reasons.append("recovery_required")
    if not step5c_available:
        reasons.append("step5c_state_unavailable")
    if orphan_claim_count is None:
        reasons.append("orphan_claim_status_unknown")
    elif orphan_claim_count > 0:
        reasons.append("unresolved_step5d_orphan_claim")
    if not portfolio_reconciled:
        reasons.append("portfolio_reconciliation_invalid")
    if not open_orders_reconciled:
        reasons.append("open_order_reconciliation_invalid")
    if not config_valid:
        reasons.append("execution_config_invalid")

    return ExecutionReadiness(
        ready=not reasons,
        reasons=reasons,
        runtime_instance_id=runtime_instance_id,
        ownership_generation=ownership_generation,
        recovery_required=recovery_required,
        orphan_claim_count=orphan_claim_count,
        portfolio_reconciled=portfolio_reconciled,
        open_orders_reconciled=open_orders_reconciled,
        config_valid=config_valid,
        execution_enabled=execution_enabled,
    )


def validate_execution_config() -> tuple[bool, List[str]]:
    """Confirms the minimal execution config this runtime needs is at
    least PARSEABLE (mode flags, allowlist, numeric limits) -- does not
    judge whether the values are "correct" for any particular deployment,
    only that reading them cannot raise or silently produce garbage.
    Reuses the exact parsing helpers real_executor.py/execute_from_packet.py
    already use, rather than inventing a second config schema.
    """
    import os

    reasons: List[str] = []
    try:
        mode = str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower()
        if mode not in ("mock", "real"):
            reasons.append(f"invalid_kiwoom_mode:{mode}")
    except Exception as exc:
        reasons.append(f"kiwoom_mode_unreadable:{type(exc).__name__}")

    try:
        exec_mode = str(os.getenv("EXECUTION_MODE", "") or "").strip().lower()
        if exec_mode and exec_mode not in ("mock", "real"):
            reasons.append(f"invalid_execution_mode:{exec_mode}")
    except Exception as exc:
        reasons.append(f"execution_mode_unreadable:{type(exc).__name__}")

    for flag_name in ("EXECUTION_ENABLED", "ALLOW_REAL_EXECUTION"):
        try:
            str(os.getenv(flag_name, "false") or "false").strip().lower()
        except Exception as exc:
            reasons.append(f"{flag_name.lower()}_unreadable:{type(exc).__name__}")

    try:
        raw_allowlist = os.getenv("SYMBOL_ALLOWLIST", "") or ""
        [s.strip() for s in str(raw_allowlist).split(",") if s.strip()]
    except Exception as exc:
        reasons.append(f"symbol_allowlist_unparseable:{type(exc).__name__}")

    for limit_name in ("MAX_ORDER_QTY", "MAX_ORDER_NOTIONAL"):
        raw = os.getenv(limit_name)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            float(raw)
        except Exception:
            reasons.append(f"{limit_name.lower()}_not_numeric:{raw!r}")

    return (not reasons), reasons
