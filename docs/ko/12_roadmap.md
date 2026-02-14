# 12. 로드맵 (M16+)

## M16: 승인 API 정식화
- approve(intent_id) / reject(intent_id) / preview(intent_id)
- 수동 승인 모드 재현 가능성 보장

## M17: Settings 단일 소스화
- approval_mode를 공식 Settings 필드로 승격
- 직접 env 조회 제거(단일 경로)

## M18: LangGraph 정식 오케스트레이션
- agent 역할을 graphs/ 노드로 정식 매핑
- 전이/재시도/취소 정책 정의

## M19+: 운영 스택 강화
- 메트릭 대시보드
- 알림 정책(Slack/Email)
- 감사 로그 아카이빙

## M20: LLM 전략가 신뢰성
- M20-1:
  - provider 스모크 커버리지(config/timeout/response-shape)
  - decide_trade 연동 스모크 + 안전 fallback
  - 전략가 전용 운영 스모크 스크립트(실행 파이프라인 미호출)
- M20-2:
  - OpenRouter chat-completions 응답 content에서 JSON 추출/파싱
  - `{"intent": ...}` 구조로 정규화 후 intent 스키마 정합성 보장
  - 일시적 오류 재시도/백오프 + attempts 메타데이터
  - `stage=strategist_llm` 이벤트 텔레메트리 추가
- M20-3:
  - legacy `libs.llm.router` import 호환성 복구(`ChatMessage`)
  - legacy router import/payload 경로 회귀 테스트 추가
- M20-4:
  - smoke CLI에서 strategist LLM 이벤트 가시성 옵션 추가
    (`--show-llm-event`, `--require-llm-event`)
  - `strategist_llm` 결과 이벤트 운영 조회 CLI 추가
- M20-5:
  - 일일 metrics 리포트에 strategist LLM 신뢰성 집계 추가
  - 성공률/지연/재시도/오류 유형 요약 제공
- M20-6:
  - strategist LLM 텔레메트리에 `prompt_version` / `schema_version` 필드 추가
  - 버전 분포 메트릭(`prompt_version_total`, `schema_version_total`) 집계 추가

## M21-M30 (프로그램 플랜)
- M21: Commander 중심 LangGraph 통합(단일 표준 런타임 경로)
- M22: 스킬 네이티브 Scanner/Monitor 고도화(`market.quote`, `account.orders`, `order.status`)
- M23: 런타임 복원력(circuit breaker + safe degrade 모드)
- M24: 실행 안전성 강화(엄격한 idempotency + guard 우선순위)
- M25: 관측성/알림 운영 체계 고도화(SLI/SLO 지표)
- M26: 전략 평가 프레임워크(replay/backtest + 승격 기준)
- M27: 멀티 전략 포트폴리오 배분/충돌 조정
- M28: 배포/런타임 플랫폼화(container + scheduler + rollback)
- M29: 거버넌스/감사/복구 체계(보관, 무결성, DR 리허설)
- M30: 프로덕션 준비 게이트(최종 안전/운영 승인)

상세 계획:
- `docs/plan/m20_to_m30_master_plan.md`
