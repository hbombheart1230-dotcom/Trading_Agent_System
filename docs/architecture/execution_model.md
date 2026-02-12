# Execution Model (M15)

이 문서는 Trading_Agent_System의 **Execution Layer**와 안전장치(Guard) 모델을 요약한다.

## 원칙

- Agent Layer는 **판단/계획/의도(intent) 생성**까지만 담당
- 실제 API 호출은 **Execution Layer**에서만 수행
- 실행은 항상 **승인/가드**를 통과해야 함

## 구성

- Agent 레벨 실행 조정: `libs/agent/executor.py`
- 실제 실행(브로커/API 호출): `libs/execution/executor.py` + `libs/execution/executors/*`

## Guards

### 1) Idempotent Approve
- 동일한 의도(intent)가 중복 실행되지 않도록 방지

### 2) Symbol Allowlist Guard
- 환경변수 `SYMBOL_ALLOWLIST` 기반
- 값이 비어 있으면 비활성(allow-all)

### 3) Execution Enabled Guard
- 환경변수 `EXECUTION_ENABLED=false` 인 경우
  - 승인/auto 모드이더라도 **실제 실행은 차단**

### 4) Kiwoom Mode 분기
- `KIWOOM_MODE=mock|real`
- mock: 모의투자/시뮬레이터로 라우팅
- real: 실전 API 라우팅

## Approval

- `APPROVAL_MODE=auto|manual`
- (호환) `AUTO_APPROVE`는 다음처럼 해석:
  - `AUTO_APPROVE=auto|manual` → 모드로 사용
  - `AUTO_APPROVE=true` → auto로 간주(레거시)
