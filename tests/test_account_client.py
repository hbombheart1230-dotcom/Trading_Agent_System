import json
from types import SimpleNamespace

from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_account_client import KiwoomAccountClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings


class DummySession:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def request(self, **kwargs):
        kwargs = dict(kwargs)
        if isinstance(kwargs.get("headers"), dict):
            kwargs["headers"] = dict(kwargs["headers"])
        self.calls.append(kwargs)
        class R:
            status_code = 200
            headers = {}
            text = json.dumps({"return_code": 0, "return_msg": "ok", "day_bal_rt": []})
        if self.responses:
            R.text = json.dumps(self.responses.pop(0), ensure_ascii=False)
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


def test_get_account_balance_uses_kiwoom_account_endpoint_contract(tmp_path, monkeypatch):
    s = make_settings(tmp_path, monkeypatch)
    sess = DummySession()
    http = HttpClient(s.base_url, session=sess, retry_max=0)
    token_cli = KiwoomTokenClient(s, http)
    acct = KiwoomAccountClient(s, http, token_cli)

    monkeypatch.setattr(
        token_cli,
        "ensure_token",
        lambda dry_run=False, force_refresh=False: SimpleNamespace(token="tok", action="cache_hit", reason=""),
    )
    monkeypatch.setattr(
        token_cli,
        "auth_headers",
        lambda token: {"Authorization": f"Bearer {token}"},
    )

    res = acct.get_account_balance(dry_run=False)
    assert res.ok is True
    assert len(sess.calls) == 1
    call = sess.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/api/dostk/acnt")
    headers = call.get("headers") or {}
    assert headers.get("api-id") == "kt00018"
    assert "Authorization" in headers
    body = call.get("json") or {}
    assert body.get("qry_tp") == "1"
    assert body.get("dmst_stex_tp") == "KRX"


def test_get_account_balance_retries_once_after_invalid_token(tmp_path, monkeypatch):
    s = make_settings(tmp_path, monkeypatch)
    sess = DummySession(
        responses=[
            {"return_code": 3, "return_msg": "인증에 실패했습니다[8005:Token이 유효하지 않습니다]"},
            {"return_code": 0, "return_msg": "ok", "acnt_evlt_remn_indv_tot": []},
        ]
    )
    http = HttpClient(s.base_url, session=sess, retry_max=0)
    token_cli = KiwoomTokenClient(s, http)
    acct = KiwoomAccountClient(s, http, token_cli)
    calls = []

    def ensure_token(dry_run=False, force_refresh=False):  # type: ignore[no-untyped-def]
        calls.append(bool(force_refresh))
        token = "new-token" if force_refresh else "old-token"
        return SimpleNamespace(token=token, action="refreshed", reason="")

    monkeypatch.setattr(token_cli, "ensure_token", ensure_token)
    monkeypatch.setattr(token_cli, "auth_headers", lambda token: {"Authorization": f"Bearer {token}"})

    res = acct.get_account_balance(dry_run=False)

    assert res.ok is True
    assert calls == [False, True]
    assert len(sess.calls) == 2
    assert sess.calls[0]["headers"]["Authorization"] == "Bearer old-token"
    assert sess.calls[1]["headers"]["Authorization"] == "Bearer new-token"
