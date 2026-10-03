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


def _intent_id_material(state: dict, order: dict, *, child: bool) -> list:
    action = str(order.get('action') or '').strip().upper()
    symbol = normalize_symbol(order.get('symbol') or order.get('stk_cd'))
    reference = order.get('orig_ord_no') or order.get('original_order_id') or ''
    if child:
        # Automatic cancellation of the same broker order is one logical
        # intent even when reached from a later polling tick.
        return [execution_scope(state), 'automatic_child', symbol, action, reference,
                order.get('cncl_qty'), order.get('mdfy_qty'), order.get('mdfy_uv')]
    return [execution_scope(state), state['run_id'], symbol, action, reference]


def compute_self_minted_intent_id(state: dict, order: dict, *, child: bool = False) -> str:
    """The intent_id bind_intent's own deterministic scheme would generate
    for this order's content, independent of whatever order['intent_id']
    currently holds. Requires state['run_id'] to already be set (bind_intent
    sets it on first use via setdefault)."""
    return 'intent-v1-' + _digest(_intent_id_material(state, order, child=child))


def is_self_minted_intent_id(state: dict, order: dict, intent_id: str, *, child: bool = False) -> bool:
    """Compatibility helper for deterministic identity comparison.

    This function is not an authorization primitive. Step5C Fix4 requires
    explicit persisted admission before execution regardless of whether an
    identifier matches the deterministic format.
    """
    try:
        return str(intent_id or '') == compute_self_minted_intent_id(state, order, child=child)
    except Exception:
        return False


def bind_intent(state: dict, order: dict, intent: dict | None = None, *, child: bool = False) -> str:
    intent = intent if isinstance(intent, dict) else {}
    ids = {str(row['intent_id']).strip() for row in (order, intent) if row.get('intent_id')}
    if len(ids) > 1:
        raise ValueError('intent_identity_conflict')
    state.setdefault('run_id', uuid.uuid4().hex)
    iid = next(iter(ids)) if ids else compute_self_minted_intent_id(state, order, child=child)
    order['intent_id'] = iid
    intent['intent_id'] = iid
    if not child:
        state['intent_id'] = iid
    return iid


def order_fingerprint(state: dict, order: dict) -> str:
    keys = ('action', 'symbol', 'qty', 'price', 'order_type', 'orig_ord_no',
            'cncl_qty', 'mdfy_qty', 'mdfy_uv', 'dmst_stex_tp')
    return _digest([execution_scope(state), {key: order.get(key) for key in keys}])


_CANONICAL_ACTIONS = frozenset({'BUY', 'SELL', 'CANCEL', 'MODIFY'})


def _canonical_action(value) -> str | None:
    action = str(value or '').strip().upper()
    return action if action in _CANONICAL_ACTIONS else None


def _canonical_order_type(order: dict) -> str | None:
    """Resolve logical order type against the Kiwoom broker trade type.

    ``trde_tp`` is authoritative when present because that is what reaches
    Kiwoom. Logical aliases remain useful before request construction. A
    disagreement is malformed input, not a reason to guess.
    """
    raw_logical = str(order.get('order_type') or '').strip().lower()
    logical = None
    if raw_logical in {'market', 'mkt'}:
        logical = 'MARKET'
    elif raw_logical in {'limit', 'lmt'}:
        logical = 'LIMIT'
    elif raw_logical:
        return None

    raw_broker = str(order.get('trde_tp') or '').strip()
    broker = None
    if raw_broker:
        if raw_broker == '3':
            broker = 'MARKET'
        elif raw_broker == '0':
            broker = 'LIMIT'
        else:
            return None

    if logical and broker and logical != broker:
        return None
    return broker or logical or 'LIMIT'


