# M12 AI Hook (Strategist Contract)

- 날짜: 2026-02-11
- 목적: 전략(의사결정)을 **교체 가능한 인터페이스**로 분리해 LLM/규칙/하이브리드 모두 지원한다.
- 주의: M12에서는 외부 LLM 호출을 하지 않는다(프롬프트/컨트랙트/주입 포인트만 만든다).

## 산출물
- `libs/ai/strategist.py`
  - `Strategist` Protocol
  - `StrategyInput`, `StrategyDecision`
  - `RuleStrategist` (deterministic baseline)

- `graphs/nodes/decide_trade.py`
  - `state['strategist']`가 있으면 `strategist.decide()` 결과로 intent 생성
  - 없으면 기존 M11-1 룰 기반 의사결정 유지

## 다음 확장 (M12-1)
- `PromptStrategist` 추가 (프롬프트 스키마만 정의)
- provider 설정(.env) 기반 전략 라우팅
