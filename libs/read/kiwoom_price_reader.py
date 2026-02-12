from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from libs.core.settings import Settings
from libs.core.http_client import HttpClient, HttpResponse
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.read.snapshot_models import MarketSnapshot


def _parse_kiwoom_number(x: Any) -> float:
    """Parse Kiwoom numeric strings like '+123', '-2394.49', '00123' etc."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return 0.0
    s = s.replace(",", "")
    # remove leading + sign
    if s.startswith("+"):
        s = s[1:]
    try:
        return float(s)
    except ValueError:
        # fallback: extract first number-like token
        import re
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


@dataclass(frozen=True)
class PriceFetchResult:
    url: str
    status_code: Optional[int]
    ok: bool
    payload: Dict[str, Any]


class KiwoomPriceReader:
    """Real reader (mock or real host depending on Settings.KIWOOM_MODE).
    Uses ka10001 (주식기본정보요청) endpoint to get current price (cur_prc).
    """

    API_ID = "ka10001"
    ENDPOINT = "/api/dostk/stkinfo"

    def __init__(self, settings: Settings, http: HttpClient, token: KiwoomTokenClient):
        self.s = settings
        self.http = http
        self.token = token

    @classmethod
    def from_env(cls) -> "KiwoomPriceReader":
        s = Settings.from_env()
        base = s.kiwoom_base_url_mock if s.kiwoom_mode == "mock" else s.kiwoom_base_url_real
        http = HttpClient(
            base_url=base,
            timeout_sec=int(s.kiwoom_http_timeout_sec),
            retry_max=int(s.kiwoom_retry_max),
        )
        token = KiwoomTokenClient(s, http)
        return cls(s, http, token)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        # ensure token (real HTTP call even in mock trading)
        tok = self.token.ensure_token(dry_run=False)
        if not tok.token:
            raise RuntimeError(f"Token not available: {tok.action} {tok.reason}")

        headers: Dict[str, Any] = {}
        headers.update(self.token.auth_headers(tok.token))
        headers["Content-Type"] = "application/json;charset=UTF-8"

        body = {"stk_cd": str(symbol)}

        url, resp = self.http.request(
            "POST",
            self.ENDPOINT,
            headers=headers,
            json_body=body,
            dry_run=False,
        )
        if resp is None:
            raise RuntimeError("HTTP response is None (unexpected: dry_run?)")

        payload = {}
        try:
            payload = json.loads(resp.text) if resp.text else {}
        except Exception:
            payload = {}

        # expected field: cur_prc
        price = _parse_kiwoom_number(payload.get("cur_prc"))
        return MarketSnapshot(symbol=str(symbol), price=price, ts=int(time.time()))
