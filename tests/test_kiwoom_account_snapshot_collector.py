from __future__ import annotations

from libs.read.kiwoom_account_snapshot_collector import (
    KiwoomAccountSnapshotCollector,
    _day_trade_symbols,
    _payload_call_result,
)


def test_payload_call_result_distinguishes_ok_error_and_mock_unsupported() -> None:
    assert _payload_call_result({"return_code": 0, "return_msg": "조회 완료"}) == ("ok", "")

    status, error = _payload_call_result(
        {"status": 400, "error": "BAD_REQUEST", "message": "Required request body is missing"}
    )
    assert status == "error"
    assert "http_status=400" in error

    status, error = _payload_call_result(
        {"return_code": 20, "return_msg": "[2000](RC9000:모의투자에서는 해당업무가 제공되지 않습니다.)"}
    )
    assert status == "unsupported"
    assert "return_code=20" in error


def test_day_trade_symbols_normalizes_and_deduplicates_codes() -> None:
    assert _day_trade_symbols(
        {
            "tdy_trde_diary": [
                {"stk_cd": "A005930"},
                {"stk_cd": "005930"},
                {"stk_cd": "000660"},
                {"stk_cd": ""},
            ]
        }
    ) == ["005930", "000660"]


def test_collect_marks_ka10077_not_applicable_without_traded_symbols() -> None:
    collector = object.__new__(KiwoomAccountSnapshotCollector)
    attempted: list[tuple[str, dict]] = []

    def fake_call(api_id: str, title: str, body: dict) -> dict:
        attempted.append((api_id, dict(body)))
        payload = {"return_code": 0}
        if api_id == "ka10170":
            payload["tdy_trde_diary"] = [{"stk_cd": ""}]
        return {"api_id": api_id, "title": title, "body": body, "status": "ok", "payload": payload}

    collector._call = fake_call  # type: ignore[method-assign]
    snapshot = collector.collect(day="2026-08-14")

    detail = [row for row in snapshot["calls"] if row["api_id"] == "ka10077"]
    assert detail[0]["status"] == "not_applicable"
    assert detail[0]["reason"] == "no_day_trade_symbols"
    assert not any(api_id == "ka10077" for api_id, _body in attempted)
    assert snapshot["summary"]["error_count"] == 0
    assert snapshot["summary"]["not_applicable_count"] == 1
    assert snapshot["summary"]["api_call_count"] == snapshot["summary"]["call_record_count"] - 1
