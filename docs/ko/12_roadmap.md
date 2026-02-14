# 12. 로드맵 (M16+)

## M16: 승인 API 정식화
- approve(intent_id)/reject(intent_id)/preview(intent_id)
- manual 모드 완전 재현 가능

## M17: Settings 단일화
- approval_mode 정식 필드화
- env 직접 조회 코드 제거(단일 진실 소스)

## M18: LangGraph 정식 파이프라인
- nodes/에 agent role 매핑
- 상태 전이/재시도/취소 정책 확립

## M19+: 운영 스택 강화
- 메트릭 대시보드
- 알림 정책(Slack/Email)
- 감사 로그 아카이빙

## M20: LLM 전략가 신뢰성
- M20-1:
  - provider 스모크 커버리지(config/timeout/response-shape)
  - decide_trade 연동 스모크 + 안전한 fallback
  - 전략가 전용 운영 스모크 스크립트(실행 파이프라인 미호출)
- M20-2:
  - OpenRouter chat-completions 응답 content에서 JSON 추출/파싱
  - `{"intent": ...}` 구조로 어댑트 후 표준 intent 스키마 정규화
  - 일시적 오류 재시도/백오프 + attempts 메타데이터
  - `stage=strategist_llm` 이벤트 텔레메트리 추가
