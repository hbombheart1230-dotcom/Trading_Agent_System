from libs.runtime.kiwoom_market_status import parse_market_status_messages


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
