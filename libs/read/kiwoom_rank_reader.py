from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from libs.core.settings import Settings
from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


class RankMode(str, Enum):
    VOLUME = "volume"
    VALUE = "value"
    CHANGE_RATE = "change_rate"


def _extract_symbols(payload: Any) -> List[str]:
    """Best-effort extraction of symbol list from Kiwoom rank API payload.

    Different endpoints may return different shapes. We attempt:
      - payload['output'] list of dicts
      - payload['output1'] list
      - payload['data'] list
      - any list value of dicts
    Accept keys:
      - 'stk_cd', 'stkcode', 'code', 'symbol'
    """
    if not isinstance(payload, dict):
        return []

    candidates: List[Any] = []
    for key in ("output", "output1", "output2", "data", "list", "items"):
        v = payload.get(key)
        if isinstance(v, list):
            candidates = v
            break
    if not candidates:
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                candidates = v
                break

    syms: List[str] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        for k in ("stk_cd", "stkcode", "stk_code", "code", "symbol"):
            if k in row and row[k]:
                s = str(row[k]).strip()
                if s:
                    syms.append(s)
                    break
    # de-dup preserving order
    seen = set()
    out: List[str] = []
    for s in syms:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


@dataclass(frozen=True)
class RankFetchResult:
    url: str
    status_code: Optional[int]
    ok: bool
    payload: Dict[str, Any]


class KiwoomRankReader:
    """Reader for Kiwoom rank endpoints (/api/dostk/rkinfo).

    Uses:
      - ka10030: 당일거래량상위요청 (sort_tp=1 volume, sort_tp=3 value)
      - ka10031: 전일대비등락률상위요청 (when available)

    Note: exact response fields may vary. We parse best-effort.
    """

    ENDPOINT = "/api/dostk/rkinfo"

    def __init__(self, settings: Settings, http: HttpClient, token: KiwoomTokenClient):
        self.s = settings
        self.http = http
        self.token = token

    @classmethod
    def from_env(cls) -> "KiwoomRankReader":
        s = Settings.from_env()
        base = s.kiwoom_base_url_mock if s.kiwoom_mode == "mock" else s.kiwoom_base_url_real
        http = HttpClient(
            base_url=base,
            timeout_sec=int(s.kiwoom_http_timeout_sec),
            retry_max=int(s.kiwoom_retry_max),
        )
        token = KiwoomTokenClient(s, http)
        return cls(s, http, token)

    def get_top_symbols(self, *, mode: RankMode, topk: int = 5) -> List[str]:
        tok = self.token.ensure_token(dry_run=False)
        if not tok.token:
            raise RuntimeError(f"Token not available: {tok.action} {tok.reason}")

        headers: Dict[str, Any] = {}
        headers.update(self.token.auth_headers(tok.token))
        headers["Content-Type"] = "application/json;charset=UTF-8"

        # Default filters (safe): exclude preferred shares/ETFs where possible.
        # See api_catalog for details; keep minimal required fields.
        if mode in (RankMode.VOLUME, RankMode.VALUE):
            body = {
                "sort_tp": "1" if mode == RankMode.VOLUME else "3",
                "mang_stk_incls": "1",
                "crd_tp": "0",
                "trde_qty_tp": "0",
                "pric_tp": "0",
                "trde_prica_tp": "0",
                "mrkt_open_tp": "1",
                "stex_tp": "1",  # KRX
            }
        else:
            # CHANGE_RATE: best-effort (uses same endpoint in catalog; parameters may differ by api_id)
            body = {
                "sort_tp": "1",
                "mang_stk_incls": "1",
                "stex_tp": "1",
            }

        url, resp = self.http.request("POST", self.ENDPOINT, headers=headers, json_body=body, dry_run=False)
        if resp is None:
            raise RuntimeError("HTTP response is None (unexpected: dry_run?)")

        payload: Dict[str, Any] = {}
        try:
            payload = json.loads(resp.text) if resp.text else {}
        except Exception:
            payload = {}

        syms = _extract_symbols(payload)
        return syms[: max(1, int(topk))]
