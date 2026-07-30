from __future__ import annotations

from libs.core.http_client import HttpClientError
from libs.runtime.monitor_minute_ohlcv import _run_monitor_minute_skill


class _TransportFailureRunner:
    def run(self, **kwargs):
        raise HttpClientError("temporary DNS failure")


def test_monitor_minute_transport_failure_becomes_safe_unavailable_result() -> None:
    result = _run_monitor_minute_skill(
        runner=_TransportFailureRunner(),
        run_id="RUN_1",
        symbol="005930",
        timeframe_minutes=1,
    )

    payload = result["result"]
    assert payload["action"] == "error"
    assert payload["question"] == "market.minute_ohlcv transport unavailable"
    assert payload["meta"] == {
        "reason": "minute_ohlcv_transport_error",
        "error_type": "HttpClientError",
        "transient": True,
    }
