import pytest

from libs.core.http_client import HttpClient


class DummySession:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        class R:
            status_code = 200
            headers = {"X": "1"}
            text = "OK"
        return R()


def test_build_url():
    c = HttpClient("https://mockapi.kiwoom.com", session=DummySession())
    assert c.build_url("/v1/test") == "https://mockapi.kiwoom.com/v1/test"


def test_dry_run_no_call():
    sess = DummySession()
    c = HttpClient("https://mockapi.kiwoom.com", session=sess)
    url, resp = c.request("GET", "/v1/test", dry_run=True)
    assert url.endswith("/v1/test")
    assert resp is None
    assert len(sess.calls) == 0


def test_request_calls_session():
    sess = DummySession()
    c = HttpClient("https://mockapi.kiwoom.com", session=sess, timeout_sec=3, retry_max=0)
    url, resp = c.request("GET", "/v1/test", headers={"A": "B"}, params={"q": "1"})
    assert url.endswith("/v1/test")
    assert resp is not None
    assert resp.status_code == 200
    assert len(sess.calls) == 1
    call = sess.calls[0]
    assert call["timeout"] == 3
    assert call["headers"]["A"] == "B"
    assert call["params"]["q"] == "1"
