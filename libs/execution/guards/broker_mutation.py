from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Canonical inventory of Kiwoom broker-mutation API ids (Phase 1 Step 5B).
#
# Mutation is identified by api_id, never by HTTP method/path -- Kiwoom read
# (query) APIs also use POST, so method/path cannot distinguish a mutation
# from a read.
#
# kt10002 (MODIFY) is included for completeness of the inventory but is not
# currently wired into any live order path in this codebase (verified: no
# reference anywhere outside this registry). It is listed so any future
# MODIFY integration inherits the same retry=0 / no-replay safety by
# construction instead of being added separately later.
MUTATION_API_NAMES: Dict[str, str] = {
    "kt10000": "BUY",
    "kt10001": "SELL",
    "kt10002": "MODIFY",
    "kt10003": "CANCEL",
}

MUTATION_API_IDS = frozenset(MUTATION_API_NAMES.keys())

# The generic order-submission alias used before catalog/spec resolution
# picks a concrete kt10000/kt10001 api_id (see
# graphs/nodes/execute_from_packet.py::_prepare_request). If catalog lookup
# fails for either the alias or the resolved concrete id, _prepare_request's
# fallback PreparedRequest still carries this literal alias as api_id (never
# blank) -- so it must independently count as a mutation. Without this, a
# catalog lookup failure would silently downgrade a real BUY/SELL to
# non-mutation transport behavior (full retry, token-refresh replay
# allowed) -- the exact CRITICAL gap this constant closes.
_UNRESOLVED_MUTATION_ALIASES = frozenset({"order_submit"})


def is_mutation_api_id(api_id: Any) -> bool:
    normalized = str(api_id or "").strip().lower()
    return normalized in MUTATION_API_IDS or normalized in _UNRESOLVED_MUTATION_ALIASES


_MUTATION_ACTIONS = frozenset({"buy", "sell", "cancel", "modify"})


def is_mutation_request(req: Any) -> bool:
    """Mutation detection (Phase 1 Step 5B Safety Fix 2).

    api_id is the primary, most reliable signal (checked first). But a
    custom order_builder or an alternate live mutation path (see
    graphs/nodes/execute_order.py, libs/skills/runner.py) could construct a
    request-like object where api_id is missing or unrecognized while the
    request is still, unambiguously, a real mutation -- e.g. an action/side
    field of "buy"/"sell"/"cancel"/"modify" on the request body. This cross
    checks those secondary signals so api_id alone being empty/wrong can
    never silently downgrade a real mutation to non-mutation (full retry,
    token-refresh replay allowed) transport treatment. It is one-directional
    by design: these secondary signals can only ADD a mutation
    classification, never remove one that api_id already established, and
    they never reclassify a genuine read/query call (which would need a
    recognized mutation action to trigger this branch at all) as a
    mutation.
    """
    if is_mutation_api_id(getattr(req, "api_id", None)):
        return True

    body = getattr(req, "body", None)
    if isinstance(body, dict):
        for key in ("action", "side", "operation"):
            value = str(body.get(key) or "").strip().lower()
            if value in _MUTATION_ACTIONS:
                return True

    action_attr = str(getattr(req, "action", "") or getattr(req, "operation", "") or "").strip().lower()
    if action_attr in _MUTATION_ACTIONS:
        return True

    return False


_BROKER_CODE_FIELDS = ("msg_cd", "message_code", "code", "rt_cd", "error_code", "err_cd", "return_code")
_ORDER_REFERENCE_FIELDS = ("ord_no", "order_id", "orderId", "odno", "ODNO", "ordNo")


def _broker_code_value(payload: Dict[str, Any]) -> Optional[str]:
    for key in _BROKER_CODE_FIELDS:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _broker_code_is_success(code: str) -> Optional[bool]:
    try:
        return int(float(code)) == 0
    except Exception:
        pass
    normalized = code.strip().lower()
    if normalized in ("ok", "success", "accepted"):
        return True
    if normalized in ("error", "failed", "rejected"):
        return False
    return None


def order_reference_present(payload: Dict[str, Any]) -> bool:
    for key in _ORDER_REFERENCE_FIELDS:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return True
    return False


def _all_broker_code_signals(payload: Dict[str, Any]) -> Tuple[list, bool]:
    """Every recognized business-code field's parsed success/reject signal.

    Unlike _broker_code_value (which stops at the first recognized field),
    this evaluates every field present so a response carrying conflicting
    codes (e.g. msg_cd says success, return_code says reject) is detectable
    instead of silently trusting whichever field happens to be checked
    first.

    Returns (signals, has_unrecognized_value). Phase 1 Step 5B Safety Fix 2:
    a recognized field (e.g. msg_cd) present with a value that doesn't parse
    into a known success/reject signal (e.g. "UNRECOGNIZED") is itself
    grounds for UNKNOWN -- it must not be silently ignored just because
    some OTHER field happened to parse cleanly (return_code=0 +
    msg_cd="UNRECOGNIZED" is ambiguous, not a clean ACCEPTED).
    """
    signals = []
    has_unrecognized_value = False
    for key in _BROKER_CODE_FIELDS:
        value = payload.get(key)
        if value is None or not str(value).strip():
            continue
        outcome = _broker_code_is_success(str(value).strip())
        if outcome is None:
            has_unrecognized_value = True
        else:
            signals.append(outcome)
    return signals, has_unrecognized_value


def classify_mutation_response(payload: Dict[str, Any], *, status_code: Optional[int] = None) -> Tuple[str, bool]:
    """Classify a broker mutation response into ACCEPTED/REJECTED/UNKNOWN.

    Returns (broker_outcome, broker_reference_missing).

    Rules (Phase 1 Step 5B Safety Fix -- evaluates ALL present business-code
    fields, not just the first, and cross-checks against HTTP status):
    - all explicit business-code signals agree "success" -> ACCEPTED
      (unless HTTP status is present and non-2xx, which contradicts a
      business "success" -> UNKNOWN)
    - all explicit business-code signals agree "reject" -> REJECTED
    - signals conflict with each other -> UNKNOWN
    - no recognized business signal at all (malformed body, unfamiliar
      field names, empty body) -> UNKNOWN, regardless of HTTP status; HTTP
      2xx alone is never sufficient for ACCEPTED
    """
    if not isinstance(payload, dict):
        return "UNKNOWN", False

    signals, has_unrecognized_value = _all_broker_code_signals(payload)
    if has_unrecognized_value:
        # A recognized business-code field is present but its value doesn't
        # parse -- an unrecognized explicit signal is never silently
        # dropped in favor of a cleaner-looking field elsewhere.
        return "UNKNOWN", False
    if not signals:
        return "UNKNOWN", False

    if all(signal is True for signal in signals):
        if status_code is not None:
            try:
                is_http_2xx = 200 <= int(status_code) < 300
            except Exception:
                # status_code was explicitly provided but couldn't be
                # parsed -- an unrecognized explicit signal, not something
                # to wave through as an assumed success.
                return "UNKNOWN", False
            if not is_http_2xx:
                # Business code says success but the transport layer says
                # otherwise -- a real contradiction, not a confirmed outcome.
                return "UNKNOWN", False
        return "ACCEPTED", not order_reference_present(payload)

    if all(signal is False for signal in signals):
        return "REJECTED", False

    # Mixed True/False across fields -- do not guess which one is right.
    return "UNKNOWN", False
