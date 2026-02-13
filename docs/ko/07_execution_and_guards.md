# 7. 실행 통제/가드/승인 모델

## 7.1 승인 모드(Approval Mode)
- auto: Supervisor approve 시 즉시 실행(단, 가드 통과 필요)
- manual: SupervisorDecision은 "pending"으로 유지 → 운영자 승인 필요

(레거시) AUTO_APPROVE 호환:
- true → auto
- false → manual
- "auto"/"manual" 문자열도 지원 가능

## 7.2 Guard 우선순위
1) EXECUTION_ENABLED == false → 항상 차단
2) KIWOOM_MODE == real AND ALLOW_REAL_EXECUTION != true → 차단
3) SYMBOL_ALLOWLIST 불일치 → 차단
4) MAX_QTY 초과 → 차단
5) MAX_NOTIONAL 초과 → 차단
6) Idempotency(이미 실행된 intent) → 차단

## 7.3 “진짜 approve API” (M16 권장)
- approve(intent_id) 호출 → intent 상태 approved
- execution_enabled이면 즉시 Execution Layer로 이어짐
- 수동 승인 흐름이 재현 가능(테스트 가능)

## 7.4 운영 안전 권장값
- 기본값: EXECUTION_ENABLED=false
- real 모드: 반드시 allowlist 설정
- max_notional: 계좌 규모 대비 보수적으로
