# 5. 런타임 플로우

## 5.1 통합 체인 순서

Operator -> Commander: run 시작  
Commander -> Strategist: 테마/섹터 + 후보 종목 Top-N 생성  
Strategist -> Commander: `strategist_output` (`themes`, `candidates`) 반환  
Commander -> Scanner: 전략가 후보만 스코어링  
Scanner -> Commander: 랭킹 + `top_stock` 반환  
Commander -> Monitor: `top_stock` 진입/청산 판단  
Monitor -> Commander: `OrderIntent` (BUY/SELL/NOOP)  
Commander -> Supervisor: 승인 요청  
Supervisor -> Commander: approve/reject/modify  
Commander -> Executor: 승인된 경우만 실행  
Executor -> Broker(Mock/Real): 주문/정정/상태 조회  
Executor -> EventLog: 이벤트 기록  
Commander -> Reporter: 보고서 생성

## 5.2 Intent 상태 머신

(created)  
-> (pending_approval)  
-> (approved | rejected)  
-> (executing)  
-> (executed | failed)  
-> (settled/closed)

규칙: 동일 `intent_id`는 `executing` 상태에 중복 진입하면 안 된다.
