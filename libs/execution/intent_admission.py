"""Explicit authority admission at trusted policy boundaries."""
from __future__ import annotations

from libs.execution.intent_identity import bind_intent, physical_order_fingerprint
from libs.supervisor.intent_state_store import SQLiteIntentStateStore


def admit_order_intent(*, state: dict, order: dict, source: str, child: bool = False) -> dict:
    iid = ''
    physical_key = None
    try:
        iid = bind_intent(state, order, child=child)
        physical_key = physical_order_fingerprint(state, order)
        if physical_key is None:
            return {'admitted': False, 'reason': 'invalid_physical_order', 'intent_id': iid}
        result = SQLiteIntentStateStore().admit_intent(iid, fingerprint=physical_key, source=source)
        result.update(intent_id=iid, physical_order_key=physical_key)
        return result
    except Exception as exc:
        return {
            'admitted': False,
            'reason': 'intent_admission_unavailable',
            'error_type': type(exc).__name__,
            'intent_id': iid,
            'physical_order_key': physical_key,
        }
