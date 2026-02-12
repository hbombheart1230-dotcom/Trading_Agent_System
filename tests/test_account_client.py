import json

from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_account_client import KiwoomAccountClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings


class DummySession:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        class R:
            status_code = 200
            headers = {}
            text = json.dumps({"ok": True})
        return R()


def make_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("KIWOOM_BASE_URL_MOCK", "https://mock.example")
    monkeypatch.setenv("KIWOOM_BASE_URL_REAL", "https://real.example")
    monkeypatch.setenv("KIWOOM_APP_KEY", "k")
    monkeypatch.setenv("KIWOOM_APP_SECRET", "s")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIWOOM_TOKEN_CACHE_PATH", str(tmp_path / "token_cache.json"))
    return Settings.from_env(env_path="__missing__.env")


def test_get_account_balance_calls_http(tmp_path, monkeypatch):
    s = make_settings(tmp_path, monkeypatch)
    sess = DummySession()
    http = HttpClient(s.base_url, session=sess, retry_max=0)
    token_cli = KiwoomTokenClient(s, http)
    acct = KiwoomAccountClient(s, http, token_cli)

    res = acct.get_account_balance(dry_run=True)
    assert res.payload["action"] in ("dry_run", "cache_hit", "refreshed")
    # dry_run=True => no HTTP calls
    assert len(sess.calls) == 0
