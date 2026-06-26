from libs.runtime.kiwoom_market_status import parse_market_status_messages
from libs.runtime.market_status_closeout import apply_market_status_closeout_events


def test_parse_market_status_closeout_notice():
    events = parse_market_status_messages(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "0s",
                    "values": {"215": "2", "20": "152000", "214": "000600"},
                }
            ],
        }
    )

    assert len(events) == 1
    assert events[0]["code"] == "2"
    assert events[0]["label"] == "closeout_notice"
    assert events[0]["exchange_time"] == "152000"


def test_parse_market_status_regular_session_r_code():
    events = parse_market_status_messages(
        {
            "trnm": "REAL",
            "data": [{"type": "0s", "values": {"215": "R", "20": "090030"}}],
        }
    )

    assert events[0]["label"] == "regular_session_open"


def test_current_open_status_clears_stale_closeout_notice(monkeypatch):
    open_event = {
        "event_id": "2026-06-25T00:00:30+00:00:R:090030",
        "received_at": "2026-06-25T00:00:30+00:00",
        "code": "R",
        "label": "regular_session_open",
        "exchange_time": "090030",
    }
    old_closeout = {
        "event_id": "2026-06-24T06:20:00+00:00:2:152000",
        "received_at": "2026-06-24T06:20:00+00:00",
        "code": "2",
        "label": "closeout_notice",
        "exchange_time": "152000",
    }
    monkeypatch.setattr(
        "libs.runtime.market_status_closeout.load_market_status",
        lambda: {"current": open_event, "events": [old_closeout, open_event]},
    )
    state = {
        "persisted_state": {
            "kiwoom_closeout_notice_active": True,
            "processed_market_status_event_ids": [open_event["event_id"]],
        }
    }

    result = apply_market_status_closeout_events(state)

    assert result["kiwoom_closeout_notice_active"] is False
    assert result["persisted_state"]["kiwoom_closeout_notice_active"] is False
    assert result["persisted_state"]["kiwoom_market_status"]["code"] == "R"
    assert old_closeout["event_id"] not in result["persisted_state"]["processed_market_status_event_ids"]


def test_stale_current_closeout_does_not_keep_today_closeout_active(monkeypatch):
    stale_closeout = {
        "event_id": "2026-06-25T06:30:00+00:00:4:153000",
        "received_at": "2026-06-25T06:30:00+00:00",
        "code": "4",
        "label": "regular_session_close",
        "exchange_time": "153000",
    }
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            from datetime import datetime

            return datetime(2026, 6, 26, 9, 10, tzinfo=tz)

        @classmethod
        def fromisoformat(cls, value):  # type: ignore[no-untyped-def]
            from datetime import datetime

            return datetime.fromisoformat(value)

    monkeypatch.setattr(
        "libs.runtime.market_status_closeout.load_market_status",
        lambda: {"current": stale_closeout, "events": [stale_closeout]},
    )
    monkeypatch.setattr("libs.runtime.market_status_closeout.datetime", FixedDatetime)
    state = {"persisted_state": {"kiwoom_closeout_notice_active": True}}

    result = apply_market_status_closeout_events(state)

    assert result["kiwoom_closeout_notice_active"] is False
    assert result["kiwoom_market_status_stale"] is True
    assert result["persisted_state"]["kiwoom_closeout_notice_active"] is False
