# 4. 논리 아키텍처

## 4.1 레이어 정의
1) Agent Layer: 판단/의도 생성 (side-effect 금지)
2) Approval Layer: Supervisor 승인 결정
3) Execution Layer: 실제 호출, guard 적용, idempotency 보장
4) Contract Layer: DTO/IO 계약, api catalog
5) Observability Layer: 이벤트/메트릭/감사

## 4.2 컴포넌트 책임

### Agent Layer
- Strategist: 후보군/시나리오/제약 정의
- Scanner: API/데이터를 통해 후보 평가 및 정량화
- Monitor: 감시 + OrderIntent 생성 (실행 금지)
- Reporter: 로그 재생/요약/개선안

### Approval Layer (Supervisor)
- 정책 검증: max qty/notional, 허용 심볼, 일일 손실 제한 등
- 승인 모드: auto/manual
- 수정 승인: modify(수량/가격/타입 수정)

### Execution Layer
- Guard evaluation
- Broker routing (mock/real)
- Idempotent execute: 동일 intent 재실행 방지
- Execution result 기록

## 4.3 데이터 흐름(Contract 중심)
- Raw API 응답은 Skill 내부에서만 사용
- Agent/Reporter는 DTO만 소비
- 계약 파손 시 시스템 전체가 불안정해지므로, DTO 변경은 “버저닝”으로만
