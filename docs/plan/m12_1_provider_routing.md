# M12-1 Strategist Provider Routing (Env-based)

- 날짜: 2026-02-11
- 목적: 모의 운용 중에도 시스템이 **키 없이 안전하게 동작**하고,
  키가 준비되면 env만으로 LLM Strategist를 **무중단으로 교체**할 수 있게 한다.

## Env
- `AI_STRATEGIST_PROVIDER`
  - `"" | rule` : RuleStrategist
  - `openai` : OpenAIStrategist (placeholder, M12-2에서 실제 호출 구현)
  - 그 외 : RuleStrategist로 fallback
- `AI_STRATEGIST_API_KEY`
  - provider가 `openai`인데 키가 비어있으면 RuleStrategist로 fallback (안전)
- `AI_STRATEGIST_MODEL`
  - 선택값 (provider에 전달)

## 구현
- `libs/ai/strategist_factory.py` : env → strategist 인스턴스 생성
- `libs/ai/providers/openai_provider.py` : placeholder (NOOP 반환)
- `graphs/nodes/decide_trade.py`
  - state['strategist'] 없으면 factory로 생성 후 state에 캐시
  - strategist 실패 시 NOOP로 안전 처리

## 다음 (M12-2)
- OpenAI/사내 LLM endpoint 실제 HTTP 호출 구현
- 프롬프트/스키마 고정 + 응답 검증 + rate limit/backoff
