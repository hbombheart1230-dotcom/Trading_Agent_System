# M12-3 Intent Schema Normalization + Validation

- 날짜: 2026-02-11
- 목표: Strategist(Rule/LLM)가 어떤 형태로 intent를 내더라도 **단일 스키마로 정규화**하고,
  잘못된 출력은 **NOOP로 다운그레이드**하여 안정적으로 운용한다.

## Canonical Intent Schema
```json
{
  "action": "BUY|SELL|NOOP",
  "symbol": "005930",
  "qty": 1,
  "price": 70000,
  "order_type": "limit|market",
  "order_api_id": "ORDER_SUBMIT",
  "rationale": "..."
}
```

## Validation Rules (핵심)
- BUY/SELL 인데 `symbol` 없거나 `qty<=0` → NOOP
- limit 인데 `price<=0` 또는 None → NOOP (market이면 허용)

## Logging
- decide_trade에서 best-effort로 `stage=decision, event=trace`를 `EVENT_LOG_PATH`에 기록
  - `decision_packet` + `trace` (raw_intent 포함)

## 변경 파일
- `libs/ai/intent_schema.py`
- `graphs/nodes/decide_trade.py`
