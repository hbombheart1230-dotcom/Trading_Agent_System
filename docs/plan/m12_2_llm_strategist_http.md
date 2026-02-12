# M12-2 LLM Strategist (HTTP) + Safe Fallback

- 날짜: 2026-02-11
- 목표: 모의 운용 중에도 파이프라인이 멈추지 않도록 **LLM 실패 시 규칙 기반으로 자동 폴백**한다.

## Env
- `AI_STRATEGIST_PROVIDER=openai`
- `AI_STRATEGIST_API_KEY=...`
- `AI_STRATEGIST_ENDPOINT=https://...`  (full URL, POST)
- `AI_STRATEGIST_MODEL=...` (옵션)
- `AI_STRATEGIST_TIMEOUT_SEC=15` (옵션)
- `AI_STRATEGIST_MAX_TOKENS=256` (옵션)

## 응답 스키마(권장)
엔드포인트는 아래 형태로 응답하도록 맞추는 것을 권장한다:

```json
{"intent": {"action":"BUY","symbol":"005930","qty":1,"price":70000,"order_type":"limit"}, "rationale":"...", "meta":{...}}
```

`intent`가 dict가 아니면 예외를 발생시키고, decide_trade에서 **RuleStrategist로 폴백**한다.

## 안전 설계
- endpoint/key 누락: factory 단계에서 RuleStrategist로 폴백
- endpoint 호출 실패/응답 깨짐: decide_trade에서 RuleStrategist로 폴백
