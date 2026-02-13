# Kiwoom Agentic Trader Plan v2 (Current Code Baseline)

> 기준: 현재 구현은 M8까지 완료된 상태이며, “휴먼 승인”은 존재하지 않습니다.  
> 모든 주문 실행은 **Supervisor 승인(자동 승인/차단)** 을 반드시 통과해야 합니다.  
> 모의/실전 차이는 **Executor(mock/real)** 로만 분기합니다.

---

## 0. 핵심 원칙 (Non-negotiable)

1. **No Human Approval**  
   - 사용자가 매번 직접 승인하는 단계는 설계에 포함하지 않습니다.

2. **Supervisor Approval is Mandatory**  
   - 주문 실행은 항상 `Supervisor.allow()`를 거친 뒤에만 가능합니다.

3. **Mock/Real is Execution-only**  
   - mock/real 분기는 `Executor` 레이어에서만 처리합니다.
   - `EXECUTION_ENABLED=true` 없이는 real 실행이 불가합니다.

4. **Decision Packet Contract**  
   - AI/전략의 출력은 항상 `TradeDecisionPacket(intent, risk, exec_context)` 형태로 고정합니다.
   - 실행은 `execute_from_packet` 단일 노드로 닫습니다.

---

## 1. Current Status (DONE)

### M1–M2: Logging + API Catalog
- EventLogger 기반 이벤트 로그
- Excel 기반 API → JSONL 카탈로그 생성
- 테스트 통과

### M3–M5: API Discovery → Plan → Request Builder
- 검색(top_k) 기반 후보 탐색
- Planner로 select/clarify 결정
- RequestBuilder로 required params 확인/질문 생성

### M6: HTTP/Token/Read-only Account + ApiResponse
- HTTP Client (timeout/retry/dry-run)
- Token Client (cache + refresh), **dry-run 시 자격증명 불필요**
- Read-only 계좌 조회 클라이언트
- 공통 응답 구조 `ApiResponse`

### M7: Supervisor + Order Dry-run
- Supervisor(리스크 가드레일) 자동 승인/차단
- OrderClient(dry-run only): 네트워크 호출 없이 주문 요청 형태만 생성
- 데모 파이프라인

### M8: Executors + Decision Packet + Wiring
- Executors 분리: `MockExecutor` / `RealExecutor(guarded)`
- Decision Packet 계약: `TradeDecisionPacket`
- Wiring: `execute_from_packet`로 Supervisor → Executor 실행 라인 완결

---

## 2. Plan v2 (NEXT)

## M9: Read Layer 표준화 (데이터 수집/요약)
**목표:** 전략/감독관이 사용할 입력을 “항상 같은 형태(snapshot)”로 제공

### 범위(권장 최소)
- account/positions: 잔고/보유 종목 요약
- price(최소 1개): 종목 1개 가격/체결/호가 중 하나
- output:
  - `portfolio_snapshot`
  - `market_snapshot`

### 산출물(예시)
- `libs/read/*` 또는 `libs/kiwoom/read_*` 계열
- `graphs/nodes/build_market_snapshot.py`
- `graphs/nodes/build_portfolio_snapshot.py`
- tests

---

## M10: State/Portfolio 저장소 + 계산 (Supervisor 입력 자동화)
**목표:** Supervisor 입력을 사람이 넣지 않고 저장소가 자동 계산

### 자동 산출(필수)
- `open_positions`
- `daily_pnl_ratio`
- `last_order_epoch`

### 선택
- `per_trade_risk_ratio` 계산 규칙(간단 버전부터)

### 저장(권장)
- `./data/state.json` 유지 (단일 파일로 시작)

### 산출물(예시)
- `libs/storage/state_store.py`
- `libs/storage/portfolio_store.py`
- `graphs/nodes/update_state_after_execution.py`
- tests

---

## 3. Plan v2 (LATER)

### M11: Monitor Loop (폴링 기반 운영)
- 주기적으로 snapshot 갱신
- 조건 충족 시 청산 intent 생성 → packet → execute

### M12: Real Execution Enable Checklist (운영 가드)
- `EXECUTION_MODE=real` + `EXECUTION_ENABLED=true` 전 체크리스트
- 리스크 상한/쿨다운 검증
- 로그/리포트/롤백 전략

### (옵션) News/RAG
- M9 이후 인터페이스만 고정하고, 소스는 나중에 교체 가능하도록 설계

---

## 4. Decisions to Lock (3 items)

1. **M9에 price 조회 포함 여부**
   - 추천: 포함(최소 1개) → 전략/리스크 계산 확장 용이

2. **M10 daily_pnl_ratio 정의**
   - 추천: 당일 기준 “실현+평가 합산” 단순 버전부터

3. **State 저장 단위**
   - 추천: `./data/state.json` 단일 파일 유지 (추후 분리 가능)

---

## 5. Execution Controls (Env)

```env
# execution
EXECUTION_MODE=mock     # mock | real
EXECUTION_ENABLED=false # true일 때만 real HTTP 실행 허용

# risk guardrails
RISK_DAILY_LOSS_LIMIT=0.02
RISK_PER_TRADE_LOSS_LIMIT=0.005
RISK_MAX_POSITIONS=1
RISK_ORDER_COOLDOWN_SEC=60
```

---

## 6. Current End-to-End Flow (fixed)

1) 전략/AI → `TradeDecisionPacket` 생성  
2) `execute_from_packet`  
3) Supervisor 승인/차단  
4) Executor(mock/real) 실행  
5) (M10 이후) State/Portfolio 갱신
