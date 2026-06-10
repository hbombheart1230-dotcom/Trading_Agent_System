from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


def _parse_number(value: Any) -> Optional[float]:
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "time": _text(row.get("cntr_tm")),
        "kospi200": _parse_number(row.get("kospi200")),
        "basis": _parse_number(row.get("basis")),
        "all_sell": _parse_number(row.get("all_sel")),
        "all_buy": _parse_number(row.get("all_buy")),
        "all_net_buy": _parse_number(row.get("all_netprps")),
        "arbitrage_sell": _parse_number(row.get("dfrt_trde_sel")),
        "arbitrage_buy": _parse_number(row.get("dfrt_trde_buy")),
        "arbitrage_net_buy": _parse_number(row.get("dfrt_trde_netprps")),
        "non_arbitrage_sell": _parse_number(row.get("ndiffpro_trde_sel")),
        "non_arbitrage_buy": _parse_number(row.get("ndiffpro_trde_buy")),
        "non_arbitrage_net_buy": _parse_number(row.get("ndiffpro_trde_netprps")),
        "raw": dict(row),
    }


class KiwoomProgramTradingReader:
    """Read KOSPI program trading flow, KOSPI200, and basis context.

    Kiwoom REST docs expose this through ka90005. This is not a direct futures
    price feed, but the KOSPI200 + basis fields are useful as observation-only
    derivatives pressure evidence.
    """

    API_ID_INTRADAY = "ka90005"
    ENDPOINT_MARKET_CONDITION = "/api/dostk/mrkcond"

    def __init__(self, settings: Settings, http: HttpClient, token: KiwoomTokenClient):
        self.s = settings
        self.http = http
        self.token = token

    @classmethod
    def from_env(cls) -> "KiwoomProgramTradingReader":
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

        retry_max = max(0, int(float(os.getenv("KIWOOM_PROGRAM_RETRY_MAX", "1") or 1)))
        retry_sleep = max(0.0, float(os.getenv("KIWOOM_PROGRAM_RATE_LIMIT_SLEEP_SEC", "1.2") or 1.2))
        last_error = ""
        for attempt in range(retry_max + 1):
            _, response = self.http.request("POST", path, headers=headers, json_body=body, dry_run=False)
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
            last_error = f"kiwoom_program_trading_error:return_code={code} return_msg={message}"
            if code == "5" and attempt < retry_max:
                time.sleep(retry_sleep)
                continue
            raise RuntimeError(last_error)
        raise RuntimeError(last_error or "kiwoom_program_trading_error")

    def get_intraday_packet(self, *, date: str = "") -> Dict[str, Any]:
        day = str(date or datetime.now().strftime("%Y%m%d")).replace("-", "")[:8]
        payload = self._request(
            api_id=self.API_ID_INTRADAY,
            path=self.ENDPOINT_MARKET_CONDITION,
            body={
                "date": day,
                "amt_qty_tp": "1",
                "mrkt_tp": "P00101",
                "min_tic_tp": "1",
                "stex_tp": "1",
            },
        )
        raw_rows = payload.get("prm_trde_trnsn") if isinstance(payload.get("prm_trde_trnsn"), list) else []
        rows: List[Dict[str, Any]] = [
            _row_to_dict(dict(row))
            for row in raw_rows
            if isinstance(row, dict)
        ]
        latest = dict(rows[0] or {}) if rows else {}
        return {
            "schema_version": "kiwoom_program_trading.v1",
            "source": "kiwoom.ka90005",
            "status": "ok" if rows else "unavailable",
            "date": day,
            "latest": latest,
            "rows": rows[:10],
            "row_count": len(rows),
            "basis": latest.get("basis"),
            "kospi200": latest.get("kospi200"),
            "all_net_buy": latest.get("all_net_buy"),
            "non_arbitrage_net_buy": latest.get("non_arbitrage_net_buy"),
            "arbitrage_net_buy": latest.get("arbitrage_net_buy"),
            "ts": int(time.time()),
        }


def fetch_kiwoom_program_trading_packet(*, date: str = "") -> Dict[str, Any]:
    return KiwoomProgramTradingReader.from_env().get_intraday_packet(date=date)
