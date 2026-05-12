from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


INDEX_CODES = {
    "KOSPI": "001",
    "KOSDAQ": "101",
}


def _parse_kiwoom_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        import re

        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None


def _price(value: Any) -> Optional[float]:
    number = _parse_kiwoom_number(value)
    if number is None:
        return None
    return abs(float(number))


def _signed(value: Any) -> Optional[float]:
    number = _parse_kiwoom_number(value)
    if number is None:
        return None
    return float(number)


def _safe_int(value: Any) -> int:
    number = _parse_kiwoom_number(value)
    if number is None:
        return 0
    return int(number)


@dataclass(frozen=True)
class MarketIndexSnapshot:
    name: str
    code: str
    current: Optional[float]
    previous_close: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[float]
    value: Optional[float]
    rising: int
    falling: int
    unchanged: int
    current_date: str
    previous_date: str
    ts: int
    source: str
    previous_close_source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "current": self.current,
            "previous_close": self.previous_close,
            "change": self.change,
            "change_pct": self.change_pct,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "volume": self.volume,
            "value": self.value,
            "rising": self.rising,
            "falling": self.falling,
            "unchanged": self.unchanged,
            "current_date": self.current_date,
            "previous_date": self.previous_date,
            "ts": self.ts,
            "source": self.source,
            "previous_close_source": self.previous_close_source,
        }


