"""Durable logical execution ownership composed with existing broker semantics."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.intent_identity import bind_intent, order_fingerprint
from libs.supervisor.intent_state_store import SQLiteIntentStateStore


def _store():
    default = Path(__file__).resolve().parents[2] / 'data/state/intent_state.db'
    return SQLiteIntentStateStore(os.getenv('INTENT_STATE_DB_PATH') or str(default))


def execute_owned_order(*, state: dict, order: dict, request, executor, normalize, child: bool = False, on_submit=None) -> dict:
    """Call only after existing policy approval; never bypass those guards.

    normalize is the caller's existing Step5B outcome normalization boundary.
    No transport classification is invented by this ownership layer.
    """
    owner = uuid.uuid4().hex
    iid = ''
    try:
        iid = bind_intent(state, order, child=child)
        store = _store()
        claim = store.claim_execution(iid, fingerprint=order_fingerprint(state, order), owner=owner)
    except Exception as exc:
        claim = {'claimed': False, 'reason': 'intent_CAS_unavailable', 'error_type': type(exc).__name__}
    if not claim.get('claimed'):
        verdict = normalize(None)
        verdict.update(allowed=False, ok=False, execution_ok=False, broker_outcome='NOT_SENT',
                       submission_attempts=0, submission_phase='not_dispatched',
                       reason=claim['reason'], intent_id=iid, intent_claim=claim,
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
            store.finish_execution(iid, owner=owner, execution={'broker_outcome': 'NOT_SENT'})
        except Exception:
            pass  # EXECUTING is conservative and cannot be replayed.
        raise
    # Other exceptions (including crashes during normalization) deliberately
    # leave EXECUTING durable. Existing Step5B exception handling is unchanged.
    verdict['intent_id'] = iid
    verdict['intent_claim'] = claim
    try:
        store.finish_execution(iid, owner=owner, execution=verdict)
    except Exception as exc:
        verdict['intent_state_persistence_error'] = type(exc).__name__
        verdict['reconciliation_required'] = True
    return verdict
