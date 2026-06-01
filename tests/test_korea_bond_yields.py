from __future__ import annotations

from libs.market.korea_bond_yields import fetch_korea_bond_yield_overrides


def test_fetch_korea_bond_yield_overrides_parses_kofia_rows(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<root><message><BISComDspDatListDTO>
<BISComDspDatDTO><val1>최고</val1><val2>3.760</val2><val3>4.239</val3></BISComDspDatDTO>
<BISComDspDatDTO><val1>2026-05-27</val1><val2>3.711</val2><val3>4.102</val3></BISComDspDatDTO>
<BISComDspDatDTO><val1>2026-05-26</val1><val2>3.664</val2><val3>4.073</val3></BISComDspDatDTO>
</BISComDspDatListDTO></message></root>
"""
    monkeypatch.setattr("libs.market.korea_bond_yields._fetch_kofia_xml", lambda **_: xml)

    out = fetch_korea_bond_yield_overrides({})

    assert out["kr_3y_yield"]["status"] == "ok"
    assert out["kr_3y_yield"]["source"] == "kofia"
    assert out["kr_3y_yield"]["current_yield_pct"] == 3.711
    assert out["kr_3y_yield"]["previous_yield_pct"] == 3.664
    assert round(float(out["kr_3y_yield"]["delta"]), 3) == 0.047
    assert out["kr_10y_yield"]["current_yield_pct"] == 4.102


def test_fetch_korea_bond_yield_overrides_returns_unavailable_on_error(monkeypatch):
    def _boom(**_):
        raise TimeoutError("timeout")

    monkeypatch.setattr("libs.market.korea_bond_yields._fetch_kofia_xml", _boom)

    out = fetch_korea_bond_yield_overrides({})

    assert out["kr_3y_yield"]["status"] == "unavailable"
    assert out["kr_3y_yield"]["source"] == "kofia"
    assert str(out["kr_3y_yield"]["reason"]).startswith("kofia_fetch_error:")
