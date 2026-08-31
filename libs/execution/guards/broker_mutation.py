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


def _all_broker_code_signals(payload: Dict[str, Any]) -> list:
    """Every recognized business-code field's parsed success/reject signal.

    Unlike _broker_code_value (which stops at the first recognized field),
    this evaluates every field present so a response carrying conflicting
    codes (e.g. msg_cd says success, return_code says reject) is detectable
    instead of silently trusting whichever field happens to be checked
    first.
    """
    signals = []
    for key in _BROKER_CODE_FIELDS:
        value = payload.get(key)
        if value is None or not str(value).strip():
            continue
        outcome = _broker_code_is_success(str(value).strip())
        if outcome is not None:
            signals.append(outcome)
        # A recognized field present with an unparseable value contributes
        # no signal either way here; classify_mutation_response's "no
        # signals at all" branch below still correctly falls through to
        # UNKNOWN in that case (an unparseable code is not evidence of
        # anything).
    return signals


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

    signals = _all_broker_code_signals(payload)
    if not signals:
        return "UNKNOWN", False

    if all(signal is True for signal in signals):
        if status_code is not None:
            try:
                is_http_2xx = 200 <= int(status_code) < 300
            except Exception:
                is_http_2xx = True  # unparseable status shouldn't itself veto an otherwise-clean success
            if not is_http_2xx:
                # Business code says success but the transport layer says
                # otherwise -- a real contradiction, not a confirmed outcome.
                return "UNKNOWN", False
        return "ACCEPTED", not order_reference_present(payload)

    if all(signal is False for signal in signals):
        return "REJECTED", False

    # Mixed True/False across fields -- do not guess which one is right.
    return "UNKNOWN", False