class KiwoomMarketIndexReader:
    """Read KOSPI/KOSDAQ index context from Kiwoom sector index APIs."""

    API_ID_DAILY = "ka20009"
    ENDPOINT_SECTOR = "/api/dostk/sect"

    def __init__(self, settings: Settings, http: HttpClient, token: KiwoomTokenClient):
        self.s = settings
        self.http = http
        self.token = token

    @classmethod
    def from_env(cls) -> "KiwoomMarketIndexReader":
        settings = Settings.from_env()
        base = settings.kiwoom_base_url_mock if settings.kiwoom_mode == "mock" else settings.kiwoom_base_url_real
        http = HttpClient(
            base_url=base,
            timeout_sec=int(settings.kiwoom_http_timeout_sec),
            retry_max=int(settings.kiwoom_retry_max),
        )
        token = KiwoomTokenClient(settings, http)
        return cls(settings, http, token)

    def _request(self, *, api_id: str, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        token_result = self.token.ensure_token(dry_run=False)
        if not token_result.token:
            raise RuntimeError(f"Token not available: {token_result.action} {token_result.reason}")

        headers: Dict[str, Any] = {}
        headers.update(self.token.auth_headers(token_result.token))
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["api-id"] = api_id
        headers.setdefault("appkey", self.s.kiwoom_app_key or "")
        headers.setdefault("appsecret", self.s.kiwoom_app_secret or "")

        retry_max = max(0, int(float(os.getenv("KIWOOM_INDEX_RETRY_MAX", "2") or 2)))
        retry_sleep = max(0.0, float(os.getenv("KIWOOM_INDEX_RATE_LIMIT_SLEEP_SEC", "1.2") or 1.2))
        last_error = ""
        for attempt in range(retry_max + 1):
            _, response = self.http.request(
                "POST",
                path,
                headers=headers,
                json_body=body,
                dry_run=False,
            )
            if response is None:
                raise RuntimeError("HTTP response is None")
            try:
                payload = json.loads(response.text) if response.text else {}
            except Exception:
                payload = {}
            code = str(payload.get("return_code") or "").strip()
            if not code or code == "0":
                return dict(payload)
            message = str(payload.get("return_msg") or "").strip()
            last_error = f"kiwoom_market_index_error:return_code={code} return_msg={message}"
            if code == "5" and ("1700" in message or "허용된 요청" in message) and attempt < retry_max:
                time.sleep(retry_sleep)
                continue
            raise RuntimeError(last_error)
        raise RuntimeError(last_error or "kiwoom_market_index_error")

    def get_index_snapshot(self, name: str) -> MarketIndexSnapshot:
        index_name = str(name or "").strip().upper()
        code = INDEX_CODES.get(index_name, index_name)
        resolved_name = next((key for key, value in INDEX_CODES.items() if value == code), index_name)
        if code not in set(INDEX_CODES.values()):
            raise ValueError(f"unsupported_market_index:{name}")

        payload = self._request(
            api_id=self.API_ID_DAILY,
            path=self.ENDPOINT_SECTOR,
            body={"mrkt_tp": "0", "inds_cd": code},
        )
        rows = payload.get("inds_cur_prc_daly_rept") if isinstance(payload.get("inds_cur_prc_daly_rept"), list) else []
        first = dict(rows[0] or {}) if rows and isinstance(rows[0], dict) else {}
        second = dict(rows[1] or {}) if len(rows) > 1 and isinstance(rows[1], dict) else {}

        current = _price(payload.get("cur_prc"))
        if current is None:
            current = _price(first.get("cur_prc_n"))
        change = _signed(payload.get("pred_pre"))
        if change is None:
            change = _signed(first.get("pred_pre_n"))
        change_pct = _signed(payload.get("flu_rt"))
        if change_pct is None:
            change_pct = _signed(first.get("flu_rt_n"))

        previous_close = _price(second.get("cur_prc_n"))
        previous_source = "kiwoom.ka20009.daily_row"
        if previous_close is None and current is not None and change is not None:
            previous_close = float(current) - float(change)
            previous_source = "kiwoom.ka20009.current_minus_change"

        return MarketIndexSnapshot(
            name=resolved_name,
            code=code,
            current=current,
            previous_close=previous_close,
            change=change,
            change_pct=change_pct,
            open=_price(payload.get("open_pric")),
            high=_price(payload.get("high_pric")),
            low=_price(payload.get("low_pric")),
            volume=_parse_kiwoom_number(payload.get("trde_qty")),
            value=_parse_kiwoom_number(payload.get("trde_prica")),
            rising=_safe_int(payload.get("rising")),
            falling=_safe_int(payload.get("fall")),
            unchanged=_safe_int(payload.get("stdns")),
            current_date=str(first.get("dt_n") or ""),
            previous_date=str(second.get("dt_n") or ""),
            ts=int(time.time()),
            source="kiwoom.ka20009",
            previous_close_source=previous_source,
        )

    def get_index_packet(self, names: Iterable[str] = ("KOSPI", "KOSDAQ")) -> Dict[str, Any]:
        indices: Dict[str, Dict[str, Any]] = {}
        errors: Dict[str, str] = {}
        name_list = list(names)
        request_gap = max(0.0, float(os.getenv("KIWOOM_INDEX_REQUEST_GAP_SEC", "1.2") or 1.2))
        for idx, name in enumerate(name_list):
            key = str(name or "").strip().upper()
            try:
                snapshot = self.get_index_snapshot(key)
                indices[snapshot.name] = snapshot.to_dict()
            except Exception as exc:
                errors[key] = str(exc)
            if idx < len(name_list) - 1 and request_gap > 0.0:
                time.sleep(request_gap)

        change_values = [
            float(row.get("change_pct"))
            for row in indices.values()
            if isinstance(row, dict) and row.get("change_pct") not in (None, "")
        ]
        rising = sum(int(row.get("rising") or 0) for row in indices.values() if isinstance(row, dict))
        falling = sum(int(row.get("falling") or 0) for row in indices.values() if isinstance(row, dict))
        unchanged = sum(int(row.get("unchanged") or 0) for row in indices.values() if isinstance(row, dict))
        breadth_total = rising + falling + unchanged
        breadth = ((rising - falling) / breadth_total) if breadth_total > 0 else None
        return {
            "status": "ok" if len(indices) == len(name_list) else "partial" if indices else "unavailable",
            "source": "kiwoom.ka20009",
            "indices": indices,
            "errors": errors,
            "average_change_pct": (sum(change_values) / len(change_values)) if change_values else None,
            "breadth": breadth,
            "rising": rising,
            "falling": falling,
            "unchanged": unchanged,
            "ts": int(time.time()),
        }
