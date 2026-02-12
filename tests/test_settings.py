from libs.core.settings import Settings


def test_settings_base_url_mock(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("KIWOOM_BASE_URL_MOCK", "https://mock.example")
    monkeypatch.setenv("KIWOOM_BASE_URL_REAL", "https://real.example")

    s = Settings.from_env(env_path="__missing__.env")
    assert s.base_url == "https://mock.example"


def test_settings_base_url_real(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("KIWOOM_BASE_URL_MOCK", "https://mock.example")
    monkeypatch.setenv("KIWOOM_BASE_URL_REAL", "https://real.example")

    s = Settings.from_env(env_path="__missing__.env")
    assert s.base_url == "https://real.example"


def test_settings_defaults(monkeypatch):
    # ensure no env overrides exist
    for k in [
        "KIWOOM_MODE",
        "KIWOOM_HTTP_TIMEOUT_SEC",
        "KIWOOM_RETRY_MAX",
        "KIWOOM_PAGINATION_MAX_CALLS",
        "EVENT_LOG_PATH",
        "KIWOOM_API_CATALOG_PATH",
    ]:
        monkeypatch.delenv(k, raising=False)

    s = Settings.from_env(env_path="__missing__.env")
    assert s.kiwoom_mode == "mock"
    assert s.kiwoom_http_timeout_sec == 10
    assert s.kiwoom_retry_max == 2
    assert s.kiwoom_pagination_max_calls == 10
    assert s.event_log_path.endswith("events.jsonl")
    assert s.kiwoom_api_catalog_path.endswith("api_catalog.jsonl")
