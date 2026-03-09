import json
import time

import pytest

from libs.read.kiwoom_price_reader import KiwoomPriceReader
from libs.core.settings import Settings
from libs.core.http_client import HttpClient, HttpResponse
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


class StubHttp(HttpClient):
    def __init__(self, text: str):
        self._text = text
        self.last_headers = None
        self.last_json_body = None

    def build_url(self, path: str) -> str:  # type: ignore
        return "https://mockapi.kiwoom.com" + path

    def request(self, method, path, *, headers=None, params=None, json_body=None, data=None, dry_run=False):  # type: ignore
        self.last_headers = dict(headers or {})
        self.last_json_body = dict(json_body or {})
        url = self.build_url(path)
        return url, HttpResponse(status_code=200, headers={}, text=self._text)


class StubToken(KiwoomTokenClient):
    def __init__(self):
        pass

    def ensure_token(self, *, dry_run: bool = False):  # type: ignore
        class R:
            action = "stub"
            token = "stubtoken"
            expires_at_epoch = int(time.time()) + 3600
            reason = "stub"
            url = ""
        return R()

    def auth_headers(self, token: str):  # type: ignore
        return {"Authorization": f"Bearer {token}"}


def test_kiwoom_price_reader_parses_cur_prc():
    s = Settings.from_env()
    http = StubHttp(text=json.dumps({"cur_prc": "+71200", "return_code": 0}))
    token = StubToken()
    r = KiwoomPriceReader(s, http, token)
    snap = r.get_market_snapshot("005930")
    assert snap.symbol == "005930"
    assert snap.price == 71200.0


def test_kiwoom_price_reader_sends_required_headers_and_abs_price():
    s = Settings.from_env()
    http = StubHttp(text=json.dumps({"cur_prc": "-71200", "return_code": 0}))
    token = StubToken()
    r = KiwoomPriceReader(s, http, token)

    snap = r.get_market_snapshot("005930")
    assert snap.price == 71200.0
    assert http.last_json_body == {"stk_cd": "005930"}
    assert isinstance(http.last_headers, dict)
    assert http.last_headers.get("Authorization") == "Bearer stubtoken"
    assert http.last_headers.get("Content-Type") == "application/json;charset=UTF-8"
    assert http.last_headers.get("api-id") == "ka10001"
    assert "appkey" in http.last_headers
    assert "appsecret" in http.last_headers


def test_kiwoom_price_reader_raises_on_return_code_error():
    s = Settings.from_env()
    http = StubHttp(text=json.dumps({"return_code": 2, "return_msg": "API ID missing"}))
    token = StubToken()
    r = KiwoomPriceReader(s, http, token)

    with pytest.raises(RuntimeError):
        r.get_market_snapshot("005930")
