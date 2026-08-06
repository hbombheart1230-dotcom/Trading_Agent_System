import time
from pathlib import Path

from libs.kiwoom.token_cache import TokenCache, TokenRecord


def test_token_cache_roundtrip(tmp_path):
    p = tmp_path / "token.json"
    cache = TokenCache(p)
    rec = TokenRecord(access_token="abc", expires_at_epoch=int(time.time()) + 3600, raw={"x": 1})
    cache.save(rec)

    loaded = cache.load()
    assert loaded is not None
    assert loaded.access_token == "abc"
    assert loaded.raw["x"] == 1


def test_token_cache_prefers_kiwoom_expiry_datetime(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(
        '{"access_token":"abc","expires_at_epoch":1,"raw":{"expires_dt":"20300102123456"}}',
        encoding="utf-8",
    )

    loaded = TokenCache(path).load()

    assert loaded is not None
    assert loaded.expires_at_epoch > 1
