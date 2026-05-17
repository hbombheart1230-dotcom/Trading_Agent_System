from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional


def to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None

    if isinstance(ts, (int, float)):
        return int(ts)

    s = str(ts).strip()
    if not s:
        return None

    try:
        return int(float(s))
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def utc_day(ts: Any) -> str:
    epoch = to_epoch(ts)
    if epoch is None:
        return date.today().isoformat()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def extract_intent_action(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return ""

    packet = payload.get("decision_packet")
    if isinstance(packet, dict):
        intent = packet.get("intent")
        if isinstance(intent, dict):
            action = intent.get("action") or intent.get("intent")
            return str(action or "").upper()

    action = payload.get("action") or payload.get("intent")
    return str(action or "").upper()


def extract_guard_reason(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return "unknown"

    reason = payload.get("reason")
    if reason:
        return str(reason)

    details = payload.get("details")
    if isinstance(details, dict) and details.get("reason"):
        return str(details["reason"])

    return "unknown"


def extract_api_id(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return "unknown"

    for key in ("api_id", "order_api_id"):
        value = payload.get(key)
        if value:
            return str(value)

    order = payload.get("order")
    if isinstance(order, dict):
        for key in ("api_id", "order_api_id"):
            value = order.get(key)
            if value:
                return str(value)

    packet = payload.get("decision_packet")
    if isinstance(packet, dict):
        intent = packet.get("intent")
        if isinstance(intent, dict):
            for key in ("order_api_id", "api_id"):
                value = intent.get(key)
                if value:
                    return str(value)

    skill = payload.get("skill")
    if skill:
        return f"skill:{skill}"

    return "unknown"


def looks_like_429(value: Any) -> bool:
    if value is None:
        return False
    try:
        if int(float(value)) == 429:
            return True
    except Exception:
        pass

    text = str(value).strip().lower()
    if not text:
        return False
    if text == "429":
        return True
    if "429" in text:
        return True
    return False


def is_429_error_row(row: Dict[str, Any]) -> bool:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return False

    for key in ("status_code", "http_status", "http_status_code", "code", "error_code"):
        if looks_like_429(payload.get(key)):
            return True

    nested = payload.get("response")
    if isinstance(nested, dict):
        for key in ("status_code", "http_status", "code"):
            if looks_like_429(nested.get(key)):
                return True

    if looks_like_429(payload.get("error")):
        return True
    if looks_like_429(payload.get("error_type")):
        return True
    return False


def to_non_negative_int(value: Any) -> int:
    try:
        number = int(float(value))
    except Exception:
        return 0
    return number if number >= 0 else 0


def extract_skill_error_tag(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    if "(" in text:
        return (text.split("(", 1)[0] or "unknown").strip() or "unknown"
    return (text.split(":", 1)[0] or "unknown").strip() or "unknown"
