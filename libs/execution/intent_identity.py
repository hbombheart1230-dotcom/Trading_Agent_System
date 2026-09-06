"""Canonical order-intent identity. Does not authorize execution."""
from __future__ import annotations

import hashlib
import json
import os
import uuid

from libs.core.symbols import normalize_symbol


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def execution_scope(state: dict) -> str:
    # Only a digest of the account identifier is persisted in identity material.
    return _digest([os.getenv('EXECUTION_MODE', 'mock'), os.getenv('KIWOOM_MODE', 'mock'),
                    state.get('account_id') or os.getenv('KIWOOM_ACCOUNT_NO', '')])


def bind_intent(state: dict, order: dict, intent: dict | None = None, *, child: bool = False) -> str:
    intent = intent if isinstance(intent, dict) else {}
    ids = {str(row['intent_id']).strip() for row in (order, intent) if row.get('intent_id')}
    if len(ids) > 1:
        raise ValueError('intent_identity_conflict')
    state.setdefault('run_id', uuid.uuid4().hex)
    action = str(order.get('action') or '').strip().upper()
    symbol = normalize_symbol(order.get('symbol') or order.get('stk_cd'))
    reference = order.get('orig_ord_no') or order.get('original_order_id') or ''
    material = [execution_scope(state), state['run_id'], symbol, action, reference]
    if child:
        # Automatic cancellation of the same broker order is one logical
        # intent even when reached from a later polling tick.
        material = [execution_scope(state), 'automatic_child', symbol, action, reference,
                    order.get('cncl_qty'), order.get('mdfy_qty'), order.get('mdfy_uv')]
    iid = next(iter(ids)) if ids else 'intent-v1-' + _digest(material)
    order['intent_id'] = iid
    intent['intent_id'] = iid
    if not child:
        state['intent_id'] = iid
    return iid


def order_fingerprint(state: dict, order: dict) -> str:
    keys = ('action', 'symbol', 'qty', 'price', 'order_type', 'orig_ord_no',
            'cncl_qty', 'mdfy_qty', 'mdfy_uv', 'dmst_stex_tp')
    return _digest([execution_scope(state), {key: order.get(key) for key in keys}])