def _canonical_qty(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        qty = value
    elif isinstance(value, float):
        if not value.is_integer():
            return None
        qty = int(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s or not s.lstrip('-').isdigit():
            return None
        qty = int(s)
    else:
        return None
    return qty if qty > 0 else None


def _canonical_positive_number(value) -> int | None:
    """A KRW order price is a whole-won integer -- never hashed as a float
    (float hashing/serialization is non-deterministic across equal values
    like 70000.0 vs 70000). Accepts int/str/float forms of the same whole
    number; rejects fractional, non-numeric, non-positive, and None/"" -- a
    LIMIT order with no such value has no real price identity."""
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not num.is_integer():
        return None
    n = int(num)
    return n if n > 0 else None


def physical_order_fingerprint(state: dict, order: dict) -> str | None:
    """Identity of the real-world broker mutation itself, independent of
    which intent_id (or generation scheme) is asking for it.

    Step5C Fix2 HIGH3: two DIFFERENT intent_id values -- e.g. the automated
    path's content-hash and the manual approval path's uuid4 -- can still
    describe the same physical order (same account/symbol/side/order_type/
    qty/price/orig_ord_no). This fingerprint is the key the physical-order
    duplicate guard (SQLiteIntentStateStore.claim_physical_order) uses to
    ensure at most one intent holds an active lease on one physical shape
    at a time, regardless of intent_id or entry path.

    Step5C Fix3: raw field values are canonicalized BEFORE hashing (see
    _canonical_action/_canonical_order_type/_canonical_qty/
    _canonical_positive_number above, each grounded in this codebase's own
    existing order-building contract, not guessed) so equivalent
    representations of the same real order -- qty=10 vs qty="10", price=
    70000 vs "70000", or a market order carrying a stray cached/reference
    price -- always produce the SAME key, and inequivalent orders (BUY vs
    SELL, 10 vs 20 shares, market vs limit, different limit price, a
    CANCEL vs the BUY/SELL it targets) always produce DIFFERENT keys.

    Returns None when the order cannot be canonicalized into a valid
    physical order identity at all (unrecognized action, invalid symbol, a
    BUY/SELL with no valid positive qty, or a LIMIT order with no valid
    positive price). Callers MUST treat None as fail-closed -- never
    fingerprint, claim, or dispatch a malformed order; there is no
    "assume market" or "assume qty 0" fallback here.
    """
    action = _canonical_action(order.get('action'))
    symbol = normalize_symbol(order.get('symbol') or order.get('stk_cd'))
    orig_ord_no = str(order.get('orig_ord_no') or order.get('original_order_id') or '').strip()
    if not action or not symbol:
        return None

    if action in ('CANCEL', 'MODIFY'):
        # A CANCEL/MODIFY's physical identity is the original broker order
        # it targets (action + orig_ord_no), not an independent qty/price/
        # order_type triple -- there is no meaningful "market vs limit"
        # concept for a cancel/modify request itself. This mirrors
        # bind_intent's own child-intent material (cncl_qty/mdfy_qty/
        # mdfy_uv), and action alone already keeps a CANCEL from ever
        # colliding with the BUY/SELL it targets.
        if not orig_ord_no:
            return None
        qty_field = 'cncl_qty' if action == 'CANCEL' else 'mdfy_qty'
        raw_qty = order.get(qty_field)
        qty = _canonical_qty(raw_qty) if raw_qty is not None else 0
        price = _canonical_positive_number(order.get('mdfy_uv')) if action == 'MODIFY' else None
        material = [execution_scope(state), symbol, action, orig_ord_no, qty, price]
        return _digest(material)

    order_type = _canonical_order_type(order)
    if order_type is None:
        return None
    qty = _canonical_qty(order.get('qty'))
    if qty is None:
        return None
    if order_type == 'MARKET':
        # A market order's identity never includes price -- any cached/
        # reference/display price field the caller happened to carry is
        # not part of the physical order and must not leak into its key.
        price = None
    else:
        price = _canonical_positive_number(order.get('price'))
        if price is None:
            return None
    material = [execution_scope(state), symbol, action, order_type, qty, price, orig_ord_no]
    return _digest(material)
