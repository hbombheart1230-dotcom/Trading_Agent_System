from __future__ import annotations

import json
import time

from libs.core.http_client import HttpClient, HttpResponse
from libs.core.settings import Settings
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.read.kiwoom_market_index_reader import KiwoomMarketIndexReader


class StubHttp(HttpClient):
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def request(self, method, path, *, headers=None, params=None, json_body=None, data=None, dry_run=False):  # type: ignore
        self.requests.append({"method": method, "path": path, "headers": dict(headers or {}), "json_body": dict(json_body or {})})
        payload = self.payloads.pop(0)
        return "https://mockapi.kiwoom.com/api/dostk/sect", HttpResponse(status_code=200, headers={}, text=json.dumps(payload))


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


def test_kiwoom_market_index_reader_parses_current_and_previous_close():
    payload = {
        "cur_prc": "-2384.71",
        "pred_pre": "-288.25",
        "flu_rt": "-10.78",
        "open_pric": "-2669.53",
        "high_pric": "-2669.53",
        "low_pric": "-2375.21",
        "trde_qty": "1103",
        "trde_prica": "48151",
        "rising": "18",
        "stdns": "183",
        "fall": "132",
        "inds_cur_prc_daly_rept": [
            {"dt_n": "20241122", "cur_prc_n": "-2384.71", "flu_rt_n": "-10.78"},
            {"dt_n": "20241121", "cur_prc_n": "+2672.96", "flu_rt_n": "+0.97"},
        ],
        "return_code": 0,
    }
    http = StubHttp([payload])
    reader = KiwoomMarketIndexReader(Settings.from_env(), http, StubToken())

    snapshot = reader.get_index_snapshot("KOSPI")

    assert snapshot.name == "KOSPI"
    assert snapshot.code == "001"
    assert snapshot.current == 2384.71
    assert snapshot.previous_close == 2672.96
    assert snapshot.change == -288.25
    assert snapshot.change_pct == -10.78
    assert snapshot.current_date == "20241122"
    assert snapshot.previous_date == "20241121"
    assert http.requests[0]["headers"]["api-id"] == "ka20009"
    assert http.requests[0]["json_body"] == {"mrkt_tp": "0", "inds_cd": "001"}


def test_kiwoom_market_index_reader_builds_packet_breadth(monkeypatch):
    monkeypatch.setenv("KIWOOM_INDEX_REQUEST_GAP_SEC", "0")
    kospi = {
        "cur_prc": "+3000.00",
        "pred_pre": "+15.00",
        "flu_rt": "+0.50",
        "rising": "500",
        "stdns": "50",
        "fall": "350",
        "inds_cur_prc_daly_rept": [{"dt_n": "20260506", "cur_prc_n": "+3000.00"}, {"dt_n": "20260505", "cur_prc_n": "+2985.00"}],
        "return_code": 0,
    }
    kosdaq = {
        "cur_prc": "+900.00",
        "pred_pre": "+9.00",
        "flu_rt": "+1.01",
        "rising": "700",
        "stdns": "100",
        "fall": "400",
        "inds_cur_prc_daly_rept": [{"dt_n": "20260506", "cur_prc_n": "+900.00"}, {"dt_n": "20260505", "cur_prc_n": "+891.00"}],
        "return_code": 0,
    }
    reader = KiwoomMarketIndexReader(Settings.from_env(), StubHttp([kospi, kosdaq]), StubToken())

    packet = reader.get_index_packet()

    assert packet["status"] == "ok"
    assert packet["indices"]["KOSPI"]["previous_close"] == 2985.0
    assert packet["indices"]["KOSDAQ"]["change_pct"] == 1.01
    assert abs(float(packet["average_change_pct"]) - 0.755) < 1e-9
    assert packet["breadth"] > 0
