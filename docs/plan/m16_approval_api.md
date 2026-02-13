# M16 승인(Approval) API

## 목표
- **Supervisor(감독관)** 단계에서 주문 의도(OrderIntent)를 2단계 승인(2-phase approval)으로 관리한다.
- 승인/거절/재시도 결과가 **idempotent(멱등)** 하게 동작하도록 보장한다.
- `DRY_RUN` 환경에서도 동일한 플로우로 테스트 가능해야 한다.

## 구성요소
- **IntentStore**: `intents.jsonl`에 의도/상태를 기록(append-only)하여 재실행 시 중복 실행을 막는다.
- **TwoPhaseSupervisor**: 정책(policy) 기반으로 `approve | reject | retry_scan` 결정.
- **Approval API(또는 함수)**: 특정 `intent_id`를 승인 처리하고, 승인된 intent만 Executor로 전달.

## 데이터(예시)
- intent 레코드(개념)
```json
{
  "intent_id": "2026-..-..-..",
  "symbol": "005930",
  "action": "BUY",
  "qty": 1,
  "risk_score": 0.12,
  "confidence": 0.78,
  "status": "pending",  // pending|approved|rejected|executed
  "created_at": "..."
}
```

## 승인 플로우
1. Monitor가 **OrderIntent(초안)** 을 state에 추가하거나 store에 저장할 준비를 한다.
2. Supervisor가 policy를 적용해 intent를 `approve/reject/retry_scan`으로 분기한다.
3. `approve`인 경우:
   - store에 `approved` 마킹(멱등: 이미 approved면 그대로)
   - Executor는 **approved intent만 실행**
4. `reject`인 경우:
   - store에 `rejected` 마킹
   - 실행 없음
5. `retry_scan`인 경우:
   - scan retry count 증가
   - Scanner로 루프

## 멱등성(idempotency)
- 동일 `intent_id`에 대해 `approve()`를 여러 번 호출해도 결과는 동일해야 한다.
- 이미 `executed` 상태인 intent는 다시 실행되지 않아야 한다.

## 환경 변수/설정
- `DRY_RUN=1`: 외부 네트워크/API 호출 최소화, 실행은 모의로 처리.
- `EXECUTION_ENABLED=false`(또는 유사 플래그): 승인되더라도 실제 주문 전송 차단(옵션).

## 테스트 포인트
- 승인 호출을 2회 수행해도 실행은 1회만 발생
- 승인 전 intent 실행 불가
- 승인/거절 상태가 store에 누적 기록되고 재실행 시 반영
