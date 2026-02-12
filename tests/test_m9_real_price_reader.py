import json
import time

from libs.read.kiwoom_price_reader import KiwoomPriceReader
from libs.core.settings import Settings
from libs.core.http_client import HttpClient, HttpResponse
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


class StubHttp(HttpClient):
    def __init__(self, text: str):
        self._text = text

    def build_url(self, path: str) -> str:  # type: ignore
        return "https://mockapi.kiwoom.com" + path

    def request(self, method, path, *, headers=None, params=None, json_body=None, data=None, dry_run=False):  # type: ignore
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
