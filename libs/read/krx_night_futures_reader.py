from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_URLS = (
    "https://chartlog.net/stats/market-index/kospi-night-futures/",
)


def _float(value: Any, default: float | None = None) -> Optional[float]:
    try:
        if value in (None, ""):
            return default
        text = str(value).strip().replace(",", "").replace("%", "")
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _packet(
    *,
    status: str,
    source: str,
    reason: str = "",
    current: Any = None,
    previous: Any = None,
    change: Any = None,
    change_pct: Any = None,
    basis: Any = None,
    session: str = "KRX night",
    raw: Any = None,
) -> Dict[str, Any]:
    current_f = _float(current)
    previous_f = _float(previous)
    change_f = _float(change)
    change_pct_f = _float(change_pct)
    if change_f is None and current_f is not None and previous_f is not None:
        change_f = current_f - previous_f
    if change_pct_f is None and current_f is not None and previous_f not in (None, 0.0):
        change_pct_f = ((current_f / float(previous_f)) - 1.0) * 100.0
    pressure = "unknown"
    if change_pct_f is not None:
        if change_pct_f <= -1.0:
            pressure = "strong_down"
        elif change_pct_f <= -0.35:
            pressure = "down"
        elif change_pct_f >= 1.0:
            pressure = "strong_up"
        elif change_pct_f >= 0.35:
            pressure = "up"
        else:
            pressure = "flat"
    return {
        "schema_version": "krx_night_futures.v1",
        "behavior_effect": "observation_only",
        "market": "KRX",
        "instrument": "KOSPI200 night futures",
        "session": session,
        "source": source,
        "status": status,
        "reason": reason,
        "current": current_f,
        "previous": previous_f,
        "change": change_f,
        "change_pct": change_pct_f,
        "basis": _float(basis),
        "direction_pressure": pressure,
        "trading_action_allowed": False,
        "ts": int(time.time()),
        "raw": raw if isinstance(raw, dict) else {},
    }


def _packet_from_mapping(data: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    nested = data.get("krx_night_futures") if isinstance(data.get("krx_night_futures"), dict) else data
    return _packet(
        status=_text(nested.get("status") or "ok"),
        source=source,
        reason=_text(nested.get("reason")),
        current=nested.get("current") or nested.get("price") or nested.get("last"),
        previous=nested.get("previous") or nested.get("previous_close") or nested.get("prev"),
        change=nested.get("change") or nested.get("diff"),
        change_pct=nested.get("change_pct") or nested.get("rate") or nested.get("return_pct"),
        basis=nested.get("basis"),
        session=_text(nested.get("session") or "KRX night"),
        raw=dict(nested),
    )


def _from_env() -> Dict[str, Any]:
    current = os.getenv("KRX_NIGHT_FUTURES_CURRENT")
    change_pct = os.getenv("KRX_NIGHT_FUTURES_CHANGE_PCT")
    previous = os.getenv("KRX_NIGHT_FUTURES_PREVIOUS")
    basis = os.getenv("KRX_NIGHT_FUTURES_BASIS")
    if any(_text(x) for x in (current, change_pct, previous, basis)):
        return _packet(
            status="ok",
            source="env",
            reason="env_override",
            current=current,
            previous=previous,
            change_pct=change_pct,
            basis=basis,
        )
    return {}


def _from_local_file() -> Dict[str, Any]:
    path = Path(os.getenv("KRX_NIGHT_FUTURES_LOCAL_JSON", "data/logs/krx_night_futures/latest.json"))
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _packet(status="unavailable", source=str(path), reason=f"local_json_parse_failed:{exc}")
    return _packet_from_mapping(data if isinstance(data, dict) else {}, source=str(path))


def _extract_from_html(text: str, *, source: str) -> Dict[str, Any]:
    patterns = [
        r'\\?"(?:current|price|last)\\?"\s*:\s*"?([-+]?\d+(?:,\d{3})*(?:\.\d+)?)"?',
        r'\\?"(?:change_pct|change_rate)\\?"\s*:\s*"?([-+]?\d+(?:\.\d+)?)"?',
        r'\\?"(?:previous|previous_close|prev)\\?"\s*:\s*"?([-+]?\d+(?:,\d{3})*(?:\.\d+)?)"?',
        r'\\?"(?:change|change_value)\\?"\s*:\s*"?([-+]?\d+(?:,\d{3})*(?:\.\d+)?)"?',
    ]
    current = None
    change_pct = None
    previous = None
    change = None
    match = re.search(patterns[0], text, flags=re.IGNORECASE)
    if match:
        current = match.group(1)
    match = re.search(patterns[1], text, flags=re.IGNORECASE)
    if match:
        change_pct = match.group(1)
    match = re.search(patterns[2], text, flags=re.IGNORECASE)
    if match:
        previous = match.group(1)
    match = re.search(patterns[3], text, flags=re.IGNORECASE)
    if match:
        change = match.group(1)
    if current is not None or change_pct is not None:
        return _packet(
            status="ok",
            source=source,
            reason="html_embedded_value",
            current=current,
            previous=previous,
            change=change,
            change_pct=change_pct,
        )

    compact = re.sub(r"\s+", " ", text)
    current_match = re.search(
        r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*[▲▼]?\s*[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*\(\s*([-+]?\d+(?:\.\d+)?)%\s*\)",
        compact,
    )
    previous_match = re.search(r"전일\s*정산가\s*(-?\d+(?:,\d{3})*(?:\.\d+)?)", compact)
    change_match = re.search(r"전일\s*종가\s*대비\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)", compact)
    change_pct_match = re.search(r"등락률\s*([-+]?\d+(?:\.\d+)?)%", compact)
    if current_match or previous_match or change_match or change_pct_match:
        return _packet(
            status="ok",
            source=source,
            reason="html_korean_market_snapshot",
            current=current_match.group(1) if current_match else None,
            previous=previous_match.group(1) if previous_match else None,
            change=change_match.group(1) if change_match else None,
            change_pct=change_pct_match.group(1) if change_pct_match else (current_match.group(2) if current_match else None),
        )

    meta_ok = "kospi-night-futures" in text.lower() or "KOSPI 200" in text
    if meta_ok:
        return _packet(status="unavailable", source=source, reason="page_reachable_but_realtime_value_not_embedded")
    return {}


def _from_url(url: str) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        timeout = float(os.getenv("KRX_NIGHT_FUTURES_TIMEOUT_SEC", "5") or 5)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read(250000).decode("utf-8", errors="ignore")
    except Exception as exc:
        return _packet(status="unavailable", source=url, reason=f"url_fetch_failed:{exc}")
    return _extract_from_html(text, source=url)


def _urls() -> Iterable[str]:
    raw = os.getenv("KRX_NIGHT_FUTURES_URLS") or os.getenv("KRX_NIGHT_FUTURES_URL") or ""
    values = [item.strip() for item in raw.split(",") if item.strip()] if raw else []
    return values or list(DEFAULT_URLS)


def fetch_krx_night_futures_packet() -> Dict[str, Any]:
    for provider in (_from_env, _from_local_file):
        packet = provider()
        if packet:
            return packet
    last: Dict[str, Any] = {}
    for url in _urls():
        packet = _from_url(str(url))
        if packet and packet.get("status") == "ok":
            return packet
        if packet:
            last = packet
    return last or _packet(status="unavailable", source="none", reason="no_provider_available")
