# 2. 설계 원칙 및 불변 규칙

## 2.1 불변 규칙 (Non-negotiable)
1) Monitor는 주문을 직접 호출할 수 없다. (코드/구조적으로 금지)
2) Execution Layer는 승인 없이 실행할 수 없다.
3) Guard는 승인보다 우선한다. (승인=OK여도 가드가 NO면 실행 금지)
4) DTO/IO 계약은 하위호환을 깨지 않는다.
5) 로그(Event Logging)는 관측만 한다. (로깅이 제어흐름 바꾸면 안됨)

## 2.2 설계 원칙
- Single Source of Truth: Settings/env/Config는 단일 경로로 읽는다.
- Determinism where possible: Risk/Guard는 결정론적이어야 한다.
- Idempotency: 동일 intent_id는 중복 실행되지 않는다.
- Small surface area: 승인/실행 API는 최소 표면적을 유지한다.
- Safe defaults: 기본값은 “실행 금지”가 되어야 한다.

## 2.3 실수 방지 가이드
- real 모드 기본 차단: ALLOW_REAL_EXECUTION 없으면 real 실행 불가
- EXECUTION_ENABLED=false이면 무조건 실행 금지
- allowlist 비어있으면 allow-all이 아니라, 운영 정책에 따라 권장값을 정의
