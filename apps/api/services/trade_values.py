from __future__ import annotations

from datetime import datetime

from ..models.common import AvailabilityStatus


def source_status(value):
    return {
        "VALID": AvailabilityStatus.AVAILABLE,
        "PARTIAL": AvailabilityStatus.PARTIAL,
        "MISSING": AvailabilityStatus.UNAVAILABLE,
        "INVALID": AvailabilityStatus.ERROR,
    }.get(value, AvailabilityStatus.ERROR)


def mapping(value):
    return value if isinstance(value, dict) else {}


def list_value(value):
    return value if isinstance(value, list) else []


def string_list(value):
    return list(
        dict.fromkeys(
            str(item).strip()
            for item in list_value(value)
            if str(item).strip()
        )
    )


def text_value(value):
    text = str(value or "").strip()
    return text or None


def first_text(*values):
    return next((text_value(value) for value in values if text_value(value)), None)


def number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def integer(value):
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def ratio_to_pct(value):
    parsed = number(value)
    return round(parsed * 100.0, 8) if parsed is not None else None


def timestamp(value):
    raw = text_value(value)
    if raw is None:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
