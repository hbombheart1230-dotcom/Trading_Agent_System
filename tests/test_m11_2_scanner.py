from graphs.nodes.scan_candidates import scan_candidates
from graphs.nodes.select_candidate import select_candidate

def test_scan_candidates_default():
    st = {}
    out = scan_candidates(st)
    assert "candidates" in out
    assert isinstance(out["candidates"], list)
    assert len(out["candidates"]) >= 1

def test_select_candidate_sets_symbol_when_missing():
    st = {"candidates": ["005930", "000660"]}
    out = select_candidate(st)
    assert out["selected_symbol"] == "005930"
    assert out["symbol"] == "005930"

def test_select_candidate_keeps_existing_symbol():
    st = {"symbol": "035420", "candidates": ["005930"]}
    out = select_candidate(st)
    assert out["selected_symbol"] == "035420"
    assert out["symbol"] == "035420"
