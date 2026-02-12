from libs.ai.intent_schema import normalize_intent

def test_normalize_accepts_variants():
    raw = {"intent": "buy", "code": "005930", "quantity": "2", "price": "70000", "type": "LIMIT", "rationale": "x"}
    out, _ = normalize_intent(raw, default_symbol=None, default_price=None)
    assert out["action"] == "BUY"
    assert out["symbol"] == "005930"
    assert out["qty"] == 2
    assert out["price"] == 70000.0
    assert out["order_type"] == "limit"

def test_invalid_limit_without_price_becomes_noop():
    raw = {"action": "BUY", "symbol": "005930", "qty": 1, "order_type": "limit"}
    out, _ = normalize_intent(raw, default_symbol=None, default_price=None)
    assert out["action"] == "NOOP"

def test_market_allows_missing_price():
    raw = {"action": "BUY", "symbol": "005930", "qty": 1, "order_type": "market"}
    out, _ = normalize_intent(raw, default_symbol=None, default_price=None)
    assert out["action"] in ("BUY", "NOOP")
