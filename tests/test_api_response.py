from libs.core.api_response import ApiResponse

def test_ok_json():
    r = ApiResponse.from_http(200, '{"a":1}')
    assert r.ok is True
    assert r.payload["a"] == 1

def test_error_json():
    r = ApiResponse.from_http(400, '{"error_code":"E1","error_message":"bad"}')
    assert r.ok is False
    assert r.error_code == "E1"
    assert r.error_message == "bad"

def test_non_json():
    r = ApiResponse.from_http(500, "<html>err</html>")
    assert r.ok is False
    assert "_raw" in r.payload
