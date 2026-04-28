from __future__ import annotations

from libs.read.kiwoom_theme_reader import build_theme_strength_packet


def test_theme_strength_packet_builds_from_state_mocks(monkeypatch):
    monkeypatch.delenv("MOCK_THEME_GROUPS", raising=False)
    monkeypatch.delenv("MOCK_THEME_COMPONENT_MAP", raising=False)
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)

    packet = build_theme_strength_packet(
        {
            "mock_theme_groups": [
                {
                    "thema_grp_cd": "319",
                    "thema_nm": "semiconductor",
                    "stk_num": "4",
                    "flu_rt": "+4.0",
                    "rising_stk_num": "3",
                    "fall_stk_num": "0",
                    "dt_prft_rt": "+12.0",
                },
                {
                    "thema_grp_cd": "401",
                    "thema_nm": "battery",
                    "stk_num": "5",
                    "flu_rt": "+1.0",
                    "rising_stk_num": "1",
                    "fall_stk_num": "2",
                    "dt_prft_rt": "+2.0",
                },
            ],
            "mock_theme_component_map": {
                "semiconductor": [
                    {"stk_cd": "005930", "stk_nm": "Samsung", "flu_rt": "+2.5"},
                    {"stk_cd": "A000660", "stk_nm": "SK Hynix", "flu_rt": "+3.0"},
                ],
                "battery": ["373220"],
            },
        }
    )

    assert packet["status"] == "ok"
    assert packet["source"] == "state_mock"
    assert packet["top_themes"][0]["theme_name"] == "semiconductor"
    assert packet["theme_scores"]["semiconductor"] > packet["theme_scores"]["battery"]
    assert packet["theme_map"]["semiconductor"] == ["005930", "000660"]
    assert packet["component_symbols_by_theme"]["battery"] == ["373220"]


def test_theme_strength_packet_reports_unavailable_when_live_disabled(monkeypatch):
    monkeypatch.delenv("MOCK_THEME_GROUPS", raising=False)
    monkeypatch.delenv("MOCK_THEME_COMPONENT_MAP", raising=False)
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)

    packet = build_theme_strength_packet({})

    assert packet["status"] == "unavailable"
    assert packet["source"] == "unavailable"
    assert packet["reason"] == "kiwoom_theme_live_fetch_disabled"
    assert packet["theme_scores"] == {}
    assert packet["theme_map"] == {}


def test_theme_strength_packet_uses_commander_scanner_live_fetch_without_env(monkeypatch):
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)
    monkeypatch.delenv("KIWOOM_THEME_FETCH_COMPONENTS", raising=False)
    monkeypatch.setenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", "true")

    class _FakeReader:
        @staticmethod
        def from_env():
            return _FakeReader()

        def get_theme_groups(self, *, limit=20, date_tp="10", stex_tp="1"):
            return [
                {
                    "theme_code": "319",
                    "theme_name": "semiconductor",
                    "stock_count": 4,
                    "rising_count": 3,
                    "falling_count": 0,
                    "change_rate": 4.0,
                    "period_return": 12.0,
                }
            ]

        def get_theme_components(self, *, theme_code, limit=100, stex_tp="1"):
            assert theme_code == "319"
            return [
                {"symbol": "005930", "name": "Samsung", "change_rate": 2.5},
                {"symbol": "000660", "name": "SK Hynix", "change_rate": 3.0},
            ]

    monkeypatch.setattr("libs.read.kiwoom_theme_reader.KiwoomThemeReader", _FakeReader)

    packet = build_theme_strength_packet(
        {
            "applied_policy": {
                "scanner": {
                    "kiwoom": {
                        "live_fetch": True,
                    }
                }
            }
        }
    )

    assert packet["status"] == "ok"
    assert packet["source"] == "kiwoom_live"
    assert packet["reason"] == "ka90001"
    assert packet["component_source"] == "kiwoom_live.ka90002"
    assert packet["theme_map"]["semiconductor"] == ["005930", "000660"]


def test_theme_specific_live_fetch_false_overrides_commander_scanner_live_fetch(monkeypatch):
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)
    monkeypatch.setenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", "true")

    packet = build_theme_strength_packet(
        {
            "theme_live_fetch": False,
            "applied_policy": {
                "scanner": {
                    "kiwoom": {
                        "live_fetch": True,
                    }
                }
            },
        }
    )

    assert packet["status"] == "unavailable"
    assert packet["source"] == "unavailable"
    assert packet["reason"] == "kiwoom_theme_live_fetch_disabled"
