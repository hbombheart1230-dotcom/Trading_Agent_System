from __future__ import annotations

from typing import Any, Dict


def _clip(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:max_len]


def _fallback_label(source: Any) -> str:
    return _clip(source, max_len=120) or "직접 확인 불가"


def price_truth_source_label(source: Any) -> str:
    token = _clip(source, max_len=80).lower()
    mapping = {
        "broker_fill": "브로커 체결가 기준",
        "account_mark": "계좌 평가 가격 기준",
        "monitor_mark": "모니터 관측값 기준",
        "unavailable": "직접 확인 불가",
        "not_available": "직접 확인 불가",
    }
    return mapping.get(token, _fallback_label(source))


def pnl_truth_source_label(source: Any) -> str:
    token = _clip(source, max_len=120)
    token_lower = token.lower()
    mapping = {
        "kiwoom.ka10077": "키움 당일 실현손익 기준(ka10077)",
        "broker_fill_account_snapshot_estimate": "브로커 체결가와 계좌 평가손익 역산 기준",
        "unavailable": "직접 확인 불가",
        "not_available": "직접 확인 불가",
    }
    return mapping.get(token_lower, _fallback_label(source))


def monitor_price_source_label(source: Any) -> str:
    token = _clip(source, max_len=120)
    token_lower = token.lower()
    mapping = {
        "position.current_price": "포지션 현재가 기준",
        "market.quote.price": "시장 체결가 조회 기준",
        "state.minute_ohlcv_by_symbol.close": "분봉 최신 종가 기준",
        "selected": "선택 종목 스냅샷 기준",
        "market_snapshot": "시장 스냅샷 기준",
        "unavailable": "직접 확인 불가",
        "not_available": "직접 확인 불가",
    }
    return mapping.get(token_lower, _fallback_label(source))


def truth_availability_line(availability: Dict[str, Any] | None) -> str:
    data = availability if isinstance(availability, dict) else {}
    def _label(flag: Any) -> str:
        return "있음" if bool(flag) else "없음"

    return (
        "truth 가용성: "
        f"브로커 체결가={_label(data.get('broker_fill_present'))}, "
        f"계좌 마크={_label(data.get('account_mark_present'))}, "
        f"모니터 가격={_label(data.get('monitor_mark_present'))}, "
        f"브로커 손익={_label(data.get('broker_pnl_present'))}."
    )


def with_ro_particle(label: Any) -> str:
    text = _clip(label, max_len=120)
    if not text:
        return "직접 확인 불가로"
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        jong = (code - 0xAC00) % 28
        if jong == 0 or jong == 8:
            return f"{text}로"
        return f"{text}으로"
    return f"{text}으로"
