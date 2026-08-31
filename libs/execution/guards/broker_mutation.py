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


def is_mutation_api_id(api_id: Any) -> bool:
    return str(api_id or "").strip().lower() in MUTATION_API_IDS


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


def classify_mutation_response(payload: Dict[str, Any]) -> Tuple[str, bool]:
    """Classify a broker mutation response body into ACCEPTED/REJECTED/UNKNOWN.

    Returns (broker_outcome, broker_reference_missing). Never returns
    ACCEPTED on HTTP status alone -- only an explicit, recognized business
    success code counts. Absence of any recognized business code (malformed
    body, unfamiliar field names, or a body with no code at all) is UNKNOWN,
    never a silent ACCEPTED default.
    """
    if not isinstance(payload, dict):
        return "UNKNOWN", False

    code = _broker_code_value(payload)
    if code is not None:
        success = _broker_code_is_success(code)
        if success is True:
            return "ACCEPTED", not order_reference_present(payload)
        if success is False:
            return "REJECTED", False
        # Recognized field present but its value doesn't parse as a known
        # success/reject signal -- do not guess.
        return "UNKNOWN", False

    return "UNKNOWN", False
