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
