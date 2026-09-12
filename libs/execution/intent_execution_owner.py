"""Durable logical execution ownership composed with existing broker semantics."""
from __future__ import annotations

import uuid

from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.intent_identity import (
    bind_intent,
    physical_order_fingerprint,
)
from libs.supervisor.intent_state_store import (
    INTENT_STATE_EXECUTED,
    INTENT_STATE_FAILED,
    SQLiteIntentStateStore,
)

_TERMINAL_STATES = frozenset({INTENT_STATE_EXECUTED, INTENT_STATE_FAILED})


def _store():
    # Step5C Fix1: no locally-computed default -- the canonical resolver
    # inside SQLiteIntentStateStore (shared by ApprovalService and every
    # other consumer) is the single source of truth for this path.
    return SQLiteIntentStateStore()


def execute_owned_order(*, state: dict, order: dict, request, executor, normalize, child: bool = False, on_submit=None) -> dict:
    """Call only after existing policy approval; never bypass those guards.

    This is the single canonical claim-dispatch-finish sequence for every
    real broker mutation path in this codebase (Step5C Fix2 HIGH1): there
    is deliberately no "state already reads EXECUTING, so just dispatch"
    shortcut anywhere else in this codebase (see libs/skills/runner.py) --
    reading a state value is not ownership evidence. The only way to
    legitimately reach executor.execute() below is to win the atomic
    claim_execution() CAS in *this* call.

    Composed with a second, independent guard (Fix2 HIGH3): claim_execution
    guarantees at most one owner per intent_id, but two different intent_id
    values (e.g. the automated content-hash scheme and the manual approval
    uuid4 scheme) can still describe the same real-world physical order.
    claim_physical_order is checked first and guarantees at most one active
    lease per physical order shape, independent of intent_id or which path
    is asking. The physical lease is deliberately not auto-released on an
    ambiguous outcome (crash, UNKNOWN, persistence failure) -- only a
    genuine terminal state (EXECUTED/FAILED) releases it, matching this
    module's existing no-implicit-replay philosophy.

    normalize is the caller's existing Step5B outcome normalization boundary.
    No transport classification is invented by this ownership layer.
    """
    owner = uuid.uuid4().hex
    iid = ''
    physical_key = ''
    store = None
    phys_claim: dict = {}
    try:
        iid = bind_intent(state, order, child=child)
        physical_key = physical_order_fingerprint(state, order)
        if physical_key is None:
            # Step5C Fix3: the order cannot be canonicalized into a valid
            # physical order identity at all (unrecognized action, invalid
            # symbol, missing/invalid qty, or a LIMIT order with no real
            # price) -- fail closed rather than fingerprint or dispatch a
            # malformed order.
            claim = {'claimed': False, 'reason': 'invalid_physical_order'}
        else:
            store = _store()
            phys_claim = store.claim_physical_order(physical_key, intent_id=iid, owner=owner)
            if not phys_claim.get('claimed'):
                claim = {'claimed': False, 'reason': phys_claim.get('reason') or 'physical_order_already_claimed'}
            else:
                # Step5C Fix3 (HIGH2): a caller-supplied intent_id does not
                # carry execution authority by itself. Only an identity
                # bind_intent itself just minted (verified by recomputing
                # its deterministic scheme) may be self-admitted by
                # claim_execution; anything else must already exist as a
                # persisted, approved OrderIntent.
                claim = store.claim_execution(iid, fingerprint=physical_key, owner=owner)
                if not claim.get('claimed') and not phys_claim.get('reused'):
                    # Reserved the physical lease but could not win the
                    # intent-level CAS -- no ambiguity (nothing was
                    # dispatched), so it is safe to release immediately
                    # rather than block a future legitimate attempt at this
                    # physical order forever.
                    try:
                        store.release_physical_order(physical_key, intent_id=iid)
                    except Exception:
                        pass
    except Exception as exc:
        claim = {'claimed': False, 'reason': 'intent_CAS_unavailable', 'error_type': type(exc).__name__}
    if not claim.get('claimed'):
        verdict = normalize(None)
        verdict.update(allowed=False, ok=False, execution_ok=False, broker_outcome='NOT_SENT',
                       submission_attempts=0, submission_phase='not_dispatched',
                       reason=claim['reason'], intent_id=iid, intent_claim=claim,
                       physical_order_key=physical_key,
                       reconciliation_required=claim.get('state') == 'executing')
        return verdict

    try:
        if on_submit is not None:
            on_submit()
        result = executor.execute(request)
        verdict = normalize(result)
    except ExecutionDisabledError:
        # The existing executor explicitly guarantees no dispatch for this exception.
        try:
            target = store.finish_execution(iid, owner=owner, execution={'broker_outcome': 'NOT_SENT'})
            if target in _TERMINAL_STATES and not phys_claim.get('reused'):
                store.release_physical_order(physical_key, intent_id=iid)
        except Exception:
            pass  # EXECUTING is conservative and cannot be replayed.
        raise
    # Other exceptions (including crashes during normalization) deliberately
    # leave EXECUTING durable. Existing Step5B exception handling is unchanged.
    verdict['intent_id'] = iid
    verdict['intent_claim'] = claim
    verdict['physical_order_key'] = physical_key
    try:
        target = store.finish_execution(iid, owner=owner, execution=verdict)
        if target in _TERMINAL_STATES and not phys_claim.get('reused'):
            store.release_physical_order(physical_key, intent_id=iid)
    except Exception as exc:
        verdict['intent_state_persistence_error'] = type(exc).__name__
        verdict['reconciliation_required'] = True
    return verdict
