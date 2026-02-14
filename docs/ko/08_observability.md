# 8. 관측성(Observability)

## 8.1 목표
- 모든 run은 run_id로 추적 가능
- 승인/가드 판단 근거가 로그에 남아야 함
- 장애 시 “어디서 왜 멈췄는지” 즉시 알 수 있어야 함

## 8.2 이벤트 로그(JSONL)
필드 예시:
- ts, run_id, stage, event(start/end/error), payload

payload에는:
- intent_id
- guard 결과(allowed/blocked + reason)
- approve 결과
- order_id(있으면)

## 8.3 메트릭(권장)
- intents_created_total
- intents_approved_total
- intents_blocked_total (by guard_reason)
- execution_latency_seconds
- api_error_total (by api_id)
- strategist_llm.success_rate
- strategist_llm.latency_ms
- strategist_llm.attempts
- strategist_llm.error_type_total

## 8.4 감사(Audit)
- real 실행은 항상 별도 audit tag 부여
- 환경변수 변경 이력(가능하면) 기록
