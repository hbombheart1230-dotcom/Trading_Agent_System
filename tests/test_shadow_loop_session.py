from datetime import datetime
from zoneinfo import ZoneInfo

from libs.runtime.shadow_loop_session import should_stop_shadow_loop


KST = ZoneInfo("Asia/Seoul")


def test_shadow_loop_stays_alive_until_final_artifacts_can_finish() -> None:
    assert should_stop_shadow_loop(
        day="2026-08-21",
        now=datetime(2026, 8, 21, 16, 5, tzinfo=KST),
    ) is False


def test_shadow_loop_stops_after_closeout_window() -> None:
    assert should_stop_shadow_loop(
        day="2026-08-21",
        now=datetime(2026, 8, 21, 16, 10, tzinfo=KST),
    ) is True


def test_shadow_loop_stops_when_configured_day_is_stale() -> None:
    assert should_stop_shadow_loop(
        day="2026-08-20",
        now=datetime(2026, 8, 21, 9, 0, tzinfo=KST),
    ) is True
