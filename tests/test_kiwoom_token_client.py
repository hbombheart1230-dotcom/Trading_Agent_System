import json
import time

import pytest

from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient, KiwoomAuthError
from libs.core.settings import Settings


class DummySession:
    def __init__(self, status_code=200, payload=None):
        self.calls = []
        self.status_code = status_code
        self.payload = payload or {"access_token": "tok", "token_type": "Bearer", "expires_in": 10}

    def request(self, **kwargs):
        self.calls.append(kwargs)
        class R:
            pass
        r = R()
        r.status_code = self.status_code
        r.headers = {}
        r.text = json.dumps(self.payload)
        return r


def make_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("KIWOOM_BASE_URL_MOCK", "https://mock.example")
    monkeypatch.setenv("KIWOOM_BASE_URL_REAL", "https://real.example")
    monkeypatch.setenv("KIWOOM_APP_KEY", "k")
    monkeypatch.setenv("KIWOOM_APP_SECRET", "s")
    monkeypatch.setenv("KIWOOM_TOKEN_CACHE_PATH", str(tmp_path / "token_cache.json"))
    monkeypatch.setenv("KIWOOM_TOKEN_REFRESH_MARGIN_SEC", "1")
    return Settings.from_env(env_path="__missing__.env")


def test_ensure_token_refresh_and_cache(tmp_path, monkeypatch):
    s = make_settings(tmp_path, monkeypatch)
    sess = DummySession(payload={"access_token": "tok1", "token_type": "Bearer", "expires_in": 100})
    http = HttpClient(s.base_url, session=sess, retry_max=0)
    cli = KiwoomTokenClient(s, http)

    res = cli.ensure_token()
    assert res.action == "refreshed"
    assert res.token == "tok1"
    assert len(sess.calls) == 1

    # second call should hit cache (not expired within margin)
    sess2 = DummySession(payload={"access_token": "tok2", "expires_in": 100})
    http2 = HttpClient(s.base_url, session=sess2, retry_max=0)
    cli2 = KiwoomTokenClient(s, http2)

    res2 = cli2.ensure_token()
    assert res2.action == "cache_hit"
    assert res2.token == "tok1"
    assert len(sess2.calls) == 0


def test_ensure_token_dry_run(tmp_path, monkeypatch):
    s = make_settings(tmp_path, monkeypatch)
    sess = DummySession(payload={"access_token": "tok1", "expires_in": 100})
    http = HttpClient(s.base_url, session=sess, retry_max=0)
    cli = KiwoomTokenClient(s, http)

    res = cli.ensure_token(dry_run=True)
    assert res.action == "dry_run"
    assert len(sess.calls) == 0


def test_missing_credentials_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("KIWOOM_BASE_URL_MOCK", "https://mock.example")
    monkeypatch.setenv("KIWOOM_BASE_URL_REAL", "https://real.example")
    monkeypatch.setenv("KIWOOM_APP_KEY", "")
    monkeypatch.setenv("KIWOOM_APP_SECRET", "")
    monkeypatch.setenv("KIWOOM_TOKEN_CACHE_PATH", str(tmp_path / "token_cache.json"))

    s = Settings.from_env(env_path="__missing__.env")
    http = HttpClient(s.base_url, session=DummySession(), retry_max=0)
    cli = KiwoomTokenClient(s, http)

    with pytest.raises(KiwoomAuthError):
        cli.ensure_token()
