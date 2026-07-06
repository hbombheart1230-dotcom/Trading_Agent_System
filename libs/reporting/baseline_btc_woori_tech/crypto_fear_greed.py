from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.request import Request, urlopen


KST = timezone(timedelta(hours=9))
API_URL = "https://api.alternative.me/fng/?limit=30&format=json"


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _regime(value: int | None, classification: str = "") -> str:
    text = str(classification or "").strip().lower().replace(" ", "_")
    if text:
        return text
    if value is None:
        return "unavailable"
    if value <= 24:
        return "extreme_fear"
    if value <= 44:
        return "fear"
    if value <= 55:
        return "neutral"
    if value <= 74:
        return "greed"
    return "extreme_greed"


def _normalize_row(row: Mapping[str, Any], *, day: str) -> dict[str, Any]:
    value = _to_int(row.get("value"))
    timestamp = _to_int(row.get("timestamp"))
    observed_at = ""
    observed_day = ""
    if timestamp:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(KST)
        observed_at = dt.isoformat()
        observed_day = dt.date().isoformat()
    classification = str(row.get("value_classification") or "").strip()
    return {
        "schema_version": "q12_crypto_fear_greed.v1",
        "available": value is not None,
        "source": "alternative.me/fng",
        "day": day,
        "observed_day": observed_day,
        "observed_at": observed_at,
        "value": value,
        "classification": classification,
        "regime": _regime(value, classification),
        "time_until_update": row.get("time_until_update"),
        "fallback_reason": "" if value is not None else "crypto_fear_greed_value_missing",
        "behavior_effect": "observation_only",
    }


def unavailable(reason: str, *, day: str) -> dict[str, Any]:
    return {
        "schema_version": "q12_crypto_fear_greed.v1",
        "available": False,
        "source": "alternative.me/fng",
        "day": day,
        "observed_day": "",
        "observed_at": "",
        "value": None,
        "classification": "",
        "regime": "unavailable",
        "time_until_update": None,
        "fallback_reason": reason,
        "behavior_effect": "observation_only",
    }


def load_crypto_fear_greed_index(*, day: str, timeout_sec: float = 5.0) -> dict[str, Any]:
    request = Request(API_URL, headers={"User-Agent": "TradingAgentSystem/1.0"})
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return unavailable(f"crypto_fear_greed_fetch_failed:{type(exc).__name__}", day=day)

    rows = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list) or not rows:
        return unavailable("crypto_fear_greed_empty_response", day=day)

    normalized = [
        _normalize_row(row, day=day)
        for row in rows
        if isinstance(row, Mapping)
    ]
    exact = [row for row in normalized if row.get("observed_day") == day]
    if exact:
        return exact[0]
    latest = normalized[0] if normalized else unavailable("crypto_fear_greed_no_valid_rows", day=day)
    latest["fallback_reason"] = "exact_day_not_found_latest_used" if latest.get("available") else latest.get("fallback_reason")
    return latest
